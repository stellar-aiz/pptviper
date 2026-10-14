"""Exact affine geometry with rational enclosures for trigonometric values."""

from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache
from math import factorial
from xml.etree.ElementTree import Element

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
PI = F(
    "3.14159265358979323846264338327950288419716939937510582097494459230781640628620899"
)
PI_ERROR = F(1, 10**80)


@dataclass(frozen=True)
class Interval:
    low: F
    high: F

    @classmethod
    def exact(cls, value: int | F) -> "Interval":
        return cls(F(value), F(value))

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(self.low + other.low, self.high + other.high)

    def __neg__(self) -> "Interval":
        return Interval(-self.high, -self.low)

    def __sub__(self, other: "Interval") -> "Interval":
        return self + -other

    def __mul__(self, other: "Interval") -> "Interval":
        values = [a * b for a in (self.low, self.high) for b in (other.low, other.high)]
        return Interval(min(values), max(values))

    @property
    def midpoint(self) -> F:
        return (self.low + self.high) / 2


Z, ONE = Interval.exact(0), Interval.exact(1)


@lru_cache(maxsize=256)
def trig(rotation: int) -> tuple[Interval, Interval]:
    """Sin/cos: exact cardinal angles; rational degree-49/48 Taylor enclosures.

    Reduced argument lies in [-pi, pi]. Remainder <= |x|**50/50!, plus pi
    truncation uncertainty (sin/cos are 1-Lipschitz). No platform libm is used.
    """
    units = rotation % 21600000
    if units % 5400000 == 0:
        s, c = [(0, 1), (1, 0), (0, -1), (-1, 0)][units // 5400000]
        return Interval.exact(s), Interval.exact(c)
    if units > 10800000:
        units -= 21600000
    x = F(units, 10800000) * PI
    sin, cos, st, ct = x, F(1), x, F(1)
    for k in range(1, 25):
        st *= -x * x / ((2 * k) * (2 * k + 1))
        ct *= -x * x / ((2 * k - 1) * (2 * k))
        sin += st
        cos += ct
    error = abs(x) ** 50 / factorial(50) + PI_ERROR
    # Outward quantization bounds denominator growth in nested transforms.
    scale = 10**35

    def enclosure(value: F) -> Interval:
        low = (value - error) * scale
        high = (value + error) * scale
        return Interval(
            F(low.numerator // low.denominator, scale),
            F(-((-high.numerator) // high.denominator), scale),
        )

    return enclosure(sin), enclosure(cos)


@dataclass(frozen=True)
class Matrix:
    a: Interval = ONE
    b: Interval = Z
    c: Interval = Z
    d: Interval = ONE
    e: Interval = Z
    f: Interval = Z

    def point(self, x: Interval, y: Interval) -> tuple[Interval, Interval]:
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f

    def compose(self, o: "Matrix") -> "Matrix":
        e, f = self.point(o.e, o.f)
        return Matrix(
            self.a * o.a + self.c * o.b,
            self.b * o.a + self.d * o.b,
            self.a * o.c + self.c * o.d,
            self.b * o.c + self.d * o.d,
            e,
            f,
        )


def translate(x: F, y: F) -> Matrix:
    return Matrix(e=Interval.exact(x), f=Interval.exact(y))


@dataclass(frozen=True)
class Bounds:
    left: Interval
    top: Interval
    right: Interval
    bottom: Interval

    @classmethod
    def rectangle(cls, x: int, y: int, width: int, height: int) -> "Bounds":
        return cls(*(Interval.exact(v) for v in (x, y, x + width, y + height)))

    def overflows(self, width: int, height: int) -> dict[str, Interval]:
        return dict(
            left=-self.left,
            top=-self.top,
            right=self.right - Interval.exact(width),
            bottom=self.bottom - Interval.exact(height),
        )


def pair(node: Element, name: str, keys: tuple[str, str]) -> tuple[F, F]:
    child = node.find(A + name)
    if child is None:
        raise ValueError(f"Missing transform {name}")
    values = tuple(int(child.attrib[key]) for key in keys)
    if any(abs(value) > 2**63 - 1 for value in values):
        raise ValueError("Coordinate exceeds supported OOXML integer range")
    return F(values[0]), F(values[1])


def transform(
    node: Element, parent: Matrix, group: bool = False
) -> tuple[Bounds, Matrix]:
    x, y = pair(node, "off", ("x", "y"))
    w, h = pair(node, "ext", ("cx", "cy"))
    if w < 0 or h < 0:
        raise ValueError("Negative extent")
    s, c = trig(int(node.get("rot", "0")))
    flips = []
    for key in ("flipH", "flipV"):
        v = node.get(key, "0")
        if v not in ("0", "1", "true", "false"):
            raise ValueError(f"Invalid {key}")
        flips.append(Interval.exact(-1 if v in ("1", "true") else 1))
    fx, fy = flips
    rotate = Matrix(c * fx, s * fx, -s * fy, c * fy)
    local = (
        translate(x + w / 2, y + h / 2)
        .compose(rotate)
        .compose(translate(-w / 2, -h / 2))
    )
    world = parent.compose(local)
    corners = [
        world.point(Interval.exact(a), Interval.exact(b))
        for a, b in ((0, 0), (w, 0), (0, h), (w, h))
    ]
    xs, ys = zip(*corners, strict=True)
    bounds = Bounds(
        Interval(min(v.low for v in xs), min(v.high for v in xs)),
        Interval(min(v.low for v in ys), min(v.high for v in ys)),
        Interval(max(v.low for v in xs), max(v.high for v in xs)),
        Interval(max(v.low for v in ys), max(v.high for v in ys)),
    )
    if group:
        ox, oy = pair(node, "chOff", ("x", "y"))
        cw, ch = pair(node, "chExt", ("cx", "cy"))
        if cw <= 0 or ch <= 0:
            raise ValueError("Non-positive group child extent")
        world = world.compose(
            Matrix(a=Interval.exact(w / cw), d=Interval.exact(h / ch))
        ).compose(translate(-ox, -oy))
    return bounds, world
