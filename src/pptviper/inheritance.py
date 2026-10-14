"""Resolve stored properties while preserving unsupported semantics explicitly."""

from typing import Any
from xml.etree.ElementTree import Element

from pptviper.geometry import A
from pptviper.package import P

NS = {"a": A[1:-1], "p": P[1:-1]}
BODY_DEFAULTS = {
    "lIns": "91440",
    "rIns": "91440",
    "tIns": "45720",
    "bIns": "45720",
    "anchor": "t",
    "wrap": "square",
    "vert": "horz",
}
MASTER_TYPES = {
    "ctrTitle": "title",
    **dict.fromkeys(
        ("subTitle", "obj", "pic", "chart", "clipArt", "dgm", "media", "tbl"), "body"
    ),
}


def ph(shape: Element) -> Element | None:
    return shape.find("./*/p:nvPr/p:ph", NS)


def master_type(shape: Element) -> str:
    node = ph(shape)
    value = node.get("type", "obj") if node is not None else "other"
    return MASTER_TYPES.get(value, value)


def placeholders(root: Element | None) -> list[Element]:
    return (
        []
        if root is None
        else [s for s in root.findall("./p:cSld/p:spTree/*", NS) if ph(s) is not None]
    )


def chain(
    shape: Element, layout: Element | None, master: Element | None
) -> tuple[list[Element], list[str]]:
    result = [shape]
    errors = []
    node = ph(shape)
    if node is None:
        return result, errors
    if layout is not None:
        idx = node.get("idx", "0")
        matches = [s for s in placeholders(layout) if ph(s).get("idx", "0") == idx]  # type: ignore[union-attr]
        if len(matches) == 1:
            result.extend(matches)
        elif len(matches) > 1:
            errors.append("Ambiguous layout placeholder idx")
    if master is not None:
        kind = master_type(result[-1])
        matches = [s for s in placeholders(master) if master_type(s) == kind]
        if len(matches) == 1:
            result.extend(matches)
        elif len(matches) > 1:
            errors.append("Ambiguous master placeholder type")
    return result, errors


def xfrm(shapes: list[Element]) -> Element | None:
    for shape in shapes:
        for path in ("p:spPr/a:xfrm", "p:grpSpPr/a:xfrm", "p:xfrm"):
            found = shape.find(path, NS)
            if found is not None:
                return found
    return None


def structure(node: Element) -> dict[str, Any]:
    return dict(
        tag=node.tag.rsplit("}", 1)[-1],
        attributes=dict(node.attrib),
        children=[structure(c) for c in node],
    )


def theme_maps(theme: Element | None) -> tuple[dict[str, str], dict[str, str]]:
    colors: dict[str, str] = {}
    fonts: dict[str, str] = {}
    if theme is not None:
        for c in theme.findall("./a:themeElements/a:clrScheme/*", NS):
            if len(c):
                value = (
                    c[0].get("val")
                    if c[0].tag == A + "srgbClr"
                    else c[0].get("lastClr")
                )
                if value:
                    colors[c.tag.rsplit("}", 1)[-1]] = value
        for kind, prefix in (("majorFont", "mj"), ("minorFont", "mn")):
            for script, suffix in (("latin", "lt"), ("ea", "ea"), ("cs", "cs")):
                node = theme.find(
                    f"./a:themeElements/a:fontScheme/a:{kind}/a:{script}", NS
                )
                if node is not None:
                    fonts[f"+{prefix}-{suffix}"] = node.get("typeface", "")
    return colors, fonts


