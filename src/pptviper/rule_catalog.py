"""Registered rule names and explicit configurable threshold defaults."""

BASE_RULES = ("off-slide", "invalid-ooxml", "unreadable-part")
GEOMETRY_RULES = (
    "edge-margin",
    "overlap",
    "too-close",
    "misaligned",
    "uneven-gap",
    "uneven-size",
    "zero-size",
    "tiny-shape",
    "hidden-shape",
    "connector-unattached",
    "position-drift",
    "layout-override",
)
TEXT_RULES = (
    "autofit-shrunk",
    "font-too-small",
    "font-size-inconsistent",
    "line-spacing-inconsistent",
    "font-family-count",
    "east-asian-font-unset",
    "empty-paragraph-spacing",
    "manual-line-break",
    "bullet-inconsistent",
    "title-missing",
    "title-duplicate",
    "empty-placeholder",
    "text-hygiene",
)
NEW_RULES = GEOMETRY_RULES + TEXT_RULES + ("table-column-uneven",)
LAYOUT_RULES = (
    "text-overflow",
    "unbreakable-word",
    "excessive-wrap",
    "orphan-line",
    "font-missing",
    "table-cell-overflow",
    "table-overflow",
)
RULES = BASE_RULES + NEW_RULES + LAYOUT_RULES
THRESHOLDS: dict[str, int | float | None] = {
    "edge-margin": 457200,
    "too-close": 273600,
    "misaligned": 72000,
    "tiny-shape": 36000,
    "font-too-small": 12,
    "font-too-small-note": 9,
    "font-family-count": None,
}
