# Shared source-effect validation assessment

Assessed against v231 (`2026.10.20.231`, commit `eb76ac3`). Recommended next
release: **v232 — Establish shared source-effect proof helpers**.
This is an independently useful preparatory extraction with no intended behavior
change. Production sources and tracked tests remain unchanged in this assessment.

## Why this boundary

The frame-echo processing subsystem is a promising larger extraction: sixteen
functions and five existing frozen records implement admission, recorded motion,
settled-caption/paint-stack proofs, per-family processing and ordered replacement.
Its only remaining engine-defined runtime dependencies outside that family are
`event_override_tokens()` and `parse_effect_move()`. Other outgoing dependencies
already have private owners: event records/operations, caption geometry,
caption rendering and override syntax, plus the standard library.

Those two helpers also serve many other passes. Moving their definitions into an
echo module would give common policy a pass-specific owner. Forwarding callbacks
or importing the engine would leave the dependency unresolved. The transform
validator belongs with the move validator because both establish the existing
strict source-effect timing/admission contract; they do not evaluate an animation.

Extract these shared primitives first and verify their many consumers separately.
This is useful independently of whether the next processing extraction is echoes,
source-paint reconstruction or supporting drawings. The full supporting-drawing
subsystem still depends on the general frame-sequence reducer, which also owns
lyric-boundary and near-static-pose decisions. Sliced-text processing has additional
shared span/paint/clip dependencies. Echoes therefore offer a shorter route to a
closed processing subsystem after this preparation. Reassess that resulting graph
before committing to its extraction; no final module hierarchy is prescribed.

## Recommended move and dependencies

| Existing function | Defining owner after v232 | Engine consumers |
| --- | --- | --- |
| `parse_effect_transform()` | New `_simplify_ass/effect_validation.py` | 24 |
| `parse_effect_move()` | Same validation module | 7 |
| `event_override_tokens()` | Existing `_simplify_ass/event_operations.py` | 40 |

There are 44 definition lines and 48 distinct consuming engine definitions;
counts overlap and include `OutlineStripEvidence.tokens_for()` through its class.
Keep direct engine aliases for all three names, with unchanged signatures and
defaults. Do not introduce result records, contexts, caches or adapters.

The validators depend only on `math` and the canonical `tokenize_override()` from
`ass_overrides`. The event-token reader borrows the canonical `Event` annotation,
`OVERRIDE_RE` and `tokenize_override()`. Event operations already owns the record
and regex imports; only the tokenizer import is added there.

Dependencies remain engine → validation → interpreter and engine → event
operations → existing geometry/model/interpreter owners. Neither new placement
imports the engine or an effect-specific processing pass. There is no circular
import, duplicate implementation, callback injection or path-sensitive discovery.
Everything is engine-specific and belongs under `_simplify_ass/`, not `shared/`.

## Data, caches, diagnostics and results

| Concern | Contract to preserve |
| --- | --- |
| Original event text | Caller-owned and borrowed. Token access scans the supplied event's raw override blocks in their original order; it does not substitute resolved formatting or a reconstructed descendant. |
| Token result | Return a fresh mutable flat list on each call. Do not install an event cache or retain the event. Unknown/raw arguments and repeated/reset tags remain available to the caller. |
| Existing token reuse | `OutlineStripEvidence.tokens_for()` retains its family-local, exact-object-identity cache and tuple conversion. Keep that cache with the proof owner; do not move it into event operations or key it by source index. |
| Parsed transform changes | When supplied, borrow and return the same list after validation. Do not copy, mutate, retain or retokenize it. Otherwise create the usual tokenizer result. Allowed-tag sets remain borrowed. |
| Timing and effect policy | Keep all current transform timing forms, positive-acceleration/finite-timing checks, the existing 50 ms endpoint allowance, and explicit instant/after-end opt-ins. Move endpoint slack stays a caller choice. Each matcher retains its own allowed tags and geometric/source-family proof. |
| Results and refusals | Keep the transform tuple, move coordinate list and `None` refusal behavior exactly. This extraction does not tighten grammar, add exception handling, normalize coordinates or alter malformed-input policy. |
| Other state and diagnostics | No counters, font measurements, reports or diagnostics move. Callers retain source maps, parsed-source lifetimes, context/result records, stage order and all user-visible reporting. |

