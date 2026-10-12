# Near-color normalization — v178

The AoT v177 English/romanized opening and ending lines already have uniform
fill and outline colors, including every inline static text span. No dithering
color repair is needed for those reconstructed lines. Demon Slayer's ending has
many deliberate inline gradient steps and contrasting paint phases.

The final standard-mode pipeline now includes `normalize_near_text_colors()`
after support reconstruction and shadow-lettering normalization. It requires no
font measurements and does not change source matching or reconstruction proofs.

For each text style and separately for fill and outline, collect the complete
static palette. Normalize only if every RGB axis spans at most two 8-bit levels.
Choose an existing color by duration times literal-span length, with a stable
lexical tie-break. No rounding grid, nearest-neighbor chain or transitive
clustering is used. A long chain of individually close shades is retained.

Any inline color variation vetoes normalization for that style/channel, even when
its total variation fits inside the tolerance. Wide palettes also veto it,
including gradients split across separate events. Animated paint, karaoke,
movement, fades, mixed/drawing events and hidden paint are conservatively
excluded. Outline admission also requires a visible ordinary border.

This deliberately leaves inline noise untouched: color runs may change glyph
shaping and outline composition when combined. Meaningful color variation
elsewhere in a style can block normalization. Tiny intentional differences
between captions cannot always be inferred
from colors alone; the two-level bound limits the admitted visual change.

For an admitted channel, redundant color tags are removed and a representative
override is inserted only where inherited styling or a reset requires it. Styles
and borrowed events are unchanged. Text, alpha, timing, layers, positions and
other override ordering are retained. Changes use `replace_event()` after all
source-evidence consumers have finished. A second run is byte-idempotent.

`text_colors_normalized` reports changed events only when any change occurred;
zero-change conversions retain their existing statistics. Legacy mode does not
invoke this pass. CLI and PowerShell options are unchanged.

Run the focused check from the repository root:

```sh
python validation/run_backend_check.py --backend windows tests/check_color_normalization.py
```

The regression checks cover dither reduction, threshold boundaries, chaining, ordered gradients,
split gradients, resets, alpha, input ownership, real song palettes and pipeline
idempotence. The v177 lifecycle AST audit is frozen at its release reference;
the new check independently verifies that v178 adds only this helper and changes
only the final pipeline function.
