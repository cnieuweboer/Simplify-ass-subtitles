# Moving-glyph sequences — bounded extraction assessment

Implemented in [v242](MOVING_GLYPH_EXTRACTION.md). The evidence below describes
the historical assessment.

Assessed against v241 (`2026.10.20.241`, commit `e05d357`). Recommended next
release: **v242 — Extract complete moving-glyph sequence processing** into
`_simplify_ass/moving_glyphs.py`, with no intended behavior changes.

Two shared helper moves establish the remaining dependencies. They have useful
owners independently of this extraction, but are small enough to include as the
first preparatory commit of the same release. A separate preparatory release is
not necessary. Production code is unchanged by this assessment; the prototype and
fresh evidence remain under ignored `validation/next-extraction-assessment/`.

## Boundary and alternatives

Move seventeen existing functions and two frozen records unchanged: 313
definition lines including decorators. Keep the complete operation together:

- `MovingGlyphContext`, `MovingGlyphChain`.
- `_moving_glyph_source_families`, `_moving_glyph_geometry`,
  `_moving_glyph_paint`, `_index_moving_glyph_sources`,
  `_index_retained_moving_glyphs`, `_retained_moving_glyph`,
  `_group_moving_glyph_sequences`, `_moving_glyph_group_fits`,
  `_matching_moving_glyph_fades`, `_prove_moving_glyph_chain`,
  `_match_moving_glyph_prefix`, `_collect_moving_glyph_overlays`,
  `_match_moving_glyph_exit`, `_render_moving_glyph_caption`,
  `_propose_moving_glyph_sequence`, `_apply_moving_glyph_proposals`,
  `collapse_moving_glyph_sequences`.

This operation proves stationary/moving/stationary text chains or complete
recorded exits, then reconstructs the held caption. Whole-fragment destinations
can prove placement directly; individual glyph runs require exact measured
advances and an authored word anchor. Preserve that distinction and optional
metrics, complete coverage, unique ownership, font switches, boundary flashes,
entrances and absorbed-exit timing. Do not replace movement with a new placement
heuristic or broaden its bounds during extraction.

Sliced-text processing is another plausible subsequent subsystem, but still
depends on the two shared helpers and `rectangle_clip()`. The larger stacked-text
subsystem remains coupled to source-palette consumers, lyric coalescing and
several engine-owned paint/geometry services. Moving it now would require a
broader ownership decision. Moving-glyph sequences have a smaller complete
dependency closure and a clear existing caller.

## Incoming and outgoing dependencies

The sole production caller is `_finish_text_effect_sequences()`. It retains the
scale-trail condition, source-event selection, optional metrics, aggregate removal
count, subsequent karaoke paint normalization and final exact-position phase
consolidation. The new module must not import or call that orchestration.

| Dependency | Owner after the preparatory moves |
| --- | --- |
| Canonical events and local dataclass successors | `event_model`; standard-library dataclasses |
| Source interpretation, continuation replay and raw override tokens | `ass_overrides`, `event_operations` |
| Literal font-span reads | `event_operations`, as described below |
| Strict transform/move evidence and supported opaque-text state | `effect_validation`, as described below |
| Position/layout comparisons and upright-state checks | `caption_geometry`, `static_selection` |
| Visible literal extraction | `text_freezing` |
| Exact fragment-anchor fitting and font resources | `glyph_placement`, borrowed `FontMetrics` |
| Source paint, caption/tag serialization and time formatting | `caption_rendering`, `subtitle_document` |

The resulting module depends on eleven existing private owners and the standard
library. No outgoing runtime helper remains defined in the engine. The isolated
prototype's private graph is acyclic, without reverse engine imports, callbacks
or production forwarding. Cold import from an unrelated directory loads neither
the engine nor Pillow, fontTools or HarfBuzz. No `__file__` path logic moves.

## Independently useful preparation

Move these two helpers unchanged, totaling thirty definition lines, with direct
engine aliases:

1. **`literal_font_spans()` → `event_operations`.** This is a source-event read,
   not movement-family matching or a general layout proof. It owns a local
   formatting copy, parser continuation and span accumulator; it borrows text,
   defaults and styles without installing a cache. Preserve empty-font reset
   semantics, merging adjacent equal-font literals, and refusal of unsupported
   overrides after literal content. Add only the standard `re` import and the
   existing interpreter's `apply_override` binding to that owner.
