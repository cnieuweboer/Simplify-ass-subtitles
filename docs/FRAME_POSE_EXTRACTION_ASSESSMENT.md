# Representative frame-pose extraction assessment

Assessed against v225 (`2026.10.19.225`, commit `45495e9`). Recommended next
release: **v226 — Extract representative frame-pose policy**. This assessment
does not change production code.

## Recommended boundary

Move five unchanged functions into `_simplify_ass/frame_pose.py`:

- `_frame_paint_alphas()`
- `_frame_pose_intervals()`
- `_visible_pose_support()`
- `_preserve_frame_pose_support()`
- `_representative_frame_pose()`

Together these are 81 definition lines with 12 engine callers. They implement
the shared source-exposure policy introduced in v200: retain actual sampled
support, avoid multiplying dwell through duplicate records, and select an
existing pose independently of output paint normalization. This is one selection
algorithm and its evidence handoff, rather than a collection of unrelated keys.

Keep `_frame_sequence_paint_owner()` in the frame freezer. It chooses that
route's output paint using its established current-opacity/duration rule. It
continues calling the shared alpha helper through an engine alias. The pose
module must not acquire general paint ownership or normalization policy merely
because this function is adjacent in the source.

## Incoming and outgoing dependencies

The 12 engine callers are:

| Caller | Uses the boundary for |
| --- | --- |
| `coalesce_lyric_phases()` | Compatible source-support handoff |
| `collapse_full_lyric_copies()` | Compatible source-support handoff |
| `_frame_sequence_paint_owner()` | Actual visible-channel alpha |
| `_normalize_inline_frame_paint()` | Visibility-weighted source exposure and existing intervals |
| `freeze_vector_sequences()` | Representative source pose |
| `_render_matched_backing_fade()` | Compatible source-support handoff |
| `_render_stacked_text_caption()` | Compatible source-support handoff |
| `_render_complete_line_jitter()` | Representative pose and support handoff |
| `_select_text_effect_sequence_geometry()` | Representative source pose after route-specific admission |
| `_construct_text_effect_sequence_caption()` | Compatible source-support handoff |
| `_merge_static_phase_round()` | Support aggregation at completed-run emission |
| `_freeze_event_effects()` | Initial sampled/frozen support capture |

Outgoing dependencies are only standard-library `collections`,
`dataclasses.replace` and `typing.Iterable`, canonical `Event` from `event_model`,
and `_frame_pose_key()` from v225's `event_operations` module. Keep that key in
its current owner: event replacement depends on it, so moving it with selection
would create the wrong dependency direction. Do not duplicate it.

The graph remains engine → frame-pose policy → event operations/event model →
existing interpretation/geometry modules. There is no reverse engine import,
cycle, callback adapter, font-backend initialization or path-sensitive code.
Keep direct engine aliases for all five functions.

## Data, caches, diagnostics and results

| Concern | Owner after extraction |
| --- | --- |
| Candidate-family admission | Existing processing callers; they still prove literal/geometry, timing, layering and compositing eligibility. |
| Initial evidence capture | `_freeze_event_effects()` still chooses the sampling boundary, before paint normalization; inline reconstruction retains its span-specific exposure proof. |
| Immutable source evidence | Canonical `EventEvidence.frame_pose_intervals` remains in `event_model`; input events and evidence are borrowed. |
| Interval clipping | `_frame_pose_intervals()` clips absolute source support to the surviving event and retains microsecond rounding. Extended output timing creates no new source dwell. |
| Exposure aggregation | `_visible_pose_support()` owns call-local endpoint counters and maximum-opacity support. Coincident copies cannot multiply votes; gaps remain gaps. |
| Pose selection | `_representative_frame_pose()` owns call-local grouping, exposure ranking and deterministic tie-breaking; returns an existing input event and immutable interval tuple. |
| Support handoff | `_preserve_frame_pose_support()` returns a successor with compatible peers' sorted, deduplicated intervals. It retains the successor's other proofs rather than copying historical contour/opacity proofs from the source. |
| Incompatible handoff | Returns the supplied successor unchanged by identity when literal/layout identity differs. |
| Edit invalidation | Stays in `event_operations.replace_event()`; the new module consumes its canonical pose key. |
| Paint selection/rendering | Remains with existing route-specific selectors and renderers. |
| Metrics, caches and diagnostics | No font owner, persistent cache, report or counter moves. Pipeline sequencing and result installation remain caller-owned. |

