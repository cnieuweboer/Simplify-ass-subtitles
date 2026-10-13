# Returning highlights and persistent glow paint — v190

The ordinary stack reducer used frozen foreground paint and literal ASS border
paint. A persistent colored glow is primary paint on a blurred lower copy, so it
was discarded without supplying a contour color. The generated foreground also
moved to layer zero, allowing retained offset shadow copies to darken its fill.
Short dissolving highlight fragments had different intervals and sampled scales,
so they survived as visible karaoke remnants.

The existing stack preparation now collects a bounded source proof before
rendering removes those paint layers. Original events, formatting and parser
continuation remain borrowed and unchanged; evaluations and indexes are private
to this invocation. No source context is persisted through serialization.

Admission requires uniform stationary foreground fragments, a returning primary
color pulse, and exactly one persistent lower glow at the same anchor and layout.
The glow may share synchronized scale pulses which restore the source size.
An admitted row has at least two distinct, monotonically ordered activations and
one shared base/highlight/contour palette. Every candidate word must pass: a
missing letter, unsupported pulse, competing glow or inconsistent palette keeps
the ordinary fallback for the row. Neither show names nor particular colors,
fonts, actors, glyph counts or lyric wording select the runtime behavior.

Each pulse must have complete matching original letters or whole-word copies.
Glyph anchors use the existing exact-font advance model, with a tolerance of
1.5 script units or 6% of text height, whichever is larger. Whole-word copies
retain the same anchor and layout; bounded scale changes are allowed. Source
copies must dissolve to transparent and may animate only opacity, blur and scale.
The existing effect validator supplies the 50 ms timing-rounding allowance.
Independent text, movement, resets, clips and paint-changing copies provide no
ownership proof. Exact fonts are required even for whole-word proofs.

The normal stack renderer receives explicit representative fill and glow contour
paint. It restores the source scale and retains the foreground's compositing
layer. Only this source-proved glow route bypasses the ordinary neutral-contour
contrast fallback: converting an authored glow into a crisp two-unit border is
an approximation, and the original palette is retained. Other caption rendering,
static gradients and the one-way karaoke completion detector keep their policy.
No global contrast threshold or near-color normalization policy changes.

The stack coordinator owns accepted fragment IDs and removes them after their
caption has actually been rendered. These removals contribute to the existing
`stacked_text_copies_flattened` counter; wrapper catalogs need no new counter.
Offset shadow copies and ordinary entrance/exit tails are retained. The release
therefore removes proven highlight remnants without claiming every opening
becomes exactly one event per line or that the whole converter is idempotent.

Validation includes synthetic letter/word copies, reversed sweeps, scale pulses,
alternative palettes, missing/shifted letters, competing glows, independent text,
returning/cyclic colors, source immutability and repeated stack processing.
Native libass samples check a stable static hold. The Goblin Slayer opening is
local regression evidence; its subtitles and fonts are not published with code.
Fresh corpus comparisons use the verified v189 engine/output hashes and require
unchanged bytes and statistics for all nine established sources, including the
Demon Slayer ending gradient. See `validation/run_glow_pulse_corpus.py`.

The fresh v190 run passes 174 focused assertions. It reduces this full track from
998 to 660 events: top-left lyrics 499 → 324 and the matching chant family
457 → 294. The ending and signs remain identical. Fourteen native render pairs
verify static top-left holds. All nine established corpus outputs and statistics
are unchanged. Generate the native samples with
`python validation/render_glow_pulse_corpus.py` after the corpus runner.

v191 corrects the representative-paint policy recorded above: v190's temporary
highlight fill and opaque raw glow did not reproduce the resting appearance.
See [SETTLED_GLOW_PAINT.md](SETTLED_GLOW_PAINT.md). Ownership and sweep admission
remain unchanged.
