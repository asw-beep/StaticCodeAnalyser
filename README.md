# analyzer

A small static analyzer for Python source files. Parses a `.py` file with the standard-library `ast` module, runs a set of rules over the tree, and prints findings.

## Install

From the repository root:

```bash
pip install .
```

Or, for development (changes take effect without reinstall):

```bash
pip install -e .
```

This registers an `analyzer` console script and exposes the package as `python -m analyzer`.

Requires Python 3.10+. No third-party runtime dependencies.

## Usage

```bash
analyzer path/to/file.py
```

Or without installing:

```bash
python -m analyzer path/to/file.py
```

### Options

| Flag | Effect |
|---|---|
| `--ast` | Print the first 30 lines of the parsed AST and exit. Quick preview. |
| `--dump-ast` | Print the full parsed AST and exit. Useful for understanding what the rules are seeing. |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | No findings (or `--ast`/`--dump-ast` succeeded). |
| 1 | One or more findings reported. |
| 2 | Input error: file missing, not readable, or contains a syntax error. |

## Rules

| Rule | Severity | Detects |
|---|---|---|
| `unused-variable` | WARNING | Names assigned but never read in the same scope. Exempts function parameters, loop variables, names starting with `_`, augmented assignments, and `def`/`class` declarations. Closure references count as use. |
| `dead-code` | WARNING | Statements that follow `return`, `raise`, `break`, or `continue` in the same block. Reports only the first dead statement per block. |
| `division-by-zero` | ERROR / INFO | ERROR for literal-zero divisors (or names provably always-zero in scope). INFO for non-constant divisors (`/`, `//`, `%`). Non-zero numeric literal divisors are silent. |
| `unsafe-execution` | ERROR / WARNING | ERROR for `eval`/`exec`/`compile`, `os.system(...)`, and `subprocess.*(..., shell=True)`. WARNING for `pickle.load`/`pickle.loads` and `yaml.load(...)` without `Loader=yaml.SafeLoader`. |
| `hardcoded-secrets` | ERROR | Non-empty, non-placeholder string literals assigned to credential-shaped names (`password`, `secret`, `api_key`, `token`, ...) or passed as credential-shaped keyword arguments. |
| `sql-injection` | ERROR | `.execute(...)`/`.executemany(...)` calls whose SQL argument is built with an f-string, string concatenation, `%` formatting, or `str.format()` instead of a parameterized query. |

## Example

```bash
$ analyzer examples/kitchen_sink.py
[WARNING] Unused variable 'unused' at line 5 (unused-variable)
  4 | def buggy(x):
  5 |     unused = 99               # unused-variable  <-- HERE
  6 |     z = 0
[ERROR] Division by zero ('/' by 'z', always 0) at line 7 (division-by-zero)
  6 |     z = 0
  7 |     result = x / z            # division-by-zero (ERROR, name tracked)  <-- HERE
  8 |     return result
[WARNING] Unreachable code after 'return' at line 9 (dead-code)
  8 |     return result
  9 |     print("never runs")       # dead-code  <-- HERE
  10 | 
[INFO] Possible division by zero ('/' with non-constant divisor) at line 13 (division-by-zero)
  12 | def maybe(x, divisor):
  13 |     return x / divisor        # division-by-zero (INFO)  <-- HERE
  14 | 
[ERROR] Use of 'eval()' allows arbitrary code execution at line 17 (unsafe-execution)
  16 | def run_untrusted(expr):
  17 |     return eval(expr)         # unsafe-execution (ERROR)  <-- HERE
  18 | 
[ERROR] Hardcoded secret in variable 'API_KEY' at line 20 (hardcoded-secrets)
  19 | 
  20 | API_KEY = "sk-live-abc123def456"  # hardcoded-secrets (ERROR)  <-- HERE
  21 | 
[ERROR] SQL query built with an f-string instead of a parameterized query in 'execute()' at line 24 (sql-injection)
  23 | def query_user(cursor, user_id):
  24 |     cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")  # sql-injection (ERROR)  <-- HERE
  25 |     return API_KEY
```

## Project layout

```
analyzer/         package — parser, engine, reporter, rules/
examples/         sample .py files exercising each rule
tests/            pytest suite
docs/             one document per build stage; read these to understand
                  why each rule is shaped the way it is and what's
                  deliberately not handled
.github/workflows/ci.yml   CI: ruff check + pytest on every push/PR
Plan.md           original phased build plan
```

`docs/` is the canonical reference for design decisions and known limitations of each rule. Start with `docs/00-project-setup.md`.

## Running the test suite

```bash
pip install pytest
pytest
```

## Linting

```bash
pip install ruff
ruff check .
```

CI (`.github/workflows/ci.yml`) runs both `ruff check .` and `pytest -q` on every push and pull request.

## Status

Phases 1–5 of `Plan.md` are complete (requirements, design, all three Phase-3 rules, integration testing, packaging), plus three additional security-focused rules (`unsafe-execution`, `hardcoded-secrets`, `sql-injection`) and CI automation. Further Phase 6 enhancements (unused imports, shadowed variables, multi-file analysis, severity-filter CLI flags) are not yet implemented.
