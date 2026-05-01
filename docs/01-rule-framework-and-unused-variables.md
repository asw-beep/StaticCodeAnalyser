# Stage 1 — Rule framework + unused-variable detection

**Status:** complete
**Plan reference:** Phase 3 Milestones 2 and 3

## What was built

1. A `Rule` abstract base class — every future rule subclasses it.
2. The engine now runs each registered rule against the parsed module and concatenates findings.
3. The first real rule: `UnusedVariableRule`.

## The Rule contract

```python
class Rule(ABC):
    name: str
    severity: str = "WARNING"
    def check(self, tree: ast.Module) -> list[Finding]: ...
```

- Each rule is **stateless across invocations** and receives the whole module.
- Rules do not share state. Anything cross-rule belongs in the engine.
- The engine has a `default_rules()` factory; tests can pass a custom list to `analyze(tree, rules=[...])` to isolate one rule.

## Unused-variable rule — what counts as "unused"

A name is flagged when, in the scope where it was assigned:
- it is never loaded (`Load` context) inside that scope, **and**
- it is never loaded by any nested function/class (closures count as use), **and**
- it is not exempt.

**Exemptions** (deliberate, not bugs to fix later):
| Case | Why exempt |
|---|---|
| Function parameters | Part of the callable's API; caller chooses to pass them. |
| `for x in ...` loop variables | Iterating for side effects is a normal Python idiom. |
| Names starting with `_` | Convention for "intentionally unused". |
| `x += 1` (`AugAssign`) | The op is both a load and a store. |
| `def f(): ...` and `class C: ...` at any level | Declarations may be public API; flagging them creates noise. |

## Scope model

Per-function (and module) scope, not whole-program. Nested functions form their own scopes but their loads are checked against the enclosing scope — so closure variables don't get false-flagged.

Implementation: `_ScopeVisitor` walks one scope's statements and **does not descend into** nested `FunctionDef` / `AsyncFunctionDef` / `ClassDef` bodies for the assignment/load bookkeeping. Decorators, default arguments, and class bases ARE visited in the enclosing scope (that's where they evaluate). Then `_analyze_scope` recurses into nested function/class bodies.

## Edge cases covered (with tests)

- Simple unused local: flagged
- Loop variables: not flagged
- Function params (incl. `*args`, `**kw`): not flagged
- Underscore-prefixed names: not flagged
- `total += i`-style augmented assignment: not flagged
- Closure use (`inner` reads `x` from `outer`): `x` not flagged
- Module-level `CONST = 1` never read: flagged
- Tuple unpacking `a, b = 1, 2` with only `a` used: flags `b` only

See `tests/test_unused_variable.py` for executable specs.

## How to use

```bash
python -m analyzer examples/unused_variable.py
# [WARNING] Unused variable 'unused' at line 3 (unused-variable)
```

Run only this rule's tests:

```bash
pytest tests/test_unused_variable.py
```

## Key decisions

- **Skip nested-function bodies during enclosing-scope traversal, then recurse.** A naive `ast.walk` at module level would double-count assignments and break scope semantics.
- **Closure detection is conservative:** any `Name(ctx=Load)` inside a nested scope counts as a use of that name in the enclosing scope. This may *under*-flag (false negatives) when a nested scope shadows a name, but never *over*-flags. Acceptable tradeoff for a Phase-3 milestone — refine later if it bites.
- **`def`/`class` are not assignments for this rule.** Otherwise every top-level helper function in a library file would be flagged. Real "unused function" detection needs cross-module reachability and belongs in Phase 6.

## What's next

Stage 2 — Plan Milestone 4: dead-code detection (statements after `return`, `break`, `continue`, `raise`).
