# Inline paint ownership — v201

Paint decisions now use the relevant literal ranges across complete source spans
and phases. The frame reducer no longer applies a representative prefix to an
entire line. Inline stacked-copy reconstruction likewise uses corresponding
source ranges instead of pooling every contour in the caption.

## Evidence and ownership

`_literal_paint_ranges()` reuses `static_object_key()` and its resolved span
signatures. It aligns identical literal strings at the union of their character
offsets, so different override splitting does not create a different ownership
relation. Spaces retain their exact offsets. Drawings, remaining animation and
different literals cannot establish this correspondence. Inputs, styles and
parser dictionaries remain borrowed and unchanged.

The selected inline foreground owns its visible authored stroke separately in
each range. Borderless or otherwise uncertain ranges use the compatible source
paint at that range and the existing `SourceCaptionPaint` proof. Uncertain
reconstruction still uses neutral contrast repair. A fully invisible range is
proved absence of paint, not a reason to invent a contrast outline: its glyph
advance remains while its paint stays hidden.

A translucent foreground over another visible fill is composite paint, rather
than redundant lettering. Inline stack removal now keeps those layers unless a
backing proof can reconstruct them. Fully opaque foreground reduction retains its
existing admission. This avoids pretending that an individual transparent source
plane describes the combined appearance of several planes.

## Source phases and reduction

Inline frame paint is resolved within time-connected, nonoverlapping families.
For each literal range, the most visible source phase supplies the resting paint;
longer equal-opacity holds provide the tie-break. Authored base fill transparency
and independent contour transparency remain. A coupled fill/outline fade settles
at the authored base alpha rather than forcing both channels opaque. Known
invisible spacing glyphs stay invisible throughout the replacement.

The complete relevant palette uses the existing two-RGB-level policy through
`_bounded_text_color()`. Representatives are observed source colors, chosen by
votes. There are no transitive clusters; wider gradients and ordered ramps remain
separate colors. Visible temporal color/contour changes that do not establish one
resting paint family retain their original phases. Clip uncertainty, shadow
transfer, mixed layout or unavailable visible paint also retains existing refusal
or reconstruction fallback behavior.

Uniform geometry is proved independently of paint. Paint-only resets can satisfy
that existing geometry requirement through their resolved state. The frame
producer then passes a local set of approved source identities to the existing
motion merger, whose key includes every settled paint range. This replaces raw
inline spelling as an obstruction for those proved families. Ordinary inline
admission remains guarded; motion and jitter displacement bounds are unchanged.
No show-specific rule, new ownership graph or serialized proof marker is added.

The v204 vector-mask crash fix preserves drawing command strings in resolved
`state_key()` tuples while rounding only numeric coordinates to the existing
six decimal places. Both `clip` and `iclip` remain geometry evidence; different
commands, coordinates and path lengths remain distinct. Inline frame paint still
refuses clipped reconstruction. The fix changes neither clip admission nor the
source/cache ownership contract.

Restored fade paint also explicitly hands off original source exposure to v200's
pose selector. Existing support intervals remain authoritative. When only inline
source states are available, primary/outline/shadow alpha is averaged across
non-whitespace literal characters at the proved uniform geometry. This is a
character-count exposure proxy, not a pixel-area measurement. Extended output
visibility and hidden exits cannot manufacture new pose support.

Inline reconstruction replays authored geometry and resets while attaching
selected paint at exact offsets. Frame families with uniform geometry can resolve
those resets once before emitting their span paint. Secondary and removed-shadow
channels are not reintroduced as unused per-span overrides. Later phase merging
and final compaction consume the emitted paint rather than replacing its owner.

## Validation

`tests/check_inline_paint_ownership.py` covers mixed contours, gradients, tiny
palettes, fades, independent/coupled transparency, named/empty resets, whitespace,
a borderless prefix followed by outlined text, invisible spacing, uncertain
composites, shadow transfer, motion handoff, source exposure and full conversion.
`tests/check_inline_paint_ownership_render.py` compares independently authored
source paint with native output on black, gray and white, including held/extended
fade timing and an invisible moving spacing glyph.

The historical parser-consumer check now compares inline admission, identities,
event fields, resolved geometry/history and the actual foreground's primary
paint. Obsolete raw spelling and historical pooled paint are no longer the
specification for those changed inline cases. Unaffected historical comparisons
remain. The routine inventory contains 80 scripts.

`validation/run_inline_paint_corpus.py` regenerates all ten restored sources
against hash-verified v200 outputs. Existing literal geometry, timing and event
fields must remain. Additional retained records must have exact source-paint
witnesses from refused inline stacks. Fonts, sources, generated conversions,
render panels and reports remain ignored local development assets.

Fresh validation: all 80 regression scripts pass, including 94 whole-span
ownership assertions, 94 native paint checks and 9,894 parser-consumer checks.
Runtime and harness inputs remained stable throughout the final run. All eight
wrapper/utility suites (76 tests) and the MKV/font-sync smoke workflow also pass.
All ten corpus sources convert with their exact fonts and unchanged source files.
Eight outputs remain byte-identical. Existing literal geometry, timing and event
fields remain unchanged in every case. Attack on Titan preserves its invisible
district-name spacer and authored borderless paint. Shangri restores a per-letter
gradient and retains 36 source-witnessed translucent composite records instead of
discarding their foreground fill. Its flattened-copy counter decreases by 36;
the other changed file's statistics remain identical.

Four native source/v200/v201 comparison panels cover the restored gradient and
district label on gray and white. All 36 retained source copies were also rendered;
23 still contribute visible paint, and 13 are outside the viewport at their
sampled midpoint. Retention does not introduce a new compositing approximation.

## After-release evaluation

The decisions now reflect the complete corresponding span family and survive
phase merging, final compaction and repeated conversion in the focused checks.
Exact literal offsets and the existing source-contour/geometry proofs suffice;
no new ownership model is required. The earlier pooled/prefix transformations
were corrected at their producers, with an explicit source-exposure handoff.

No larger review is required to complete this release. Reducing the remaining
uncertain translucent composites would require a genuine backing/compositing
proof, rather than treating them as redundant copies; they are deliberately kept.
The planned thick-outline policy review (v202), global API review and pass-local
index review remain separate work.
