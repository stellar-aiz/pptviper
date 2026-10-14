"""Static rule dispatch, shared candidate identities, and normalized observations."""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction as F
from itertools import combinations
from typing import Any, cast

from pptviper.geometry import Interval as I
from pptviper.report import Report, number


@dataclass
class Item:
    slide: dict[str, Any]
    ref: dict[str, Any]
    props: dict[str, Any]
    bounds: tuple[I, I, I, I] | None
    ambiguous: bool = False

    @property
    def key(self) -> str:
        return str(self.slide["id"]) + ":" + self.ref["key"]

    @property
    def meta(self) -> dict[str, Any]:
        return self.props.get("semantic", {})

    @property
    def text(self) -> str:
        return self.meta.get("text", "")

    @property
    def kind(self) -> tuple[Any, ...]:
        return (
            self.meta.get("preset"),
            bool(self.text),
            (self.meta.get("placeholder") or {}).get("type"),
        )

    @property
    def peer(self) -> bool:
        return self.ref["kind"] not in ("grpSp", "table-cell")


@dataclass
class Result:
    hit: bool = False
    applicable: bool = True
    unknown: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    value: F | int | None = None
    unit: str = "count"
    confidence: str = "certain"
    threshold: F | int | None = None


def missing(reason: str = "Required saved values are unavailable") -> Result:
    return Result(unknown=[reason])


def na() -> Result:
    return Result(applicable=False)


def exact_bounds(item: Item) -> tuple[F, F, F, F] | None:
    if item.bounds is None or any(v.low != v.high for v in item.bounds):
        return None
    return tuple(v.low for v in item.bounds)  # type: ignore[return-value]


def minimum(values: list[I]) -> I:
    return I(min(v.low for v in values), min(v.high for v in values))


def maximum(values: list[I]) -> I:
    return I(max(v.low for v in values), max(v.high for v in values))


def less(value: I, threshold: F) -> bool | None:
    return True if value.high < threshold else False if value.low >= threshold else None


def positive(value: I) -> bool | None:
    return True if value.low > 0 else False if value.high <= 0 else None


def difference(a: I, b: I) -> I:
    d = a - b
    return I(
        F(0) if d.low <= 0 <= d.high else min(abs(d.low), abs(d.high)),
        max(abs(d.low), abs(d.high)),
    )


def condition(
    states: list[bool | None],
    *,
    details: dict[str, Any] | None = None,
    value: F | int | None = None,
    unit: str = "EMU",
) -> Result:
    return Result(
        hit=any(s is True for s in states),
        unknown=["Numerical enclosure crosses a rule boundary"]
        if None in states
        else [],
        details=details or {},
        value=value,
        unit=unit,
    )


def emit(
    report: Report,
    rule: str,
    items: list[Item],
    result: Result,
    label: str = "",
    slide: dict[str, Any] | None = None,
) -> None:
    items = sorted(items, key=lambda x: x.key)
    key = json.dumps([label, [i.key for i in items]], separators=(",", ":"))
    ref = [{**i.ref, "slide_id": str(i.slide["id"])} for i in items]
    anchor = slide or (items[0].slide if items else None)
    state = (
        "not-applicable"
        if not result.applicable
        else "finding"
        if result.hit
        else "unknown"
        if result.unknown
        else "pass"
    )
    report.state(rule, key, state)
    for reason in result.unknown:
        report.unresolved(reason, rule=rule, locator=key, slide=anchor, shapes=ref)
    if result.hit:
        measured = (
            None
            if result.value is None
            else dict(
                value=number(F(result.value)),
                exact_value=str(result.value),
                unit=result.unit,
            )
        )
        report.finding(
            rule,
            key,
            f"{rule}: "
            + json.dumps(result.details, sort_keys=True, ensure_ascii=False),
            slide=anchor,
            shapes=ref,
            measured=measured,
            threshold=(
                dict(
                    value=number(F(str(limit))),
                    exact_value=str(limit),
                    unit=result.unit,
                )
                if (
                    limit := result.threshold
                    if result.threshold is not None
                    else report.config.thresholds.get(rule)
                )
                is not None
                else None
            ),
            confidence="worst-case"
            if result.unknown
            or any(i.bounds and any(v.low != v.high for v in i.bounds) for i in items)
            else result.confidence,
            details=result.details,
        )