2. **`opaque_text_effect_state()` → `effect_validation`.** This is a shared
   predicate over borrowed resolved formatting: opaque fill with the existing
   supported glyph/outline, clipping, origin and shadow conditions. It introduces
   no imports, state, cache or diagnostics. It does not prove that every paint
   channel is opaque or replace each caller's family-specific admission.

Both serve several independent consumers, including sliced text and fade
handling; the predicate also serves translated and boundary-glyph processing.
Neither should become owned by the moving-glyph subsystem and imported by those
siblings. Existing owners already provide their required dependencies, so this
does not justify a new utility module, new context or general span model.

## Data, caches, diagnostics and results

| Concern | Responsibility to preserve |
| --- | --- |
| Inputs | Borrow retained events, visible-text map, source-event map, defaults/styles, measurement context and optional metrics. Do not mutate source or retained caches. |
| Source resolution | Source formatting/continuation is evaluated into local successor events; caller catalogs and measurement context remain shared. Do not replace this with cache installation on the originals. |
| Pass data | Source-family sets, static/move/fade indexes, retained-caption lookup, destination groups and boundary lookup belong to one invocation. Sorting affects private peer lists. |
| Records | Preserve canonical identities and shallow freezing of `MovingGlyphContext` and `MovingGlyphChain`; their event references and mutable containers retain current sharing. |
| Measurements | Borrow the existing metrics owner. Font discovery, handles, measurement caches and existing font diagnostics stay there; the operation adds no diagnostic/report owner. |
| Proposals | Source-ID sets, ownership counts, accepted proposals and replacement output stay local. Reject every competing ownership claim before applying replacements. |
| Results | Return the existing `(events, removed_count)` tuple. Preserve the original list on refusal, untouched event identity, source-index sorting after acceptance and actual list-length reduction. |
| Reporting | Caller retains stage order, aggregate statistics, font-report lifetime and subsequent geometry/paint handoffs. No new counters or CLI settings. |

## Fresh evidence and implementation acceptance

The isolated prototype moves all nineteen operation definition ASTs unchanged,
along with the two unchanged shared helper definitions. Remaining root definitions
are unchanged. Production stays pinned to `e05d357`; complete manifests cover the
26-source current runtime and 27-source prototype. Cold import and acyclicity
checks pass.

Current v241 and the prototype produce identical complete results, counts,
original-list decisions and untouched-object identity across **675 direct
comparisons**: 75 scenarios, three input orders and three metric modes (absent,
exact real Arial regular, unavailable). Source events/maps remain unchanged.
Historical movement-test builders supply variations; their old single-file
coverage and call-count assertions do not define the new architecture.

Both runtimes also pass these fresh current checks:

| Check | Assertions for each runtime |
| --- | --- |
| Inline interpretation/continuation | 51,222 |
| Context and borrowed-input contracts | 2,500 |
| Effect continuation, including moving-chain builders | 179,958 across 3,144 effect cases |

Interpreter observers in the prototype include the defining consumers of
`literal_font_spans()` and `collapse_moving_glyph_sequences()`. This is a test-only
binding update, not a reason for production forwarding. Keep historical harnesses
archived; reuse builders without restoring obsolete source-file helper counts.

These focused checks support the boundary; they are not new full-suite or corpus
validation. Implementation should add module-contract coverage for aliases,
records, independent pass buffers, supported/refused chains, optional exact
metrics, proposal arbitration/counts, source ownership and cold source/installed
execution. Preserve caller handoff and repeat-conversion behavior. Run the full
current suite and strict-font corpus comparison, requiring unchanged bytes and
complete statistics, plus relevant native rendering and recursive delivery/update
rollback/retry/uninstall checks. Keep the batch wrapper and pipeline unchanged.

## After-release evaluation

Confirm that moving-glyph admission, source-chain proof, exits and replacement
have one owner while the text-effect caller retains orchestration. Confirm that
the shared reads still serve sibling consumers directly through their own owners.
The assessment needed no adapters, duplicated proofs or local production
exceptions and uncovered no dedicated corrective review. The separate scrolling
iterator contract and global API/index reviews remain deferred; Pillow pixel
compatibility was resolved in v241. Reassess the next subsystem after extraction
rather than committing to a final module hierarchy now.
