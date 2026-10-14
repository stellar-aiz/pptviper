"""Text, role, and deck predicates using saved values only."""

import json
import re
import unicodedata
from collections import defaultdict
from fractions import Fraction as F
from typing import Any

from pptviper.report import Report
from pptviper.rules import (
    Item,
    Result,
    condition,
    difference,
    emit,
    missing,
    na,
    positive,
)


def script(ch: str) -> str:
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return "ea"
    if 0x590 <= ord(ch) < 0x1100 or unicodedata.bidirectional(ch) in ("AL", "R"):
        return "cs"
    return "latin"


def used_runs(i: Item) -> list[dict[str, Any]]:
    return [
        r
        for p in i.props.get("paragraphs", [])
        for r in p.get("runs", [])
        if r.get("text")
    ]


def size(i: Item, props: dict[str, Any]) -> F | None:
    try:
        value = F(props["sz"]) / 100
        scale = F(i.props.get("autofit", {}).get("fontScale", "100000")) / 100000
        if value <= 0 or scale <= 0 or scale > 1:
            return None
        return value * scale
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return None


def hygiene(text: str) -> list[str]:
    reasons = []
    if re.search(r"[ \u3000]{2,}", text):
        reasons.append("repeated spaces")
    if any(p != p.strip() for p in text.split("\n")):
        reasons.append("paragraph boundary whitespace")
    if re.search(r"[0-9A-Za-z]", text) and re.search(r"[０-９Ａ-Ｚａ-ｚ]", text):
        reasons.append("mixed full/half-width Latin letters or digits")
    for opening, closing in (
        ("(", ")"),
        ("（", "）"),
        ("「", "」"),
        ("『", "』"),
        ("[", "]"),
        ("【", "】"),
    ):
        if text.count(opening) != text.count(closing):
            reasons.append(f"unbalanced {opening}{closing} counts")
    return reasons


def text_rules(i: Item, thresholds: dict[str, Any]) -> dict[str, Result]:
    names = (
        "autofit-shrunk",
        "font-too-small",
        "east-asian-font-unset",
        "empty-paragraph-spacing",
        "manual-line-break",
        "empty-placeholder",
        "text-hygiene",
        "table-column-uneven",
    )
    if i.ambiguous:
        return dict.fromkeys(
            names, missing("AlternateContent text/structure is ambiguous")
        )
    result = {name: na() for name in names}
    fit = i.props.get("autofit", {})
    if i.props.get("paragraphs"):
        try:
            scale = F(fit.get("fontScale", "100000"))
            reduction = F(fit.get("lnSpcReduction", "0"))
            if scale <= 0 or scale > 100000 or reduction < 0 or reduction > 100000:
                raise ValueError
            result["autofit-shrunk"] = Result(
                hit=fit.get("mode") == "normAutofit"
                and (scale < 100000 or reduction > 0),
                value=scale / 100000,
                unit="ratio",
                details={"fontScale": str(scale), "lnSpcReduction": str(reduction)},
            )
        except (ValueError, TypeError, ZeroDivisionError):
            result["autofit-shrunk"] = missing("Invalid saved AutoFit parameters")
    if i.text:
        runs = used_runs(i)
        sizes = [size(i, r.get("properties", {})) for r in runs]
        note = i.ref["kind"] == "table-cell" or (i.meta.get("placeholder") or {}).get(
            "type"
        ) in ("ftr", "dt", "sldNum")
        limit = F(str(thresholds["font-too-small-note" if note else "font-too-small"]))
        known = [s for s in sizes if s is not None]
        result["font-too-small"] = Result(
            hit=any(s < limit for s in known),
            value=min(known) if known else None,
            unit="pt",
            threshold=F(str(limit)),
            details={"sizes_pt": list(map(str, known)), "threshold_pt": str(limit)},
            unknown=["Effective font size is unresolved"]
            if not sizes or None in sizes
            else [],
        )
        ea_runs = [r for r in runs if any(script(ch) == "ea" for ch in r["text"])]
        result["east-asian-font-unset"] = Result(
            hit=any(not r.get("properties", {}).get("ea") for r in ea_runs),
            applicable=bool(ea_runs),
            value=sum(not r.get("properties", {}).get("ea") for r in ea_runs),
            details={
                "missing_ea_runs": sum(
                    not r.get("properties", {}).get("ea") for r in ea_runs
                )
            },
        )
        paragraphs = i.props.get("paragraphs", [])
        strings = [
            "".join(r.get("text", "") for r in p.get("runs", [])) for p in paragraphs
        ]
        result["empty-paragraph-spacing"] = Result(
            hit=bool(strings) and any(not s for s in strings) and any(strings),
            value=sum(not s for s in strings),
            details={"empty_paragraphs": sum(not s for s in strings)},
        )
        breaks = sum(
            r.get("kind") == "br" for p in paragraphs for r in p.get("runs", [])
        )
        result["manual-line-break"] = Result(
            hit=breaks > 0, value=breaks, details={"breaks": breaks}
        )
        reasons = hygiene(i.text)
        result["text-hygiene"] = Result(
            hit=bool(reasons), value=len(reasons), details={"reasons": reasons}
        )
    if i.meta.get("placeholder") and (i.ref["kind"] == "sp" or i.text):
        empty = not i.text or i.text in i.meta.get("inherited_text", [])
        result["empty-placeholder"] = Result(
            hit=empty, value=int(empty), details={"empty_or_template_text": empty}
        )
    tables = i.meta.get("tables", [])
    if tables:
        diffs = []
        issues = []
        for table in tables:
            try:
                widths = [int(w) for w in table["widths"]]
                if any(w < 0 for w in widths):
                    raise ValueError
                widths = widths[1:] if table["first_col"] else widths
                if len(widths) >= 2:
                    diffs.append(max(widths) - min(widths))
            except (ValueError, TypeError):
                issues.append("Table column widths are invalid")
        result["table-column-uneven"] = Result(
            hit=any(d > 0 for d in diffs),
            applicable=bool(diffs or issues),
            unknown=issues,
            value=max(diffs, default=0),
            unit="EMU",
            details={"width_differences": diffs},
        )
    for name in ("autofit-shrunk", "font-too-small", "east-asian-font-unset"):
        if result[name].applicable:
            result[name].unknown.extend(i.meta.get("text_unknown", []))
    return result


