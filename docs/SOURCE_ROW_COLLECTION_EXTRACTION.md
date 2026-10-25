# Original-source row collection — v269

Three existing functions and the existing mutable `CollectedSourceText` record,
186 definition lines, live in `_simplify_ass/source_row_collection.py`. Names,
signatures, defaults, annotations, comments and bodies move unchanged. The engine
retains direct aliases for all four definitions. Runtime: `2026.10.25.269`.

## Boundary and dependencies

The collector resolves eligible original-source formatting, compares corresponding
row fragmentations and preserves visibility evidence before later transformations.
Its opacity-coupling proof prevents fill visibility from claiming independently
visible outlines/shadows. Exact-font fragmentation matching compares actual glyph
anchors without inventing spacing or fitting a different size.

Dependencies are existing override interpretation, freezing, row evidence, glyph
placement, geometry, strict effect validation and compositing clearance. No
engine-local dependency remains. Imports stay one-way; no private module imports
the engine. No preparation, adapter, callback, new context, record consolidation
or policy change is required. Existing installer/update discovery includes the
new source automatically. Public signatures, including existing parameters, are
preserved without unrelated cleanup.

## Ownership and data flow

| Resource | Preserved responsibility |
| --- | --- |
| Inputs | Source Events, source-map keys/order, animation membership, styles and supplied metrics remain borrowed. |
| Working views | The returned map owns resolved successors where existing eligibility requires them. Source formatting is not populated in place. Existing shallow defaults/style/document sharing is preserved. |
| Row evidence | Sampled row paint and absolute visibility intervals belong to separate row successors; they do not replace the working map's full-cue formatting. |
| Local state | Word/position maps, grouping, profile sets, glyph comparisons, anchor buffers and result containers belong to one invocation. |
| Result | `CollectedSourceText` keeps its mutable bindings and existing four fields/sharing. `TextRow` remains owned by `row_evidence`. |
| Callers | Source preparation adopts the resolved working and timing-map views. Effect removal, paint-timeline capture, reconstruction, stage order and aggregate reporting remain with existing consumers. |
| Measurements | Supplied metrics retains exact fonts, caches, diagnostics and resource lifetimes. The collector creates no font handle or report owner. |

The wrapper, CLI, configuration and report catalog are unchanged. Interpreter
observers follow the defining collector consumer, without production forwarding.

## Validation

The existing source-visibility check retains 207 historical collection
comparisons and now passes 50 ownership/replacement checks. Boundary coverage
protects canonical aliases and annotations, historical result-record lookup,
mutable result bindings, borrowed style/document identity, authored map keys/order,
independent per-call containers/row formatting and source/cache immutability.
Cold checkout and installed imports collect actual rows without loading the
engine or optional font backends. Delivery/removal is exercised in a directory
with spaces while preserving an unrelated private file.

Existing alternating-fragmentation, current paint-handoff and full-copy ownership
checks exercise downstream consumers. Inactive historical scope/helper-count
audits are not reactivated. Local release evidence lives in
`validation/source-row-collection-extraction/`. Its structure audit compares all
four moved definitions and the remaining engine against v268, checks all existing
private sources and wrapper byte-for-byte, and verifies acyclic imports. Runtime
manifests identify all 56 Python sources. Fixtures, fonts, outputs and generated
reports remain ignored local assets.

All 121 regression scripts passed, including native source-phase, paint,
source-pose, fade/handoff, contour-order and caption/backdrop rendering. Fresh
comparison of all thirteen corpus tracks against the hash-bound v268 baseline
found every output byte and complete statistics record identical. Exact fonts
and source bytes are unchanged, with no missing required font families. Runtime
and test/harness hashes stayed unchanged throughout validation.
`release-verification.json` binds the structure audit, full regression report and
corpus comparison. Checks use Pillow BASIC plus real HarfBuzz on Linux, including
native libass; they do not establish native Windows filesystem/PowerShell behavior.

## After-release evaluation

The extraction keeps source-row admission and evidence capture together while
preserving caller-owned timing adoption and downstream effect/reconstruction
responsibilities. It adds no workaround, duplicated proof or matching exception.
No behavioral issue requiring a dedicated follow-up review was uncovered.
