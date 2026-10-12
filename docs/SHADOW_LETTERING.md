# Final shadow lettering normalization — v174

The Sword S01E01 progressive skill scene uses an almost transparent primary
glyph (ASS alpha FE) and a practically coincident opaque shadow for its visible
letters. The simplified output retained both components. At 3:59 libass emitted
28 bitmaps for 18 active events: eight rectangles, nine sign labels and dialogue.

`normalize_shadow_lettering` runs once on the final default output after shadow
offset repair, masked foreground restoration, scrolling decisions and backdrop
reconstruction. It never participates in source/effect recognition or panel
admission. Support measurements and statistics retain their pre-normalization
inputs. Shared readers/writers, the generic caption renderer and legacy mode
are unchanged.

Admission requires one positioned, uniform, static literal span; primary alpha
FE/FF; visible shadow alpha below FE; BorderStyle 1; zero effective outline,
blur and edge blur; upright unsheared geometry; no clip; an ordinary horizontal
font; and finite position/offsets. The offset must be nonzero and at most 0.05
times the document unit on either axis, matching the existing nearly coincident
paint convention. Inline formatting is retained unchanged rather than flattened.
Ordinary filled text and offset drop shadows do not qualify.

The routine first filters resolved event state, then reuses `static_object_key`
to validate actual spans and inherited style/reset semantics. It transfers
shadow BGR colour and opacity to primary paint and moves the anchor by the actual
shadow offset. ASS uses the first position tag, so that tag is replaced rather
than appending a second position. Position serialization retains subpixel
precision. Explicit shadow alpha FF and all three shadow offsets zero override
inherited or earlier axis settings. Final paint overrides follow all leading
blocks, preserving global alpha/reset ordering. Text, geometry, event order,
timing and layer are retained; `replace_event` synchronizes the formatting cache.
No new font measurement, cache, configuration or data type is introduced.

The FE foreground contributes at most 1/255 opacity and is intentionally
discarded, using the script's existing faint-paint cutoff. Rasterization of an
offset shadow and a moved foreground can also differ slightly at glyph edges.
This is a bounded simplification, not a pixel-equivalence claim for every font,
resolution or renderer.

Verification:

- 69 focused assertions cover admission/rejection, inherited style paint,
  resets/global alpha, first-position and shadow-axis ordering, opacity,
  source immutability, idempotence, legacy separation and the actual scene.
- The permanent focused check renders 3:59 through FFmpeg/libass at 1920×1080;
  the before/after difference is at most one colour level.
- 57 scripts pass on each Windows/BASIC and RAQM target (114 executions).
- All eight full fixtures were converted on each backend with v173 and v174.
  Sword S01E01/track6 normalize 24 labels; Sword S01E02 track5 normalizes nine.
  The other five fixtures are byte-identical. All drawing events and existing
  statistics are unchanged. Both backends produce identical current outputs.
- 31 libass frames cover the seven progressive entrance boundaries and 4:17.
  The progressive scene differs by at most one RGB level. At 4:17 the largest
  edge difference is 28 levels, with mean absolute channel difference 0.028
  across the frame; the panel geometry and colour remain unchanged. Both
  scenes were visually inspected.
- At 3:59, bitmaps fall from 28 to 20 and summed bitmap rectangle area from
  4,038,411 to 3,604,974 pixels. This measures renderer output; TV performance
  still requires playback testing on the user's device.

The statistics key `shadow_lettering_normalized` records accepted event count,
including zero. Structural auditing against frozen v173 permits only the new
normalizer and final `simplify_ass` wiring. Historical stage audits retain that
baseline; their live semantic comparisons assert zero new normalizations on
unaffected fixtures. Reports retain runtime and regression-harness hashes.
