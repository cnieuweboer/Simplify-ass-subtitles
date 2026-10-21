# Progressive text reveals — bounded extraction assessment

Assessed against v243 (`2026.10.20.243`, commit `8a731cc`). Recommended next
release: **v244 — Extract complete progressive text-reveal processing** into
`_simplify_ass/progressive_reveals.py`, with no intended behavior changes.

The remaining engine-defined dependency is `TextVisibilityResult`, already shared
by progressive reveals and full-lyric-copy cleanup. First give that unchanged
record a neutral owner in `_simplify_ass/text_visibility.py`, then extract the
operation in the same release. This is a concrete shared value contract, not a
new result hierarchy or general visibility service. Leave other result types
and the full-copy algorithm where they are.

This assessment changes documentation only. The isolated prototype and fresh
reports remain under ignored `validation/progressive-reveal-assessment/`.

## Complete boundary

Move thirteen existing functions and three frozen records unchanged, totaling
246 definition lines including decorators:

- `ProgressiveRevealPrefix`, `ProgressiveRevealBand`, `ProgressiveRevealCaption`.
- `_eligible_progressive_reveal_families`, `_parse_progressive_reveal_prefix`,
  `_profile_progressive_reveal_event`, `_index_progressive_reveal_families`,
  `_build_progressive_reveal_chains`, `_progressive_reveal_finishing_holds`,
  `_progressive_reveal_strip_band`, `_progressive_reveal_strips_cover_band`,
  `_progressive_reveal_strip_coverage`, `_select_progressive_reveal_caption`,
  `_progressive_reveal_intervals`, `_record_progressive_reveal_replacements`,
  `collapse_progressive_text_reveals`.

This is one complete responsibility: prove increasing visible prefixes of a
complete caption, require a finishing hold and complete temporal strip coverage,
then reconstruct its representative foreground across the original covered
intervals. Keep span interpretation, chain admission, band coverage, hold/paint
selection, transparency restoration, interval preservation and accepted visibility
deltas together. Preserve actual gaps, refusal conditions, bounds and source-order
tie breaking; do not redesign reveal matching while moving it.

V243 closed the shared rectangular-clip dependency. Shrinking-row processing
still needs ownership for a boundary-group lookup shared with other matchers;
larger stacked-text processing retains several engine-owned collaborators.
Progressive reveals now have the simpler complete closure. Do not prescribe the
remaining module hierarchy from this choice.

## Incoming and outgoing dependencies

The sole production caller is `_consolidate_text_events()`. It retains the
level-one condition, stage after word-echo removal, event adoption, aggregate
count and immediate `visible_map.update(result.visibility_updates)` before font
decoration and later consumers. The same caller adopts full-copy results at their
existing later stage. Neither adoption moves into the shared record or producer.

| Dependency | Existing or explicitly shared owner |
| --- | --- |
| Canonical Event | `event_model` |
| Continuation record | `ass_overrides` |
| Complete static-span interpretation and geometry key | `static_objects` |
| Position, inline guard, rectangular clips and nominal height | `caption_geometry` |
| Resolved-state comparison and successor edits | `event_operations` |
| Unrotated-state proof | `static_selection` |
| Source paint and caption/tag serialization | `caption_rendering` |
| Authored time serialization | `subtitle_document` |
| Existing shared result record | `text_visibility` |

The operation depends on nine private owners and the standard library. The
shared result module depends only on dataclasses and the canonical Event model.
No runtime helper remains engine-defined. The prototype graph is acyclic without
reverse engine imports, callbacks or production forwarding. Cold supported and
refused processing loads neither the engine nor Pillow, fontTools or HarfBuzz.
No font discovery or path-sensitive code moves.

## Small independently useful preparation

Move the existing eleven-line `TextVisibilityResult` definition unchanged into
`_simplify_ass/text_visibility.py`, retaining its engine alias. Both existing
producers must construct that same canonical class, with unchanged positional
fields, frozen bindings and shallow container sharing. Preserve historical root
pickle lookup; accept the natural defining-module change.

This neutral owner prevents full-copy cleanup from depending on progressive-reveal
implementation, and prevents the new reveal module from importing the engine.
It does not move unrelated result dataclasses into a collection, add inheritance,
validation, cache state, adoption methods or a ProcessingContext. The independent
shared contract justifies this small module; a separate release is unnecessary.

## Data, caches, diagnostics and results

