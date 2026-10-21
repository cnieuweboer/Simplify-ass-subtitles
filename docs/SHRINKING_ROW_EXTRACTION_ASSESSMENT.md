# Shrinking glyph rows — bounded extraction assessment

Assessed against v244 (`2026.10.21.244`, commit `d634588`). Recommended next
release: **v245 — Extract complete shrinking glyph-row processing** into
`_simplify_ass/shrinking_rows.py`, with no intended behavior changes.

Give the existing shared `nearby_boundary_groups()` query a neutral owner in
`_simplify_ass/boundary_groups.py`, then move the complete operation. The helper
serves shrinking rows, boundary-glyph matching and departing-glyph matching;
none of those producers should own another's common query. Both changes fit
one release. No index hierarchy, generic timing service or new result type is
needed.

This assessment changes documentation only. The isolated prototype and fresh
evidence remain under ignored `validation/shrinking-row-assessment/`.

## Complete responsibility

Move nine existing functions and three frozen records unchanged: **237 definition
lines**, including decorators:

- `ShrinkingRowSource`, `ShrinkingRowIndex`, `ShrinkingRowProposal`.
- `_eligible_shrinking_row_families`, `_shrinking_row_geometry`,
  `_profile_shrinking_row_source`, `_index_shrinking_row_hold`,
  `_prove_shrinking_row_glyph`, `_index_shrinking_row_sources`,
  `_shrinking_row_owners`, `_adjust_shrinking_row_fade_handoffs`,
  `collapse_shrinking_glyph_rows`.

Keep source admission, current-policy held-caption freezing, complete literal and
exact-font anchor proof, unique ownership, interval extension and proved terminal
fade handoffs together. Preserve paint supplied by the held caption and existing
movement, scale, opacity, timing and ambiguity bounds. Do not turn the extraction
into new fade policy or generalized glyph reconstruction.

This boundary closes with one small shared query. Broader stacked-text and row
reconstruction still depend on several engine-owned collaborators. Full-lyric-copy
cleanup is also independently extractable after v244's shared-result preparation;
it need not be bundled with this different operation or pipeline stage. Choose
later extractions from their dependencies rather than prescribing a final tree.

## Incoming and outgoing dependencies

The sole production caller is `_prepare_source_text()`. It keeps level-one gating,
configuration, the preceding vector recovery and rotation normalization, working
map adoption, subsequent glyph-lifecycle/source-row processing and aggregate
`source_effects` accounting. Keep `shrinking_effects`' existing contribution; do
not replace the producer's unique-source-ID count with a different count policy.

The caller captures `timing_sources` **before** shrinking-row collapse. Later it
adopts resolved formatting only where the working event is still the same authored
object. Preserve this timing snapshot and exact-object handoff; an extended caption
must not overwrite the original timing evidence later fade consumers need.

| Outgoing dependency | Owner |
| --- | --- |
| Canonical Event | `event_model` |
| Supplied measurement owner/type | `font_metrics` |
| Complete authored glyph fitting | `glyph_placement` |
| Tokenization, interpretation and continuation replay | `ass_overrides` |
| Raw source tokens and successor edits | `event_operations` |
| Strict move/transform timing validation | `effect_validation` |
| Position, inline guard, placement and text layout | `caption_geometry` |
| Unrotated-state admission | `static_selection` |
| Visible text and held-caption freezing | `text_freezing` |
| Authored time serialization | `subtitle_document` |
| Shared fixed-boundary group query | `boundary_groups` |

After preparation there are eleven private owners plus the standard library and
no remaining engine-defined helper. The prototype graph is acyclic without reverse
engine imports, callbacks or forwarding adapters. No path-sensitive code moves;
font discovery remains with its existing measurement owner.

## Independently useful preparation

Move the unchanged **eleven-line** `nearby_boundary_groups()` helper to
`_simplify_ass/boundary_groups.py`, retaining its direct engine alias. The new owner
needs only standard-library bisection. Leave all index construction, payload
ownership and acceptance decisions with their producers.

Preserve the existing `(sorted_times, groups_by_time)` contract, inclusive
`.05 + 1e-6` search slack, authored timestamps, output order and original group-list
references. Query around one fixed boundary; do not chain nearby times, sort or
copy payloads, or coalesce separate repetitions. Missing keys still return an empty
result.

