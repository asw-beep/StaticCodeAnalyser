"""Command-line entry point.

Exit codes:
    0  no findings
    1  one or more findings reported
    2  input error (missing file, syntax error, unreadable file)
"""

from __future__ import annotations

import argparse
import sys

from analyzer.engine import analyze
from analyzer.parser import dump_tree, parse_file
from analyzer.reporter import render


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="analyzer", description="Static analyzer for Python files.")
    p.add_argument("path", help="Path to a .py file")
    p.add_argument("--ast", action="store_true", help="Print first 30 lines of the parsed AST and exit")
    p.add_argument("--dump-ast", action="store_true", help="Print the full parsed AST and exit")
    args = p.parse_args(argv)

    try:
        tree, source = parse_file(args.path)
    except FileNotFoundError:
        print(f"analyzer: file not found: {args.path}", file=sys.stderr)
        return 2
    except IsADirectoryError:
        print(f"analyzer: not a file: {args.path}", file=sys.stderr)
        return 2
    except SyntaxError as e:
        loc = f"{e.filename}:{e.lineno}" if e.filename and e.lineno else args.path
        print(f"analyzer: syntax error in {loc}: {e.msg}", file=sys.stderr)
        return 2
    except UnicodeDecodeError as e:
        print(f"analyzer: cannot decode {args.path} as UTF-8: {e}", file=sys.stderr)
        return 2

    if args.ast or args.dump_ast:
        full_output = dump_tree(tree)
        if args.ast:
            lines = full_output.splitlines()[:30]
            print("\n".join(lines))
            if len(full_output.splitlines()) > 30:
                print("... (truncated, use --dump-ast for full output)")
        else:
            print(full_output)
        return 0

    findings = analyze(tree)
    print(render(findings, source))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
