"""Forward value-flow analysis over the CFG.

Tracks, for every local variable, whether its current value carries some
property — "built dynamically" for SQL strings, "derived from untrusted
input" for taint — and where that property came from (an `Origin`).

The analysis is a forward may-analysis solved to a fixed point:

    in(B)  = ∪ out(P) for each predecessor P
    out(B) = transfer(in(B), items of B)

The property itself is pluggable: callers pass an `evaluate(expr, env)`
function that says whether an expression's value has the property, given
the properties of the variables it reads.

Transfer rules (shared by every property):
- `x = e`            strong update: x gets evaluate(e), or loses the property
- `a, b = e`         every unpacked name gets evaluate(e)
- `x += e`           x keeps its property and gains evaluate(x + e)
- `x[k] = e`, `x.a = e`, `x.append(e)` and other mutators
                     weak update: x gains evaluate(e), never loses anything
- `for x in e`, `with e as x`, `case <capture>` bind from e
- `x := e` inside any expression is a strong update
- `def x`, `class x`, `del x`, `except ... as x` clear x

Limitations (deliberate): intra-procedural; object attributes and
container elements are not tracked separately (a container is "tainted"
as a whole); nested functions don't see the enclosing scope's facts.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from analyzer.cfg import CFG, Block, Item, build_cfg


@dataclass(frozen=True, order=True)
class Origin:
    line: int
    desc: str


Env = dict[str, Origin]
Evaluate = Callable[[ast.expr, Env], "Origin | None"]

_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_MUTATORS = {"append", "extend", "insert", "add", "update", "setdefault", "appendleft", "write", "writelines"}


def _join(a: Env, b: Env) -> Env:
    out = dict(a)
    for k, v in b.items():
        out[k] = min(out[k], v) if k in out else v  # deterministic: earliest origin
    return out


def walk_scope(node: ast.AST) -> Iterator[ast.AST]:
    """ast.walk that doesn't enter nested functions, classes or lambdas.

    A nested-scope node itself is yielded (its name is bound here), but
    nothing inside it — not even when it is the starting node.
    """
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, _NESTED):
            stack.extend(ast.iter_child_nodes(n))


def _base_name(target: ast.expr) -> str | None:
    while isinstance(target, (ast.Attribute, ast.Subscript, ast.Starred)):
        target = target.value
    return target.id if isinstance(target, ast.Name) else None


def _bind_source(item: Item) -> ast.expr | None:
    """The expression an implicit binding (for/with/match) takes its value from."""
    owner = item.owner
    if isinstance(owner, (ast.For, ast.AsyncFor)):
        return owner.iter
    if isinstance(owner, (ast.With, ast.AsyncWith)):
        for w in owner.items:
            if w.optional_vars is item.node:
                return w.context_expr
    if isinstance(owner, ast.Match):
        return owner.subject
    return None  # except-handler names: the exception object is not ours


class _Transfer:
    def __init__(self, evaluate: Evaluate) -> None:
        self.evaluate = evaluate

    def assign(self, env: Env, target: ast.expr, value: Origin | None) -> None:
        if isinstance(target, ast.Name):
            if value is None:
                env.pop(target.id, None)
            else:
                env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self.assign(env, elt, value)
        elif isinstance(target, ast.Starred):
            self.assign(env, target.value, value)
        else:  # attribute / subscript store: weak update of the base object
            base = _base_name(target)
            if base is not None and value is not None:
                env[base] = min(env[base], value) if base in env else value

    def side_effects(self, env: Env, node: ast.AST) -> None:
        """Walrus assignments and container mutators inside an expression."""
        for n in walk_scope(node):
            if isinstance(n, ast.NamedExpr):
                self.assign(env, n.target, self.evaluate(n.value, env))
            elif (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr in _MUTATORS
                and isinstance(n.func.value, ast.Name)
            ):
                for arg in [*n.args, *(k.value for k in n.keywords)]:
                    self.assign(env, ast.Subscript(value=n.func.value), self.evaluate(arg, env))

    def __call__(self, env: Env, item: Item) -> None:
        node = item.node
        if item.kind == "nop":
            return
        if item.kind == "bind":
            src = _bind_source(item)
            self.assign(env, node, self.evaluate(src, env) if src is not None else None)
            return
        if item.kind == "pattern":
            value = self.evaluate(item.owner.subject, env)
            for n in ast.walk(node):
                name = getattr(n, "name", None) or getattr(n, "rest", None)
                if isinstance(name, str):
                    self.assign(env, ast.Name(id=name, ctx=ast.Store()), value)
            return
        if item.kind == "expr":
            self.side_effects(env, node)
            return

        # simple statements
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            env.pop(node.name, None)
        elif isinstance(node, ast.Assign):
            self.side_effects(env, node.value)
            value = self.evaluate(node.value, env)
            for t in node.targets:
                self.assign(env, t, value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            self.side_effects(env, node.value)
            self.assign(env, node.target, self.evaluate(node.value, env))
        elif isinstance(node, ast.AugAssign):
            self.side_effects(env, node.value)
            combined = ast.BinOp(left=_load(node.target), op=node.op, right=node.value)
            ast.copy_location(combined, node)
            new = self.evaluate(combined, env)
            if isinstance(node.target, ast.Name):
                old = env.get(node.target.id)
                if new is not None or old is not None:
                    env[node.target.id] = min(o for o in (old, new) if o is not None)
            else:
                self.assign(env, node.target, new)
        elif isinstance(node, ast.Delete):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    env.pop(t.id, None)
        else:
            self.side_effects(env, node)


def _load(target: ast.expr) -> ast.expr:
    """A Load-context copy of an assignment target (for `x += e` as `x + e`)."""
    if isinstance(target, ast.Name):
        return ast.copy_location(ast.Name(id=target.id, ctx=ast.Load()), target)
    return target


@dataclass
class FlowResult:
    cfg: CFG
    block_in: dict[Block, Env]
    transfer: _Transfer

    def items_with_env(self) -> Iterator[tuple[Item, Env]]:
        """Each reachable item with the environment *before* it executes."""
        reachable = self.cfg.reachable()
        for block in self.cfg.blocks:
            if block not in reachable:
                continue
            env = dict(self.block_in[block])
            for item in block.items:
                yield item, env
                env = dict(env)
                self.transfer(env, item)


def analyze_flow(body: list[ast.stmt], evaluate: Evaluate, initial: Env | None = None) -> FlowResult:
    cfg = build_cfg(body)
    transfer = _Transfer(evaluate)
    block_in: dict[Block, Env] = {b: {} for b in cfg.blocks}
    block_out: dict[Block, Env | None] = {b: None for b in cfg.blocks}  # None = not yet computed
    block_in[cfg.entry] = dict(initial or {})

    work = [cfg.entry]
    while work:
        b = work.pop()
        env: Env = dict(initial or {}) if b is cfg.entry else {}
        for p in b.preds:
            if block_out[p] is not None:
                env = _join(env, block_out[p])
        block_in[b] = env
        out = dict(env)
        for item in b.items:
            transfer(out, item)
        if out != block_out[b]:
            block_out[b] = out
            work.extend(s for s in b.succs if s not in work)
    return FlowResult(cfg, block_in, transfer)
