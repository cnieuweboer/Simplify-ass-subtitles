# Frame-echo processing extraction assessment

Assessed against v232 (`2026.10.20.232`, commit `2208f9c`). Recommended next
release: **v233 — Extract frame-echo processing**. The v232 preparation closed
this dependency boundary; no additional preparatory production change is needed.
Production sources and tracked tests remain unchanged in this assessment.

## Boundary and responsibilities

Move sixteen existing functions and five frozen records, totaling 277 definition
lines including decorators, into `_simplify_ass/frame_echoes.py`:

- `FrameEchoContext`, `FrameEchoFamily`, `FrameEchoFrame`, `FrameEchoHold`,
  `FrameEchoPaintProfile`.
- `_index_frame_echo_families`, `_frame_echo_follows_motion`, `_replace_frame_echo`,
  `_recorded_frame_echo_motion`, `_frame_echo_is_exit`, `_frame_echo_candidates`,
  `_isolated_frame_echo_times`, `_blocked_frame_echo_times`,
  `_prepare_frame_echo_family`, `_profile_frame_echo`, `_match_flattened_frame_echo`,
  `_advance_flattened_frame_echo`, `_frame_echo_paint_profile`,
  `_match_stacked_frame_echo`, `_collapse_frame_echo_family`,
  `collapse_frame_text_echoes`.

This is one cohesive operation: prove that replicated frame text represents an
exit echo, then replace it using the established preceding caption. Preserve the
two cooperating proof paths: corresponding multilayer paint stacks, and already
flattened copies following an isolated opaque hold. Candidate preparation,
recorded-source motion, temporal ambiguity, paint continuity, replacement
construction and final application belong together.

Keep all 21 names as direct engine aliases, preserving signatures/defaults and
canonical record identity. Allow the natural defining-module change; historical
root pickle lookup remains available through the aliases. Do not rewrite
`__module__`, alter shallow freezing or consolidate the records with other results.

## Incoming and outgoing dependencies

There is one external engine consumer: `_prepare_stacked_text_copies()` calls
`collapse_frame_text_echoes()` before its held-paint reduction and copy grouping.
Keep that invocation, input selection and aggregate contribution count in the
engine. Do not move stacked-copy reconstruction merely because it calls echoes.

| Dependency | Existing owner |
| --- | --- |
| Canonical `Event` annotation | `event_model` |
| Override-block regex | `ass_overrides` |
| Position, inline-layout guard, nominal height and exact layout key | `caption_geometry` |
| Raw original-event tokens, successor editing and resolved-state key | `event_operations` |
| Source move timing/coordinates | `effect_validation` |
| Source-paint proof and reconstructed caption serialization | `caption_rendering` |
| Distances, centers and record construction | Standard-library `math`, `statistics`, `dataclasses` |

There are no remaining outgoing engine-defined runtime helpers. The graph is
engine → frame echoes → these established private owners. None imports frame
echoes back, so no circular dependency, engine import, callback adapter or duplicate
helper is needed. This is engine implementation, not cross-tool `shared/` code.
No path-sensitive font discovery moves.

## Data, cache, diagnostic and result ownership

| Concern | Existing contract to retain |
| --- | --- |
| Working events and source evidence | Caller-owned and borrowed. Original source maps remain distinct from the already-simplified working frames. Preserve missing-source refusal, original lifetime bounds and the existing 50 ms move endpoint allowance. |
| Per-call state | The subsystem creates its context, omission set, confirmed removal IDs and replacement dictionary for one invocation. No state survives into another pass call. |
| Frame indexes and profiles | Local groups, ordered timelines, offset buckets, positions, centers, isolation/blocking sets and profile records borrow their event members. Keep candidate selection and all-family ambiguity preparation before the ordered proof traversal. |
| Recorded-motion cache | `FrameEchoFamily.moving_frames` stores positive and negative results for one family's interval keys. Frames and the borrowed source map remain stable while that cache is used. Do not promote it to an event, document or global cache. |
| Frozen records | Fields remain frozen; dictionaries, sets, lists and referenced events retain their existing mutability and identities. Do not deep-freeze or copy them during extraction. |
| Pose, paint and replacement | Preserve the preceding opaque anchor's pose/paint and row/lyric flags, while retaining the current frame sample's lifetime and minimum contributing source ID. Stacked reconstruction keeps its established layer choice; flattened reconstruction keeps the anchor's layer. Paint proof/serialization and source-evidence invalidation remain with their existing owners. |
| Measurement and parsing | Forward the existing event measurement context into caption rendering. No font owner is constructed or moved. Raw source-token reads and strict move validation remain imported primitives, not reimplementations. |
| Output list and count | Return a new list in supplied event-list order. Retained events keep identity. Replacement application remains keyed by source ID, including the existing duplicate-ID behavior. The count stays `len(removed_ids) - len(replacements)`, not a newly defined list-length difference. |
| Diagnostics | The subsystem returns its removal contribution and emits no report. Callers retain aggregate counters, source selection, diagnostics and pipeline placement. |

