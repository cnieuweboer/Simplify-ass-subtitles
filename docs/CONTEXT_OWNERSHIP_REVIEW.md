# Measurement context and parser bookkeeping — ownership contracts

Migration reviewed in v162, source-cache follow-up in v163; documentation reviewed for v168.

The completed migration preserves the existing matching and rendering policies.
The v162 review corrected stale contract documentation and test harness paths.
The v163 follow-up resolved its first bounded candidate: authored lyric source
caches and row additions are explicit results, applied by the pipeline owner.
Matching and rendering behaviour remain unchanged. The executable AST audit
bounds the follow-up to three functions and two result records.

## Final ownership contracts

In v236 masked-glyph processing retains local ownership of each freshly opened
font until glyph-set initialization succeeds. Failures close that handle before
ordinary unsupported-outline refusal or interruption propagation. Initialized
handles enter the existing pass cache and close in pass-level `finally`, including
unexpected proof failures. The metrics owner remains borrowed, and per-glyph
negative caching, source ownership and matching results are unchanged. See
[MASKED_FONT_RESOURCE_CLEANUP.md](MASKED_FONT_RESOURCE_CLEANUP.md).

In v235 complete-line jitter processing moved unchanged with its two frozen
records to `_simplify_ass/complete_line_jitter.py`, with direct engine aliases.
Inputs remain borrowed; family/group/removal/replacement state remains local to
one call. Accepted caption objects are shared between the output list and the
explicit word-echo ownership tuple. `_consolidate_text_events()` retains that
handoff, original-source selection, configuration and aggregate frame/stack
counts. Existing paint, source-pose and event replacement owners are unchanged.
See [COMPLETE_LINE_JITTER_EXTRACTION.md](COMPLETE_LINE_JITTER_EXTRACTION.md).

In v233 the complete frame-echo operation and its five frozen records moved
unchanged to `_simplify_ass/frame_echoes.py`, with direct engine aliases. Original
source maps, working frames and measurement context remain borrowed; movement
cache entries stay family-local and removal/replacement buffers stay call-local.
Retained identity, frame lifetime, anchor paint/flags, source-ID counts and
original-list ordering remain unchanged. `_prepare_stacked_text_copies()` retains
stage invocation and aggregate contribution ownership. Test stubs follow the
function's defining owner. See [FRAME_ECHO_EXTRACTION.md](FRAME_ECHO_EXTRACTION.md).

In v232 strict transform/move proof validators moved unchanged to
`_simplify_ass/effect_validation.py`; raw `event_override_tokens()` moved into event
operations. Engine names remain direct aliases. Raw reads create fresh lists and
never resolve formatting or install caches. Supplied parsed-change lists remain
borrowed and retain identity. `OutlineStripEvidence` keeps exact-object-identity
source-token reuse for its family lifetime. Callers retain source maps, allowed
tags, timing opt-ins, proof/measurement caches, diagnostics, counters and stage
placement. See [EFFECT_VALIDATION_EXTRACTION.md](EFFECT_VALIDATION_EXTRACTION.md).

In v231 residual scrolling-track recognition, motion/edge proof and optional
block-local concurrency removal moved unchanged to `_simplify_ass/scrolling_blocks.py`.
Events, styles, continuations, evidence and caller metrics remain borrowed.
Tracks/profiles, common proof intervals, confirmed/removal sets and ordered
per-block diagnostics stay call-local. The frozen match record retains its
mutable list of profile indices. The engine retains the late residual-stage
invocation, configuration, resolution lookup and aggregate counters. See
[SCROLLING_BLOCKS_EXTRACTION.md](SCROLLING_BLOCKS_EXTRACTION.md), including the
separate existing single-use iterator-contract follow-up.

In v230 the four shared layout helpers moved unchanged into caption geometry,
and `state_key()` moved into event operations, with direct engine aliases. All
read supplied resolved formatting without parsing or caching. Their exact,
tolerant, nominal-height and rounded-state contracts remain distinct from
complete-span identity and pose validity. Passes retain indexes, measurements,
evidence, diagnostics and comparison selection. See
[EVENT_COMPARISON_EXTRACTION.md](EVENT_COMPARISON_EXTRACTION.md).

