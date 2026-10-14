"""CLI entry point. Inspection will be added in subsequent issues."""

import argparse
from collections.abc import Sequence

from pptviper import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static PPTX inspection (development foundation only)"
    )
    parser.add_argument(
        "--version", action="version", version=f"pptviper {__version__}"
    )
    parser.parse_args(argv)
    parser.print_help()
    return 0
