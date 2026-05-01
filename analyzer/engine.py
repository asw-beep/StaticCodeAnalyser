"""Analyzer engine. Runs every registered rule against a parsed module."""

from __future__ import annotations

import ast

from analyzer.reporter import Finding
from analyzer.rules.base import Rule
from analyzer.rules.unused_variable import UnusedVariableRule


def default_rules() -> list[Rule]:
    return [UnusedVariableRule()]


def analyze(tree: ast.Module, rules: list[Rule] | None = None) -> list[Finding]:
    rules = rules if rules is not None else default_rules()
    findings: list[Finding] = []
    for rule in rules:
        findings.extend(rule.check(tree))
    return findings
