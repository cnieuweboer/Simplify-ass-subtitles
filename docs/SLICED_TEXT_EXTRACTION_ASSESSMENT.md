# Sliced-text sequences — bounded extraction assessment

Implemented in [v243](SLICED_TEXT_EXTRACTION.md). The evidence below describes
the historical assessment.

Assessed against v242 (`2026.10.20.242`, commit `08e9b25`). Recommended next
release: **v243 — Extract complete sliced-text sequence processing** into
`_simplify_ass/sliced_text.py`, with no intended behavior changes.

V242 established the shared literal-font and opaque-text validation owners. Only
`rectangle_clip()` remains an engine-defined dependency. Move that shared read
into caption geometry first, then extract the operation in the same release.
The six-line preparatory move is independently useful but does not warrant a
separate release. This assessment changes documentation only; its isolated
prototype and fresh reports remain under ignored `validation/sliced-text-assessment/`.

## Complete boundary

Move sixteen existing functions and two existing frozen records unchanged,
totaling 263 definition lines including decorators:

- `SlicedTextIndex`, `SlicedTextEvent`.
- `_eligible_sliced_text_families`, `_sliced_text_layout`, `_sliced_text_paint`,
  `_profile_sliced_text_event`, `_sliced_text_final_state`,
  `_index_sliced_text_pulse`, `_index_sliced_text_tile`, `_index_sliced_text_event`,
  `_prove_sliced_text_strip_phases`, `_propose_sliced_text_caption`,
  `_propose_sliced_text_replacements`, `_accept_sliced_text_ownership`,
  `_group_sliced_text_cues`, `_adjust_sliced_text_cue_timing`,
  `_adjust_authored_sliced_text_timing`, `collapse_sliced_text_sequences`.

This is one complete responsibility: replace a proved tiled entrance, opaque
hold and tiled exit with its recorded caption. Keep family admission, source
resolution, complete full-width strip coverage, anchor/paint agreement,
translucent-pulse ownership, conflicting-claim refusal, caption reconstruction
and authored-lyric timing adjustment together. Both complete strip phases remain
necessary. Preserve existing bounds and conservative refusal rather than adding
or generalizing heuristics during extraction.

Progressive reveals also use rectangular clips but additionally share their
result record with another engine operation. Larger stacked-text processing
still has source-palette consumers and several engine-owned collaborators.
Sliced text now has a simpler complete dependency closure; this recommendation
does not prescribe their eventual ownership or a final module hierarchy.

## Incoming and outgoing dependencies

The sole production caller is `remove_source_fragment_effects()`. It retains
unresolved-source isolation, original row/visibility evidence, the preceding
fragment proofs and backed-glyph pulse call, and the `SourceFragmentRemoval`
result. Its aggregate remains `len(removed) + pulses + slices`. No stage, CLI,
counter, report or later row-assembly responsibility moves.

| Dependency | Existing owner after preparation |
| --- | --- |
| Canonical events and local record successors | `event_model`; standard-library dataclasses |
| Source interpretation, defaults and continuation replay | `ass_overrides` |
| Raw tokens, literal font spans and successor edits | `event_operations` |
| Strict transform/move validation and supported opaque-text state | `effect_validation` |
| Positions, rectangular clips, nominal height and layout identity | `caption_geometry` |
| Visible literal extraction | `text_freezing` |
| Source paint and reconstructed caption serialization | `caption_rendering` |
| Authored time serialization | `subtitle_document` |

The operation depends on eight existing private owners and the standard library.
There is no direct FontMetrics dependency or new measurement service. It borrows
the recorded canvas for strip coverage and passes through measurement context
for rendering. Font discovery, resources, caches and diagnostics stay with their
existing owners.

## Independent preparation

Move `rectangle_clip()` unchanged into `caption_geometry`, retaining a direct
engine alias. That module already owns conservative event geometry and has the
required Event and `re` imports; add the canonical `NUMBER` pattern from the
existing interpreter. Do not replace it with another parser or consolidate the
position regexes as part of this move.