def spacing(children: dict[str, Any], key: str) -> tuple[str, str]:
    node = children.get(key)
    if node is None:
        return ("spcPct", "100000") if key == "lnSpc" else ("zero", "0")
    values = node.get("children", [])
    if len(values) != 1 or values[0].get("tag") not in ("spcPct", "spcPts"):
        raise ValueError("Unsupported spacing")
    child = values[0]
    value = F(child["attributes"]["val"])
    if value < 0:
        raise ValueError("Negative spacing")
    return ("zero", "0") if value == 0 else (child["tag"], str(value))


def signatures(i: Item, rule: str) -> tuple[dict[str, set[str]], bool]:
    values: dict[str, set[str]] = defaultdict(set)
    unknown = False
    for p in i.props.get("paragraphs", []):
        if not any(r.get("text") for r in p.get("runs", [])):
            continue
        level = p.get("properties", {}).get("lvl", "0")
        if rule == "font-size-inconsistent":
            for r in p.get("runs", []):
                if not r.get("text"):
                    continue
                font_size = size(i, r.get("properties", {}))
                if font_size is None:
                    unknown = True
                else:
                    values[level].add(str(font_size))
        else:
            props = p.get("properties", {})
            children = p.get("children", {})
            if rule == "line-spacing-inconsistent":
                try:
                    value: dict[str, Any] = {
                        k: spacing(children, k) for k in ("lnSpc", "spcBef", "spcAft")
                    }
                    value["reduction"] = str(
                        F(i.props.get("autofit", {}).get("lnSpcReduction", "0"))
                    )
                except (ValueError, KeyError, TypeError, ZeroDivisionError):
                    unknown = True
                    continue
            else:
                value = {
                    k: v
                    for k, v in children.items()
                    if k.startswith("bu") and k != "buNone"
                }
                # No bullet and explicit buNone have the same effective signature.
                if "buNone" in children or not any(
                    k in children for k in ("buChar", "buAutoNum", "buBlip")
                ):
                    value = {}
                for default in ("buFontTx", "buClrTx", "buSzTx"):
                    value.pop(default, None)
                if (
                    value.get("buSzPct", {}).get("attributes", {}).get("val")
                    == "100000"
                ):
                    value.pop("buSzPct")
                try:
                    value.update(
                        {k: str(F(props.get(k, "0"))) for k in ("marL", "indent")}
                    )
                except (ValueError, TypeError, ZeroDivisionError):
                    unknown = True
                    continue
            values[level].add(json.dumps(value, sort_keys=True))
    return values, unknown or bool(i.meta.get("text_unknown"))


