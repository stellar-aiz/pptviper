"""コマンドラインの入口。検査機能は後続 Issue で追加する。"""

import argparse
from collections.abc import Sequence

from pptviper import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PPTX の静的検査ツール（現在は開発基盤のみ）"
    )
    parser.add_argument(
        "--version", action="version", version=f"pptviper {__version__}"
    )
    parser.parse_args(argv)
    parser.print_help()
    return 0
