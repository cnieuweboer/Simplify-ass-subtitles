# Late complete-copy cleanup — v184

Standard simplification now removes remaining nearly coincident complete text
copies after lyric reconstruction, caption/support layering, shadow-lettering
restoration and small color normalization. Early lyric flags and source evidence
remain available to their original consumers. This is a bounded final pass,
not a second conversion or a new representative-paint selection rule.

`remove_late_complete_copies()` compares `static_object_key()` literal spans.
Text, style, actor, margins, layer, document measurement, parser continuation,
font, emphasis, wrapping, rotations, scale, spacing and every paint channel must
match exactly. Only the explicit position may differ: both coordinate offsets
must fit a 6% bound using the smallest literal-span height in either record.
Offset copies that permit automatic wrapping remain separate: a different
anchor can change the actual line breaks even with identical formatting. This intentionally
removes a tiny doubled stroke/jitter effect; it does not promise pixel identity
with the doubled input. Small color normalization has already run, so its
existing bounded policy determines which tiny color differences have converged.
Larger intentional inline gradients still participate in exact span matching.

The covering record must contain the entire discarded interval. Neither timing
nor text is extended or replaced. Longer holds win; equal holds use stable list
order. Only retained records authorize removal, preventing a chain of small
position differences from merging increasingly distant anchors. Another active
same-layer record between the copies blocks removal, including drawings. This
conservative ordering guard preserves foreground/card compositing even when the
intervening record appears far away.

Animated, moving, faded, karaoke, clipped and partially translucent records are
excluded. Drawings, unpositioned collision-managed text and lone glyphs are
excluded. Copies in different layers remain separate. All literal spans must
share one anchor. Records, styles, formatting caches and lyric flags are borrowed
without mutation. Only the final output list changes.

The existing `deduped` statistic (“duplicate layers removed”) includes these
removals; no new sparse counter or reporting convention is introduced. Output
and concurrency statistics are computed from the cleaned final events.

## Validation

Run the focused checks and complete suite:

```sh
python validation/run_backend_check.py --backend windows tests/check_late_complete_copies.py
python validation/run_review_checks.py
```

The focused check uses all 22 existing exact-font lyric-layer fixtures. Eighteen
previously needed a second conversion to remove a complete redundant copy;
these now reach that event count in one conversion. Distinct displaced rows,
fonts, sizes, case and spacing remain. Direct negative controls cover paint,
inline gradients, alpha, geometry, timing and interleaved compositing. Render
samples at the entrance, hold and exit of each reduced fixture compare the first
output to the previously useful second-conversion result. These sampled gray
frames do not prove equivalence for every video background or frame.

`validation/run_late_copy_corpus.py` regenerates all nine restored corpus sources
and compares them against hash-verified v183 outputs under
`validation/caption-layer-corpus/windows`. Both engines use the same local fonts;
missing-font reports abort the comparison. Reports and assets remain ignored.
The runner permits only the new final cleanup's removals and associated counts,
and explicitly checks that Attack on Titan's short light-colored North/South
Group copies remain rather than being deduplicated against dark paint.

Overlord's residual late phase joins and final override compaction remain
separate follow-up work. Whole-file second-conversion idempotence is not a claim
of this release.

Fresh v184 verification passed all 67 suite scripts, 221 focused checks
(including 54 render comparisons), all nine corpus comparisons, 72 PowerShell
reporting checks and the MKV extraction/simplification/remux smoke check. All
nine corpus outputs and their statistics are unchanged from v183; no exact
fonts were missing. Windows BASIC plus real HarfBuzz was exercised on Linux;
native Windows wrapper execution is still separate validation.