In v229 conservative drawing geometry, alignment/stroke normalization, exterior
sliver removal and bounded contour reduction moved unchanged into
`_simplify_ass/drawing_geometry.py`, retaining direct engine aliases. Working
buffers remain local; document/event inputs remain borrowed. The producer still
stores original-contour returns in its pass-local map and finalization attaches
them after group/sequence reduction. Admission, movement, measured caption
coverage, compositing, counts and stage order remain caller-owned. See
[DRAWING_GEOMETRY_EXTRACTION.md](DRAWING_GEOMETRY_EXTRACTION.md).

In v228 early and final override compaction moved together into
`_simplify_ass/static_compaction.py`, retaining direct engine aliases. Inputs
remain borrowed; buffers are call-local. Early edits use ordinary replacement
invalidation, while final shorter/equivalent edits explicitly retain evidence.
Callers retain all seven invocations, stage order, configuration and reporting.
Test tracing/stubbing follows the defining consumer without production adapters.
See [STATIC_COMPACTION_EXTRACTION.md](STATIC_COMPACTION_EXTRACTION.md).

In v227 complete static-span identity, `StaticSpanSignature` and ordered static
phase merging moved to `_simplify_ass/static_objects.py`, retaining canonical
engine aliases and the frozen record. Parser/group/slot/bounds buffers stay local;
styles/events and supplied metrics remain borrowed. Callers retain both stage
invocations, row eligibility, evidence lifetime and reporting. The existing trace
helper now observes the static-object interpreter consumer. See
[STATIC_OBJECTS_EXTRACTION.md](STATIC_OBJECTS_EXTRACTION.md).

In v226 source-frame exposure, representative-pose selection and compatible
support handoff moved to `_simplify_ass/frame_pose.py`, with canonical engine
aliases. Inputs remain borrowed and working buffers stay call-local; selection
returns an existing candidate. Callers retain candidate admission, initial
evidence capture, route-specific paint selection and diagnostics. The shared
pose-validity key remains in event operations. See
[FRAME_POSE_EXTRACTION.md](FRAME_POSE_EXTRACTION.md).

In v225 resolved event reads, replacement and their pose-validity key moved to
`_simplify_ass/event_operations.py`, with canonical engine aliases. Cache/history
sharing and edit invalidation remain unchanged. Callers retain proof admission,
absolute exposure production/clipping, pipeline transitions and diagnostics.
See [EVENT_OPERATIONS_EXTRACTION.md](EVENT_OPERATIONS_EXTRACTION.md).

In v224 explicit anchors, the inline-layout guard and conservative measured
bounds moved to `_simplify_ass/caption_geometry.py`, with canonical engine
aliases for functions and position patterns. Inputs remain borrowed; font
measurements/caches stay with the supplied metrics owner. Bounds caches, source
versus output extent decisions, adjacency/coverage proofs and diagnostics stay
with callers. See [CAPTION_GEOMETRY_EXTRACTION.md](CAPTION_GEOMETRY_EXTRACTION.md).

In v223 static override/text freezing moved with `FrozenBlock` and its shared
output whitelist to `_simplify_ass/text_freezing.py`, retaining engine aliases.
Stream buffers stay call-local; initial/default/style inputs and source seeds
remain borrowed. Selection passes through unchanged, then freezing clamps its
selected formatting while retaining pre-clamp settled snapshots. Event cache
installation, evidence lifetime and report aggregation stay caller-owned. See
[TEXT_FREEZING_EXTRACTION.md](TEXT_FREEZING_EXTRACTION.md).

In v222 caption paint resolution and rendering moved with the frozen
`SourceCaptionPaint` record to `_simplify_ass/caption_rendering.py`, retaining
engine aliases. Inputs remain borrowed read-only; working state is call-local.
Source-family, timing, geometry, compositing proofs and evidence lifetime remain
producer-owned. No cache or diagnostic owner changed. See
[CAPTION_RENDERING_EXTRACTION.md](CAPTION_RENDERING_EXTRACTION.md).

