# Stage 0 — Project Setup

**Status:** complete
**Plan reference:** Phase 2 (System Design) + Phase 3 Milestone 1 (AST understanding)

## What was built

A runnable scaffold of the analyzer pipeline with no rule logic yet. Every later milestone slots a piece into one of these existing modules instead of restructuring the project.

## Layout

```
analyzer/
  __init__.py        package marker, version
  __main__.py        enables `python -m analyzer ...`
  cli.py             argparse entry point, calls parser + engine + reporter
  parser.py          parse_file(), dump_tree() — wraps ast.parse / ast.dump
  engine.py          analyze(tree) -> list[Finding]   (stub: returns [])
  reporter.py        Finding dataclass + render() formatter
  rules/             empty package; one class per rule lands here later
examples/            sample .py files exercising each future rule
tests/               pytest suite
docs/                this folder — one file per milestone
pyproject.toml       PEP 621 metadata, registers `analyzer` console script
```

## Pipeline (current state)

```
file path -> parser.parse_file -> ast.Module -> engine.analyze -> [Finding] -> reporter.render -> stdout
```

`engine.analyze` is a stub returning `[]`. `--dump-ast` short-circuits the engine and prints `ast.dump` output — useful while learning AST node types.

## How to use

Run on a sample file:

```bash
python -m analyzer examples/unused_variable.py
# -> No issues found.   (engine is still a stub)
```

Inspect the AST of any file:

```bash
python -m analyzer examples/dead_code.py --dump-ast
```

Run tests:

```bash
pytest
```

Install as a CLI (editable):

```bash
pip install -e .
analyzer examples/division_by_zero.py
```

## Key decisions

- **`Finding` is a frozen dataclass, not a dict.** Rules will produce many of these; a typed object catches mistakes earlier than stringly-typed dicts and lets the reporter sort/filter without guessing keys.
- **`engine.analyze` takes an `ast.Module`, not a path.** Keeps parsing separate from analysis so tests can hand the engine a hand-built tree without touching the filesystem.
- **Rules will live in `analyzer/rules/` as one class per file.** Matches the plan's "modular rules" goal and keeps each rule's tests focused.
- **CLI exit code: 1 if any finding, 0 if clean.** Standard lint-tool convention so the analyzer can be wired into pre-commit hooks later.

## What's next

Stage 1 — Milestone 2: implement the `ast.NodeVisitor`-based engine and a `Rule` base class so the first real rule (unused variables) has somewhere to plug in.
