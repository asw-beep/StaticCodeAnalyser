from pathlib import Path

from analyzer.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_cli_runs_clean(capsys):
    rc = main([str(EXAMPLES / "unused_variable.py")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No issues found." in out


def test_cli_dump_ast(capsys):
    rc = main([str(EXAMPLES / "dead_code.py"), "--dump-ast"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "FunctionDef" in out
