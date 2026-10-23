# Translated-phase caption reconstruction — v257

Complete authored-caption reconstruction across entrances, horizontal movement
and held text lives in `_simplify_ass/translated_phases.py`: fifteen functions
and the existing frozen `TranslatedPhaseContext`, `TranslatedCueLayout`,
`TranslatedCueModel` and `TranslatedCuePhases` records. The shared literal helpers
`index_fragment_spans()` and `matching_fragment_spans()` live in
`_simplify_ass/fragment_spans.py`. All twenty-one definitions moved unchanged,
including signatures, fields, defaults, decorators and algorithm bodies. The
engine retains direct aliases for every moved name. Its version is
`2026.10.24.257`.

## Boundary and preparation

The processing module owns authored comment-cue discovery, unique before/moving/
after source profiles, initial and held glyph-model fitting, entrance and pulse
classification, complete backing/coverage proof, conflicting-neighbor refusal,
source ownership arbitration and caption construction. The touching-fragment
helper moves with its sole processing consumer. Authored spacing, geometry,
representative paint, source timing and activation-core bounds are unchanged.

The shared span helpers are a small independently useful preparation in the same
release. Translated reconstruction, word echoes, source-fragment matching and
covered-fragment removal already use the same literal-boundary algorithm. The
neutral owner depends only on the standard library, creates fresh index data,
and borrows that data during matching. It has no event/font/diagnostic dependency
and grants no reconstruction or removal authority. Keep whitespace removal and
optional case folding at index construction; callers supply normalized targets
and retain their own literal, geometric and ownership proofs. Overlapping matches,
empty recorded boundaries and uncapped text length retain their existing behavior.

Dependencies point from engine to reconstruction to the existing geometry,
glyph-fitting, rendering, freezing, event, row-evidence and document owners.
There are no engine imports from private modules, callback adapters, new records
or context hierarchies. No resource-path, CLI, configuration, report-catalog or
batch-wrapper changes are needed. Existing delivery discovers both new sources
automatically. Independent importing needs neither the engine nor optional font
backends; the literal helpers do not load events or font metrics.

The engine's `_finalize_text_layout()` retains level gating, stage order after
geometry/compaction cleanup and before fragment-phase reconstruction, event and
visibility adoption, protected-row handoff to overlap trimming, subsequent row
reconstruction and aggregate reporting. Its remaining executable algorithm is
unchanged.

## Data, caches, diagnostics and results

| Resource | Preserved ownership and contract |
| --- | --- |
| Inputs | Events and visibility remain borrowed. The per-call context owns movement profiles, eligible phase pools and source-ID indexes that refer to the original Events. |
| Cue model | Each authored cue owns its glyph model and positive/negative span-match cache. Source ID, displacement and travel mode remain distinct cache keys. No matches survive into another cue. Frozen bindings retain the mutable cache and its exclusion from model equality. |
| Temporary proof state | Held/entrance/pulse classifications, coverage evidence, blockers, proposals, source claims and output buffers stay call-local. |
| Font resources | The supplied `FontMetrics` retains face, shaping and measurement caches. No new font service or cache is introduced. |
| Diagnostics | The caller supplies and chooses the lifetime of `FontProcessingReport`. Accepted-row increments remain at proposal application. Missing-font refusal/reporting policy is unchanged; this pass does not introduce new missing-family writes. |
| Results | Existing shared `TextPhaseRowsResult` and `TextRow` retain their canonical owner and shallow contracts. Return retained events, reduction counts, complete glyph anchors, protected cores and sparse visibility updates. The caller adopts the delta after success. Preserve no-op list identity and untouched-event identity. |

Complete held backing remains required, including support beyond movement pulses.
Authored cue text and exact font geometry must account for all glyphs. Persistent
neighbors, incomplete coverage and competing source claims retain their existing
refusal behavior. Independent phase proofs and timing policy keep their owners.

## Validation and provenance

The active translated-phase test retains 138 admission/refusal comparisons and
eight cache assertions. Execution tracing follows the defining module rather than
the engine file; fitting doubles and interpreter observers follow the defining
consumer. No production forwarding is introduced for tests. Existing visibility
checks cover reporting, borrowed inputs, sparse deltas, frozen results and failure
after private acceptance.

Forty-five additional module/boundary checks protect canonical aliases, resolved
annotations, frozen records, cache-independent equality, isolated replacement
caches, full fragment boundaries, repeated/overlapping matches, empty fragments,
Unicode whitespace, optional case folding, literal combining text, long captions,
single-pass inputs, unchanged borrowed indexes and independent imports.

One-release AST evidence verifies unchanged definitions and the remaining engine
algorithm. Every previously existing private module and the batch wrapper is
byte-identical to v256. Fresh runtime/harness manifests and validation results
live locally under `validation/translated-phase-extraction/`; the runtime now
comprises 43 Python sources. Required regression validation uses the Windows font
backend (Pillow BASIC plus real HarfBuzz) on Linux, including native libass
rendering. It does not claim native Windows filesystem or PowerShell validation.

Fresh corpus comparison regenerated all thirteen tracks against the hash-bound
v256 baseline. Every output is byte-identical and every complete statistics
record matches. Source files and exact fonts are unchanged, with no missing font
families. Focused validation passed the 138 translated-phase comparisons, eight
cache assertions, 45 module/boundary checks and 1,170 visibility ownership checks.

All 121 regression scripts passed, including native libass rendering. Complete
runtime and covered harness hashes remained unchanged throughout the run.
`structure-checks.json`, `final-regression-checks.json`, `corpus-summary.json`
and `release-verification.json` retain the fresh evidence.

## After-release evaluation

The extraction preserves a complete reconstruction responsibility with its own
cue-local evidence. Shared literal indexing has a neutral owner while geometric,
paint, timing and source-ownership proofs retain their existing producers. No
workaround, duplicated proof, local exception or new dedicated behavioral review
was needed. Previously documented unrelated issues remain outside this structural
release.