def role_rules(a: Item, b: Item) -> dict[str, Result]:
    result = {}
    cross = a.slide["id"] != b.slide["id"]
    if cross:
        if a.bounds is None or b.bounds is None:
            result["position-drift"] = missing("Role geometry is unavailable")
        else:
            diffs = [difference(x, y) for x, y in zip(a.bounds, b.bounds, strict=True)]
            result["position-drift"] = condition(
                [positive(d) for d in diffs],
                value=max(d.midpoint for d in diffs),
                details={"differences_emu": list(str(d.midpoint) for d in diffs)},
            )
    else:
        result["position-drift"] = na()
    for rule in (
        "font-size-inconsistent",
        "line-spacing-inconsistent",
        "bullet-inconsistent",
    ):
        if a.ambiguous or b.ambiguous:
            result[rule] = missing("Role properties have ambiguous alternatives")
        elif not a.text or not b.text:
            result[rule] = na()
        else:
            av, au = signatures(a, rule)
            bv, bu = signatures(b, rule)
            levels = sorted(av.keys() & bv.keys())
            different = [level for level in levels if av[level] != bv[level]]
            result[rule] = Result(
                hit=bool(different),
                applicable=bool(levels or au or bu),
                unknown=["Role property is unresolved"] if au or bu else [],
                value=len(different),
                details={
                    "levels": different,
                    "left": {k: sorted(v) for k, v in av.items()},
                    "right": {k: sorted(v) for k, v in bv.items()},
                },
            )
    return result


def deck_rules(report: Report, items: list[Item]) -> None:
    by_slide: dict[str, list[Item]] = defaultdict(list)
    title_groups: dict[str, list[Item]] = defaultdict(list)
    for i in items:
        by_slide[str(i.slide["id"])].append(i)
    contexts = report.slide_contexts or {
        key: dict(slide=members[0].slide, complete=True)
        for key, members in by_slide.items()
    }
    for sid, context in contexts.items():
        titles = [
            i
            for i in by_slide[sid]
            if (i.meta.get("placeholder") or {}).get("type") in ("title", "ctrTitle")
        ]
        ambiguous = any(i.ambiguous for i in by_slide[sid]) or not context["complete"]
        valid = [i for i in titles if i.text.strip() and not i.ambiguous]
        result = Result(
            hit=not valid and not ambiguous,
            unknown=["Title presence is unresolved"] if ambiguous else [],
            value=len(valid),
            details={"nonempty_titles": len(valid)},
        )
        emit(
            report,
            "title-missing",
            titles,
            result,
            label="slide:" + sid,
            slide=context["slide"],
        )
        for i in valid:
            title_groups[i.text.strip()].append(i)
    for i in items:
        if i.ambiguous:
            emit(
                report,
                "title-duplicate",
                [i],
                missing("Title grouping depends on AlternateContent"),
                label="unresolved-title-group",
            )
    if any(not context["complete"] for context in contexts.values()):
        emit(
            report,
            "title-duplicate",
            [],
            missing("Incomplete slide content prevents title grouping"),
            label="unresolved-title-enumeration",
        )
    for members in title_groups.values():
        # Multiple title shapes on the same slide do not constitute duplicate slides.
        unique = {str(i.slide["id"]): i for i in members}
        members = list(unique.values())
        emit(
            report,
            "title-duplicate",
            members,
            Result(
                hit=len(members) > 1,
                value=len(members),
                details={"title": members[0].text.strip(), "slides": sorted(unique)},
            ),
            label="title-group",
        )
    fonts: set[str] = set()
    theme: set[str] = set()
    unresolved = []
    text_items = []
    for i in items:
        theme.update(i.meta.get("theme_fonts", []))
        if not i.text:
            continue
        text_items.append(i)
        unresolved.extend(i.meta.get("text_unknown", []))
        unresolved.extend(i.meta.get("text_unknown", []))
        if i.ambiguous:
            unresolved.append("Font usage depends on AlternateContent")
            continue
        for run in used_runs(i):
            for script_name in {script(ch) for ch in run["text"] if not ch.isspace()}:
                font = run.get("properties", {}).get(script_name)
                if font and not font.startswith("+"):
                    fonts.add(font)
                else:
                    unresolved.append("Used font family is unresolved")
    limit = report.config.thresholds["font-family-count"]
    if limit is None:
        limit = len(theme) + 1
        if text_items and not theme:
            unresolved.append("Theme font count is unresolved")
    if report.unenumerated or any(not c["complete"] for c in contexts.values()):
        unresolved.append("Unreadable input prevents complete deck font enumeration")
    emit(
        report,
        "font-family-count",
        text_items,
        Result(
            hit=len(fonts) > limit,
            unknown=sorted(set(unresolved)),
            value=len(fonts),
            threshold=F(str(limit)),
            details={"fonts": sorted(fonts), "threshold": limit},
        ),
        label="deck",
    )