def color(
    node: Element, colors: dict[str, str], mapping: dict[str, str], unknown: list[str]
) -> dict[str, Any] | None:
    import colorsys

    kind = node.tag.rsplit("}", 1)[-1]
    value = node.get("val", "")
    if kind == "schemeClr":
        value = colors.get(mapping.get(value, value), "")
    elif kind == "sysClr":
        value = node.get("lastClr", "")
    elif kind != "srgbClr":
        unknown.append(f"Unsupported color representation: {kind}")
        return None
    try:
        if len(value) != 6:
            raise ValueError
        rgb = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        alpha = 1.0
        for item in node:
            tag = item.tag.rsplit("}", 1)[-1]
            v = int(item.attrib["val"]) / 100000
            if tag in ("lumMod", "lumOff"):
                h, lightness, s = colorsys.rgb_to_hls(*rgb)
                lightness = lightness * v if tag == "lumMod" else lightness + v
                rgb = list(colorsys.hls_to_rgb(h, min(1, max(0, lightness)), s))
            elif tag in ("satMod", "satOff", "hueMod", "hueOff"):
                h, lightness, s = colorsys.rgb_to_hls(*rgb)
                if tag == "satMod":
                    s *= v
                elif tag == "satOff":
                    s += v
                elif tag == "hueMod":
                    h *= v
                else:
                    h += int(item.attrib["val"]) / 21600000
                rgb = list(colorsys.hls_to_rgb(h % 1, lightness, min(1, max(0, s))))
            elif tag == "tint":
                rgb = [x + (1 - x) * v for x in rgb]
            elif tag == "shade":
                rgb = [x * v for x in rgb]
            elif tag == "alpha":
                alpha = v
            elif tag == "alphaMod":
                alpha *= v
            elif tag == "alphaOff":
                alpha += v
            else:
                unknown.append(f"Unsupported color transform: {tag}")
        return dict(
            rgb=[round(min(1, max(0, x)) * 255, 6) for x in rgb],
            alpha=round(min(1, max(0, alpha)), 6),
            source=structure(node),
        )
    except (ValueError, KeyError):
        unknown.append("Unresolved or invalid color value")
        return None


