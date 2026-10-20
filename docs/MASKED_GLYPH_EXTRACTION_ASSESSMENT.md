# Masked-glyph processing — bounded extraction assessment

Implemented in [v237](MASKED_GLYPH_EXTRACTION.md). The evidence below describes
the historical assessment.

Assessed against v236 (`2026.10.20.236`, commit `13e2eae`). Recommended next
release: **v237 — Extract masked-glyph processing** into
`_simplify_ass/masked_glyphs.py`. V236 resolved the independent font-resource
cleanup gap; no additional preparatory production release is needed.

This assessment changes documentation only. The isolated whole-engine prototype
and fresh reports remain under ignored `validation/masked-glyph-assessment/`.

## Boundary and responsibilities

Move eighteen existing functions and four frozen records unchanged, totaling
425 definition lines including decorators:

- `MaskedGlyphContext`, `ParsedGlyphMask`, `MaskedGlyphModel`, `MaskedGlyphProof`.
- `_canonicalize_mask_contours`, `_prepare_masked_glyphs`,
  `_index_masked_texture_peers`, `_parse_glyph_mask`,
  `_match_masked_shadow_texture`, `_masked_glyph_candidates`,
  `_masked_placement_matches`, `_same_masked_text_copy`,
  `_masked_glyph_outline`, `_prepare_masked_outline_model`,
  `_fit_masked_outline_segment`, `_match_masked_glyph_contours`,
  `_match_masked_glyph_bases`, `_remove_masked_texture_companions`,
  `_apply_masked_glyph_proof`, `_follow_proven_shadow_mask_phases`,
  `_close_masked_glyph_fonts`, `remove_masked_glyph_effects`.

This is a complete processing responsibility: index retained text and texture
carriers, prove identical text or exact-font contour coverage, establish
corresponding texture/shadow ownership, construct readable retained glyphs and
apply removals/replacements. Keep these cooperating proof paths and their
resource lifetime together.

Retain all 22 names as direct engine aliases, preserving signatures/defaults,
canonical record identity and historical root pickle lookup. Allow the natural
change in defining module; preserve shallow freezing and existing mutable field
identities. Do not consolidate the records or introduce a broader context.

Leave `remove_fragmented_font_decorations()` in the engine: it proves scattered
fragmented-font stamps, rather than glyph-shaped masks. Later
`restore_masked_caption_foregrounds()` and caption/background ownership likewise
have separate inputs, proofs and stage responsibilities. Do not combine these
operations merely because their names mention fonts or masks. Keep the exact
mask contour/anchor proof distinct from general drawing reduction and the
existing font-outline matcher; extraction requires no algorithm consolidation.

## Incoming and outgoing dependencies

The sole production caller is `_consolidate_text_events()`, which invokes
`remove_masked_glyph_effects()` after fragmented-font decoration removal and
before stacked-text flattening. It supplies working events, the visibility map,
shared metrics and original animation IDs. Keep that invocation, source choice,
configuration, stage order and result unpacking in the engine.

| Outgoing dependency | Existing owner |
| --- | --- |
| Canonical `Event` annotation | `event_model` |
| Shared `FontMetrics` interface and exact face opening | `font_metrics` |
| Override parsing, regex, numeric grammar and defaults | `ass_overrides` |
| Position, inline-layout guard, nominal height, placement and exact layout keys | `caption_geometry` |
| Successor editing and resolved-state identity | `event_operations` |
| Reconstructed caption serialization and paint policy | `caption_rendering` |
| Records, regex parsing and fit arithmetic | Standard-library `dataclasses`, `re`, `statistics` |
| Recording/decomposing pens and quadratic-to-cubic conversion | Existing lazy imports from `fontTools.pens.recordingPen` and `fontTools.pens.qu2cuPen` |

No outgoing runtime helper remains defined in the engine. The prototype's private
import graph is acyclic and has no reverse engine import. FontTools imports stay
inside the exact-outline branch: importing the module and using font-independent
proof paths must not eagerly load optional font backends. No path-sensitive
`__file__` logic moves; font discovery remains with the measurement owner.

This remains engine-specific code under `_simplify_ass/`. No callback adapter,
new shared service, engine import or cross-tool `shared/` module is needed.

## Data, cache, diagnostic and result ownership