| Concern | Responsibility to preserve |
| --- | --- |
| Inputs | Borrow events, visibility lookup, defaults/styles, evidence and measurement context. Do not copy/traverse the visibility history or mutate event caches. |
| Span proof | Borrow canonical static-span signatures/continuations; create local formatting copies and temporary event views for layout/paint comparisons. Static interpretation retains its existing owner. |
| Pass data | Eligible families, profiles, chains, temporal strip changes, active bands, interval buffers, removals and replacements belong to one call. |
| Records | Keep the three reveal records frozen with existing sharing. The shared result remains the same existing type; no new field or default is introduced. |
| Paint | The producer owns finishing-hold evidence and opacity/duration/source-order selection. Shared rendering retains policy/serialization. Preserve source fill transparency and its coupled contour restoration. |
| Measurements/diagnostics | No direct FontMetrics instance, font cache, handle or diagnostic owner is introduced. Pass through the chosen measurement context. |
| Results | Preserve producer-specific removal counting, source-ID replacement, output list ordering, untouched event identity and the existing no-family early-return list identity. The result stores payload references rather than copying them. |
| Visibility | Each producer owns its sparse per-call delta, including accepted equal-value assignments. The caller owns adoption and retains unrelated historical entries. A zero removal count can still carry necessary updates and changed caption text when gaps survive. |
| Failure | Partial local work must not leak into caller events or visibility if a later caption fails. No automatic adoption occurs inside the result record. |

Do not infer a no-op from `removed_count == 0`, prune equal-value delta writes,
merge gaps, or combine these two producers' matching/paint algorithms merely
because they share a result type.

## Fresh evidence and test bindings

All seventeen moved definition ASTs are unchanged in the prototype: sixteen
operation definitions plus the shared result. Remaining root definitions and all
27 existing private sources are unchanged. Complete manifests cover the pinned
28-source production runtime and 30-source prototype.

Current v243 and the prototype match in **1,008 direct comparisons**: 84 scenarios,
three input orders and four visibility-map modes. Complete result payloads,
sparse deltas, caller-adopted visibility, original-list/retained-object identity
and repeat decisions match. Borrowed events, state identity and visibility remain
unchanged. Historical progressive-reveal builders provide variations without
reviving their obsolete single-file coverage and helper-count requirements.

Cold supported/refused proofs, canonical aliases/annotations, frozen shared
result bindings and historical root pickle lookup pass. Both independent
producers construct the same class after the move.

Both runtimes also pass these fresh checks:

| Check | Assertions for each runtime |
| --- | --- |
| Text visibility ownership, zero-count deltas and failure isolation | 53 |
| Parser effect consumers, including progressive scenarios | 9,894 |
| Native contrast reconstruction fallback | 96 |

The visibility-ownership test's failure injection must target the defining
producer module, resolved from its function, instead of assuming every helper
lives in the engine. The prototype makes that test-only binding adjustment while
preserving all assertions. No production adapter is needed.

One synthetic scenario admits further merging on a repeated direct call because
the first result becomes new chain evidence. That behavior matches between
v243 and the prototype. Complete conversion of the same scenario already settles
to one caption in one run, and a second full conversion is byte-identical for
both runtimes. Preserve this distinction; do not add a pass-local fixed-point
requirement to a structural extraction. No corrective fix is indicated by this
bounded check.

These focused checks are not new full-suite/corpus or native Windows validation.
Implementation should cover shared canonical results from both producers,
shallow ownership, supported/refused reveals, incomplete temporal bands, gaps,
transparent paint, sparse/zero-count deltas, exception isolation and cold
source/installed execution. Verify the unchanged caller adoption boundary and
relevant native rendering. Run the full current suite and strict-font corpus
comparison, requiring identical output bytes and complete statistics. Check
recursive delivery of both modules, updater rollback/retry and owned uninstall.
Keep the production wrapper, pipeline configuration and reports unchanged.

## After-release evaluation

Confirm that reveal proof/reconstruction has one owner, the existing shared
result has a neutral owner, and callers retain visibility adoption and stage
orchestration. No adapters, duplicated proofs, local production exceptions or
downstream repairs were needed. The bounded repeat investigation did not expose
a complete-conversion regression. No new dedicated corrective review was
identified. The scrolling iterator contract and global API/index reviews remain
separate; Pillow compatibility was resolved in v241.
