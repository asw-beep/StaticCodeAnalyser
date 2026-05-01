from pathlib import Path

from analyzer.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_cli_reports_unused_variable_example(capsys):
    rc = main([str(EXAMPLES / "unused_variable.py")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "unused" in out.lower()


def test_cli_ast_preview(capsys):
    rc = main([str(EXAMPLES / "dead_code.py"), "--ast"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Module" in out or "FunctionDef" in out
    assert "truncated" in out or len(out.splitlines()) <= 30


def test_cli_dump_ast_full(capsys):
    rc = main([str(EXAMPLES / "dead_code.py"), "--dump-ast"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "FunctionDef" in out
