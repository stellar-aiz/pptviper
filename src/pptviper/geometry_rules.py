"""Geometric predicates over the common effective bounds."""

from collections import defaultdict
from fractions import Fraction as F
from typing import Any

from pptviper.geometry import Interval as I
from pptviper.rules import (
    Item,
    Result,
    condition,
    difference,
    exact_bounds,
    less,
    maximum,
    minimum,
    missing,
    na,
    positive,
)


def unary_rules(
    i: Item, width: int, height: int, thresholds: dict[str, Any]
) -> dict[str, Result]:
    rules = {
        r: missing()
        for r in ("edge-margin", "zero-size", "tiny-shape", "layout-override")
    }
    rules["hidden-shape"] = Result(
        hit=i.ref.get("hidden", False), value=1, details={"hidden": True}
    )
    if i.ambiguous:
        return {
            r: missing("AlternateContent alternatives are ambiguous for this rule")
            for r in rules
        }
    if i.bounds:
        left, t, r, b = i.bounds
        w, h = r - left, b - t
        margins = [left, t, I.exact(width) - r, I.exact(height) - b]
        rules["edge-margin"] = condition(
            [less(x, F(str(thresholds["edge-margin"]))) for x in margins],
            details={
                "edges": {
                    name: str(x.midpoint)
                    for name, x in zip(
                        ("left", "top", "right", "bottom"), margins, strict=True
                    )
                }
            },
            value=min(x.midpoint for x in margins),
        )
        if i.ref["kind"] == "cxnSp" or i.meta.get("preset") == "line":
            rules["zero-size"] = na()
        else:
            states = [
                True if x.low == x.high == 0 else False if x.low > 0 else None
                for x in (w, h)
            ]
            rules["zero-size"] = condition(
                states,
                details={"width": str(w.midpoint), "height": str(h.midpoint)},
                value=min(w.midpoint, h.midpoint),
            )
        states = [less(x, F(str(thresholds["tiny-shape"]))) for x in (w, h)]
        both = False if False in states else None if None in states else True
        rules["tiny-shape"] = condition(
            [both],
            details={"width": str(w.midpoint), "height": str(h.midpoint)},
            value=max(w.midpoint, h.midpoint),
        )
    if not i.meta.get("placeholder") or not i.meta.get("local_geometry"):
        rules["layout-override"] = na()
    elif i.bounds and i.meta.get("layout_bounds"):
        layout = [
            I(F(i.meta["layout_bounds"][k][0]), F(i.meta["layout_bounds"][k][1]))
            for k in ("left", "top", "right", "bottom")
        ]
        diffs = [difference(a, b) for a, b in zip(i.bounds, layout, strict=True)]
        rules["layout-override"] = condition(
            [positive(x) for x in diffs],
            details={"differences": [str(x.midpoint) for x in diffs]},
            value=max(x.midpoint for x in diffs),
        )
    return rules


def pair_rules(a: Item, b: Item, thresholds: dict[str, Any]) -> dict[str, Result]:
    names = ("overlap", "too-close", "misaligned")
    if a.bounds is None or b.bounds is None:
        return dict.fromkeys(
            names, missing("Pair geometry is unavailable or branch-dependent")
        )
    al, at, ar, ab = a.bounds
    bl, bt, br, bb = b.bounds
    ox = minimum([ar, br]) - maximum([al, bl])
    oy = minimum([ab, bb]) - maximum([at, bt])
    sx, sy = positive(ox), positive(oy)
    overlap = False if False in (sx, sy) else None if None in (sx, sy) else True
    typ = (
        "text/text"
        if a.text and b.text
        else "text/shape"
        if a.text or b.text
        else "shape/shape"
    )
    contained = (
        al.high <= bl.low
        and at.high <= bt.low
        and ar.low >= br.high
        and ab.low >= bb.high
    ) or (
        bl.high <= al.low
        and bt.high <= at.low
        and br.low >= ar.high
        and bb.low >= ab.high
    )
    result = {
        "overlap": condition(
            [overlap],
            details={"kind": typ, "containment": contained},
            value=max(F(0), ox.midpoint) * max(F(0), oy.midpoint),
            unit="EMU²",
        )
    }
    close = []
    gaps = []
    for axis_gap, cross in ((-ox, oy), (-oy, ox)):
        if axis_gap.high < 0 or cross.high <= 0:
            close.append(False)
        elif axis_gap.low < 0 or cross.low <= 0:
            close.append(None)
        else:
            close.append(less(axis_gap, F(str(thresholds["too-close"]))))
            gaps.append(axis_gap.midpoint)
    result["too-close"] = condition(
        close, details={"gaps": list(map(str, gaps))}, value=min(gaps) if gaps else 0
    )
    halves = I.exact(F(1, 2))
    av = [al, ar, at, ab, (al + ar) * halves, (at + ab) * halves]
    bv = [bl, br, bt, bb, (bl + br) * halves, (bt + bb) * halves]
    limit = F(str(thresholds["misaligned"]))
    diffs = [difference(x, y) for x, y in zip(av, bv, strict=True)]
    states = [
        True
        if d.low > 0 and d.high <= limit
        else False
        if d.high == 0 or d.low > limit
        else None
        for d in diffs
    ]
    axes = {
        name: str(d.midpoint)
        for name, d, s in zip(
            ("left", "right", "top", "bottom", "center-x", "center-y"),
            diffs,
            states,
            strict=True,
        )
        if s is True
    }
    result["misaligned"] = condition(
        states,
        details={"axes": axes},
        value=max(
            (d.midpoint for d, s in zip(diffs, states, strict=True) if s is True),
            default=F(0),
        ),
    )
    return result


