"""PPTX inspection orchestration and the initial three rules."""

from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from pptviper.config import Config
from pptviper.fonts import FontBook
from pptviper.geometry import A, Bounds, Matrix, pair, transform
from pptviper.inheritance import NS, chain, ph, resolve, xfrm
from pptviper.package import P, Package, R
from pptviper.paint import background, visual
from pptviper.report import Report, measurement
from pptviper.semantics import metadata
from pptviper.text_layout import evaluate, prepare

MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
BoundsProvider = Callable[[dict[str, Any], Bounds], tuple[Bounds, list[str]]]
SHAPES = {P + s for s in ("sp", "pic", "cxnSp", "graphicFrame", "grpSp", "contentPart")}
METADATA = {P + s for s in ("nvGrpSpPr", "grpSpPr", "extLst")}


def shape_id(shape: Element) -> str | None:
    node = shape.find("./*/p:cNvPr", NS)
    return node.get("id") if node is not None else None


def inspect(
    source: str | Path | bytes,
    *,
    config: Config | str | Path | None = None,
    bounds_provider: BoundsProvider | None = None,
) -> Report:
    """Inspect saved presentation data and local font metrics without rendering."""
    try:
        settings = (
            config
            if isinstance(config, Config)
            else Config.from_toml(config)
            if config is not None
            else Config()
        )
        settings = deepcopy(settings)
        settings.__post_init__()
    except (ValueError, TypeError, OSError) as exc:
        report = Report()
        report.errors.append(
            dict(
                kind="configuration",
                message=str(exc)
                if not isinstance(exc, OSError)
                else "Cannot read configuration",
            )
        )
        return report
    report = Report(settings)
    book = FontBook(settings.font_paths, settings.system_fonts)
    package = Package(source, report)
    if package.stopped or "package" in package.failed:
        return report
    part = package.presentation()
    if part is None:
        return report
    presentation = package.root(part)
    if presentation is None:
        return report
    if presentation.tag != P + "presentation" and presentation.tag.endswith(
        "}presentation"
    ):
        report.unresolved("Unsupported presentation namespace", locator=part)
        report.unenumerated.append(
            dict(part=part, reason="Unsupported presentation namespace")
        )
        return report
    try:
        size = presentation.find(P + "sldSz")
        if presentation.tag != P + "presentation" or size is None:
            raise ValueError(
                "Missing presentation dimensions or unsupported presentation root"
            )
        width, height = int(size.attrib["cx"]), int(size.attrib["cy"])
        if width <= 0 or height <= 0:
            raise ValueError("Non-positive slide dimensions")
    except (ValueError, KeyError) as exc:
        package.invalid(part + ":dimensions", str(exc))
        report.unresolved("Slide dimensions cannot be resolved", locator=part)
        report.unenumerated.append(
            dict(part=part, reason="Invalid presentation structure")
        )
        return report
    report.state("invalid-ooxml", part + ":dimensions", "pass")
    table_part = package.related(part, "tableStyles", required=False)
    table_styles = package.root(table_part) if table_part else None
    relationships = package.relationships(part)
    ids: set[str] = set()
    for ordinal, entry in enumerate(presentation.findall("p:sldIdLst/p:sldId", NS), 1):
        sid = entry.get("id", "")
        if not sid.isdigit() or sid in ids:
            package.invalid(f"{part}:slide:{ordinal}", "Missing or duplicate slide ID")
            sid = f"malformed-slide-{ordinal}"
        ids.add(sid)
        slide = dict(number=ordinal, id=sid)
        report.slide_contexts[sid] = dict(slide=slide, complete=False)
        rel = relationships.get(entry.get(R + "id", ""))
        if rel is None or rel[0] != "slide" or rel[2]:
            package.failure(
                f"{part}:slide:{sid}",
                "Missing, invalid, or external slide relationship",
            )
            continue
        sp = rel[1]
        root = package.root(sp)
        if root is None:
            continue
        report.slide_contexts[sid]["complete"] = (
            root.find("p:cSld/p:spTree", NS) is not None
        )
        slide["hidden"] = root.get("show", "1") in ("0", "false")
        lp = package.related(sp, "slideLayout")
        layout = package.root(lp) if lp else None
        mp = package.related(lp, "slideMaster") if lp and layout is not None else None
        master = package.root(mp) if mp else None
        tp = package.related(mp, "theme") if mp and master is not None else None
        theme = package.root(tp) if tp else None
        mapping = dict(bg1="lt1", tx1="dk1", bg2="lt2", tx2="dk2")
        for holder, path in (
            (master, "p:clrMap"),
            (layout, "p:clrMapOvr/a:overrideClrMapping"),
            (root, "p:clrMapOvr/a:overrideClrMapping"),
        ):
            node = holder.find(path, NS) if holder is not None else None
            if node is not None:
                mapping.update(node.attrib)
        report.slide_contexts[sid]["background"] = background(
            root, layout, master, theme, mapping
        )
        report.slide_contexts[sid]["size"] = [width, height]
        contexts = [(sp, root, "slide", layout, master)]
        if root.get("showMasterSp", "1") not in ("0", "false"):
            if layout is not None and lp:
                contexts.append((lp, layout, "layout", None, master))
            if (
                master is not None
                and mp
                and (
                    layout is None
                    or layout.get("showMasterSp", "1") not in ("0", "false")
                )
            ):
                contexts.append((mp, master, "master", None, None))
        for source_part, holder, origin, layout_source, master_source in contexts:
            tree = holder.find("p:cSld/p:spTree", NS)
            if tree is None:
                package.failure(source_part + ":spTree", "Missing required shape tree")
                continue
            _inspect_tree(
                tree,
                source_part,
                origin,
                slide,
                layout_source,
                master_source,
                master,
                presentation,
                theme,
                mapping,
                width,
                height,
                package,
                bounds_provider,
                table_styles,
                lp,
                book,
            )
    from pptviper.rules import evaluate_rules

    evaluate(report, width, height)
    evaluate_rules(report, width, height)
    from pptviper.color_rules import evaluate as evaluate_colors

    evaluate_colors(report)
    return report


