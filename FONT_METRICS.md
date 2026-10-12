# Font measurement boundary

Extraction completed in v166; contracts reviewed for v168.

The three responsibility-review steps are complete: FontMetrics owns reusable
font operations, FontOutlineMatcher owns exact-font profiles, and row geometry
is a coherent set of functions using FontMetrics directly. FontSpacing is removed
without production compatibility aliases or forwarding methods.

| Owner | Responsibilities and lifetime |
| --- | --- |
| FontMetrics | Discovery, exact variants, coverage, bytes/instances, shaping, ASS metrics, contours, fragmented-glyph inspection and RAQM/HarfBuzz ink. Reusable across a batch. |
| FontOutlineMatcher | Bounded decoding and alphabet-specific profiles, borrowing the same FontMetrics; retains the CLI batch lifetime. |
| Row geometry functions | Borrow metrics/events and return fits; do not own fonts, reusable source-fit caches or counters. |
| FontProcessingReport | Explicit caller-owned accepted joins and selective missing-font diagnostics, independent of caches. |
| Subtitle passes | Admission, placement, wrapping, paint, coverage, timing, ownership and reconstruction/removal decisions. |
| Masked-glyph context | Mask indexes and opened handles for one pass; closes those handles. |

All direct and row-proof consumers receive FontMetrics. The CLI constructs it once
before its input loop, with a matcher and report. The Python API uses font_metrics,
optional outline_matcher and optional font_report. See ROW_GEOMETRY.md for the
reuse, failure and selective-reporting contracts.

## Measurement contracts

`FontFace` identifies the exact source path, collection index and sorted variable
coordinates. Face keys, directory/name priority, flags, collection selection and
negative-cache semantics are unchanged. Variable coordinates follow the subtitle's
requested variant; this release does not change that decision to follow libass's
regular-only variable-font behavior.

`FontMetrics.available` is initialized dependency availability. The frozen
`FontCapabilities` record exposes dependency availability, RAQM and optional
HarfBuzz installation. Both describe construction-time support; per-face shaping
still uses the loaded Pillow font's layout engine and retains its original error
and fallback behavior. Consumers do not inspect backend modules or backend caches.

`measure()` returns the same 1024-pixel shaped advances and retains kerning,
ligature, direction, missing-glyph and vertical-advance behavior. Raw outlines,
font sizing, instantiated bytes and shaping all refer to the same exact face.
No measurements write replacement fonts or alter supplied font files.

`open_face()` returns an independently opened TTFont lease. Its caller must close
it; it is not an event cache or a permanently open document font. Font-data caches
are private to FontMetrics. Raw contour results, coverage and face coordinates
remain immutable values; callers borrow them without modification.

## Caption ink and geometry

`line_ink_metrics()` returns an immutable `FontLineInkMetrics` record containing
ASS ascent ratio and baseline-relative 1024-pixel boxes in the original line order.
Blank lines retain None slots. It only refines a face already loaded for measurement:
RAQM supplies raster bounds, while direct HarfBuzz supplies outward-rounded shaped
glyph extents, offsets and advances. Unmeasured or unsupported faces return None.
It does not load a new backend font just to inspect ink. The old lazily attached
`_caption_line_metrics` cache is replaced by a private, initialized ascent cache.

The caller retains its established guard for nonzero tracking. Caption bounds
still own script wrapping and explicit q, alignment, viewport assumptions, shadow
paint offsets, scaling, padding, rotation and coverage policy. The v173 HarfBuzz
ink path preserves the conservative horizontal advance/overhang convention.
Unsupported measurements remain unknown rather than guessed.

## Verification

The v166 extraction preserved the executable FontMetrics implementation from v165. Its focused checks compare immutable v163
selection, variants, collections, measurements, ink, cache identity and dependency
fallbacks; the current focused runner also checks the later explicit result types. Font files are hash-checked. The six row algorithms
also retain normalized AST and decision parity.

The v173 checks also use real uharfbuzz with Pillow forced to BASIC. They reproduce
the missing Skill Bank panel with v172 and retain it with v173. Shaped/raster
bound comparisons cover TTF/CFF, kerning, ligatures, spacing, accents and combining
marks. Deterministic tests cover offsets, outward rounding and unknown extents.
The missing-backend behavior remains conservative.

Run `python validation/run_review_checks.py` for current regression results.
README.md records current release verification; validation/ contains focused
reports, libass comparisons and the full-output comparison report.
