"""Intra-procedural control-flow graph (CFG) and liveness analysis.

`build_cfg(body)` turns one scope's statement list (a function, class or
module body) into basic blocks connected by possible-control-flow edges.
Rules use it for two things:

- **Reachability** (`CFG.reachable()`): a statement whose block can't be
  reached from the entry is dead code. This sees through `if`/`else` where
  every branch exits, `while True` without `break`, `sys.exit()`, etc.
- **Liveness** (`live_out()`): a backward dataflow analysis computing, for
  each block, the variables whose current value may still be read. An
  assignment to a variable that isn't live right after it is a dead store.

Soundness stance: the graph OVER-approximates possible control flow. Every
uncertain edge is added (any statement in a `try` body may jump to every
handler; any `with` may swallow an exception; `finally` may continue to any
of its possible successors). Extra edges only make code look *more*
reachable and variables *more* live, so imprecision turns into missed
findings, never false positives.

Block items
-----------
Blocks hold `Item`s rather than raw statements, because a compound
statement contributes several separately-placed pieces: an `if` contributes
its test, a `for` its iterable (before the loop) and its target binding (at
the top of each iteration), an `except E as e` handler its binding of `e`.
Each item records its `owner` statement; a statement is reachable iff the
block holding its first item is.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field

# Item kinds:
#   "stmt"    a simple statement (or a def/class header)
#   "expr"    an expression evaluated for its uses (if/while test, for iterable, ...)
#   "bind"    an assignment target bound implicitly (for/with/except targets)
#   "pattern" a match-case pattern (binds capture names)
#   "nop"     a placeholder that only marks where a statement starts (try)


@dataclass(eq=False)
class Item:
    node: ast.AST
    owner: ast.stmt
    kind: str


@dataclass(eq=False)
class Block:
    id: int
    items: list[Item] = field(default_factory=list)
    succs: list[Block] = field(default_factory=list)
    preds: list[Block] = field(default_factory=list)

    def __repr__(self) -> str:  # dataclass repr would recurse through succs/preds
        return f"Block({self.id}, items={len(self.items)}, succs={[s.id for s in self.succs]})"


@dataclass
class CFG:
    entry: Block
    exit: Block
    blocks: list[Block]

    def reachable(self) -> set[Block]:
        seen = {self.entry}
        stack = [self.entry]
        while stack:
            for s in stack.pop().succs:
                if s not in seen:
                    seen.add(s)
                    stack.append(s)
        return seen

    def owner_blocks(self) -> dict[ast.stmt, Block]:
        """Statement -> block holding its first item."""
        out: dict[ast.stmt, Block] = {}
        for b in self.blocks:
            for item in b.items:
                out.setdefault(item.owner, b)
        return out


# --- helpers -----------------------------------------------------------------

_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_NORETURN_ATTRS = {("sys", "exit"), ("os", "_exit"), ("os", "abort")}
_NORETURN_NAMES = {"exit", "quit"}


def constant_truth(test: ast.expr) -> bool | None:
    """True/False if `test` is a literal constant, else None (unknown)."""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    return None


def noreturn_call_name(stmt: ast.stmt) -> str | None:
    """'sys.exit' etc. if `stmt` is a bare call that never returns."""
    if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
        return None
    func = stmt.value.func
    if isinstance(func, ast.Name) and func.id in _NORETURN_NAMES:
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if (func.value.id, func.attr) in _NORETURN_ATTRS:
            return f"{func.value.id}.{func.attr}"
    return None


def _is_irrefutable(case: ast.match_case) -> bool:
    p = case.pattern
    return case.guard is None and isinstance(p, ast.MatchAs) and p.pattern is None


# --- builder -----------------------------------------------------------------


class _Builder:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.entry = self.new()
        self.exit = self.new()
        self.loops: list[tuple[Block, Block]] = []  # (continue target, break target)
        self.exc_targets: list[list[Block]] = []  # where an exception raised here may go
        self.finallys: list[tuple[Block, int]] = []  # (finally entry, loop depth at the try)
        self.routed: dict[Block, set[str]] = {}  # finally entry -> jumps routed through it

    def new(self) -> Block:
        b = Block(len(self.blocks))
        self.blocks.append(b)
        return b

    @staticmethod
    def link(a: Block, b: Block) -> None:
        if b not in a.succs:
            a.succs.append(b)
            b.preds.append(a)

    def raise_targets(self) -> list[Block]:
        return self.exc_targets[-1] if self.exc_targets else [self.exit]

    def jump_target(self, kind: str) -> Block:
        """Where return/break/continue go, routing through an enclosing finally."""
        if self.finallys and (kind == "return" or self.finallys[-1][1] == len(self.loops)):
            # Inside a try (that is itself inside the loop, for break/continue):
            # the finally runs first.
            entry = self.finallys[-1][0]
            self.routed.setdefault(entry, set()).add(kind)
            return entry
        if kind == "return":
            return self.exit
        cont, brk = self.loops[-1]
        return brk if kind == "break" else cont

    def follow(self, cur: Block) -> Block:
        b = self.new()
        self.link(cur, b)
        return b

    def join(self, ends: list[Block | None]) -> Block | None:
        live = [e for e in ends if e is not None]
        if not live:
            return None
        after = self.new()
        for e in live:
            self.link(e, after)
        return after

    # -- statement lists --

    def stmts(self, body: list[ast.stmt], cur: Block | None) -> Block | None:
        """Build `body` starting in `cur`; return the fall-through block or None."""
        for s in body:
            if cur is None:
                cur = self.new()  # code after an exit: a block nothing reaches
            cur = self.stmt(s, cur)
        return cur

    def stmt(self, s: ast.stmt, cur: Block) -> Block | None:
        if self.exc_targets:
            # Inside a try: the state *before* this statement may reach a
            # handler (the statement can raise before completing).
            pre = self.follow(cur) if cur.items else cur
            for t in self.raise_targets():
                self.link(pre, t)
            cur = self.follow(pre)

        if isinstance(s, ast.If):
            return self.if_(s, cur)
        if isinstance(s, ast.While):
            return self.while_(s, cur)
        if isinstance(s, (ast.For, ast.AsyncFor)):
            return self.for_(s, cur)
        if isinstance(s, (ast.With, ast.AsyncWith)):
            return self.with_(s, cur)
        if isinstance(s, ast.Try) or type(s).__name__ == "TryStar":
            return self.try_(s, cur)
        if isinstance(s, ast.Match):
            return self.match_(s, cur)

        cur.items.append(Item(s, s, "stmt"))
        if isinstance(s, ast.Return):
            self.link(cur, self.jump_target("return"))
            return None
        if isinstance(s, (ast.Break, ast.Continue)):
            if self.loops:  # outside a loop it's a SyntaxError; be lenient
                self.link(cur, self.jump_target("break" if isinstance(s, ast.Break) else "continue"))
            return None
        if isinstance(s, ast.Raise) or noreturn_call_name(s):
            for t in self.raise_targets():
                self.link(cur, t)
            return None
        return cur

    # -- compound statements --

    def if_(self, s: ast.If, cur: Block) -> Block | None:
        cur.items.append(Item(s.test, s, "expr"))
        truth = constant_truth(s.test)
        then_entry, else_entry = self.new(), self.new()
        if truth is not False:
            self.link(cur, then_entry)
        if truth is not True:
            self.link(cur, else_entry)
        then_end = self.stmts(s.body, then_entry)
        else_end = self.stmts(s.orelse, else_entry)
        return self.join([then_end, else_end])

    def while_(self, s: ast.While, cur: Block) -> Block | None:
        header = self.follow(cur)
        header.items.append(Item(s.test, s, "expr"))
        truth = constant_truth(s.test)
        after = self.new()
        body_entry = self.new()
        if truth is not False:
            self.link(header, body_entry)
        self.loops.append((header, after))
        body_end = self.stmts(s.body, body_entry)
        self.loops.pop()
        if body_end is not None:
            self.link(body_end, header)
        if truth is not True:
            else_end = self.stmts(s.orelse, self.follow(header))
            if else_end is not None:
                self.link(else_end, after)
        else:
            self.stmts(s.orelse, self.new())  # `else` of an infinite loop never runs
        return after if after.preds else None

    def for_(self, s: ast.For | ast.AsyncFor, cur: Block) -> Block | None:
        cur.items.append(Item(s.iter, s, "expr"))
        header = self.follow(cur)
        after = self.new()
        body_entry = self.follow(header)
        body_entry.items.append(Item(s.target, s, "bind"))
        self.loops.append((header, after))
        body_end = self.stmts(s.body, body_entry)
        self.loops.pop()
        if body_end is not None:
            self.link(body_end, header)
        else_end = self.stmts(s.orelse, self.follow(header))
        if else_end is not None:
            self.link(else_end, after)
        return after if after.preds else None

    def with_(self, s: ast.With | ast.AsyncWith, cur: Block) -> Block | None:
        for item in s.items:
            cur.items.append(Item(item.context_expr, s, "expr"))
            if item.optional_vars is not None:
                cur.items.append(Item(item.optional_vars, s, "bind"))
        after = self.new()
        self.link(cur, after)  # the context manager may swallow an exception
        body_end = self.stmts(s.body, self.follow(cur))
        if body_end is not None:
            self.link(body_end, after)
        return after

    def try_(self, s: ast.stmt, cur: Block) -> Block | None:
        cur.items.append(Item(s, s, "nop"))
        handlers: list[ast.ExceptHandler] = s.handlers
        outer = self.raise_targets()
        final_entry = self.new() if s.finalbody else None
        handler_entries = [self.new() for _ in handlers]
        propagate = [final_entry] if final_entry else outer

        if final_entry:
            self.finallys.append((final_entry, len(self.loops)))

        self.exc_targets.append(handler_entries + propagate)
        body_end = self.stmts(s.body, self.follow(cur))
        self.exc_targets.pop()

        # `else` and handler bodies are outside the try's protection.
        self.exc_targets.append(propagate)
        else_end = self.stmts(s.orelse, body_end) if body_end is not None else None
        normal_ends = [else_end]
        for h, entry in zip(handlers, handler_entries):
            if h.type is not None:
                entry.items.append(Item(h.type, s, "expr"))
            if h.name:
                name = ast.Name(id=h.name, ctx=ast.Store(), lineno=h.lineno, col_offset=h.col_offset)
                entry.items.append(Item(name, s, "bind"))
            normal_ends.append(self.stmts(h.body, entry))
        self.exc_targets.pop()

        if not final_entry:
            return self.join(normal_ends)

        self.finallys.pop()
        live_ends = [e for e in normal_ends if e is not None]
        for e in live_ends:
            self.link(e, final_entry)
        final_end = self.stmts(s.finalbody, final_entry)
        if final_end is None:
            return None
        # After finally, control resumes wherever it was headed: normal
        # fall-through, a propagating exception, or a jump routed through it.
        for t in outer:
            self.link(final_end, t)
        # This finally is already popped, so jump_target() resolves to the
        # next enclosing finally or the real destination.
        for kind in sorted(self.routed.get(final_entry, set())):
            if kind == "return" or self.loops:
                self.link(final_end, self.jump_target(kind))
        if not live_ends:
            return None
        return self.follow(final_end)

    def match_(self, s: ast.Match, cur: Block) -> Block | None:
        cur.items.append(Item(s.subject, s, "expr"))
        ends: list[Block | None] = []
        exhaustive = False
        for case in s.cases:
            entry = self.follow(cur)
            entry.items.append(Item(case.pattern, s, "pattern"))
            if case.guard is not None:
                entry.items.append(Item(case.guard, s, "expr"))
            ends.append(self.stmts(case.body, entry))
            exhaustive = exhaustive or _is_irrefutable(case)
        if not exhaustive:
            ends.append(cur)  # no case matched
        return self.join(ends)


def build_cfg(body: list[ast.stmt]) -> CFG:
    b = _Builder()
    end = b.stmts(body, b.entry)
    if end is not None:
        b.link(end, b.exit)
    return CFG(b.entry, b.exit, b.blocks)


# --- defs / uses ---------------------------------------------------------------

_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _names(node: ast.AST, defs: set[str], uses: set[str], *, in_comp: bool = False) -> None:
    """Collect Name loads (uses) and stores (defs), staying in the current scope.

    - Lambda bodies are closures: their loads count as uses, nothing as a def.
    - Comprehension targets live in their own scope, so stores inside a
      comprehension are not defs of this scope (loads still are uses).
    - `del x` counts as a use (conservative).
    """
    if isinstance(node, ast.Name):
        if isinstance(node.ctx, ast.Store):
            if not in_comp:
                defs.add(node.id)
        else:
            uses.add(node.id)
        return
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return  # handled by the caller as a declaration
    in_comp = in_comp or isinstance(node, (*_COMPREHENSIONS, ast.Lambda))
    for child in ast.iter_child_nodes(node):
        _names(child, defs, uses, in_comp=in_comp)


def _pattern_names(p: ast.AST, defs: set[str], uses: set[str]) -> None:
    for node in ast.walk(p):
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            defs.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            defs.add(node.rest)
        elif isinstance(node, ast.Name):
            uses.add(node.id)


def _decl_uses(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> set[str]:
    """Names a def/class statement reads when it executes (not its body)."""
    parts: list[ast.AST] = list(node.decorator_list)
    if isinstance(node, ast.ClassDef):
        parts += node.bases + [k.value for k in node.keywords]
    else:
        a = node.args
        parts += a.defaults + [d for d in a.kw_defaults if d is not None]
        parts += [x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs if x.annotation]
        if node.returns:
            parts.append(node.returns)
    uses: set[str] = set()
    for part in parts:
        _names(part, set(), uses)
    return uses


def defs_uses(item: Item) -> tuple[set[str], set[str]]:
    defs: set[str] = set()
    uses: set[str] = set()
    node = item.node
    if item.kind == "nop":
        return defs, uses
    if item.kind == "pattern":
        _pattern_names(node, defs, uses)
        return defs, uses
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}, _decl_uses(node)
    _names(node, defs, uses)
    if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        uses.add(node.target.id)  # x += 1 reads x first
    return defs, uses


# --- liveness ------------------------------------------------------------------


def live_out(cfg: CFG) -> dict[Block, set[str]]:
    """Backward may-liveness: names whose value may be read after each block."""
    gen: dict[Block, set[str]] = {}
    kill: dict[Block, set[str]] = {}
    for b in cfg.blocks:
        g: set[str] = set()
        k: set[str] = set()
        for item in reversed(b.items):
            d, u = defs_uses(item)
            g = u | (g - d)
            k |= d
        gen[b], kill[b] = g, k

    live_in = {b: set() for b in cfg.blocks}
    out = {b: set() for b in cfg.blocks}
    work = list(cfg.blocks)
    while work:
        b = work.pop()
        new_out = set().union(*(live_in[s] for s in b.succs)) if b.succs else set()
        out[b] = new_out
        new_in = gen[b] | (new_out - kill[b])
        if new_in != live_in[b]:
            live_in[b] = new_in
            work.extend(p for p in b.preds if p not in work)
    return out


def iter_live_items(block: Block, out: set[str]) -> Iterator[tuple[Item, set[str]]]:
    """Yield (item, names live immediately after it), walking the block backward."""
    live = set(out)
    for item in reversed(block.items):
        yield item, live
        d, u = defs_uses(item)
        live = u | (live - d)
