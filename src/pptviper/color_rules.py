"""Color/image rule dispatch with explicit unresolved background pixels."""

from collections import defaultdict
from fractions import Fraction as F
from itertools import combinations
from typing import Any

from pptviper.backgrounds import behind
from pptviper.color_math import below, composite, contrast, delta_e_2000, lab
from pptviper.image_headers import image_checks
from pptviper.rules import Item, Result, collect, emit, missing, na
from pptviper.text_rules import size, used_runs

DIRECT = {"srgbClr", "sysClr", "prstClr", "scrgbClr", "hslClr"}


def colors(item: Item) -> list[dict[str, Any]]:
    visual = item.props.get("visual", {})
    values = [
        c for layer in ("fill", "line") for c in visual.get(layer, {}).get("colors", [])
    ]
    values.extend(
        r["properties"]["color"]
        for r in used_runs(item)
        if r.get("properties", {}).get("color")
    )
    return values


def text_contrast(
    item: Item, local: list[Item], context: dict[str, Any], level: str
) -> Result:
    if not item.text:
        return na()
    if item.ambiguous:
        return missing("Alternate text paint is unresolved")
    samples = behind(
        item, local, context.get("background", {}), context.get("size", [0, 0])
    )
    unknown = list(samples.unknown)
    if item.props.get("visual", {}).get("effects"):
        unknown.append("Text shape effects are not composited")
    if samples.image:
        return Result(unknown=unknown or ["Image background pixels are not decoded"])
    candidates = []
    for run in used_runs(item):
        props = run.get("properties", {})
        foreground = props.get("color")
        points = size(item, props)
        if foreground is None or points is None:
            unknown.append("Effective text color or size is unresolved")
            continue
        large = points >= 18 or props.get("b") in ("1", "true") and points >= 14
        threshold = (4.5 if large else 7) if level == "AAA" else (3 if large else 4.5)
        for back in samples.colors:
            actual = composite(
                foreground["rgb"], foreground.get("alpha", 1), back["rgb"]
            )
            ratio = contrast(actual, back["rgb"])
            candidates.append(
                dict(
                    ratio=ratio,
                    threshold=threshold,
                    foreground=actual,
                    background=back["rgb"],
                    source=back["source"],
                )
            )
    if not candidates:
        return Result(unknown=sorted(set(unknown + ["No resolved contrast pair"])))
    if any(below(c["ratio"], c["threshold"]) is None for c in candidates):
        unknown.append("Numerical contrast enclosure crosses the threshold")
    failed = [c for c in candidates if below(c["ratio"], c["threshold"]) is True]
    worst = min(failed or candidates, key=lambda c: c["ratio"] / c["threshold"])
    return Result(
        hit=bool(failed),
        value=F(str(worst["ratio"])),
        unit="ratio",
        threshold=F(str(worst["threshold"])),
        unknown=sorted(set(unknown)),
        details=worst,
        confidence="worst-case",
    )


def nontext_contrast(item: Item, local: list[Item], context: dict[str, Any]) -> Result:
    visual = item.props.get("visual", {})
    if item.ref["kind"] in ("grpSp", "table-cell"):
        return na()
    if visual.get("images") or item.ref["kind"] == "pic":
        return missing("Image pixels cannot identify non-text outlines or icons")
    fills = [] if item.text else visual.get("fill", {}).get("colors", [])
    strokes = visual.get("line", {}).get("colors", [])
    if not fills and not strokes:
        return na()
    samples = behind(
        item,
        local,
        context.get("background", {}),
        context.get("size", [0, 0]),
        own=False,
    )
    if samples.image:
        return Result(
            unknown=samples.unknown or ["Image background pixels are not decoded"]
        )
    pairs = []

    def weakest(colors, background_rgb):
        return min(
            (
                contrast(
                    composite(c["rgb"], c.get("alpha", 1), background_rgb),
                    background_rgb,
                )
                for c in colors
            ),
            default=0,
        )

    for back in samples.colors:
        # Either a distinguishable fill or outline can identify the shape.
        ratio = max(weakest(fills, back["rgb"]), weakest(strokes, back["rgb"]))
        pairs.append(dict(ratio=ratio, background=back["rgb"], source=back["source"]))
    if not pairs:
        return missing("No resolved non-text background")
    worst = min(pairs, key=lambda c: c["ratio"])
    unknown = list(samples.unknown)
    if visual.get("effects"):
        unknown.append("Shape effects are not composited")
    if below(worst["ratio"], 3) is None:
        unknown.append("Numerical contrast enclosure crosses the threshold")
    return Result(
        hit=below(worst["ratio"], 3) is True,
        value=F(str(worst["ratio"])),
        unit="ratio",
        threshold=3,
        unknown=unknown,
        details=worst,
        confidence="worst-case",
    )


