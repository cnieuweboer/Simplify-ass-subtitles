# Backed-glyph pulses — bounded extraction assessment

Assessed against v239 (`2026.10.20.239`, commit `9af1e8f`). Recommended next
release: **v240 — Extract backed-glyph pulse processing** into
`_simplify_ass/backed_glyph_pulses.py`, with no intended behavior changes.
V239 supplied the useful shared-paint preparation; no further preparatory
production release is needed.

This assessment changes documentation only. The isolated prototype, complete
runtime manifests and fresh reports remain under ignored
`validation/backed-glyph-pulses-assessment/`.

## Boundary

Move eighteen existing functions and two frozen records unchanged, totaling
410 definition lines including decorators:

- `BackedPulseContext`, `BackedPulseRow`.
- `_eligible_backed_glyph_state`, `_parse_backed_glyph_effects`,
  `_prepare_backed_glyph_pulses`, `_group_backed_glyph_rows`,
  `_backed_glyph_pose`, `_backed_frames_converge`, `_collect_backed_row_holds`,
  `_backed_row_has_conflicts`, `_select_backed_row_pose`,
  `_backed_sizes_are_positive`, `_backed_foreground_coverage`,
  `_backed_transform_returns`, `_prove_backed_foreground_pulses`,
  `_extend_backed_pulse_tails`, `_proved_backed_row_paint`,
  `_propose_backed_pulse_row`, `_apply_backed_pulse_proposals`,
  `collapse_backed_glyph_pulses`.

This is one complete processing responsibility. A continuous translucent backing
establishes glyph anchors and cue bounds; shared opaque holds and returning
foreground pulses establish readable replacement poses. Keep admission,
coverage/conflict proof, transform/frame return proof, complete exit handling,
row paint selection, proposal arbitration and ordered application together.
The operation reconstructs retained glyph events; later row assembly still owns
spacing and combining them into complete caption lines.

Retain all twenty names as direct engine aliases, preserving signatures/defaults,
canonical record identity, shallow freezing and historical root pickle lookup.
Accept the natural change in defining module. Do not consolidate the records,
introduce another context or redesign the tuple result.

## Incoming and outgoing dependencies

The sole production caller is `remove_source_fragment_effects()`. It supplies
surviving source events after the earlier fragment proofs, with the existing
word/position maps and optional metrics. It retains unresolved-source isolation,
row evidence, stage order, the subsequent sliced-text pass and the
`SourceFragmentRemoval` result. Its aggregate remains
`len(removed) + pulses + slices`; no counter or reporting change is needed.

| Outgoing dependency | Existing owner |
| --- | --- |
| Canonical `Event` | `event_model` |
| Override evaluation/continuation records, defaults and transform replay | `ass_overrides` |
| Resolved event reads, raw tokens and successor edits | `event_operations` |
| Strict transform validation | `effect_validation` |
| Inline guard, nominal text height and layout key | `caption_geometry` |
| Reconstructed caption serialization and canonical `SourceCaptionPaint` | `caption_rendering` |
| Settled-plane sampling and complete-row paint pooling | `caption_paint_sampling` |
| Time serialization | `subtitle_document` |
| Optional exact metrics interface and font caches | Borrowed `FontMetrics` in `font_metrics` |
| Records, local replacements, geometry arithmetic and character eligibility | Standard-library `dataclasses`, `math`, `unicodedata` |

No outgoing runtime helper remains defined in the engine. The prototype's private
import graph is acyclic and has no reverse engine import. Shared sampling remains
with its v239 owner; glow processing neither imports this operation nor changes.
No callback adapter, forwarding wrapper or cross-tool shared module is needed.
No `__file__` path logic moves. Cold import and supported/refused processing with
metrics absent load neither the engine nor optional font backends. Optional
metrics retain the existing paint estimate and fallback behavior, rather than
becoming a prerequisite for the glyph proof.

## Data, caches, diagnostics and results

