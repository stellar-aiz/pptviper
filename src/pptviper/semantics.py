"""Saved semantic metadata needed by static rules, without glyph measurement."""

from fractions import Fraction
from typing import Any
from xml.etree.ElementTree import Element

from pptviper.geometry import A, Interval, Matrix, pair, transform
from pptviper.inheritance import NS, ph, theme_maps, xfrm
from pptviper.package import P


def text(shape: Element) -> str:
    paragraphs = []
    for paragraph in shape.findall("p:txBody/a:p", NS):
        paragraphs.append(
            "".join(
                "\n" if r.tag == A + "br" else r.findtext(A + "t", default="")
                for r in paragraph
            )
        )
    return "\n".join(paragraphs)


def metadata(
    node: Element,
    chain: list[Element],
    parent: Matrix,
    world: Matrix,
    layout: Element | None,
    layout_part: str | None,
    theme: Element | None,
) -> dict[str, Any]:
    placeholder = ph(node)
    preset = node.find("p:spPr/a:prstGeom", NS)
    shape_type = (
        preset.get("prst")
        if preset is not None
        else "custom"
        if node.find("p:spPr/a:custGeom", NS) is not None
        else node.tag.rsplit("}", 1)[-1]
    )
    result: dict[str, Any] = {
        "preset": shape_type,
        "has_text": bool(text(node)),
        "text": text(node),
        "placeholder": dict(placeholder.attrib) if placeholder is not None else None,
        "layout_part": layout_part,
        "inherited_text": [text(s) for s in chain[1:]],
        "theme_fonts": sorted({v for v in theme_maps(theme)[1].values() if v}),
        "local_geometry": xfrm([node]) is not None,
        "layout_bounds": None,
        "connections": {},
        "endpoints": None,
    }
    if placeholder is not None:
        result["placeholder"].setdefault("type", "obj")
        result["placeholder"].setdefault("idx", "0")
        matching = (
            []
            if layout is None
            else [
                s
                for s in layout.findall("p:cSld/p:spTree/*", NS)
                if (sph := ph(s)) is not None
                and sph.get("idx", "0") == placeholder.get("idx", "0")
            ]
        )
        if len(matching) == 1:
            # The chain can include the matching layout and its master fallback.
            inherited = (
                chain[1:] if len(chain) > 1 and chain[1] is matching[0] else matching
            )
            tx = xfrm(inherited)
            if tx is not None:
                try:
                    bounds, _ = transform(tx, parent)
                    result["layout_bounds"] = {
                        name: [str(v.low), str(v.high)]
                        for name, v in zip(
                            ("left", "top", "right", "bottom"),
                            (bounds.left, bounds.top, bounds.right, bounds.bottom),
                            strict=True,
                        )
                    }
                except (ValueError, KeyError, ZeroDivisionError):
                    pass
    if node.tag == P + "cxnSp":
        for end, tag in (("start", "stCxn"), ("end", "endCxn")):
            conn = node.find(f"p:nvCxnSpPr/p:cNvCxnSpPr/a:{tag}", NS)
            result["connections"][end] = dict(conn.attrib) if conn is not None else None
        tx = xfrm([node])
        if tx is not None:
            try:
                w, h = pair(tx, "ext", ("cx", "cy"))
                result["endpoints"] = [
                    [
                        [str(v.low), str(v.high)]
                        for v in world.point(Interval.exact(x), Interval.exact(y))
                    ]
                    for x, y in ((Fraction(0), Fraction(0)), (w, h))
                ]
            except (ValueError, KeyError):
                pass
    columns = []
    for table in node.findall("a:graphic/a:graphicData/a:tbl", NS):
        props = table.find(A + "tblPr")
        columns.append(
            {
                "widths": [
                    c.get("w") for c in table.findall("a:tblGrid/a:gridCol", NS)
                ],
                "first_col": props is not None
                and props.get("firstCol", "0") in ("1", "true"),
            }
        )
    result["tables"] = columns
    return result
