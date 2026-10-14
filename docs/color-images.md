# Color and image inspection

The eight rules are `low-contrast`, `low-contrast-non-text`, `off-theme-color`,
`near-duplicate-color`, `color-count`, `image-distorted`, `image-low-resolution`,
and `image-crop-outside`. They run by default alongside the existing rules.

## Contrast and background candidates

Set `contrast_level = "AA"` (default) or `"AAA"` at the top level of inspection
settings. AA thresholds are 4.5 for normal text and 3 for large text; AAA uses
7 and 4.5. Large means at least 18 pt, or bold at least 14 pt, after saved scaling.
Non-text contrast uses 3. A distinguishable outline or fill suffices; the worse
color within each paint is used before selecting the better of fill and outline.

The inspector follows the text/shape's own fill, lower shapes in saved paint
order, layout/master shapes, then the effective slide/layout/master background.
Partially covering rectangles split the region, so an opaque shape does not erase
uncovered background candidates. Transparent paints composite against every
remaining background candidate in sRGB. Linear gradients include intersecting
stops and interpolated region endpoints; patterns include foreground/background.
Theme matrix references retain their resolved placeholder colors.

The minimum supported contrast pair and its source are included in evidence.
The [WCAG relative-luminance definition](https://www.w3.org/WAI/WCAG21/Understanding/relative-luminance.html)
uses the 0.04045 sRGB breakpoint. A small floating-point enclosure around a
threshold stays unknown rather than being rounded into a finding. Numeric output
is an estimate, not an exact symbolic evaluation of fractional powers.

Any image background, including picture fills and unsupported image formats,
keeps text contrast unknown. Pixels are never decoded, and the image case does
not generate a low-contrast finding from guessed colors. Effects keep unresolved
reasons alongside the result that ignores the effect. Unsupported paint, missing
geometry, and traversal limits remain explicit unknowns.

Bounds are the existing effective AABBs, including text growth. Arbitrary shape
contours, rotated/path-gradient mapping, complex effects and actual glyph-pixel
coverage are not renderer-equivalent. Contrast findings are worst-case estimates;
#7 owns the PowerPoint visual check. Traversal is bounded at 4096 region visits,
512 layers and 512 color combinations per result; truncation is never clean.

## Palette checks

Resolved text, fill and outline RGB colors participate; image pixels do not.
Direct `srgbClr`, `sysClr`, `prstClr`, `scrgbClr` and `hslClr` sources produce
`off-theme-color`, including inherited visible sources. Theme references retain
their source identity. Standard named RGB values are stored as data; there is no
runtime image-library dependency.

`color-count` finds more than 14 distinct colors. `near-duplicate-color` compares
unordered RGB pairs after D65 Lab conversion: 0 < CIEDE2000 difference < 3.
The implementation is checked against the published reference pairs from
[Sharma, Wu and Dalal (2005)](https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/ciede2000noteCRNA.pdf).
Unresolved palette portions remain visible alongside known counts/findings.

## Image checks

The ZIP loader reads at most a 64 KiB prefix of each binary part for header
metadata, while continuing its existing streamed size/CRC checks. It retains only
parsed dimensions, not the binary pixels. PNG IHDR, JPEG SOF, GIF and BMP headers
are supported. Invalid/truncated headers or unsupported formats remain unknown;
JPEG metadata placing SOF beyond the prefix limit is also unknown.

Aspect ratios use exact cross-products of stored unrotated extents and cropped
pixel dimensions. No rounding tolerance hides a one-EMU distortion. Effective
resolution must be at least 150 dpi on both axes. Negative srcRect values produce
`image-crop-outside`; exhausted/invalid crops leave aspect and resolution unknown.
All candidates retain existing coverage and suppression semantics.

No image decoder dependency was added. Pillow is used only by test fixture
creation, already a development dependency through python-pptx. Manual color-miss
calibration remains the explicit unchecked #7 gate.
