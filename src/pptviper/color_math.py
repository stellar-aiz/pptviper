"""sRGB WCAG luminance and CIEDE2000 differences (D65, unit weights).

References: W3C relative-luminance definition; Sharma, Wu & Dalal (2005),
The CIEDE2000 Color-Difference Formula: Implementation Notes.
"""

from collections.abc import Sequence
from math import atan2, cos, degrees, exp, hypot, radians, sin, sqrt, ulp


def linear(channel: float) -> float:
    channel = channel / 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(rgb: Sequence[float]) -> float:
    return sum(
        c * w for c, w in zip(map(linear, rgb), (0.2126, 0.7152, 0.0722), strict=True)
    )


def contrast(a: Sequence[float], b: Sequence[float]) -> float:
    x, y = sorted((luminance(a), luminance(b)))
    return (y + 0.05) / (x + 0.05)


def composite(
    front: Sequence[float], alpha: float, back: Sequence[float]
) -> tuple[float, ...]:
    return tuple(f * alpha + b * (1 - alpha) for f, b in zip(front, back, strict=True))


def lab(rgb: Sequence[float]) -> tuple[float, float, float]:
    r, g, b = map(linear, rgb)
    xyz = (
        (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047,
        r * 0.2126729 + g * 0.7151522 + b * 0.0721750,
        (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883,
    )

    def f(t):
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    x, y, z = map(f, xyz)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def delta_e_2000(first: Sequence[float], second: Sequence[float]) -> float:
    l1, a1, b1 = first
    l2, a2, b2 = second
    c1, c2 = hypot(a1, b1), hypot(a2, b2)
    mean_c = (c1 + c2) / 2
    g = (1 - sqrt(mean_c**7 / (mean_c**7 + 25**7))) / 2
    ap1, ap2 = (1 + g) * a1, (1 + g) * a2
    cp1, cp2 = hypot(ap1, b1), hypot(ap2, b2)
    hp1, hp2 = degrees(atan2(b1, ap1)) % 360, degrees(atan2(b2, ap2)) % 360
    dl = l2 - l1
    dc = cp2 - cp1
    dh = hp2 - hp1
    if cp1 * cp2 == 0:
        dh = 0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    d_h = 2 * sqrt(cp1 * cp2) * sin(radians(dh / 2))
    mean_l = (l1 + l2) / 2
    mean_cp = (cp1 + cp2) / 2
    mean_h = (hp1 + hp2) / 2
    if cp1 * cp2 == 0:
        mean_h = hp1 + hp2
    elif abs(hp1 - hp2) > 180:
        mean_h += 180 if hp1 + hp2 < 360 else -180
    t = (
        1
        - 0.17 * cos(radians(mean_h - 30))
        + 0.24 * cos(radians(2 * mean_h))
        + 0.32 * cos(radians(3 * mean_h + 6))
        - 0.20 * cos(radians(4 * mean_h - 63))
    )
    sl = 1 + 0.015 * (mean_l - 50) ** 2 / sqrt(20 + (mean_l - 50) ** 2)
    sc = 1 + 0.045 * mean_cp
    sh = 1 + 0.015 * mean_cp * t
    rt = (
        -2
        * sqrt(mean_cp**7 / (mean_cp**7 + 25**7))
        * sin(radians(60 * exp(-(((mean_h - 275) / 25) ** 2))))
    )
    return sqrt(
        (dl / sl) ** 2 + (dc / sc) ** 2 + (d_h / sh) ** 2 + rt * (dc / sc) * (d_h / sh)
    )


def below(value: float, threshold: float) -> bool | None:
    """Keep a floating-point boundary crossing unresolved instead of rounding it."""
    if value == threshold:
        return False
    error = 16 * max(ulp(value), ulp(threshold))
    return (
        True
        if value + error < threshold
        else False
        if value - error >= threshold
        else None
    )
