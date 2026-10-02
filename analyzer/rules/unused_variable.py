"""Unused-variable rule.

Per-scope analysis: for each function (and the module itself), collect names
that are assigned but never loaded inside the same scope. Names assigned in a
scope but used only by a nested function are still considered used (closures).

Edge cases handled:
- function parameters are exempt (they're part of the API)
- loop variables (`for x in ...`) are exempt — common Python idiom is to
  iterate for side effects
- `_` and names starting with `_` are exempt (convention for "intentionally
  unused")
- augmented assignment (`x += 1`) counts as both load and store
- tuple/starred unpacking targets are each treated as an assignment
- `with ... as x` and walrus (`x := ...`) targets are assignments
- class-body assignments are attributes (dataclass fields, constants,
  method aliases), not locals, and are never flagged; methods inside the
  class are still checked
- subscript/attribute targets (`d[k] = v`, `o.x = v`) are a *use* of `d`/`o`,
  not an assignment — they mutate an existing object
"""

from __future__ import annotations

import ast

from analyzer.reporter import Finding
from analyzer.rules.base import Rule


def _iter_assigned_names(target: ast.expr):
    """Yield (name, lineno) for every Name target inside an assignment LHS."""
    if isinstance(target, ast.Name):
        yield target.id, target.lineno
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _iter_assigned_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _iter_assigned_names(target.value)


class _ScopeVisitor(ast.NodeVisitor):
    """Walks one scope, collecting assignments and loads.

    Nested function/class bodies are NOT descended into for this scope's
    bookkeeping — they form their own scopes — but their names ARE checked
    for closure references back into this scope.
    """

    def __init__(self) -> None:
        self.assigned: dict[str, int] = {}      # name -> first assignment line
        self.loaded: set[str] = set()
        self.exempt: set[str] = set()           # params, loop vars, etc.
        self._nested: list[ast.AST] = []        # nested scopes to scan for loads

    # --- assignments ----------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        for tgt in node.targets:
            for name, line in _iter_assigned_names(tgt):
                self.assigned.setdefault(name, line)
            self.visit(tgt)  # picks up loads in `d[k] = ...` / `o.x = ...`
        self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # x += 1  -> counts as both a load and a store; skip flagging.
        for name, _ in _iter_assigned_names(node.target):
            self.exempt.add(name)
        self.visit(node.target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            for name, line in _iter_assigned_names(node.target):
                self.assigned.setdefault(name, line)
            self.visit(node.target)
            self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        for name, _ in _iter_assigned_names(node.target):
            self.exempt.add(name)
        self.visit(node.target)
        self.visit(node.iter)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                for name, line in _iter_assigned_names(item.optional_vars):
                    self.assigned.setdefault(name, line)
                self.visit(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    visit_AsyncWith = visit_With

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.assigned.setdefault(node.target.id, node.target.lineno)
        self.visit(node.value)

    # --- loads ----------------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loaded.add(node.id)

    # --- nested scopes --------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Declarations are not flagged as unused — they may be public API.
        # Decorators, defaults, and the body still need scanning.
        for d in node.decorator_list:
            self.visit(d)
        for d in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
            self.visit(d)
        self._nested.append(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        for d in node.decorator_list:
            self.visit(d)
        for d in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
            self.visit(d)
        self._nested.append(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for d in node.decorator_list:
            self.visit(d)
        for b in node.bases:
            self.visit(b)
        self._nested.append(node)


def _collect_closure_loads(node: ast.AST) -> set[str]:
    """All names loaded anywhere in this subtree (used to detect closure use)."""
    loads: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            loads.add(child.id)
    return loads


def _params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func.args
    out = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
    if args.vararg:
        out.add(args.vararg.arg)
    if args.kwarg:
        out.add(args.kwarg.arg)
    return out


def _analyze_scope(body: list[ast.stmt], param_names: set[str], report: bool = True) -> list[Finding]:
    visitor = _ScopeVisitor()
    for stmt in body:
        visitor.visit(stmt)

    # Names loaded by any nested function/class (closure references).
    closure_loads: set[str] = set()
    for nested in visitor._nested:
        closure_loads |= _collect_closure_loads(nested)

    used = visitor.loaded | closure_loads | visitor.exempt | param_names

    findings: list[Finding] = []
    for name, line in visitor.assigned.items():
        if not report or name in used or name.startswith("_"):
            continue
        findings.append(
            Finding(
                severity="WARNING",
                message=f"Unused variable '{name}'",
                line=line,
                rule="unused-variable",
            )
        )

    # Recurse into nested function scopes.
    for nested in visitor._nested:
        if isinstance(nested, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_analyze_scope(nested.body, _params(nested)))
        elif isinstance(nested, ast.ClassDef):
            findings.extend(_analyze_scope(nested.body, set(), report=False))

    return findings


class UnusedVariableRule(Rule):
    name = "unused-variable"
    description = "Local names assigned but never read"

    def check(self, tree: ast.Module) -> list[Finding]:
        return _analyze_scope(tree.body, set())
