# Karaoke completion — bounded extraction assessment

Implemented in [v238](KARAOKE_COMPLETION_EXTRACTION.md). The evidence below
describes the historical assessment.

Assessed against v237 (`2026.10.20.237`, commit `1d024d8`). Recommended next
release: **v238 — Extract karaoke completion** into
`_simplify_ass/karaoke_completion.py`, with no intended behavior changes.
No preparatory production release is needed.

This assessment changes documentation only. The isolated prototype, source
manifests and fresh reports remain under ignored
`validation/karaoke-completion-assessment/`.

## Boundary

Move thirteen existing functions and two frozen records unchanged: 215 definition
lines including decorators.

- `KaraokeCompletionSourcePhase`, `KaraokeCompletionProfile`.
- `_karaoke_completion_identity`, `_karaoke_completion_cue_start`,
  `_karaoke_completion_paint`, `_index_retained_karaoke_completion_rows`,
  `_select_karaoke_completion_rows`, `_index_karaoke_completion_sources`,
  `_karaoke_completion_source_phases`, `_profile_karaoke_completion_source_phase`,
  `_prove_karaoke_completion_transition`, `_match_karaoke_completion_profiles`,
  `_prove_ordered_karaoke_completion_sweep`, `_replace_karaoke_completion_paint`,
  `normalize_karaoke_completion_paint`.

This is one complete operation: identify retained fragment rows, establish full
source-phase coverage, prove an ordered shared color transition and apply its
destination paint. Keep its ordinary source-transform and supplied outline-profile
routes together. Preserve all names as direct engine aliases, signatures,
canonical record identity and historical root pickle lookup. Accept the natural
change in defining module; preserve shallow frozen dictionaries.

The outline-strip producer remains in the engine. Its geometry, palette,
compositing, fade and contrast proofs establish evidence before copies disappear.
It constructs the same `KaraokeCompletionProfile`; sharing that canonical record
with its consumer does not transfer ownership of those proofs. Likewise, moving
glyph reconstruction and whole-caption color-phase policy remain separate.

## Incoming and outgoing dependencies

Two production callers retain their current conditions and stage positions:

- `flatten_stacked_text_copies()` supplies pass-local outline profiles after
  reducing stack groups and before the glow-boundary handoff.
- `_finish_text_effect_sequences()` supplies original source events after moving
  glyph reduction, before the existing exact-position consolidation.

The engine's `_profile_outline_strip_sweep()` also constructs the shared profile;
its enclosing rendering/grouping helpers retain their existing annotations.
Import the canonical aliases before dependent definitions.

| Outgoing dependency | Existing owner |
| --- | --- |
| Canonical `Event` | `event_model` |
| Override interpretation and effective-state evaluation | `ass_overrides` |
| Raw override tokens and successor event edits | `event_operations` |
| Strict source-transform validation | `effect_validation` |
| Position, inline guard, height and layout/placement keys | `caption_geometry` |
| Upright/unrotated state eligibility | `static_selection` |
| Visible literal extraction | `text_freezing` |
| Paint tag serialization | `caption_rendering` |
| Records, source-state copies and rotation arithmetic | Standard-library `dataclasses` and `math` |

No outgoing helper remains defined in the engine. The prototype's private import
graph is acyclic, with no reverse engine import. There are no font handles,
font discovery paths or moved `__file__` assumptions. Cold import does not load
Pillow, fontTools or HarfBuzz. This belongs under `_simplify_ass/`; no callback,
forwarding adapter, new context or cross-tool shared service is needed.

Other screened operations currently retain engine dependencies: sliced-text
processing needs literal-span/opacity/clip helpers; backed-glyph pulses need
source-paint pooling and settled samples; supporting-drawing reduction needs
several vector operations. Those may become useful later boundaries, but do not
pull them into this extraction to increase its size.

## Ownership to preserve

