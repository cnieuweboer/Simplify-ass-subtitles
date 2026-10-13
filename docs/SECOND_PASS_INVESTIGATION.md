# Repeated simplification investigation — v182

This investigation compares running the converter once and running it again on
its own output. It does not compare the extraction and cached-input test wrappers.
Production code is unchanged.

The first follow-up release, v183, implements final caption/backdrop layering;
see [CAPTION_BACKDROP_LAYERS.md](CAPTION_BACKDROP_LAYERS.md). The observations
below describe the original v182 investigation.

## What the second conversion improves

All 22 lyric-layer fixtures and nine full corpus outputs were converted again,
then a third time. The baseline corpus files were freshly generated during v182
validation; their runtime, source and output hashes are verified before reuse.
All conversions used the same exact fonts, Windows BASIC and real HarfBuzz on
Linux. No required fonts were missing.

**18 synthetic fixtures lose one redundant full-line copy.** The normal cases
go from two events to one; controls containing genuinely different text go from
three events to two, retaining the distinct caption. The authored wording,
font, fill/outline colors and complete readable exposure remain intact. Rendered
holds lose the slightly doubled stroke/offset effect, rather than introducing
new text or changing the timing. All synthetic second outputs are stable on the
third conversion. The other four fixtures already have stable output.

The real corpus has a mixture of consequences:

| Source | First → second events | Observation |
| --- | --- | --- |
| Sword S01E01 | 1,221 → 1,221 | Mainly override spelling and layer changes; sampled frames identical |
| Sword S01E03 | 385 → 384 | Hidden lower panel removed; previously obscured “(Cat Beastmen Style)” becomes readable |
| Shangri S01E14 | 7,203 → 7,203 | Byte-identical |
| WitchHat S01E02 | 831 → 831 | Byte-identical |
| Demon Slayer S04E02 | 523 → 523 | Redundant override compaction; sampled ending frames identical |
| Overlord S04E02 | 2,221 → 2,157 | 64 fewer ending-song events: 22 frame joins, 37 effect-sequence removals and 5 static joins |
| Sword S01E01 track 6 | 781 → 781 | Same override/layer effect as the other S01E01 track; sampled frame identical |
| Sword S01E02 track 5 | 349 → 348 | Hidden lower panel removed; smaller sign text becomes readable |
| Attack on Titan S02E01 | 376 → 374 | Two 40 ms light-colored sign copies removed; darker underlying copies remain |

Seven corpus files change on the second conversion. Five of those stabilize
immediately. The two Sword panel cases change their caption layer once more on
the third conversion (1 → 2), with identical sampled rendering, and stabilize
on the fourth. Convergence is not uniformly a two-conversion property.

There are 54 synthetic first/second frame pairs and 21 native-resolution corpus
first/second/third frame triplets, including actual Overlord ending intervals
as well as unchanged opening controls. The Sword sign restoration, synthetic
duplicate cleanup and Attack on Titan paint difference were visually inspected.
These gray-background samples do not establish all-frame or video-background
equivalence. Overlord's sampled ending frames include small visible changes;
lower event count alone does not certify all paint/compositing decisions.

## Why the synthetic copies survive the first conversion

`assign_layout()` marks repeated layers at multiple positions as `lyric=True`.
That evidence protects fragments from inappropriate sign-copy removal.
`reduce_static_sign_copies()` deliberately skips every lyric-marked event,
including the complete full-line copies in these fixtures. Later passes reduce
the layers and reconstruct captions, but this early filter is not rerun.

Row/lyric flags are transient evidence, not ASS fields. The existing normalization
boundary explicitly drops them. On another conversion, layout is recognized from
the reduced source: the remaining single copy at each position no longer proves
the original repeated-layer pattern. The captions are now `lyric=False`, so
`reduce_static_sign_copies()` removes the offset, wholly covered duplicate.

This is supported by causal diagnostics, not only counter correlations:

- Bypassing only that filter on the second conversion preserves the first
  conversion's semantic event set in all 18 affected fixtures.
