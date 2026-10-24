# Supporting-drawing reduction — v267

Fifteen existing functions and three existing frozen records, 313 definition
lines, live in `_simplify_ass/supporting_drawings.py`. The shared 26-line
`merge_tiled_clips()` proof lives in the existing `drawing_geometry` module.
Names, signatures, defaults, annotations, comments and bodies move unchanged.
The engine retains direct aliases for all nineteen definitions. Runtime version:
`2026.10.25.267`.

## Boundary and dependencies

The subsystem normalizes drawing candidates, validates held-scale/short entrance
motion, proves complete strip coverage, composes visible paint, reduces identical
layers and compatible frame sequences, and attaches original-contour evidence.
Exact opaque-vector deduplication also retains its existing legacy caller. The
shared clip-tiling proof stays independent of drawing reduction and text-outline
recovery, which both consume it.

Dependencies are existing drawing/caption geometry, strict effect validation,
override interpretation, text freezing, event operations, static identity,
caption rendering and the v266 frame freezer. Imports remain one-way; no private
module imports the engine. The shared helper's unchanged relocation is the only
preparation needed and belongs in this same release. No adapter, callback, record
consolidation, global context, new cache or matching policy is introduced.
Installation/update discovery includes the new source automatically.

## Ownership and data flow

| Resource | Preserved responsibility |
| --- | --- |
| Inputs | Original Events, formatting, styles and source iterables remain borrowed. Normalized candidates are successors made through canonical event replacement. |
| Context | `SupportingDrawingContext` keeps frozen bindings with its existing mutable per-call counters, paint tags and original-contour map. No resource lifetime crosses calls. |
| Proof records | `SupportingDrawingCandidate` and `SupportingDrawingCoverage` preserve frozen bindings and their existing shallow sharing of candidate Events, points, clip groups and rectangle lists. |
| Reduction | Existing geometry admission, compositing order, transparent-area weighting, union masks, source identities and refusal rules remain unchanged. Frame reduction stays restricted to the producer's pose/original-contour families. |
| Evidence and results | Finalization attaches retained original contours to owned successors. The existing `(events, counts)` result and source-index ordering are preserved. Each invocation produces fresh working containers and counters. |
| Callers | Caption association, fallback/backdrop reconstruction, optional budgets, layering, pipeline stage order and aggregate reporting remain in the engine. |
| Fonts and diagnostics | Existing measurement/resource and reporting owners remain unchanged. The reducer creates no font resource or report object. |

The wrapper, CLI and report catalog are unchanged. Other legacy vector reducers
remain outside this boundary. Test interpreter observers follow the defining
consumer, without adding production forwarding.

## Validation

The existing drawing-geometry check also covers canonical subsystem aliases and
annotations, historical record lookup, frozen record bindings, retained strip
masks, composed gradient paint, immutable sources, iterable inputs and independent
repeat-call counters. Cold imports run without the engine or optional font
backends. Installed delivery/removal is exercised in a directory with spaces.
All eleven focused boundary tests pass.

Local evidence lives under `validation/supporting-drawing-extraction/`. The
structure audit compares all nineteen moved definitions and the remaining engine
algorithm against v266. Existing drawing-geometry logic is unchanged apart from
the added shared helper; other existing private sources and the wrapper are
byte-identical. The audit also checks acyclic imports. Runtime manifests cover
all 54 Python sources. Fixtures, fonts, reports and outputs stay ignored local
development assets.

All 121 regression scripts passed, including native caption/backdrop, source-pose,
paint, contour-order, fade/handoff and near-backing rendering. Fresh comparison
of all thirteen corpus tracks against the hash-bound v266 baseline found every
output byte and complete statistics record identical. Exact fonts and source
bytes are unchanged, with no missing required font families. Runtime and
test/harness hashes stayed unchanged throughout validation.
`release-verification.json` binds the structure audit, full regression report and
corpus comparison. Validation uses Pillow BASIC plus real HarfBuzz on Linux,
including native libass rendering; it does not establish native Windows
filesystem/PowerShell behavior.

## After-release evaluation

The boundary preserves candidate/proof/result ownership without downstream
repairs, duplicated proofs or local matching exceptions. The shared geometry
helper has an existing neutral owner. No behavioral issue requiring a dedicated
follow-up review was uncovered.
