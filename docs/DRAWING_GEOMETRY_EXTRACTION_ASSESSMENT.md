# Drawing geometry and contour normalization extraction assessment

Assessed against v228 (`2026.10.19.228`, commit `6cffda8`). Recommended next
release: **v229 — Extract drawing geometry and contour normalization**.
This assessment changes no production source or tracked test.

## Recommended boundary

Move these eight existing functions unchanged into
`_simplify_ass/drawing_geometry.py`, retaining direct engine aliases:

- `coverage_geometry()` and `polygon_covers_box()`.
- `drawing_polygon()` and `fit_rectangular_contour()`.
- `normalize_drawing_alignment()` and `flatten_rectangular_border()`.
- `detach_drawing_edge_slivers()` and `simplify_drawing_contour()`.

The boundary contains 321 definition lines and serves 18 engine functions. It
includes an actual contour-processing subsystem: conservative footprint proofs,
anchor/stroke normalization and bounded contour reduction. These operations
share their contour representation and admission primitives. Their dependency
graph closes without importing candidate preparation or caption ownership.

Keep them together rather than moving only the parser: normalization and contour
reduction already depend entirely on these primitives and existing private
owners. Keep measured caption coverage, source-family admission, timing,
compositing, movement and reporting with their current callers.

## Incoming and outgoing dependencies

Incoming consumers cover supporting-drawing preparation/admission/strip coverage,
composite backdrops, caption clipping and panel ownership, unmeasured backdrops,
final layer settling and support summaries. The freezer and final text layout
also consume conservative coverage. Legacy vector occlusion retains its engine
consumer and uses the same aliases; it does not move into this module.

| Outgoing owner | Borrowed dependency |
| --- | --- |
| Standard library | `math`, `re` |
| `ass_overrides` | Canonical `NUMBER` and `OVERRIDE_RE` patterns |
| `caption_geometry` | `get_pos()` |
| `event_model` | Canonical `Event` annotation |
| `event_operations` | `replace_event()` and its existing invalidation policy |
| `static_objects` | The existing shared `geometry_key()` primitive |

The graph is engine → drawing geometry → existing private owners. None of those
owners depends on the proposed module or imports the engine. No adapters,
callbacks, circular imports, new contexts or result hierarchies are required.
Keep `geometry_key()` in its current owner and reuse its canonical binding;
moving or duplicating it solely to change the module name would add scope.
Cold processing needs no optional font backend or file access.

## Data, caches, diagnostics and results

| Concern | Responsibility after extraction |
| --- | --- |
| Events, styles, defaults and measurement context | Remain document/caller-owned and borrowed. No cache is installed or input mutated. |
| Contour parsing and geometry buffers | Remain local lists, token streams, edge partitions and temporary successor events. There is no persistent cache. |
| Conservative footprint | Return the same scene-space points, padded bounds and opaque-fill eligibility. Preserve separate raw-contour versus transformed-footprint meanings. |
| Normalized event successors | Retain the exact replacement contract, metadata, timing and refusal/identity behavior; formatting edits use canonical event operations. |
| Sliver removal | Return the same selected fragment and detached count only after the existing exterior-contact/nonintersection proof. Caller aggregates the count. |
| Contour reduction | Return the same raw reduced path plus original scene-space points, or `None`. The supporting-drawing producer retains responsibility for storing original-contour evidence. |
| Admission and source evidence | `_normalize_supporting_drawing_candidate()` retains ordering, freezing and counts; `_index_supporting_drawing_candidates()` retains the original-contour map. `_finalize_supporting_drawings()` attaches that evidence after group/sequence reduction. |
| Measurements and support proof | Existing metrics retain font caches/diagnostics. Callers still require original and reduced contours to cover the measured caption and preserve timing/compositing checks. |
| Results and reporting | Existing tuples, events, lists and optional returns remain unchanged. No dataclass or diagnostic/report owner moves. |

Preserve every existing distinction: straight contours versus Bezier control-point
bounds, opaque-cover eligibility versus being coverable, unknown syntax versus
finite supported geometry, drawing scale versus stroke/shadow footprint,
scaled-border refusal, rotated/alignment refusal, tangent boundary contact,
interior overlap and original-contour evidence. Do not consolidate the internal
area/fill predicates or change tolerances as part of this movement.

## Preparatory work and alternatives

**No preparatory production change is needed.** Canonical parsing, replacement
and representation owners already provide the boundary. One extraction release
is sufficient. No current test-observer adjustment has been identified.

The full supporting-drawing pass is broader: it owns source admission, movement,
strip grouping, paint composition, caller-owned context/results and counters.
Keep that ownership intact while extracting its closed geometry dependency.
This creates a useful boundary for later assessment without prescribing the
next module tree or relocating its shared helpers incidentally.

Frame echoes and scrolling remain candidates for later assessment, but still
use shared engine layout/state helpers. Those helpers should not become owned
by one effect merely to close its imports. A preparatory extraction for those
helpers may be useful later; it is unnecessary for this closed subsystem.

## Assessment evidence

An ignored prototype moves the exact eight definitions with direct aliases.
AST checks verify identical moved functions and unchanged remaining engine code
apart from the import. All pre-existing private sources remain byte-identical;
the prototype retains the v228 version. The 17 production source hashes, tracked
regression harness and all 124 recorded font hashes still match verified v228.

An isolated process passed cold import without font backends, canonical aliases,
conservative footprint/curve/edge refusal, alignment/stroke normalization,
exterior-versus-interior sliver guards, original contour handoff and borrowed
input checks. These use the real module dependencies without adapters or stubs.

Seven existing checks passed unchanged on both baseline and prototype: **14
successful script/version runs**, using Windows BASIC plus real HarfBuzz on Linux.

| Check | Results per version |
| --- | --- |
| General simplifier regression | 275 checks |
| Portable caption ink | 49 checks |
| Parser effect consumers | 9,894 checks |
| Outline parsing reuse | 219 checks |
| Effect continuation | 179,958 checks across 3,144 cases |
| Native outline policy and geometry | 92 checks |
| Native caption/backdrop layers | 107 checks; both Sword signs visible and layers stable in one run |

The tests, assertions and observer bindings were unchanged. Native checks use
the current pipeline and paint policy. Runtime, harness and font hashes were
verified again after these checks completed.

Local prototype, manifests, dependency audit and logs live in
`validation/drawing-geometry-assessment/`. An initial local runner launch used a
leftover helper path; only that ignored runner was corrected. The launch record
is retained separately. This was not a production or regression failure.
The full suite and paired corpus are reserved for implementation; this assessment
does not claim a fresh full run.

## Proposed v229 validation and after-release evaluation

Add focused module/cold/installed checks for canonical aliases/types, borrowed
inputs, conservative unknown-geometry refusal, scales/alignments/strokes,
curves, nonintersecting slivers, reduction bounds, original-contour handoff and
successor evidence. Verify installed paths with spaces and owned module/cache
removal while preserving user files.

Run the full current regression suite and fresh paired conversions of all 13
corpus tracks, requiring byte-identical output and complete statistics. Retain
native caption/backdrop, outline/geometry and continuation checks. Verify
recursive Python/PowerShell delivery manifests, the actual shipped updater's
rollback/retry, owned uninstall and the MKV smoke test. Leave
`simplify_subtitles.py` unchanged and identify native Windows limitations.

Afterward, confirm contour operations borrow their inputs and producers still
own stage order, original-contour evidence, admission and counters. No production
workaround, duplicate proof or ownership conflict currently warrants a dedicated
corrective review. Broader API and pass-local index reviews remain separate.