def run_rules(
    group: list[Item], axis: int
) -> list[tuple[str, list[Item], Result, str]]:
    out = []
    boxes = [exact_bounds(i) for i in group]
    assert all(b is not None for b in boxes)
    gaps = [boxes[j + 1][axis] - boxes[j][axis + 2] for j in range(len(boxes) - 1)]  # type: ignore[index]
    label = f"axis-{axis}"
    if len(group) >= 3:
        lo, hi = min(gaps), max(gaps)
        out.append(
            (
                "uneven-gap",
                group,
                Result(
                    hit=lo != hi,
                    value=hi - lo,
                    unit="EMU",
                    details={"minimum_gap": str(lo), "maximum_gap": str(hi)},
                ),
                label,
            )
        )
    else:
        out.append(("uneven-gap", group, na(), label))
    kinds: dict[tuple[Any, ...], list[Item]] = defaultdict(list)
    for i in group:
        kinds[i.kind].append(i)
    for kind, members in kinds.items():
        if kind[0] is None:
            out.append(
                ("uneven-size", members, missing("Shape kind is unavailable"), label)
            )
            continue
        if len(members) < 2:
            out.append(("uneven-size", members, na(), label))
            continue
        sizes = []
        for i in members:
            b = exact_bounds(i)
            assert b is not None
            sizes.append(b[axis + 2] - b[axis])
        out.append(
            (
                "uneven-size",
                members,
                Result(
                    hit=min(sizes) != max(sizes),
                    value=max(sizes) - min(sizes),
                    unit="EMU",
                    details={"sizes": list(map(str, sizes))},
                ),
                label,
            )
        )
    return out


def connector(i: Item, local: list[Item]) -> Result:
    if i.ref["kind"] != "cxnSp":
        return na()
    if i.ambiguous:
        return missing("Connector alternatives are ambiguous")
    result = Result(details={"endpoints": {}}, value=0, unit="EMU")
    conns = i.meta.get("connections", {})
    endpoints = i.meta.get("endpoints")
    distances = []
    for index, end in enumerate(("start", "end")):
        conn = conns.get(end)
        if conn is None:
            result.hit = True
            result.details["endpoints"][end] = "missing connection reference"
            continue
        targets = [
            t
            for t in local
            if t.ref["part"] == i.ref["part"] and t.ref["id"] == conn.get("id")
        ]
        if len(targets) != 1 or not endpoints or i.bounds is None:
            result.unknown.append(f"{end}: target or endpoint is unavailable")
            continue
        target = exact_bounds(targets[0])
        if target is None:
            result.unknown.append(f"{end}: target bounds are uncertain")
            continue
        left, t, r, b = target
        pts = [
            ((left + r) / 2, t),
            (r, (t + b) / 2),
            ((left + r) / 2, b),
            (left, (t + b) / 2),
        ]
        ep = [I(F(v[0]), F(v[1])) for v in endpoints[index]]
        result.unknown.append(
            f"{end}: nearest AABB midpoint is a proxy; "
            f"saved site {conn.get('idx')} is not resolved"
        )
        if any(v.low != v.high for v in ep):
            continue
        distance = min(max(abs(ep[0].low - x), abs(ep[1].low - y)) for x, y in pts)
        distances.append(distance)
        result.hit |= distance > 0
        result.details["endpoints"][end] = {
            "proxy_distance_emu": str(distance),
            "site": conn.get("idx"),
        }
    result.value = max(distances, default=F(0))
    return result