def _inspect_tree(
    tree: Element,
    part: str,
    origin: str,
    slide: dict[str, Any],
    layout: Element | None,
    inherit_master: Element | None,
    master: Element | None,
    presentation: Element,
    theme: Element | None,
    mapping: dict[str, str],
    width: int,
    height: int,
    package: Package,
    provider: BoundsProvider | None,
    table_styles: Element | None,
    layout_part: str | None,
    book: FontBook,
) -> None:
    report = package.report
    # Alternative branches intentionally may reuse a shape ID. Detect duplicates
    # within each branch context, not across mutually exclusive representations.
    ids = Counter(shape_id(s) for s in tree.iter() if s.tag in SHAPES)
    groups: dict[str, list[dict[str, Any]]] = {}
    stack = [
        (child, Matrix(), str(i), False, "")
        for i, child in reversed(list(enumerate(tree)))
    ]
    order = 0
    while stack:
        order += 1
        node, parent, path, parent_bad, alternative = stack.pop()
        if node.tag == MC + "AlternateContent":
            for b, branch in reversed(list(enumerate(node))):
                for j, child in reversed(list(enumerate(branch))):
                    stack.append(
                        (child, parent, f"{path}/branch{b}/{j}", parent_bad, path)
                    )
            continue
        if node.tag in METADATA:
            if node.tag == P + "extLst":
                report.slide_contexts[str(slide["id"])]["complete"] = False
                report.unresolved(
                    "Uninterpreted shape-tree extension",
                    locator=part + ":" + path,
                    slide=slide,
                )
            continue
        if node.tag not in SHAPES:
            report.slide_contexts[str(slide["id"])]["complete"] = False
            key = part + ":" + path
            report.unresolved(
                "Unsupported shape-tree element: " + node.tag, locator=key, slide=slide
            )
            report.state("off-slide", str(slide["id"]) + ":" + key, "unknown")
            continue
        if origin != "slide" and ph(node) is not None:
            # Master/layout placeholders are templates, not independently rendered
            # shapes. Slide placeholder instances are resolved through this source.
            continue
        sid = shape_id(node)
        invalid_id = not sid or not sid.isdigit() or (ids[sid] > 1 and not alternative)
        identity = path if invalid_id else sid
        if alternative:
            identity = f"alternate:{alternative}:{identity}"
        key = f"{part}#{identity}"
        if invalid_id:
            package.invalid(
                part + ":" + path + ":identity",
                "Missing, duplicate, or invalid shape ID",
            )
        elif part + ":" + path + ":identity" not in report.candidates["invalid-ooxml"]:
            report.state("invalid-ooxml", part + ":" + path + ":identity", "pass")
        cnv = node.find("./*/p:cNvPr", NS)
        ref = dict(
            id=sid,
            name=cnv.get("name", "") if cnv is not None else "",
            kind=node.tag.rsplit("}", 1)[-1],
            origin=origin,
            part=part,
            key=key,
            hidden=cnv is not None and cnv.get("hidden", "0") in ("1", "true"),
        )
        shapes, unknown = chain(node, layout, inherit_master)
        if alternative and invalid_id:
            unknown.append("AlternateContent shape correspondence is unresolved")
        try:
            properties, property_unknown = resolve(
                shapes, master, presentation, theme, mapping, table_styles
            )
        except RecursionError:
            package.failure(
                part + ":" + path + ":properties",
                "Property nesting exceeds parser processing capacity",
            )
            properties, property_unknown = {}, ["Properties could not be enumerated"]
        # Property uncertainty belongs to the affected future rules. It remains
        # observable even though only the initial rule set is implemented here.
        unknown.extend(property_unknown)
        unsupported = (
            node.tag in (P + "contentPart",)
            or node.find(".//a:graphicData", NS) is not None
            and node.find("a:graphic/a:graphicData/a:tbl", NS) is None
        )
        if unsupported:
            unknown.append(
                "Stored outer bounds checked; embedded visual extent is unsupported"
            )
        known_children = {
            P + name
            for name in (
                "nvSpPr",
                "nvPicPr",
                "nvCxnSpPr",
                "nvGraphicFramePr",
                "nvGrpSpPr",
                "spPr",
                "grpSpPr",
                "xfrm",
                "style",
                "txBody",
            )
        } | {A + "graphic"}
        for descendant in node:
            if descendant.tag not in known_children and descendant.tag not in SHAPES:
                unknown.append("Uninterpreted shape element: " + descendant.tag)
        sppr = node.find(P + "spPr")
        known_properties = {
            A + name
            for name in (
                "xfrm",
                "prstGeom",
                "custGeom",
                "solidFill",
                "noFill",
                "gradFill",
                "blipFill",
                "pattFill",
                "grpFill",
                "ln",
                "effectLst",
                "effectDag",
                "scene3d",
                "sp3d",
            )
        }
        if sppr is not None:
            for prop in sppr:
                if prop.tag not in known_properties:
                    unknown.append("Uninterpreted shape property: " + prop.tag)
        for effect in ("effectLst", "effectDag", "scene3d", "sp3d", "custGeom"):
            if node.find(f"p:spPr/a:{effect}", NS) is not None:
                unknown.append(f"Visual extent of {effect} is not evaluated")
        bounds = None
        tx = None
        world = parent
        try:
            tx = xfrm(shapes)
            if parent_bad:
                unknown.append("Ancestor group transform is invalid")
            elif tx is None:
                unknown.append("Geometry is unavailable after inheritance")
            else:
                bounds, world = transform(tx, parent, node.tag == P + "grpSp")
                geometry_key = part + ":" + path + ":geometry"
                if geometry_key not in report.candidates["invalid-ooxml"]:
                    report.state("invalid-ooxml", geometry_key, "pass")
        except (ValueError, KeyError, ZeroDivisionError, OverflowError) as exc:
            package.invalid(part + ":" + path + ":geometry", str(exc))
            unknown.append("Invalid geometry prevents evaluation")
        if node.tag == P + "grpSp":
            for j, child in reversed(list(enumerate(node))):
                stack.append(
                    (child, world, path + "/" + str(j), bounds is None, alternative)
                )
        properties["visual"] = visual(
            node, shapes, properties, theme, mapping, package, part, order
        )
        if (
            world.b.low != 0
            or world.b.high != 0
            or world.c.low != 0
            or world.c.high != 0
            or world.a.low <= 0
            or world.d.low <= 0
        ):
            for paint in ("fill", "line"):
                if properties["visual"][paint].get("kind") == "gradFill":
                    properties["visual"][paint]["angle"] = None
                    properties["visual"][paint]["unknown"].append(
                        "Rotated or reflected gradient projection is unresolved"
                    )
        properties["semantic"] = metadata(
            node, shapes, parent, world, layout, layout_part, theme
        )
        properties["semantic"]["text_unknown"] = [
            reason
            for reason in unknown
            if any(
                token in reason.lower()
                for token in ("font", "paragraph", "placeholder", "properties could")
            )
        ]
        if layout is None or master is None or theme is None:
            properties["semantic"]["text_unknown"].append(
                "Text inheritance sources are incomplete"
            )
        record = dict(
            world=world,
            local_size=pair(tx, "ext", ("cx", "cy"))
            if bounds is not None and tx is not None
            else None,
            ref=ref,
            bounds=bounds,
            unknown=sorted(set(unknown)),
            path=path,
            properties=properties,
            alternative=alternative,
        )
        groups.setdefault(key, []).append(record)
        if node.find("a:graphic/a:graphicData/a:tbl", NS) is not None:
            for cell in _table_cells(
                node,
                ref,
                world,
                bounds is None,
                properties,
                master,
                presentation,
                theme,
                mapping,
                table_styles,
                package,
            ):
                groups.setdefault(cell["ref"]["key"], []).append(cell)
    if report.config.measure_text:
        prepare(groups, book)
    for key, records in groups.items():
        _evaluate(key, records, slide, width, height, report, provider)