The helper reads borrowed resolved formatting and returns the existing source
coordinate tuple or refusal. It does not resolve or cache an event, infer a
canvas, transform coordinates or decide ownership. Preserve numeric syntax,
positive extents and inverse/vector/malformed-clip behavior exactly. Its existing
consumers include supporting drawings, caption panels, outline strips,
progressive reveals and sliced text, so none should import it from the sliced
text subsystem. No new utility module or adapter is needed.

## Ownership to preserve

| Concern | Owner and contract |
| --- | --- |
| Inputs | Borrow events, source defaults/styles, continuation, evidence and measurement context. Preserve input formatting and object identity. |
| Source profiles | Evaluate source formatting into local successor events. Their catalogs and measurement context remain shared; parsing does not install caches on original events. Move/transform lists and layout keys belong to the local profile. |
| Pass state | Each invocation owns eligible families, held-caption/strip/pulse indexes, resolved profiles, coverage groups and proposals. Sorting changes private peer lists rather than the caller's event list. |
| Records | Keep both canonical frozen records and their shallow sharing; do not deep-freeze buffers or consolidate dataclasses. |
| Timing | The operation owns its existing complete-caption, anchor-ordered authored-comment proof and local timing successors. It does not absorb general fade synchronization or neighboring-cue policy. |
| Paint | Require the existing unanimous held paint and compatible complete strip endpoints. Shared rendering owns serialization/paint policy. Keep original inline font switches and matching translucent-pulse requirements. |
| Application | Count ownership claims before accepting proposals, retain uncertain groups, preserve untouched event identity, and sort accepted output by source index. |
| Result/reporting | Return the same `(events, removed_count)` tuple, with actual list-length reduction. Refusal returns the original list. Caller retains row adoption, aggregate statistics and diagnostics. |

## Fresh evidence

The isolated prototype moves all nineteen definitions unchanged: the operation's
eighteen definitions and the shared rectangle read. Other root definitions and
all existing caption-geometry definitions remain unchanged; the other 25 private
sources remain byte-identical. Complete manifests cover the production
27-source runtime and 28-source prototype, pinned to `08e9b25`.

The private import graph is acyclic, with no reverse engine import, callback or
production forwarding. Cold supported/refused processing from an unrelated
directory loads neither the engine nor Pillow, fontTools or HarfBuzz. Canonical
record aliases, annotations and historical root pickle lookup pass.

Current v242 and the prototype match in **426 direct comparisons**: 142 scenarios
and three input orders. Complete output, removal count, original-list and
retained-object identity decisions match. Borrowed inputs and formatting identity
are unchanged; repeat results are stable with no additional removal. Fourteen
separate rectangular-clip reads preserve results/refusals and borrowed state.
Historical sliced-text builders supply variations, without reviving old helper
counts, single-file trace assertions or historical paint policy.

Both runtimes also pass these fresh current checks:

| Check | Assertions for each runtime |
| --- | --- |
| Source-fragment isolation/adoption | 39 |
| Current paint handoffs | 177 |
| Effect continuation, including sliced-text builders | 179,958 across 3,144 effect cases |

The prototype's interpreter observer includes the defining consumer of
`collapse_sliced_text_sequences()`. That test-only binding update preserves
observation without adding forwarding in production. Caller-level observers
remain on the actual engine invocation.

These focused runs support the boundary; they are not new full-suite, corpus or
native Windows validation. Implementation should add module coverage for both
records, local indexes, borrowed inputs, coverage/paint/ownership refusals,
authored timing and count/identity contracts, plus cold source/installed
processing. Run the full current suite and strict-font corpus comparison,
requiring identical output bytes and complete statistics. Include relevant native
rendering, recursive manifests, updater rollback/retry and owned uninstall.
Keep the wrapper, pipeline and reporting unchanged.

## After-release evaluation

Confirm that strip/hold/exit proof and authored timing have one owner while
source-fragment orchestration and shared geometry retain their responsibilities.
No adapters, duplicated proofs, local production exceptions or downstream repairs
were needed in the assessment. No new dedicated corrective review was identified.
The scrolling iterator contract and global API/index reviews remain separate;
Pillow compatibility was resolved in v241. Reassess the next boundary after this
extraction.
