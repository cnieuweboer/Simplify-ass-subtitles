# Development guidance

This project simplifies ASS/SSA subtitles for embedded playback devices. Reduce
karaoke and other complex text effects to static events where source evidence
supports it. Reconstruct individual letters into complete lines when reasonably
provable, retaining representative fill and outline colors and readable timing.
Keep uncertain content when ownership, geometry, timing or exact fonts cannot be
proved; avoid guessing text or substituting fonts.

The production entry point is `simplify_subtitles.py` → `simplify_ass.py`.
Core `Event`, `EventEvidence` and `DocumentMeasurementContext` records live in
`_simplify_ass/event_model.py`, with direct engine aliases. Import those aliases
before dependent factories/defaults. Resolved reads, event replacement and the
shared pose-validity key live in
`_simplify_ass/event_operations.py`, with direct engine aliases. Keep cache/history
sharing and edit invalidation there. Source-frame exposure, support handoff and
representative-pose selection live in `_simplify_ass/frame_pose.py`, with direct
engine aliases and call-local working buffers. Candidate admission, initial
evidence capture, output paint selection, pipeline transitions and reporting
remain with their producers. Keep the canonical pose-validity key in event
operations; do not duplicate it or import the engine from private modules.
Complete-line jitter admission, readable-core/layer ownership and caption
replacement live in `_simplify_ass/complete_line_jitter.py`, with direct engine
aliases for seven functions and two frozen records. Borrow working/original
events, visibility and styles; keep buckets and replacement buffers call-local.
Preserve accepted-caption object identity for the subsequent word-echo proof.
The caller retains pass order, original-source selection and aggregate frame/stack
counts; rendering, paint policy and source-pose support keep their existing owners.
Frame-sequence freezing and its private visible-paint/near-static admission helpers
live in `_simplify_ass/frame_sequences.py`, with direct engine aliases for all
three functions. Borrow Events, inline-paint source proofs and lyric boundaries;
keep grouping, timing components, run buffers and paint lookups call-local.
Preserve independent source-pose and output-paint selection, overlap refusal,
fixed-anchor jitter bounds, source exposure evidence and source-index ordering.
Text-frame merging retains inline-paint normalization and boundary capture;
supporting-drawing reduction retains its pose/contour restrictions. Callers retain
stage order, configuration and aggregate counts. No font resources, persistent
caches or diagnostic owners move here; do not introduce engine imports or test
forwarding in the private module.
Supporting-drawing normalization, motion admission, strip coverage, paint
composition, exact opaque-vector deduplication and sequence reduction live in
`_simplify_ass/supporting_drawings.py`, with direct engine aliases for fifteen
functions and three existing frozen records. Borrow sources; keep candidate
groups, contour maps, paint tags and counters local to one invocation. Preserve
source ordering, original-contour evidence, movement refusal, union clips and the
existing `(events, counts)` result. Callers retain caption association, budgets,
layering and aggregate reporting. Shared `merge_tiled_clips()` lives in
`drawing_geometry`; preserve its mask, gap/overlap bounds and borrowed rectangle
inputs for both drawing reduction and text-outline recovery. No font resources,
persistent caches, report owners or private imports of the engine are introduced.
Interpreter observers follow the defining supporting-drawing consumer.
Caption-support selection, measured ownership, fallback and final layer settling
live in `_simplify_ass/caption_supports.py`, with direct engine aliases for thirteen
functions, frozen `CaptionPanelOwnership` and mutable `CaptionSupportResult`.
Borrow candidate/caption Events and caller metrics; keep bounds maps,
associations and proof lists local.
Preserve the two-result selection API and internal three-result handoff, exact
borrowed caption identity, shared-outline versus measured ownership distinctions,
opaque contour successors and fallback equivalence. Shared `caption_clip_outline()`
lives in `drawing_geometry`, retaining static-mask validation and scene scaling.
Final settling consumes carried ownership, preserves independent masks and updates
successor associations without inventing new claims. Keep `ownership=None`
compatibility distinct from an explicit empty proof list; preserve branch-specific
result sharing and the existing copied duplicate count on the full proof path.
Geometry/normalized-caption caches remain call-local. Callers retain reduction,
budgets, output assembly, late normalization, invocation order and reporting.
Font caches keep their measurement owner. Test measurement mocks follow the
defining consumer without production forwarding or private imports of the engine.
Original-source row collection, opacity-coupling and exact-fragmentation proofs
live in `_simplify_ass/source_row_collection.py`, with direct engine aliases for
three functions and the existing mutable `CollectedSourceText` record. Borrow
source Events, animation membership and metrics. Keep resolved-map successors,
word/position maps, grouping, visibility profiles and anchor buffers local to
one invocation. Preserve authored map keys/order, separate working formatting
from sampled row paint/opacity history, and retain existing shallow style and
document sharing. Source preparation owns timing-map adoption, effect removal,
paint-timeline capture, reconstruction and reporting. Metrics retains fonts,
measurement caches and resource/diagnostic lifetimes. Interpreter observers follow
the defining collector consumer without production forwarding or engine imports.
Exact positioned-duplicate removal, strict whole-lifetime redundancy and early
static-sign paint selection live in `_simplify_ass/text_copy_reduction.py`, with
direct engine aliases for all eight functions. Keep these three admission rules
and their stage roles distinct. Borrow Events, visibility, styles and formatting;
keep parsing state, indexes, ranks, retained anchors and removal sets call-local.
Preserve transparency/collision safeguards, full literal-span identity, wrapping
and intervening-compositing checks, retained-anchor bounds and original order.
Retain source-ID versus list-slot counting as currently defined. Callers retain
lyric handoffs, stage order and aggregate reporting. No font resources, caches,
new records or report owners move here. Interpreter observers follow the defining
copy consumer without production forwarding or private imports of the engine.
Static paint normalization lives in `_simplify_ass/paint_normalization.py`, with
direct engine aliases for `normalize_near_text_colors`, `_bounded_text_color`
and `normalize_shadow_lettering`. Keep their separate admission rules and
invocation points. Borrow Events, styles and formatting; keep palette votes,
blocked channels, continuations and serialization buffers call-local. Preserve
whole-palette bounds, observed-color selection, gradient/transparency vetoes,
reset continuation, exact shadow paint/anchor transfer and canonical replacement.
Producers retain geometry/ownership/source evidence and pose selection; callers
retain evidence requirements, stage order and aggregate reporting. No font
resource, persistent cache, result record or diagnostic owner moves here.
Interpreter observers follow the defining paint consumer without production
forwarding or private imports of the engine.
Source-owned word fade/jitter family proof, exact-font ownership and atomic
removal live in `_simplify_ass/word_echoes.py`, with direct engine aliases for
all five functions. Borrow working events, visibility, the exact accepted-caption
tuple, original sources and metrics; keep owner/family buckets, anchor caches
and removal IDs call-local. Resolve empty source formatting into temporary views
without populating caller caches. Preserve unchanged Event identity, early-return
list identity, whole-family ambiguity refusal, bounded faint tails and unchanged
parent paint/timing. Reuse `CoveredFragmentRemoval` from neutral `row_evidence`
with empty rows and the existing unique-source removal count. The consolidation
caller retains the jitter handoff, stage conditions, adoption and aggregate
reporting. Measurement resources and diagnostics keep their existing owners;
test stubs follow the defining consumer without production forwarding.
Frame-exit echo admission, source-motion/paint proofs and ordered replacement live
in `_simplify_ass/frame_echoes.py`, with direct engine aliases for all functions
and five frozen records. Borrow working events and original source maps; keep
positive/negative movement caches family-local and removal/replacement state
call-local. Preserve both proof paths, anchor paint/flags, frame lifetimes,
source-ID application and original-list ordering. Callers retain stage order,
source selection and aggregate counts. Test stubs must target the defining owner.
Strict source-effect timing validators live in `_simplify_ass/effect_validation.py`;
raw `event_override_tokens()` lives in event operations, with direct engine aliases.
Keep strict validation distinct from permissive freezer parsing. Borrow allowed
sets and supplied parsed-change lists, preserving list identity and caller opt-ins.
The shared upper-endpoint comparisons include only a one-nanosecond arithmetic
rounding allowance; do not round returned values or widen authored timing slack.
Raw token reads return fresh lists without resolving/caching formatting. Family-local
source-token reuse stays with `OutlineStripEvidence` and its exact-object identity;
callers retain source lifetimes, proof state, diagnostic ownership and reporting.
Shared layout comparisons (`text_height`, `placement_key`, `text_layout_key`,
`compatible_text_layout`) live in `_simplify_ass/caption_geometry.py`; resolved
`state_key` lives in event operations, with direct engine aliases. Read supplied
formatting without parsing/caching. Keep nominal height, exact/tolerant layout,
resolved-state rounding, complete-span identity and pose-validity proofs distinct.
Callers retain the choice of comparison, pass indexes, evidence and diagnostics.
Complete static-span identity, the frozen `StaticSpanSignature` record and ordered
static-phase merging live in `_simplify_ass/static_objects.py`, with direct engine
aliases. Keep parsing/grouping/bounds buffers call-local, borrow document inputs
and supplied metrics, and preserve continuation-sensitive identity and actual
list-slot ordering. Callers still own both stage invocations, row eligibility,
evidence boundaries and reporting. Interpreter trace helpers must watch the
defining consumer binding; do not introduce production forwarding for spies.
Event-level early/final override compaction lives in
`_simplify_ass/static_compaction.py`, with direct engine aliases. Keep both modes
and their distinct evidence/origin/blur contracts together. Borrow inputs and
keep serialization buffers local; callers retain stage order and reporting.
Final mode retains evidence only after complete-span equivalence proof. Test
observers and stubs must follow the defining consumer, without production
forwarding.
Conservative drawing geometry and contour normalization live in
`_simplify_ass/drawing_geometry.py`, with direct engine aliases. Inputs remain
borrowed; parsing/normalization buffers stay local. Preserve raw versus scene
coordinates, opaque-cover eligibility, conservative refusal and original-contour
returns. Supporting-drawing producers retain stage order, admission, movement,
measured coverage, evidence attachment and counters. Do not move those owners
or duplicate the canonical `geometry_key()` to close a drawing dependency.
Residual scrolling-track recognition, coherent block/edge proofs and optional
concurrency removal live in `_simplify_ass/scrolling_blocks.py`, with direct
engine aliases. Borrow events and caller metrics; keep tracks, profile indices,
match intervals, removal sets and per-block reports call-local. Preserve measured
edge refusal, spatial voters and block-local concurrency. The engine retains
late-stage placement, configuration and aggregate counters. An existing single-use
iterator exhaustion issue remains a separate contract review; production supplies
lists. Do not silently change that contract during extraction.
Document decoding,
parsing, resolved views and rendering
live in `_simplify_ass/subtitle_document.py`, with direct engine aliases. Preserve
canonical document factories and the shared fallback field list. Resolved views
own new styles/events/formatting while borrowing source lines/field order;
pipeline callers still choose stage transitions and proof-lifetime boundaries.
Reconstructed caption rendering and its source-paint resolver/record live in
`_simplify_ass/caption_rendering.py`, with direct engine aliases. Callers retain
source-family, timing, geometry and compositing proofs; the module borrows those
inputs and preserves the established contrast, contour and shadow-transfer policy.
Merged-row and literal-span serialization also live there. Preserve exact versus
whitespace-insensitive correspondence, override continuation and border/shadow
axis resets. Callers retain row fitting, paint-family proofs and event edits;
test interpreter observers follow the defining rendering consumer.
Explicit caption anchors and conservative measured bounds live in
`_simplify_ass/caption_geometry.py`, with direct engine aliases
for its anchor/bounds functions and shared position patterns. Geometry borrows event inputs and the
supplied metrics owner. Keep font caches, pass bounds caches, source-span extent
proofs and reporting with their existing owners. Preserve
unknown bounds, adjacency distinctions and the separate anchor precisions.
ASS style/override interpretation lives in `_simplify_ass/ass_overrides.py`, with
engine aliases for existing callers. Its recognized vocabulary is independent
of the text freezer's output whitelist. Transform sampling lives in
`_simplify_ass/transform_sampling.py`, depending on the interpreter and standard
library, with direct engine aliases and call-local caches. Static-state geometry
and representative paint selection live in `_simplify_ass/static_selection.py`,
with their five existing records and direct engine aliases. Selection owns its
call-local votes/samples, borrows input evidence and preserves the unchanged-state
identity contract. Source-family admission and pipeline/report
decisions remain in the engine; preserve the explicit continuation contracts.
Text freezing lives in `_simplify_ass/text_freezing.py`, with direct engine aliases
for its frozen result, shared output whitelist and functions. It owns local
stream state and serialization; selectors retain their sampling/evidence work.
Preserve borrowed inputs, canonical continuation/selection identity, the visible-only
bypass and post-selection blur clamping with pre-clamp settled snapshots.
The shared `without_inert_spacing_tail()` normalizer also lives there. Preserve
its unchanged-event identity on refusal, painted tracking, source immutability
and canonical event-replacement invalidation; other trailing tags remain intact.
Source-backed early rotation normalization, adjacent sustained-layout proof and
late upright-pose recovery live in `_simplify_ass/source_poses.py`, with direct
engine aliases for all three functions. Borrow source maps, Events, formatting
and styles; keep hold indexes, candidate layouts and lazy geometry proofs local
to each call. Preserve the early shallow map copy, map order, untouched Event
identity, late no-target list identity, selected paint/timing and canonical
replacement/evidence invalidation. Source preparation and final layout retain
their existing invocation points; covered-fragment matching retains its own
cross-candidate pose cache. Selection/freezing keep their existing owners. No
font resources, diagnostics or counters move into this module. Interpreter
observers follow the defining consumer without production forwarding.
Caption ownership of nested/staggered glyph copies, authored entrance/exit row
proof, scaffold foreground rendering and ordered replacement live in
`_simplify_ass/caption_fragment_copies.py`, with direct engine aliases for six
functions and three existing frozen records. Borrow working events, visibility,
original sources and optional metrics; keep indexes, collision sets, proposals,
private source successors and removal/replacement buffers call-local. Preserve
exact source-object alias rebinding, existing cached Event identity, canonical
replacement/evidence invalidation and row-collection opt-ins. Return source
updates even when no content is removed; the caller retains source/timing-map
adoption before reconstruction, row handoffs and aggregate reporting. Preserve
retained caption text/timing/geometry and proved scaffold foreground paint.
Rendering, geometry and font resources retain their existing owners. Test spies,
interpreter observers, fitting doubles and failure injection follow the defining
consumer, without production forwarding or private imports of the engine.
Original-source layered highlight, translucent particle and repeated flash proofs,
private source resolution, confirmation and paint-family handoffs live in
`_simplify_ass/source_fragments.py`, with direct engine aliases for fourteen
functions and four existing frozen records. Borrow source events, rows, word/
position maps, animation evidence, metrics and reports; retain exact-object
successor rebinding for unresolved Events and independent row containers. Keep
indexes, per-row syllable caches, candidates and removal state local. Preserve
backed-pulse then sliced-text sequencing, historical paint/visibility evidence,
paint-family identity and aggregate counts. The caller retains source preparation,
timing snapshots, row/timeline adoption and reporting. Shared
`static_text_paint_geometry()` lives in `static_objects`: preserve span continuation,
caller-selected paint exclusions and geometry coalescing without editing Events.
Shared `_index_source_fragment_visibility()` lives in `row_evidence`: preserve
borrowed paint-row identity/order, empty profiles and the absent-profile fallback.
Producers retain visibility admission, coverage and paint/timing selection.
Font caches and selective diagnostics keep their existing owners; interpreter
observers, fit doubles, failure injection and handoff spies follow the defining
consumer without production forwarding.
Complete recorded-row covered-fragment proofs, departing/staggered glyph matching,
shadow timing selection and ordered removal live in
`_simplify_ass/covered_fragments.py`, with direct engine aliases for eighteen
functions and the frozen `CoveredFragmentContext`. Borrow events, visibility,
source maps, rows and metrics; keep timing/span indexes, positive/negative shadow
proofs and recovered-pose caches local to one pass. Preserve source-ID removal,
untouched Event identity, row-identity timing proofs and independent successor
containers even with zero removals. The frozen `CoveredFragmentRemoval` belongs
to neutral `row_evidence`, shared with word-echo cleanup. The unchanged
`animated_shadow_painted_source()` validator belongs to `effect_validation`;
covered-fragment and row-reconstruction producers retain family admission and
cache lifetimes. Callers retain stage order, row adoption and aggregate reporting.
Test interpreter observers, exact-fit doubles and failure injection follow the
defining consumer; no production forwarding or engine imports in private modules.
Complete sliced-text strip/hold/exit admission, coverage and paint proof,
proposal arbitration and authored timing live in `_simplify_ass/sliced_text.py`,
with direct engine aliases for sixteen functions and two frozen records. Borrow
input events, catalogs and measurement context; keep resolved source successors,
move/transform lists, indexes, coverage groups and proposals local. Preserve
complete incoming/outgoing coverage, unanimous held paint, pulse ownership,
source-index application, untouched identity and actual list-slot counts. The
source-fragment caller retains isolation, the backing-pulse handoff, row adoption
and aggregate reporting. Shared `rectangle_clip()` reads belong to caption
geometry: preserve source coordinates and refusal without parsing/caching events.
The interpreter observer follows the defining sliced-text consumer.
Complete progressive text-reveal admission, prefix/chain and temporal strip-band
proofs, representative paint and interval reconstruction live in
`_simplify_ass/progressive_reveals.py`, with direct engine aliases for thirteen
functions and three frozen records. Borrow events, visibility history, catalogs
and measurement context; keep profiles, coverage counters, replacements and sparse
deltas call-local. Preserve real gaps, opacity/source-order selection, untouched
event identity and no-family early-return list identity. The existing frozen
`TextVisibilityResult` lives in `_simplify_ass/text_visibility.py`, shared with
full-lyric-copy cleanup, with a direct engine alias. Keep shallow sharing and
accepted equal-value assignments; callers adopt deltas unconditionally before the
next consumer, even with zero removals. The consolidation caller retains stage
conditions, event adoption and reporting. Test fault injection follows the defining
producer; no production forwarding is needed.
Complete overlapping full-lyric-copy clustering, representative paint/caption
selection and sparse visibility handoff live in `_simplify_ass/full_lyric_copies.py`,
with a direct engine alias. Borrow resolved working events and visibility history;
keep groups, original connected components, partitions, removal IDs and replacements call-local.
Preserve original ordering, untouched identity, source-pose support and accepted
equal-value visibility assignments. Discover connected matches between positive-
duration originals before removals; zero-duration records cannot bridge families.
Compare original foreground coverage over each independent peer's lifetime;
lower effect planes do not block continuously covered foreground. Partition when
replacement would cross independent ink in actual layer/list order and measured
clearance cannot prove separation. Recheck original
child families after partitioning. Normalize output layers only when independently
clear or order-preserving. Do not impose family-size/duration caps or require all
members to overlap one anchor. Claim every accepted member once, including the
retained ID; rendered output unions never authorize further removals.
Select text and paint once from the complete accepted original family in stable
source order, retaining its full timing union and compatible original pose dwell.
Use a compatible original as pose reference when selection changes geometry.
Never use an expanded replacement as new overlap/paint evidence or manufacture
dwell across its union span. The existing shared `TextVisibilityResult`
retains its neutral owner. `_consolidate_text_events()` retains stage order,
unconditional delta adoption before frame merging, level gating and reporting.
Selection, rendering, replacement and measurement policy retain their existing
owners. Shared measured clearance and implicit anchor resolution live in
`_simplify_ass/caption_clearance.py`, with direct engine aliases. Borrow caller
metrics and inputs; keep geometry query buffers local. The shared caption-paint
vocabulary belongs to caption rendering. Clearance grants no family/removal
ownership. Test observers target the defining consumer without production forwarding.
The shared original-foreground order primitive also lives in caption clearance;
full-copy cleanup retains its direct alias. Nearly coincident stroked-backing
admission stays with stack preparation, using measured uniform displacement from
caption geometry and pass-local original-plane/paint/layer evidence. Keep original
and working correspondence separate, preserve source geometry and exposure, and
require existing shared-fade proof for translucent candidates. Do not rewrite
source geometry to satisfy an exact matcher or globally relax layout identity.
Complete vector-caption cue discovery, drawing-run and exact-font proofs,
representative paint, caption reconstruction and source-claim arbitration live in
`_simplify_ass/vector_text.py`, with direct engine aliases for fourteen functions
and the frozen `VectorTextFitContext`. Borrow source events, metrics, matcher and
report; keep drawing indexes, inferred cue evidence, successful/refused source
fits and proposal claims call-local. Preserve no-op map identity, untouched event
identity, dictionary insertion order, source-ID application and recovered-caption
counts. The engine retains stage order, configuration, source handoffs and
aggregate reporting. Font measurement caches and reusable decoder profiles retain
their existing owners. Test interpreter observers and fit doubles follow the
defining vector consumer; pipeline spies retain the engine entry alias.
Shared `TextRow` and frozen `TextPhaseRowsResult` records live in
`_simplify_ass/row_evidence.py`, with direct engine aliases. Keep mutable row
bindings, independent default containers, borrowed explicit payloads and shallow
successors unchanged. Producers retain source paint/timing/ownership decisions;
the neutral records introduce no policy or font/cache dependency. Complete
fragment-phase admission, touching-chain/row proof, missing-fragment protection,
unique source ownership and application live in `_simplify_ass/fragment_phases.py`,
with direct aliases for twelve functions and two frozen records. Borrow events,
visibility and supplied metrics/report; keep indexes, successful/failed chain
profiles, blockers, proposals, claims and output local. Preserve terminal paint,
activation cores, source-index ordering, reduction counts and no-op identity.
The final-layout caller retains stage order after translated phases, event/delta
adoption, overlap handoffs and aggregate reporting. Font caches, selective missing
findings and accepted-join commit timing retain their existing owners. Interpreter
observers and fit doubles follow the defining consumer, without production forwarding.
Complete authored translated-phase cue discovery, exact-font movement/entrance/
held backing proof, unique source ownership and caption construction live in
`_simplify_ass/translated_phases.py`, with direct engine aliases for fifteen
functions and four frozen records. Borrow events, visibility and supplied
metrics/report; keep profile/pool indexes and proposals call-local, and positive/
negative span caches cue-local with displacement/travel keys and cache-excluded
model equality. Preserve complete glyph anchors, timing cores, held backing,
reduction counts and no-op identity. The final-layout caller retains stage order
before fragment phases, event/delta adoption, overlap handoffs and reporting.
Accepted-row counter commits stay with proposal application; do not broaden
missing-font diagnostics during extraction. Shared `index_fragment_spans()` and
`matching_fragment_spans()` belong to `_simplify_ass/fragment_spans.py`. Preserve
normalization choices, literal boundaries, repeated/overlapping matches, empty
fragments, uncapped lengths, caller-normalized targets and borrowed-index reads.
These helpers grant no event/removal ownership. Test trace coverage, interpreter
observers and fit doubles follow the defining consumer, without production forwarding.
Complete source glyph-lifecycle admission, letter/whole-syllable phase proof,
readable paint, row fitting, clearance and atomic ownership live in
`_simplify_ass/glyph_lifecycles.py`, with direct engine aliases for five functions
and frozen `GlyphPhaseLife`. Borrow source maps, Events and supplied metrics/report;
keep resolved successors, spatial/obstacle indexes, positive/negative widths,
paths, proposals and claims call-local. Preserve required shared-member ownership,
source paint/timing cores, input-map iteration order, untouched identity and
reduction counts. The source-preparation caller retains pre-collapse timing,
stage order, collection, row adoption and reporting. Font caches and existing
selective missing findings retain their owners; do not add report counters or
change diagnostic lifetimes during extraction. Shared `_faded_cue_is_scrolling()`
is a raw event read in event operations: retain the legacy effect-prefix test,
borrowed formatting and existing caller decisions. Interpreter observers and
fitting doubles follow the defining lifecycle consumer, without production forwarding.
Complete source-backed fade-core derivation, cue-family proof, collision discovery,
cross-lane synchronization and owned-backing timing trims live in
`_simplify_ass/cue_fades.py`, with direct engine aliases for sixteen functions and
three frozen records. Borrow events, row provenance and original source maps;
keep successful/refused source proofs, indexes, groups and replacement buffers
call-local. Preserve protected cores, centisecond-safe cutoffs, original list
ordering, untouched identity and timing-only edits that never extend lifetimes.
The shared readable-core cutoff selector remains canonical for whole-caption
color phases too. Callers retain both pipeline placements, evidence adoption and
aggregate handoff counts. No font resources or diagnostics move into this pass.
Interpreter observers and historical synchronization mocks follow the defining
consumer; pipeline spies retain the engine entry alias without production forwarding.
Complete text-effect sequence grouping, exact-position and scale-trail admission,
representative geometry/paint selection, caption construction and movement/karaoke
handoffs live in `_simplify_ass/text_effect_sequences.py`, with direct engine
aliases for fourteen functions and three frozen records. Borrow events, visibility,
styles, animation/source maps and supplied metrics/report; keep geometry caches,
components, profiles and output buffers call-local. Preserve the existing exact/
scale recursion order, source-index sorting, untouched Event identity and removal
counts. Exact-position recursive calls retain their existing lack of font metrics;
font caches, report lifetime, stage invocation and aggregate counts keep their owners.
Shared `LyricBoundaryIndex`, `_index_lyric_boundaries()` and
`_crosses_lyric_boundary()` live in `_simplify_ass/lyric_boundaries.py`. Capture
surrounding-row evidence before glyph reduction, retaining the same borrowed index
through coalescing, frame/vector merging and both sequence recursion routes.
Construction owns fresh signatures; consumers do not edit or recapture supplied
proofs. Preserve complete-caption versus glyph-boundary decisions and fallback
capture for standalone callers. Interpreter observers and handoff mocks follow
the defining consumer; no production forwarding is needed.
Complete shared-interval row discovery, exact-font/paint/compositing proof,
proposal arbitration, tail retention and ordered application live in
`_simplify_ass/shared_interval_rows.py`, with direct engine aliases for sixteen
functions and four existing records. Borrow events, visibility and supplied
metrics/report; keep eligibility copies, pending visibility, per-round bounds
(including unknown results), actual-order indexes, proposals and edits local.
Preserve original tails, span paint, numeric layer/list order, jointly compatible
slots, generated-ID uniqueness and no-op identity. The final-layout caller
retains stage order, event/delta adoption after success and aggregate reporting.
Shared `positioned_row_geometry()` and `split_positioned_row_runs()` belong to
caption geometry; preserve explicit tolerances, supplied reading order, stable
sorting and borrowed Event identities. Font caches and selective missing-face
diagnostics retain their owners. Test observers and fitting doubles follow the
defining consumer, without production forwarding.
Complete shrinking glyph-row source admission, held-caption/anchor proofs, unique
ownership and terminal-fade handoffs live in `_simplify_ass/shrinking_rows.py`,
with direct engine aliases for nine functions and three frozen records. Borrow
source maps/catalogs and metrics; keep resolved successors, token lists, indexes,
claims and replacements call-local. Preserve held paint, actual gaps, refusal map
identity, insertion order and unique-source-ID counts. Font caches and canonical
replacement/evidence policy retain their owners. `_prepare_source_text()` keeps
its pre-collapse timing snapshot, exact-object formatting adoption, stage order
and aggregate reporting. Shared `nearby_boundary_groups()` lives in
`_simplify_ass/boundary_groups.py`: preserve fixed-boundary bisection, authored
50 ms plus rounding search bounds and borrowed group references. Producers retain
index construction and their separate acceptance rules. Interpreter observers and
fit doubles follow the defining shrinking-row consumer, without production forwarding.
Complete boundary-glyph rotating-entrance/flying-exit classification, ordered literal
and exact-font anchor proof and unique ownership live in
`_simplify_ass/boundary_glyphs.py`, with direct engine aliases for twelve functions
and two frozen records. Borrow working events, visibility, source maps and metrics;
keep resolved source views, indexes, protected IDs and proposals call-local.
Preserve protected absorbed holds, per-phase caption ownership and unique effect
ownership. Return removal IDs; the covered-fragment caller retains application,
row timing handoffs, order and reporting. The strict shared simple-fade read lives
in `effect_validation`; caption-phase and boundary producers retain their distinct
core/duration decisions. Test observers and fit doubles follow the defining
consumer, without production forwarding.
Complete stationary/moving/held-caption chain proofs and replacement live in
`_simplify_ass/moving_glyphs.py`, with direct engine aliases for seventeen
functions and two frozen records. Source/retained events, visible maps and metrics
remain borrowed; resolved successors, indexes, chain evidence and proposals stay
pass-local. Preserve whole-fragment proof without metrics, exact-font glyph fits,
complete recorded exits, shared-owner refusal, source-index ordering and actual
list-slot counts. The text-effect caller retains stage conditions, subsequent
karaoke normalization, exact-position consolidation and reporting. Shared
`literal_font_spans()` reads belong to event operations; supported opaque-text
state validation belongs to effect validation. Preserve their distinct scope and
continuation/borrowed-input contracts. Interpreter observers follow both defining
consumers, without production forwarding.
Complete backed-glyph pulse admission, row/coverage/return proofs, exit handling,
paint selection and ordered replacement live in `_simplify_ass/backed_glyph_pulses.py`,
with direct engine aliases for eighteen functions and two frozen records. Borrow
source events, word/position maps and optional metrics; keep resolved indexes,
continuations, row evidence and proposal/removal buffers call-local. Preserve
shallow record sharing, complete-row/conflict refusal, source-ID application,
original list placement, untouched identity and actual list-length reduction.
The caller retains source-fragment isolation, stage order before sliced text,
row handoffs and reporting. Sampling/rendering and later full-row assembly keep
their existing owners. Interpreter observers follow the defining consumer.
Shared settled-plane paint estimation and complete-row pooling live in
`_simplify_ass/caption_paint_sampling.py`, with direct engine aliases for both
helpers. Events, styles, continuations, plane lists and accepted samples remain
borrowed; raster buffers and accumulators are call-local. Metrics retains font
caches, and `caption_rendering` retains the canonical `SourceCaptionPaint` record.
Keep Pillow lazy and preserve approximation, ordering, bounds and refusal policy.
Glow/backed-glyph producers retain source-family, timing, geometry, compositing
and row-completeness proof, fallback decisions and reporting. Sampling grants no
removal authority. Interpreter observers must include the defining consumer.
Ordered karaoke-completion matching, sweep proof and destination paint replacement
live in `_simplify_ass/karaoke_completion.py`, with direct engine aliases for
thirteen functions and two frozen records. Borrow source/working events,
visibility and supplied outline profiles; keep indexes and replacements call-local.
The outline-strip producer retains its geometry/compositing/paint proof and
profile lifetime. Keep both consumer routes, continuation/timing bounds, untouched
identity and original list order. Callers retain stage conditions and reporting;
this paint operation introduces no removal counter. Interpreter observers must
include the defining consumer, without production forwarding.
Masked-glyph indexing, exact contour/text proofs and ordered replacement live in
`_simplify_ass/masked_glyphs.py`, with direct engine aliases for eighteen functions
and four frozen records. Borrow working events, visibility, animation evidence and
metrics; keep geometry/proof caches and font handles pass-local. Close temporary
handles if initialization fails; register only initialized handles and close them
in pass-level `finally`. Preserve per-glyph negative caching, conservative refusal,
retained identity, source-ID counts and original list order. The caller retains
stage placement and `masked_decorations` aggregation. Test fault injection and
helper coverage follow the defining owner; pipeline observers use the caller alias.
The exact-font measurement owner lives in `_simplify_ass/font_metrics.py`;
the engine re-exports its four classes for existing callers. Exact-font contour
matching and cubic fitting live in `_simplify_ass/font_outlines.py`, depending
only on measurements and the standard library; the engine re-exports both names.
Exact-font fragment fitting and authored glyph placement live in
`_simplify_ass/glyph_placement.py`, depending only on measurements and the standard
library, with direct engine aliases. Event-based row recovery lives in
`_simplify_ass/row_fitting.py`; the shared mutable `FontProcessingReport` lives in
`_simplify_ass/font_reporting.py`, with direct engine aliases. Borrow caller
events, measurements and reports; preserve temporary zero-tracking event views
and their shallow sharing. Keep selective missing-face writes, caller-selected
report lifetimes and the four accepted-join commit sites unchanged. The fitting
module returns geometry only; reconstruction-family proofs, rendering, timing
and event ownership remain with producers. Test doubles follow the defining
fitting consumer. Ship the private package with the engine and preserve
one-way imports and sibling font discovery.
The Windows installer/updater discover private Python sources and persist owned
paths; keep this delivery contract and the older-updater migration documented in
`docs/MODULE_DELIVERY.md`. New modules must not need a delivery filename list.
Preserve this batch MKV workflow and the engine's CLI compatibility. The older
`simplify_ass.bat` / `simplify_ass.ps1` launchers have been retired.
`tests/windows/test_mkv_subtitles.ps1` performs extraction and conversion in one pass.
`tests/windows/test_subtitles_step2_test.bat` / `.ps1` rerun conversion against an existing
extracted cache. Native Windows wrapper behavior requires Windows validation.

