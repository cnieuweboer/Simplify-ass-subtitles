# Visibility ownership contracts

The v156 review identified five passes that returned events while writing into
pipeline-owned visibility. The first two were migrated in v156 and the remaining
three in v167. All five now borrow visibility and return sparse assignments.
These contracts were reviewed for v168.

| Pass | Result | Local reads and writes |
| --- | --- | --- |
| `collapse_full_lyric_copies()` | `TextVisibilityResult(events, removed_count, visibility_updates)` | An owned delta and `ChainMap` overlay let later clusters read accepted spaced captions. |
| `collapse_progressive_text_reveals()` | `TextVisibilityResult(events, removed_count, visibility_updates)` | The replacement recorder writes an owned delta; accepted intervals retain updates even when preserved gaps leave removal count at zero. |
| `collapse_translated_phase_rows()` | `TextPhaseRowsResult(events, removed_count, rows, visibility_updates)` | Proposals are collected before acceptance; no read-through overlay is needed. |
| `collapse_fragment_phase_rows()` | `TextPhaseRowsResult(events, removed_count, rows, visibility_updates)` | Accepted rows and caption assignments are returned together for reconstruction and timing consumers. |
| `merge_shared_interval_rows()` | `SharedIntervalRowsResult(events, rows_joined, tails_retained, visibility_updates)` | One pass-owned `ChainMap` overlay spans four bounded rounds; generated captions and tail IDs are readable in later rounds. |

`_consolidate_text_events()` adopts the first two results. `_finalize_text_layout()`
adopts the other three. The pipeline applies each visibility delta before the next
consumer and adopts returned row evidence where present. Shared-interval context
borrows the local overlay, not the caller's writable map. Its private one-round
helper accepts a pass-owned mutable mapping explicitly.

Result records have frozen bindings but caller-owned mutable collection payloads.
Input events and visibility are borrowed read-only. Deltas contain accepted
caption assignments, including equal-value writes; they are not computed by
copying or comparing the entire source history. Removed source entries are retained
as historical evidence. Event order, retained identity, paint, geometry, timing,
gaps, IDs and count meanings follow the existing matching decisions.

Pending visibility cannot leak to the caller before successful completion.
Explicit font reporting has a different contract: its accepted joins and selective
discoveries accumulate directly, including work preceding a later failure, and
are not rolled back. See ROW_GEOMETRY.md.

Other visibility writes have explicit owners:

- `_freeze_event_effects()` creates and returns its dictionary in `FrozenTextEvents`.
- Reconstruction writes into `RowReconstructionEdits.visibility_updates`, reads
  through a local overlay and returns the delta for the pipeline to apply.
- Source collection and phase indexes create pass-local `words` dictionaries.
  Source opacity evidence remains separate from these visibility mappings.
- Pipeline `visible_map.update(...)` calls apply accepted changes to its own map.

Lookup-only and read-only mapping regressions exercise all five contracts without
whole-history traversal. Failure tests verify isolation of pending updates.
FINAL_STRUCTURAL_REVIEW.md records the v167 migration; README.md and validation/
record current release checks.