In v221 document decoding, parsing, resolved views and rendering moved with
`SubtitleDocument` to `_simplify_ass/subtitle_document.py`, retaining engine
aliases. Resolved views still produce independent styles/events/formatting and
borrow source lines/field order. The engine still chooses preparation and
serialize/reparse boundaries; cache/evidence lifetimes and diagnostics retain
their existing contracts. See
[SUBTITLE_DOCUMENT_EXTRACTION.md](SUBTITLE_DOCUMENT_EXTRACTION.md).

In v220 static-state selection and its five existing records moved to
`_simplify_ass/static_selection.py`, with canonical engine aliases. Base/style
buffers and seed snapshots remain borrowed; sample/vote buffers and rotation
search caches remain call-local. The unchanged early result still returns its
input formatting dictionary. Continuation, pose evidence and serialization
handoffs retain their existing ownership. See
[STATIC_SELECTION_EXTRACTION.md](STATIC_SELECTION_EXTRACTION.md).

In v219 the three core event records moved to `_simplify_ass/event_model.py`,
with engine aliases. This changes their defining location; document ownership,
cache installation, replacement/invalidation and measurement policy retain
their existing producer/consumer boundaries.

| Object | Owner / permitted sharing | Lifetime and edits |
| --- | --- | --- |
| Parsed styles | Document owns catalog and each style dictionary; events borrow them read-only | Text preparation shares the catalog. Measurement preparation copies the map and each style. Native values are immutable scalars. |
| Lines and event field order | Parsed document owns lists; prepared documents borrow them read-only | Rendering constructs new lists. Event indices belong to their own parsed document. |
| Event formatting | Cache owner installs a formatting/continuation pair; consumers borrow it read-only | Timing successors may share the dictionary. Formatting edits use a fresh buffer. Empty cache is unresolved. |
| Document measurement | Frozen record shared by document/events | Canvas requires both authored valid dimensions. Wrapping is inactive until measurement preparation; explicit q wins. Replacements retain context unless a phase/document boundary supplies its successor. |
| Parser continuation | Frozen record paired with the formatting it evaluates | Adjacent blocks and literal spans retain history. Branches share immutable snapshots and own formatting copies. Ordered overrides return successors. |
| Evaluation record | Frozen binding, not a frozen dictionary | Complete evaluation/sampling own buffers. `event_evaluation()` borrows a nonempty cache or returns an uncached fresh parse. |
| Selected static state | Selection owns changed formatting; unchanged early return deliberately borrows the input | Selected continuation follows the chosen branch. Paint voting does not invent parser history. |
| Visibility, pose, settled snapshots | Explicit evidence inputs/results, distinct from rendered formatting | Seed containers are copied locally. Existing snapshot dictionaries are borrowed read-only; new snapshots are independent. Replacement evidence follows the existing proof-preservation rules. |
| Sampled frame-pose support (v200) | Immutable event evidence captured before paint normalization | Paint-only successors retain support for unchanged literal/layout/geometry. Timing clips support; interval extension grants no new exposure. Completed phase joins combine compatible support once. Serialization clears it. |
| Pass caches | Font/cache owner or bounded pass context | No new mutable global parser cache. Vector outline fits and negative results remain pass-local; backed pulse continuation map borrows immutable snapshots. |

A frozen `OverrideEvaluation` cannot guarantee immutability of its dictionary.
The same applies to a mutable Event's cache. Copy before applying overrides to
borrowed state; do not edit event defaults or document style dictionaries. These
contracts use ordinary dictionaries intentionally, without copying whole maps
or adding runtime freezing to every pass.

## Parser and replacement rules

`apply_override()` is the sole single-tag implementation. `evaluate_effective_state()`
starts a complete stream with empty history; `effective_state()` is its useful
formatting-only projection. None reset history differs from an explicit empty or
unknown reset. Named resets remain exact and case sensitive. An invalid first
alignment consumes the latch, which survives resets.

