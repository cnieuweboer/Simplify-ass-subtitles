# Nearly coincident stroked backings — v251

Version `2026.10.23.251` implements the producer-level correction described in
[the moving foreground/backing assessment](MOVING_STROKE_BACKING_ASSESSMENT.md).

## Ownership before pose reduction

Stack preparation now considers a unique pair with the same literal text,
interval, style, actor and margins even when its positions or uniform layout
differ slightly. The existing borderless-foreground/stroked-backing proof checks
paint correspondence. The new measured geometry proof authorizes only a
quarter-unit displacement at PlayResY 1080, scaled with the existing event units.
Its bound includes translation, scale and 2D rotation over the caption's measured
exact-font extent. Long captions therefore do not inherit a short word's scale
tolerance. Exact layout keys and unrelated matchers remain unchanged.

Both original planes and their working handoffs must satisfy correspondence.
Original formatting is resolved into borrowed views rather than adopted in place.
This permits the freezer's decimal position/angle serialization without assuming
its replacement pose is source evidence. Original masks, movement, geometry
transforms, changed layout, uncertain fonts, projection and inline geometry do not
gain this new admission path.

Source intervals and visible-plane opacity must agree. Opacity-only transforms
reuse the existing settled-contour progression proof, and simple `fad` timing
uses the existing strict parser. Different source fades cannot become ownership
evidence merely because freezing selected equal working opacities.
Paint-only source transforms do not disqualify geometry correspondence: the
existing freezer owns their representative appearance. Geometry-changing
transforms still prevent this admission.

Accepted evidence remains local to `StackedTextContext`: borrowed foreground and
backing events, the original source map, span paint, opacity and a proved output layer. Neither event's
geometry is rewritten to satisfy an exact matcher. The producer passes foreground
geometry and compatible source-pose support together with proved backing paint to
the existing caption renderer. Frame reduction can then select one supported
caption pose instead of independently selecting its fill and contour. Source
exposure, representative-pose policy, motion simplification and the two-unit
reconstruction cap are unchanged.

Opaque near-matched pairs use the same ordinary caption renderer as exact stacks.
This preserves the renderer's explicit default blur/surface state through frame
grouping. Using the span-fade renderer followed by early compaction would instead
make equivalent producer routes disagree about absent versus explicit zero state,
blocking frame reduction until a second conversion. A mixed exact/near moving
sequence protects the common handoff; no frame-key exception is needed.

The canonical source-paint resolver still owns contour policy. After geometry
correspondence has been proved, a paint-only view aligns the backing's rotation
with the foreground for that resolver. This does not change source or working
event geometry. An opaque accepted pair can be reconstructed immediately; a
translucent candidate still requires the existing complete shared-fade family
proof and its real opaque support. The general transparency guard remains intact.

## Compositing and shared responsibilities

New admission tries the ordinary normalized layer, then the original foreground
layer, at the retained source slot. Original foreground coverage must preserve
order relative to independent content, or existing exact-font clearance must
prove separation. If neither layer is safe, the planes remain separate. Negative
layers and same-layer list order are included.

The temporal source-order primitive moved unchanged from full-copy cleanup to
`_simplify_ass/caption_clearance.py`, with a direct alias for its existing caller.
Stack reconstruction shares the proof without importing another processing pass.
Measured uniform displacement belongs to `caption_geometry`; font caches remain
with the supplied metrics owner. Candidate grouping, accepted ownership,
reconstruction and aggregate stack-removal reporting remain with the stack
producer. No new pass, global cache or reporting counter is introduced.

## Deliberate limits

This is not general fuzzy caption matching. Multiple competing planes, unilateral
frame splitting and different timing do not acquire ownership through proximity.
Existing exact inline/projective and fade paths retain their responsibilities;
unsupported near-coincident variants stay layered. Trailing overrides also remain
unsupported by measured correspondence: an inert reset can make the cached final
state misrepresent the visible glyph extent. Independently changing paint
or opacity cannot borrow an opaque neighbor without the existing family proof.

The production `simplify_subtitles.py` wrapper is unchanged.

## Validation

Focused behavioral checks live in `tests/check_near_stacked_backings.py` and
`tests/check_near_stacked_backings_render.py`. They cover source/working
correspondence, rounding, measured scale/rotation, width sensitivity, bold/italic,
uncertainty, shared fades, source immutability, independent ink, negative layers,
frame splitting and repeat conversion. Native checks compare against independently
authored single-caption references across backgrounds and timing boundaries.

Fresh full-suite, corpus and native real-example evidence is saved locally under
ignored `validation/moving-stroke-backing/`, with complete engine/private-module
runtime manifests. Fonts, subtitle fixtures and generated images remain local.

The full Attack on Titan S02E01 track reduces from 351 to 301 dialogue events.
Changed records are confined to South/North/East Group in 12:05.91–12:09.20;
other records are unchanged. The complete converted file is byte-identical after
repeat conversion. The scene excerpt also settles in one run (261 to 208 events),
including all four Group signs. Native verification uses the exact Señor Domingo
face: 21 full-track scene frames at seven timestamps and five isolated extent
checks keep South Group's contour 2–3 pixels around its fill, replacing the
previous detached pale copy.

The 13-track v250/current corpus comparison leaves the other twelve tracks
byte-for-byte and statistics-identical. Every conversion checks its input hashes,
exact fonts and complete runtime manifest; corpus fonts remain unchanged.

The full 121-script regression command passes under the Windows BASIC/HarfBuzz
backend on Linux, with all runtime and harness inputs unchanged. The archived
`final-regression-checks.json` and `release-verification.json` identify all 35
engine/private-module sources. Final verification also checks unchanged text/timing
coverage and the production wrapper. This does not claim Windows OS validation.

The focused checks pass 68 behavioral assertions and 27 independent native
comparisons. Six additional moving/jitter/entrance-exit conversions preserve
paint, source inputs, equivalent subdivision and repeat output. A countercheck
using the superseded span-fade rendering handoff fails the mixed-route behavioral
regression, confirming that it protects the actual producer interaction.

## After-release review

The correction extends the existing stack ownership producer and caption renderer.
It adds no show-specific matching, late repair or duplicated source-order proof.
The paint-only rotation view is explicitly authorized by the geometry proof; it
must not be reused as unqualified geometry evidence. Unsupported correspondence
remains a deliberate refusal rather than a downstream workaround.

No new dedicated follow-up review is indicated by the completed validation.

The previously recorded v250 inter-family barrier-removal observation remains a
separate review item. It is not addressed by this foreground/backing correction.
