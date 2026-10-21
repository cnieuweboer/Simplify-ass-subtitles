# Boundary-glyph processing — bounded extraction assessment

Assessed against v245 (`2026.10.21.245`, commit `4624899`). Recommended next
release: **v246 — Extract complete boundary-glyph matching** into
`_simplify_ass/boundary_glyphs.py`, with no intended behavior changes.

Move the shared `_parse_simple_source_fade()` read unchanged to the existing
`effect_validation.py` owner first, then move the operation. Both fit one release.
No new context, result hierarchy, callback or generic glyph framework is needed.
This assessment changes documentation only; the isolated prototype and reports
remain ignored under `validation/boundary-glyph-assessment/`.

## Complete responsibility

Move twelve functions and two frozen records unchanged: **211 definition lines**
including decorators:

- `BoundaryGlyphPhase`, `BoundaryGlyphIndex`.
- `_boundary_glyph_geometry`, `_boundary_glyph_caption_key`,
  `_classify_boundary_glyph_phase`, `_profile_boundary_glyph_source`,
  `_boundary_glyph_protection`, `_index_boundary_glyph_events`,
  `_index_boundary_glyph_captions`, `_match_boundary_glyph_words`,
  `_fit_boundary_glyph_words`, `_collect_boundary_glyph_proposals`,
  `_resolve_boundary_glyph_ownership`, `match_boundary_glyph_effects`.

Keep rotating entrances and flying exits together: they use one classification,
complete ordered-literal/anchor proof and ownership arbitration. Retain protected
absorbed entrances, independent brief holds, closest-anchor selection, rejection
of duplicate/partial groups and the existing tracking allowance. Preserve all
current source-fade, transform, movement and boundary tolerances.

Do not include `match_departing_glyph_effects()` merely because it also recognizes
exits. That operation consumes reconstructed `TextRow` evidence and has distinct
outline/layer/trajectory proofs. Boundary matching instead proves retained words
from source and working-event maps. Full-lyric-copy cleanup is independently
extractable, but belongs to another pipeline stage and need not be bundled here.

## Incoming and outgoing dependencies

The sole production caller is `remove_covered_fragment_effects()`. It retains
source-map gating, order relative to departing/staggered glyph matching,
aggregation of removal IDs, later shadow/fragment proofs, row timing successors,
output-list construction and the final removal count. The extracted operation
returns evidence authorizing removal; it does not remove or replace events itself.
Keep direct engine aliases for existing callers and record lookup.

| Outgoing dependency | Existing owner |
| --- | --- |
| Canonical Event | `event_model` |
| Supplied exact-font metrics | `font_metrics` |
| Authored fragment anchor fitting | `glyph_placement` |
| Initial source interpretation and continuation replay | `ass_overrides` |
| Raw authored override tokens | `event_operations` |
| Strict transform/movement validation, opaque-state admission, shared fade parser | `effect_validation` |
| Position, placement, inline guard and text-layout reads | `caption_geometry` |
| Visible-only literal extraction | `text_freezing` |
| Upright/unrotated-state admission | `static_selection` |
| Fixed-boundary borrowed group query | `boundary_groups` |

After the small preparation, every outgoing dependency already has a private
owner. The prototype graph is acyclic and imports no engine from a private module.
No path-sensitive code moves. Exact-font discovery stays with measurements.

## Independently useful preparation

Move the existing **twelve-line** `_parse_simple_source_fade()` to
`effect_validation.py`, retaining its engine alias. Both boundary source profiling
and `_caption_phase_source()` use it. Making either producer own the other's
parser would obscure the dependency; the existing strict validation module needs
only its already-imported `math` module to own this shared read.

Preserve exactly one `fad`, rejection of any `fade`, two finite nonnegative values,
existing parsing behavior and a fresh returned list. This helper does not validate
cue duration, classify a phase or decide a readable core: each producer keeps
those different decisions. Do not broaden it into fade policy or merge it with
permissive rendering parsers. The ownership improvement is useful independently,
but too small to need a separate release.