Transform evaluation moved to `_simplify_ass/transform_sampling.py` in v218,
with engine aliases. Selection moved to `_simplify_ass/static_selection.py` in
v220; event-cache installation remains with its engine owners.
Transform targets own copies. Independent time samples restart from the same
seed. The sampler's historical commit policy remains explicit: target history
commits only fields already present in the base history, immediately when active,
independently of interpolation weight. Its optimized target/default seed rules
are preserved. Sustained geometry still wins over upright fallback.

Text/style replacement reparses complete replacement text and installs both
cache fields; supplied stale state/history does not override that authority.
Timing/layer/source-ID edits retain history and context. Nonempty resolved
paint/geometry edits retain history unless their branch provides its successor.
An empty state clears history. Formatting/layout replacements invalidate source
proof unless the caller explicitly supplies valid evidence. Reparsing reconstructs
styles, context and continuation; transient row/lyric/evidence state does not cross
serialization.

The v200 sampled frame-pose support has a narrower automatic handoff: paint-only
formatting changes retain it when `_frame_pose_key()` proves unchanged literal,
geometry, layout and measurement context. This does not retain historical contour
or opaque-span proofs. See [REPRESENTATIVE_FRAME_POSES.md](REPRESENTATIVE_FRAME_POSES.md)
for capture, clipping and completed-run ownership.

The v201 inline paint producer resolves corresponding literal ranges with the
existing static-span parser. Its uniform-geometry admission stays separate from
paint ownership. A local frozen set of approved source identities authorizes the
frame merger to match resolved span paint; descendants retain a contributing
identity. This proof does not outlive that merge call or cross serialization.
Original span visibility supplies source exposure before fade restoration. See
[INLINE_PAINT_OWNERSHIP.md](INLINE_PAINT_OWNERSHIP.md).

`dataclass_replace()` is intentionally lower-level: it preserves fields by default
and does not reparse or invalidate evidence. Its production formatting probes
carry corresponding branch/span continuation, retain source history for derived
measurement states, or explicitly use empty continuation for formatting-only
proof records. Callers using it to install a complete parse supply both fields.

## Matching and wrappers

`static_object_key()` includes literal formatting, continuation and document
context. Literal coalescing retains reset/latch distinctions, including absent
versus explicit empty reset and inactive versus explicit mode-zero wrapping.
`state_key()` deliberately continues to ignore parser history and compares
resolved paint/geometry. Event dataclass equality continues to exclude these
internal records. Pre-migration matching regressions verify decisions, rather
than simply dropping the newly typed values during comparison.

The short helpers remain useful:

- `effective_state()` gives formatting-only readers a clear complete-parse API.
- `event_evaluation()` centralizes cache borrowing versus independent parsing.
- `_commit_transform_continuation()` names a nontrivial historical animation rule.
- `_normalize_text_result()` names the intentional serialize/reparse measurement
  boundary, including regenerated indices and cleared transient proof.
- `load_subtitle_events()` retains the established resolved-reader interface used
  by tools/tests. It is unrelated to the removed parser compatibility adapters.

These helpers name distinct parsing, cache or normalization contracts. No surviving
parser compatibility adapter or legacy-key access remains. Docstrings for `Event`,
`OverrideEvaluation` and `apply_override()` state ownership accurately; old documentation claiming
parser bookkeeping still lived inside formatting has been corrected.

## Follow-up status

1. **Authored lyric source cache and row evidence — resolved in v163.**
   Both passes now return source updates and row additions. The pipeline applies
   them before reconstruction/coverage and adopts exact timing-source aliases.
   See `AUTHORED_LYRIC_OWNERSHIP.md` for preservation and opt-in rules.
2. **Simultaneous catalog and text/style replacement.**
   `replace_event()` resolves a text/style replacement against the original event's
   catalog and overwrites supplied defaults. No production caller combines text/
   style replacement with a catalog swap. This preserves prior behaviour, but the
   general API should eventually either explicitly reject that combination or
   define successor-catalog precedence. Treat it as a separate API decision, not
   an incidental cleanup in this behaviour-preserving review.
