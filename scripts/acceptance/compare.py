"""測定の欠落を合格扱いにせず、実測 CSV と推定を突き合わせる。"""

import csv
import hashlib
from fractions import Fraction as F
from pathlib import Path

from pptviper import Config, inspect


def compare(
    deck: Path, manifest: dict, csv_path: Path, mode: str = "macro", config=None
) -> dict:
    if hashlib.sha256(deck.read_bytes()).hexdigest() != manifest["deck_sha256"]:
        raise ValueError("デッキの SHA-256 が manifest と一致しません")
    cases = {c["name"]: c for c in manifest["cases"]}
    if len(cases) != len(manifest["cases"]) or len(cases) < 200:
        raise ValueError("較正 manifest は 200 個以上の一意な図形が必要です")
    if mode not in ("macro", "manual"):
        raise ValueError("測定方式が不正です")
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    names = [r["name"] for r in rows]
    if len(names) != len(set(names)) or not set(names) <= cases.keys():
        raise ValueError("重複または不明な図形です")
    if (mode == "macro" and set(names) != cases.keys()) or len(rows) < 50:
        raise ValueError("測定不足です。macro は全件、manual は 50 件以上必要です")
    report = inspect(deck, config=config or Config()).to_dict()
    if report["errors"] or report["unenumerated"]:
        raise ValueError("入力の解析が不完全です")
    layouts = {}
    for record in report["shapes"]:
        for ref in record["shapes"]:
            if ref.get("origin") == "slide":
                layouts[(record["slide"]["number"], str(ref["id"]))] = record[
                    "properties"
                ].get("text_layout", {})
    results = []
    for row in rows:
        case = cases[row["name"]]
        if (
            int(row["slide"]) != case["slide"]
            or int(row["shape_id"]) != case["shape_id"]
        ):
            raise ValueError("図形名とスライド・図形 ID が一致しません")
        actual = [F(row[k]) for k in ("lines", "width_pt", "height_pt")]
        if actual[0].denominator != 1 or actual[0] <= 0 or min(actual[1:]) < 0:
            raise ValueError("測定値が不正です")
        layout = layouts.get((case["slide"], str(case["shape_id"])), {})
        supported = layout.get("supported", False)
        delta = (
            [
                F(layout["lines"]) - actual[0],
                F(layout["width"]) / 12700 - actual[1],
                F(layout["height"]) / 12700 - actual[2],
            ]
            if supported
            else None
        )
        results.append(
            dict(
                name=row["name"],
                slide=case["slide"],
                delta=[str(x) for x in delta] if delta is not None else None,
                passed=delta is not None and min(delta) >= 0,
                unknown=layout.get("unknown", []),
                missing_fonts=layout.get("missing_fonts", []),
            )
        )
    return dict(
        passed=all(r["passed"] for r in results),
        mode=mode,
        deck_sha256=manifest["deck_sha256"],
        measured=len(rows),
        total=len(cases),
        omitted=sorted(cases.keys() - set(names)),
        results=results,
    )
