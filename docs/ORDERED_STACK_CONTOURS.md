# Ordered source contours — v206

A borderless foreground over several differently colored strokes used to pool
those strokes as conflicting paint. Neutral contrast fallback replaced authored
contours with black or white; dark-to-light fill gradients could acquire an
abrupt neutral-outline switch. The fill gradient itself survived.

The existing stack producer now distinguishes paint order from conflicting
owners. With identical literal geometry, an opaque sharp contour directly below
an opaque borderless foreground owns the retained inner band. Wider lower
contours are decorative and need not agree with that contour's color. The
producer passes this evidence through the existing `SourceCaptionPaint` and
renderer; global contrast fallback and the two-unit reconstruction cap remain.

Uniform glyph stacks and corresponding inline spans share the same proof.
Literal offsets align different tag splitting, so both fill and contour gradients
survive row reconstruction and final compaction. Actual numeric layer and source
order select the nearest supporting plane, independently of group traversal.
Thin and per-axis widths retain the existing policy. This selects representative
source paint; it does not try to reproduce a discarded outer glow.

Original sources must match the current literal, lifetime and layout. The proof
reads original blur and masks before freezing erased them. It can skip a lower
borderless fill wholly hidden by the foreground, but cannot borrow through an
uncertain blurred, shadowed, masked or translucent contour. Missing sources,
independent contour transparency, unsupported animation and source-ID reuse with
different text retain ordinary fallback. The foreground's own stroke continues
to use the existing authored-stroke proof.

Some constant-color source planes have synchronized opacity-only header
animation, including instant reveal/hide handoffs. Their full initial opacity,
transform timing, acceleration and target opacity must agree. Fill and contour
opacity must remain coupled and reach an opaque state. Such a shared progression
can supply settled paint evidence without changing the freezer's visibility or
timing decisions. Geometry and color transforms do not gain admission. Independent
or inline opacity animation does not acquire an inferred ownership relation.

All source/parser dictionaries remain borrowed. Settled source views and span
paint buffers are private to this producer invocation; no serialized proof tags,
new cleanup pass, counter or show-specific condition is introduced. Existing stack
admission, removal, layer assignment and geometry proofs retain responsibility for
their contracts. This patch changes representative contour selection within
already admitted stacks, not the scope of redundant content removal.

## Validation and evaluation

`tests/check_stacked_contour_paint.py` checks general opaque ordered stacks,
low-contrast and dark/light gradients, inline splitting, same-layer source order,
width caps, rotation/perspective, shared opacity legs, refusals, source immutability
and full-pipeline repeat conversion. `tests/check_stacked_contour_paint_render.py`
compares output to independently authored single-caption references on black,
gray and white, including visibility boundaries and transformed captions.

`validation/run_ordered_contour_corpus.py` regenerates the eleven local corpus
sources with the same exact fonts as the hash-bound v205 baseline. It checks
source/runtime/font bindings and reports every changed style and statistic.
Private fixtures, fonts, conversions, renders and generated reports stay ignored.

The change extends source paint ownership at its existing producer. Shared
opacity evidence is the related handoff needed for the same captions' reveal and
exit variants. It does not require a downstream exception or a broader API/index
review. A pre-existing English ending caption at 21:59.01–22:04.26 still combines
an earlier full-line phase with later gradient copies after freezing. Its source
opacity handoff deserves a separate phase/visibility investigation; paint
preservation does not prove that the differently painted copies are redundant.
The source's instant opacity handoff occurs about 22:01.58: the earlier whole
line disappears as the gradient glyphs appear. Follow-up should carry that source
phase relationship through freezing and reconstruction; the differing paints
alone do not authorize duplicate removal.

Fresh validation passes all 87 routine regression scripts, including 201 focused
ownership checks and 70 native ordered-contour checks. Runtime and harness inputs
remain unchanged throughout the final run. All eleven corpus conversions use
exact fonts and preserve their source files; ten outputs remain byte-identical
to v205. Demon Slayer changes only its two ending styles and opening translation
style: corrected paint permits more complete rows, reducing dialogue events from
516 to 470 and peak concurrency from nine to five. Its complete output is
byte-identical on repeat conversion. Native original/v205/v206 panels confirm
restored colored outlines for both gradient families. The MKV/font-sync smoke
workflow and the integrated track/property utility suites (64 tests) also pass.
