"""SQL-injection rule.

Flags `.execute(...)` / `.executemany(...)` calls (the canonical DB-API
cursor methods — matched by attribute name, on any receiver: `cursor.execute`,
`self.cursor.execute`, `conn.execute`, ...) whose SQL argument is built
dynamically instead of passed as a parameterized query:

- f-string             -> `ast.JoinedStr`
- string concatenation -> `ast.BinOp` with `ast.Add`
- `%` formatting       -> `ast.BinOp` with `ast.Mod`
- `"...".format(...)`  -> `ast.Call` whose func is an attribute `.format`

A plain string constant as the first argument is safe regardless of a second
"params" argument — that's exactly the parameterized-query pattern this rule
wants to encourage:

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))  # safe

Limitations (deliberate):
- Shape-based, not taint-based: `cursor.execute(query)` where `query` was
  built dynamically several lines earlier is not traced.
- Matches on method name alone, not on the receiver's type — a non-DB
  `.execute()` method with the same name would also be flagged.
"""

from __future__ import annotations

import ast

from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_EXEC_METHODS = {"execute", "executemany"}


def _dynamic_sql_reason(node: ast.expr) -> str | None:
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

    def check(self, tree: ast.Module) -> list[Finding]:
        v = _SqlInjectionVisitor()
        v.visit(tree)
        return sorted(v.findings, key=lambda f: f.line)
