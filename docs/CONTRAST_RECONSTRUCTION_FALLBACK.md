# Contrast correction as a reconstruction fallback — v198

Caption producers can now distinguish proved authored contours, proved absence
of a contour, and proved backing approximations from uncertain reconstruction.
`SourceCaptionPaint` carries the result explicitly. The renderer's neutral
black/white correction and 3:1 candidate threshold remain the fallback when a
producer cannot establish source paint; they no longer override proved paint.
There is no show-specific recognition or user-facing contrast toggle.

## Source evidence

The shared `_source_caption_paint()` checks a producer-owned compatible family
for one visible contour color, opacity and pair of border widths. Clipped or
masked paint, drawings, incompatible font/pose state, invalid widths/colors and
conflicting contour evidence remain uncertain. Borderless evidence requires
visible foreground-only sources with one fill and no discarded shadow support.
Invisible contour parameters are canonicalized for a borderless result rather
than creating unused palette/timing differences.

A selected foreground's complete authored stroke is authoritative in the stack
reducer even when decoration copies have other contours. It is recovered from
the original source only while the selected literal still matches that source.
A hidden stroke does not establish this authority. Full-copy reduction likewise
uses its selected complete foreground's visible stroke. This prevents an early
neutral fallback from mixing with preserved source contours in later glyph and
phase reconstruction.

Thin authored contours retain their widths, including separate horizontal and
vertical widths. Thick contours keep the established two-script-unit cap. This
preserves the simplification budget and prevents larger reconstructed stroke
footprints from changing otherwise valid row grouping. The v197 backing and
returning-glow approximations retain their two-unit measured contour and alpha.

A coupled source fill/outline fade is normalized along with the renderer's
existing opaque fill selection; independent contour transparency remains authored.
The progressive-reveal route deliberately retaining fill transparency restores
its coupled contour transparency too. An off-canvas foreground replaced by its
visible offset shadow invalidates the foreground contour proof before rendering.
The neutral fallback then evaluates the actual visible paint.

## Producer audit and handoff

Migrated producers include complete lyric copies, uniform frame-family paint,
held paint-copy reduction, ordinary stack foregrounds, proved static and animated
outline strips, held moving/sliced captions, progressive reveals, complete-line
jitter, source-aware authored rows, proved full-line captions, animated merged
rows, translated anchor pieces and fragment-phase tails. Existing geometry,
coverage, foreground selection, actor and compositing proofs remain their owners.

Merged rows carry contour alpha and border/axis widths per literal span, along
with color. The covered-held-glyph check uses this same source-aware formatting
conversion; it does not weaken source geometry or paint matching. Later static
joins and serialization keep the resulting formatting rather than reevaluating
contrast. Original events, styles and context dictionaries remain borrowed and
unchanged. No mutable global parser cache or serialized proof marker is added.

Masked glyph recovery, inferred vector text, unresolved shadow stacks and uncertain
backing reconstruction retain the fallback. Inline paint-only frame normalization
keeps the established representative prefix paint and uses its valid visible
stroke. That prefix alone cannot prove borderless paint across a mixed-span line.
These distinctions concern evidence, rather than anime, font or literal names.

The v201 follow-up replaces the inline prefix shortcut and pooled inline-copy
paint with corresponding literal-span ownership. Known borderless/transparent
and invisible spacing ranges remain distinct; uncertain composite layers remain
available to backing proofs. See [INLINE_PAINT_OWNERSHIP.md](INLINE_PAINT_OWNERSHIP.md).

## Validation policy

`tests/check_contrast_fallback_render.py` checks authored white/pale contours,
translucent contours, borderless text, axis widths, coupled fades, shadow transfer,
original foreground authority, missing/conflicting/invalid evidence, span
handoffs, full conversion and repeat stability. Static unblurred source paint is
compared pixel-for-pixel with the proved output on black, gray and white.

At v198, historical extraction/parity checks temporarily substituted v197
caption paint. The v199 test follow-up removes that substitution from all 16
checks: current rendering runs directly, historical contour-independent contracts
remain where useful, and direct paint/native handoff checks protect current intent.
See [CURRENT_POLICY_INTEGRATION_COVERAGE.md](CURRENT_POLICY_INTEGRATION_COVERAGE.md).

`validation/run_contrast_fallback_corpus.py` regenerates ten sources against
hash-verified v197 baselines. Its timeline comparison excludes only contour
color/alpha/width; it retains text, fill, font, placement, layers, actors, clipping
and other formatting, and verifies these at every visibility boundary. When additional frame merges
choose a different pose, the non-pose timeline must remain identical and the
pose must exist in an overlapping original source cue, within 0.011 units of
serialization rounding. Equivalent
adjacent literal spans and identical touching phase joins can coalesce. Fonts,
fixtures, generated subtitles and reports remain ignored local development assets.

Fresh v198 verification: all 75 regression scripts pass, including 96 current
source-intent assertions and 253 backing-paint assertions. All ten full sources
convert without missing fonts. Nine preserve the exact non-contour visibility
timeline; Attack on Titan preserves text/fill/font/visibility and selects three
poses found in the original sign cues after three additional frame merges.
Overlord removes three redundant phase records with the same non-contour timeline
and peak concurrency 32. The supplied Goblin Slayer ending retains v197 paint;
its episode title recovers the authored translucent contour instead of an opaque
black border. Twelve native comparison panels cover source/v197/v198 samples.
After rebasing concurrent menu/worker/flag updates, all 37 Python wrapper/batch,
worker and flag checks pass. The MKV/font extraction, simplification, remuxing and
font-sync smoke test passes. Engine and regression harness hashes remain unchanged.
