"""Dead-code rule.

Flags statements that can never execute, using reachability on each scope's
control-flow graph (`analyzer/cfg.py`). That covers:

- code after `return`, `raise`, `break`, `continue`
- code after `sys.exit()`, `os._exit()`, `os.abort()`, `exit()`, `quit()`
- code after an `if`/`try`/`match` where every path exits
- code after `while True:` with no `break` (an infinite loop)
- the body of `if False:` / `while 0:`, the `else` of `if True:`

Only the first statement of each unreachable region is reported: once that
line is fixed, the rest cascades. Statements nested inside an already
reported region are not reported again.

Limitations (deliberate — all of these under-report, never over-report):
- Only literal constants are folded: `if DEBUG:` is always "maybe".
- Any `with` block is assumed able to swallow an exception
  (`contextlib.suppress`), so code after a `with` whose body always
  returns is not reported.
- A call is "noreturn" only for the fixed list above, matched by name
  (`import sys as s; s.exit()` is missed; a local `exit` shadowing the
  builtin would be wrongly trusted).
"""

from __future__ import annotations

import ast

from analyzer.cfg import build_cfg, constant_truth, noreturn_call_name
from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_JUMPS = {ast.Return: "return", ast.Raise: "raise", ast.Break: "break", ast.Continue: "continue"}
_COMPOUND_LABEL = {ast.If: "if", ast.Try: "try", ast.Match: "match"}


def _child_blocks(s: ast.stmt) -> list[tuple[str, list[ast.stmt]]]:
    """(field, statement list) pairs nested directly in `s`, same scope only."""
    if isinstance(s, _NESTED_SCOPES):
        return []
    out = []
    for name in ("body", "orelse", "finalbody"):
        stmts = getattr(s, name, None)
        if stmts:
            out.append((name, stmts))
    for h in getattr(s, "handlers", []):
        out.append(("handler", h.body))
    for c in getattr(s, "cases", []):
        out.append(("case", c.body))
    return out


def _reason(stmts: list[ast.stmt], i: int, parent: ast.stmt | None, field: str) -> str:
    if i > 0:
        prev = stmts[i - 1]
        for typ, label in _JUMPS.items():
            if isinstance(prev, typ):
                return f"Unreachable code after '{label}'"
        call = noreturn_call_name(prev)
        if call:
            return f"Unreachable code after '{call}()'"
        if isinstance(prev, ast.While) and constant_truth(prev.test):
            return "Unreachable code after infinite loop"
        label = _COMPOUND_LABEL.get(type(prev)) or ("try" if type(prev).__name__ == "TryStar" else None)
        if label:
            return f"Unreachable code: every path through the preceding '{label}' exits"
    elif isinstance(parent, (ast.If, ast.While)):
        truth = constant_truth(parent.test)
        if field == "body" and truth is False:
            return "Unreachable code: condition is always false"
        if field == "orelse" and truth is True:
            return "Unreachable code: 'else' never runs (condition is always true)"
    return "Unreachable code"


def _check_scope(body: list[ast.stmt]) -> list[Finding]:
    cfg = build_cfg(body)
    reachable = cfg.reachable()
    blocks = cfg.owner_blocks()

    def dead(s: ast.stmt) -> bool:
        return blocks[s] not in reachable

    findings: list[Finding] = []

    def scan(stmts: list[ast.stmt], parent: ast.stmt | None, field: str, parent_dead: bool) -> None:
        prev_dead = parent_dead
        for i, s in enumerate(stmts):
            is_dead = dead(s)
            if is_dead and not prev_dead:
                findings.append(
                    Finding(
                        severity="WARNING",
                        message=_reason(stmts, i, parent, field),
                        line=s.lineno,
                        rule="dead-code",
                    )
                )
            for child_field, child in _child_blocks(s):
                scan(child, s, child_field, is_dead)
            prev_dead = is_dead

    scan(body, None, "body", False)
    return findings


class DeadCodeRule(Rule):
    name = "dead-code"
    description = "Statements that can never execute (after exits, infinite loops, constant conditions)"

    def check(self, tree: ast.Module) -> list[Finding]:
        findings = _check_scope(tree.body)
        for node in ast.walk(tree):
            if isinstance(node, _NESTED_SCOPES):
                findings.extend(_check_scope(node.body))
        return sorted(findings, key=lambda f: f.line)
