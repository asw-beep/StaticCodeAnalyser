# Stage 3 — Division-by-zero detection

**Status:** complete
**Plan reference:** Phase 3 Milestone 5

## What was built

`DivisionByZeroRule` inspects every `BinOp` whose operator is `/`, `//`, or `%` and classifies the right operand:

| RHS shape | Severity | Reasoning |
|---|---|---|
| Literal `0` or `0.0` | **ERROR** | Definite crash at runtime. |
| Name only ever assigned to `0` in this scope | **ERROR** | Provably zero. |
| Non-zero numeric literal (`2`, `3.14`) | (silent) | Provably safe. |
| Anything else (variable, call, expression) | **INFO** | Possible — too noisy as WARNING. |

## Why three tiers (not two)

The plan called for "definite" vs "possible". Splitting "possible" off into INFO instead of WARNING is a deliberate severity choice: most divisions in real code are safe. If every `a / b` produced a WARNING, users would tune the analyzer out. INFO keeps the signal in the report without crowding the genuine errors.

This is the first rule that exercises severity beyond a single level — the `Finding.severity` field's `Literal["INFO", "WARNING", "ERROR"]` type now earns its keep.

## Constant-tracking, scoped

`_collect_constant_zero_names(scope_body)` records names whose only `Assign` value is a literal `0`. If a name is reassigned non-zero anywhere in the scope, it drops out of the set. The check runs **per scope**, not module-wide:

```python
def outer():
    z = 0           # not relevant to inner
    def inner(z):
        return 10 / z   # INFO — inner's z is a parameter
```

Function bodies are recursed into separately so an outer `z = 0` doesn't poison an inner `z`.

## Edge cases covered (with tests)

- `10 / 0`, `10 // 0`, `10 % 0`, `1 / 0.0` → ERROR
- `10 / x` (param) → INFO
- `10 / 2` → silent (provably safe)
- `z = 0; return 10 / z` → ERROR (constant-tracked)
- `z = 0; z = 5; return 10 / z` → INFO (mixed assignments invalidate the proof)
- Nested functions → outer constants don't leak

## Limitations (deliberate)

- **Single-scope constant tracking only.** No global propagation, no aliasing, no flow-sensitive narrowing (`if x != 0: a / x` still INFO).
- **No call-site tracking.** `divmod(a, b)` is not analyzed.
- **No symbolic reasoning.** `a / (1 - 1)` is INFO, not ERROR — we don't fold expressions.

These all under-report; none over-report. The rule won't generate false-positive ERRORs.

## How to use

```bash
python -m analyzer examples/division_by_zero.py
# [ERROR] Division by zero ('/' with literal 0) at line 2 (division-by-zero)
# [INFO]  Possible division by zero ('/' with non-constant divisor) at line 6 (division-by-zero)
```

Run only this rule's tests:

```bash
pytest tests/test_division_by_zero.py
```

## Key decisions

- **`%` and `//` count as division operators.** Both raise `ZeroDivisionError` at runtime — same risk profile as `/`.
- **Non-zero numeric literal RHS is silent, not INFO.** Otherwise every `x / 2` becomes a finding and INFO turns into background noise.
- **Constant tracking is "always-zero or nothing".** A name is in the zero-set only if every assignment to it is literal 0. Conservative, easy to reason about, no false ERRORs.

## What's next

All three Phase 3 rules are implemented. Stage 4 covers Phase 4 work: a richer integration test harness and an end-to-end CLI test running over the `examples/` folder. After that, packaging (Phase 5) and Phase 6 enhancements (unused imports, shadowed variables, severity-filter CLI flags).
