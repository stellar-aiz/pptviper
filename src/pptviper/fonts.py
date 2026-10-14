"""Local font discovery and saved OpenType metrics; never render glyphs."""

import os
import sys
from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from fontTools.ttLib import TTCollection, TTFont


def system_paths() -> list[Path]:
    if sys.platform == "win32":
        return [
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts",
        ]
    if sys.platform == "darwin":
        return [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    return [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
    ]


@dataclass(frozen=True)
class Face:
    path: str
    index: int
    names: frozenset[str]
    bold: bool
    italic: bool


@lru_cache(maxsize=16)
def discover(paths: tuple[str, ...], system: bool) -> tuple[Face, ...]:
    roots = [Path(p).expanduser() for p in paths] + (system_paths() if system else [])
    files = set()
    for root in roots:
        if root.is_file():
            files.add(root)
        elif root.is_dir():
            files.update(
                p
                for p in root.rglob("*")
                if p.suffix.lower() in (".ttf", ".otf", ".ttc", ".otc")
            )
    faces = []
    for path in sorted(files):
        collection = None
        fonts = []
        try:
            if path.suffix.lower() in (".ttc", ".otc"):
                collection = TTCollection(path, lazy=True)
                fonts = collection.fonts
            else:
                fonts = [TTFont(path, lazy=True)]
            for index, font in enumerate(fonts):
                names = set()
                for record in font["name"].names:
                    if record.nameID in (1, 16):
                        try:
                            names.add(record.toUnicode().strip().casefold())
                        except (UnicodeError, LookupError):
                            continue
                style = cast(Any, font["head"]).macStyle
                faces.append(
                    Face(
                        str(path),
                        index,
                        frozenset(names),
                        bool(style & 1),
                        bool(style & 2),
                    )
                )
        except Exception:
            # A corrupt local font is an unavailable candidate, not a failed deck.
            continue
        finally:
            if collection is not None:
                collection.close()
            else:
                for font in fonts:
                    font.close()
    return tuple(faces)


@dataclass
class Metrics:
    units: int
    height: int
    cmap: dict[int, str]
    advances: dict[str, tuple[int, int]]
    kern: dict[tuple[str, str], int]
    shaping: bool


@lru_cache(maxsize=64)
def metrics(face: Face) -> Metrics | None:
    try:
        with TTFont(face.path, fontNumber=face.index, lazy=True) as font:
            units = cast(Any, font["head"]).unitsPerEm
            hhea = font["hhea"]
            heights = [hhea.ascent - hhea.descent]
            if "OS/2" in font:
                os2 = font["OS/2"]
                heights.append(
                    cast(Any, os2).sTypoAscender - cast(Any, os2).sTypoDescender
                )
            if units <= 0 or max(heights) <= 0:
                return None
            kern: dict[tuple[str, str], int] = {}
            if "kern" in font:
                for table in font["kern"].kernTables:
                    if table.format == 0 and table.coverage & 1:
                        kern.update(table.kernTable)
            return Metrics(
                units,
                max(heights),
                font.getBestCmap() or {},
                dict(font["hmtx"].metrics),
                kern,
                "GPOS" in font or "GSUB" in font,
            )
    except Exception:
        return None


class FontBook:
    def __init__(self, paths: list[str], system: bool):
        self.paths, self.system = paths, system
        self._faces: tuple[Face, ...] | None = None
        self._selection: dict[
            tuple[str, bool, bool], tuple[Face | None, Metrics | None]
        ] = {}

    def select(
        self, family: str, bold: bool, italic: bool
    ) -> tuple[Face | None, Metrics | None]:
        key = (family.casefold(), bold, italic)
        if key in self._selection:
            return self._selection[key]
        if self._faces is None:
            self._faces = discover(tuple(self.paths), self.system)
        choices = [f for f in self._faces if family.strip().casefold() in f.names]
        choices.sort(
            key=lambda f: (f.bold != bold, f.italic != italic, f.path, f.index)
        )
        for face in choices:
            data = metrics(face)
            if data is not None:
                self._selection[key] = (face, data)
                return face, data
        self._selection[key] = (None, None)
        return None, None

    def measure(
        self, char: str, props: dict[str, Any], points: F, previous: str = ""
    ) -> tuple[F, F, list[str], str | None]:
        from pptviper.text_rules import script

        family = props.get(script(char), "")
        bold, italic = props.get("b") in ("1", "true"), props.get("i") in ("1", "true")
        face, data = self.select(family, bold, italic) if family else (None, None)
        reasons = []
        missing = None
        em = points * 12700
        if face is None or data is None:
            advance, height = em, em
            missing = family or "<unresolved family>"
            reasons.append("Unavailable font: 1 em fallback per character")
        else:
            glyph = data.cmap.get(ord(char))
            if glyph is None or glyph not in data.advances:
                advance = em
                reasons.append("Unavailable glyph: 1 em fallback")
            else:
                advance = F(data.advances[glyph][0], data.units) * em
                # Ignore negative pair adjustments conservatively; retain positive ones.
                if previous and points >= F(props.get("kern", "0")) / 100:
                    prev = data.cmap.get(ord(previous), "")
                    advance += (
                        F(max(0, data.kern.get((prev, glyph), 0)), data.units) * em
                    )
                if data.shaping:
                    reasons.append(
                        "OpenType shaping/GPOS is not resolved; "
                        "advance metrics are estimates"
                    )
            height = F(data.height, data.units) * em
        if bold and (face is None or not face.bold):
            advance += em / 16
            reasons.append("Synthetic bold: added 1/16 em per character")
        if italic and (face is None or not face.italic):
            reasons.append("Synthetic italic overhang is unresolved")
        if props.get("baseline", "0") != "0":
            height += abs(F(props["baseline"])) / 100000 * em
            reasons.append("Baseline shift retains full font size")
        advance += F(props.get("spc", "0")) * 127
        return max(F(0), advance), height, reasons, missing
