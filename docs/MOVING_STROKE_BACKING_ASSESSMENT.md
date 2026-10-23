# Moving foreground/backing assessment

Assessment against v250 (`a4c02d9`), 2026-10-23. Production behavior is unchanged.
The motivating example is Attack on Titan S02E01 track 3, “South Group”, notably
12:08.18–12:08.70. The supplied exact Señor Domingo font is available, including
native verification of the authored bold rendering.

## Finding

Ownership is established for only part of the source sequence. It is not a
complete foreground/backing family whose ownership is subsequently discarded.
Exact grouping rejects slightly different authored positions; the following
stack proof also requires exact layout identity. Consequently some frame pairs
become outlined captions while others remain separate dark and pale planes.

South Group contains 96 simultaneous foreground/backing pairs over
12:05.20–12:09.20. Stack reconstruction collapses 31 pairs and leaves 65 pairs
unmatched: 192 input planes become 161 records. A representative rejected pair at
12:08.16 differs by 0.015 script units in horizontal position, 0.01 percentage
points in horizontal scale and 0.01 degrees in rotation. Its borderless dark
foreground and pale, stroked backing otherwise describe one caption.

Subsequent frame reduction sees separate paint/layer groups. It combines 18 dark
frames over 12:07.87–12:08.74, choosing a supported source pose at y=819. The
backing's changing stroke widths and the mixed reconstructed/unreconstructed
frames prevent equivalent grouping. At 12:08.70 its position is y=862.11. The
result is a detached pale copy below the static dark text. Some other intervals
lose the pale contour instead. The representative-pose selector is choosing
valid supplied evidence; it has not been told these planes belong together.

The responsible boundary is `_prepare_stacked_text_copies()` /
`_prove_stacked_text_paint()`, before `merge_frame_animation()` and
`freeze_vector_sequences()`. Enlarging frame-freezing tolerances or removing pale
copies late would conceal the ownership failure and risk losing real contours.

## Bounded experiment

An ignored, isolated prototype measures a conservative upper bound on glyph
displacement using exact-font extent, translation, scale and 2D rotation. This
tests the useful abstraction: a nearly coincident stroked backing, rather than
independent tolerances for tag spelling. A scale difference can be harmless for a
short word but significant across a long caption.

The experimental allowance is 0.25 units at PlayResY 1080, scaled with the event's
existing unit convention. This is a candidate for implementation, not an approved
global geometry tolerance. Maximum measured bounds among admitted opaque pairs:

| Caption | Pairs | Maximum displacement bound |
| --- | ---: | ---: |
| South Group | 88 | 0.0700 |
| North Group | 88 | 0.2350 |
| East Group | 80 | 0.0200 |
| West Group | 88 | 0 |

Titan Pack and Wall Sina do not require this new borderless-front admission path.
The experiment leaves uncertain/translucent pairs intact.

A complete-scene excerpt with 1,625 source events produces 261 current output
events versus 208 with the experimental pairing; South Group contributes 76
versus 53. Its fill and reconstructed contour then share one representative
placement. Twelve native full-scene renders at 12:07.90, 12:08.18, 12:08.70 and
12:09.00, plus isolated caption renders, confirm the direction. At 12:08.70 the
current pale pixels extend 46 pixels below the dark glyph extent; the prototype
keeps the capped contour approximately 2–3 pixels around those glyphs.

The prototype deliberately makes temporary working geometry agree to exercise
the existing renderer. **That shortcut is not a proposed production handoff.**
Canonical source events remain untouched, but shipping the shortcut would obscure
the distinction between source geometry and accepted correspondence. A real proof
must retain both original planes and explicitly authorize foreground geometry
and backing paint together.

Sixteen isolated synthetic candidate checks cover translation, rotation, scale,
bold, italic, another exact font, font size and caption length, plus refusal for
larger offsets, divergent geometry, masks, projection, independent contour color
and translucency. They test this admission direction, not a completed production
proof. Matching unilateral frame splits, inline spans and complete compositing
safety are not implemented by the prototype.

## Compositing requirement

The existing ordinary stack renderer normalizes output to layer 0 and retains the
lowest source ID. Broader admission must not inherit this unconditionally.
An interleaved synthetic example places independent red text between the pale
backing and dark foreground. The isolated prototype moves 1,183 original dark
foreground pixels behind that red peer. Keeping the foreground layer avoids that
loss in this example, but is not sufficient proof for arbitrary arrangements.

Use original layer/list order and temporal foreground coverage, with existing
measured clearance where appropriate, to decide whether a proposed replacement
preserves independent ink. The existing full-copy order proof contains relevant
logic; share a neutral primitive if useful instead of duplicating it or importing
one processing pass from another. Its output-layer helper cannot be reused
blindly: stack reconstruction retains a lower source ID while taking its geometry
and foreground from an upper plane. Preserve layers or abstain when necessary.

This order qualification belongs in the same release as wider stack admission.
It is directly related safety work, not a reason to redesign the pipeline.

## Proposed next release: v251

1. Extend the stack producer's candidate discovery to nearly coincident stroked
   backings using measured whole-caption displacement. Keep exact layout helpers
   and unrelated matchers unchanged; do not globally round positions or tags.
2. Establish unique foreground/backing ownership from original text spans,
   geometry, paint, timing and compositing evidence. Preserve real source
   geometry, opacity, masks and phase boundaries throughout the proof. Retain
   existing layers when correspondence is incomplete or ambiguous.
3. Feed the accepted foreground geometry and compatible original pose support,
   together with proved backing paint, through the existing caption renderer.
   Keep the two-unit reconstruction cap and source exposure policy. Extend the
   existing matched-fade handoff only when its shared-opacity evidence holds;
   do not relax the general transparency guard or sharp-contour proof.
4. Protect meaningful behavior with exact-font real examples and synthetic
   variations: shared rotation/scale, long captions, divergent geometry,
   differing opacity, masks, frame splitting and independent intervening ink.
   Incomplete cases may remain layered. Verify text, contour, timing, order,
   source immutability and repeat conversion, then run the full regression suite,
   full-track corpus comparison and native rendering of changed examples.

One focused release is justified by the current evidence. No new global context,
pose-selection redesign or late cleanup pass is indicated. Reassess scope if
explicit source correspondence cannot survive the existing stack renderer without
further destructive transformations.

## Evidence and limits

Local artifacts are under ignored `validation/sign-plane-assessment/`:
`trace.json`, `probe.json`, `excerpt.json`, `synthetic.json`, `native.json` and
`order.json`, with scripts and native images alongside them. The fresh full-track
instrumented conversion equals the saved uninstrumented v250 output. The excerpt
reproduces full-track South/East/West output exactly, but not North Group (61
versus 58 events because the excerpt truncates context). North's candidate
measurements therefore do not establish full-track output parity or final
behavior. The production fix still needs complete-track validation.

All 35 engine/private-module source hashes remain unchanged across the probes.
The production wrapper is unchanged. The full 119-script suite and corpus were
not rerun for this assessment; the evidence above is fresh bounded assessment
work, not release certification. No fonts or subtitle assets are published.

Dedicated follow-up: qualify stack compositing order as part of v251. The separate
v250 inter-family barrier-removal/idempotence observation remains separate; this
assessment neither fixes it nor adds evidence about it.
