"""Formats analyzer findings for terminal output."""

from dataclasses import dataclass
from typing import Literal

Severity = Literal["INFO", "WARNING", "ERROR"]


@dataclass(frozen=True)
class Finding:
    severity: Severity
    message: str
    line: int
    rule: str


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
