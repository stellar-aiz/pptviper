"""python -m scripts.acceptance の入口。"""

import argparse
import json
from pathlib import Path

from scripts.acceptance.compare import compare
from scripts.acceptance.generate import generate, write_json
from scripts.acceptance.review import aggregate, build


def main() -> int:
    parser = argparse.ArgumentParser(description="PowerPoint 実機検証の補助")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("directory", type=Path)
    cal = sub.add_parser("compare")
    for field in ("deck", "manifest", "csv", "output"):
        cal.add_argument(field, type=Path)
    cal.add_argument("--mode", choices=("macro", "manual"), default="macro")
    page = sub.add_parser("review")
    for field in ("deck", "images", "output"):
        page.add_argument(field, type=Path)
    page.add_argument("--provenance", choices=("generated", "human"), required=True)
    total = sub.add_parser("aggregate")
    total.add_argument("manifest", type=Path)
    total.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            generate(args.directory)
        elif args.command == "review":
            build(args.deck, args.images, args.output, args.provenance)
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            result = (
                compare(args.deck, manifest, args.csv, args.mode)
                if args.command == "compare"
                else aggregate(manifest["decks"], args.manifest.parent)
            )
            write_json(args.output, result)
            return 0 if result["passed"] else 1
        return 0
    except (ValueError, KeyError, TypeError, OSError, ZeroDivisionError) as error:
        parser.exit(2, f"証跡エラー: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
