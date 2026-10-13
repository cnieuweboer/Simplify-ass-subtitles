# Late static phase merging — v185

The v186 consolidation replaces the separate late implementation with a shared
merger; see [STATIC_PHASE_MERGING.md](STATIC_PHASE_MERGING.md). The description
and results below record v185. Current functional checks use the shared merger.

Standard simplification now settles exact touching text phases after caption
support reconstruction, shadow-lettering restoration, color normalization and
late complete-copy cleanup. This catches fragments generated too late for the
early frame/effect passes. It does not repeat the animation or paint-selection
pipeline.

## Admission and ordering

`merge_late_static_phases()` groups by `static_object_key()`: literal spans,
paint, geometry, placement, layer, style, actor, margins, parser continuation and
document measurement must match exactly. It joins only touching intervals;
visible gaps and overlapping copies remain. Animated objects and drawings are
excluded. Partial opacity and inline gradients can join when their complete
static spans match, since no overlapping paint is added or removed.

The final list order is the compositing authority. Caption normalization and
support reconstruction have separate source-index namespaces; numerical source
IDs cannot prove the relative order of their combined output. Unchanged records
retain their identity. A timing successor borrows its retained record's cache,
continuation, catalog and context without editing them.

A merged record occupies its earliest original list slot. For every constituent
phase, the proof checks peers between that slot and the phase's original slot
only during that phase's own lifetime. A peer ending exactly at the handoff
cannot alter later compositing. This is the distinction missed by the older
whole-union ordering guard.

A peer active during a displaced phase blocks merging unless exact-font bounds
prove spatial separation. Unknown/animated/drawing/clipped/inline-layout bounds
remain a conflict. The spatial route excludes blur, edge blur, shadows,
underline/strikeout, extra spacing and opaque text boxes. Automatic wrapping
also blocks that route, except for a single glyph which cannot wrap. Bounds
include the existing outline and font overhang clearance; touching boxes are
not considered disjoint. Other layers retain their existing compositing order.

Only this narrow proof repeats. One join can remove an obsolete ordering
obstacle for another family. Every contributing round strictly reduces event
count, and the final result is stable when the helper is reapplied. No new
colors, coordinates or caption wording are selected. The existing `static_merged`
statistic (“identical timed copies merged”) includes late joins. Final output
counts use the settled list.

## Overlord result

The v184 first output has 2,221 parsed records. This pass joins 27 redundant
static phases, leaving 2,194, without changing the painted-event multiplicity or
paint/geometry signature at any atomic timing interval. The newly generated `o`
hold at 1280.68–1280.93 now joins its identical 1280.93–1283.26 hold directly.
Readable exposure and peak concurrency are preserved.

The historical second conversion removed another 37 styling phases by selecting
representative border/color/layer values. Those phases contain actual paint or layering differences
in the first output, not exact duplicate phases. This pass preserves them. A
whole second conversion can still change those effects and override spelling;
this release does not claim whole-file idempotence.

## Verification

```sh
python validation/run_backend_check.py --backend windows tests/check_late_static_phases_render.py
python validation/run_review_checks.py
python validation/run_late_phase_corpus.py
```

The focused check regenerates Overlord with immutable v184 and current engines
and the same supplied fonts. It checks exact interval signatures and multiplicity
throughout the full file, plus native-resolution pixel comparisons at every
ending interval where active record order changes, sampling its boundary and
midpoint. Direct controls cover gaps, overlapping paint, changing layout/paint,
active foregrounds/drawings, expired peers, source-ID collisions, reversed source
order, unavailable measurement and cache ownership. Scope audits bound the
production change to two phase helpers and final pipeline wiring.

The corpus runner regenerates all nine restored sources, checks exact font
availability and compares against hash-verified v184 outputs. It permits only
this final proof's changes and the `static_merged`/output counters. Generated
subtitles, reports and render assets remain ignored local files. Linux validation
uses Windows BASIC and real HarfBuzz; native Windows wrapper execution remains
separate validation. Gray-frame samples do not establish all-background or
all-frame equivalence independently of the temporal and ordering proofs.

Historical ownership and fade-timing audits keep their existing whole-file
oracles by bypassing the v185 final phase call only within those historical
comparison contexts. Their direct pass captures and ownership assertions still
use live code. The new full-file check and corpus runner exercise the unmodified
current pipeline. Previous release scope audits use immutable snapshots; their
functional copy/backdrop checks continue to exercise current behavior.

Fresh v185 validation passed all 68 suite scripts, 1,798 focused phase checks
and 36 pixel-identical native-resolution order/boundary render pairs. Overlord
loses exactly 27 static phases (2,119 → 2,092 Dialogue events); the other eight
corpus files and their statistics remain byte-identical/unchanged. No required
fonts were missing. The 72 PowerShell reporting checks and MKV extraction,
simplification, remux and font-sync smoke check also passed.
