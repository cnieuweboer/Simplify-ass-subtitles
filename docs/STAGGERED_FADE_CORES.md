# Staggered glyph fade cores (v180)

Reconstructed captions can span the earliest glyph entrance through the latest
glyph exit. Flattening those fades makes their tails opaque. The existing late
overlap filter required source fragments at the caption's outer boundaries,
which did not prove the readable interval of staggered glyph rows.

`derive_staggered_fade_cores` now supplies that interval before the existing
filter runs. For each original glyph with `\fad(in,out)`, its fully readable
interval is `[start + in, end - out]`. The row core is the intersection:
`[max(start + in), min(end - out)]`. A positive interval strictly inside the
caption is required. Existing phase cores take precedence.

Every retained piece must identify one original stationary, opaque source with
matching literal text, font, layout and anchor. The caption must contain all
pieces, with one unambiguous provenance row. An anchor displacement of at most
0.0071 pixels accommodates rounding both coordinates to two decimals; all other
identity fields and the vertical lane match exactly. Missing, repeated or malformed fades, transforms,
movement, clipping, shear, drawing, inline state changes, karaoke and scrolling effects cannot establish this proof.
Inputs and original source events remain immutable; only independent row
successors receive the new evidence.

The existing overlap filter still chooses the handoff and protects the cores.
It declines overlapping readable cores, unrelated horizontal placement and
ambiguous collisions. No translation/romanized synchronization is introduced.

`tests/check_staggered_fade_cores.py` covers proof rejection, rounding bounds,
ownership, timing preservation, idempotence and the actual AoT opening against
frozen v179. The English intro has 21 lines and 20 overlaps in v179; v180 gives
20 touching handoffs without changing text, placement or paint. Romanized lines
retain their previous timing. The focused Overlord ending fixture likewise
repairs two overlaps across three captions while retaining every source core.
The complete Overlord episode additionally repairs one romanized ending overlap,
for three repairs across five captions in total.

Historical pass-refactor conversion audits opt into
`install_row_test_doubles(..., historical_fade_timing=True)`. That scopes the
pre-v180 fade policy to those conversions so their original equality assertions
remain meaningful; direct pass checks still run current functions. The new
staggered-core regression uses the production pipeline and real fonts without
this historical timing adjustment.

AoT opening conversion is byte-idempotent. The Overlord fixture retains a
pre-existing v179 second-pass reduction of unrelated romanized fragments
(99 events become 89). Its repaired English caption fields are byte-idempotent,
and the unrelated second-pass results still match v179. Global conversion
idempotence for that fixture remains separate work.