def resolve(
    shapes: list[Element],
    master: Element | None,
    presentation: Element,
    theme: Element | None,
    mapping: dict[str, str],
    table_styles: Element | None = None,
) -> tuple[dict[str, Any], list[str]]:
    unknown: list[str] = []
    colors, fonts = theme_maps(theme)
    result: dict[str, Any] = {
        "body": dict(BODY_DEFAULTS),
        "autofit": {"mode": "noAutofit", "source": "schema-default"},
        "paragraphs": [],
        "fill": None,
    }
    for index, shape in reversed(list(enumerate(shapes))):
        body = shape.find("p:txBody/a:bodyPr", NS)
        if body is not None:
            result["body"].update(body.attrib)
            for mode in ("normAutofit", "spAutoFit", "noAutofit"):
                fit = body.find(A + mode)
                if fit is not None:
                    result["autofit"] = {
                        "mode": mode,
                        "fontScale": "100000",
                        "lnSpcReduction": "0",
                        **fit.attrib,
                        "source": f"inheritance[{index}]",
                        "fontScale_defaulted": "fontScale" not in fit.attrib,
                    }
        for fill in shape.findall("./p:spPr/*", NS):
            tag = fill.tag.rsplit("}", 1)[-1]
            if tag in (
                "solidFill",
                "noFill",
                "gradFill",
                "blipFill",
                "pattFill",
                "grpFill",
            ):
                resolved = []
                for c in fill.iter():
                    if c.tag.rsplit("}", 1)[-1] in (
                        "srgbClr",
                        "schemeClr",
                        "sysClr",
                        "prstClr",
                        "scrgbClr",
                        "hslClr",
                    ):
                        resolved.append(color(c, colors, mapping, unknown))
                result["fill"] = {
                    "kind": tag,
                    "colors": resolved,
                    "stored": structure(fill),
                    "source": f"inheritance[{index}]",
                }
                if tag in ("grpFill", "pattFill"):
                    unknown.append(f"Unsupported effective fill: {tag}")
    shape = shapes[0]
    if result["fill"] is None:
        style = shape.find("p:style/a:fillRef", NS)
        if style is not None:
            try:
                index = int(style.get("idx", "0"))
                placeholder = (
                    color(style[0], colors, mapping, unknown) if len(style) else None
                )
                if index == 0:
                    result["fill"] = {"kind": "noFill", "source": "theme-style[0]"}
                else:
                    entries = (
                        theme.findall(
                            "./a:themeElements/a:fmtScheme/a:"
                            + ("bgFillStyleLst" if index >= 1001 else "fillStyleLst")
                            + "/*",
                            NS,
                        )
                        if theme is not None
                        else []
                    )
                    selected = entries[index - 1001 if index >= 1001 else index - 1]
                    local_colors = dict(colors)
                    if placeholder:
                        local_colors["phClr"] = "".join(
                            f"{round(v):02x}" for v in placeholder["rgb"]
                        )
                    resolved = [
                        color(c, local_colors, mapping, unknown)
                        for c in selected.iter()
                        if c.tag in (A + "srgbClr", A + "schemeClr", A + "sysClr")
                    ]
                    result["fill"] = {
                        "kind": selected.tag.rsplit("}", 1)[-1],
                        "colors": resolved,
                        "stored": structure(selected),
                        "source": f"theme-style[{index}]",
                    }
            except (ValueError, IndexError):
                result["fill"] = {"kind": "theme-reference", "stored": structure(style)}
                unknown.append("Theme fill style matrix is unresolved")
    kind = master_type(shape)
    style_name = (
        "titleStyle"
        if kind == "title"
        else "bodyStyle"
        if kind == "body"
        else "otherStyle"
    )
    for paragraph in shape.findall("p:txBody/a:p", NS):
        pp = paragraph.find(A + "pPr")
        try:
            level = int(pp.get("lvl", "0")) if pp is not None else 0
            if not 0 <= level <= 8:
                raise ValueError
        except ValueError:
            unknown.append("Invalid paragraph level")
            level = 0
        sources: list[Element] = []
        default = presentation.find(f"p:defaultTextStyle/a:lvl{level + 1}pPr", NS)
        if default is not None:
            sources.append(default)
        if master is not None:
            mst = master.find(f"p:txStyles/p:{style_name}/a:lvl{level + 1}pPr", NS)
            if mst is not None:
                sources.append(mst)
        for ancestor in reversed(shapes):
            value = ancestor.find(f"p:txBody/a:lstStyle/a:lvl{level + 1}pPr", NS)
            if value is not None:
                sources.append(value)
            if ancestor is not shape:
                for inherited in ancestor.findall("p:txBody/a:p/a:pPr", NS):
                    if inherited.get("lvl", "0") == str(level):
                        sources.append(inherited)
                        break
        if pp is not None:
            sources.append(pp)
        attrs: dict[str, str] = {}
        children: dict[str, Any] = {}
        run_defaults: dict[str, Any] = {}

        def run_values(node: Element) -> dict[str, Any]:
            values: dict[str, Any] = dict(node.attrib)
            for c in node:
                tag = c.tag.rsplit("}", 1)[-1]
                if tag in ("latin", "ea", "cs"):
                    name = c.get("typeface", "")
                    values[tag] = fonts.get(name, name)
                    if (
                        name.startswith("+")
                        and not values[tag]
                        and any(
                            (tag == "latin" and ord(ch) < 0x590)
                            or (tag == "ea" and ord(ch) >= 0x2E80)
                            or (tag == "cs" and 0x590 <= ord(ch) < 0x900)
                            for t in shape.iter(A + "t")
                            for ch in (t.text or "")
                        )
                    ):
                        unknown.append(
                            f"Theme font requires language-specific resolution: {name}"
                        )
                elif tag == "solidFill" and len(c):
                    values["color"] = color(c[0], colors, mapping, unknown)
                else:
                    values[tag] = structure(c)
            return values

        for source in sources:
            attrs.update(source.attrib)
            for child in source:
                if child.tag == A + "defRPr":
                    run_defaults.update(run_values(child))
                else:
                    tag = child.tag.rsplit("}", 1)[-1]
                    for choices in (
                        ("buNone", "buChar", "buAutoNum", "buBlip"),
                        ("buSzPct", "buSzPts", "buSzTx"),
                        ("buFont", "buFontTx"),
                        ("buClr", "buClrTx"),
                    ):
                        if tag in choices:
                            for old in choices:
                                children.pop(old, None)
                    children[tag] = structure(child)
        runs = []
        for run in paragraph:
            if run.tag not in (A + "r", A + "fld", A + "br"):
                continue
            values = dict(run_defaults)
            rp = run.find(A + "rPr")
            if rp is not None:
                values.update(run_values(rp))
            runs.append(
                {
                    "text": run.findtext(A + "t", default=""),
                    "properties": values,
                    "kind": run.tag.rsplit("}", 1)[-1],
                }
            )
        result["paragraphs"].append(
            dict(
                properties=attrs, children=children, default_run=run_defaults, runs=runs
            )
        )
    for table in shape.findall("a:graphic/a:graphicData/a:tbl", NS):
        result.setdefault("tables", []).append(
            resolve_table(table, table_styles, colors, mapping, unknown)
        )
    if result["body"].get("vert") not in ("horz", None):
        unknown.append("Vertical text layout is not evaluated")
    return result, sorted(set(unknown))