def _evaluate(
    key: str,
    records: list[dict[str, Any]],
    slide: dict[str, Any],
    width: int,
    height: int,
    report: Report,
    provider: BoundsProvider | None = None,
) -> None:
    ref = records[0]["ref"]
    threshold = F(report.config.off_slide_threshold_emu)
    worst = None
    worst_value = F(-1)
    unresolved = False
    for record in records:
        bounds = record["bounds"]
        if bounds is not None and provider is not None:
            bounds, extra = provider(
                dict(shape=record["ref"], slide=slide, properties=record["properties"]),
                bounds,
            )
            record["unknown"].extend(extra)
        for reason in record["unknown"]:
            report.unresolved(reason, locator=key, slide=slide, shapes=[ref])
            unresolved = True
        data = dict(
            slide=slide,
            shapes=[ref],
            locator=key,
            properties=record["properties"],
            branch=record["path"] if record["alternative"] else None,
        )
        if bounds is not None:
            overflows = bounds.overflows(width, height)
            data["bounds"] = {
                name: dict(low=measurement(v.low), high=measurement(v.high))
                for name, v in zip(
                    ("left", "top", "right", "bottom"),
                    (bounds.left, bounds.top, bounds.right, bounds.bottom),
                    strict=True,
                )
            }
            uncertain = any(v.low <= threshold < v.high for v in overflows.values())
            if uncertain:
                report.unresolved(
                    "Numerical enclosure crosses the off-slide threshold",
                    locator=key,
                    slide=slide,
                    shapes=[ref],
                )
                unresolved = True
            if any(v.low > threshold for v in overflows.values()):
                value = max(v.midpoint for v in overflows.values())
                if value > worst_value:
                    worst_value = value
                    worst = (bounds, overflows, record)
        else:
            unresolved = True
        report.shapes.append(data)
    state = "unknown" if unresolved else "pass"
    if worst is not None:
        bounds, edges, record = worst
        approximate = any(v.low != v.high for v in edges.values()) or record[
            "properties"
        ].get("bounds_estimated", False)
        report.finding(
            "off-slide",
            key,
            "Shape exceeds slide bounds; bounds use stored geometry "
            "and documented transforms",
            slide=slide,
            shapes=[ref],
            measured=measurement(worst_value),
            threshold=measurement(threshold),
            confidence="worst-case" if approximate else "certain",
            details=dict(
                edges={
                    edge: dict(low=measurement(v.low), high=measurement(v.high))
                    for edge, v in edges.items()
                },
                complete=bounds.right.high < 0
                or bounds.bottom.high < 0
                or bounds.left.low > width
                or bounds.top.low > height,
                branch=record["path"] if record["alternative"] else None,
            ),
        )
        state = "finding"
    report.state("off-slide", str(slide["id"]) + ":" + key, state)


