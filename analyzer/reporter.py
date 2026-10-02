"""Formats analyzer findings: terminal text, JSON, or SARIF 2.1.0."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["INFO", "WARNING", "ERROR"]


@dataclass(frozen=True)
class Finding:
    severity: Severity
    message: str
    line: int
    rule: str
    path: str = ""  # set by the runner; rules leave it empty


def format_finding(f: Finding, source_lines: list[str] | None = None) -> str:
    header = f"[{f.severity}] {f.message} at line {f.line} ({f.rule})"

    if not source_lines or f.line < 1 or f.line > len(source_lines):
        return header

    # Show 1 line before, the line itself, 1 line after (if they exist)
    start = max(0, f.line - 2)
    end = min(len(source_lines), f.line + 1)

    snippet = []
    for i in range(start, end):
        line_num = i + 1
        code = source_lines[i].rstrip()
        if line_num == f.line:
            snippet.append(f"  {line_num} | {code}  <-- HERE")
        else:
            snippet.append(f"  {line_num} | {code}")

    return header + "\n" + "\n".join(snippet)


def render(findings: list[Finding], source: str = "") -> str:
    if not findings:
        return "No issues found."

    source_lines = source.splitlines() if source else []
    sorted_findings = sorted(findings, key=lambda x: x.line)

    output = []
    for f in sorted_findings:
        output.append(format_finding(f, source_lines if source_lines else None))

    return "\n".join(output)


# --- multi-file output ------------------------------------------------------
#
# `results` is a sequence of (path, source, findings) and `errors` a sequence
# of (path, message), as produced by analyzer.runner.


def render_text(results: Sequence, errors: Sequence = ()) -> str:
    """Findings grouped under a header per file, plus a summary line."""
    blocks = []
    for path, source, findings in results:
        if findings:
            blocks.append(f"{path}\n{render(findings, source)}")
    total = sum(len(f) for _, _, f in results)
    files_with = sum(1 for _, _, f in results if f)
    checked = len(results)
    if total:
        summary = f"Found {total} issue(s) in {files_with} of {checked} file(s)."
    else:
        summary = f"No issues found in {checked} file(s)."
    if errors:
        summary += f" {len(errors)} file(s) could not be analyzed."
    return "\n\n".join([*blocks, summary])


def _finding_dict(f: Finding) -> dict:
    return {"path": f.path, "line": f.line, "severity": f.severity, "rule": f.rule, "message": f.message}


def render_json(results: Sequence, errors: Sequence = ()) -> str:
    findings = sorted((f for _, _, fs in results for f in fs), key=lambda f: (f.path, f.line))
    payload = {
        "findings": [_finding_dict(f) for f in findings],
        "errors": [{"path": str(p), "message": m} for p, m in errors],
        "summary": {
            "files": len(results),
            "findings": len(findings),
            "by_severity": {
                s: sum(1 for f in findings if f.severity == s) for s in ("ERROR", "WARNING", "INFO")
            },
        },
    }
    return json.dumps(payload, indent=2)


_SARIF_LEVEL = {"ERROR": "error", "WARNING": "warning", "INFO": "note"}


def _sarif_uri(path: str) -> str:
    p = Path(path)
    return p.resolve().as_uri() if p.is_absolute() else p.as_posix()


def render_sarif(results: Sequence, rules: Sequence, version: str, errors: Sequence = ()) -> str:
    """SARIF 2.1.0 — the format GitHub code scanning ingests."""
    rule_ids = [r.name for r in rules]
    sarif_results = []
    for _, _, findings in results:
        for f in sorted(findings, key=lambda f: f.line):
            result = {
                "ruleId": f.rule,
                "level": _SARIF_LEVEL[f.severity],
                "message": {"text": f.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": _sarif_uri(f.path)},
                            "region": {"startLine": f.line},
                        }
                    }
                ],
            }
            if f.rule in rule_ids:
                result["ruleIndex"] = rule_ids.index(f.rule)
            sarif_results.append(result)

    run = {
        "tool": {
            "driver": {
                "name": "analyzer",
                "version": version,
                "rules": [
                    {"id": r.name, "shortDescription": {"text": r.description or r.name}} for r in rules
                ],
            }
        },
        "results": sarif_results,
        "invocations": [
            {
                "executionSuccessful": not errors,
                "toolExecutionNotifications": [
                    {"level": "error", "message": {"text": f"{p}: {m}"}} for p, m in errors
                ],
            }
        ],
    }
    doc = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [run],
    }
    return json.dumps(doc, indent=2)
