"""Thin wrapper around ast.parse so callers don't import ast directly."""

import ast
from pathlib import Path


def parse_file(path: str | Path) -> ast.Module:
    source = Path(path).read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))


def dump_tree(tree: ast.AST, indent: int = 2) -> str:
    return ast.dump(tree, indent=indent)
