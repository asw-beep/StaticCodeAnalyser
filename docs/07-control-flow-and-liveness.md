# Stage 7 — Control-flow graph and liveness

**Status:** complete
**Code:** `analyzer/cfg.py`, `analyzer/rules/dead_code.py`, `analyzer/rules/dead_store.py`

## Why

The original dead-code rule scanned one statement list at a time: "is there a statement after a `return` in this block?". It could not see that

```python
if x >= 0:
    return 1
else:
    return -1
print("never runs")
```

makes the `print` unreachable, because the `print` sits in a different block from either `return`. Questions like "can this line run?" and "can this value ever be read?" are questions about *paths*, which needs a control-flow graph.

## The graph

`build_cfg(body)` builds one graph per scope (module, class or function body). Nested functions get their own graph.

- **Blocks** are straight-line runs of *items*. An item is one piece of a statement placed where it executes. An `if` contributes its test. A `for` contributes its iterable, evaluated once before the loop, and its target binding, which runs at the top of every iteration. An `except E as e` contributes the binding of `e` at the handler entry.
- **Edges** are possible transfers of control: branches, loop back-edges, `break`/`continue` to the loop's exit or header, `return` to the exit block, and `raise` to the innermost handler.
- Code after an exit is still built, into a block with no predecessors. That keeps every statement in the graph, which the dead-code rule relies on.

Statement-specific handling:

| Construct | Modelling |
|---|---|
| `if` / `while` with a literal constant test | Only the feasible edge is added (`while True` has no exit edge; `if False` body has no entry edge). |
| `for` / `while` `else` | Entered from the loop header (normal exhaustion), not from `break`. |
| `try` | Before *each* statement in the body, an empty block links to every handler (and the `finally`). Placing the edge before the statement matters: a statement can raise before its assignment completes, so the handler must see the *previous* value as live. |
| `finally` | Entered from normal completion, from every exception edge, and from any `return`/`break`/`continue` routed through it. Its end continues only to the destinations of what was actually routed through it. |
| `with` | An edge from the header to after the block, because the context manager might swallow an exception (`contextlib.suppress`). |
| `match` | One edge per case. Falls through to after the `match` unless a case is irrefutable (`case _:`). |
| `sys.exit()`, `os._exit()`, `os.abort()`, `exit()`, `quit()` | Treated like `raise`. |

## Soundness stance

The graph **over-approximates**. When the precise behaviour is uncertain (can this statement raise? does this context manager swallow exceptions?), the edge is added. Extra edges can only make code look *more* reachable and variables *more* live. Both rules report what the graph says is impossible, so imprecision becomes a missed finding, never a false one. That's the right trade for WARNING-level rules: a tool that cries wolf gets turned off.

## Liveness

`live_out(cfg)` is the textbook backward may-analysis, solved with a worklist to a fixed point:

```
live_in(B)  = use(B) ∪ (live_out(B) − def(B))
live_out(B) = ∪ live_in(S) for each successor S
```

`use`/`def` per item come from `defs_uses()`, which follows these rules:
- Comprehension targets are their own scope, so they don't define names in this scope.
- Lambda bodies count as uses (closures).
- `x += 1` both uses and defines `x`.
- `del x` counts as a use, which is conservative.

## The rules built on it

**dead-code** reports every statement whose block is unreachable from the entry, but only the first statement of each unreachable region. Nested statements inside an already-reported region are skipped. The message names the cause, inferred from the preceding sibling statement.

**dead-store** walks each reachable block backward from `live_out` and reports `name = value` when `name` is not live immediately after. These cases are deliberately excluded to keep it quiet:
- default-value initializations
- closures, `global`, `nonlocal` and `_`-prefixed names
- functions using `locals()`/`vars()`/`eval()`/`exec()`
- names never read at all, which are left to `unused-variable` so the same line isn't reported twice

## Validation

Running the analyzer on its own source (`analyzer/` and `tests/`) produces no `dead-code` or `dead-store` findings, and CI enforces that on every push.

## Limitations

- **Intra-procedural:** calls are opaque, so a function that always raises isn't known to.
- **Literal constants only:** constant folding covers literals, not names like `DEBUG = False`.
- **Name-matched noreturn calls:** `import sys as s; s.exit()` is missed.
- **Line-level `try` granularity:** the exception edge before a statement doesn't model a statement that raises halfway through evaluating a multi-name expression.
