"""Analyzer engine. Walks the AST and dispatches to rules.

This is a stub for milestone 0; rule dispatch and visitor logic land in
milestone 2.
"""

import ast

from analyzer.reporter import Finding


def analyze(tree: ast.Module) -> list[Finding]:
    return []
