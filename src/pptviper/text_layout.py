"""Best-effort text layout in local EMU coordinates, before global rule dispatch."""

from collections import defaultdict
from fractions import Fraction as F
from math import ceil
from typing import Any

from pptviper.fonts import FontBook
from pptviper.geometry import Bounds, Matrix
from pptviper.geometry import Interval as I
from pptviper.linebreak import Glyph, line_width, wrap
from pptviper.rules import Result, collect, emit, missing, na
from pptviper.text_rules import script


def spacing(node: dict[str, Any] | None, basis: F, default: F) -> F:
    if node is None:
        return default
    children = node.get("children", [])
    if len(children) != 1:
        raise ValueError("Invalid paragraph spacing")
    value = F(children[0]["attributes"]["val"])
    if value < 0:
        raise ValueError("Negative paragraph spacing")
    return value * 127 if children[0]["tag"] == "spcPts" else basis * value / 100000


def layout(
    props: dict[str, Any], width: F, height: F, book: FontBook
) -> dict[str, Any]:
    body = props.get("body", {})
    if body.get("vert", "horz") != "horz":
        return dict(unknown=["Vertical text layout is not evaluated"], supported=False)
    reasons = set(props.get("semantic", {}).get("text_unknown", []))
    missing_fonts = set()
    fonts = set()
    margins = [
        F(body.get(k, v))
        for k, v in (
            ("lIns", "91440"),
            ("rIns", "91440"),
            ("tIns", "45720"),
            ("bIns", "45720"),
        )
    ]
    if any(m < 0 for m in margins):
        reasons.add("Negative text insets require manual layout verification")
    fit = props.get("autofit", {})
    scale = F(fit.get("fontScale", "100000")) / 100000
    reduction = F(fit.get("lnSpcReduction", "0")) / 100000
    if not 0 < scale <= 1 or not 0 <= reduction <= 1:
        raise ValueError("Invalid saved AutoFit parameters")
    if fit.get("mode") == "normAutofit" and fit.get("fontScale_defaulted"):
        reasons.add("Missing normAutofit fontScale: no shrink assumed")
    enabled = body.get("wrap", "square") != "none"
    paragraphs = []
    max_width = F(0)
    total_height = F(0)
    total_lines = 0
    for paragraph in props.get("paragraphs", []):
        pp = paragraph.get("properties", {})
        children = paragraph.get("children", {})
        indent = F(pp.get("marL", "0")) + max(F(0), F(pp.get("indent", "0")))
        tab = F(pp.get("defTabSz", "457200"))
        if tab <= 0:
            raise ValueError("Invalid default tab interval")
        glyphs = []
        default_size = (
            F(paragraph.get("default_run", {}).get("sz", "1800")) / 100 * scale
        )
        default_height = default_size * 12700
        previous = ""
        for run in paragraph.get("runs", []):
            rp = run.get("properties", {})
            points = (
                F(rp.get("sz", paragraph.get("default_run", {}).get("sz", "1800")))
                / 100
                * scale
            )
            if points <= 0:
                raise ValueError("Invalid text size")
            if "sz" not in rp and run.get("text"):
                reasons.add("Unresolved text size: 18 pt estimate requires calibration")
            if run.get("kind") == "br":
                glyphs.append(Glyph("\n", F(0), points * 12700))
                previous = ""
                continue
            text = run.get("text", "")
            if rp.get("cap") in ("all", "small"):
                text = text.upper()
                if rp["cap"] == "small":
                    points *= F(4, 5)
                    reasons.add("Small capitals use the provisional 80% size")
            for char in text:
                if char in "\n\t":
                    advance, line_height, unknown, family = (
                        F(0),
                        points * 12700,
                        [],
                        None,
                    )
                else:
                    advance, line_height, unknown, family = book.measure(
                        char, rp, points, previous
                    )
                reasons.update(unknown)
                if char not in "\n\t":
                    fonts.add(rp.get(script(char), "") or "<unresolved family>")
                if family:
                    missing_fonts.add(family)
                glyphs.append(Glyph(char, advance, line_height))
                previous = char
                default_height = max(default_height, line_height)
        bullet = children.get("buChar")
        if bullet or "buAutoNum" in children or "buBlip" in children:
            bullet_text = (bullet or {}).get("attributes", {}).get("char", "1.")
            rp = paragraph.get("default_run", {})
            bullet_width = F(0)
            for ch in bullet_text:
                advance, _, unknown, family = book.measure(ch, rp, default_size)
                bullet_width += advance
                reasons.update(unknown)
                fonts.add(rp.get(script(ch), "") or "<unresolved family>")
                if family:
                    missing_fonts.add(family)
            indent += bullet_width
            if "buAutoNum" in children or "buBlip" in children:
                reasons.add("Automatic/image bullet width uses a provisional marker")
        available = width - margins[0] - margins[1] - indent
        if available <= 0:
            reasons.add("No positive text width after margins and indentation")
        lines, forced = wrap(glyphs, max(F(1), available), tab, enabled)
        line_widths = [line_width(line, tab) for line in lines]
        line_heights = [
            spacing(
                children.get("lnSpc"),
                max((g.height for g in line), default=default_height),
                max((g.height for g in line), default=default_height),
            )
            * (1 - reduction)
            for line in lines
        ]
        para_height = (
            sum(line_heights, F(0))
            + spacing(children.get("spcBef"), default_height, F(0))
            + spacing(children.get("spcAft"), default_height, F(0))
        )
        counts = [sum(not g.text.isspace() for g in line) for line in lines]
        unwrapped = line_width([g for g in glyphs if g.text != "\n"], tab)
        baseline = max(1, ceil(unwrapped / max(F(1), available)))
        paragraphs.append(
            dict(
                lines=len(lines),
                line_widths=list(map(str, line_widths)),
                line_characters=counts,
                unbreakable=forced,
                excessive=len(lines) >= baseline + 2
                or any(0 < c <= 2 for c in counts[:-1]),
                orphan=len(lines) > 1 and 0 < counts[-1] <= 2,
                height=str(para_height),
            )
        )
        total_lines += len(lines)
        total_height += para_height
        max_width = max(max_width, max(line_widths, default=F(0)) + indent)
    full_width = max_width + margins[0] + margins[1]
    full_height = total_height + margins[2] + margins[3]
    if fit.get("mode") == "spAutoFit":
        reasons.add(
            "spAutoFit uses estimated content height instead of stale saved height"
        )
    if not enabled:
        reasons.add("wrap=none extends effective width without automatic wrapping")
    return dict(
        supported=True,
        width=str(max_width),
        height=str(total_height),
        full_width=str(full_width),
        full_height=str(full_height),
        overflow_width=str(max(F(0), full_width - width)),
        overflow_height=str(max(F(0), full_height - height)),
        lines=total_lines,
        paragraphs=paragraphs,
        missing_fonts=sorted(missing_fonts),
        fonts=sorted(fonts),
        unknown=sorted(reasons),
        expand_width=not enabled,
        expand_height=fit.get("mode") == "spAutoFit",
    )


