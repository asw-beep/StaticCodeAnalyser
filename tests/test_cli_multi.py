"""CLI behaviour added for multi-file runs: directories, filtering, config,
suppressions and machine-readable output formats.

Every test chdirs into tmp_path so config discovery can't pick up a
pyproject.toml from the repository or the machine.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from analyzer.cli import main

REPO = Path(__file__).parent.parent

UNSAFE = "def f(s):\n    return eval(s)\n"           # unsafe-execution ERROR, line 2
UNUSED = "def g():\n    x = 1\n    return 0\n"       # unused-variable WARNING, line 2
MAYBE_DIV = "def h(a, b):\n    return a / b\n"       # division-by-zero INFO, line 2


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def write(rel: str, body: str) -> Path:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    return write


def _json(capsys, *argv) -> tuple[int, dict]:
    rc = main([*argv, "--format", "json"])
    return rc, json.loads(capsys.readouterr().out)


def test_directory_groups_findings_by_file_with_summary(project, capsys):
    project("a.py", UNSAFE)
    project("pkg/b.py", UNUSED)
    project("clean.py", "def ok():\n    return 1\n")
    rc = main(["."])
    out = capsys.readouterr().out
    assert rc == 1
    assert "a.py\n[ERROR]" in out
    assert os.path.join("pkg", "b.py") + "\n[WARNING]" in out
    assert "clean.py" not in out
    assert out.strip().endswith("Found 2 issue(s) in 2 of 3 file(s).")


def test_one_broken_file_does_not_hide_others(project, capsys):
    project("bad.py", "def f(:\n")
    project("good.py", UNSAFE)
    rc = main(["."])
    captured = capsys.readouterr()
    assert rc == 2  # input errors take precedence over findings
    assert "syntax error" in captured.err
    assert "eval()" in captured.out
    assert "1 file(s) could not be analyzed" in captured.out


def test_select_and_ignore(project, capsys):
    project("a.py", UNSAFE + UNUSED)
    _, data = _json(capsys, "a.py", "--select", "unused-variable")
    assert {f["rule"] for f in data["findings"]} == {"unused-variable"}
    _, data = _json(capsys, "a.py", "--ignore", "unused-variable,dead-code")
    assert {f["rule"] for f in data["findings"]} == {"unsafe-execution"}


def test_unknown_rule_is_a_usage_error(project, capsys):
    project("a.py", UNSAFE)
    rc = main(["a.py", "--select", "no-such-rule"])
    assert rc == 2
    assert "unknown rule(s): no-such-rule" in capsys.readouterr().err


def test_min_severity_filters_lower_findings(project, capsys):
    project("a.py", UNSAFE + UNUSED + MAYBE_DIV)
    _, data = _json(capsys, "a.py", "--min-severity", "warning")
    assert sorted(f["severity"] for f in data["findings"]) == ["ERROR", "WARNING"]
    rc, data = _json(capsys, "a.py", "--min-severity", "ERROR")
    assert [f["severity"] for f in data["findings"]] == ["ERROR"]
    assert rc == 1


def test_all_findings_filtered_exits_zero(project, capsys):
    project("a.py", MAYBE_DIV)
    assert main(["a.py", "--min-severity", "ERROR"]) == 0
    assert capsys.readouterr().out.strip() == "No issues found."


def test_inline_suppression(project, capsys):
    project("a.py", "def f(s):\n    return eval(s)  # analyzer: ignore[unsafe-execution]\n")
    assert main(["a.py"]) == 0


def test_pyproject_config_is_discovered_and_cli_overrides_it(project, capsys):
    project("pyproject.toml", '[tool.analyzer]\nignore = ["unsafe-execution"]\nexclude = ["vendor"]\n')
    project("a.py", UNSAFE + UNUSED)
    project("vendor/lib.py", UNSAFE)
    _, data = _json(capsys, ".")
    assert {(f["path"], f["rule"]) for f in data["findings"]} == {("a.py", "unused-variable")}
    # --ignore on the command line replaces the config's ignore list.
    _, data = _json(capsys, ".", "--ignore", "unused-variable")
    assert {f["rule"] for f in data["findings"]} == {"unsafe-execution"}


def test_bad_config_is_a_usage_error(project, capsys):
    project("pyproject.toml", '[tool.analyzer]\nmin-severity = "LOUD"\n')
    project("a.py", UNSAFE)
    assert main(["a.py"]) == 2
    assert "min-severity" in capsys.readouterr().err


def test_json_output_shape(project, capsys):
    project("a.py", UNSAFE)
    project("bad.py", "def f(:\n")
    rc, data = _json(capsys, ".")
    assert rc == 2
    assert data["findings"] == [
        {
            "path": "a.py",
            "line": 2,
            "severity": "ERROR",
            "rule": "unsafe-execution",
            "message": "Use of 'eval()' allows arbitrary code execution",
        }
    ]
    assert data["errors"][0]["path"] == "bad.py"
    assert data["summary"] == {
        "files": 1,
        "findings": 1,
        "by_severity": {"ERROR": 1, "WARNING": 0, "INFO": 0},
    }


def test_sarif_output_shape(project, capsys):
    project("pkg/a.py", UNSAFE + MAYBE_DIV)
    rc = main(["pkg", "--format", "sarif"])
    doc = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    assert all(r["shortDescription"]["text"] for r in rules)
    levels = {r["ruleId"]: r["level"] for r in run["results"]}
    assert levels == {"unsafe-execution": "error", "division-by-zero": "note"}
    for r in run["results"]:
        loc = r["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "pkg/a.py"  # forward slashes on every OS
        assert rules[r["ruleIndex"]]["id"] == r["ruleId"]
    assert run["invocations"][0]["executionSuccessful"] is True


def test_ast_requires_exactly_one_path(project, capsys):
    project("a.py", UNSAFE)
    project("b.py", UNSAFE)
    assert main(["a.py", "b.py", "--ast"]) == 2


def test_no_paths_is_a_usage_error(project):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_list_rules(capsys):
    assert main(["--list-rules"]) == 0
    out = capsys.readouterr().out
    assert "sql-injection" in out and "unused-variable" in out


def test_non_ascii_source_does_not_crash_on_a_legacy_console(project):
    # A cp1252 console can't encode '→'; output must degrade, not traceback.
    project("a.py", "def f():\n    x = '→'\n    return 0\n")
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONPATH": str(REPO)}
    proc = subprocess.run(
        [sys.executable, "-m", "analyzer", "a.py"], capture_output=True, env=env, cwd=os.getcwd()
    )
    assert proc.returncode == 1, proc.stderr
    assert b"Unused variable 'x'" in proc.stdout
