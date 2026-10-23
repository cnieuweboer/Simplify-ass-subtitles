# Fragment-phase row reconstruction — v256

Complete fragment-phase row reconstruction lives in
`_simplify_ass/fragment_phases.py`: twelve functions and the existing frozen
`FragmentPhaseContext` and `FragmentPhaseProfile` records. The shared `TextRow`
and `TextPhaseRowsResult` records live in `_simplify_ass/row_evidence.py`.
All sixteen definitions moved unchanged, including signatures, fields, defaults,
decorators and algorithm bodies. The engine retains direct aliases for every
moved name. Its version is `2026.10.24.256`.

## Boundary and preparation

The processing module owns stationary-fragment admission, exact touching-boundary
indexes, fragment-to-word and same-anchor chain proofs, directional cue grouping,
complete exact-font row fitting, missing-fragment protection, unique ownership
and ordered application. Failed chain proofs remain blockers; a family cannot
turn a missing or competing phase into a partial reconstructed caption.
Terminal readable paint, source intervals, activation cores, source-index ordering
and event reduction counts retain their established meanings.

Moving the two shared records is a small independently useful preparation in the
same release. `TextRow` already connects source collection, paint reconstruction,
effect removal and timing. `TextPhaseRowsResult` is shared by translated-phase,
fragment-phase and glyph-lifecycle producers. The neutral module depends only
on `Event` and the standard library. It introduces no matching policy, cache,
new record or class hierarchy; other contexts/results retain their owners.

Dependencies point from engine to processing to the existing geometry, fitting,
rendering, event, static-state and document owners. There are no private imports
of the engine, callbacks or production adapters. There are no resource-path,
configuration, CLI, report-catalog or batch-wrapper changes. Existing module
delivery discovers both new files automatically. Standalone importing needs
neither the engine nor optional font backends; the shared records do not load
font metrics.

The engine's `_finalize_text_layout()` retains the call after translated phases,
event and sparse-visibility adoption, protected row handoff to overlap trimming,
subsequent reconstruction, level gating and aggregate reporting. Its remaining
executable algorithm is unchanged.

## Data, caches, diagnostics and results

| Resource | Preserved ownership and contract |
| --- | --- |
| Inputs | Events and visibility remain borrowed. Eligibility, word/geometry/position maps and touching start/end indexes belong to one pass. |
| Proof state | Chain profiles, including failed proofs, cue families, proposals, nearby blockers, claims and output buffers remain call-local. No persistent parser or event caches are introduced. |
| Font resources | The supplied `FontMetrics` retains exact-font, shaping and measurement caches. Geometry fitting still owns no caption-removal authority. |
| Diagnostics | The caller supplies and chooses the lifetime of `FontProcessingReport`. Existing fitting calls retain selective missing-face findings; accepted row increments remain at proposal application. |
| Row evidence | `TextRow` remains mutable, with independent default containers and borrowed explicit payloads. Successors retain shallow sharing; derived anchors are fresh lists. Source paint rows, anchors, foreground, virtual/confirmed status, phase cores and owned backing keep their existing contracts. |
| Phase result | `TextPhaseRowsResult` retains frozen bindings and its supplied event/row/delta containers. The caller applies the sparse visibility delta after success; no-op and untouched-event identity remain unchanged. |

Protected row pieces retain the source geometry/timing needed by later overlap
proofs. Reconstruction does not take over timing handoff policy or reinterpret
paint selection. Failure after private caption acceptance does not leak event
or visibility edits into borrowed caller inputs. Diagnostic mutation retains its
existing contract; no new rollback semantics are introduced.

## Validation and provenance

The active visibility check covers admission/refusal, chain lengths and direction,
missing fragments, readonly/lookup-only visibility, sparse deltas, reporting and
failure after private acceptance. It now also protects direct fragment aliases,
resolvable annotations, frozen context/profile bindings and independent imports.
The reconstruction ownership check adds shared-record aliases, old engine-name
class lookup, mutable/frozen bindings, independent defaults, derived-anchor
isolation, borrowed payloads and shallow successors.

Fit doubles and interpreter observers follow the defining fragment consumer;
pipeline observers continue using the engine entry alias. Historical immutable
scope audits are not reactivated to constrain the current hierarchy. Production
contains no forwarding for test spies.

One-release AST evidence verifies unchanged definitions and the remaining engine
algorithm. Every previously existing private module and the batch wrapper is
byte-identical to v255. Fresh manifests and validation results live locally under
`validation/fragment-phase-extraction/`; the runtime comprises 41 Python sources.
Required regression validation uses the Windows font backend (Pillow BASIC plus
real HarfBuzz) on Linux, with native libass rendering checks. It does not claim
native Windows filesystem or PowerShell validation.

Fresh corpus comparison regenerated all thirteen tracks against the hash-bound
v255 baseline. Every output is byte-identical and every complete statistics
record matches. Source files and exact fonts are unchanged, with no missing font
families. Focused checks include 1,170 final-visibility ownership assertions and
75 row-reconstruction ownership assertions with two focused conversions.

All 121 regression scripts passed, including native libass rendering. Complete
runtime and covered harness hashes remained unchanged throughout the run.
`structure-checks.json`, `final-regression-checks.json`, `corpus-summary.json`
and `release-verification.json` retain the fresh evidence.

## After-release evaluation

The extraction preserves one complete reconstruction responsibility. Shared row
evidence has a neutral owner without changing the producers' data flow, and the
engine retains pipeline adoption and reporting. No workaround, duplicated proof,
local exception or new dedicated behavioral review was needed. Previously
documented unrelated issues remain outside this structural release.