def transformed(world: Matrix, width: F, height: F) -> Bounds:
    points = [
        world.point(I.exact(x), I.exact(y))
        for x, y in ((F(0), F(0)), (width, F(0)), (F(0), height), (width, height))
    ]
    return Bounds(
        I(min(p[0].low for p in points), min(p[0].high for p in points)),
        I(min(p[1].low for p in points), min(p[1].high for p in points)),
        I(max(p[0].low for p in points), max(p[0].high for p in points)),
        I(max(p[1].low for p in points), max(p[1].high for p in points)),
    )


def union(a: Bounds, b: Bounds) -> Bounds:
    return Bounds(
        I(min(a.left.low, b.left.low), min(a.left.high, b.left.high)),
        I(min(a.top.low, b.top.low), min(a.top.high, b.top.high)),
        I(max(a.right.low, b.right.low), max(a.right.high, b.right.high)),
        I(max(a.bottom.low, b.bottom.low), max(a.bottom.high, b.bottom.high)),
    )


def prepare(groups: dict[str, list[dict[str, Any]]], book: FontBook) -> None:
    """Measure text before off-slide and pair rules consume the effective bounds."""
    for records in groups.values():
        for record in records:
            props = record["properties"]
            if not props.get("semantic", {}).get("text"):
                continue
            dimensions = record.get("local_size")
            if record["bounds"] is None or dimensions is None:
                props["text_layout"] = dict(
                    supported=False, unknown=["Text frame geometry is unresolved"]
                )
                continue
            try:
                width, height = dimensions
                result = layout(props, width, height, book)
                props["text_layout"] = result
                if result["supported"]:
                    grown_width = (
                        max(width, F(result["full_width"]))
                        if result["expand_width"]
                        else width
                    )
                    grown_height = (
                        max(height, F(result["full_height"]))
                        if result["expand_height"]
                        else height
                    )
                    props["bounds_estimated"] = (
                        grown_width != width or grown_height != height
                    )
                    record["bounds"] = union(
                        record["bounds"],
                        transformed(record["world"], grown_width, grown_height),
                    )
                record["unknown"].extend(result["unknown"])
            except (
                ValueError,
                KeyError,
                TypeError,
                ZeroDivisionError,
                OverflowError,
            ) as exc:
                props["text_layout"] = dict(
                    supported=False, unknown=[f"Unsupported saved text metrics: {exc}"]
                )
    table_cells = defaultdict(list)
    for cell_key, values in groups.items():
        if "/cell/" in cell_key:
            table_cells[cell_key.split("/cell/", 1)[0]].extend(values)
    for key, cells in table_cells.items():
        records = groups.get(key, [])
        for record in records:
            rows: dict[int, F] = defaultdict(F)
            unknown = []
            for cell in cells:
                result = cell["properties"].get("text_layout")
                if result and result.get("supported"):
                    row = int(cell["ref"]["key"].split("/")[-2])
                    rows[row] = max(rows[row], F(result["overflow_height"]))
                    unknown.extend(result["unknown"])
                elif result:
                    unknown.extend(result["unknown"])
            growth = sum(rows.values(), F(0))
            props = record["properties"]
            props["table_growth"] = dict(
                height=str(growth), unknown=sorted(set(unknown))
            )
            if growth and record["bounds"] and record.get("local_size"):
                props["bounds_estimated"] = True
                width, height = record["local_size"]
                record["bounds"] = union(
                    record["bounds"],
                    transformed(record["world"], width, height + growth),
                )
                record["unknown"].append("Table row growth estimated from cell content")