| Concern | Responsibility to preserve |
| --- | --- |
| Inputs | Borrow events, word/position maps, defaults/styles/continuations and supplied metrics. Preserve source object/cache identity. Unresolved reads use the existing uncached event evaluator; do not install formatting on input events. |
| Pass context | One invocation owns allowed tags, eligible-family/backing indexes, resolved-detail and continuation maps. Borrow cached formatting and immutable continuations; keep replayed destinations in local copies. Each call creates independent buffers, without a persistent parsing cache. |
| Row evidence | Runs, foreground peer lists, held-pose buckets and common-pose sets belong to the pass. Their event references remain borrowed. The frozen row/context records retain mutable containers and their current sharing; do not deep-copy everything or add runtime freezing. |
| Proof decisions | This operation retains full foreground coverage, common held-pose selection, finite positive size checks, returning pulse/frame convergence, ambiguous-neighbor refusal and complete shared exit proof. Preserve existing timing bounds, ordering and the minimum complete-row/pulse requirements. |
| Paint | The operation proves a common settled backing and eligible complete row. The shared sampler computes appearance, metrics owns font caches, and caption rendering owns serialization/policy. Keep the existing fallback if sampling is unavailable or uncertain. |
| Proposal/application state | Members, kept successors, ownership counts, removals and replacement maps are call-local. Competing proposals are rejected before edits. Preserve untouched identity, selected successor flags/measurement and actual original-list placement, including source-ID-based replacement behavior. |
| Result and reporting | Return the same `(events, removed_count)` tuple. The count remains the actual input/output list-length difference. If no proposal is accepted, return the original input list and zero. Callers retain aggregate statistics, logs, font reports, row adoption and reconstruction handoffs. |

Keep source-paint proof separate from sampling, and keep backing/foreground exit
handling separate from broader cue synchronization. Preserve continuation replay,
clipped terminal convergence, held-pose ambiguity, complete-row refusal and
all-or-nothing proposal arbitration. Do not add broader filters, new heuristics,
new indexes or downstream repairs during the move.

## Preparation and test bindings

V239 removed the two shared engine dependencies cleanly. Further preparation
would add no necessary boundary: the operation, its existing records and all its
internal helpers can now move together unchanged.

The established `patch_interpreter_bindings()` test helper needs the module
defining `collapse_backed_glyph_pulses()` in its existing consumer list. That keeps
`check_effect_continuation.py` observing both entry-point processing and direct
calls to the exported parser helper. The prototype applies this test-only binding
update without changing assertions. Caller-side source-fragment observers stay
on the engine alias, which remains the actual invocation site.

`check_backed_pulses.py` is an archived extraction harness, not a current suite
entry point. Its case builders remain useful; this assessment compares current
v239 directly with the prototype instead of reviving historical call-order or
source-file helper-count requirements. Its earlier historical oracle does not
specify future source layout.

## Fresh evidence and implementation acceptance

All twenty definition ASTs move unchanged in the isolated prototype. Remaining
root definitions and all prior private sources are unchanged. The production
25-source runtime, tracked tests and all 124 recorded font hashes remain unchanged.
Cold supported/refused proofs, borrowed-map and local-buffer ownership, canonical
aliases/annotations, shallow frozen records and root pickle lookup pass.

Current v239 and the prototype each passed:

| Check | Result for each runtime |
| --- | --- |
| Direct current-policy comparison | 186 cases across 62 scenarios and three input orders; complete decisions, counts and return/retained identity identical between runtimes |
| Ownership and repeat checks in those cases | Borrowed events/maps unchanged; repeated result stable with no additional removal |
| Backed paint and native rendering/repeat conversion | 253 assertions |
| Source-fragment isolation/adoption | 39 assertions |
| Current paint handoffs with actual serialization/exact geometry | 177 assertions |
| Effect continuation, including backed pulse/parser cases | 179,958 assertions across 3,144 cases |

These ten focused runs support the boundary; they are not a new full-corpus or
native Windows filesystem validation. For implementation, add module-contract
coverage for both existing records, independent pass buffers, supported/refused
rows, ordered application/counting, borrowed inputs, canonical aliases and cold
source/installed execution. Keep metrics optional. Run the full current regression
suite and fresh strict-font corpus comparison, requiring identical output bytes
and complete statistics. Verify recursive delivery, the shipped updater's new
module rollback/retry, installed processing and owned uninstall. Keep the batch
wrapper, CLI, pipeline configuration and reporting unchanged.

After implementation, confirm that this module owns the complete pulse proof
and that source-fragment orchestration, shared paint sampling and later row
assembly keep their existing responsibilities. No new workaround, duplicated
proof or unclear ownership was uncovered; no dedicated corrective review is
indicated. The existing Pillow `getdata()` compatibility follow-up, scrolling
iterator contract and deferred global API/index reviews remain separate work.
Pillow compatibility does not need to precede this behavior-neutral extraction.
