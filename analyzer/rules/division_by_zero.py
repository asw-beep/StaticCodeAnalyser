"""Division-by-zero rule.

Inspects every binary op whose operator divides (`/`, `//`, `%`) and checks
the right operand:

- Literal `0` / `0.0` -> ERROR (definite)
- Name we can prove was last assigned a literal `0` in the same scope -> ERROR
- Anything else (variable, expression, call) -> INFO (possible)

The "possible" tier is deliberately quiet (INFO, not WARNING). Most divisions
are safe in practice; flagging every one as a warning trains users to ignore
the analyzer.

Limitations (deliberate):
- No interprocedural analysis.
- No flow-sensitive narrowing (e.g. `if x != 0: a / x` still INFO).
- We trace constant assignments only at the immediate scope, no aliasing.
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


def _collect_constant_zero_names(scope_body: list[ast.stmt]) -> set[str]:
    """Names whose ONLY assignment in this scope is a literal 0."""
    assigns: dict[str, list[ast.expr]] = {}
    for node in ast.walk(ast.Module(body=scope_body, type_ignores=[])):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    assigns.setdefault(tgt.id, []).append(node.value)
    return {name for name, vals in assigns.items() if all(_is_zero_literal(v) for v in vals)}


class _DivVisitor(ast.NodeVisitor):
    def __init__(self, zero_names: set[str]) -> None:
        self.zero_names = zero_names
        self.findings: list[Finding] = []

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, _DIV_OPS):
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

    def check(self, tree: ast.Module) -> list[Finding]:
        # Build per-scope sets of "always zero" names. Module + each function.
        findings: list[Finding] = []

        def run(body: list[ast.stmt]) -> None:
            zero_names = _collect_constant_zero_names(body)
            v = _DivVisitor(zero_names)
            for stmt in body:
                # Don't descend into nested function bodies — they're their own scope.
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    run(stmt.body)
                else:
                    v.visit(stmt)
            findings.extend(v.findings)

        run(tree.body)
        return sorted(findings, key=lambda f: f.line)
