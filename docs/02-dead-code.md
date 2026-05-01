# Stage 2 — Dead-code detection

**Status:** complete
**Plan reference:** Phase 3 Milestone 4

## What was built

`DeadCodeRule` flags statements that follow a terminal statement in the same block.

Terminals: `return`, `raise`, `break`, `continue`.

## How it walks the tree

A statement-list lives in many places: function bodies, `if`/`else` branches, loop bodies, `try` / `except` / `finally`, `with` blocks, `match` cases. Hard-coding every node type that holds one is brittle.

Instead, `_DeadCodeVisitor.generic_visit` iterates each node's fields and treats any list whose first element is an `ast.stmt` as a block to scan. That covers every block type without enumerating them.

For each block, scan top to bottom. The instant a terminal is followed by another statement, record one finding pointing at that statement and stop scanning the block. Reporting only the *first* dead statement per block keeps output focused — once the user fixes that line, the rest cascades or disappears.

## Edge cases covered (with tests)

- After `return` / `raise` / `break` / `continue` — flagged
- Multiple dead statements in a row — only the first is reported per block
- `if`/`else` branches each tracked independently — both can be flagged in one pass
- Terminal as the last statement in a block — clean
- Normal control flow with no dead code — clean

## Limitations (deliberate)

- **No constant-folding.** `if True: return` does not make subsequent statements unreachable in our model. Real reachability analysis is Phase 6.
- **`sys.exit()` and other "noreturn" calls are not terminals.** We only trust syntactic terminals.

These under-flag (false negatives) but never produce false positives, which matches the rule's WARNING severity.

## How to use

```bash
python -m analyzer examples/dead_code.py
# [WARNING] Unreachable code after 'return' at line 3 (dead-code)
# [WARNING] Unreachable code after 'break' at line 9 (dead-code)
```

Run only this rule's tests:

```bash
pytest tests/test_dead_code.py
```

## Key decisions

- **Generic block discovery via `iter_fields` + isinstance check.** Avoids per-node-type visitor methods. New AST node kinds (e.g. `match` was added in 3.10) work without changes.
- **One finding per block.** Cascading dead lines is noise — flag the entry point.
- **Terminal vocabulary fixed at four AST classes.** Treating function calls as terminals would require a noreturn registry — deferred.

## What's next

Stage 3 — Plan Milestone 5: division-by-zero detection. Constant-`0` divisor → ERROR; variable divisor → INFO/WARNING (still deciding severity). This will exercise the `Finding.severity` field for the first time with multiple levels.
