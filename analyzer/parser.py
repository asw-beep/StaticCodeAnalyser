"""Thin wrapper around ast.parse so callers don't import ast directly."""

import ast
from pathlib import Path


def parse_file(path: str | Path) -> tuple[ast.Module, str]:
    """Parse a file and return (tree, source_code)."""
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return tree, source


def dump_tree(tree: ast.AST, indent: int = 2) -> str:
    return ast.dump(tree, indent=indent)
