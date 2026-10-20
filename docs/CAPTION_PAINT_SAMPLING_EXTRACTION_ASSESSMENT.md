# Settled caption paint sampling — bounded extraction assessment

Implemented in [v239](CAPTION_PAINT_SAMPLING_EXTRACTION.md). The evidence below
describes the historical assessment.

Assessed against v238 (`2026.10.20.238`, commit `aea576a`). Recommended next
release: **v239 — Establish shared settled-paint sampling ownership** in
`_simplify_ass/caption_paint_sampling.py`, with no intended behavior changes.

This is a small preparation for further processing-subsystem extraction, with
an independently useful boundary. It moves the shared computation used by two
existing producers, rather than assigning it to either producer. This assessment
changes documentation only; the isolated prototype and fresh reports remain
under ignored `validation/caption-paint-sampling-assessment/`.

## Boundary and why this step

Move two existing functions unchanged, totaling 91 definition lines:

- `_settled_caption_paint_samples()` estimates subtitle-only settled composited
  paint within an exact-font ink core and a two-unit contour band.
- `_pool_source_caption_paint()` combines accepted glyph/word contributions into
  coherent row paint so glyph thickness does not create inconsistent colors.

Keep `SourceCaptionPaint` in `caption_rendering`, with its canonical engine alias.
Do not introduce a new sample/result hierarchy or context, change the existing
weighted tuple representation, or move ownership proof into the estimator.

The backed-glyph pulse operation currently contains eighteen functions and two
records, totaling 410 definition lines. These two shared helpers are its only
remaining engine dependencies. Moving them into the backed-glyph module would
make glow processing depend on that unrelated processing operation. Copying them
would duplicate the estimator. An independent owner avoids both problems and
leaves a dependency-closed larger operation to reassess after v239.

Keep the estimator separate from caption serialization: it performs bounded,
approximate raster compositing of already-proved planes, while `caption_rendering`
resolves supplied paint and emits ASS. Import the result record in one direction;
the renderer must not import this sampler. Exact-font discovery, shaping and font
caches retain their existing measurement owner. This is implementation specific
to this engine, not a cross-tool `shared/` service.

Other candidates still require their own decisions: sliced-text processing shares
font-span/opacity/clip helpers, progressive reveals share a result record and clip
reading, and shrinking rows share a timing index helper. Do not relocate those
unrelated responsibilities merely to make this release larger.

## Incoming and outgoing dependencies

The incoming callers are `_index_glow_pulse_paint()` and
`_proved_backed_row_paint()`. Both select the foreground, source planes and complete
row before accepting pooled paint. Retain those proofs, source selection, timing,
geometry, overlap/ordering guards and fallback decisions in their current owners.
Keep both helper names as direct engine aliases, preserving signatures and old
root pickle lookup. The helpers' defining module changes naturally.

| Outgoing dependency | Existing owner |
| --- | --- |
| Canonical event annotation | `event_model` |
| Exact face lookup, font bytes/collection index and ASS em scale | Borrowed `FontMetrics` in `font_metrics` |
| Transform replay and override-block pattern | `ass_overrides` |
| Raw source override tokens | `event_operations` |
| Strict source-transform validation | `effect_validation` |
| Canonical `SourceCaptionPaint` result | `caption_rendering` |
| Mask construction, dilation/erosion and blur | Existing function-local Pillow imports |
| Font-byte buffer, arithmetic and text eligibility | Standard-library `io`, `math`, `unicodedata` |

Neither helper needs another engine-defined function. The prototype import graph
is acyclic, with no reverse engine import, callback adapter or production
forwarding. Cold import loads neither the engine nor Pillow/fontTools/HarfBuzz.
Keep Pillow imports inside the sampling function. No `__file__` path logic moves;
font discovery stays with metrics. The now-unused root `BytesIO` import can be
removed during implementation; it has no other root use.

## Ownership to preserve

