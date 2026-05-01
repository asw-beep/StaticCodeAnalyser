"""End-to-end tests: run the CLI against fixtures in examples/ and assert
on the full output. These guard the integration of parser + engine + all
rules + reporter, which unit tests don't cover.
"""

from pathlib import Path

from analyzer.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"


def _run(path: Path, capsys) -> tuple[int, str]:
    rc = main([str(path)])
    return rc, capsys.readouterr().out


def test_clean_example_has_no_findings(capsys):
    rc, out = _run(EXAMPLES / "clean.py", capsys)
    assert rc == 0
    assert out.strip() == "No issues found."


def test_unused_variable_example(capsys):
    rc, out = _run(EXAMPLES / "unused_variable.py", capsys)
    assert rc == 1
    assert "Unused variable 'unused'" in out
    assert "(unused-variable)" in out


def test_dead_code_example(capsys):
    rc, out = _run(EXAMPLES / "dead_code.py", capsys)
    assert rc == 1
    assert "Unreachable code after 'return'" in out
    assert "Unreachable code after 'break'" in out


def test_division_by_zero_example(capsys):
    rc, out = _run(EXAMPLES / "division_by_zero.py", capsys)
    assert rc == 1
    assert "[ERROR]" in out
    assert "[INFO]" in out


def test_kitchen_sink_triggers_all_rules(capsys):
    rc, out = _run(EXAMPLES / "kitchen_sink.py", capsys)
    assert rc == 1
    assert "(unused-variable)" in out
    assert "(dead-code)" in out
    assert "(division-by-zero)" in out


def test_findings_sorted_by_line(capsys):
    """Reporter must order findings ascending by line, regardless of which rule produced them."""
    _, out = _run(EXAMPLES / "kitchen_sink.py", capsys)
    lines = [ln for ln in out.splitlines() if ln.startswith("[")]
    line_numbers = [int(ln.split(" at line ")[1].split(" ")[0]) for ln in lines]
    assert line_numbers == sorted(line_numbers)


def test_missing_file_exits_with_code_2(capsys):
    rc = main([str(EXAMPLES / "does_not_exist.py")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "file not found" in err


def test_syntax_error_in_input_exits_with_code_2(tmp_path, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text("def f(:\n    pass\n", encoding="utf-8")
    rc = main([str(bad)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "syntax error" in err


def test_ast_short_circuits_engine_with_preview(capsys):
    rc, out = _run_with_args(["--ast"], EXAMPLES / "kitchen_sink.py", capsys)
    assert rc == 0
    # Engine output should be absent; AST dump preview should be present.
    assert "[ERROR]" not in out
    assert "[WARNING]" not in out
    assert "Module" in out
    # Should show truncation message for a non-trivial file.
    assert "truncated" in out


def test_dump_ast_short_circuits_engine_full(capsys):
    rc, out = _run_with_args(["--dump-ast"], EXAMPLES / "kitchen_sink.py", capsys)
    assert rc == 0
    # Engine output should be absent; full AST dump should be present.
    assert "[ERROR]" not in out
    assert "[WARNING]" not in out
    assert "FunctionDef" in out


def _run_with_args(extra: list[str], path: Path, capsys) -> tuple[int, str]:
    rc = main([str(path), *extra])
    return rc, capsys.readouterr().out
