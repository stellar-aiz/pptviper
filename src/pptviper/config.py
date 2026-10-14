"""Validated, explicit inspection settings."""

import math
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pptviper.rule_catalog import RULES, THRESHOLDS


@dataclass
class Config:
    max_expanded_bytes: int = 2 * 1024**3
    max_parts: int = 10000
    measure_text: bool = True
    system_fonts: bool = True
    font_paths: list[str] = field(default_factory=list)
    off_slide_threshold_emu: int = 0
    suppress: list[dict[str, str]] = field(default_factory=list)
    thresholds: dict[str, int | float | None] = field(
        default_factory=lambda: dict(THRESHOLDS)
    )

    def __post_init__(self) -> None:
        if type(self.measure_text) is not bool or type(self.system_fonts) is not bool:
            raise ValueError("measure_text and system_fonts must be booleans")
        if not isinstance(self.font_paths, list) or any(
            not isinstance(p, str) or not p for p in self.font_paths
        ):
            raise ValueError("font_paths must be a list of nonempty paths")
        for key in ("max_expanded_bytes", "max_parts", "off_slide_threshold_emu"):
            value = getattr(self, key)
            minimum = 0 if key == "off_slide_threshold_emu" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{key} must be an integer >= {minimum}")
        if not isinstance(self.thresholds, dict) or set(self.thresholds) - set(
            THRESHOLDS
        ):
            raise ValueError("Unknown threshold key")
        self.thresholds = {**THRESHOLDS, **self.thresholds}
        for key, value in self.thresholds.items():
            if value is None and key == "font-family-count":
                continue
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or (isinstance(value, float) and not math.isfinite(value))
                or value < 0
            ):
                raise ValueError(f"{key} threshold must be finite and nonnegative")
            if key == "font-family-count" and type(value) is not int:
                raise ValueError("font-family-count threshold must be an integer")
        if not isinstance(self.suppress, list):
            raise ValueError("suppress must be an array of tables")
        for s in self.suppress:
            if not isinstance(s, dict) or not s or set(s) - {"rule", "slide", "shape"}:
                raise ValueError(
                    "Suppression requires rule, slide, and/or shape selectors"
                )
            if any(not isinstance(v, str) or not v for v in s.values()):
                raise ValueError("Suppression selectors must be nonempty strings")
            if "rule" in s and s["rule"] not in RULES:
                raise ValueError(f"Unknown rule: {s['rule']}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_toml(cls, path: str | Path) -> "Config":
        with Path(path).open("rb") as stream:
            data = tomllib.load(stream)
        if set(data) - set(cls.__dataclass_fields__):
            raise ValueError("Unknown configuration key")
        return cls(**data)

    def suppressed(self, rule: str, slide: str, shapes: list[dict[str, Any]]) -> bool:
        return any(
            ("rule" not in s or s["rule"] == rule)
            and (
                "slide" not in s
                or s["slide"] == slide
                or any(p.get("slide_id") == s["slide"] for p in shapes)
            )
            and ("shape" not in s or any(s["shape"] == p["key"] for p in shapes))
            for s in self.suppress
        )
