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


def format_finding(f: Finding) -> str:
    return f"[{f.severity}] {f.message} at line {f.line} ({f.rule})"


def render(findings: list[Finding]) -> str:
    if not findings:
        return "No issues found."
    return "\n".join(format_finding(f) for f in sorted(findings, key=lambda x: x.line))