def evaluate(report, width: int, height: int) -> None:
    from pptviper.geometry_rules import pair_rules
    from pptviper.rule_catalog import THRESHOLDS

    items = collect(report)
    font_groups = defaultdict(list)
    missing_families = set()
    for item in items:
        result = item.props.get("text_layout")
        cell = item.ref["kind"] == "table-cell"
        names = (
            "text-overflow",
            "table-cell-overflow",
            "unbreakable-word",
            "excessive-wrap",
            "orphan-line",
        )
        for rule in names:
            if (
                rule == "text-overflow"
                and cell
                or rule == "table-cell-overflow"
                and not cell
                or not item.text
                or not report.config.measure_text
            ):
                outcome = na()
            elif item.ambiguous or not result or not result.get("supported"):
                outcome = missing(
                    "Text layout is unavailable or ambiguous"
                    if not result
                    else "; ".join(result.get("unknown", []))
                )
            else:
                reasons = result["unknown"]
                if rule.endswith("overflow"):
                    value = max(
                        F(result["overflow_width"]), F(result["overflow_height"])
                    )
                    hit = value > 0
                    unit = "EMU"
                else:
                    flag = {
                        "unbreakable-word": "unbreakable",
                        "excessive-wrap": "excessive",
                        "orphan-line": "orphan",
                    }[rule]
                    value = sum(p[flag] for p in result["paragraphs"])
                    hit = value > 0
                    unit = "count"
                outcome = Result(
                    hit=hit,
                    value=value,
                    unit=unit,
                    unknown=reasons,
                    confidence="worst-case",
                    details=dict(layout=result),
                    threshold=0,
                )
            emit(report, rule, [item], outcome)
        if result and result.get("supported"):
            for family in result["fonts"]:
                font_groups[family].append(item)
            missing_families.update(result["missing_fonts"])
        growth = item.props.get("table_growth")
        if not item.meta.get("tables") or not report.config.measure_text:
            outcome = na()
        elif item.bounds is None or not growth or item.ambiguous:
            outcome = missing("Table growth geometry is unresolved")
        else:
            left, top, right, bottom = item.bounds
            outside = (
                left.high < 0
                or top.high < 0
                or right.low > width
                or bottom.low > height
            )
            overlaps = [
                other.ref["key"]
                for other in items
                if other.peer
                and other.key != item.key
                and other.slide["id"] == item.slide["id"]
                and pair_rules(item, other, THRESHOLDS)["overlap"].hit
            ]
            outcome = Result(
                hit=outside or bool(overlaps),
                value=F(growth["height"]),
                unit="EMU",
                unknown=growth["unknown"],
                confidence="worst-case",
                details=dict(growth=growth, outside=outside, overlaps=overlaps),
            )
        emit(report, "table-overflow", [item], outcome)
    for family, members in sorted(font_groups.items()):
        emit(
            report,
            "font-missing",
            members,
            Result(
                hit=family in missing_families,
                value=int(family in missing_families),
                confidence="worst-case",
                details=dict(
                    family=family,
                    fallback="1 em per character; not a proven upper bound",
                ),
            ),
            label=family,
        )
