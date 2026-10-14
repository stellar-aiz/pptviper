# Saved-text layout estimates

The seven additional rules are `text-overflow`, `unbreakable-word`,
`excessive-wrap`, `orphan-line`, `font-missing`, `table-cell-overflow`, and
`table-overflow`. They are enabled by default and run without a rendering engine.

## Fonts and reproducibility

fontTools (MIT) reads local TrueType/OpenType fonts and collections. Discovery
uses standard OS directories and optional configured paths. All localized family
names are indexed; available bold/italic faces are preferred. Tests generate an
original MIT-licensed font with known metrics, outside the wheel.

```toml
measure_text = true
system_fonts = false
font_paths = ["/path/to/reproducible/fonts"]
```

Use fixed font files with `system_fonts = false` for reproducible measurements
across machines. Font discovery/metrics are cached within the process; restart
inspection after changing font files. `measure_text = false` explicitly disables
these checks and retains the geometry-only behavior; the effective configuration
records that choice.

Unavailable fonts and missing glyphs use 1 em per character. Synthetic bold adds
1/16 em. Synthetic italic remains unresolved. These are provisional heuristics,
not mathematical upper bounds on every font. `font-missing` groups by requested
font name; found families count as passes. All estimated findings are worst-case,
and uncertainty remains visible even alongside a finding.

## Layout and limitations

Measurements use rational EMU arithmetic (1 pt = 12700 EMU). Saved fontScale,
character spacing, full/small capitals, baseline shift, paragraph spacing, body
and cell margins, indentation, default tabs, explicit breaks and bullet widths
participate. Small capitals use the specified provisional 80% size. Negative
legacy kerning is not used to reduce widths; positive adjustments are retained.
OpenType shaping/GPOS is not implemented and is explicitly unresolved when those
tables are present. Automatic numbering/image bullet widths use a provisional
marker and remain unresolved. Missing sizes use an explicit unresolved estimate.

Western text wraps after whitespace or hyphens. Overlong fragments wrap at
characters. Japanese prohibited start/end classes are stored in `linebreak.py`,
following the JIS X 4051 categories documented by
[W3C JLReq](https://www.w3.org/TR/jlreq/). Closing punctuation moves with the
preceding character; opening punctuation stays with its successor. Punctuation
does not hang outside the frame. Vertical text is unknown, never measured as
horizontal text. This is not a full Japanese typesetting engine.

`properties.text_layout` exposes total lines, content width/height, paragraph line
widths and character counts, overflow distances, font names, and assumptions.
All dimensional strings are exact rational EMU. This observation surface is used
by the calibration tools in #7.

`text-overflow` and `table-cell-overflow` find any positive width/height overflow.
`unbreakable-word` finds forced character wrapping. `excessive-wrap` finds two
extra lines beyond the unwrapped-width baseline, or an intermediate line with at
most two non-whitespace characters. `orphan-line` finds a multi-line paragraph's
final line with at most two such characters. Reasons aggregate per shape.

spAutoFit extends height; wrap=none extends width. Local growth is transformed
through the existing shape/group matrix before off-slide and pair rules execute.
Table frame height grows by the maximum required growth per row. `table-overflow`
checks the resulting frame against slide edges and other peers. Merged cell
geometry remains unresolved. Text row growth is an estimate, not an edit to the
source presentation. Caller bounds providers run after this built-in expansion.

## Calibration gate

Issue #5 AC-9 is a manual gate owned by #7: compare line count and text dimensions
with PowerPoint observations. Automated fixture checks do not establish that real
PowerPoint output is always bounded by these estimates. Keep that criterion open
until real Windows/macOS evidence is available. No source PPTX is modified.

API reference: [fontTools TTFont](https://fonttools.readthedocs.io/en/stable/ttLib/ttFont.html).
