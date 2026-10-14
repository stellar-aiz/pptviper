"""Read bounded OPC packages without extraction or external relationship access."""

import zlib
from io import BytesIO
from pathlib import Path, PurePosixPath
from posixpath import dirname, normpath
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import Element, ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import DefusedXMLParser

from pptviper.report import Report

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"


class Package:
    def __init__(self, source: str | Path | bytes, report: Report):
        self.report = report
        self.roots: dict[str, Element] = {}
        self.names: set[str] = set()
        self.failed: set[str] = set()
        self.rels_cache: dict[str, dict[str, tuple[str, str, bool]]] = {}
        self.stopped = False
        total = 0
        try:
            with ZipFile(
                BytesIO(source) if isinstance(source, bytes) else source
            ) as archive:
                entries = archive.infolist()
                if len(entries) > report.config.max_parts:
                    self.failure("package", "ZIP entry count limit exceeded")
                    return
                for entry in entries:
                    name = entry.filename
                    if entry.is_dir():
                        continue
                    if (
                        name in self.names
                        or name.startswith("/")
                        or ".." in PurePosixPath(name).parts
                        or "\\" in name
                    ):
                        self.failure(name, "Duplicate or invalid package part name")
                        continue
                    self.names.add(name)
                    parser = (
                        DefusedXMLParser(
                            forbid_dtd=True, forbid_entities=True, forbid_external=True
                        )
                        if name.endswith((".xml", ".rels"))
                        or name == "[Content_Types].xml"
                        else None
                    )
                    try:
                        with archive.open(entry) as stream:
                            while True:
                                chunk = stream.read(
                                    min(
                                        65536,
                                        report.config.max_expanded_bytes - total + 1,
                                    )
                                )
                                if not chunk:
                                    break
                                total += len(chunk)
                                if total > report.config.max_expanded_bytes:
                                    self.failure(
                                        name, "Expanded ZIP byte limit exceeded"
                                    )
                                    self.stopped = True
                                    return
                                if parser:
                                    parser.feed(chunk)
                        if parser:
                            self.roots[name] = parser.close()
                        report.state("unreadable-part", name, "pass")
                    except (
                        ParseError,
                        DefusedXmlException,
                        BadZipFile,
                        RuntimeError,
                        NotImplementedError,
                        OSError,
                        EOFError,
                        zlib.error,
                    ) as exc:
                        position = getattr(exc, "position", None)
                        self.failure(
                            name,
                            f"{type(exc).__name__}"
                            + (
                                f" at line {position[0]}, column {position[1]}"
                                if position
                                else ""
                            ),
                        )
        except (BadZipFile, OSError, EOFError, ValueError) as exc:
            self.failure("package", f"Cannot open package: {type(exc).__name__}")

    def failure(self, part: str, reason: str) -> None:
        if part in self.failed:
            return
        self.failed.add(part)
        self.report.finding("unreadable-part", part, reason, details={"part": part})
        if part in self.report.candidates["unreadable-part"]:
            self.report.candidates["unreadable-part"][part] = "finding"
        else:
            self.report.state("unreadable-part", part, "finding")
        self.roots.pop(part, None)
        self.report.unenumerated.append(dict(part=part, reason=reason))
        self.report.unresolved(reason, rule="unreadable-part", locator=part)

    def root(self, part: str) -> Element | None:
        result = None if part in self.failed else self.roots.get(part)
        if result is None and not self.stopped:
            self.failure(part, "Missing or unreadable required XML part")
        return result

    def invalid(self, key: str, message: str) -> None:
        if key not in self.report.candidates["invalid-ooxml"]:
            self.report.state("invalid-ooxml", key, "finding")
            self.report.finding("invalid-ooxml", key, message)

    def relationships(self, part: str) -> dict[str, tuple[str, str, bool]]:
        if part in self.rels_cache:
            return self.rels_cache[part]
        path = (
            f"{dirname(part)}/_rels/{PurePosixPath(part).name}.rels"
            if part
            else "_rels/.rels"
        )
        path = path.lstrip("/")
        root = self.root(path)
        result: dict[str, tuple[str, str, bool]] = {}
        self.rels_cache[part] = result
        if root is None:
            return result
        if root.tag != PKG + "Relationships":
            self.invalid(path + ":root", "Invalid relationships root")
            return result
        for i, rel in enumerate(root):
            rid, kind, target = rel.get("Id"), rel.get("Type"), rel.get("Target")
            key = f"{path}:relationship:{i}"
            if not rid or not kind or not target or rid in result:
                self.invalid(
                    key, "Missing or duplicate relationship identity/type/target"
                )
                continue
            external = rel.get("TargetMode") == "External"
            try:
                parsed = urlsplit(target)
            except ValueError:
                self.invalid(key, "Malformed relationship URI")
                continue
            if not external and (
                parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
            ):
                self.invalid(key, "Invalid internal relationship target")
                continue
            resolved = (
                target
                if external
                else normpath(
                    unquote(target).lstrip("/")
                    if target.startswith("/")
                    else f"{dirname(part)}/{unquote(target)}".lstrip("/")
                )
            )
            if not external and (resolved.startswith("../") or "\\" in resolved):
                self.invalid(key, "Relationship escapes package")
                continue
            result[rid] = (kind.rsplit("/", 1)[-1], resolved, external)
            self.report.state("invalid-ooxml", key, "pass")
        return result

    def related(self, part: str, kind: str, required: bool = True) -> str | None:
        matches = [v for v in self.relationships(part).values() if v[0] == kind]
        if len(matches) != 1:
            if required:
                self.failure(
                    part + ":" + kind, "Missing or ambiguous required relationship"
                )
            return None
        _, target, external = matches[0]
        if external:
            if required:
                self.failure(
                    part + ":" + kind, "Required relationship is external; not fetched"
                )
            else:
                self.report.unresolved(
                    "External relationship not fetched", locator=part + ":" + kind
                )
            return None
        return target

    def presentation(self) -> str | None:
        types = self.root("[Content_Types].xml")
        if types is None:
            return None
        if types.tag != CT + "Types":
            self.invalid("[Content_Types].xml:root", "Invalid content-types root")
            return None
        return self.related("", "officeDocument")
