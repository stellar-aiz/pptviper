"""Validated, explicit inspection settings."""

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

RULES = ("off-slide", "invalid-ooxml", "unreadable-part")


@dataclass
class Config:
    max_expanded_bytes: int = 2 * 1024**3
    max_parts: int = 10000
    off_slide_threshold_emu: int = 0
    suppress: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for key in ("max_expanded_bytes", "max_parts", "off_slide_threshold_emu"):
            value = getattr(self, key)
            minimum = 0 if key == "off_slide_threshold_emu" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{key} must be an integer >= {minimum}")
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
            and ("slide" not in s or s["slide"] == slide)
            and ("shape" not in s or any(s["shape"] == p["key"] for p in shapes))
            for s in self.suppress
        )