| Concern | Contract to preserve |
| --- | --- |
| Caller inputs | Borrow events, visibility, animation evidence and metrics. The existing empty-animation-set normalization stays unchanged. Do not mutate source text, formatting/default/style dictionaries or caller maps. |
| Prepared indexes | One invocation owns positions, heights, inline-layout results, spatial base buckets, opaque-caption and texture indexes, shadow carriers and approved source sets. Indexed events remain borrowed. Preserve candidate ordering and lifetime/layer tie behavior. |
| Comparison caches | Placement/layout results stay keyed by source ID within the pass. Exact outlines and failed results stay keyed by face and glyph. Preserve per-glyph negative caching, including a later glyph's ability to initialize successfully after an earlier failure. |
| Open fonts | The measurement owner is borrowed. Each newly opened handle remains locally owned until glyph-set initialization and registration succeed. Then the pass owns the handle and glyph set until its existing `finally` cleanup. Preserve initialization/error/interrupt closure and exception propagation from v236. |
| Per-mask proof | Parsed commands/points/offsets, scaled models, covered command slots, matched successor events and loose-anchor evidence are local to that mask. Keep complete coverage and the existing multi-glyph anchor proof; do not convert an incomplete contour into deletion authority. |
| Ordered application | The pass owns removal IDs, replacements, approved shadow runs and its new output list. Retained events keep identity; replacements remain separately constructed successors. Preserve source-ID application and original list order. |
| Results and reporting | Return the existing `(events, removed_count)` tuple, with the count still derived from confirmed source IDs. The engine retains the `masked_decorations` aggregate and report formatting. This is distinct from the later `font_textures_removed` counter. No font report, logger or diagnostic owner moves into the module. |

## Preparation and test bindings

V236 already supplied the useful independent preparation: an explicit temporary
handle handoff and unconditional pass-owned cleanup. The module boundary now
closes without another production change, adapter or resource abstraction.

Two existing test observations follow the new defining owner as part of the
extraction:

- `tests/check_masked_glyphs.py` injects later proof errors by patching
  `_apply_masked_glyph_proof`. Resolve that binding through the module defining
  `remove_masked_glyph_effects()` rather than patching the engine alias.
- The same test traces helper execution and reads helper ASTs from the engine
  file. Resolve the defining module's file for coverage and helper enumeration.

The isolated prototype applies these test-only adjustments without changing
assertions. Its focused conversion observers still patch the engine's entry
alias because that remains the pipeline's actual call site. No production
forwarding is necessary. These are routine extraction-related test updates,
not a separate preparatory release or a new global API review.

## Fresh assessment evidence and implementation acceptance

All 22 definition ASTs move unchanged in the local prototype. Current v236 and
the prototype both passed:

| Check | Result for each runtime |
| --- | --- |
| Masked-glyph behavior and normal font call/closure comparisons | 686 comparisons; all 17 internal helpers exercised |
| Resource initialization, reuse, recovery, error and interruption paths | Nine lifecycle cases |
| Complete focused conversions using the existing behavioral contract | Two conversions |
| Current paint handoffs using actual caption rendering and exact-font geometry | 177 checks |
| Font measurement behavior and cache ownership | 1,459 checks |
| Font-module imports, resource roots and installed execution | Five tests |

Cold prototype import from an unrelated directory passes without loading the
engine or optional Pillow/fontTools/HarfBuzz backends. All annotations resolve;
all 22 engine aliases and historical root pickle lookups agree with canonical
module objects. Measurement, rendering and replacement interfaces retain their
existing identities. Production runtime and tracked tests are unchanged.

These are bounded assessment checks. They do not claim a fresh full-suite or
corpus validation of an implemented release. For v237, add module-boundary cases
for shallow record identity, borrowed inputs, retained/replacement identity,
source-ID/order/count semantics and actual supported/refused mask behavior.
Retain all resource lifecycle cases and existing proof variations. Verify cold
installed operation with generated exact-font fixtures, owned uninstall and
updater rollback/retry through the existing recursive delivery contract.
Then run the full regression suite, relevant native rendering and fresh paired
v236/v237 conversions of all 13 corpus tracks, expecting identical subtitle bytes
and complete statistics with unchanged font prerequisites.

## After-assessment evaluation

The complete masked-glyph operation can move with its current responsibilities,
resource lifetime and data flow intact. No new production workaround, duplicated
proof, unclear cache owner or additional preparatory release is needed. The
defining-owner test updates are identified and exercised by the prototype.
No new dedicated follow-up was uncovered. The already recorded scrolling
single-use iterator contract remains independent work.
