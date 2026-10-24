# Recorded-row covered-fragment processing — v262

The complete covered-fragment operation lives in
`_simplify_ass/covered_fragments.py`: eighteen functions and the existing frozen
`CoveredFragmentContext`, about 600 definition lines. The engine retains direct
aliases for every moved name. Function and record definitions are unchanged;
the runtime version is `2026.10.24.262`.

## Boundary and shared owners

The module consumes recorded authored/reconstructed/virtual rows rather than
rediscovering them. Its departing-glyph and staggered-row matchers prove complete
exit families from source trajectories and exact-font anchors. It then proves
held/animated/shadow copies, derives protected timing from source cues or shared
fades, removes accepted source IDs in original order and returns independent row
successors. Boundary-glyph proof and source-backed upright-pose recovery retain
their existing private owners.

The frozen `CoveredFragmentRemoval` moves unchanged into `row_evidence`, shared
with word-echo cleanup. No fields, types or shallow-sharing behavior change.
The unchanged `animated_shadow_painted_source()` moves into `effect_validation`;
row reconstruction also uses this source-effect predicate. Family admission and
source-proof caching stay with consumers. These small shared-owner moves belong
in this extraction release; no separate policy or preparatory migration is needed.

Imports remain one-way and no private module imports the engine. The module has
no adapters, callbacks, new context abstraction, global cache or report owner.
Existing automatic installation/update discovery includes the new source.
The CLI, configuration, batch wrapper and reporting catalog do not change.

## Preserved ownership

| Resource | Responsibility |
| --- | --- |
| Inputs | Working/source Events, visibility, animation evidence, recorded rows, styles and optional metrics remain borrowed. |
| Context | Row/timing indexes, exact/casefold span indexes, positive/negative shadow-source proofs, shadow layers and recovered poses belong to one removal call. The frozen context still contains mutable local caches. |
| Geometry and fonts | Existing geometry/placement helpers supply proofs. Font resources, measurement caches and diagnostics remain with the supplied measurement owner. |
| Timing | Selected cores are keyed by row object identity. Existing cores survive; a new core requires the existing complete source timing proof. Input rows are never edited. |
| Results | Untouched Events retain identity and order. Row successors have independent pieces, nested paint rows, anchor lists and foreground containers, while borrowing their Events. Row evidence is returned even when no effects are removed. |
| Pipeline | The consolidation caller retains conditions, invocation order, source selection, event/row adoption and aggregate counts. Word-echo cleanup keeps its separate proof. |

## Validation

The ownership check covers source immutability, read-only input maps, independent
successors, repeated row references, protected timing adoption and failure after
timing selection. Extraction checks also cover canonical aliases and annotations,
historical record lookup, shared owner identity, frozen context bindings, borrowed
inputs, per-call positive/negative caches and independent importing/processing
without the engine or optional font backends. It passes 69 assertions.

Interpreter observers, exact-anchor doubles and failure injection target the
actual defining consumer. The existing covered-fragment helper coverage reads
that module's source; pipeline spies continue to observe the engine alias.
These are test-instrumentation updates, without production forwarding.

Fresh release evidence is kept locally under
`validation/covered-fragment-extraction/`. Its structure audit compares all 21
moved definitions against v261, checks the unchanged remaining algorithms and
wrapper, and verifies acyclic private imports. Runtime manifests identify all
49 Python sources. Fonts, fixtures, outputs and generated reports remain ignored
local development assets.

Fresh full-track comparison regenerated all thirteen tracks against the hash-bound
v261 baseline. Every output byte and complete statistics record is identical;
source bytes and exact fonts are unchanged, with no missing font families.
The focused covered-fragment check passes 420 comparisons, six cache assertions
and two conversions; inline continuation passes 51,222 checks.
All 121 regression scripts passed, including native paint, pose, phase,
fade/handoff and caption/backdrop rendering. Complete runtime and harness hashes
stayed unchanged throughout the final run. `release-verification.json` binds the
structure audit, complete regression report and corpus comparison. Validation
uses Pillow BASIC plus real HarfBuzz on Linux, with native libass rendering; it
does not establish native Windows filesystem or PowerShell behavior.

## After-release evaluation

The boundary keeps proof, local caches, timing selection and result construction
together, with neutral owners for the two genuinely shared definitions. No
workaround, local matching exception, duplicated proof or new behavioral follow-up
is introduced. Full-suite and corpus outcomes are recorded with the release.
