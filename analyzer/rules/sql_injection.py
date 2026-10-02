"""SQL-injection rule.

Flags `.execute(...)` / `.executemany(...)` calls (the canonical DB-API
cursor methods — matched by attribute name, on any receiver: `cursor.execute`,
`self.cursor.execute`, `conn.execute`, ...) whose SQL argument is built
dynamically instead of passed as a parameterized query:

- f-string             -> `ast.JoinedStr`
- string concatenation -> `ast.BinOp` with `ast.Add`
- `%` formatting       -> `ast.BinOp` with `ast.Mod`
- `"...".format(...)`  -> `ast.Call` whose func is an attribute `.format`

The query is followed through local variables with a forward dataflow
analysis (`analyzer/dataflow.py`), so building it earlier is caught too:

    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)            # flagged, pointing back at line 1

while building a *parameterized* query in steps is not:

    query = "SELECT * FROM users WHERE a = ?"
    query += " AND b = ?"            # both pieces are literals
    cursor.execute(query, (a, b))    # safe

For the traced case a piece counts as dynamic only if it isn't a string
literal or a "static" variable — one whose every assignment in the scope is
itself static.

Limitations (deliberate):
- Intra-procedural: `cursor.execute(build_query(x))` is not traced into
  `build_query`.
- Matches on method name alone, not on the receiver's type — a non-DB
  `.execute()` method with the same name would also be flagged.
- Detects dynamic *construction*, not untrusted *input*: see the
  `tainted-data` rule for source-to-sink tracking.
"""

from __future__ import annotations

import ast

from analyzer.dataflow import Env, Origin, analyze_flow, walk_scope
from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_EXEC_METHODS = {"execute", "executemany"}
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _dynamic_sql_reason(node: ast.expr) -> str | None:
    """Shape of an inline SQL argument built dynamically at the call site."""
    if isinstance(node, ast.JoinedStr):
        return "an f-string"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            return "string concatenation"
        if isinstance(node.op, ast.Mod):
            return "'%' formatting"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return "str.format()"
    return None


# --- traced case: following the query through variables ---------------------


def _is_str_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _string_names(body: list[ast.stmt]) -> tuple[set[str], set[str]]:
    """(static, stringy) names for the scope.

    static:  every binding is a static string expression, so the value is a
             compile-time constant.
    stringy: at least one binding is string-shaped, so `x + y` with x
             stringy is a string concatenation, not arithmetic.
    """
    nodes = [n for stmt in body for n in walk_scope(stmt)]
    values: dict[str, list[ast.expr]] = {}  # name -> right-hand sides of x = .. / x += ..
    plain_targets: set[int] = set()  # id() of Name nodes that are those x's
    for node in nodes:
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
            for t in node.targets:
                values.setdefault(t.id, []).append(node.value)
                plain_targets.add(id(t))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            values.setdefault(node.target.id, []).append(node.value)
            plain_targets.add(id(node.target))
    # Any other binding (for-target, with-as, unpacking, walrus, ...) disqualifies.
    other_bound = {
        n.id
        for n in nodes
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and id(n) not in plain_targets
    }

    static: set[str] = set()
    changed = True
    while changed:  # fixed point: `b = a + "x"` is static once `a` is
        changed = False
        for name, rhs in values.items():
            if name in static or name in other_bound:
                continue
            if all(_is_static(v, static) for v in rhs):
                static.add(name)
                changed = True
    stringy = {
        name
        for name, rhs in values.items()
        if any(_is_static(v, static) or isinstance(v, ast.JoinedStr) or _has_str_operand(v) for v in rhs)
    }
    return static, stringy


def _has_str_operand(node: ast.expr) -> bool:
    return isinstance(node, ast.BinOp) and (_is_str_literal(node.left) or _is_str_literal(node.right))


def _is_static(node: ast.expr, static: set[str]) -> bool:
    if _is_str_literal(node):
        return True
    if isinstance(node, ast.Name):
        return node.id in static
    if isinstance(node, ast.JoinedStr):
        return not any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_static(node.left, static) and _is_static(node.right, static)
    return False


def _make_evaluator(static: set[str], stringy: set[str]):
    def str_like(node: ast.expr, env: Env) -> bool:
        if isinstance(node, ast.Name) and node.id in stringy:
            return True
        return _is_static(node, static) or isinstance(node, ast.JoinedStr) or dyn(node, env) is not None

    def dyn(node: ast.expr, env: Env) -> Origin | None:
        if isinstance(node, ast.Name):
            return env.get(node.id)
        if isinstance(node, ast.JoinedStr):
            if any(isinstance(v, ast.FormattedValue) for v in node.values):
                return Origin(node.lineno, "an f-string")
            return None
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            inner = [o for o in (dyn(node.left, env), dyn(node.right, env)) if o is not None]
            if inner:
                return min(inner)
            if isinstance(node.op, ast.Add):
                if (str_like(node.left, env) or str_like(node.right, env)) and not _is_static(node, static):
                    return Origin(node.lineno, "string concatenation")
            elif str_like(node.left, env) and not _is_str_literal(node.right):
                return Origin(node.lineno, "'%' formatting")
            return None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            if node.func.attr == "format" and str_like(receiver, env) and (node.args or node.keywords):
                return Origin(node.lineno, "str.format()")
            if node.func.attr == "join" and _is_str_literal(receiver) and node.args:
                if not all(_is_static(e, static) for e in getattr(node.args[0], "elts", [None])):
                    return Origin(node.lineno, "str.join()")
        return None

    return dyn


def _traced_findings(body: list[ast.stmt]) -> list[Finding]:
    dyn = _make_evaluator(*_string_names(body))
    flow = analyze_flow(body, dyn)
    findings = []
    for item, env in flow.items_with_env():
        if item.kind == "nop" or isinstance(item.node, (*_SCOPES, ast.ClassDef)):
            continue
        for node in walk_scope(item.node):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in _EXEC_METHODS or not node.args:
                continue
            sql_arg = node.args[0]
            if _dynamic_sql_reason(sql_arg):
                continue  # inline case: reported by the visitor with its own message
            origin = dyn(sql_arg, env)
            if origin is not None:
                findings.append(
                    Finding(
                        severity="ERROR",
                        message=(
                            f"SQL query built with {origin.desc} (line {origin.line}) instead of "
                            f"a parameterized query in '{node.func.attr}()'"
                        ),
                        line=sql_arg.lineno,
                        rule="sql-injection",
                    )
                )
    return findings


# --- inline case ----------------------------------------------------------------


class _SqlInjectionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _EXEC_METHODS and node.args:
            sql_arg = node.args[0]
            reason = _dynamic_sql_reason(sql_arg)
            if reason:
                self.findings.append(
                    Finding(
                        severity="ERROR",
                        message=(
                            f"SQL query built with {reason} instead of a parameterized "
                            f"query in '{func.attr}()'"
                        ),
                        line=sql_arg.lineno,
                        rule="sql-injection",
                    )
                )
        self.generic_visit(node)


class SqlInjectionRule(Rule):
    name = "sql-injection"
    description = "SQL passed to execute() built dynamically instead of parameterized"

    def check(self, tree: ast.Module) -> list[Finding]:
        v = _SqlInjectionVisitor()
        v.visit(tree)
        findings = v.findings + _traced_findings(tree.body)
        for node in ast.walk(tree):
            if isinstance(node, _SCOPES):
                findings.extend(_traced_findings(node.body))
        return sorted(findings, key=lambda f: f.line)
