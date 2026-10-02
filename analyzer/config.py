"""Project configuration from `[tool.analyzer]` in pyproject.toml.

    [tool.analyzer]
    select = ["dead-code", "sql-injection"]   # default: every rule
    ignore = ["division-by-zero"]
    exclude = ["build", "tests/fixtures/*"]   # applied when scanning directories
    min-severity = "WARNING"                  # INFO | WARNING | ERROR

Discovery walks up from the starting directory to the nearest pyproject.toml
that has a `[tool.analyzer]` table. CLI flags override config values.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on 3.10
    import tomli as tomllib

SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "ERROR": 2}

_KNOWN_KEYS = {"select", "ignore", "exclude", "min-severity"}


class ConfigError(Exception):
    pass


@dataclass
class Config:
    select: list[str] | None = None  # None means "all rules"
    ignore: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    min_severity: str = "INFO"
    source: Path | None = None  # file the config was read from, if any


def _str_list(table: dict, key: str, path: Path) -> list[str] | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{path}: [tool.analyzer] '{key}' must be a list of strings")
    return value


def _read_table(path: Path) -> dict | None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e
    return data.get("tool", {}).get("analyzer")


def find_config(start: Path) -> Path | None:
    """Nearest pyproject.toml at or above `start` that has [tool.analyzer]."""
    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file() and _read_table(candidate) is not None:
            return candidate
    return None


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    table = _read_table(path)
    if table is None:
        return Config(source=path)

    unknown = set(table) - _KNOWN_KEYS
    if unknown:
        raise ConfigError(f"{path}: unknown [tool.analyzer] key(s): {', '.join(sorted(unknown))}")

    min_severity = table.get("min-severity", "INFO")
    if not isinstance(min_severity, str) or min_severity.upper() not in SEVERITY_ORDER:
        raise ConfigError(f"{path}: 'min-severity' must be one of {', '.join(SEVERITY_ORDER)}")

    return Config(
        select=_str_list(table, "select", path),
        ignore=_str_list(table, "ignore", path) or [],
        exclude=_str_list(table, "exclude", path) or [],
        min_severity=min_severity.upper(),
        source=path,
    )