Do not broaden motion/layout tolerances, change source lifetime proof, reinterpret
contour variation or merge this operation with general frame freezing. The two
echo proof paths should remain distinguishable within this one owner.

## Test maintenance and coverage finding

The current `check_frame_echo_replacements.py` tests final application semantics
with stubbed family indexing/collapse. It currently patches those helper names
on the engine. Once the function moves, resolve its defining module (for example
with `inspect.getmodule(module.collapse_frame_text_echoes)`) and patch there.
This keeps every existing assertion and also works with the historical single-file
reference. Do not add production forwarding to preserve an obsolete stub location.
An ignored copy with exactly this observer adjustment passed against both layouts.

The broader dedicated proof-path harness, `check_frame_echo_stages.py`, is already
classified as historical and is not reused by a current entry point. The current
suite therefore lacks a dedicated behavioral matrix for both echo paths, although
other pipeline/render/corpus checks can exercise them indirectly. Address that
coverage gap during v233 with current-policy module tests. Reuse useful fixture
data, but do not reactivate old paint substitutions, historical helper-call order
or source-line coverage as current specifications. This does not require another
production preparation or a separate refactoring release.

## Assessment evidence

`validation/frame-echo-assessment/` holds an ignored exact extraction prototype.
All 21 moved definitions are AST-identical, including dataclass decorators; the
remaining engine AST changes only by direct imports. All 19 existing private
Python sources remain byte-identical, and the prototype retains the v232 version.

Fresh behavioral checks reuse 128 fixture variations as data, with current
parsing/paint policy and no historical production doubles. Both layouts passed
1,536 combinations of input order and absent/empty/static/moving source evidence.
Complete outputs, source state, retained identity and counts matched exactly.
Explicit expectations cover valid stacked/flattened exits and chains, timing,
recorded movement, paint/layout differences and ambiguity refusals. These are
assessment evidence, not a requirement to preserve every historical fixture
spelling or helper trace indefinitely.

Six selected current scripts passed on both layouts (12 script/version runs):
general regressions, parser-effect consumers, font ownership, event operations,
replacement application with the observer adjustment, and native representative-
pose rendering. The native check passed 42 assertions per layout. Cold isolated
checks imported the private owner before the engine, without optional font
backends, and exercised both proof paths, representative paint/flags, long-frame
source proof/refusal, cache reuse/lifetime, shallow frozen ownership, canonical
aliases and old root lookup.

All 20 production runtime sources and the tracked harness remained unchanged;
all 124 recorded font hashes and 13 corpus-source hashes were verified unchanged.

Full-suite, fresh corpus and actual delivery acceptance checks were not rerun for
this assessment; the v232 release's results are historical evidence for that
runtime, not completed v233 validation. Private fixtures/fonts remain local.

## v233 acceptance and after-release evaluation

One extraction release is sufficient. Add focused module/cold/installed behavior
coverage and update the replacement-test binding, retaining its existing
assertions. Cover both proof paths, source-backed long exits, missing/inconsistent
sources, persistent-label/overlap ambiguity, nonuniform paint or layout, output
pose/paint/timing/flags, original-list ordering, duplicate source IDs, borrowed
inputs, negative cache entries and per-family/per-call state lifetime. Verify all
five frozen records and direct engine aliases without metadata adapters.

Run the full current suite and fresh paired conversions of all 13 corpus tracks,
requiring identical bytes and complete statistics. Preserve exact-font guards
and native rendering under current paint policy. Verify recursive manifests,
actual shipped-updater rollback/retry, installed execution, owned module/cache
removal and MKV workflow, recording native Windows limitations. Keep
`simplify_subtitles.py` unchanged and exclude the historical movement audit from
the routine inventory.

Afterward, confirm the whole echo operation moved together while its caller
retains stage order, source maps and reporting. No production workaround, local
exception, duplicated proof or broader ownership redesign is indicated. The
identified observer adjustment and behavioral coverage gap should be resolved
within v233; broaden review only if current-policy tests reveal a real interaction.
The existing scrolling iterator issue and deferred global API/index reviews
remain separate follow-ups.
