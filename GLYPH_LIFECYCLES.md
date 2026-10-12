# Complete opening letter lifecycles — v177

A source-aware reconstruction pass now runs before effect freezing and existing
row reconstruction. It owns a complete family atomically; generic opacity and
phase-conflict guards remain unchanged for rejected families.

## Admission and ownership

The pass looks for repeated single-character fade entrances followed by short
highlight frames and a matching fade exit. Every accepted character has a unique,
touching same-layer temporal path and at least 0.32 seconds of readable core.
A style/actor family needs at least eight faded pieces and twelve short pieces;
this scopes admission to repeated letter-phase effects rather than ordinary signs.

Exact font advances normalize left/center/right anchors. Glyph paths require
upright geometry, uniform literal formatting, no clips, transforms, movement,
resets or karaoke, and bounded jitter (0.06 of text height per anchor match;
0.12 across a lifecycle). Missing exact fonts retain the source events.
Complete matching paint-layer paths are owned together. Short lower-layer paint
pieces may be owned only inside the foreground highlight interval.

Rows require at least four complete glyphs, a common readable core, coherent
baseline and temporal ordering. Existing recover_font_row() recovers spacing;
matches_authored_glyph_positions() checks the completed literal against the
retained font. Nearby rejected or unowned source text blocks incomplete-row
replacement. Competing source claims reject replacement.

## Output

Existing static paint voting chooses representative fill/outline, using saturated
source holds instead of overweighting fades. Existing render_merged_caption()
retains meaningful color spans, font and representative placement while removing
animation, blur and shadow paint. There is no new color normalization.
The reconstructed interval spans the proven entrance through exit. Existing cue
overlap trimming removes competing same-row fade tails in final output.

The matcher does not infer arbitrary moving/rotated glyphs, complex-script
shaping, unsupported spacing or missing lifecycle phases. Those continue through
the existing pipeline.

## Validation

The focused AoT opening has 21 romanized lyrics and 21 translated lyrics. All
romanized letter families become one static caption per line. Focused checks
cover source immutability, missing measurement, complete literal recovery,
missing phases, broken paths, clips, rotation, inline formatting, missing fonts,
color-independent ownership, preserved meaningful color and idempotence.
The focused suite has 84 checks, including synthetic boundaries and full opening integration.
Windows is the only regression backend run for this release. Full corpus checks
require byte-identical output/statistics for the other eight subtitles and
unchanged non-OP-R events in the full AoT episode. Libass samples inspect cue
boundaries and verify a pixel-identical static hold with the supplied font.

Full episode result: 3,491 → 354 events. OP-R drops from 3,158 events to
21 complete lines; OP-E, OP-KA, ending and signs are unchanged. The isolated
opening fixture drops to 42 events and peak 3; the full episode peak drops
from 26 to 13, with unrelated signs now determining that peak.