| Concern | Existing responsibility |
| --- | --- |
| Inputs | Borrow working events, visibility and original source maps. Borrow supplied outline profiles and their paint dictionaries. Do not mutate those inputs or their formatting/default/style/continuation data. |
| Working data | The invocation owns row buckets, sorted candidate lists, filtered source indexes, transition/hold lists and replacement maps. Resolved source phases are new records borrowing unchanged source metadata. There is no persistent subsystem cache or diagnostic store. |
| Evidence | The source route establishes complete coverage and compatible holds. The outline producer owns its independent strip proof and profile lifetime. The consumer requires a complete row before accepting that evidence. Preserve the distinction between absent and empty supplied profiles. |
| Application | Read the selected destination paint and use the existing successor editor. Preserve geometry, timing, source IDs, original list order and identity of untouched events. Preserve the early original-list return when there are no candidates and the new-list return after candidate processing, even when no row is accepted. |
| Result | Return the same event list contract. This operation changes paint, not event counts; do not add a removal counter. Callers retain configuration, aggregate accounting and reporting. |
| Shared records | Keep both records frozen with their current fields and shallow ownership. `final` remains the producer's mutable dictionary; the consumer reads it without claiming or copying it. |

Keep existing tolerances, rotation equivalence, source filtering, transform
continuation, shared-palette ordering and completed-hold requirements. Preserve
refusals for incomplete coverage, competing copies, cyclic changes, independent
color changes and unsupported geometry. Extraction is not a timing or color-policy
change. Repeated direct calls currently append redundant paint tags while keeping
resolved paint stable; preserve that behavior and the later compaction boundary.

## Preparation and test bindings

Existing owners already close this boundary. No independent production preparation
would improve it enough to justify another release.

The maintained `patch_interpreter_bindings()` test helper needs the new defining
consumer in its existing observer list so `check_effect_continuation.py` continues
to see parser calls inside this operation. The prototype applies that test-only
adjustment without changing assertions. Engine call-site observers remain on the
engine alias. Do not introduce runtime forwarding for spies.

`check_karaoke_completion_stages.py` is an archived extraction harness, not a
current suite entry point. Direct execution fails on current v237 because it
observes the removed `apply_tag` API. Do not revive that historical oracle or
count its direct execution as passing. Its case builders remain useful: the
maintained continuation test already consumes them, and this assessment uses them
for a fresh comparison against current v237. This is not a production defect or
a prerequisite cleanup release.

## Fresh evidence and implementation acceptance

All fifteen definition ASTs move unchanged in the isolated prototype. Every
remaining root definition and all prior private sources are unchanged. Production's
23-source manifest, tracked tests and all 124 recorded font hashes remain unchanged.
Cold imports, resolved annotations, canonical aliases, shallow record ownership
and historical root pickle lookup pass.

Current v237 and the prototype each passed:

| Check | Result for each runtime |
| --- | --- |
| Current-policy direct pass comparison | 711 combinations across 79 scenarios and independently ordered working/source events; complete results, repeat behavior, input immutability and identity decisions identical between runtimes |
| Karaoke completion bounds | 812 checks |
| Effect continuation, including reused karaoke cases | 179,958 checks across 3,144 effect cases |
| Outline karaoke producer/consumer and rendering | 70 checks, including nine pixel-identical libass reversed/instant timing comparisons within each runtime and the rendered completed outline |
| Current paint handoffs | 177 checks using actual caption serialization and exact-font geometry |

These focused checks support the boundary; they are not a new full-corpus or
native Windows validation. For implementation, add a focused module-contract check
and run the current full regression suite plus a fresh strict-font corpus comparison.
Require unchanged output bytes and statistics. Verify cold source/installed
imports, recursive module delivery, actual updater migration/rollback and owned
uninstall. Keep `simplify_subtitles.py`, installer filename policy, CLI, pipeline
conditions and production reporting unchanged.

After implementation, confirm that both proof routes exercise the canonical
consumer and that the outline producer still owns its evidence. No new production
workaround, duplicated proof or unclear ownership was exposed. No dedicated
follow-up review is indicated by this assessment. The previously recorded
scrolling-iterator contract issue and deferred global API/index reviews remain
separate work.
