# Consolidated static phase merging — v186

`merge_static_timed_copies()` now owns both text-stage and final static phase
merging. Its single `_merge_static_phase_round()` implementation replaces the
separate v185 late merger and the older merger's duplicate matching algorithm.
The existing two-argument entry point remains usable; stage ownership is supplied
through keyword arguments. The Windows launchers and statistics schema are
unchanged. All contributions still use `static_merged`.

## One proof, explicit stage ownership

The shared core compares every static literal span through `static_object_key()`.
It retains exact text, style, actor, margins, document measurement, parser
continuation, paint and geometry. It joins only touching lifetimes; no gap is
bridged and overlapping copies retain their multiplicity. It settles the same
proof to a fixed point because joining one family can remove an obsolete ordering
obstacle for another.

Actual event-list slots govern record ordering at both stages. Source indices
remain identities and never determine compositing. Numeric layer spellings such
as `0`, `00`, `+0` and `-0` belong to the same renderer layer for matching and
ordering. Invalid candidate layers remain unmerged; malformed peers are not
silently omitted from the ordering proof.

For finished objects, moving each constituent phase into the retained slot is
checked during that phase's own lifetime. A peer ending at the handoff cannot
obstruct a later phase. An active peer blocks movement unless the existing
exact-font conservative bounds prove spatial separation. Unmeasured, moving,
clipped, drawing, inline-layout or other unsupported extents stay obstructive.
The v185 measured-text exclusions remain: blur, edge blur, shadows, extra
spacing, underline/strikeout, opaque text boxes and automatic wrapping beyond
a single glyph.

### Before shared-interval row reconstruction

The text/vector caller supplies `row_sources=animated_sources`. This is the same
borrowed eligibility set used by the immediately following consumer. The merger
keeps distinct eligibility classes separate and, for eligible fragments, keeps
row membership separate. Eligibility is exactly the consumer's semantic rule:
`event.lyric or event.source_index in animated_sources`. Raw lyric flags need not
match when both records already have the same eligibility and row.

That consumer infers row spacing and ownership from event slots as well as
visibility. Consequently eligible pending rows retain the whole proposed
interval's slot constraints. Spatially separate peers can still participate in
row reconstruction; their pixel separation alone does not authorize an earlier
join. Finished/noneligible objects already use the improved lifetime-specific
ordering proof in this caller. No protective flags are cleared and no eligibility
set is broadened to make a merge apply.

The source handoff was tested rather than inferred. Moving the merger wholly
after row reconstruction increased the remaining fragments. Applying all final
ordering freedoms before it changed reconstructed row geometry. Neither
experiment is shipped. The retained handoff canonicalizes identical held paint
while preserving the roles and slot boundaries still consumed downstream.
The focused actual-conversion check compares the consumer's complete input,
visibility map and source eligibility against immutable v185.

### After final caption/support reconstruction

The final caller supplies `text_only=True` and no pending row context. Source
proof consumers have finished, so all eligible text phases use the improved
ordering proof. Drawings remain with the support owner: this merger does not
change committed drawing identities, associations or support counts. The earlier
text/vector caller retains its existing static-drawing admission.

A final invocation is still necessary because shared-interval reconstruction and
later support/paint restoration can create new matching phases. It uses the
same algorithm rather than another cleanup implementation.

## Ownership

The survivor is the actual earliest retained list record, with its original
source identity. Timing successors borrow its styles, formatting cache, parser
continuation, measurement and historical evidence. Unchanged records retain
identity. Input events, visibility, source eligibility and styles are not edited.
Historical evidence does not acquire a claim of opacity/coverage over the new
union interval; original source documents remain separately available.

## Verification

```sh
python validation/run_backend_check.py --backend windows tests/check_static_phase_handoff.py
python validation/run_backend_check.py --backend windows tests/check_late_static_phases_render.py
python validation/run_review_checks.py
python validation/run_static_phase_consolidation_corpus.py
```

The focused handoff check exercises pending versus completed ownership, distinct
rows and eligibility, source-ID collisions, reordered phases, expired/active
peers, drawing ownership, numeric layer aliases and regular/bold-italic/different
font and size variations. It observes both actual callers using the same entry
point. The existing phase checks continue to validate gaps, overlaps, changing
paint/layout, exact interval multiplicity and 36 native-resolution pixel pairs.
Historical release scope audits use immutable snapshots rather than dictating
current helper names or placement.

The full corpus runner verifies v185 source/engine/output hashes and freshly
regenerates all nine outputs. It requires identical bytes and statistics,
checks exact font availability, and verifies that no final static phases remain
mergeable. All original assets and generated reports remain ignored local data.
Fresh reports are under `validation/static-phase-consolidation-corpus/windows`
and `validation/static-phase-handoff`.

Older pass-specific whole-file audits explicitly bind immutable v185
finalization policy inside their historical comparison contexts. Their captured
current pass implementations and ownership checks remain live; unmodified v186
handoff, full-corpus and render checks cover the changed architecture.

This release consolidates phase merging only. Complete-copy semantics,
caption/background ownership and final tag compaction retain their separate
planned releases. Whole-file second-conversion idempotence is not claimed.

Fresh v186 validation passed all 69 suite scripts, 67 focused handoff checks,
1,798 phase checks (including 36 pixel-identical render pairs), all nine
byte-identical/statistics-identical corpus comparisons, 72 PowerShell reporting
checks and the MKV extraction/simplification/remux/font-sync smoke check. No
required fonts were missing. Overlord remains at 2,194 parsed records with its
27 useful late joins preserved.

An alternating seven-run microbenchmark over the settled 2,194-record Overlord
output measured approximately 16 ms additional text-stage work and 6 ms
additional final-stage work versus v185 under concurrent validation load. These
small absolute differences are not a statistically controlled end-to-end speed
claim. The change removes duplicate algorithm maintenance and adds correctness
contracts; it is not presented as a performance optimization.
