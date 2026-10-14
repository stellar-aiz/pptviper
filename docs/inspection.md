# Static inspection contract

`inspect(path_or_bytes, *, config=None, bounds_provider=None)` returns a `Report`.
The input is a filesystem path or complete PPTX bytes. `config` accepts a `Config`
object or a TOML path. `Report.to_dict()`, `.to_json()`, `.to_text()`, and
`.exit_code` expose the same inspection result. Invalid input is reported rather
than raised; internal accounting mistakes and errors in caller-provided bounds
callbacks remain programming errors.

## Configuration

```toml
max_expanded_bytes = 2147483648
max_parts = 10000
off_slide_threshold_emu = 0

[thresholds]
edge-margin = 457200
font-too-small = 12
# Omit font-family-count to use distinct theme families + 1.

[[suppress]]
rule = "off-slide"
slide = "256"
shape = "ppt/slides/slide1.xml#2"
```

Selectors within a suppression table are ANDed; tables are ORed. At least one
selector is required. Slide selectors use saved `sldId`, not slide ordinal.
Shape selectors use the report's `key`, which includes the source part. A master
logo can therefore be suppressed across slides, or on a single slide by adding
its stable slide ID. Unknown settings, rules, and invalid types are errors.
Only implemented rules can be configured. Resource limits and the original
`off_slide_threshold_emu` are integers. New `[thresholds]` values are finite,
nonnegative numbers; `font-family-count` is an integer. Booleans are rejected.
See [rules](rules.md) for defaults, units, candidate domains, and boundaries.
For cross-slide findings, a slide selector matches any participating slide;
shape and slide selectors are independently ANDed against the finding's members.

The report includes all effective settings. Suppression retains the finding and
its coverage state. An unreadable part always causes exit 3, even when its finding
is suppressed. Unresolved records still cause exit 2 unless a higher-priority
condition exists. Invalid configuration has a dedicated error record and is not
misrepresented as corrupt PPTX. CLI usage errors (such as unknown flags) retain
argparse's standard stderr and exit 2; inspection results use stdout.

## Loading and validation boundary

ZIP entries are streamed without filesystem extraction; actual consumed expanded
bytes and archive entry count are bounded. XML DTDs, internal entities, and
external entities are rejected by defusedxml. External relationships are never
fetched. Broken XML/ZIP, missing required parts, invalid part names, duplicate
ZIP entries, and exhausted limits produce `unreadable-part`.

The structural checks cover content-type and relationship roots, required
presentation/slide/layout/master/theme references, relationship identity and
internal targets, slide dimensions/identity, shape identity, transform integers,
nonnegative extents, and positive group child extents. This is not full OOXML XSD
validation. Transitional PresentationML is supported; unsupported namespaces and
visual constructs are explicitly unresolved. Readable independent slides continue
after local failures. Unenumerable portions are listed separately, without
inventing shape counts.

## Geometry and certainty

Geometry uses rational arithmetic, including fractional scales. Rotations are
clockwise in 1/60000 degree units. Cardinal angles are exact. Other angles use
rational sine/cosine Taylor polynomials with a remainder enclosure and an explicit
pi enclosure. Outward quantization to 35 decimal places bounds denominator growth
at the trig boundary. Affine interval arithmetic propagates uncertainty through
flips and nested groups. Group traversal uses an explicit stack.

The default threshold is zero EMU. A definitely outside edge creates one finding
per effective shape instance, with every edge and maximum overflow recorded.
An enclosure crossing the threshold produces an unresolved record. This numerical
uncertainty is not a geometric tolerance. Non-cardinal enclosures are labeled
`worst-case`; exact stored geometry can be `certain`. Neither label guarantees
that saved bounds describe all effects of PowerPoint rendering.

`emu` is an integer or JSON number; `exact_emu` retains the rational representation.
Bounds and edge details include both enclosure endpoints. mm/pt values are rounded
to three decimal places for display only. Consumers needing exact comparisons
must use `exact_emu`, not JSON floating-point conversion.

## Inheritance and supported values

