# Scrolling-block recognition and limiting extraction assessment

Assessed against v230 (`2026.10.19.230`, commit `307d4b4`). Recommended next
release: **v231 — Extract scrolling-block recognition and limiting**.
This assessment changes no production source or tracked test.

## Recommended boundary

Move the existing frozen `ScrollingBlockMatch` record and these nine functions
unchanged into `_simplify_ass/scrolling_blocks.py`, retaining direct engine aliases:

- `collect_scrolling_tracks()` and `scroll_track_crosses_canvas()`.
- `_scrolling_pose_is_translational()` and `_profile_scrolling_track()`.
- `_scrolling_profile_position()`, `_scrolling_profiles_are_coherent()` and
  `_scrolling_profiles_are_distinct()`.
- `_match_scrolling_block()` and `drop_overloaded_scrolling_blocks()`.

This is 290 definition lines including the frozen decorator. It is a complete
processing subsystem: track construction, motion/edge proof, block membership,
remaining-concurrency policy, ordered removal and per-block reporting. v230
closed its remaining shared height/state comparison dependencies.

## Incoming and outgoing dependencies

The only engine consumer is `_limit_scrolling_text()`. Keep that wrapper in the
engine: it extracts canvas dimensions, reads `SimplifyConfig`, selects the late
residual-event stage and aggregates counters. Caption support rebuilding,
restoration/layering and CLI/warning reporting remain with their current owners.
Tests and external callers continue using canonical engine aliases.

| Outgoing owner | Borrowed functionality |
| --- | --- |
| Standard library | `math`, `re`, `bisect_right`, `dataclass`, `replace` |
| `ass_overrides` | Canonical override pattern and tokenization |
| `caption_geometry` | Explicit positions, nominal height and conservative measured bounds |
| `event_model` | Canonical `Event` annotation |
| `event_operations` | Resolved `state_key()` |
| `font_metrics` | Canonical `FontMetrics` annotation; the module constructs no metrics owner |
| `subtitle_document` | Shared `peak_concurrent_events()` primitive |

The graph stays engine → scrolling blocks → existing private owners. None of
those owners needs the engine or the proposed module. No callbacks, forwarding
adapters, reverse imports or circular imports are needed. No new processing
context, class hierarchy or consolidated result model is needed.

`_faded_cue_is_scrolling()` remains with faded-cue admission: it recognizes a
different source-effect condition, rather than a proved residual scrolling block.
Do not move it merely because its name includes scrolling. The strict effect
parsers and broader frame reducer remain separate future assessments.

## Data, caches, diagnostics and results

| Concern | Responsibility after extraction |
| --- | --- |
| Events, formatting, document catalogs and evidence | Remain caller-owned and borrowed. Retained output entries are the original event objects in supplied order. |
| Tracks and profiles | Frame groups, nearest-neighbor assignments, timeline points, profiles, confirmed membership and removal sets remain call-local. |
| Shared match record | Preserve frozen fields, field order, profile indices and common proof interval. Its list field remains shallowly mutable; do not deep-freeze or redesign it. |
| Font measurements and caches | Remain with the supplied metrics owner. Unknown bounds cannot establish the required edge proof. |
| Edge-proof temporary views | Keep the existing local dataclass replacements, copied projection state and borrowed continuation. They are measurement views, not new source evidence or output events. |
| Policy decision | The module retains the existing passed limit/default, immediate negative validation, strict `peak > limit` comparison and zero-disable semantics. |
| Per-block reports | The module builds and returns the same member details, proof interval, axis/direction, unique-event peak, limit and retained/removed action. Retained blocks are still reported when removal is disabled. |
| Aggregate diagnostics and counters | `_limit_scrolling_text()` retains dropped-event totals, block totals, residual peak and configured limit; pipeline/CLI consumers retain warnings and printing. |

Preserve the distinction between spatial voters and paint-copy members. Keep
mutual nearest-neighbor ambiguity refusal, the bounded entrance prefix, pairwise
coherence over a shared interval, measured edge evidence and the three-distinct-
track minimum. Use the block's own remaining unique-event concurrency; unrelated
captions or a large total of sequential frames must not trigger removal.
No static re-placement of scrolling lines is introduced.

