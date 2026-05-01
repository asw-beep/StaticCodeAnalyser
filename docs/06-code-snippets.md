# Stage 6a — Code snippets with context

**Status:** complete
**Feature:** enhanced reporter output

## What changed

The reporter now shows code snippets instead of just line numbers. Each finding includes:

1. The message and line number (header)
2. Context: 1 line before, the problematic line, 1 line after
3. The problematic line marked with `<-- HERE`

Example:

```
[WARNING] Unused variable 'unused' at line 5 (unused-variable)
  4 | def buggy(x):
  5 |     unused = 99  <-- HERE
  6 |     z = 0
```

## Implementation

- `parse_file()` now returns `(tree, source)` tuple instead of just the tree.
- `render()` accepts an optional `source` parameter.
- `format_finding()` takes `source_lines` and displays context with line numbers.
- All tests updated; 41 passing.

## Why this matters

Modern linters (pylint, flake8, mypy) show code snippets so users can immediately understand what the issue is without jumping to their editor. This is table-stakes UX now.

Before: `[WARNING] Unused variable 'unused' at line 5 (unused-variable)`

After: context + marker so users see exactly what triggered the rule.

## Edge cases handled

- Files shorter than expected (start/end bounds checked)
- Missing source (gracefully falls back to message-only)
- Findings on line 1 (shows only lines 1–2 context)
- Findings on the last line (shows last 3 lines)
