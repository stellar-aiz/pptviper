"""Saved paint metadata and effective slide backgrounds for color rules."""

from copy import deepcopy
from typing import Any
from xml.etree.ElementTree import Element

from pptviper.geometry import A, pair
from pptviper.inheritance import NS, color, resolve, theme_maps, xfrm
from pptviper.package import P, Package, R

FILLS = ("solidFill", "noFill", "gradFill", "pattFill", "blipFill", "grpFill")


def parse_fill(
    node: Element | None, theme: Element | None, mapping: dict[str, str]
) -> dict[str, Any]:
    if node is None:
        return dict(kind="noFill", colors=[], unknown=[])
    colors, _ = theme_maps(theme)
    unknown = []
    values = [
        color(c, colors, mapping, unknown)
        for c in node.iter()
        if c.tag.rsplit("}", 1)[-1]
        in ("srgbClr", "schemeClr", "sysClr", "prstClr", "scrgbClr", "hslClr")
    ]
    values = [v for v in values if v is not None]
    result: dict[str, Any] = dict(
        kind=node.tag.rsplit("}", 1)[-1], colors=values, unknown=unknown
    )
    if node.tag == A + "gradFill":
        stops = []
        for stop in node.findall("a:gsLst/a:gs", NS):
            if len(stop):
                c = color(stop[0], colors, mapping, unknown)
                if c:
                    stops.append(dict(position=stop.get("pos", "0"), color=c))
        linear = node.find(A + "lin")
        result.update(
            stops=stops, angle=linear.get("ang", "0") if linear is not None else None
        )
        if linear is None:
            unknown.append("Path gradient geometry is unresolved")
    return result


def resolved_fill(base: dict[str, Any]) -> dict[str, Any]:
    """Retain resolved phClr colors when traversing a theme gradient matrix."""
    colors = [c for c in base.get("colors", []) if c]
    result: dict[str, Any] = dict(
        kind=base.get("kind", "unknown"), colors=colors, unknown=[]
    )
    if result["kind"] == "gradFill":
        stored = base.get("stored", {})
        children = stored.get("children", [])
        stops = next(
            (c.get("children", []) for c in children if c["tag"] == "gsLst"), []
        )
        linear = next((c for c in children if c["tag"] == "lin"), None)
        result["angle"] = (
            linear.get("attributes", {}).get("ang", "0") if linear else None
        )
        if len(stops) == len(colors):
            result["stops"] = [
                dict(position=s.get("attributes", {}).get("pos", "0"), color=c)
                for s, c in zip(stops, colors, strict=True)
            ]
        else:
            result["unknown"].append("Theme gradient stops are unresolved")
        if linear is None:
            result["unknown"].append("Path gradient geometry is unresolved")
    return result


def visual(
    node: Element,
    shapes: list[Element],
    props: dict[str, Any],
    theme: Element | None,
    mapping: dict[str, str],
    package: Package,
    part: str,
    order: int,
) -> dict[str, Any]:
    source = None
    line = None
    for ancestor in shapes:
        if source is None:
            source = next(
                (
                    ancestor.find("p:spPr/a:" + name, NS)
                    for name in FILLS
                    if ancestor.find("p:spPr/a:" + name, NS) is not None
                ),
                None,
            )
        if line is None:
            line = ancestor.find("p:spPr/a:ln", NS)
    fill = parse_fill(source, theme, mapping)
    if source is None and props.get("fill"):
        fill = resolved_fill(props["fill"])
    if node.tag == P + "pic":
        fill = dict(kind="blipFill", colors=[], unknown=[])
    line_fill = (
        next((line.find(A + n) for n in FILLS if line.find(A + n) is not None), None)
        if line is not None
        else None
    )
    stroke = parse_fill(line_fill, theme, mapping)
    if line is None:
        ref = node.find("p:style/a:lnRef", NS)
        if ref is not None and theme is not None:
            try:
                index = int(ref.get("idx", "0"))
                if index > 0:
                    matrix = theme.findall(
                        "a:themeElements/a:fmtScheme/a:lnStyleLst/a:ln", NS
                    )
                    chosen = deepcopy(matrix[index - 1])
                    if len(ref):
                        for parent in chosen.iter():
                            for child in list(parent):
                                if (
                                    child.tag == A + "schemeClr"
                                    and child.get("val") == "phClr"
                                ):
                                    pos = list(parent).index(child)
                                    parent.remove(child)
                                    parent.insert(pos, deepcopy(ref[0]))
                    line_fill = next(
                        (
                            chosen.find(A + n)
                            for n in FILLS
                            if chosen.find(A + n) is not None
                        ),
                        None,
                    )
                    stroke = parse_fill(line_fill, theme, mapping)
            except (ValueError, IndexError):
                stroke["unknown"].append("Theme line style is unresolved")
    images = []
    for blip in node.findall(".//a:blip", NS):
        rid = blip.get(R + "embed") or blip.get(R + "link")
        relationship = package.relationships(part).get(rid or "")
        header = dict(
            width=None,
            height=None,
            unknown=["Image relationship is unavailable or external"],
        )
        if relationship and relationship[0] == "image" and not relationship[2]:
            header = package.images.get(relationship[1], header)
        parent = node.find("p:blipFill", NS)
        if parent is None:
            parent = node.find("p:spPr/a:blipFill", NS)
        crop = parent.find(A + "srcRect") if parent is not None else None
        tx = xfrm(shapes)
        try:
            size = (
                list(map(str, pair(tx, "ext", ("cx", "cy"))))
                if tx is not None
                else None
            )
        except (ValueError, KeyError):
            size = None
        images.append(
            dict(
                header=header,
                crop=dict(crop.attrib) if crop is not None else {},
                size=size,
            )
        )
    effects = any(
        node.find("p:spPr/a:" + name, NS) is not None
        for name in ("effectLst", "effectDag", "scene3d", "sp3d")
    )
    return dict(fill=fill, line=stroke, images=images, effects=effects, order=order)


def background(
    root: Element,
    layout: Element | None,
    master: Element | None,
    theme: Element | None,
    mapping: dict[str, str],
) -> dict[str, Any]:
    for label, holder in (("slide", root), ("layout", layout), ("master", master)):
        bg = holder.find("p:cSld/p:bg", NS) if holder is not None else None
        if bg is None:
            continue
        direct = bg.find(P + "bgPr")
        if direct is not None:
            node = next(
                (direct.find(A + n) for n in FILLS if direct.find(A + n) is not None),
                None,
            )
            result = parse_fill(node, theme, mapping)
            result.update(
                source=label,
                effects=any(
                    direct.find(A + n) is not None for n in ("effectLst", "effectDag")
                ),
            )
            return result
        ref = bg.find(P + "bgRef")
        if ref is not None:
            fake = root.makeelement(P + "sp", {})
            style = root.makeelement(P + "style", {})
            fillref = deepcopy(ref)
            fillref.tag = A + "fillRef"
            style.append(fillref)
            fake.append(style)
            resolved, unknown = resolve([fake], master, root, theme, mapping)
            fill = resolved.get("fill") or {}
            result = resolved_fill(fill)
            result["unknown"].extend(unknown)
            result.update(source=label, effects=False)
            return result
    return dict(
        kind="solidFill",
        colors=[dict(rgb=[255, 255, 255], alpha=1, source={})],
        unknown=[],
        source="schema-default-white",
        effects=False,
    )
