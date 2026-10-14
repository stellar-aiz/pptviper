"""Command-line static PPTX inspection."""

import argparse
from collections.abc import Sequence

from pptviper import __version__
from pptviper.inspection import inspect


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lightweight static PPTX inspection")
    parser.add_argument(
        "--version", action="version", version=f"pptviper {__version__}"
    )
    parser.add_argument("input", nargs="?", help="PPTX input file (read-only)")
    parser.add_argument("--config", help="TOML settings file")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    if args.input is None:
        parser.print_help()
        return 0
    report = inspect(args.input, config=args.config)
    print(report.to_json() if args.format == "json" else report.to_text(), end="")
    return report.exit_code