There are no new result records, context objects, dataclass methods or factories.
Do not change the nonempty-candidate precondition, channel precedence, opacity
thresholds, numeric rounding, weighted temporal median or deterministic tie
rules as part of the extraction. Keep special admission for clipped sequences,
scale trails, simultaneous paint alternatives and upright entrance/exit holds
with its existing processing owners.

## Preparatory change and alternatives

**No preparatory production change is needed.** v225 supplied the canonical
literal/layout validity key without an engine dependency. Moving the five
functions unchanged now establishes a useful boundary on its own.

Other candidates remain plausible, but are not cleanly closed yet:

- Static-phase merging has a cohesive ordering algorithm, but still depends on
  engine-owned `static_object_key()`, `StaticSpanSignature` and vector-token
  identity as well as the source-support handoff. This extraction removes the
  support dependency without mixing static identity into a pose-policy owner.
- Scrolling still needs the shared paint-inclusive `state_key()` and
  `text_height()`. Moving those into scrolling solely to enable extraction
  would give a pass-specific module ownership of general matching helpers.
- Exact-font event-row recovery still shares `FontProcessingReport` with other
  font-processing routes. A row module should not acquire that shared report
  incidentally.
- Broader frame/text-effect processing still combines route-specific admission,
  inline paint proofs and shared matching helpers. Do not pull those into pose
  selection to manufacture a larger module.

This is a small shared processing policy, not the complete frame-effect subsystem.
It removes a real common dependency while preserving responsibilities. Assess
the next larger boundary from the resulting graph; no final hierarchy or broad
API cleanup is needed now.

## Fresh assessment evidence

An ignored prototype moved exactly these definitions and added engine aliases.
AST comparisons confirmed unchanged moved functions and unchanged remaining
engine code except the import. All pre-existing private sources stayed
byte-identical. No test observer correction or new substitution was required.

Eight current scripts passed on both v225 and the prototype: **16 successful
runs**, using Windows BASIC plus real HarfBuzz on Linux:

| Check | Results per version |
| --- | --- |
| Source frame poses | 66 checks |
| Event evidence | 42 checks |
| Complete-line jitter | 78 checks |
| Whole-span paint ownership | 111 checks |
| Matched backing fades | 121 checks |
| Context contracts | 2,500 checks |
| Static-phase handoff | 69 checks |
| Native source-pose rendering | 42 checks |

The handoff check retains its existing historical-finalization bracket for its
v185 consumer-role comparison. It adds no substitution for this extraction;
the source-pose and native checks exercise current selection and rendering.

A separate isolated-process check verified cold imports without the engine or
optional font backends, canonical aliases/types/key identity, existing-candidate
identity, unchanged full event fields, visible-channel alpha, duplicate-safe
exposure, repaint invariance, lifetime clipping, compatible-peer handoff,
preserved successor proofs, mismatch identity and separate output paint choice.

Local evidence lives in `validation/frame-pose-assessment/assessment.json`, with
the prototype, dependency audit, manifests and logs. All 14 runtime-source hashes
still match the fully verified v225 release; tracked tests/harnesses and all 124
recorded font hashes are unchanged. The full regression suite and corpus were
not rerun for this assessment. Production output has not changed.

## Proposed v226 acceptance and evaluation

Move only these functions and retain aliases, signatures and exact policy.
Add focused module/cold/installed coverage for borrowed inputs, candidate
identity, exposure clipping, duplicate-safe voting and successor evidence.
Run the full current suite and fresh paired conversions for all 13 corpus tracks,
requiring byte-identical output and complete statistics. Verify recursive
delivery, runtime manifests, updater rollback/retry and owned uninstall. Keep
native Windows skips explicit and leave `simplify_subtitles.py` unchanged.

Afterward, confirm source producers still choose evidence boundaries, consumers
still choose admissible families, and the module owns only exposure/pose policy.
No workaround, duplicated proof, local exception or ownership conflict was
introduced or uncovered that needs a dedicated corrective review. The global
API and pass-local index reviews remain separate work.