Read `docs/DEVELOPMENT.md`, the relevant pass documentation, and
`docs/CONTEXT_OWNERSHIP_REVIEW.md` before changing matching or reconstruction policy.
Current work targets concrete failure cases. Global API and pass-local index
reviews are future work; do not mix broad refactors into a failure-case fix.
Archived release plans and historical validation reports are background evidence,
not new user requests or proof that the current checkout passes.

Follow the user's development principles in `docs/DEVELOPMENT_PRINCIPLES.md`.
Treat show-specific fixtures as evidence of general subtitle concepts, never as
runtime recognition rules. Investigate upstream transformations and clean
handoffs before adding downstream workarounds or another pass. Preserve useful
source context until its consumers finish. Prefer reasonably general structural
proofs to narrow formatting patterns or accumulating exceptions. Use evidence
proportional to the destructive change; do not add restrictions solely for
hypothetical false positives. Keep each pass responsible for a distinct concept,
and justify algorithmic complexity with measured performance gains. Tests should
protect intended text, paint, timing, ownership and compositing behavior;
historical release scope audits must not dictate the future implementation.

After each change, briefly report whether anything was introduced or uncovered
that deserves a dedicated follow-up review. Examples include workarounds, local
exceptions, duplicated logic, unclear ownership, fragile assumptions, or changes
that interact with unrelated subsystems. If nothing stands out, say so briefly.

