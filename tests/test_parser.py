import ast
from pathlib import Path

from analyzer.parser import dump_tree, parse_file

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_parse_file_returns_module_and_source():
    tree, source = parse_file(EXAMPLES / "unused_variable.py")
    assert isinstance(tree, ast.Module)
    assert isinstance(source, str) and len(source) > 0


def test_dump_tree_is_nonempty_string():
    tree, source = parse_file(EXAMPLES / "dead_code.py")
    out = dump_tree(tree)
    assert isinstance(out, str) and "FunctionDef" in out
