# Stage 4 — Integration testing

**Status:** complete
**Plan reference:** Phase 4 (Testing)

## What was built

End-to-end CLI tests in `tests/test_integration.py` that drive the full pipeline (parser → engine → all three rules → reporter → stdout) over real fixtures, plus two new fixtures:

- `examples/clean.py` — negative control. Must produce zero findings; guards against false positives creeping in as new rules are added.
- `examples/kitchen_sink.py` — positive control. Triggers all three rules in one file; guards multi-rule output ordering and the rule-tagging suffix.

## What integration tests catch that unit tests don't

Each rule has its own unit tests over hand-built ASTs. Those don't catch:

- The CLI exit code contract (0 = clean, 1 = findings).
- The reporter's cross-rule sort-by-line order — findings from different rules concatenate in rule order in the engine; the reporter is what enforces the line-sorted view.
- `--dump-ast` short-circuiting the engine.
- Error propagation: missing files, syntax errors. We assert these raise rather than swallow — the CLI is intentionally not catching them yet (no error-formatting layer exists).

## Test inventory added

| Test | Guards |
|---|---|
| `test_clean_example_has_no_findings` | False-positive regression. |
| `test_unused_variable_example` | Rule wiring + reporter format. |
| `test_dead_code_example` | Both `return` and `break` flagged in one run. |
| `test_division_by_zero_example` | Multi-severity output (`[ERROR]` + `[INFO]`). |
| `test_kitchen_sink_triggers_all_rules` | All three rule tags appear in one report. |
| `test_findings_sorted_by_line` | Cross-rule output ordering. |
| `test_missing_file_raises` | I/O error contract. |
| `test_syntax_error_in_input_raises` | Parser error contract. |
| `test_dump_ast_short_circuits_engine` | `--dump-ast` doesn't run rules. |

## Total test count

39 passing (parser 2, CLI 2, unused-variable 8, dead-code 8, division-by-zero 10, integration 9).

## Decisions

- **Errors propagate, not get caught.** A real lint tool wraps `FileNotFoundError` / `SyntaxError` in a friendly message. We don't yet — Phase 5 packaging is a more natural place to add an error-formatting boundary so it's documented in user-facing help. For now the tests pin "raises" as the current behavior so we'll notice when we change it.
- **`clean.py` deliberately avoids division.** The INFO division-by-zero rule has no flow-sensitive narrowing (documented limitation in Stage 3) — even safe-by-guard divisions like `a / b if b else 0` would fire. The fixture sidesteps that to remain a true negative control. Adding flow-sensitive narrowing is a Phase 6 enhancement.
- **Kitchen-sink fixture exercises all severities and rules together** so the cross-rule sort and the severity tags are tested in one place rather than scattered across rule unit tests.

## What's next

Stage 5 — Phase 5 packaging: install via `pip install .`, validate the `analyzer` console script, and add a `README.md` covering install + usage + example output. After that, Phase 6 enhancements: severity-filter / rule-filter CLI flags, unused imports, shadowed variables.
