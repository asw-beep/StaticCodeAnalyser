"""Command-line entry point."""

import argparse
import sys

from analyzer.engine import analyze
from analyzer.parser import dump_tree, parse_file
from analyzer.reporter import render


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="analyzer", description="Static analyzer for Python files.")
    p.add_argument("path", help="Path to a .py file")
    p.add_argument("--dump-ast", action="store_true", help="Print the parsed AST and exit")
    args = p.parse_args(argv)

    tree = parse_file(args.path)

    if args.dump_ast:
        print(dump_tree(tree))
        return 0

    findings = analyze(tree)
    print(render(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
