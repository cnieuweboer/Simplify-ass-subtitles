# Complete glyph-lifecycle reconstruction — v258

Complete source glyph-lifecycle reconstruction lives in
`_simplify_ass/glyph_lifecycles.py`: five functions and the existing frozen
`GlyphPhaseLife` record, about 494 definition lines. The shared raw legacy-scrolling
read `_faded_cue_is_scrolling()` lives in the existing `event_operations` owner.
All seven definitions moved unchanged, including signatures, defaults, fields,
decorators and algorithm bodies. The engine retains direct aliases for every
moved name. Its version is `2026.10.24.258`.

## Boundary, preparation and benefit

The processing module owns source-family admission, exact-font glyph anchors,
entrance/highlight/exit path proofs, whole-syllable replacement bridges, readable
paint selection, complete row fitting, clearance, unique source ownership and
ordered replacement. Ordinary letter lifecycles and syllable replacements keep
their shared final row/claim proof. Unknown nearby text remains evidence against
partial reconstruction; shared replacement phases require complete row ownership
before any source is consumed. Authored geometry, color dwell, contours, timing
cores and refusal bounds are unchanged.

Moving the three-line scrolling classifier is an independently useful preparation
included in this release. It reads only the event's legacy effect prefix and is
already used by several paint, phase and fade consumers. Event operations owns
raw event reads. Existing names/aliases and admission decisions remain unchanged;
the read does not resolve formatting or grant removal authority. This avoids a
new module for one tiny helper or a dependency on another processing subsystem.

One new processing module isolates a substantial, complete proof-and-replacement
algorithm behind its single production entry point. Keeping its five functions
together reduces unrelated code in the engine without adding navigation between
its internal stages. No further splitting of this subsystem is needed. The
extraction follows the established pattern of borrowed inputs, local evidence,
shared foundation modules and caller-owned pipeline adoption.

Dependencies point from engine to lifecycles to existing event, geometry, font,
fitting, selection, rendering, timing-validation, clearance and row-evidence
owners. No private module imports the engine. There are no adapters, callbacks,
new records, context hierarchies or global caches. No resource paths, configuration,
CLI options, batch-wrapper behavior or report catalogs change. Existing delivery
discovers the new source automatically. Independent importing needs neither the
engine nor optional font backends.

## Data, caches, diagnostics and results

| Resource | Preserved ownership and contract |
| --- | --- |
| Inputs | The source event map and its Events, formatting, continuation and evidence remain borrowed. Resolution and canonical anchors use successors without populating borrowed partial caches. |
| Indexes and proof state | Family profiles, spatial indexes, rejected obstacles, endpoints, lifecycle paths, row proposals and ownership claims remain local to one call. |
| Width cache | Positive widths and failed `None` results remain local to source indexing. Measurement refusal does not survive into another reconstruction call. |
| Font resources | The supplied `FontMetrics` retains exact-face, shaping and measurement caches. The pass does not own font-handle lifetime. |
| Record | Frozen `GlyphPhaseLife` retains its source-member tuple, pose, timing core and immutable required-member set. Shallow sharing is unchanged. A shared syllable's required source IDs must belong to the whole accepted row. |
| Diagnostics | The caller supplies and chooses the lifetime of `FontProcessingReport`. Existing indexing/fitting missing-family findings accumulate there. No new accepted-join counter or rollback semantics are introduced. |
| Results | Existing `TextPhaseRowsResult` retains events, removal count, rows and visibility data. Ordered application preserves input-map iteration order, untouched Event identity and replacement slots. The caller retains adoption and source collection. |

`_prepare_source_text()` retains level gating, stage order after shrinking rows,
its pre-collapse timing snapshot, source collection, row adoption, subsequent
fragment processing and aggregate effect counts. Its executable body is unchanged.
Source collection continues deriving the visibility evidence it needs from the
adopted working events; no new delta-adoption boundary is inserted.

## Validation and provenance

The active glyph-lifecycle check retains synthetic admission/refusal and actual
opening conversion/idempotence coverage. Added assertions protect canonical
aliases and resolved annotations, old engine-name class lookup, frozen record
bindings and borrowed members, exact legacy-effect classification without parsing,
caller-owned findings, retry after measurement refusal, source immutability,
untouched identity/order and independent importing. Existing syllable tests cover
required shared ownership, intentional gradients, intervening content, source
ordering, timing boundaries and real ending conversion.

Interpreter observers and fitting doubles follow the defining lifecycle consumer;
pipeline spies retain the engine entry alias. Production has no forwarding for
test spies. Historical immutable scope audits are not reactivated to constrain
this module boundary.

One-release AST evidence verifies all unchanged definitions and the remaining
engine/event-operations algorithms. Every other existing private module and the
batch wrapper is byte-identical to v257. Fresh manifests and validation results
live locally under `validation/glyph-lifecycle-extraction/`; the runtime comprises
44 Python sources. Required validation uses the Windows font backend (Pillow BASIC
plus real HarfBuzz) on Linux, including native libass rendering. It does not claim
native Windows filesystem or PowerShell validation.

Fresh corpus comparison regenerated all thirteen tracks against the hash-bound
v257 baseline. Every output is byte-identical and every complete statistics
record matches. Source files and exact fonts are unchanged, with no missing font
families. The expanded active glyph-lifecycle test passed 113 checks, including
21 real opening captions and repeat-conversion stability.

All 121 regression scripts passed, including native libass rendering. The full
160-case syllable lifecycle check retained sixteen real ending captions and
repeat-conversion stability; native lifecycle rendering also passed. Complete
runtime and covered harness hashes remained unchanged throughout the final run.
`structure-checks.json`, `final-regression-checks.json`, `corpus-summary.json`
and `release-verification.json` retain the fresh evidence.

## After-release evaluation

The boundary keeps both lifecycle routes and their final atomic ownership together.
Shared event metadata has an existing owner, and pipeline/source-history handoffs
stay with the engine. No workaround, duplicated proof, local exception or new
dedicated behavioral review was needed. Previously documented unrelated issues
remain outside this structural release.
