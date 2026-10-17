"""Piecewise background traversal over saved bounds and paint order."""

from dataclasses import dataclass, field
from fractions import Fraction as F
from math import cos, isfinite, radians, sin
from typing import Any

from pptviper.color_math import composite
from pptviper.rules import Item, exact_bounds

Rect = tuple[F, F, F, F]


@dataclass
class Samples:
    colors: list[dict[str, Any]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    image: bool = False


def intersection(a: Rect, b: Rect) -> Rect | None:
    result = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return result if result[0] < result[2] and result[1] < result[3] else None


def subtract(region: Rect, cover: Rect) -> list[Rect]:
    left, top, right, bottom = region
    x, y, z, w = cover
    return [
        r
        for r in (
            (left, top, right, y),
            (left, w, right, bottom),
            (left, y, x, w),
            (z, y, right, w),
        )
        if r[0] < r[2] and r[1] < r[3]
    ]


def paint_colors(paint: dict[str, Any], region: Rect, bounds: Rect) -> Samples:
    unknown = list(paint.get("unknown", []))
    kind = paint.get("kind", "noFill")
    if paint.get("effects"):
        unknown.append("Background effects are not composited")
    if kind == "blipFill":
        return Samples(
            unknown=unknown + ["Image pixels are not decoded for contrast"], image=True
        )
    if kind == "noFill":
        return Samples(unknown=unknown)
    colors = paint.get("colors", [])
    if kind == "gradFill" and paint.get("stops"):
        try:
            angle = radians(float(paint["angle"]) / 60000)
            if not isfinite(angle):
                raise ValueError("Invalid gradient angle")
            dx, dy = cos(angle), sin(angle)
            width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
            if width <= 0 or height <= 0:
                raise ValueError
            projections = [
                float((x - bounds[0]) / width) * dx
                + float((y - bounds[1]) / height) * dy
                for x, y in (
                    (region[0], region[1]),
                    (region[2], region[1]),
                    (region[0], region[3]),
                    (region[2], region[3]),
                )
            ]
            base = min(0, dx) + min(0, dy)
            span = abs(dx) + abs(dy)
            lo = max(0, min(1, (min(projections) - base) / span))
            hi = max(0, min(1, (max(projections) - base) / span))
            stops = sorted(
                (float(s["position"]) / 100000, s["color"]) for s in paint["stops"]
            )
            if any(not isfinite(pos) or not 0 <= pos <= 1 for pos, _ in stops):
                raise ValueError("Invalid gradient stop")
            positions = sorted({lo, hi, *[pos for pos, _ in stops if lo <= pos <= hi]})
            colors = []
            for position in positions:
                if position <= stops[0][0]:
                    colors.append(stops[0][1])
                    continue
                if position >= stops[-1][0]:
                    colors.append(stops[-1][1])
                    continue
                for (a, c), (b, d) in zip(stops, stops[1:], strict=False):
                    if a <= position <= b:
                        t = (position - a) / (b - a) if b > a else 0
                        colors.append(
                            dict(
                                rgb=[
                                    x * (1 - t) + y * t
                                    for x, y in zip(c["rgb"], d["rgb"], strict=True)
                                ],
                                alpha=c.get("alpha", 1) * (1 - t)
                                + d.get("alpha", 1) * t,
                                source=dict(gradient_position=position),
                            )
                        )
                        break
        except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError):
            unknown.append(
                "Gradient projection is unresolved; all saved stops retained"
            )
    if kind not in ("solidFill", "gradFill", "pattFill", "noFill") or not colors:
        unknown.append("Effective background paint is unresolved")
    return Samples(colors=colors, unknown=unknown)


def behind(
    item: Item,
    local: list[Item],
    background: dict[str, Any],
    slide_size: list[int],
    own: bool = True,
) -> Samples:
    region = exact_bounds(item)
    if region is None or region[0] >= region[2] or region[1] >= region[3]:
        return Samples(unknown=["Contrast target bounds are unavailable"])
    rank = {"master": 0, "layout": 1, "slide": 2}

    def order(i):
        return rank.get(i.ref["origin"], 2), i.props.get("visual", {}).get("order", 0)

    layers = []
    uncertain = []
    if own:
        layers.append(
            (region, item.props.get("visual", {}).get("fill", {}), item.ref["key"])
        )
    for other in sorted(local, key=order, reverse=True):
        if other.key == item.key or order(other) >= order(item) or not other.peer:
            continue
        bounds = exact_bounds(other)
        if bounds is None:
            uncertain.append("Background layer geometry is unresolved")
            continue
        if intersection(region, bounds):
            visual = other.props.get("visual", {})
            layers.append(
                (
                    bounds,
                    {**visual.get("fill", {}), "effects": visual.get("effects", False)},
                    other.ref["key"],
                )
            )
    screen = (F(0), F(0), F(slide_size[0]), F(slide_size[1]))
    layers.append((screen, background, background.get("source", "background")))
    result = Samples(unknown=uncertain)
    budget = [4096]

    def walk(area: Rect, index: int) -> Samples:
        budget[0] -= 1
        if budget[0] < 0 or index >= 512:
            return Samples(unknown=["Background traversal limit reached"])
        if index == len(layers):
            return Samples(unknown=["No opaque background could be resolved"])
        bounds, paint, source = layers[index]
        cover = intersection(area, bounds)
        if cover is None:
            return walk(area, index + 1)
        current = paint_colors(paint, cover, bounds)
        samples = Samples(unknown=list(current.unknown), image=current.image)
        # Images are opaque unknowns for covered regions; never claim their contrast.
        if not current.image:
            if not current.colors:
                samples = walk(cover, index + 1)
                samples.unknown.extend(current.unknown)
            elif all(c.get("alpha", 1) >= 1 for c in current.colors):
                samples.colors = [
                    dict(rgb=c["rgb"], source=source) for c in current.colors
                ]
            else:
                back = walk(cover, index + 1)
                samples.unknown.extend(back.unknown)
                samples.image |= back.image
                for front in current.colors:
                    alpha = front.get("alpha", 1)
                    if alpha >= 1:
                        samples.colors.append(dict(rgb=front["rgb"], source=source))
                    else:
                        for color in back.colors:
                            samples.colors.append(
                                dict(
                                    rgb=composite(front["rgb"], alpha, color["rgb"]),
                                    source=f"{source} over {color['source']}",
                                )
                            )
        for remainder in subtract(area, cover):
            back = walk(remainder, index + 1)
            samples.colors.extend(back.colors)
            samples.unknown.extend(back.unknown)
            samples.image |= back.image
        if len(samples.colors) > 512:
            samples.colors = samples.colors[:512]
            samples.unknown.append("Background color combination limit reached")
        return samples

    measured = walk(region, 0)
    result.colors = measured.colors
    result.image = measured.image
    result.unknown = sorted(set(result.unknown + measured.unknown))
    return result
