# Caption rendering — bounded extraction assessment

Historical assessment of v221. Implemented in
[v222](CAPTION_RENDERING_EXTRACTION.md); the evidence below describes the assessment.

Assessed against v221 (`2026.10.18.221`). Recommend **v222: extract the existing
caption rendering boundary into `_simplify_ass/caption_rendering.py`**, retaining
direct engine aliases. One implementation release should suffice; no preparatory
production release or behavior change is proposed.

Production, tests, the batch wrapper and delivery code are unchanged by this
assessment. The isolated prototype and fresh evidence remain private under
`validation/caption-rendering-assessment/`.

## Recommended boundary

Move these five existing definitions together, unchanged:

- `SourceCaptionPaint`, retaining its frozen fields and default border tuple;
- `MAX_PROVED_CAPTION_BORDER`, retaining the two-unit reconstruction cap;
- `render_tag()`;
- `_source_caption_paint()`;
- `render_simplified_caption()`.

Their definitions, decorators and constant assignment total 153 lines. This
boundary owns resolving already-selected compatible contour evidence and
rendering a reconstructed caption from that evidence. It includes the current
uncertain-paint contrast fallback, source-paint override and bounded off-canvas
foreground-to-shadow paint/position transfer. It is not merely a formatting-only
helper: preserve those existing rendering decisions as one unchanged function.

Keep source-family selection, span correspondence, geometric/timing proofs,
compositing clearance, matched fades, row assembly, replacement and emission in
the engine. Moving the paint resolver does not transfer these producer proofs.
`render_tag()` also serves ordinary tag serialization outside reconstruction;
keep its behavior independent of caption reconstruction policy.

## Incoming and outgoing dependencies

Incoming uses include lyric reconstruction, inline paint normalization,
frame-echo reduction, stacked text, matched backing fades and row rendering.
Paint producers construct `SourceCaptionPaint`; `BackingFadePhase`,
`MatchedBackingFade` and `CaptionPaintTimeline` annotate it. Freezing, lyric
coalescing and vector processing also use `render_tag()` independently.

The new module needs only standard-library dataclasses, `math`, `re` and
`typing.Iterable`, plus the existing interpreter's `DEFAULT_STATE` and the
canonical `DocumentMeasurementContext` record. No font backend, selector,
event replacement helper, document I/O, pipeline or engine import is required.
There are no filesystem paths or `__file__` references to relocate.

Dependency direction is engine → caption rendering → interpreter/event model.
Existing private modules need no source changes. Import all five canonical
aliases before dependent engine declarations and defaults. Keep the renderer's
measurement default and the source-paint record's field order, frozen behavior,
signatures and default values unchanged. Ordinary new pickles naturally identify
the private defining module; engine aliases retain historical class-name lookup.
Do not add wrappers or rewrite `__module__`.

## Ownership retained by the move

| Data or responsibility | Preserved owner and contract |
| --- | --- |
| Selected source family | Caller proves correspondence, timing, geometry and compositing, then supplies the complete compatible state family. The resolver does not discover event families. |
| Input formatting and layout | Resolver and renderer borrow input dictionaries/context read-only. They create local merged dictionaries, contour sets and output buffers. They do not install state on events or consume evidence. |
| Paint proof | Resolver verifies the existing contour compatibility rules and returns immutable scalar/tuple `SourceCaptionPaint`, or `None` when evidence is incomplete. Preserve low-contrast authored contours, independent contour alpha, borderless evidence, coupled fade settlement and the two-unit cap. |
| Caption rendering | Renderer owns serialized output and its existing reconstruction policy. Explicit source paint bypasses uncertain-paint contrast repair. Shadow transfer invalidates the foreground proof before rendering; retain that responsibility in the same function. |
| Source evidence and results | Producers retain their source-span, geometry, fade and paint-timeline evidence. Event/result dataclasses and source-proof lifetime decisions stay at current stage boundaries. The moved renderer returns the same string. |
| Caches and diagnostics | There are no persistent caches, counters or diagnostic accumulators in this group. Font caches, pass indexes, cache installation, conversion reporting and event replacement remain with current owners. |

## Is independent preparation useful?

No preparatory production change is needed. The interpreter and measurement
context already provide the required independently importable dependencies.
Moving the short tag serializer and cap with their consumer closes the graph;
separate utility/constants modules would not resolve another dependency here.
No callback adapter, engine import or model consolidation is warranted.

Text freezing remains a closed alternative: six functions, `FrozenBlock` and
`SAFE_SIMPLE_TAGS` total 213 definition lines. It depends on the interpreter and
static selector, and would require retargeting nested selection/freeze test
observers to their actual owners. Caption rendering is the cleaner next seam,
with fewer observer adjustments and a useful dependency for future processing
extractions. No test observer correction was needed in this prototype.

Event-based exact-font row fitting still reaches engine position parsing and a
cross-pass font report. Do not relocate that report into a row-specific module
or inject callbacks merely to close an extraction. Larger echo/effect subsystems
still need replacement, rendering and layout dependencies. Reassess the next
boundary after this move rather than fixing the final hierarchy now.

## Prototype evidence

The isolated whole-engine prototype moves all five definitions unchanged and
imports aliases before dependent declarations. Moved ASTs and the remaining
engine executable AST match; all existing private source files are byte-identical.

Cold import loads neither the engine nor optional font packages. Canonical
aliases, runtime annotations, measurement default identity, frozen paint and
ordinary/legacy pickle lookup pass. Focused probes also verify borrowed-input
isolation, capped/borderless/translucent contours and foreground-proof
invalidation during shadow transfer.

Eight existing scripts run against both baseline and prototype, without test
source substitutions: measurement context, frozen-block results, event-model
identity, matched backing fades, backed-paint rendering, contrast-fallback
rendering, outline-policy rendering and inline-paint ownership rendering.
All **16 executions passed**, with no test source substitutions.
The native libass rendering checks use the available exact Volkhov Regular face.
The event-model script's installed subtest exercises the actual v221 checkout,
so it is not delivery validation of the proposed module.

The production manifest remains identical to the validated v221 release.
Full regression and corpus conversions belong to implementation acceptance,
not this documentation-only assessment. Local evidence includes `audit.json`,
`assessment.json`, `checks.json`, `identity.log`, drivers and paired logs.
Linux Windows-backend validation does not establish native Windows behavior.

## Proposed v222 acceptance and evaluation

Extract the bounded group unchanged, retain direct aliases and add focused
module/import/installed-use checks. Preserve source borrowing, canonical record
and default identity, alpha/contour policy, shadow transfer and ordinary tag
serialization. Keep the batch wrapper and generic delivery code unchanged.

Run the full current regression suite and fresh baseline/current corpus
comparisons, requiring identical output and complete statistics. Verify installed
use from an unrelated directory, updater discovery/rollback/uninstall and full
Python/PowerShell runtime manifests. Record native Windows skips separately.

After release, confirm that source-family proofs and evidence lifetime remain
producer-owned while the module owns paint resolution and rendering. This
assessment required no adapter, duplicated proof, new cache owner or local
exception. No dedicated corrective review emerged; the deferred global API and
pass-local index reviews remain separate work.