| Concern | Existing owner and lifetime |
| --- | --- |
| Source data | Events, their formatting/default/style/continuation data and the supplied plane list remain borrowed. Replay transforms on private state copies. Sort local settled-plane pairs, not the caller's list. |
| Proof authority | Callers prove caption family, geometry, source coverage, compositing eligibility and row completeness. A plausible sampled color is not deletion or reconstruction authority. |
| Font caches | Metrics owns face discovery, font-byte and em-scale caches. The sampler borrows that interface and creates local Pillow font/mask objects; it adds no persistent cache or resource owner. |
| Sampling buffers | Resolved settled states, masks, resized ink, core/ring weights, compositing planes and accumulators belong to one call. Preserve current size/blur limits, BASIC layout, shaping refusals, supersampling and approximation policy. |
| Samples | Return the same immutable tuples of weighted core/contour contributions, or `None` for the existing unsupported cases. Callers collect those samples for their row. No event evidence or index is installed. |
| Pooling | Borrow the accepted sample list, construct local totals and return the canonical frozen `SourceCaptionPaint`. Preserve current rounding, alpha bounds and two-unit contour policy. Positive accepted contributions remain a caller precondition; do not add a new fallback or broaden exception handling. |
| Diagnostics/results | No logger, missing-font report, pass counter or visibility result moves. Producers still decide whether to retain their ordinary paint fallback and how accepted paint reaches later reconstruction. |

Preserve equal-layer/source-order compositing, continuation replay, supported
transform fields, refusal/exception boundaries and source-paint normalization.
This release does not change the sampling approximation, authored-outline policy,
whole-caption color-phase settings or ownership rules.

## Preparation and test bindings

V239 is the preparation itself; no earlier production step is needed. Its value
does not depend on a later extraction: two existing callers gain the same clear,
one-way computational owner while retaining their distinct proof responsibilities.
After implementation, reassess the complete backed-glyph operation using the new
owner. Do not design the rest of the final module hierarchy in advance.

The existing interpreter observer should include the defining sampler consumer,
using the established `patch_interpreter_bindings()` helper. This is a test-only
binding update, not a runtime adapter. The prototype verifies six actual transform
replay calls with that observer on each runtime. Existing caller-side observers
can continue to use the engine aliases.

## Fresh evidence and implementation acceptance

Both helper ASTs move unchanged in the prototype. All remaining root definitions
and prior private sources are unchanged. The production 24-source manifest,
tracked tests and all 124 recorded font hashes remain unchanged. Cold import,
resolved annotations, direct aliases, root pickle lookup and canonical result
identity pass.

Current v238 and the prototype each passed:

| Focused check | Result for each runtime |
| --- | --- |
| Proved backing paint, native rendering and repeat conversion | 253 assertions; all 194 captured sampling/pooling decisions identical between runtimes |
| Glow paint, native rendering and real Goblin Slayer source | 309 assertions; all 1,059 captured decisions identical between runtimes |
| Current paint handoffs with actual serialization/exact geometry | 177 assertions |
| Existing effect continuation | 179,958 assertions across 3,144 cases |
| Defining-consumer observer probe | Six actual sampler transform calls observed; sample and call sequence identical |

The 1,253 captured decisions also verify unchanged borrowed event/sample buffers.
The native checks exercise both current/prototype pipelines; this assessment does
not claim a new full-corpus comparison or native Windows filesystem validation.

For implementation, add a focused module contract check covering cold source and
installed imports, canonical result/alias identity, borrowed metrics/inputs,
supported/refused estimation, pooling and independent invocation buffers. Keep
Pillow lazy. Run the full current regression suite and a fresh strict-font corpus
comparison, requiring unchanged bytes and complete statistics. Verify recursive
delivery and the shipped updater's rollback/retry/installed processing/uninstall.
Keep the production batch wrapper, CLI, reporting and delivery policy unchanged.

After implementation, confirm that callers retain ownership proofs and only the
bounded shared computation moved. No new workaround, duplicated proof, unclear
owner or production defect was uncovered. No separate corrective review is needed.
The existing scrolling-iterator contract and deferred global API/index reviews
remain independent work.