- Letting only that filter see private successors with cleared lyric flags on
  the first conversion reproduces the exact second file in 15 fixtures. In the
  other three, later compaction/reconstruction also differs. The experiment
  restores the original flags on surviving records; it is not a proposed fix.
- The second-conversion trace attributes all 18 synthetic event removals to
  this filter. No unrelated caption needs to be discarded.

The flag has not become invalid globally. Clearing it prematurely would alter
later source-dependent proofs and reconstruction, as the three exceptions show.

## Other reasons uncovered in the corpus

**Later stages create inputs that earlier passes could have reduced.** Overlord's
initial merge pass still sees the original mix of paint layers and phases. Later
effect selection, coverage/reconstruction and override compaction leave simpler
held fragments. For example, a newly emitted `o` interval at 1280.68–1280.93
seconds precedes an identical hold at 1280.93–1283.26. The new first interval
does not exist at the first frame-merge call, but both are present when the
second conversion reaches it. The second frame merger joins such pieces; effect
freezing and touching-copy joining then make further reductions. The final
touching-copy pass also has stricter interleaved same-layer ordering protection
than the earlier frame merger, so final cleanup is not equivalent to repeating
the whole pipeline.

**Caption paint and support geometry are finalized after early layer checks.**
The Sword cases contain a lower green mask and an upper light paper panel.
The text-stage backdrop/layer proof runs before final support reconstruction and
shadow-lettering normalization. Consequently the first file can retain the
lower mask and place a newly opaque small caption beneath the upper panel.
The second conversion sees the already static rectangle and opaque text, drops
the hidden lower support, and raises the small caption to layer 1. The third
conversion raises it above the remaining layer-1 panel to layer 2. Existing
backdrop promotion uses the caption's layer at the start of that stage, so the
layer adjustment can take another conversion when the set of supports changes.

**Late formatting changes become early inputs next time.** Solid shadow-lettering
normalization emits new override blocks after ordinary text compaction has
finished. Another conversion can compact these blocks. This explains changes
that reduce tag spelling without reducing event count. Demon Slayer's ending
samples retain their rendering and intentional gradient.

**The older sign-copy pass is not paint-neutral.** In Attack on Titan, it removes
“North Group” at 728.20–728.24 seconds and “South Group” at 729.16–729.20. The
discarded fills are `EAE9E7`; retained covers have fills `222121` and `272627`.
The pass ranks opacity, layer, duration and source order, and checks broad layout
compatibility; it does not require matching fill/outline colors. Removing a short
flash may be desirable simplification, but this is a paint-selection decision,
not a pixel-identical deduplication. It should not be generalized without an
explicit representative-paint policy.

## Recommended follow-up

The second conversion demonstrably helps the synthetic cases and two obscured
Sword signs, and reduces residual Overlord effects. However, it also performs
different paint/compositing decisions and can require a third conversion for
layer stability. Do not implement an unconditional second run as the fix.

Address the missed first-conversion work directly:

1. Fix final caption/support layering after paint restoration and shadow
   normalization, so retained readable text sits above its actual final panel.
2. Add a bounded cleanup for proved redundant complete captions after the
   source-dependent proofs, with explicit paint/layout checks. Keep lyric flags
   intact until their existing consumers have finished.
3. Investigate Overlord's late-created phase joins separately, preserving the
   final same-layer compositing safeguards rather than bypassing them.
4. Compact final static text after late generators without changing paint or
   reopening source timing proofs.

## Reproduce

Use the current local fonts and corpus baselines generated by
`validation/run_lyric_layer_corpus.py`, then run:

```sh
source /workspace/.setup/simplify-ass/activate.sh
python validation/run_backend_check.py --backend windows validation/investigate_second_pass.py
python validation/render_second_pass_cases.py
```

`--corpus-only` is also available when invoking the investigation directly with
the backend startup environment. Generated ASS files, stage traces, font-selection
logs and PNGs remain ignored local assets under
`validation/second-pass-investigation/2026.10.12.182/`. Production runtime hashes
are recorded; missing fonts abort analysis. No production behavior was changed
for this investigation.
