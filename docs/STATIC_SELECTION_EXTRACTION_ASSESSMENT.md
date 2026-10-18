# Static-state selection — bounded extraction assessment

Assessed against v219 (`2026.10.18.219`). The recommended next release is
**v220: extract static-state selection into `_simplify_ass/static_selection.py`**.
This moves a complete processing responsibility: ranking transform intervals,
choosing readable geometry, protecting sustained holds and voting representative
paint. It does not move text serialization or redesign selection policy.

Production and test sources remain unchanged in this assessment. The isolated
whole-engine prototype and fresh evidence are private under
`validation/static-state-assessment/`.

## Boundary and alternatives

Move the five existing records unchanged: `StaticStateContext`,
`StaticStateEvidence`, `StaticStateSamples`, `StaticPoseEvidence` and
`StaticStateSelection`. Move `select_static_state()`, its twelve internal
helpers, and `unrotated_text_state()`, `upright_text_state()` and
`upright_transform_pose()`. The 21 definitions total 407 lines including their
decorators; surrounding whitespace is not counted.

The three pose helpers close the dependency graph. Other passes also use the
two state predicates, so retain direct engine aliases. These predicates do not
invoke selection or introduce another policy owner. There is no need to split
them into a separate utility module solely to avoid importing the selector.

Leave `FrozenBlock`, `_freeze_inputs()`, `freeze_block()`,
`simplify_visual_text()`, animated-shadow source admission, event replacement,
rendering and pass orchestration in the engine. In particular, the nearby
`animated_shadow_painted_source()` depends on source-event/layout policy and
does not belong to this boundary.

Other processing candidates were compared by global-symbol dependencies:
frame echoes (16 functions), masked-glyph removal (18), sliced-text sequences
(16), scrolling-block detection/removal (nine), and supporting-drawing reduction
(12 in its core block). Each still reaches into engine-owned rendering,
replacement, geometry or other processing services. None is rejected as a future
module. Moving one now would require a larger dependency closure or another
preparatory boundary. Static selection already closes over existing modules and
has substantial current semantic coverage.

## Incoming and outgoing dependencies

The module needs `dataclasses`, `math`, `re`, `typing.Iterable`, the existing
`Event` record, interpreter records/`apply_override()`, and the two transform
sampling functions. `Event` is used for paint-evidence annotations and field
reads, not event construction. There are no font backends, paths, CLI settings,
renderers, event-replacement helpers or reverse engine imports.

The dependency direction is engine → static selection → event model,
interpreter and transform sampler. Those existing modules need no change.

Six engine functions call `select_static_state()`: `freeze_block()`,
`coalesce_lyric_phases()`, `collapse_full_lyric_copies()`,
`_render_complete_line_jitter()`, `_select_text_effect_sequence_paint()` and
`_prove_glyph_phase_lives()`. Numerous other passes read the shared pose
predicates. `simplify_visual_text()` constructs pose evidence; `FrozenBlock`
annotates the selection result. Import canonical aliases before these dependent
definitions. Preserve all existing names rather than adding forwarding wrappers.

## Ownership

| Data | Existing owner and contract to preserve |
| --- | --- |
| Base formatting, styles, defaults, transforms and paint events | Caller owns inputs; selector borrows them. The unchanged early return deliberately returns the base dictionary itself. Sampled selection owns its changed formatting. No event cache is installed or invalidated here. |
| Opaque intervals and settled-state seeds | Caller owns seed containers. Selector copies the containers; existing snapshot dictionaries remain borrowed, and newly collected snapshots are independent copies. Preserve disabled versus enabled-empty results. |
| Hold votes, candidates, paint samples and rotation-search cache | Selection call owns temporary buffers. They do not become persistent caches or fields on events/documents. |
| Parser continuation | Immutable interpreter value follows the selected branch. Paint voting does not synthesize parser history. |
| Pose evidence | Existing frozen selection-specific proof, distinct from EventEvidence. Continued spans may explicitly carry it; reset/replacement/serialization policy remains with existing consumers. Keep tuple protection and factory identity. |
| Result records | Selector returns the existing frozen bindings. Frozen bindings do not recursively freeze formatting dictionaries. Callers retain responsibility for applying and serializing results. |
| Diagnostics and counters | None are produced here. Font reports, output counters and pipeline diagnostics stay with existing owners. |

No new context, callback adapter, data-copying policy or dataclass consolidation
is required. The useful preparation was already completed by the interpreter,
sampler and canonical event-record extractions. Another preparatory production
release would not independently improve this particular boundary.

## Prototype evidence and test implications

The prototype moves complete definitions unchanged and imports aliases before
dependent declarations. An AST audit confirms identical moved definitions and
identical remaining engine executable AST after excluding the new import.
Independent import loads neither the engine nor optional font packages. Alias,
runtime annotation, `FrozenBlock` annotation, pose-factory and ordinary pickle
probes pass.

Six existing scripts were run freshly against both baseline and prototype:

- `check_frozen_block_results.py`: 3,360 comparisons and 27 ownership checks.
- `check_pose_evidence.py`: 2,592 comparisons and 24 boundary/ownership checks.
- `check_freeze_continuation.py`: sampler, selector and continued-block behavior.
- `check_freeze_consumers.py`: 16,704 checks, including 1,932 selector cases,
  1,728 lyric-copy cases and 428 text-effect sequence cases.
- `check_context_contracts.py`: 2,500 checks.
- `check_event_model_module.py`: nine checks, including installed event-model
  contracts. This is not delivery validation of the proposed selector module.

All twelve executions passed, but the unadjusted continuation observer recorded
fewer interpreter assertions after extraction: it patches engine and sampler
bindings, not the new selector's imported binding. A private test-only prototype
adds that actual consumer to observation and restores all **634,286** assertions,
with the same 5,130 sampler cases, 1,440 selection cases and 576 continued steps.
The implementation should extend the existing binding helper with identity
deduplication; do not route production calls through the engine for a test spy.

The historical `check_static_state_stages.py` contains source-file coverage and
old call-trace assumptions. It is not a current regression entry point. Its
scenario definitions are actively reused by `check_freeze_consumers.py`; preserve
that reuse rather than reviving historical implementation-shape requirements.

These focused probes establish a viable extraction boundary, not a completed
release. Full regression, fresh baseline/current corpus comparisons and generic
installation/update/rollback checks remain implementation acceptance work.

## Proposed v220 acceptance and evaluation

Extract the bounded group unchanged, retain direct aliases and canonical
factories, update test observation at the real owner, and add focused module
import/ownership/installed-identity checks. Use the existing generic delivery
contract; leave the batch wrapper unchanged. Require the current full suite and
fresh corpus output/statistics parity, with complete runtime manifests.

After release, confirm that geometry, representative paint, continuation and
source evidence retain their current owners and that assertion coverage was not
silently reduced. This assessment found no production workaround, duplicated
proof or ownership correction requiring a separate review. The observation
adjustment belongs to the extraction itself. Larger processing subsystems remain
eligible for subsequent assessments; this is not a final module hierarchy.
