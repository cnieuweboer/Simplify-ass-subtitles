# Complete-line jitter — bounded extraction assessment

Implemented in [v235](COMPLETE_LINE_JITTER_EXTRACTION.md). The evidence below
describes the historical assessment.

Assessed against v234 (`2026.10.20.234`, commit `3b95357`). Recommended next
release: **v235 — Extract complete-line jitter processing** into
`_simplify_ass/complete_line_jitter.py`. No preparatory production change is
needed. This assessment changes documentation only; the isolated prototype and
fresh reports remain under ignored `validation/complete-line-jitter-assessment/`.

## Boundary

Move seven existing functions and two frozen records unchanged, totaling 208
definition lines including decorators:

- `JitterTextFamily`, `CompleteLineJitterResult`.
- `_index_complete_line_jitter`, `_prove_complete_line_jitter`,
  `_complete_line_jitter_families`, `_complete_line_jitter_core_overlap`,
  `_group_complete_line_jitter_stacks`, `_render_complete_line_jitter`,
  `flatten_complete_line_jitter`.

Together they recognize bounded reversals of complete explicit-frame captions,
prove a sustained readable core, establish ownership of corresponding paint
layers, and emit static captions with representative source-backed poses.
This moves a complete processing operation, including replacement application.

Keep these nine names as direct engine aliases, preserving signatures/defaults,
canonical record identity and historical root pickle lookup. Preserve shallow
freezing; the result's list and referenced events retain their existing ownership.
Do not merge this with frame echoes: bounded complete-caption jitter and exit
replicas following an opaque hold have different admission and ownership proofs.

## Incoming and outgoing dependencies

There is one production caller, `_consolidate_text_events()`. It invokes
`flatten_complete_line_jitter()` before word-echo removal and passes the accepted
`result.captions` directly to that separate proof. Keep this sequence, original
source selection, configuration and result unpacking in the engine.

| Outgoing dependency | Existing private owner |
| --- | --- |
| Canonical `Event` annotations | `event_model` |
| Position, inline-layout rejection, nominal height and exact layout key | `caption_geometry` |
| Event replacement and resolved paint identity | `event_operations` |
| Complete static-span identity | `static_objects` |
| Unrotated-state admission and representative static paint selection | `static_selection` |
| Representative source pose and compatible pose-support preservation | `frame_pose` |
| Source-paint proof and reconstructed caption serialization | `caption_rendering` |
| Output timestamp formatting | `subtitle_document` |
| Records, finite arithmetic and family-anchor medians | Standard-library `dataclasses`, `math`, `statistics` |

No outgoing runtime helper remains defined in the engine. A private-import graph
check of the isolated prototype is acyclic and contains no reverse engine import.
No callback adapter, duplicate helper, path-sensitive discovery or new shared
service is needed. This remains engine-specific implementation under
`_simplify_ass/`, not cross-tool `shared/` code.

## Ownership and handoffs

| Concern | Contract to preserve |
| --- | --- |
| Inputs | Working events, visibility map, styles and original source map remain caller-owned and borrowed. Keep source animation, source lifetime and complete-literal refusal distinct from working-frame admission. |
| Working state | Buckets, ordered temporal components, readable runs, paint-layer groups, removal IDs and replacement maps belong to one invocation. There is no persistent pass cache or font-resource owner. |
| Family records | Members and holds are tuples of borrowed events. The family median anchor is grouping evidence; final caption placement still comes from the existing source-evidence pose selector. Do not substitute the median for that selection. |
| Paint and pose | The actual foreground layer's sustained hold supplies representative paint. Existing rendering and pose-support owners retain their policies and evidence handoffs. Preserve gaps, frame/layer multiplicity refusals and original compositing order. |
| Results | The pass owns its new output list and caption successors. Unchanged entries retain identity. `captions` contains those same accepted successor objects for the subsequent word-echo proof; do not rebuild or infer that ownership downstream. |
| Counts and diagnostics | The result returns separate frame and stack reductions. The engine adds frames to `text_effect_sequences_frozen` and stacks to `stacked_text_copies_flattened`; it retains aggregate reports. The module gains no logging, font diagnostics or report accumulator. |

## Preparation and alternatives

The required boundaries already exist after the foundational extractions. Moving
this operation therefore needs no preliminary API redesign, generic context,
record consolidation or shared matching abstraction.

Dependency screening also examined masked-glyph removal, sliced-text sequences
and backed-glyph pulses. Sliced text still reaches three engine helpers; backed
pulses still reach two engine paint producers. Those are future bounded
assessments rather than reasons to expand this extraction.

Masked-glyph removal also has a closed dependency graph, but resource-lifetime
screening reproduced an existing failure path: if `open_face()` succeeds and
`getGlyphSet()` then raises, the opened font is never entered in the pass's font
map and the normal cleanup cannot close it. The outline is conservatively
refused, but the handle is left open. A synthetic resource probe confirms this
without requiring or substituting any real font. Fix that ownership path in a
separate bounded reliability change before extracting masked-glyph processing;
it is not a prerequisite for the jitter extraction. No runtime change is made
for it in this assessment.

The masked-font resource follow-up is resolved separately in
[v236](MASKED_FONT_RESOURCE_CLEANUP.md).

## Fresh assessment evidence and implementation acceptance

The isolated prototype moves all nine definition ASTs unchanged and uses direct
engine aliases. Both the current v234 runtime and that prototype passed:

| Check | Result for each runtime |
| --- | --- |
| Complete-line jitter behavior, bounds, source refusals, ownership and idempotence | 78 checks |
| Subsequent owned word echoes, exact geometry and real ending reduction | 90 checks; 4,413 real ending frames removed |
| Source frame-pose evidence and selection | 66 checks |
| Exact-font native jitter rendering and repeat conversion | 10 checks |

A cold prototype import from an unrelated directory also passed without loading
the engine or optional Pillow/fontTools/HarfBuzz backends. Annotations resolve,
canonical aliases agree and historical root record pickle lookup works. All
production runtime hashes and tracked tests remain unchanged. These are bounded
assessment checks, not a new full-suite or corpus validation claim.

For v235, add focused module-boundary coverage for canonical records, aliases,
retained object identity, complete paint/timing/pose evidence and the explicit
word-echo ownership handoff. Preserve the current behavioral and native checks;
existing historical AST comparisons concern archived releases and need not be
rewritten to follow the new module location. Validate cold installed delivery
and owned uninstall through the existing recursive module contract, then run the
full regression suite and fresh v234/v235 comparison of all 13 corpus tracks.
Expect identical subtitle bytes and complete statistics.

## After-assessment evaluation

The proposed jitter extraction needs no adapter, downstream repair, duplicated
proof or preparatory production release. Its existing responsibilities and data
flow can move intact. The separately reproduced masked-font cleanup failure is
the only new dedicated follow-up from this screening. The previously recorded
scrolling iterator contract remains independent work.
