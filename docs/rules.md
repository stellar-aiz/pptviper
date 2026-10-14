# Static rules

All rules run by default. Intentional overlap, hidden content, or irregular
arrangements still produce findings; use explicit suppression for accepted cases.
These are checks of saved values and effective AABBs, not rendered pixels.
The three foundation rules are `off-slide`, `invalid-ooxml`, and `unreadable-part`.

## Geometry

| Rule | Finding predicate | Candidate |
|---|---|---|
| edge-margin | Any signed edge margin < 457200 EMU | Shape |
| overlap | Both intersection dimensions > 0; touching passes | Unordered pair |
| too-close | Nonnegative axis gap < 273600 EMU with positive cross-axis overlap | Unordered pair |
| misaligned | Any corresponding edge/center difference > 0 and <= 72000 EMU | Unordered pair |
| uneven-gap | Maximum minus minimum adjacent gap > 0 | Run of at least 3 |
| uneven-size | Same-kind members differ in width/height on the run axis | Run/kind |
| zero-size | Either AABB dimension = 0; lines and connectors excluded | Shape |
| tiny-shape | Both AABB dimensions < 36000 EMU | Shape |
| hidden-shape | Saved shape hidden flag is true | Shape |
| connector-unattached | Missing endpoint reference or nonzero midpoint-proxy distance | Connector |
| position-drift | Same-layout/type/idx placeholders differ across slides | Role pair |
| layout-override | Local placeholder geometry differs from inherited layout bounds | Placeholder |

An overlap finding includes text/text, text/shape, or shape/shape classification
and containment. Multiple qualifying axes or reasons become one finding.
Connector proxies use the nearest of the target AABB's four edge midpoints and
maximum-axis distance. They retain unknown connection-site reasons even when the
proxy matches. Missing references are certain; proxy findings are worst-case.
Unavailable endpoints or targets remain unknown. Partial stored transforms that
the foundation cannot resolve remain unknown; no coordinates are invented.

## Text and tables

| Rule | Finding predicate | Candidate |
|---|---|---|
| autofit-shrunk | normAutofit fontScale < 100000 or lnSpcReduction > 0 | Text shape |
| font-too-small | Effective size × saved scale < 12 pt; 9 pt for footer/date/slide-number/table cells | Text shape/cell |
| font-size-inconsistent | Normalized effective size sets differ at a shared paragraph level | Role pair |
| line-spacing-inconsistent | Spacing signatures differ at a shared paragraph level | Role pair |
| bullet-inconsistent | Bullet signatures/indentation differ at a shared paragraph level | Role pair |
| font-family-count | Used distinct families > distinct theme families + 1 | Deck |
| east-asian-font-unset | A used W/F-width Unicode character has no resolved ea font | Text shape/cell |
| empty-paragraph-spacing | Empty and nonempty paragraphs coexist | Text shape/cell |
| manual-line-break | Saved a:br is present | Text shape/cell |
| title-missing | No nonempty title/ctrTitle placeholder | Slide |
| title-duplicate | Equal trimmed nonempty title appears on multiple slides | Title group |
| empty-placeholder | Text is empty or equals inherited template text | Text placeholder |
| text-hygiene | Repeated spaces, boundary whitespace, mixed full/half-width Latin/digits, or unequal paired bracket counts | Text shape/cell |
| table-column-uneven | Stored widths differ, excluding first column when firstCol is enabled | Table frame |

Bracket checks cover parentheses, full-width parentheses, Japanese corner/double
corner brackets, square brackets, and lenticular brackets. They compare counts,
not grammatical nesting. Case is preserved in titles. Font checks use saved
resolved run values; they never load or measure fonts. Missing inheritance,
font size, or theme/script resolution remains unknown. Bullet type overrides
replace inherited alternatives rather than combining incompatible bullet modes.
Fewer than two eligible table columns is not-applicable.

## Candidate domains

Global pairs and runs use leaf shapes and table frames on the same slide.
Group containers and table cells are excluded from those domains; group children
and hidden leaf shapes remain eligible. Unary rules inspect effective instances.

For horizontal runs, sort by left, top, and stable key. Append a shape to the
first existing run with a positive common vertical intersection and no horizontal
overlap with its last member; otherwise start a run. Vertical runs transpose
axes. Singletons do not participate. These deterministic disjoint partitions
avoid enumerating every possible maximal subset. Pair enumeration is quadratic
in the number of peers, so very dense slides can still be expensive.

Same kind means preset/custom geometry, text presence, and placeholder type.
Role pairs are the deduplicated union of same-kind members within runs and
cross-slide placeholders with the same layout part, type, and idx. No majority
or first-shape reference is selected. Compare sets at shared paragraph levels;
unshared levels are not asserted equal or different. Missing values remain
unknown. Candidate identity excludes measurements, but changing group membership
naturally changes run identity.

Coverage counts declared candidates, not all hypothetical arrangements. A finding
with unknown reasons counts once as finding. Non-applicable instances count as
not-applicable. Ambiguous branches, uncertain run membership, and incomplete
aggregate enumeration have explicit unresolved candidates/reasons.

## Threshold settings

```toml
[thresholds]
edge-margin = 457200       # EMU; strict <
too-close = 273600         # EMU; strict <
misaligned = 72000         # EMU; 0 < difference <= threshold
tiny-shape = 36000         # EMU; both dimensions strictly below
font-too-small = 12        # pt; strict <
font-too-small-note = 9    # pt; strict <
# font-family-count = 3    # Optional absolute integer cap; strict >
```

The original `off_slide_threshold_emu` remains a top-level setting. Python callers
may supply a partial `Config(thresholds={...})`; defaults fill the other keys.
Unknown keys, negative/nonfinite values, booleans, and noninteger family caps
are configuration errors. Equality follows each rule's operator. Numerical
intervals crossing an operator boundary are unknown, not rounded into a result.