def resolve_table(
    table: Element,
    styles: Element | None,
    colors: dict[str, str],
    mapping: dict[str, str],
    unknown: list[str],
) -> dict[str, Any]:
    props = table.find(A + "tblPr")
    style_id = (
        props.findtext(A + "tableStyleId", default="") if props is not None else ""
    )
    if not style_id and styles is not None:
        style_id = styles.get("def", "")
    matches = (
        [] if styles is None else [s for s in styles if s.get("styleId") == style_id]
    )
    style = matches[0] if len(matches) == 1 else None
    # stellar:debt(scope) Missing built-ins; upgrade: add the Office style catalog.
    if style_id and style is None:
        unknown.append("Table style definition is unavailable: " + style_id)
    if style is not None and any(
        style.find(A + name) is not None
        for name in ("nwCell", "neCell", "swCell", "seCell")
    ):
        unknown.append("Table corner style overrides are unresolved")
    rows = table.findall(A + "tr")
    output = []

    def enabled(key: str) -> bool:
        return props is not None and props.get(key, "0") in ("1", "true")

    for ri, row in enumerate(rows):
        cells = row.findall(A + "tc")
        for ci, cell in enumerate(cells):
            sections = ["wholeTbl"]
            if enabled("bandRow"):
                sections.append(
                    "band1H" if (ri - int(enabled("firstRow"))) % 2 == 0 else "band2H"
                )
            if enabled("bandCol"):
                sections.append(
                    "band1V" if (ci - int(enabled("firstCol"))) % 2 == 0 else "band2V"
                )
            if ci == len(cells) - 1 and enabled("lastCol"):
                sections.append("lastCol")
            if ci == 0 and enabled("firstCol"):
                sections.append("firstCol")
            if ri == len(rows) - 1 and enabled("lastRow"):
                sections.append("lastRow")
            if ri == 0 and enabled("firstRow"):
                sections.append("firstRow")
            fill = None
            text = {}
            applied = []
            for section in sections:
                part = style.find(A + section) if style is not None else None
                if part is None:
                    continue
                applied.append(section)
                f = part.find("a:tcStyle/a:fill/a:solidFill", NS)
                if f is not None and len(f):
                    fill = color(f[0], colors, mapping, unknown)
                ts = part.find(A + "tcTxStyle")
                if ts is not None:
                    text.update(ts.attrib)
                    for c in ts:
                        if c.tag in (A + "srgbClr", A + "schemeClr", A + "sysClr"):
                            text["color"] = color(c, colors, mapping, unknown)
                        else:
                            text[c.tag.rsplit("}", 1)[-1]] = structure(c)
            direct = cell.find("a:tcPr/a:solidFill", NS)
            if direct is not None and len(direct):
                fill = color(direct[0], colors, mapping, unknown)
                applied.append("cell")
            tcpr = cell.find(A + "tcPr")
            if (
                cell.get("gridSpan")
                or cell.get("rowSpan")
                or cell.get("hMerge")
                or cell.get("vMerge")
            ):
                unknown.append("Merged table cell geometry is unresolved")
            output.append(
                dict(
                    row=ri,
                    column=ci,
                    fill=fill,
                    text=text,
                    properties=dict(tcpr.attrib) if tcpr is not None else {},
                    sources=applied,
                )
            )
    return dict(style=style_id, cells=output, stored=structure(table))