For a behavior change, reproduce the failure, add or extend a focused existing
check, and verify representative text, paint, timing, source ownership and
idempotence where relevant. Preserve source/cache immutability and document
measurement/parser-continuation contracts. Avoid mutable global parser caches.

Run checks from the repository root with Pillow, fontTools and real uharfbuzz.
Use `python validation/run_backend_check.py --backend windows tests/check_NAME.py` for
focused checks and `python validation/run_review_checks.py` for the current
121-script suite. This exercises Pillow BASIC plus HarfBuzz on Linux; it does not
validate Windows filesystem or PowerShell behavior. RAQM is optional unless the
change affects that backend. Missing fixtures/fonts are prerequisites, not passes.
If a required font is missing, identify its family and variant and request it
from the user before continuing font-dependent analysis or changes.
Keep fresh reports separate from imported historical evidence.
Current runtime evidence must identify `simplify_ass.py` and every Python source
under `_simplify_ass/`; a root-script hash alone is incomplete. Use the manifest
helper in `validation/runtime_manifest.py` and check it before/after validation.

Fonts, subtitle fixtures, generated conversions and reports are local development
assets ignored by Git. Preserve them and the user's media. Do not publish these
assets incidentally with code changes. See `docs/DEVELOPMENT.md` for fixture layout.

Use the existing checkout: cloud tasks are already isolated. Do not create a Git
worktree unless the user explicitly requests one.

When adding production counters, update the shared test-wrapper catalog in
`tests/windows/subtitle_report_helpers.ps1`. Preserve raw track statistics; never
turn unknown/missing counters into genuine zero contributions. Run
`tests/windows/check_reporting.ps1` with PowerShell for wrapper report changes.
