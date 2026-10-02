"""Expand CLI paths into the list of Python files to analyze.

- A file passed explicitly is always analyzed, whatever its extension and
  whatever the exclude patterns say — the user asked for it by name.
- A directory is walked recursively for `*.py` files. Hidden directories,
  virtualenvs, caches and build output are skipped, as is anything matching
  an exclude pattern.

Exclude patterns are fnmatch globs checked against both the entry's name
(`build`) and its path relative to the scanned directory (`tests/fixtures/*`).

Limitations (deliberate):
- `.gitignore` is not read; use `exclude` instead.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from fnmatch import fnmatch
from pathlib import Path

DEFAULT_EXCLUDES = (
    "__pycache__",
    "venv",
    "env",
    "build",
    "dist",
    "node_modules",
    "*.egg-info",
)


def _excluded(name: str, rel: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch(name, p) or fnmatch(rel, p) for p in patterns)


def iter_python_files(paths: Iterable[str | Path], exclude: Iterable[str] = ()) -> Iterator[Path]:
    """Yield files to analyze, de-duplicated, in a stable order.

    Paths that don't exist are yielded unchanged so the caller can report
    them as input errors alongside the files that did parse.
    """
    patterns = [*DEFAULT_EXCLUDES, *exclude]
    seen: set[Path] = set()

    def emit(p: Path) -> Iterator[Path]:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            yield p

    for raw in paths:
        root = Path(raw)
        if not root.is_dir():
            yield from emit(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            base = Path(dirpath)
            rel_base = base.relative_to(root)
            dirnames[:] = sorted(
                d
                for d in dirnames
                if not d.startswith(".") and not _excluded(d, (rel_base / d).as_posix(), patterns)
            )
            for name in sorted(filenames):
                if name.endswith(".py") and not _excluded(name, (rel_base / name).as_posix(), patterns):
                    yield from emit(base / name)
