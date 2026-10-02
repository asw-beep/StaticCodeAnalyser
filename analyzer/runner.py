"""Analyze many files: discovery -> parse -> rules -> suppressions -> filters.

The CLI is a thin layer over `run()`; keeping the orchestration here makes it
testable without going through argparse or capturing stdout.

A file that can't be read or parsed is recorded as an error and the run
continues — one broken file shouldn't hide findings in the rest.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from analyzer.config import SEVERITY_ORDER, ConfigError
from analyzer.discovery import iter_python_files
from analyzer.engine import analyze
from analyzer.parser import parse_file
from analyzer.reporter import Finding
from analyzer.rules.base import Rule
from analyzer.suppressions import is_suppressed, parse_suppressions


@dataclass
class FileResult:
    path: Path
    source: str
    findings: list[Finding]

    def __iter__(self):  # lets reporters unpack (path, source, findings)
        return iter((self.path, self.source, self.findings))


@dataclass
class RunResult:
    files: list[FileResult] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        return [f for r in self.files for f in r.findings]


def select_rules(rules: Sequence[Rule], select: Iterable[str] | None, ignore: Iterable[str]) -> list[Rule]:
    """Filter `rules` by name. Unknown names are an error, not silently ignored."""
    known = {r.name for r in rules}
    select = list(select) if select is not None else None
    ignore = list(ignore)
    unknown = sorted({*(select or []), *ignore} - known)
    if unknown:
        raise ConfigError(f"unknown rule(s): {', '.join(unknown)} (known: {', '.join(sorted(known))})")
    return [r for r in rules if (select is None or r.name in select) and r.name not in ignore]


def _read_error(path: Path, exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"file not found: {path}"
    if isinstance(exc, IsADirectoryError):
        return f"not a file: {path}"
    if isinstance(exc, SyntaxError):
        loc = f"{exc.filename}:{exc.lineno}" if exc.filename and exc.lineno else str(path)
        return f"syntax error in {loc}: {exc.msg}"
    if isinstance(exc, UnicodeDecodeError):
        return f"cannot decode {path} as UTF-8: {exc}"
    return f"cannot read {path}: {exc}"


def run(
    paths: Iterable[str | Path],
    rules: Sequence[Rule],
    exclude: Iterable[str] = (),
    min_severity: str = "INFO",
) -> RunResult:
    threshold = SEVERITY_ORDER[min_severity]
    result = RunResult()
    for path in iter_python_files(paths, exclude):
        try:
            tree, source = parse_file(path)
        except (OSError, SyntaxError, UnicodeDecodeError) as e:
            result.errors.append((path, _read_error(path, e)))
            continue
        suppressions = parse_suppressions(source)
        findings = [
            dataclasses.replace(f, path=str(path))
            for f in analyze(tree, list(rules))
            if SEVERITY_ORDER[f.severity] >= threshold and not is_suppressed(f, suppressions)
        ]
        result.files.append(FileResult(path, source, findings))
    return result