These are stricter proof validators than the general freezer/sampler parser.
Do not merge those parsers or route existing sampling through this policy. Raw
source-token access is also distinct from `event_evaluation()`: reading effect
syntax must not resolve formatting, install state or change continuation.

## Preparation and release scope

**This shared-helper move is the preparation.** It needs no earlier production
redesign and fits in one release. Keep frame-echo functions and all five records
in the engine during v232. Keep `opaque_text_effect_state()`, literal-font spans,
clip proofs, lyric-boundary evidence and the general frame-sequence reducer with
their present responsibilities. Leave `simplify_subtitles.py` unchanged.

The preparation has value beyond line count: a future echo module can import
common event-token access and move validation directly from their existing
owners, while unrelated source-effect consumers avoid depending on echoes.
The broad API and pass-local index reviews remain separate work.

## Assessment evidence

An ignored prototype under `validation/effect-validation-assessment/` moves the
three definitions without changing their AST. The remaining engine AST is
unchanged except for direct alias imports; the existing event-operations owner
only gains the canonical tokenizer import and unchanged reader definition.
Other private sources remain unchanged. The production runtime stays v231.

Cold isolated imports exercise the private modules before importing the engine,
without Pillow, fontTools or HarfBuzz. Checks cover canonical aliases, raw token
ordering/fresh lists, borrowed inputs, parsed-change identity, transform timing
forms, allowed-tag refusal, finite values, instant/after-end flags and move slack.

Fresh paired current-suite checks compare the unmodified v231 runtime with the
prototype: outline parsing reuse, parser effect consumers, inline continuation,
effect continuation, font-row geometry, general engine regressions, event
operations and frame-echo replacement application. They use the current inventory
and current paint policy without changing tracked test helpers or assertions.
Full-suite, native rendering, corpus and delivery validation are implementation
acceptance work; previous v231 reports do not establish a fresh v232 pass.

All eight selected scripts passed on both layouts (16 successful script/version
runs), including 9,894 parser-effect, 51,222 inline-continuation, 179,958
effect-continuation, 219 outline-reuse and 275 general regression assertions.
Cold import/ownership checks passed. All 19 production runtime sources and the
tracked harness stayed unchanged; all 124 recorded font and 13 corpus-source
hashes were verified unchanged. Full-suite/corpus/delivery checks were not rerun.

Two initial exploratory runs used obsolete moving-glyph/backed-pulse harnesses;
both failed equally on baseline and prototype. The inventory already classifies
those as historical extraction harnesses, whose old traces/paint expectations
are not current entry points. Their current effect-continuation consumer is used
for acceptance instead. Preserve that distinction rather than adapting production
to obsolete traces or treating the failures as newly introduced regressions.

## v232 validation and after-release evaluation

Add focused validator-module/cold/installed checks and extend event-operations
coverage for the raw reader. Exercise canonical aliases, historical root lookup,
signatures/defaults, raw token ownership, supplied-list identity, refusal bounds
and caller opt-ins. If an observer needs to watch tokenizer calls inside a moved
helper, bind it to the defining private consumer; do not add production forwarding.

Run the full current suite and fresh paired conversions of all 13 corpus tracks,
requiring identical output bytes and complete statistics. Preserve exact-font
prerequisites and native rendering coverage. Verify recursive runtime/delivery
manifests, actual shipped-updater rollback/retry, installed execution, owned
uninstall and the MKV smoke workflow, identifying native Windows limitations.

Afterward, confirm the validators and raw event reader own no pass state and all
consumers retain their proof/caching/reporting responsibilities. No new workaround,
local exception or ownership redesign is indicated by this assessment. The next
larger candidate is frame-echo processing, subject to its own final assessment.

The existing scrolling single-use iterator exhaustion remains a dedicated,
independent follow-up. Production supplies lists; fixing that behavior is neither
a prerequisite for this boundary nor part of a behavior-preserving extraction.
