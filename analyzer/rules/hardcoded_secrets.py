"""Hardcoded-secrets rule.

Flags string literals assigned to credential-shaped names, or passed as
credential-shaped keyword arguments — the classic "secret checked into git
history" mistake.

A name is credential-shaped if it matches (case-insensitively):
`password|passwd|pwd|secret|api_key|apikey|token|access_key|private_key|aws_secret`

Two shapes are checked:
- `Assign` / `AnnAssign` where the target is a credential-shaped name and the
  value is a non-empty, non-placeholder string constant.
- Call keyword arguments (`ast.keyword`) whose name is credential-shaped and
  whose value is a non-empty, non-placeholder string constant, e.g.
  `connect(password="hunter2")`.

Placeholders are deliberately not flagged: empty strings, common "fill this
in" markers (`changeme`, `xxx`, `todo`, `placeholder`, `...`), and strings
made of a single repeated character (`****`, `----`).

Limitations (deliberate):
- No taint tracking — `PASSWORD = get_secret()` is fine (not a string
  literal); `PASSWORD = "hunter2"` is not.
- No cross-file/env-var awareness — this is a syntactic check, not a secret
  scanner with entropy analysis.
"""

from __future__ import annotations

import ast
import re

from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_NAME_PATTERN = re.compile(
    r"(password|passwd|pwd|secret|api_?key|token|access_key|private_key|aws_secret)",
    re.IGNORECASE,
)

_PLACEHOLDER_WORDS = {"changeme", "xxx", "todo", "placeholder", "...", "your_password_here"}


def _is_placeholder(value: str) -> bool:
    v = value.strip()
    if not v:
        return True
    if v.lower() in _PLACEHOLDER_WORDS:
        return True
    if len(set(v)) == 1:
        return True
    return False


class _SecretsVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def _flag(self, name: str, line: int, kind: str) -> None:
        self.findings.append(
            Finding(
                severity="ERROR",
                message=f"Hardcoded secret in {kind} '{name}'",
                line=line,
                rule="hardcoded-secrets",
            )
        )

    def _check_value(self, name: str, value: ast.expr, line: int, kind: str) -> None:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            if not _is_placeholder(value.value):
                self._flag(name, line, kind)

    def visit_Assign(self, node: ast.Assign) -> None:
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and _NAME_PATTERN.search(tgt.id):
                self._check_value(tgt.id, node.value, node.lineno, "variable")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target = node.target
        if node.value is not None and isinstance(target, ast.Name) and _NAME_PATTERN.search(target.id):
            self._check_value(target.id, node.value, node.lineno, "variable")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg and _NAME_PATTERN.search(kw.arg):
                self._check_value(kw.arg, kw.value, kw.value.lineno, "argument")
        self.generic_visit(node)


class HardcodedSecretsRule(Rule):
    name = "hardcoded-secrets"
    description = "String literals assigned to credential-shaped names"

    def check(self, tree: ast.Module) -> list[Finding]:
        v = _SecretsVisitor()
        v.visit(tree)
        return sorted(v.findings, key=lambda f: f.line)