def evaluate(report) -> None:
    items = collect(report)
    by_slide = defaultdict(list)
    palette = defaultdict(dict)
    palette_unknown = set()
    for item in items:
        by_slide[str(item.slide["id"])].append(item)
    for item in items:
        context = report.slide_contexts.get(str(item.slide["id"]), {})
        local = by_slide[str(item.slide["id"])]
        emit(
            report,
            "low-contrast",
            [item],
            text_contrast(item, local, context, report.config.contrast_level),
        )
        emit(
            report,
            "low-contrast-non-text",
            [item],
            nontext_contrast(item, local, context),
        )
        values = colors(item)
        paint_unknown = [
            u
            for layer in ("fill", "line")
            for u in item.props.get("visual", {}).get(layer, {}).get("unknown", [])
        ]
        if (
            item.ambiguous
            or paint_unknown
            or any(not r.get("properties", {}).get("color") for r in used_runs(item))
        ):
            palette_unknown.add("Some effective palette colors are unresolved")
        direct = [c for c in values if c.get("source", {}).get("tag") in DIRECT]
        emit(
            report,
            "off-theme-color",
            [item],
            Result(
                hit=bool(direct),
                value=len(direct),
                details=dict(colors=direct),
                unknown=(["Alternate paint is unresolved"] if item.ambiguous else [])
                + paint_unknown,
            ),
        )
        for c in values:
            palette[tuple(c["rgb"])][item.key] = item
        pictures = item.props.get("visual", {}).get("images", [])
        for rule in ("image-distorted", "image-low-resolution", "image-crop-outside"):
            if not pictures:
                emit(report, rule, [item], na())
                continue
            results = [image_checks(meta)[rule] for meta in pictures]
            hits = [r for r in results if r.hit]
            result = hits[0] if hits else results[0]
            result.unknown = sorted({u for r in results for u in r.unknown})
            if item.ambiguous:
                result = missing("Alternate image metadata is unresolved")
            emit(report, rule, [item], result)
    for sid, context in report.slide_contexts.items():
        background = context.get("background", {})
        values = background.get("colors", [])
        direct = [c for c in values if c.get("source", {}).get("tag") in DIRECT]
        emit(
            report,
            "off-theme-color",
            [],
            Result(
                hit=bool(direct),
                value=len(direct),
                details=dict(background_colors=direct),
            ),
            label="background:" + sid,
            slide=context["slide"],
        )
        for c in values:
            palette.setdefault(tuple(c["rgb"]), {})
    known = sorted(palette)
    for a, b in combinations(known, 2):
        delta = delta_e_2000(lab(a), lab(b))
        members = {**palette[a], **palette[b]}
        emit(
            report,
            "near-duplicate-color",
            list(members.values()),
            Result(
                hit=0 < delta < 3,
                value=F(str(delta)),
                unit="delta-E-2000",
                threshold=3,
                details=dict(colors=[a, b]),
            ),
            label=str((a, b)),
        )
    uncertain = (
        ["Incomplete input prevents complete palette enumeration"]
        if report.unenumerated
        or any(not c.get("complete") for c in report.slide_contexts.values())
        else []
    )
    uncertain.extend(sorted(palette_unknown))
    if palette_unknown:
        emit(
            report,
            "near-duplicate-color",
            [],
            missing("Incomplete palette prevents complete color-pair enumeration"),
            label="unresolved-palette",
        )
    emit(
        report,
        "color-count",
        items,
        Result(
            hit=len(known) > 14,
            value=len(known),
            threshold=14,
            unknown=uncertain,
            details=dict(colors=known),
        ),
        label="deck",
    )
