"""Deterministic wrapping and Japanese kinsoku character classes.

Classes follow JIS X 4051's prohibition categories as documented by W3C JLReq:
https://www.w3.org/TR/jlreq/#characters_not_starting_a_line
https://www.w3.org/TR/jlreq/#characters_not_ending_a_line
This is a saved-text heuristic, not a full JIS typesetting implementation.
"""

import unicodedata
from dataclasses import dataclass
from fractions import Fraction as F

NO_START = frozenset(
    "、。，．・：；？！‼⁇⁈⁉ー〜～ヽヾゝゞ々〻ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ）〕］｝〉》」』】〙〗»’”)]}"
)
NO_END = frozenset("（〔［｛〈《「『【〘〖«‘“([{")


@dataclass(frozen=True)
class Glyph:
    text: str
    width: F
    height: F


def breakable(a: str, b: str) -> bool:
    if b in NO_START or a in NO_END:
        return False
    return (
        a.isspace()
        or a in "-‐"
        or any(unicodedata.east_asian_width(c) in ("W", "F") for c in (a, b))
    )


def wrap(
    glyphs: list[Glyph], width: F, tab: F, enabled: bool
) -> tuple[list[list[Glyph]], bool]:
    lines: list[list[Glyph]] = []
    line: list[Glyph] = []
    forced = False
    for glyph in glyphs:
        if glyph.text == "\n":
            lines.append(line)
            line = []
            continue
        line.append(glyph)
        while enabled and line_width(line, tab) > width and len(line) > 1:
            positions = [
                i
                for i in range(1, len(line))
                if breakable(line[i - 1].text, line[i].text)
                and line_width(line[:i], tab) <= width
            ]
            if positions:
                split = positions[-1]
            else:
                # Honor kinsoku even when an overwide indivisible fragment must remain.
                split = len(line) - 1
                while split > 0 and (
                    line[split].text in NO_START or line[split - 1].text in NO_END
                ):
                    split -= 1
                if split == 0:
                    break
                forced = True
            lines.append(line[:split])
            line = line[split:]
    lines.append(line)
    too_wide = forced or any(line_width(line, tab) > width for line in lines)
    return lines, too_wide if enabled else False


def line_width(line: list[Glyph], tab: F) -> F:
    total = F(0)
    for glyph in line:
        total = (total // tab + 1) * tab if glyph.text == "\t" else total + glyph.width
    return total
