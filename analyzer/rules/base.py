"""Rule base class.

A Rule is a self-contained analyzer over an ast.Module. The engine hands each
rule the parsed tree and collects whatever findings it returns. Rules do not
share state — anything cross-rule belongs in the engine.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod

from analyzer.reporter import Finding


class Rule(ABC):
    name: str
    severity: str = "WARNING"

    @abstractmethod
    def check(self, tree: ast.Module) -> list[Finding]:
        ...