3. **Backed pulse index payload.**
   `BackedPulseContext.details` and `.continuations` use parallel source-ID keys.
   Producers and consumers agree. Continuation snapshots are immutable; formatting
   dictionaries and transform lists in the payload are borrowed read-only by
   convention. If this index changes, consider one typed payload carrying formatting, transforms, fade and
   continuation. There is no correctness reason to restructure it now.

## Verification and reproducibility

Run `python validation/run_review_checks.py` from the extracted directory. It
executes the current scripts listed in `validation/regression-inventory.json` and
records exits, summaries and runtime hash in `validation/complete-regression-checks.json`. Three rendering
checks perform 115 pixel-identical libass comparisons. The final contract test
performs 2,500 checks over 100 override streams using read-only catalogs/caches,
branch-buffer identity, phase ownership and full-cache/static-key parity.

Additional active checks cover row-reconstruction ownership, frame replacement
order/identity, fade handoffs, complete lyric copies, masked glyphs and translated
phases. Older boundary/reconstruction semantic references remain active through
the established tests. The general pipeline test now compares the complete
current reader representation with the immutable v166 reference; the earlier
formatting/history boundary comparators remain active in their dedicated regressions.

The v162 review restored the standalone fade runner's event-comparison import and
helper inventories needed by the masked/covered runners, which had been missing
from earlier bundles. These remain packaged. The full-copy harness uses its
immutable reference for parser-call tracing; the visibility tests keep their older
semantic reference. Executable assertions remain active independently of docstrings.

The package retains 21 historical extraction/call-trace harnesses for reference,
listed separately in `validation/regression-inventory.json`. They encode earlier
function decomposition, APIs or mutation contracts and are not current test-suite
entry points. Their reusable scenarios feed current semantic tests where listed;
none are reported as successful current runs.

Current full conversions are compared with the preceding release and the saved
v156 baseline from before this higher-level migration. Six fixture reports, logs
and the suite summary exclude only engine identity and duration. README.md records
the current release results. Source inputs are hash-checked. See
`validation/full-conversion-comparison.json` and `validation/structure-audit.json`.

The v163 follow-up adds 7,014 lyric/source/row ownership checks over 740 cases,
with five focused conversions and explicit caller-application/exception checks.

## Historical font measurement follow-up — v164

Release v164 moved reusable font/cache ownership to FontMetrics. At that stage,
row fitting and outline decoding retained FontSpacing; the following releases
completed their extraction. See FONT_METRICS.md.
The catalog/text replacement and backed-pulse index candidates are deferred to
the broader API and pass-local index reviews respectively.

## Historical outline matching follow-up — v165

FontOutlineMatcher now owns the alphabet-specific profiles and unchanged decoder.
Its font owner is the same shared FontMetrics instance; source-specific evidence
and vector fit caches remain in the existing passes. See OUTLINE_MATCHER.md.

## Final font responsibility boundary — v166

FontSpacing is removed. FontMetrics owns font caches; FontOutlineMatcher owns
profiles; row geometry functions borrow FontMetrics explicitly. Passes retain
source evidence, fitting authorization and edit accumulators. An explicit caller
FontProcessingReport retains the original selective discovery and commit sites,
including batch/failure behavior. See ROW_GEOMETRY.md for final contracts.
Deferred catalog/text replacement and pass-local index reviews remain outside scope.

## Original structural plan closure — v167

The three deferred visibility writers from VISIBILITY_OWNERSHIP.md now return
explicit updates. The pipeline applies them; shared-interval rounds retain
pending generated text in a private overlay. The unused SubtitleDocument.raw
member is removed. FINAL_STRUCTURAL_REVIEW.md records final contracts and
verification. Separate API and pass-local index candidates remain deferred.

## Caption/background handoff — v188

`CaptionSupportResult.ownership` owns its list of frozen
`CaptionPanelOwnership` bindings. Each binding borrows its panel and caption
records, catalogs, caches and original-contour evidence read-only. Frozen bindings
do not make those borrowed Event objects immutable. Final layer edits use
successors and return new proof bindings. A hidden panel can survive in proof
context after its output fill is removed, preserving the distinction between
the owned background and an independent card. Rebuilt support associations do
not authorize new ownership. These proofs live only in the support result;
serialization does not persist them or add role flags to Event/font resources.

