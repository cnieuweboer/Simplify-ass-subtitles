# Proved backing paint — v197

The backed-pulse reducer already proves complete stationary backing rows,
continuous foreground coverage and ordered pulses returning to a common held
pose. Previously it discarded the backing and called the ordinary caption
renderer with only the foreground. A borderless pale foreground therefore gained
an opaque black two-unit border, even when the source used a softer blurred copy.

## Proof and paint handoff

After the existing complete-row proof succeeds, the reducer uses the shared
exact-font settled mask sampler to estimate subtitle-only core and contour RGBA.
It samples a held foreground and its owned backing at the common held size.
Temporary frame-scale pulses do not define the resting backing palette. Every
glyph must supply an unanimated, unfaded held-size backing phase of at least the
existing 20 ms hold threshold. All resting phases across the row must agree in
color, opacity, blur and scale. Overlapping backing phases, unsupported geometry
or masks, actual borders/shadows, changing resting paint, and absent exact font
measurement keep the existing rendering fallback. The ownership/pulse admission
and removal rules remain unchanged.

The sampler's existing Gaussian footprint remains an approximation of libass,
not an ownership test. Contributions are pooled over the complete row before
choosing fill, contour color and constant contour alpha. This avoids glyph
thickness producing a separate palette for every letter. No background/video
color is baked into the result. A compact two-unit contour represents the soft
support; the broad source halo is not reproduced exactly.

`SourceCaptionPaint` is an immutable explicit renderer input. It generalizes the
previous glow-only paint handoff, and the returning-glow route uses the same
record and pooling helper. Ordinary callers still use the existing 3:1 contrast
validation and opaque neutral fallback. Proved absence of a border and general
low-contrast source contours are deferred to v198.

The pulse pass borrows the existing font owner, events and context dictionaries.
It returns fresh captions; mask samples and paint proofs expire within the pass.
No mutable global cache, serialized proof marker, additional event, animated
blur or alpha effect is introduced. Reconstructed captions retain the static
paint through normal ASS tags and existing paint/geometry matching.

## Validation

`tests/check_backed_paint_render.py` covers complete and ambiguous rows, alternate
backing colors, opacity/blur strengths, frame-scale pulses, absent metric owner,
unsupported masks, source immutability, ordering, full conversion, and repeat
stability. Ordinary white-on-white fallback remains unchanged. Native samples
compare source, recovered and opaque-border captions on black, gray and white
backgrounds. The sampler is not claimed to produce pixel-exact source renders.

`validation/run_proved_backing_paint_corpus.py` regenerates nine established
corpus sources and the supplied Goblin Slayer track against hash-verified v196
baselines. It checks source/engine/output hashes, missing fonts, unchanged event
metadata/text/geometry, and the permitted paint differences. Local fonts,
fixtures, outputs, comparisons and reports remain ignored development assets.

Fresh corpus verification changes only paint on 30 supplied-track ending captions
(all 18 romanized lines and 12 translated lines). Event count remains 279 and peak
concurrency remains 26; text, timing, metadata and geometry are unchanged. Other
styles and all nine established corpus outputs/statistics are identical to v196.
The existing color normalizer now reports 18 events as it consolidates tiny
sampled contour differences; all other statistics match. Translation cues outside
the backed-pulse reconstruction retain the ordinary fallback for v198 review.

`validation/render_proved_backing_paint.py` generates 18 native original/v196/v197
comparison panels at six ending times on black, gray and white backgrounds. These
confirm a subdued compact contour; the source's broader blurred halo remains an
approximation. The synthetic render check passes 253 assertions. Required fonts
are available and all fresh full conversions report no missing families.
All 74 current Windows font-backend regression scripts pass, including native
render comparisons. Runtime and harness hashes match the tested files.
After rebasing concurrent wrapper updates, all 15 production wrapper checks and
6 batch checks pass. The MKV/font extraction, simplification, remuxing and font-sync
smoke test also passes. Runtime and regression harness hashes remain unchanged.
