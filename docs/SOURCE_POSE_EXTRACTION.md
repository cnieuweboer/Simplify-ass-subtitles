# Source-backed upright-pose recovery — v261

The three source-pose functions live in `_simplify_ass/source_poses.py`, about
188 definition lines. Their signatures, defaults, annotations, comments and
algorithm bodies moved unchanged. The engine retains direct aliases for every
moved name. Its version is `2026.10.24.261`.

## Boundary and dependencies

`normalize_animated_rotations()` exposes proved oscillating text as upright
source rows before reconstruction, preserving paint animation. Moving/resizing
text and one-way entrances/exits keep their existing later selection routes.
`adjacent_sustained_geometry()` proves a short phase's layout from a touching,
longer source hold. `prefer_surviving_upright_poses()` recovers readable geometry
for intact retained text after effect cleanup, preserving its selected paint
and timing. The existing priority of a caption's own sustained geometry over
adjacent evidence remains unchanged.

These early and late uses of one source-backed orientation policy share their
held-layout proof. Keeping them together makes that policy easier to inspect
without unrelated reconstruction code. No preparatory production change is
needed. The higher-level module consumes existing override interpretation,
freezing, transform sampling, static selection, geometry, rendering and canonical
event replacement. Imports are acyclic; no private module imports the engine.
Independent importing needs neither the engine nor optional font backends.

No adapter, callback, context class, result record, global cache or policy change
is introduced. Existing records keep their owners and mutability. No CLI,
configuration, batch wrapper, resource path or report catalog changes. Automatic
module delivery includes the new source without another filename list.

## Ownership and results

| Resource | Preserved responsibility |
| --- | --- |
| Source and working inputs | Maps, Events, formatting, continuation, styles and historical evidence remain borrowed. Proof and application do not mutate source caches. |
| Early result | A shallow new dictionary retains input-map iteration order. Untouched Events retain identity; accepted text edits use canonical replacement and its existing evidence invalidation. |
| Adjacent proof | Hold indexes, sampled boundary layouts and unique-layout options remain call-local. Each call returns fresh geometry dictionaries. |
| Late result | The original working list is returned when there are no targets. Otherwise output keeps input order and untouched Event identity; accepted successors retain current literal text, paint, timing and layers. |
| Lazy geometry evidence | The late helper constructs adjacent proof only when needed and reuses it within that call. It introduces no cross-call cache. |
| Covered-fragment cache | `CoveredFragmentContext.shadow_poses` remains with its caller, retaining its existing per-candidate source-pose reuse. |
| Resources and reporting | The module owns no font handles, measurement caches, report objects or counters. Pipeline callers retain adoption and reporting. |

The source-preparation caller retains early normalization at its existing point.
Final layout retains late recovery after source-effect cleanup, using the same
original source map. Covered-shadow-fragment matching invokes the same recovery
policy when it needs a candidate pose, then stores that result in its own local
context. All three caller bodies are unchanged. Selection and freezing retain
their existing source-evidence and geometry/paint responsibilities.

## Validation

The active upright-priority check retains sustained-layout priority, ambiguous
holds, short/hidden/clipped/unrelated evidence, entrance/exit recovery, source
paint/timing and actual source examples. Added checks protect direct aliases,
resolved annotations, early normalization's paint animation and refusal cases,
source immutability, map order, untouched Event identity, no-target list identity,
call-local geometry proof and independent importing. It passes 62 assertions.

The focused pose-evidence check passed 2,592 continuation comparisons and 24
ownership/boundary assertions. Interpreter observers follow the defining
source-pose consumer; pipeline spies still target the engine entry alias.
Production has no forwarding for test instrumentation.

One-release AST evidence verifies all three unchanged functions and the unchanged
remaining engine algorithm. Every existing private runtime source and
`simplify_subtitles.py` is byte-identical to v260. Runtime manifests cover all
48 Python sources. Fresh local evidence lives under
`validation/source-pose-extraction/`; fonts, source fixtures and generated outputs
remain ignored development assets.

Fresh full-track comparison regenerated all thirteen tracks against the
hash-bound v260 baseline. Every output is byte-identical and every complete
statistics record matches. Source bytes and exact fonts are unchanged, with no
missing font families. The corpus manifest covers the complete 48-source runtime.

All 121 regression scripts passed, including native source-pose, caption/backdrop,
phase/handoff, contour and paint rendering checks. The complete runtime and
covered harness hashes stayed unchanged throughout the final run.
`structure-checks.json`, `final-regression-checks.json`, `corpus-summary.json`
and `release-verification.json` retain the fresh local release evidence.

Required validation uses the Windows font backend (Pillow BASIC plus real
HarfBuzz) on Linux, including native libass rendering. It does not claim native
Windows filesystem or PowerShell validation.

## After-release evaluation

The boundary preserves one shared source-pose policy at its deliberate early,
late and covered-fragment invocation points. Geometry proof stays local, and
the caller's pose cache retains its existing lifetime. No workaround, duplicated
proof, local exception or new dedicated behavioral review was needed. Previously
documented unrelated issues remain outside this structural release.
