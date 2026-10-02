"""Command-line entry point.

Exit codes:
    0  no findings
    1  one or more findings reported
    2  input or usage error (missing file, syntax error, unreadable file, bad
       config, unknown rule). Takes precedence over 1: if any file could not
       be analyzed, the run is not trustworthy as a pass/fail gate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analyzer import __version__
from analyzer.config import SEVERITY_ORDER, ConfigError, find_config, load_config
from analyzer.engine import default_rules
from analyzer.parser import dump_tree, parse_file
from analyzer.reporter import render, render_json, render_sarif, render_text
from analyzer.runner import run, select_rules


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="analyzer", description="Static analyzer for Python files.")
    p.add_argument("paths", nargs="*", metavar="path", help="Python files or directories to analyze")
    p.add_argument("--format", choices=["text", "json", "sarif"], default="text", help="Output format")
    p.add_argument("--select", type=_csv, metavar="RULES", help="Comma-separated rules to run (default: all)")
    p.add_argument("--ignore", type=_csv, metavar="RULES", help="Comma-separated rules to skip")
    p.add_argument(
        "--min-severity",
        type=str.upper,
        choices=list(SEVERITY_ORDER),
        help="Hide findings below this severity",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Skip matching files/dirs when scanning directories (repeatable)",
    )
    p.add_argument("--config", type=Path, help="pyproject.toml to read [tool.analyzer] from")
    p.add_argument("--list-rules", action="store_true", help="List available rules and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--ast", action="store_true", help="Print first 30 lines of the parsed AST and exit")
    p.add_argument("--dump-ast", action="store_true", help="Print the full parsed AST and exit")
    return p


def _print_ast(path: str, full: bool) -> int:
    try:
        tree, _ = parse_file(path)
    except FileNotFoundError:
        print(f"analyzer: file not found: {path}", file=sys.stderr)
        return 2
    except SyntaxError as e:
        print(f"analyzer: syntax error in {path}: {e.msg}", file=sys.stderr)
        return 2
    output = dump_tree(tree)
    if full:
        print(output)
    else:
        lines = output.splitlines()
        print("\n".join(lines[:30]))
        if len(lines) > 30:
            print("... (truncated, use --dump-ast for full output)")
    return 0


def _tolerate_unencodable_output() -> None:
    # Source snippets can contain any Unicode; a cp1252 Windows console can't
    # print all of it. Substitute rather than crash with a traceback (which
    # would also exit 1 and look like "findings found").
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _tolerate_unencodable_output()
    parser = _build_parser()
    args = parser.parse_args(argv)
    all_rules = default_rules()

    if args.list_rules:
        width = max(len(r.name) for r in all_rules)
        for r in all_rules:
            print(f"{r.name:<{width}}  {r.description}")
        return 0

    if not args.paths:
        parser.error("at least one path is required")

    if args.ast or args.dump_ast:
        if len(args.paths) != 1:
            print("analyzer: --ast/--dump-ast take exactly one file", file=sys.stderr)
            return 2
        return _print_ast(args.paths[0], full=args.dump_ast)

    try:
        config = load_config(args.config if args.config else find_config(Path.cwd()))
        rules = select_rules(
            all_rules,
            args.select if args.select is not None else config.select,
            args.ignore if args.ignore is not None else config.ignore,
        )
    except ConfigError as e:
        print(f"analyzer: {e}", file=sys.stderr)
        return 2

    result = run(
        args.paths,
        rules,
        exclude=[*config.exclude, *args.exclude],
        min_severity=args.min_severity or config.min_severity,
    )

    for path, message in result.errors:
        print(f"analyzer: {message}", file=sys.stderr)

    if args.format == "json":
        print(render_json(result.files, result.errors))
    elif args.format == "sarif":
        print(render_sarif(result.files, rules, __version__, result.errors))
    elif len(result.files) == 1 and not result.errors:
        # Single file: keep the original, header-less output.
        only = result.files[0]
        print(render(only.findings, only.source))
    elif result.files:
        print(render_text(result.files, result.errors))

    if result.errors:
        return 2
    return 1 if result.findings else 0


if __name__ == "__main__":
    sys.exit(main())
