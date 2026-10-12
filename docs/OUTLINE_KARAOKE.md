# Outline karaoke completion — v170

v172 reuses original-source parsing within these proofs; see
OUTLINE_PARSING_REUSE.md. The admission and paint policies below are unchanged.

This records the v170 release comparison. v171 additionally preserves explicit
wrapping, allowing the existing fade pass to trim previously unmatched overlaps;
see WRAPPING_HANDOFF.md and the current full-conversion report.

Sword episode 2's top ending lyrics keep a white foreground while vertically
clipped outline copies change from a purple gradient to a red gradient, in
syllable order. Separate transforms expand and restore the border and blur.
The old completion detector required an unclipped primary-color transition,
so these white-filled captions retained black outlines after simplification.

v170 collects outline evidence before the stack pass discards those copies and
passes it to `normalize_karaoke_completion_paint()`. The existing row grouping,
spacing safeguards, ordered-sweep proof and paint replacement are shared by
the previous foreground route and this new outline route. The previous route
keeps its original admission rules. No second sweep detector was introduced.

## Shared coverage and paint

Static and animated outlines use `_collect_outline_strip_evidence()` for the
same exact-font coverage, rectangular partition, layer order, layout, opacity
and base-stroke checks introduced in v169. Each family is measured once. Its
area weights are reused by `_average_outline_strip_color()`. The static route
continues to reject original transforms.

The animated route additionally requires one outline-color transition per
strip, shared activation times, coextensive source timing, consistent fades,
and unchanged foreground paint and geometry. Transform channels are limited
to outline color and border/blur pulses. Resets, movement, font/layout changes,
alpha changes, legacy scrolling, second color transitions and unproved
partitions keep the existing fallback. Unknown effect annotations are inert.

The row proof compares complete before/after strip palettes, including relative
clip coordinates, alpha and base widths. It requires distinct monotonically
ordered activations, the same palette pair and visible completed-hold evidence.
It also requires evidence for every retained fragment in the row. A missing or
ambiguous fragment cannot leave neighboring syllables independently colored.
Both sweep directions are supported through the existing proof.

The normalizer applies the first spatial fragment's representative completed
outline consistently across its row, following its existing destination-paint
selection. The ordinary renderer validates contrast and retains its opaque,
two-unit outline policy. Slight color differences between lines can reflect
their representative glyph coverage. Fill, geometry and timing are unchanged.
Gradient, blur and border pulses are simplified. No color, font, show, language,
style or strip count is hardcoded.

## Transform timing

Independent FFmpeg/libass rendering verifies that reversed endpoints act like
an instantaneous change immediately after the stated start. Equal and reversed
spelling render identically at nine samples before, at and after activation.

The outline evidence parser normalizes only those reversed endpoints, then
uses the existing `parse_effect_transform()` validator with its explicit
instantaneous policy. Negative/nonfinite times and invalid acceleration are
rejected. Color activation must occur within the cue. Border/blur-only pulses
may finish beyond it through the validator's existing `allow_after_end` option.
The border target must restore the admitted base width. This avoids rejecting
a valid color sweep because an independent geometry pulse extends slightly
past the cue. General freezing and other effect detectors are unchanged.

## Ownership

`OutlineStripEvidence` is pass-local and contains borrowed original sources and
formatting, plus independently owned immutable strip/weight tuples. Transition
evaluation clones formatting and carries parser continuation explicitly.
Its `KaraokeCompletionProfile` keeps palette and timing proof outside rendered
formatting; final formatting contains only the resolved paint to replace.

The stack renderer returns the profile explicitly alongside captions and its
removal count. The stack coordinator owns the profile map and supplies it as a
read-only optional input to the normalizer. The map expires after this pass.
No source events, visibility maps or caller evidence are mutated or cached.
The shared FontMetrics owner's existing caches and leases retain their lifetime.
Replacement parsing and evidence invalidation use the existing `replace_event()`
contract. Document measurement context reaches the contrast renderer explicitly.

## Verification

All 52 current regression scripts pass, including the 70-assertion outline
check, existing static/parser checks, ownership tests and 134 pixel-identical
libass comparisons. Source, v169 and v170 renders were visually inspected.
Production AST comparison permits five changed functions and five added proof
definitions only, excluding docstrings and version identity. Existing font,
parser, general transform and sweep-order algorithms remain unchanged.

Eight full conversions use the complete established font catalog. Four Sword
tracks change only 19 top ending outline colors each: S01E01, S01E03, S01E01
track 6 and the supplied S01E02 track 5. The S01E02 conversion remains 556 events
with peak concurrency 36; its 19 bottom red outlines remain identical to v169.
The other four full outputs, including Overlord, are byte-identical to v169.
All eight statistics, timing, text and non-outline formatting are unchanged.
Original and supplied simplified files are untouched.

The v170 full-comparison report is retained as
`validation/full-outline-comparison-v170.json`. Current sweep behavior is checked
in `validation/outline-karaoke-checks.json`; its extraction audit uses frozen v170. Portable checks run with
`python validation/run_review_checks.py`. The complete conversion harnesses
require the external originals and full font catalog documented in README.md.
