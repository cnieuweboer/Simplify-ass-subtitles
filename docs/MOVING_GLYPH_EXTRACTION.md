# Complete moving-glyph sequence processing — v242

The boundary assessed in
[MOVING_GLYPH_EXTRACTION_ASSESSMENT.md](MOVING_GLYPH_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/moving_glyphs.py`. All seventeen functions and two
existing frozen records moved unchanged: 313 definition lines, including
decorators. Engine names remain direct aliases, preserving signatures, defaults,
canonical record identity and historical root pickle lookup. Runtime version:
`2026.10.20.242`. No behavior change is intended.

## Shared preparation and responsibilities

The first commit moves two shared helpers unchanged, totaling thirty definition
lines, to existing owners. `literal_font_spans()` now belongs to event operations:
source defaults/styles remain borrowed while formatting, continuation and literal
span accumulation are local. Empty-font resets, adjacent equal-font spans and
unsupported-inline refusal are unchanged. It does not read or install an event
cache. `opaque_text_effect_state()` now belongs to effect validation: it reads
borrowed formatting with the existing opaque-fill and supported glyph/outline,
clip/origin/shadow conditions. It does not establish that every paint channel is
opaque or take over caller family admission. Both retain direct engine aliases
and serve sibling filters without importing movement processing.

The movement module owns the complete stationary/moving/held-caption operation:
source-family admission, source and retained indexes, chain/fade proof, exact
glyph fitting, entrance/exit/flash ownership, representative held caption,
proposal arbitration and ordered replacement. Whole fragments can prove their
authored landing without metrics; individual glyph rows require exact font
advances and an authored word anchor. Complete recorded exits, absorbed timing,
paint and inline font switches retain their existing proofs and bounds.

The sole production caller, `_finish_text_effect_sequences()`, retains scale-trail
conditions, source/metric selection, aggregate removal accounting, subsequent
karaoke normalization and final exact-position consolidation. Those orchestration
steps and CLI/reporting remain unchanged.

Source and retained events, visible maps, catalogs, continuations, measurement
context and metrics remain borrowed. Source resolution creates local successor
events/formatting rather than caching on originals. Family sets, static/move/fade
indexes, retained-caption lookup, grouped peers, chain evidence and proposal
buffers remain call-local. The two frozen records intentionally preserve shallow
sharing. Metrics retains font discovery, resources, caches and diagnostics;
rendering, geometry and fitting keep their existing owners.

Competing proposals are rejected before application. Refusal returns the original
list; accepted output retains untouched event identity, sorts by source index and
counts actual removed list slots. Repeat processing retains its existing semantic
result and removal count; this does not add a new no-allocation contract.

The module depends on eleven existing private owners and the standard library.
The private graph remains acyclic without engine imports, adapters or production
forwarding. Cold imports and supported/refused whole-fragment processing load
neither the engine nor optional font backends. No path-sensitive discovery moved.
Interpreter observers now include both defining consumers.

## Validation and delivery

Shared-owner tests now exercise canonical helper aliases, borrowed immutable
catalogs/state, empty-font reset continuation and the distinction between opaque
fill and transparent outline. Before extraction, both owner suites and inline,
context and effect-continuation checks passed the preparatory commit.

Eight new module tests cover canonical aliases/annotations/pickle lookup, shallow
frozen records, local source resolution and indexes, supported/refused chains,
paint/timing/flags/measurement retention, optional metrics and exact-glyph refusal,
proposal conflicts and actual list-slot counting, caller ordering/accounting, and
cold source/installed execution. Exact Arial regular is used for glyph fitting;
whole-fragment proofs run before optional backends load. Installed tests use a
separate working directory and a path with spaces, and preserve user files/fonts
while owned uninstall removes source and bytecode.

Fresh v241/v242 comparisons match across 675 cases: 75 scenarios, three input
orders and absent/exact/unavailable metrics. Complete output, counts,
original-list and retained-identity decisions match, with source events/maps
unchanged. The historical movement harness contributes builders rather than
obsolete helper-count/call-order requirements.

Four additional v241/v242 repeat probes cover whole fragments, separate glyphs,
incomplete chains and competing parents. Semantic results match with no further
removal and no mutation of the borrowed first-pass output.

Native libass probes cover whole fragments, exact separate glyphs, incomplete
chains and competing parents with the exact Arial regular face. Serialized pass
output and all twenty frame pairs match at start, active and end boundaries,
including the retained independent caption and authored held pose.

The unchanged shipped v214 updater delivers v242 over v241, rolling back when
the new movement module or either changed shared owner is locked, then retrying
successfully. Launcher choices/user files, isolated installed supported/refused
and exact-glyph processing, and owned uninstall pass. Recursive Python and
PowerShell manifests agree. Installer checks pass 32 with two native Windows
skips; updater checks pass ten with one native Windows skip. MKV extraction,
conversion, remux/extraction and font-sync smoke checks pass.

All thirteen corpus tracks retain identical output bytes and complete statistics,
with no required-font diagnostic. All 124 recorded font hashes were verified.
Final-source validation passed all 114 regression scripts using Windows BASIC
plus real HarfBuzz on Linux. The full 27-source runtime and test harness stayed
fixed throughout validation. All 21 moved definition ASTs are unchanged, as are
other root behavior, existing shared-owner definitions and the 23 other prior
private sources. The production batch wrapper and delivery code remain unchanged
from v241.
Private evidence remains under ignored `validation/moving-glyph-extraction/`.
Native Windows filesystem and launcher behavior requires separate Windows testing.

## After-release evaluation

The full movement operation has one owner while its caller retains orchestration
and shared services keep their responsibilities. The small preparatory moves
establish useful independent source-read owners without a utility module or
another context. No adapter, duplicated proof, local production exception or
downstream repair was needed. No new dedicated follow-up review was identified.

The previously recorded scrolling iterator contract and global API/index reviews
remain separate; Pillow pixel compatibility was resolved in v241. Choose the next
extraction from the resulting dependencies rather than prescribing a final
hierarchy here.
