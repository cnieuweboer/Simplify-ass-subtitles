# Static outline color — introduced in v169

v172 reuses original-source parsing within these proofs; see
OUTLINE_PARSING_REUSE.md. The admission and paint policies below are unchanged.

This document records the static route and parser correction. v170 adds a
separate animated-strip evidence route described in OUTLINE_KARAOKE.md.

The supplied Sword episode 2 ending has white foreground captions and a static
red outline made from 91 clipped copies per bottom line. The strip colors vary
vertically. The original tags have an extra `)` after a complete hex color;
libass accepts it, while the old parser ignored the color. The stack renderer
then discarded clipped candidates and selected its usual black outline.

v169 fixes the parser and recovers a representative static outline before those
copies are discarded. The 19 bottom captions receive BGR `260AC6`, RGB
`#C60A26`. Their white fill, text, timing, positions and event count stay the
same. In v169 the 19 top captions were unchanged. v170 supplies their completed
outline paint through the existing karaoke sweep normalizer.

## Recovery contract

The stacked-text pass borrows the shared FontMetrics owner and original source
events. It does not edit their formatting, visibility maps or evidence. Existing
foreground selection, replacement and evidence policies still apply.

Recovery requires an unclipped opaque foreground with no authored visible
outline, and a family of lower-painted clipped copies of the same literal text
and layout. Sources must have static paint and geometry, rectangular clips,
transparent fills, matching visible outline alpha below 128, and identical
positive horizontal and vertical border widths across the family. Simple `fad`
envelopes are permitted. Original transforms, movement, karaoke and general
fade transforms are rejected even when the processed copies look static.

The existing tile merger must prove a gapless non-overlapping rectangle. The
rectangle must cover the exact-font ink plus border width. Horizontal bounds
use the existing conservative caption measurement; vertical bounds use cubic
control points and Windows line metrics, avoiding blank ascender space.
Synthetic bold gets the existing measurement's 8% clearance. Contextual
outline shaping, multiline layouts, synthetic italic, unsupported/missing fonts,
rotation, shear and uncertain geometry keep the existing fallback.

The representative color is a linear-light average weighted by each strip's
intersection with the bounded glyph region. It is fresh formatting passed to
the existing renderer, which keeps its contrast validation, two-unit outline
and opaque output policy. No show, style, font, language, color or strip count
is hardcoded. The source gradient, blur and original outline thickness are
still simplified.

## Parser contract

The canonical override evaluator accepts exactly one trailing `)` after a
complete `&Hhex&` color/alpha value, allowing whitespace before the parenthesis.
It applies to `c`, `1c`–`4c`, `alpha` and `1a`–`4a`, including transform targets.
Other malformed suffixes remain rejected. Reset/alignment continuation and
existing channel masking remain unchanged. Ten independent libass pixel
comparisons verify equivalence with the valid spelling.

## Verification and expected differences

All 51 current regression scripts pass. The new focused check has 80 assertions,
including malformed syntax, incomplete/overlapping strips, paint/layout
mismatches, invisible or faint outlines, missing original sources/fonts, source
animation, unsupported contours, read-only inputs, a non-red family and a
rendered comparison. The existing 115 pixel comparisons also pass, for 125
pixel-identical comparisons total. Production AST comparison permits seven
changed definitions and the two new proof helpers only.

Full conversions use the established complete font catalog, not just the
smaller packaged focused-test fonts. Five affected full conversions are compared
against immutable v168 with only the hex-suffix tokenizer correction installed;
all previous matching and timing algorithms remain intact.

| Full subtitle | Expected change from v168 |
| --- | --- |
| Sword S01E02 track 5 | 19 bottom outline colors; all other event fields and statistics unchanged. |
| Sword S01E01, S01E03 and S01E01 track 6 | 19 static ending outline colors each. Two invisible stat values in the episode 1 variants become visible through the alpha parser fix. Statistics unchanged. |
| Overlord S04E02 | Previously ignored foreground colors restored. Output 2,151 → 2,119 events; peak concurrency 30 → 32. Exact output and statistics match parser-corrected v168. |
| Shangri-La, Witch Hat and Demon Slayer | Complete output bytes, statistics, diagnostics and logs unchanged. |

The target conversion remains 556 events with peak concurrency 36. No scrolling
text is dropped in these affected conversions by the scrolling fallback.
Original and supplied simplified subtitles remain untouched.

Full comparisons are recorded in `validation/full-paint-comparisons.json` and
`validation/full-conversion-comparison.json`. Run the portable regression suite
with `python validation/run_review_checks.py`. The full-fixture and paint
comparison harnesses require the external originals and complete font catalog.
