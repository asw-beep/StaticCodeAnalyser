"""Unsafe-execution rule.

Flags call sites that hand a string (or serialized blob) to something that
will execute or interpret it as code:

- `eval(...)`, `exec(...)`, `compile(...)` -> ERROR (arbitrary code execution).
  Whatever is passed in — a literal, `input()`, a variable — the sink itself
  is the risk, so we don't try to trace the argument.
- `os.system(...)` -> ERROR (shell command injection).
- `subprocess.<call|run|Popen|check_call|check_output>(..., shell=True)` ->
  ERROR (shell command injection; `shell=False`/omitted is the safe default
  and is not flagged).
- `pickle.load(...)` / `pickle.loads(...)` -> WARNING (deserializing
  untrusted data can execute arbitrary code).
- `yaml.load(...)` without `Loader=yaml.SafeLoader` (or equivalent) ->
  WARNING (the default `Loader` in PyYAML < 5.1 executes arbitrary Python).

Limitations (deliberate):
- Matched by call shape (`os.system`, `subprocess.run`, ...), not by
  resolving imports/aliases — `import os as o; o.system(...)` is missed.
- No taint tracking: `eval(x)` is flagged regardless of what `x` holds.
"""

from __future__ import annotations

import ast

from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_CODE_EXEC_NAMES = {"eval", "exec", "compile"}
_SUBPROCESS_ATTRS = {"call", "run", "Popen", "check_call", "check_output"}
_PICKLE_ATTRS = {"load", "loads"}


def _is_name(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _keyword(keywords: list[ast.keyword], arg: str) -> ast.expr | None:
    for kw in keywords:
        if kw.arg == arg:
            return kw.value
    return None


def _is_true_constant(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_safe_loader(node: ast.expr | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Attribute):
        return node.attr in {"SafeLoader", "CSafeLoader"}
    if isinstance(node, ast.Name):
        return node.id in {"SafeLoader", "CSafeLoader"}
    return False


class _UnsafeExecVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def _add(self, severity: str, message: str, line: int) -> None:
        self.findings.append(
            Finding(severity=severity, message=message, line=line, rule="unsafe-execution")
        )

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func

        if isinstance(func, ast.Name) and func.id in _CODE_EXEC_NAMES:
            self._add(
                "ERROR",
                f"Use of '{func.id}()' allows arbitrary code execution",
                node.lineno,
            )
        elif isinstance(func, ast.Attribute):
            if func.attr == "system" and _is_name(func.value, "os"):
                self._add(
                    "ERROR",
                    "os.system() runs a shell command; vulnerable to command injection",
                    node.lineno,
                )
            elif func.attr in _SUBPROCESS_ATTRS and _is_name(func.value, "subprocess"):
                if _is_true_constant(_keyword(node.keywords, "shell")):
                    self._add(
                        "ERROR",
                        f"subprocess.{func.attr}() with shell=True is vulnerable to command injection",
                        node.lineno,
                    )
            elif func.attr in _PICKLE_ATTRS and _is_name(func.value, "pickle"):
                self._add(
                    "WARNING",
                    f"pickle.{func.attr}() can execute arbitrary code when deserializing untrusted data",
                    node.lineno,
                )
            elif func.attr == "load" and _is_name(func.value, "yaml"):
                if not _is_safe_loader(_keyword(node.keywords, "Loader")):
                    self._add(
                        "WARNING",
                        "yaml.load() without Loader=yaml.SafeLoader can execute arbitrary code",
                        node.lineno,
                    )

        self.generic_visit(node)


class UnsafeExecutionRule(Rule):
    name = "unsafe-execution"

    def check(self, tree: ast.Module) -> list[Finding]:
        v = _UnsafeExecVisitor()
        v.visit(tree)
        return sorted(v.findings, key=lambda f: f.line)