The v203 stack handoff owns immutable `BackingFadePhase` candidate evidence and
`MatchedBackingFade` paint tuples in its existing pass-local context. The phase
events and original-source map remain borrowed read-only. Only a complete temporal
family with opaque support and compatible compositing authorizes emission.
Source masks, including animated masks removed upstream, remain a veto. The
successor retains the foreground's source pose support; no proof survives
serialization. See MATCHED_BACKING_FADES.md.

The v197 backing-paint handoff borrows the existing font owner and original
backing/foreground states. `SourceCaptionPaint` contains only immutable scalar
paint values; renderer consumers borrow it. Samples are pass-local, replacements
own newly parsed paint tags, and the proof does not survive serialization.

v198 extends `SourceCaptionPaint` with immutable border-width values. Producers
establish contour authority/absence before rendering; the renderer borrows that
proof. Source-aware span serialization and held-glyph matching retain the same
formatting decision. Shadow transfer changes paint origin and invalidates a
foreground proof. No event-history lifetime or replacement-invalidation rule changes.

## Syllable replacement ownership — v205

The existing source lifecycle producer retains disconnected letter endpoints
until whole-syllable replacement and complete-row ownership are proved. Shared
source-ID requirements keep boundary paint donors and multi-letter pulses atomic.
Intermediate poses retain original anchor precision; selected advance scale is
verified before final rendering. No proof crosses serialization, and no late
consumer reconstructs ownership from the simplified output. See
[SYLLABLE_LIFECYCLES.md](SYLLABLE_LIFECYCLES.md). The broader API and pass-local
index reviews remain separate.

The v206 ordered-contour proof reads original corresponding spans before frozen
blur/opacity can erase their meaning. Settled opacity-only source views and
selected paints are private, temporary buffers; source events and parser caches
remain unchanged. The existing stack producer owns emission and removal.
See [ORDERED_STACK_CONTOURS.md](ORDERED_STACK_CONTOURS.md).

The v207 source alternation collector borrows the font owner and original source
records for literal glyph-anchor and compositing proofs. Its sampled visibility
remains on private row successors. The text-stage owner creates one
`LyricBoundaryIndex` before glyph reduction; frame and text-effect mergers borrow
its complete-caption handoffs through recursion without changing the containers.
Ordinary neighboring text supplies context without becoming eligible for edits.
The proof expires before serialization, and reconstruction receives bounded
fragment lifetimes. See [SOURCE_CAPTION_ALTERNATION.md](SOURCE_CAPTION_ALTERNATION.md).

## Caption phase ownership — v209/v210

The source timeline producer owns immutable `CaptionPaintTimeline` bindings,
source identity sets and per-literal paint tuples. The owner Event is borrowed
read-only; neither style catalogs nor source formatting buffers are modified.
The text-stage consumer retains the proof separately from layout reconstruction
and requires complete surviving literal, geometry and interval correspondence.

v210 attaches `CaptionPaintCompanion` bindings for proved outer contours. Their
immutable fill/exposure samples survive earlier sequence merging, which can
otherwise discard underlying source paint. One real source time supplies both
the foreground phase and the companion's underlying fill. The consumer copies
retained events and parsed span state; no shared parser buffer is edited. Source
authority expires at serialization, with ordinary sequential output re-entering
the source proof on repeat conversion. See [CAPTION_COLOR_PHASES.md](CAPTION_COLOR_PHASES.md).

v211's immutable `CaptionPhaseSource` borrows the original record and owns a
separate fade-free paint view plus the actual non-fading core. Only timeline and
companion proofs consume these views; working events, pose dwell and the original
source map remain intact. A fade-only fragment can have an empty core; authority
requires readable support somewhere in each complete paint phase. Source-owned
overlap cutoffs travel on the timeline.
The consumer can replace a complete surviving interval union only under that
proof, without inferring handoffs again from already flattened output. The
existing fade-overlap owner and color-phase producer share one readable-core
clock selector; uniform caption-plane clearance is shared with glow ownership.
