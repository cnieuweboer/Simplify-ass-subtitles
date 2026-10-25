# Final caption-layer settling — v272

Four existing functions and the existing mutable `CaptionSupportResult` record,
143 definition lines, move into `_simplify_ass/caption_supports.py`. They are
`settle_caption_backdrop_layers`, `_rectangle_polygon`, `_same_caption_panel`,
`_covered_caption_panels` and `CaptionSupportResult`. Names, signatures, defaults,
annotations, comments and bodies move unchanged; the engine retains direct
aliases. Runtime: `2026.10.25.272`.

## Boundary and dependencies

The existing module now keeps support selection, measured ownership, fallback and
final application of ownership together. It contains thirteen functions and two
existing records, 422 definition lines. No new module or result abstraction is
introduced. v271 already supplied the shared shadow-normalization dependency.
No separate preparation, adapter, callback or policy change is required.

Final settling depends on the module's existing ownership/containment proofs,
caption/drawing geometry, static identity, event replacement and paint
normalization. No engine-local dependency remains. Imports stay one-way and no
private module imports the engine. Existing module delivery remains unchanged.

## Ownership and data flow

| Resource | Preserved responsibility |
| --- | --- |
| Inputs | Support records, Events, carried ownership and caller metrics remain borrowed. |
| Records | `CaptionSupportResult` retains mutable bindings and unchanged fields/defaults; `CaptionPanelOwnership` retains frozen bindings and borrowed Event identity. No record consolidation occurs. |
| Proof lifetime | `ownership=None` retains compatibility for older direct constructors. An explicitly empty proof list remains authoritative and cannot acquire claims through later reassociation. |
| Local state | Geometry lookups, normalized-caption caches, retained-panel/family maps, drawing order, successors and association buffers belong to one invocation. |
| Layering | Existing measured coverage, full-lifetime support, matching style/actor and ownership authorize promotion. Independent masks, partial supports, adjacency and fullscreen fills retain their existing protections. |
| Coverage | Hidden lower rectangles are removed only by the existing full-lifetime opaque-fill proof; original order, text, paint, geometry and timing remain unchanged except proved layer/duplicate edits. |
| Results/counts | Existing branch-specific shallow sharing is preserved. Early metric refusal adopts the supplied events while sharing other fields. The complete proof path copies the existing count dictionary before recording hidden-support removals. |
| Callers/resources | The engine retains reduction, budgets, output assembly, late normalization, invocation order and aggregate reporting. Metrics retains fonts, measurement caches and diagnostics. No resource/report owner moves. |

The wrapper, CLI, configuration and report catalog are unchanged. Shadow-paint
policy remains in `paint_normalization`; measured bounds and drawing geometry
keep their established owners.

## Validation

The existing drawing-geometry boundary check now passes sixteen tests. Added
coverage protects canonical settling aliases/annotations, historical result-record
lookup, mutable bindings, borrowed input identity, missing-metric result sharing
and absent versus explicitly empty ownership. Cold checkout and installed imports
exercise the moved result and settling entry point without loading the engine or
optional font backends. Existing delivery/removal checks still cover the module
in a directory with spaces while preserving an unrelated private file.

The complete caption/backdrop, current paint, general support and event-evidence
checks retain behavioral coverage. Inactive historical scope/helper-count audits
are not reactivated. Local evidence lives under
`validation/caption-settling-extraction/`. The structure audit compares all five
moved definitions and the remaining engine against v271, verifies unchanged
existing support definitions/algorithm, checks other private sources and the
wrapper byte-for-byte, and verifies acyclic imports. Runtime manifests still
identify 58 Python sources. Fixtures, fonts, generated outputs and reports remain
ignored local development assets.

All 121 regression scripts passed, including all 107 complete caption/backdrop
checks with native rendering of both Sword signs, plus source-phase, paint,
source-pose, fade/handoff, contour-order and near-backing rendering. Fresh
comparison of all thirteen corpus tracks against the hash-bound v271 baseline
found every output byte and complete statistics record identical. Exact fonts
and source bytes are unchanged, with no missing required font families. Runtime
and test/harness hashes stayed unchanged throughout validation.
`release-verification.json` binds the structure audit, full regression report and
corpus comparison. Checks use Pillow BASIC plus real HarfBuzz on Linux, including
native libass; they do not establish native Windows filesystem/PowerShell behavior.

## After-release evaluation

The existing module now owns both support proof and its final application,
without adding navigation boundaries or moving assembly/report orchestration.
The extension introduces no workaround, duplicated proof or matching exception.
No behavioral issue requiring a dedicated follow-up review was uncovered.
