# Frame-sequence freezing — v266

Three existing functions, 140 definition lines, live in
`_simplify_ass/frame_sequences.py`: `freeze_vector_sequences`,
`_frame_sequence_paint_owner` and `_near_static_frame_fits`. Names, signatures,
defaults, annotations, comments and bodies move unchanged. The engine retains
direct aliases. The runtime version is `2026.10.24.266`.

## Boundary and responsibilities

The freezer serves text frames as well as drawings. It groups compatible frames,
rejects ambiguous overlapping components, applies the existing motion/hold or
bounded-jitter proof, and emits longer holds. Source exposure chooses geometry;
the existing visible-paint rule chooses output opacity independently. Its two
engine-local helpers have no other production consumer and move with it.

Dependencies are existing event operations, static identity, caption geometry,
caption rendering, source-frame pose selection and lyric-boundary evidence.
Imports remain one-way. No preparatory change, adapter, callback, new record,
global cache or policy change is required. Existing module delivery discovery
includes the new source without a filename list.

| Resource | Preserved owner |
| --- | --- |
| Inputs | Events, styles, inline-paint source proofs and lyric-boundary indexes remain borrowed. |
| Working state | Groups, timing components, run buffers, pose references and paint lookups belong to one invocation. |
| Pose and paint | `frame_pose` retains source-exposure selection. The moved helper retains the freezer's visible-paint rule; source support is not replaced by the emitted hold's duration. |
| Results | The existing `(events, removed_count)` tuple, unchanged Event identity on refusal, canonical replacement and source-index ordering are preserved. |
| Callers | Text-frame merging retains normalization and inline-paint proof. Supporting-drawing reduction retains pose/original-contour admission. The legacy vector route retains its existing stage. Callers retain configuration, stage order and aggregate reporting. |
| Resources | Font handles, measurement caches and diagnostic/report lifetimes keep their existing owners. |

Other vector reducers, inline-paint normalization and source-palette processing
remain outside this boundary. The wrapper, CLI and reporting catalog do not change.

## Validation

The existing frame-pose module check now also protects canonical sequence aliases,
resolved annotations, borrowed source/cache immutability, independent geometry and
opacity, source-evidence retention, repeated calls, overlapping-frame refusal,
cold imports and installed delivery/removal. It exercises both the checkout and
an installed directory with spaces, without loading the engine or optional font
backends during independent imports. Existing pose, inline-paint, measurement and
current-policy paint checks continue to exercise the unchanged algorithm.

Local release evidence lives under `validation/frame-sequence-extraction/`.
The structure audit compares all three definitions and the remaining engine
algorithm against v265, checks byte-identical existing private sources and wrapper,
and verifies acyclic imports. Runtime manifests cover all 53 Python sources.
Generated reports, fixtures, fonts and outputs remain ignored development assets.

All 121 regression scripts passed, including native source-pose, inline-paint,
fade/handoff and caption/backdrop rendering. The expanded frame-pose module check
passes nine tests. Fresh comparison of all thirteen corpus tracks against the
hash-bound v265 baseline found every output byte and complete statistics record
identical. Exact fonts and source bytes are unchanged, with no missing required
font families. Runtime and test/harness hashes stayed unchanged throughout the
run. `release-verification.json` binds the structure audit, full regression report
and corpus comparison. Checks use Pillow BASIC plus real HarfBuzz on Linux,
including native libass rendering; they do not establish native Windows
filesystem/PowerShell behavior.

## After-release evaluation

The extraction keeps admission, sequence reduction and replacement together
without moving caller-owned paint normalization, evidence capture or reporting.
It adds no workaround, local exception, duplicated proof or downstream repair.
No behavioral issue requiring a dedicated follow-up review was uncovered.
