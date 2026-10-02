"""Inline suppression comments.

    x = eval(s)  # analyzer: ignore                     -> every rule on this line
    x = eval(s)  # analyzer: ignore[unsafe-execution]   -> just that rule
    x = eval(s)  # analyzer: ignore[rule-a, rule-b]     -> several rules

A suppression applies to findings reported on the same line as the comment.
Comments are found with `tokenize`, so the marker inside a string literal
does not count.
"""

from __future__ import annotations

import io
import re
import tokenize

from analyzer.reporter import Finding

# Searched only within COMMENT tokens, so it needn't start at the '#'.
_MARKER = re.compile(r"\banalyzer:\s*ignore(?:\[([^\]]*)\])?", re.IGNORECASE)

# line -> rules suppressed on that line; None means "all rules".
Suppressions = dict[int, "frozenset[str] | None"]


def parse_suppressions(source: str) -> Suppressions:
    out: Suppressions = {}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return out
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        m = _MARKER.search(tok.string)
        if not m:
            continue
        line = tok.start[0]
        if m.group(1) is None:
            out[line] = None
            continue
        rules = frozenset(r.strip() for r in m.group(1).split(",") if r.strip())
        existing = out.get(line, frozenset())
        out[line] = None if existing is None else existing | rules
    return out


def is_suppressed(finding: Finding, suppressions: Suppressions) -> bool:
    if finding.line not in suppressions:
        return False
    rules = suppressions[finding.line]
    return rules is None or finding.rule in rules
