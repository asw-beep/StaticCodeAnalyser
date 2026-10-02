"""Division-by-zero rule.

Inspects every binary op whose operator divides (`/`, `//`, `%`) and checks
the right operand:

- Literal `0` / `0.0` -> ERROR (definite)
- Name whose EVERY binding in the same scope is a literal `0` -> ERROR.
  Any other binding — `x += 1`, `x, y = ...`, `for x in`, `with ... as x`,
  `x := ...`, a parameter, or a `global`/`nonlocal` declaration — means we
  can't prove it's zero, so it drops to INFO.
- Anything else (variable, expression, call) -> INFO (possible)

Not division at all, so never reported:
- a string divisor (`base / "file.txt"` — pathlib joins)
- `%` with a string on the left (`"hi %s" % name` — printf formatting)

The "possible" tier is deliberately quiet (INFO, not WARNING). Most divisions
are safe in practice; flagging every one as a warning trains users to ignore
the analyzer.

Limitations (deliberate):
- No interprocedural analysis.
- No flow-sensitive narrowing (e.g. `if x != 0: a / x` still INFO).
- We trace constant assignments only at the immediate scope, no aliasing.
- Comprehension targets are counted as bindings of the enclosing scope. That
  can only downgrade an ERROR to INFO, never create a false ERROR.
"""

from __future__ import annotations

import ast

from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_DIV_OPS = (ast.Div, ast.FloorDiv, ast.Mod)


def _op_label(op: ast.operator) -> str:
    return {ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%"}[type(op)]


def _is_zero_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and node.value == 0


_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _walk_scope(body: list[ast.stmt]):
    """Like ast.walk over `body`, but don't descend into nested scopes."""
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _SCOPE_NODES):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _is_str(node: ast.expr) -> bool:
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes))
    )


def _collect_constant_zero_names(scope_body: list[ast.stmt], params: set[str]) -> set[str]:
    """Names whose ONLY bindings in this scope are literal-0 assignments."""
    zero_targets: set[int] = set()  # id() of Name nodes bound by `name = 0`
    for node in _walk_scope(scope_body):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            if _is_zero_literal(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                zero_targets.update(id(t) for t in targets if isinstance(t, ast.Name))

    zero: set[str] = set()
    rebound: set[str] = set(params)
    for node in _walk_scope(scope_body):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            (zero if id(node) in zero_targets else rebound).add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            rebound.update(node.names)
    return zero - rebound


def _params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func.args
    out = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
    if args.vararg:
        out.add(args.vararg.arg)
    if args.kwarg:
        out.add(args.kwarg.arg)
    return out


class _DivVisitor(ast.NodeVisitor):
    def __init__(self, zero_names: set[str]) -> None:
        self.zero_names = zero_names
        self.findings: list[Finding] = []
        self.nested: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []

    # Nested functions/classes are their own scope: the rule runs them
    # separately. Decorators, defaults and bases evaluate in THIS scope.
    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for d in node.decorator_list + node.args.defaults:
            self.visit(d)
        for d in node.args.kw_defaults:
            if d is not None:
                self.visit(d)
        self.nested.append(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for d in node.decorator_list + node.bases:
            self.visit(d)
        self.nested.append(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        is_formatting = isinstance(node.op, ast.Mod) and _is_str(node.left)
        if isinstance(node.op, _DIV_OPS) and not is_formatting and not _is_str(node.right):
            rhs = node.right
            op = _op_label(node.op)
            if _is_zero_literal(rhs):
                self.findings.append(
                    Finding(
                        severity="ERROR",
                        message=f"Division by zero ('{op}' with literal 0)",
                        line=node.lineno,
                        rule="division-by-zero",
                    )
                )
            elif isinstance(rhs, ast.Constant) and isinstance(rhs.value, (int, float)):
                # Provably non-zero numeric literal: safe, no finding.
                self.generic_visit(node)
                return
            elif isinstance(rhs, ast.Name) and rhs.id in self.zero_names:
                self.findings.append(
                    Finding(
                        severity="ERROR",
                        message=f"Division by zero ('{op}' by '{rhs.id}', always 0)",
                        line=node.lineno,
                        rule="division-by-zero",
                    )
                )
            else:
                self.findings.append(
                    Finding(
                        severity="INFO",
                        message=f"Possible division by zero ('{op}' with non-constant divisor)",
                        line=node.lineno,
                        rule="division-by-zero",
                    )
                )
        self.generic_visit(node)


class DivisionByZeroRule(Rule):
    name = "division-by-zero"
    description = "Division or modulo by zero (definite) or by a non-constant (possible)"

    def check(self, tree: ast.Module) -> list[Finding]:
        # Build per-scope sets of "always zero" names. Module + each function.
        findings: list[Finding] = []

        def run(body: list[ast.stmt], params: set[str]) -> None:
            v = _DivVisitor(_collect_constant_zero_names(body, params))
            for stmt in body:
                v.visit(stmt)
            findings.extend(v.findings)
            for nested in v.nested:
                run(nested.body, set() if isinstance(nested, ast.ClassDef) else _params(nested))

        run(tree.body, set())
        return sorted(findings, key=lambda f: f.line)
