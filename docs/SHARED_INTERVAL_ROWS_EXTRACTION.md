# Shared-interval row joining — v255

The complete shared-interval row subsystem lives in
`_simplify_ass/shared_interval_rows.py`: sixteen functions and the four existing
records `SharedIntervalRowsResult`, `SharedIntervalContext`,
`SharedIntervalProposal` and `SharedIntervalEdits`. Definitions, signatures,
decorators, defaults and matching/reconstruction policy moved unchanged. The
engine retains direct aliases for all twenty names. Its version is
`2026.10.23.255`.

## Boundary and preparation

The module owns candidate grouping, shared-start/end and sweep-window discovery,
exact-font row fitting, timing/paint/compositing proofs, proposal arbitration,
fragment-tail retention and ordered application. The existing four-round limit,
minimum shared interval, source eligibility and refusal rules are unchanged.
Per-span paint remains attached to the corresponding text, and original tails
retain the visibility outside the reconstructed row's shared interval.

Two unchanged shared helpers, `positioned_row_geometry()` and
`split_positioned_row_runs()`, move into the existing `caption_geometry` owner.
They are also used by other row reconstruction paths. Geometry validates the
supplied reading order and groups positioned candidates; callers retain admission,
font fitting and timing decisions. Explicit horizontal tolerances, minimum-height
vertical/gap bounds, stable tied-anchor sorting and borrowed Event identities
remain unchanged. This independently useful 35-line preparation is included in
this extraction release because it needs no new contract or policy.

The engine's `_finalize_text_layout()` retains invocation order, eligibility
inputs, event adoption, visibility-delta adoption and aggregate reporting.
Dependencies point from engine to shared-interval processing to existing event,
override, geometry, rendering, fitting and font owners. No private module imports
the engine. There are no callback adapters, new contexts or result hierarchies,
resource-path changes, CLI changes or delivery filename lists. The batch wrapper
is unchanged. Standalone importing requires neither the engine nor optional font
backends.

## Data, caches, diagnostics and results

| Resource | Preserved ownership and contract |
| --- | --- |
| Source events and visibility | Borrowed. The pass builds a `ChainMap` overlay over caller visibility and returns sparse updates, without modifying the caller map. Source-history entries remain available. |
| Eligible sources | A pass-owned copy, extended for generated events between rounds. |
| Geometry and order | Fresh per-round bounds cache, including unknown results, and layer/list-order indexes. Original inline stroke/shadow/blur extents remain part of measured footprint proof. |
| Proposals and edits | Per-round buffers. Frozen context/proposal bindings retain their existing shallow sharing; mutable edits own independent default containers. |
| Font resources | The supplied `FontMetrics` retains exact-face, shaping and measurement caches. |
| Diagnostics | Existing fitting calls write selective missing-face findings to the caller's optional report. Caller chooses its lifetime; accepted-font-join counters elsewhere remain unchanged. |
| Results | Existing frozen result: events, rows joined, tails retained and pending visibility updates. The caller applies updates only after successful completion. No-font/no-op paths and untouched events preserve their established identity contracts. |

Compositing checks retain numeric layer comparisons and actual original list
order, including compatibility between jointly accepted rows. Generated tails
and rows retain unique IDs and original placement slots. Private acceptance
followed by failure does not leak pending edits or visibility into caller inputs.

## Validation

Active behavioral coverage protects text multiplicity across every original/new
boundary and midpoint, tail lifetimes, per-letter paint, source identity, safe
compositing slots, interleaved content, borrowed visibility and multi-round
handoffs. New checks protect direct module aliases, resolvable annotations,
existing record mutability, independent edit buffers and standalone imports.
Test observers and fitting doubles target the defining consumer; pipeline spies
retain the engine entry alias. Production has no test forwarding.

One-release AST evidence verifies unchanged moved definitions and unchanged
remaining engine/geometry algorithms. Other existing private modules and the
batch wrapper are byte-identical. Fresh runtime/harness manifests and full-suite
and corpus results are kept locally under
`validation/shared-interval-extraction/`; the runtime now comprises 39 Python
sources. Validation uses the Windows font backend (Pillow BASIC plus real
HarfBuzz) on Linux, including native libass checks; this does not claim native
Windows filesystem or PowerShell validation.

Fresh corpus comparison regenerated all thirteen tracks against the hash-bound
v254 baseline. Every output is byte-identical, every complete statistics record
matches, source files and exact fonts are unchanged, and no font families are
missing. Focused checks include 28 row-geometry assertions, 235 shared-interval
assertions, 1,154 final-visibility ownership assertions and 51,222 inline
continuation assertions.

All 121 regression scripts passed, including the native libass checks. Complete
runtime and covered harness hashes remained unchanged throughout the final run.
`final-regression-checks.json`, `structure-checks.json`, `corpus-summary.json`
and `release-verification.json` retain the fresh evidence.

## After-release evaluation

The extraction preserves a complete processing responsibility and its pass-local
state. Shared geometry has an existing appropriate owner, while the engine keeps
pipeline and reporting decisions. No workaround, duplicated proof, local
exception or new dedicated behavioral follow-up was needed. Previously documented
unrelated issues remain outside this structural release.