The query's 50 ms window is **not** a new matching tolerance. Shrinking-row owners
still apply exact/tiny-rounding boundary checks and reject real gaps and partial
overlap. The other two matchers retain their own timing and ownership proofs.
This shared read is useful independently of extraction, but is too small to require
a separate preparation release. Keep the module narrowly about this existing query.

## Data, caches, diagnostics and results

| Concern | Responsibility to preserve |
| --- | --- |
| Inputs | Borrow the source mapping, Event objects, styles/defaults, evidence, measurement context and supplied metrics. Do not install formatting or continuation caches on input events. |
| Resolution | Create local evaluated formatting, successor events and fresh token/move/transform lists; share source catalogs and immutable context as before. |
| Pass state | Families, glyph groups, frozen holds, boundary indexes, ownership claims, proposals, removal IDs and replacements belong to one invocation. Sorting peers changes local lists only. |
| Records | The three existing frozen records retain their intentional shallow sharing; no field, factory or mutability change. |
| Fonts | Exact-face discovery, shaping and measurement caches remain with the supplied FontMetrics. Normal cache population is permitted; the pass creates no new resource owner. |
| Diagnostics | The operation accepts no FontProcessingReport and gains no reporting role. Existing measurement/refusal behavior stays unchanged; pipeline reporting remains outside the module. |
| Results | Preserve the existing `(event_mapping, removed_source_count)` tuple, refusal mapping identity, insertion order and untouched Event identity. Accepted mappings and timing successors remain local. |
| Timing | The operation owns proved extension/terminal-fade edits. The caller owns pre-collapse source history, adoption and later synchronization. |

Do not move `PreparedSourceText`, the caller's historical timing map, later row
reconstruction or reporting into the new module. No adapter or ProcessingContext
is necessary.

## Fresh evidence and test bindings

The prototype moves thirteen unchanged definition ASTs: the twelve operation
members and the shared query. Other root definitions and all 29 existing private
sources remain unchanged. Complete manifests cover the 30-source v244 runtime and
32-source prototype; production hashes are pinned to `d634588`.

Current/prototype results match in **3,504 direct comparisons**: 73 scenarios,
three input orders, four measurement modes, two blur limits and resolved/unresolved
input states. These use real exact-font fitting under current paint policy; only
the explicit failed-fit mode forces refusal at the defining fit binding. Borrowed
source mappings are read-only. Complete output, counts, mapping/key order,
retained-object identity, fit attempts and repeat decisions match; input values
and formatting-cache identity remain unchanged. Repeated calls remove nothing
further in this bounded set.

Twenty additional shared-query comparisons preserve group-list identity with
read-only indexes and payload maps, authored times, missing keys and fixed-window
rather than chained admission. Cold refused processing needs neither the engine
nor optional font backends. Supported processing with exact Arial regular also
runs before importing the engine. Canonical aliases, annotations and historical
root record lookup pass.

Two focused whole conversions have identical subtitle bytes, complete statistics
and font reports, with no missing required fonts. They use the actual current
paint/timing policy, without the archived fixture's historical fade substitution.
Existing effect-continuation checks also pass for both runtimes: **179,958
assertions across 3,144 effect cases each**.

Two test-only binding changes are needed for that existing check: interpreter
observers must include the defining shrinking-row consumer, and its existing
recording/failed-fit double must be installed at the actual imported fit binding.
Keep those changes with test helpers/consumers. Do not add production forwarding
or restore historical timing policy to accommodate a spy. Archived builders are
reused without obsolete single-file helper-count or trace requirements.

These are bounded assessment checks, not a new full-suite, corpus or native Windows
run. Implementation should add focused module/ownership and shared-query checks,
including immutable inputs, shallow records, refused/ambiguous/incomplete rows,
exact-font anchors, held paint, transparent predecessors, actual gaps and timing
snapshot adoption. Render changed-owner examples across entrance and fade
boundaries. Run the full suite and strict-font corpus comparison, requiring
unchanged output bytes and complete statistics. Check recursive delivery,
installed source execution and rollback/retry/uninstall for both new modules.
Keep the production wrapper and reporting unchanged.

## After-release evaluation

Confirm that one module owns the complete shrinking-row proof and handoff, the
shared query owns no producer's indexes, and the source-preparation caller retains
historical timing and reporting. Broaden review only if extraction needs production
adapters or reveals conflicting timing/cache ownership. None was needed or exposed
by the prototype, so no new dedicated corrective review is indicated.

The scrolling iterator contract and global API/index reviews remain separate.
