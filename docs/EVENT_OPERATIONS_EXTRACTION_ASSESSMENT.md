# Event operations extraction assessment

Assessed against v224 (`2026.10.19.224`, commit `d4a166a`). This is a proposal
for v225, not an implemented runtime change.

## Recommended boundary

Move three unchanged functions into `_simplify_ass/event_operations.py`:

- `event_evaluation()`
- `replace_event()`
- `_frame_pose_key()`

These are 58 definition lines, used by 86 engine functions. The useful boundary
is the existing contract for reading resolved formatting and creating successor
events while respecting parser history and source evidence. It is small but
widely shared by reconstruction, phase merging, fading, compaction and support
handling. Moving it removes a common engine dependency for future processing
extractions. Line count alone would understate its value.

v224 made this boundary closed: `_frame_pose_key()` now obtains inline geometry
from the extracted `inline_layout_key()`. No preparatory production change is
needed. Do not expand this into a general event-utilities collection.

## Dependencies

The new module would depend on:

- Standard-library `dataclasses.replace`.
- `ass_overrides`: canonical evaluation/continuation records, default state,
  override pattern, complete-stream evaluation and style resolution.
- `event_model`: canonical `Event` and `EventEvidence` records.
- `caption_geometry`: `inline_layout_key()`.

The dependency direction remains engine → event operations → existing private
owners. None imports the engine. No callback adapters, circular imports, new
records, factories or context objects are required. No paths or `__file__`
assumptions move. Cold importing and using the prototype does not initialize
font backends or require optional rendering dependencies.

Keep direct engine aliases for all three functions, including the private key.
Its existing pose producers and consumers must use the same implementation as
replacement validation. Do not copy that key into two owners.

## Ownership and behavior to preserve

| Concern | Existing responsibility after extraction |
| --- | --- |
| Resolved cache reads | `event_evaluation()` borrows state and continuation by identity. |
| Unresolved reads | Fresh complete evaluation ignores stale history and installs no cache. |
| Text/style replacement | `replace_event()` resolves and parses the replacement; supplied stale formatting/history cannot override it. |
| Explicit state replacement | Nonempty state keeps existing history unless replaced; empty state clears continuation. |
| Document inputs | Style/default maps and measurement context remain borrowed; no new global cache or defensive deep copies. |
| Source evidence | Existing edit invalidation stays with replacement; callers still decide when to supply explicit proof. |
| Pose support | Paint-only edits may retain source exposure intervals when literal/layout identity matches. Other historical paint/coverage proofs still expire. |
| Timing/layer edits | Existing cache/history/evidence sharing remains; replacement does not invent or extend source exposure. Consumers clip absolute intervals. |
| Results | Return the same canonical evaluation/event types and geometry key; input events remain unchanged. |
| Pipeline/reporting | Callers retain cache installation, stage transitions, family admission, event emission, counters and diagnostics. |

Preserve the current distinction between automatic invalidation and explicitly
supplied evidence. This structural change must not broaden proof retention,
alter numeric precision or make passive event records responsible for policy.
Mutable state sharing is part of the existing contract; freezing or copying
records would be a separate behavioral change.

`_frame_pose_key()` belongs here because successor validity depends on it. Keep
exposure accumulation, interval clipping and representative-pose selection in
their current owners. Those algorithms have a different responsibility from
creating a valid successor event.

## Alternatives considered

- **Scrolling text:** approximately 284 function lines plus its result record,
  but still depends on engine-owned `state_key()` and `text_height()`. Moving a
  general paint-inclusive fingerprint into scrolling would create poor ownership.
- **Exact-font row recovery:** approximately 240 function lines, but its report
  record is shared with other font-processing work. Do not make a row-specific
  module own a cross-pass report merely to close its imports.
- **Frame-pose processing:** its helpers form another plausible boundary, but
  combining exposure/selection policy with event replacement would blur their
  responsibilities. Assess it independently after this extraction.
- **Static-phase processing:** still relies on shared geometry/signature and
  source-support operations. Extracting event operations removes one common
  dependency without prematurely deciding the remaining module structure.

These findings do not require a broad API or report redesign. Continue choosing
the next boundary from the resulting graph rather than planning the final tree.

## Fresh assessment evidence

An ignored prototype moved the exact definitions and added direct engine aliases.
AST comparison confirmed unchanged moved functions and unchanged remaining engine
code except the import. Existing private sources remained byte-identical. No
test observer changes or runtime substitutions were needed.

Eight existing scripts passed on both v224 and the prototype: **16 successful
runs**, using the Windows BASIC plus real HarfBuzz backend on Linux:

| Check | Results per version |
| --- | --- |
| Event continuation | 4,099 checks |
| Event evidence | 42 checks |
| Source visibility | 207 comparisons plus 27 ownership/replacement checks |
| Context contracts | 2,500 checks |
| Row reconstruction ownership | 61 checks plus two focused conversions |
| Frame pose selection | 66 checks |
| Inline continuation | 51,222 checks |
| Native frame pose rendering | 42 checks |

A separate isolated-process check verified cold imports, canonical aliases and
types, borrowed versus fresh evaluation, replacement parsing authority, history
clearing, timing-only sharing, selective frame-support retention, geometry-change
invalidation, explicit proof authority and unchanged inputs.

Local evidence is in `validation/event-operations-assessment/assessment.json`,
with source manifests, dependency audit, prototype, logs and the isolated check.
All 13 production-source hashes still match the fully verified v224 release.
Tracked tests and harnesses are unchanged. The complete regression suite and
corpus were not rerun for this assessment; the prototype checks do not replace
implementation release validation or native Windows validation.

## Proposed v225 acceptance

1. Move only these definitions and preserve direct aliases, signatures and code.
2. Add focused module and installed-import coverage for the contracts above,
   including numeric/layout identity, document context and absolute exposure.
3. Run the full current regression suite and fresh paired conversions for the
   13-track corpus, requiring byte-identical output and complete statistics.
4. Verify recursive delivery/manifests, updater rollback/retry and owned uninstall.
   Keep native Windows skips explicit; leave `simplify_subtitles.py` unchanged.
5. Inspect the resulting import graph and choose the next boundary afterward.

## After-assessment evaluation

No adapters, duplicated proofs, local exceptions or unclear ownership were
introduced or uncovered that require a dedicated corrective review. Existing
cross-pass dependencies remain visible for later bounded assessments. The global
API and pass-local index reviews remain separate work.
