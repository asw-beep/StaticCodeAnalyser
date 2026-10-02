from analyzer.reporter import Finding
from analyzer.suppressions import is_suppressed, parse_suppressions


def _finding(line: int, rule: str = "unsafe-execution") -> Finding:
    return Finding(severity="ERROR", message="m", line=line, rule=rule)


def test_bare_marker_suppresses_every_rule_on_that_line():
    s = parse_suppressions("x = 1\ny = eval(s)  # analyzer: ignore\n")
    assert is_suppressed(_finding(2), s)
    assert is_suppressed(_finding(2, "unused-variable"), s)
    assert not is_suppressed(_finding(1), s)


def test_bracketed_marker_suppresses_only_listed_rules():
    s = parse_suppressions("y = eval(s)  # analyzer: ignore[unsafe-execution, dead-code]\n")
    assert is_suppressed(_finding(1, "unsafe-execution"), s)
    assert is_suppressed(_finding(1, "dead-code"), s)
    assert not is_suppressed(_finding(1, "unused-variable"), s)


def test_marker_inside_a_string_is_not_a_suppression():
    s = parse_suppressions('y = eval("# analyzer: ignore")\n')
    assert s == {}


def test_marker_can_follow_other_comment_text():
    s = parse_suppressions("y = eval(s)  # trusted input, analyzer: ignore[unsafe-execution]\n")
    assert is_suppressed(_finding(1), s)