Slide placeholders match layout placeholders by `idx` (default 0). Layout
placeholders match master placeholders by type, including title/body mappings for
centered titles, subtitles, and content placeholders. Ambiguous mappings are
reported. See the [python-pptx placeholder analysis](https://python-pptx.readthedocs.io/en/latest/dev/analysis/placeholders/)
and [type mapping observations](https://python-pptx.readthedocs.io/en/develop/dev/analysis/placeholders/layout-placeholders.html).

Non-placeholder layout/master shapes become slide instances, subject to saved
master-shape visibility controls. Placeholder templates are inherited through
slide placeholder instances, rather than rendered again as duplicate shapes.
Hidden slides and instantiated hidden shapes are inspected.

The report exposes body margins/defaults, saved AutoFit mode and parameters,
paragraph/list spacing, inherited run properties, theme font references, fills,
theme colors and color mapping. Supported color transforms include luminosity,
saturation, hue, tint, shade, and alpha. Color values are best-effort numeric
values, not a color-managed rendering claim. Theme style fill references resolve
through the theme fill list. Missing script-specific fonts remain unresolved.

Table cells are individual candidates with stored grid/row geometry. Explicit
table style definitions resolve whole-table, banding, first/last row and column
fills/text properties, followed by direct cell fill. Merged-cell geometry and
missing built-in table style definitions remain unresolved. Cell style sources
and raw stored properties are exposed for later text/color rules. [Text layout](text-layout.md) adds saved-font measurement and estimated row
growth. Composited backgrounds, effects, and contrast remain separate work. Unsupported content is not a clean bill of health.

Every Choice/Fallback branch of AlternateContent is inspected. Alternatives with
the same shape ID at the same AlternateContent site share one candidate; the
largest supported overflow wins. Otherwise separate branch locators are used.
Unresolved branches remain visible alongside any finding.

## Coverage and finding identity

The off-slide candidate domain is each effective slide/shape instance, including
groups and table cells. Unknown shape-tree elements also get candidates. Mutually
exclusive corresponding branch alternatives share a candidate. Input checks use
package/part/check locators rather than fictional shape IDs. Unreadable-part
candidates include streamed parts and required references that could not be read;
invalid-ooxml candidates include evaluated relationship, identity, dimensions,
and geometry checks.

Each candidate is counted exactly once: pass, finding, unknown, or not-applicable.
An unresolved reason may coexist with a finding without adding a second candidate.
Suppression never changes these counts. Unenumerated content is disclosed outside
the count. These totals describe executed checks, not rendering accuracy.

Fingerprints hash rule, stable slide ID, and source-qualified target identity.
They exclude measurements and slide ordinals. Malformed/missing IDs use structural
locators with no stability promise across structural edits. Package diagnostics
sort first; then slide ordinal, rule, source-qualified shape, measurement, locator,
and reason determine serialization order. No timestamps or absolute input paths
are included. The packaged `report.schema.json` describes all output variants.

## Text bounds extension

```python
from pptviper import Bounds, inspect


def expanded_bounds(context, saved):
    # context contains shape, slide, and resolved properties.
    # A later text measurer can replace the bounds and return limitations.
    return Bounds.rectangle(-1, 0, 100, 100), ["Estimated text layout"]


report = inspect("slides.pptx", bounds_provider=expanded_bounds)
```

Callbacks are optional and execute in the caller's process. Their bounds must be
in slide coordinates. They must retain saved geometry when text expansion is not
applicable and return every unresolved limitation. The core inspector itself
starts no subprocesses and uses no network connections.

## Additional static rules

All 26 [additional rules](rules.md) use the same effective bounds, including
bounds-provider replacements. Their measured values use `value`, `exact_value`,
and `unit` (EMU, EMU², pt, ratio, or count). Bounds and the original off-slide
measurement retain `emu`/`exact_emu` for compatibility. Configurable limits appear
in `threshold`; predicate-specific values also appear in `details`. A null
threshold denotes a structural predicate or a fixed comparison described in the
catalog. Cross-slide finding members include `slide_id`.

For these additional rules, AlternateContent candidates are marked unresolved
instead of choosing a branch or comparing alternatives as coexisting peers.
The existing off-slide rule still evaluates all supported branches. Unknown
geometry leaves run membership unresolved. Unsupported shape-tree content and
unreadable slides keep aggregate enumeration explicitly incomplete.