def collect(report: Report) -> list[Item]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report.shapes:
        grouped[str(row["slide"]["id"]) + ":" + row["shapes"][0]["key"]].append(row)
    items = []
    for rows in grouped.values():
        row = rows[0]
        b = row.get("bounds")
        ambiguous = (
            len(rows) > 1
            or any(r.get("branch") is not None for r in rows)
            or any(r.get("branch") is not None for r in rows)
        )
        bounds = (
            None
            if b is None or ambiguous
            else tuple(
                I(F(b[k]["low"]["exact_emu"]), F(b[k]["high"]["exact_emu"]))
                for k in ("left", "top", "right", "bottom")
            )
        )
        items.append(
            Item(
                row["slide"],
                row["shapes"][0],
                row["properties"],
                cast(tuple[I, I, I, I] | None, bounds),
                ambiguous,
            )
        )
    return sorted(items, key=lambda i: i.key)


def runs(items: list[Item], axis: int) -> list[list[Item]]:
    """Greedy disjoint runs; common cross-axis intersection avoids chaining."""
    eligible = [i for i in items if i.peer and exact_bounds(i) is not None]

    def coords(i: Item) -> tuple[F, F, F, F]:
        b = exact_bounds(i)
        assert b is not None
        return b if axis == 0 else (b[1], b[0], b[3], b[2])

    eligible.sort(key=lambda i: (coords(i)[0], coords(i)[1], i.key))
    groups: list[list[Item]] = []
    for item in eligible:
        a, b, c, d = coords(item)
        for group in groups:
            _, _, last, _ = coords(group[-1])
            low = max(coords(member)[1] for member in group)
            high = min(coords(member)[3] for member in group)
            if a >= last and max(b, low) < min(d, high):
                group.append(item)
                break
        else:
            groups.append([item])
    return [g for g in groups if len(g) >= 2]


def evaluate_rules(report: Report, width: int, height: int) -> None:
    from pptviper.geometry_rules import connector, pair_rules, run_rules, unary_rules
    from pptviper.text_rules import deck_rules, role_rules, text_rules

    items = collect(report)
    by_slide: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        by_slide[str(item.slide["id"])].append(item)
        for rule, result in unary_rules(
            item, width, height, report.config.thresholds
        ).items():
            emit(report, rule, [item], result)
        for rule, result in text_rules(item, report.config.thresholds).items():
            emit(report, rule, [item], result)
    roles: dict[tuple[str, ...], tuple[Item, Item]] = {}
    for local in by_slide.values():
        peers = [i for i in local if i.peer]
        for a, b in combinations(peers, 2):
            for rule, result in pair_rules(a, b, report.config.thresholds).items():
                emit(report, rule, [a, b], result)
        for item in local:
            emit(report, "connector-unattached", [item], connector(item, local))
        for axis in (0, 1):
            for group in runs(local, axis):
                for rule, members, result, label in run_rules(group, axis):
                    emit(report, rule, members, result, label)
                for a, b in combinations(group, 2):
                    if a.kind == b.kind:
                        roles[tuple(sorted((a.key, b.key)))] = (a, b)
            for item in peers:
                if exact_bounds(item) is None:
                    for rule in ("uneven-gap", "uneven-size"):
                        emit(
                            report,
                            rule,
                            [item],
                            missing("Run membership needs unambiguous exact bounds"),
                            f"unresolved-axis-{axis}",
                        )
    placeholders: dict[tuple[str, str, str], list[Item]] = defaultdict(list)
    for i in items:
        ph = i.meta.get("placeholder")
        if ph and i.ref["origin"] == "slide" and i.meta.get("layout_part"):
            placeholders[(i.meta["layout_part"], ph["type"], ph["idx"])].append(i)
    for group in placeholders.values():
        for a, b in combinations(group, 2):
            if a.slide["id"] != b.slide["id"]:
                roles[tuple(sorted((a.key, b.key)))] = (a, b)
    for a, b in roles.values():
        for rule, result in role_rules(a, b).items():
            emit(report, rule, [a, b], result)
    deck_rules(report, items)