def _table_cells(
    node: Element,
    ref: dict[str, Any],
    world: Matrix,
    parent_bad: bool,
    properties: dict[str, Any],
    master: Element | None,
    presentation: Element,
    theme: Element | None,
    mapping: dict[str, str],
    table_styles: Element | None,
    package: Package,
) -> list[dict[str, Any]]:
    """Expose cells as candidates, using grid/row geometry rather than text metrics."""
    from xml.etree.ElementTree import SubElement

    result = []
    for table_index, table in enumerate(
        node.findall("a:graphic/a:graphicData/a:tbl", NS)
    ):
        columns = table.findall("a:tblGrid/a:gridCol", NS)
        resolved = properties.get("tables", [])
        cell_styles = (
            resolved[table_index]["cells"] if table_index < len(resolved) else []
        )
        y = 0
        for ri, row in enumerate(table.findall(A + "tr")):
            x = 0
            for ci, cell in enumerate(row.findall(A + "tc")):
                key = f"{ref['key']}/cell/{table_index}/{ri}/{ci}"
                cell_ref = {
                    **ref,
                    "id": f"{ref['id']}/cell/{ri}/{ci}",
                    "key": key,
                    "kind": "table-cell",
                }
                unknown = []
                bounds = None
                cell_world = world
                width = height = 0
                try:
                    width = int(columns[ci].attrib["w"])
                    height = int(row.attrib["h"])
                    t = Element(A + "xfrm")
                    SubElement(t, A + "off", x=str(x), y=str(y))
                    SubElement(t, A + "ext", cx=str(width), cy=str(height))
                    if parent_bad:
                        unknown.append("Table frame geometry is unavailable")
                    elif any(
                        cell.get(k)
                        not in (
                            None,
                            "0",
                            "false",
                            "1" if k in ("gridSpan", "rowSpan") else "0",
                        )
                        for k in ("gridSpan", "rowSpan", "hMerge", "vMerge")
                    ):
                        unknown.append("Merged cell geometry is unresolved")
                    else:
                        bounds, cell_world = transform(t, world)
                    x += width
                except (ValueError, KeyError, IndexError):
                    package.invalid(
                        key + ":geometry", "Invalid table grid/row dimensions"
                    )
                    unknown.append("Table cell geometry is unavailable")
                fake = node.makeelement(P + "sp", {})
                body = cell.find(A + "txBody")
                if body is not None:
                    body = deepcopy(body)
                    body.tag = P + "txBody"
                    fake.append(body)
                cell_props, issues = resolve(
                    [fake], master, presentation, theme, mapping, table_styles
                )
                unknown.extend(issues)
                cell_attributes = cell.find(A + "tcPr")
                if cell_attributes is not None:
                    for source, target in (
                        ("marL", "lIns"),
                        ("marR", "rIns"),
                        ("marT", "tIns"),
                        ("marB", "bIns"),
                        ("vert", "vert"),
                        ("anchor", "anchor"),
                    ):
                        if source in cell_attributes.attrib:
                            cell_props["body"][target] = cell_attributes.attrib[source]
                cell_props["semantic"] = metadata(
                    fake, [fake], Matrix(), Matrix(), None, None, theme
                )
                cell_props["table_style"] = next(
                    (s for s in cell_styles if s["row"] == ri and s["column"] == ci), {}
                )
                style = cell_props["table_style"]
                cell_color = style.get("fill")
                cell_props["visual"] = dict(
                    fill=dict(
                        kind="solidFill" if cell_color else "noFill",
                        colors=[cell_color] if cell_color else [],
                        unknown=[],
                    ),
                    line={},
                    images=[],
                    effects=False,
                    order=properties.get("visual", {}).get("order", 0) + 0.5,
                )
                style_text_color = style.get("text", {}).get("color")
                if style_text_color:
                    for saved, effective in zip(
                        fake.findall("p:txBody/a:p", NS),
                        cell_props["paragraphs"],
                        strict=False,
                    ):
                        saved_runs = [
                            r for r in saved if r.tag in (A + "r", A + "br", A + "fld")
                        ]
                        for saved_run, effective_run in zip(
                            saved_runs, effective["runs"], strict=False
                        ):
                            if saved_run.find("a:rPr/a:solidFill", NS) is None:
                                effective_run["properties"]["color"] = style_text_color
                result.append(
                    dict(
                        world=cell_world if bounds is not None else world,
                        local_size=(F(width), F(height))
                        if bounds is not None
                        else None,
                        ref=cell_ref,
                        bounds=bounds,
                        unknown=unknown,
                        path=key,
                        properties=cell_props,
                        alternative="",
                    )
                )
            try:
                y += int(row.attrib["h"])
            except (ValueError, KeyError):
                parent_bad = True
    return result
