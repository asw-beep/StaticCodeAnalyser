"""Dead-store rule.

Flags an assignment whose value is never read: on every path from it, the
variable is either reassigned or never read again. Uses liveness analysis
over the function's control-flow graph (`analyzer/cfg.py`):

    def f(c):
        x = compute()   # dead store: both branches overwrite x
        if c:
            x = 1
        else:
            x = 2
        return x

This is the complement of `unused-variable`: that rule reports names never
read anywhere in the scope; this one reports individual assignments whose
value is lost even though the name *is* read elsewhere. A name never read at
all is left to `unused-variable` so the same line isn't reported twice.

Only simple `name = value` / `name: T = value` statements inside functions
are checked. Skipped, to stay quiet on intentional code:
- module and class scopes (names there are importable / attributes)
- names starting with `_`, `global`/`nonlocal` names, and names read by a
  nested function, lambda or class (a closure may read them at any time)
- functions that call `locals()`, `vars()`, `eval()` or `exec()`
- default-value initializations (`x = None`, `0`, `1`, `-1`, `""`, `True`,
  `False`, `[]`, `{}`, `()`) — "declare, then assign in every branch" is a
  common, harmless idiom
- tuple-unpacking, augmented, walrus, and loop/with/except targets

Limitations (deliberate): intra-procedural only, and the CFG over-
approximates control flow, so some dead stores are missed — never the
reverse.
"""

from __future__ import annotations

import ast

from analyzer.cfg import build_cfg, iter_live_items, live_out
from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (*_FUNCS, ast.ClassDef, ast.Lambda)
_DYNAMIC_ACCESS = {"locals", "vars", "eval", "exec"}


def _is_default_init(value: ast.expr) -> bool:
    if isinstance(value, ast.Constant):
        return value.value in (None, True, False, 0, 1, "", b"")
    if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
        return isinstance(value.operand, ast.Constant) and value.operand.value == 1
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys
    return False


def _store_target(stmt: ast.AST) -> tuple[str, ast.expr] | None:
    """(name, value) for a checkable `name = value` statement, else None."""
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        return stmt.targets[0].id, stmt.value
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None and isinstance(stmt.target, ast.Name):
        return stmt.target.id, stmt.value
    return None


def _scope_facts(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[set[str], set[str]]:
    """(names to never report, names loaded anywhere in this scope)."""
    skip: set[str] = set()
    loaded: set[str] = set()

    def walk(node: ast.AST, nested: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Global, ast.Nonlocal)):
                skip.update(child.names)
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                (skip if nested else loaded).add(child.id)
            walk(child, nested or isinstance(child, _SCOPES))

    walk(func, False)
    return skip, loaded


def _check_function(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Finding]:
    skip, loaded = _scope_facts(func)
    if loaded & _DYNAMIC_ACCESS:
        return []
    cfg = build_cfg(func.body)
    out = live_out(cfg)
    findings: list[Finding] = []
    for block in cfg.reachable():
        for item, live_after in iter_live_items(block, out[block]):
            if item.kind != "stmt":
                continue
            target = _store_target(item.node)
            if target is None:
                continue
            name, value = target
            if (
                name in live_after
                or name not in loaded  # never read at all: unused-variable's job
                or name in skip
                or name.startswith("_")
                or _is_default_init(value)
            ):
                continue
            findings.append(
                Finding(
                    severity="WARNING",
                    message=f"Value assigned to '{name}' is never read (overwritten or discarded first)",
                    line=item.node.lineno,
                    rule="dead-store",
                )
            )
    return findings


class DeadStoreRule(Rule):
    name = "dead-store"
    description = "Assignments whose value is always overwritten or discarded before being read"

    def check(self, tree: ast.Module) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, _FUNCS):
                findings.extend(_check_function(node))
        return sorted(findings, key=lambda f: f.line)
