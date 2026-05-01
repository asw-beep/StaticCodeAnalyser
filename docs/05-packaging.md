# Stage 5 — Packaging and friendly CLI errors

**Status:** complete
**Plan reference:** Phase 5 (Deployment)

## What was built

1. The CLI now formats input errors instead of letting them propagate.
2. `pip install .` works; the `analyzer` console script is registered via `pyproject.toml`'s `[project.scripts]` and verified end-to-end.
3. A user-facing `README.md` covering install, usage, exit codes, the rule catalog, and where to find design docs.

## CLI error contract (new)

| Condition | Old behavior | New behavior |
|---|---|---|
| File missing | `FileNotFoundError` propagates | `analyzer: file not found: <path>` to stderr, exit 2 |
| Path is a directory | `IsADirectoryError` propagates | `analyzer: not a file: <path>` to stderr, exit 2 |
| File is not UTF-8 | `UnicodeDecodeError` propagates | `analyzer: cannot decode <path> as UTF-8: ...` to stderr, exit 2 |
| Syntax error | `SyntaxError` propagates | `analyzer: syntax error in <file>:<line>: <msg>` to stderr, exit 2 |

Exit-code conventions:
- `0` clean
- `1` findings
- `2` input error

This matches common lint-tool behavior (flake8, pylint) and keeps "the input was bad" distinct from "the input was fine but had issues" — important for shell pipelines and pre-commit hooks.

## Why stderr, not stdout

Errors go to stderr so a pipeline like `analyzer file.py | grep ERROR` doesn't conflate "no ERROR-severity findings" with "the file didn't exist". Findings stay on stdout because they're the tool's primary output.

## Packaging structure

`pyproject.toml` was already PEP-621-correct from Stage 0; this stage just verified the install path works and that `[project.scripts] analyzer = "analyzer.cli:main"` produces a callable script.

```toml
[project.scripts]
analyzer = "analyzer.cli:main"
```

`main()` returns an `int`; setuptools wraps that into a console-script entry point that calls `sys.exit(main())`. The `if __name__ == "__main__"` block in `cli.py` keeps `python -m analyzer` working too.

## Verification

```
$ pip install -e .
$ analyzer examples/kitchen_sink.py
[WARNING] Unused variable 'unused' at line 5 (unused-variable)
[ERROR] Division by zero ('/' by 'z', always 0) at line 7 (division-by-zero)
[WARNING] Unreachable code after 'return' at line 9 (dead-code)
[INFO] Possible division by zero ('/' with non-constant divisor) at line 13 (division-by-zero)
$ echo $?
1
```

## Test changes

`tests/test_integration.py` — the two error-propagation tests changed contract:

- `test_missing_file_raises` → `test_missing_file_exits_with_code_2` (asserts rc==2 + stderr message)
- `test_syntax_error_in_input_raises` → `test_syntax_error_in_input_exits_with_code_2`

Test count remains 39; one removed dependency on `pytest.raises`.

## Decisions

- **Catch only at the CLI boundary.** `parser.parse_file` still raises naturally; the CLI is the single layer that translates exceptions into user-facing exit codes. Library users (e.g. future programmatic embedders) get the raw exceptions.
- **Exit code 2 for input errors, not 1.** Conflating "found bugs" with "couldn't read the file" makes pre-commit hooks unable to distinguish "block the commit" from "config is broken". Stage 4 explicitly deferred this layer to packaging — it's now in.
- **README links to `docs/` for design rationale**, doesn't duplicate it. Stage docs are the canonical source for *why* each rule is shaped the way it is; the README is a quick-start.

## What's next

Phase 6 enhancements. Candidates, roughly in order of value:

1. `--severity` and `--rule` CLI filters (small, demonstrates extension points).
2. Unused-imports rule (natural fit; adds a fourth rule and stresses the rule framework).
3. Shadowed-variables rule.
4. Multi-file / directory input.
5. Flow-sensitive narrowing for division-by-zero (would let `clean.py` use the `a / b if b else 0` form again — see Stage 4 limitation).