## Preparation and scope

**No preparatory production change is required.** One extraction release is
sufficient. All helpers retain their current signatures/defaults and every
pipeline/reporting boundary stays explicit. No current test observer change has
been identified by the prototype.

The helper currently expects an input that can be iterated again after track
collection. Production supplies a list. Keep this extraction behavior-only;
the existing single-use-iterator mismatch below deserves a separate contract
review, rather than silently mixing an API behavior fix into the movement.

## Assessment evidence

An ignored prototype moves the exact nine functions and decorated record with
direct aliases. AST checks verify identical moved definitions and unchanged
remaining engine code except the import. All existing private sources remain
byte-identical and the version remains v230.

An isolated process passed cold import without optional font backends, canonical
aliases, frozen/pickle record identity, track construction, borrowed event and
measurement ownership, cap/zero behavior, per-block reports, unknown-bound
refusal and negative-limit validation before input consumption.

Six existing checks passed unchanged on baseline and prototype: **12 successful
script/version runs**, using Windows BASIC plus real HarfBuzz on Linux.

| Check | Results per version |
| --- | --- |
| General simplifier, including scrolling detection and limits | 275 checks |
| Font measurement ownership/parity | 1,459 checks |
| Parser effect consumers | 9,894 checks |
| Inline continuation | 51,222 checks |
| Caption-geometry module contracts | 10 tests |
| Native source poses | 42 checks |

No assertions, test helpers or observer bindings were changed. All 18 production
source hashes still match verified v230; tracked harness inputs and all 124
recorded font hashes were verified unchanged after the checks. The local
`assessment.json` records final evidence and the separate iterable reproduction.

Local prototype, manifests, dependency audit and logs are in
`validation/scrolling-blocks-assessment/`. Full regression and fresh paired
corpus/delivery checks are reserved for implementation; this assessment does not
claim a fresh full run.

## Dedicated follow-up: input iteration contract

Both unmodified v230 and the prototype reproduce the same mismatch:
`drop_overloaded_scrolling_blocks([event], ..., concurrency_limit=0)` retains a
single ordinary event, while passing `iter([event])` returns an empty list. Track
collection consumes the iterator before the final output filter can traverse it.
This occurs without a proved scrolling block and even with removal disabled.

The production caller is typed and supplied as a list, so its current behavior
is unaffected. Separately decide whether this helper accepts general iterables
and materializes them once, or explicitly requires/rejects non-reiterable input.
Add assertions for the chosen behavior. The historical generator parity check
only compares two implementations; it does not prove content preservation and
must not become an oracle that treats iterator exhaustion as intended removal.
The local reproduction is evidence of a follow-up, not a desired regression
expectation. No other corrective review has been identified.

## Proposed v231 validation and after-release evaluation

Add focused module/cold/installed coverage for canonical aliases/types, old root
lookup, frozen-record semantics, borrowed inputs/metrics, track ambiguity,
independent voters versus paint copies, measured edge refusal, cap boundaries,
zero/negative settings, report fields, ordering and per-call state lifetime.
Use actual current paint/measurement policy and intended content/report behavior.
Keep the separate iterator-contract issue explicit.

Run the full current suite and fresh paired conversions of all 13 corpus tracks,
requiring identical bytes and complete statistics. Retain general scrolling,
font ownership, parser continuation and native rendering checks. Verify recursive
delivery/manifests, actual shipped-updater rollback/retry, installed processing,
owned module/cache removal and the MKV smoke test. Leave `simplify_subtitles.py`
unchanged and identify native Windows limitations.

Afterward, confirm the module owns one scrolling proof/limit/reporting operation
while the pipeline still owns stage invocation, canvas/configuration and aggregate
reporting. Preserve existing uncertainty rather than changing motion bounds or
static placement. Carry the iterable-contract finding as a dedicated follow-up;
the broader API and pass-local index reviews remain separate.
