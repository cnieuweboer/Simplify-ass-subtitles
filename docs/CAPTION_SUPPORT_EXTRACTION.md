# Caption-support selection — v268

This records the v268 boundary. [v272](CAPTION_SETTLING_EXTRACTION.md) extends the
same module with final layer settling and the existing `CaptionSupportResult`.

Nine existing functions and the existing frozen `CaptionPanelOwnership` record,
279 definition lines, live in `_simplify_ass/caption_supports.py`. The shared
17-line `caption_clip_outline()` reader lives in `drawing_geometry`. Names,
signatures, defaults, annotations, comments and bodies move unchanged. The engine
retains direct aliases for all eleven definitions. Runtime: `2026.10.25.268`.

## Boundary and dependencies

This subsystem selects enclosing panels and sparse adjacent decorations,
distinguishes fullscreen fills, records measured enclosing ownership, and retains
fallback supports where overlapping text cannot be measured. It preserves both
the public two-result selection API and the internal three-result proof handoff.

Dependencies are existing caption/drawing geometry, static identity, event
operations and caller-owned metrics, plus the standard library. The shared
clip-contour reader is also used by masked-foreground recovery; its unchanged
relocation into the existing geometry owner is the only preparation required.
Both moves belong in the same release. Imports remain acyclic; no private module
imports the engine. No adapter, callback, new context, cache or policy is added.
Existing installer/update source discovery includes the module automatically.

## Preserved ownership

| Resource | Responsibility |
| --- | --- |
| Inputs | Candidate/caption Events, formatting, styles and supplied metrics stay borrowed. |
| Local state | Bounds maps, geometry indexes, selected IDs, association lists, measured claims and fallback-equivalence sets belong to one invocation. |
| Selection | Existing timing, geometry and layer admission remains unchanged. Shared authored masks and adjacency do not manufacture measured enclosing ownership. |
| Successors | Accepted reconstructed enclosing panels retain the existing opaque-paint replacement and original contour evidence. Canonical event replacement and invalidation remain authoritative. |
| Proof | `CaptionPanelOwnership` retains frozen bindings and borrowed panel/caption identity. Ownership refers to the accepted panel successor where paint was normalized. |
| Results | Existing returned lists/dictionaries and shallow sharing remain unchanged. `CaptionSupportResult` stays with engine assembly. |
| Callers | Drawing reduction, optional budgets, texture removal, output ordering, late shadow normalization, final layer settling and reporting keep their existing owners. |
| Fonts | Measurement resources and caches remain with the supplied metrics owner. The subsystem introduces no report object or counter owner. |

Final-only panel equivalence/coverage helpers remain with final layer settling.
The wrapper, CLI, configuration and report catalog do not change.

## Validation

The existing drawing-geometry module check also protects canonical aliases,
resolved annotations, historical ownership-record lookup, frozen bindings,
borrowed Event identity and source immutability, independent per-call result
containers, the two-result API and the shared clip reader's scaling/refusal.
Cold checkout and installed imports work without the engine or optional font
backends. Delivery/removal is checked in a directory with spaces. All thirteen
boundary tests and all 42 event-evidence ownership checks pass.

The isolated final texture-removal test supplies its existing measured bounds to
both the assembly caller and the defining selection consumer. This preserves the
test's intended geometry after extraction without production forwarding. General
support behavior, portable caption ink and current-policy paint checks retain
their existing behavioral coverage; inactive historical helper-count audits are
not reactivated.

Local release evidence lives in `validation/caption-support-extraction/`. Its
structure audit compares all eleven definitions and the remaining engine against
v267, verifies unchanged existing drawing-geometry logic apart from the added
reader, and checks other existing private sources and the wrapper byte-for-byte.
It also checks acyclic imports. Runtime manifests identify all 55 Python sources.
Fixtures, fonts, outputs and generated reports remain ignored local assets.

All 121 regression scripts passed, including native caption/backdrop layering,
source-pose, paint, contour-order, fade/handoff and near-backing rendering. Fresh
comparison of all thirteen corpus tracks against the hash-bound v267 baseline
found every output byte and complete statistics record identical. Exact fonts
and source bytes are unchanged, with no missing required font families. Runtime
and test/harness hashes stayed unchanged throughout validation.
`release-verification.json` binds the structure audit, full regression report and
corpus comparison. Checks use Pillow BASIC plus real HarfBuzz on Linux, including
native libass; they do not establish native Windows filesystem/PowerShell behavior.

## After-release evaluation

The extraction keeps association and ownership proof together, preserves the
caller-owned final layer handoff, and adds no workaround, duplicated proof or
matching exception. No behavioral issue requiring a dedicated follow-up review
was uncovered.
