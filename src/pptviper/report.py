"""Deterministic reports and candidate accounting."""

import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from pptviper.config import RULES, Config


def number(value: Fraction) -> int | float:
    return value.numerator if value.denominator == 1 else float(value)


def measurement(value: Fraction) -> dict[str, Any]:
    return dict(
        emu=number(value),
        exact_emu=str(value),
        mm=round(float(value / 36000), 3),
        pt=round(float(value / 12700), 3),
    )


@dataclass
class Report:
    config: Config = field(default_factory=Config)
    slide_contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    unknown: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    shapes: list[dict[str, Any]] = field(default_factory=list)
    unenumerated: list[dict[str, str]] = field(default_factory=list)
    candidates: dict[str, dict[str, str]] = field(
        default_factory=lambda: {r: {} for r in RULES}
    )

    def state(self, rule: str, key: str, state: str) -> None:
        if state not in ("pass", "finding", "unknown", "not-applicable"):
            raise AssertionError("Invalid coverage state")
        if key in self.candidates[rule]:
            raise AssertionError(f"Duplicate candidate: {rule}:{key}")
        self.candidates[rule][key] = state

    def finding(
        self,
        rule: str,
        key: str,
        evidence: str,
        *,
        slide: dict[str, Any] | None = None,
        shapes: list[dict[str, Any]] | None = None,
        measured: dict[str, Any] | None = None,
        threshold: dict[str, Any] | None = None,
        confidence: str = "certain",
        details: dict[str, Any] | None = None,
    ) -> None:
        shapes = shapes or []
        sid = str(slide["id"]) if slide else ""
        digest = hashlib.sha256(
            json.dumps([rule, sid, key], separators=(",", ":")).encode()
        ).hexdigest()
        self.findings.append(
            dict(
                rule=rule,
                slide=slide,
                shapes=shapes,
                measured=measured,
                threshold=threshold,
                confidence=confidence,
                evidence=evidence,
                fingerprint=digest,
                suppressed=self.config.suppressed(rule, sid, shapes),
                locator=key,
                details=details or {},
            )
        )

    def unresolved(
        self,
        reason: str,
        *,
        rule: str = "off-slide",
        locator: str = "package",
        slide: dict[str, Any] | None = None,
        shapes: list[dict[str, Any]] | None = None,
    ) -> None:
        item = dict(
            rule=rule, locator=locator, slide=slide, shapes=shapes or [], reason=reason
        )
        if item not in self.unknown:
            self.unknown.append(item)

    @property
    def exit_code(self) -> int:
        if self.errors or any(f["rule"] == "unreadable-part" for f in self.findings):
            return 3
        if any(not f["suppressed"] for f in self.findings):
            return 1
        return 2 if self.unknown else 0

    def to_dict(self) -> dict[str, Any]:
        def order(item: dict[str, Any]) -> tuple[Any, ...]:
            slide = item.get("slide")
            return (
                slide["number"] if slide else 0,
                item.get("rule", ""),
                tuple(s["key"] for s in item.get("shapes", [])),
                (item.get("measured") or {}).get("emu", 0),
                item.get("locator", ""),
                item.get("reason", ""),
            )

        coverage = {}
        for rule, candidates in self.candidates.items():
            counts = {
                s: sum(v == s for v in candidates.values())
                for s in ("pass", "finding", "unknown", "not-applicable")
            }
            assert sum(counts.values()) == len(candidates), (
                "Coverage accounting mismatch"
            )
            coverage[rule] = dict(candidates=len(candidates), **counts)
        return dict(
            schema_version="1.0",
            rules=list(RULES),
            findings=sorted(self.findings, key=order),
            unknown=sorted(self.unknown, key=order),
            errors=self.errors,
            coverage=coverage,
            effective_config=self.config.to_dict(),
            shapes=sorted(self.shapes, key=order),
            unenumerated=sorted(
                self.unenumerated, key=lambda x: (x["part"], x["reason"])
            ),
            exit_code=self.exit_code,
        )

    def to_json(self) -> str:
        return (
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            + "\n"
        )

    def to_text(self) -> str:
        data = self.to_dict()
        lines = [
            f"pptviper: {len(self.findings)} findings, "
            f"{len(self.unknown)} unresolved; exit {self.exit_code}"
        ]
        lines.extend(
            f"{f['rule']} [{f['confidence']}]"
            f"{' (suppressed)' if f['suppressed'] else ''}: {f['evidence']}"
            for f in data["findings"]
        )
        lines.extend(f"unknown {u['locator']}: {u['reason']}" for u in data["unknown"])
        lines.extend(f"error: {e['message']}" for e in self.errors)
        return "\n".join(lines) + "\n"