## Data, caches, diagnostics and results

| Concern | Responsibility to preserve |
| --- | --- |
| Inputs | Borrow working events, visibility, original source map, catalogs and metrics. Do not install formatting/continuation caches on source events. |
| Source views | Initial evaluation creates local state/continuation and a shallow source successor. Preserve source timing and original geometry; working captions supply retained text and their own anchors. |
| Records | Keep both existing frozen records and intentional shallow sharing. The index contains locally mutable dictionaries/lists/sets; frozen does not imply deep immutability. |
| Pass state | Caption/effect groups, boundary indexes, protected IDs, candidate deduplication, sorted peers, proposals and ownership counts belong to one invocation. Index-building mutation is local. |
| Font caches | Remain with the supplied FontMetrics; the operation owns no font handles or persistent cache. |
| Diagnostics | No report argument, new counter or diagnostic owner. Preserve metric refusal/failure behavior; pipeline reporting remains outside. |
| Results | Return the existing fresh `set[int]` of uniquely owned removable source IDs, including an empty set when metrics are absent/unavailable. Do not introduce an event/result wrapper. |

Preserve ownership per phase for captions and unique ownership for effects;
an entrance and exit may independently belong to one retained caption. Protected
absorbed glyphs can prove slots without becoming removable. Keep source history
and retained-caption membership distinct rather than inferring either from a
frozen event's extended lifetime.

## Fresh bounded evidence

The isolated prototype preserves all fourteen moved definition ASTs, the shared
parser AST and every remaining engine definition. Thirty existing private source
files are byte-identical; only `effect_validation.py` changes and one new private
module is added. Complete manifests cover the 32-source baseline and 33-source
prototype. Independent cold import, canonical aliases, evaluated public record/
operation annotations and an acyclic private import graph pass. Cold metric-free
refusal loads neither the engine nor optional font backends before engine import.

Current and prototype match across **3,915 direct comparisons**: 87 scenarios,
three working-event orders, three source-map orders and five metric modes.
Cases include accepted entrances/exits, tracking, absorbed holds, ambiguity,
partial groups, invalid geometry/fades/transforms, boundary tolerance and exact
Arial fitting. Explicit missing-font cases test refusal; the required exact Arial
regular is available. Decisions and recorded fit calls match, borrowed input
values remain unchanged and working formatting dictionaries retain identity.
Read-only source/visibility maps are accepted.

Two focused conversions (`Overlord-22m06-source.ass` and
`Overlord-opening-fades-source.ass`) have identical subtitle SHA-256 values,
complete statistics and font reports, with no missing required fonts. They use
current timing/paint policy without the archived harness's historical fade or
static-phase substitutions. These are assessment checks, not a fresh full-suite,
full-corpus, native-rendering or native-Windows run.

Implementation should add a focused module/ownership check and shared-parser
checks for both producers. Interpreter observers must follow the defining
boundary consumer, and recording/failed-fit doubles must target its imported fit
binding. The old boundary-stage audit also observes root bindings and historical
helper traces; update test-only observation rather than adding production
forwarders or preserving obsolete scope assertions.

Then run the full regression suite and strict-font corpus comparison, requiring
unchanged bytes/statistics. Verify exact-font native entrance/exit examples and
recursive installed delivery, rollback/retry and uninstall for the new module.
Keep the production wrapper, reporting and matching policy unchanged.

## After-release evaluation

Confirm that one module owns classification through final removal authorization,
while the caller still applies IDs and reports counts. Verify both fade-parser
consumers retain their distinct decisions. Broaden review if production adapters,
input mutation or conflicting evidence lifetimes appear. None was needed or
uncovered by this prototype; no new dedicated corrective review is indicated.
The existing scrolling iterator contract and global API/index reviews remain
separate.
