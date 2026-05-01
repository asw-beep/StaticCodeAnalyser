"""Dead-code rule.

Flags statements that appear after a terminal statement in the same block.
A "terminal" statement unconditionally exits the current control flow:

    return, raise, break, continue

The rule walks every statement-list in the module (function bodies, if/else
branches, loop bodies, try/except/finally, with-blocks, match cases). For
each block it scans top to bottom and reports the first statement after a
terminal — only the first, because once that's flagged the user fixes it
and the rest cascades.

Limitations (intentional, not bugs):
- We don't infer that `if True: return` makes the rest of the enclosing
  function unreachable. Constant-folding control flow is Phase 6.
- We don't track functions that always raise (e.g. `sys.exit`).
"""

from __future__ import annotations

import ast

from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_TERMINALS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


def _terminal_label(node: ast.stmt) -> str:
    return {
        ast.Return: "return",
        ast.Raise: "raise",
        ast.Break: "break",
        ast.Continue: "continue",
    }[type(node)]


class _DeadCodeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def _scan_block(self, body: list[ast.stmt]) -> None:
        for i, stmt in enumerate(body):
            if isinstance(stmt, _TERMINALS) and i + 1 < len(body):
                nxt = body[i + 1]
                self.findings.append(
                    Finding(
                        severity="WARNING",
                        message=f"Unreachable code after '{_terminal_label(stmt)}'",
                        line=nxt.lineno,
                        rule="dead-code",
                    )
                )
                break  # only flag the first dead statement per block

    def generic_visit(self, node: ast.AST) -> None:
        for field, value in ast.iter_fields(node):
            if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                self._scan_block(value)
        super().generic_visit(node)

    # ExceptHandler.body is a stmt list but the handler itself isn't a stmt;
    # generic_visit covers it via iter_fields.


class DeadCodeRule(Rule):
    name = "dead-code"

    def check(self, tree: ast.Module) -> list[Finding]:
        v = _DeadCodeVisitor()
        v.visit(tree)
        return sorted(v.findings, key=lambda f: f.line)
