# Final caption/backdrop layers — v183

This document records the v183 correction and historical validation.
[CAPTION_BACKGROUND_OWNERSHIP.md](CAPTION_BACKGROUND_OWNERSHIP.md) describes its
v188 consolidation and explicit ownership handoff.

The first conversion of Sword S01E03 hides “(Cat Beastmen Style)” beneath its
paper panel. Sword S01E02 track 5 similarly hides the smaller VIT/MAG sign text.
Earlier layer checks run before final support reconstruction and nearly
coincident shadow lettering becomes ordinary opaque text. Repeated conversion
previously removed a hidden lower mask and advanced the captions through layers
0 → 1 → 2 before stabilizing.

Runtime **2026.10.13.183** adds `settle_caption_backdrop_layers()` after shadow
lettering normalization and before final color normalization/writing. It uses
only retained, measured enclosing backgrounds. It does not admit new drawings
or change the existing source/effect, timing, paint or support-selection policy.

## Proof and ownership

- A background must already enclose an associated measured caption, with a
  source layer no higher than that caption. Adjacency alone cannot qualify an
  arrow or foreground decoration. Fullscreen fills, clipped/translucent or
  unsupported shapes are excluded.
- A promoted caption must be opaque, positioned, static, contain a letter or
  digit, and match the panel's exact style and actor. Exact-font bounds must lie
  inside both the retained contour and original contour evidence. The panel
  must cover the caption's entire lifetime. Unknown fonts and ambiguous
  punctuation-only glyph artwork authorize no promotion.
- The caption must already belong to the panel. A higher layer qualifies as
  another version of that panel only when its footprint matches (allowing a
  small stroke-expansion/rounding margin). A different overlapping card already
  above the text remains a mask. Same-layer source order is considered too;
  assigning the mask's layer could otherwise reveal a later text record.
- The layer becomes the maximum of its current layer and one above every
  qualifying panel. All eligible panels are considered in the same call, so
  promotion does not depend on progressively rerunning the converter.
- A lower rectangular support is removed only when a retained opaque rectangle
  of the same style/actor covers its entire fill for its whole lifetime. Lower
  strokes, shadows, partial geometry or partial timing are retained. Hidden
  supports contribute to the existing `drawing_duplicates_removed` counter.
- Events, formatting/parser caches, catalogs and original support containers
  are borrowed. Layer edits use successors; result lists, associations and
  counters are independent. Text, font, paint, position, timing and unrelated
  same-layer ordering are preserved.

## Verification and scope

The focused check includes synthetic admission/rejection and ownership tests,
missing-font guards, helper idempotence, and complete first/second/third Sword
conversions. It regenerates the readable old third-pass oracle from immutable
v182 rather than depending on ignored historical output files.

Both affected captions are visible at layer **2 on the first conversion**, with
stable paint, geometry and timing thereafter. Their first/second/third sampled
renders are identical and match the verified readable v182 third conversion.

Across nine full corpus comparisons, caption changes are exclusively layers;
no text, paint, placement or authored timing changes. There are 91 layer
corrections across four Sword tracks and two fully hidden lower panels removed.
Five other corpus files are byte-identical to v182. Existing punctuation-only
custom-font artwork retains its source-layer policy; a previously observed
artwork layer change on a repeated conversion remains outside this caption fix.

Late text duplication and phase merging are the next separate releases. Full
file byte-idempotence is not claimed by this change. Final tag compaction also
remains separate. Checks use Windows BASIC/real HarfBuzz and FFmpeg/libass on
Linux; native Windows workflow and TV playback are not established by them.

Run from the repository root with restored fonts and test-data:

```sh
python validation/run_backend_check.py --backend windows tests/check_caption_backdrop_layers_render.py
python validation/run_review_checks.py
python validation/run_caption_layer_corpus.py
python validation/render_caption_layer_changes.py
```

The corpus comparator verifies the cached v182 source/runtime/output hashes
before reuse. Generated ASS files, JSON traces and PNGs remain ignored under
`validation/caption-backdrop-layers/`, `validation/caption-layer-corpus/` and
`validation/caption-layer-renders/`.

Final verification: all **66 regression scripts** pass, including **70 focused
caption/backdrop checks**. All nine corpus comparisons pass without missing
fonts. Fourteen sampled render pairs cover changed caption intervals and the
deliberately masked S01E01 card: twelve are pixel-identical to v182, and the
other two reveal only the intended smaller sign text. The “Owner”/“Race” masks
are unchanged in both S01E01 tracks. The two corrected frames were visually
inspected. PowerShell's 72 reporting checks and the MKV extraction/simplification/
remux/font-sync smoke test also passed.
