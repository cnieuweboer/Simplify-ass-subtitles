# Matched foreground/backing fades — v203

The stack producer now carries an established opaque caption's paint into
matching entrance/exit phases. Previously the opaque stack became one caption,
but its fading phases hit v201's translucent-composite guard and kept both source
planes. A capped two-unit contour could therefore abruptly return to the source
backing's roughly six-unit contour when the fade began.

This is a reconstruction of a caption fading as one object. It deliberately
removes the extra pale fill contribution under the fading foreground. It does
not claim pixel equivalence with separately fading source planes. The readable
fill/outline, existing contour cap, movement and fade boundaries define the
intended simplified result.

## Evidence at the stack producer

`_matched_backing_fade_phase()` establishes corresponding complete literal spans
on two coincident paint planes: a borderless foreground over a stroked backing
whose fill and outline have the same color at each range. Both planes must have
matching resolved geometry throughout the literal, including font, spacing,
position, origin, rotation, skew and perspective. Layout is compared directly;
an axis-aligned box is not used to guess projective containment.

The backing's primary and contour opacity must equal the foreground's primary
opacity. A caption phase uses one common opacity, rather than independent letter
fades. Independent contour fades, visible offset shadows, missing contours and
uncertain masks retain the ordinary route. Original-source override blocks are
also checked for clips, including clips inside transforms, so earlier mask
removal cannot manufacture complete-caption evidence.

`_index_matched_backing_fades()` connects compatible, nonoverlapping phases of the
same literal/style/actor/margins. Gaps are limited to the existing centisecond
rounding allowance of 11 ms. The family needs at least 20 ms of actual opaque
support in total; splitting that hold does not erase its evidence. Opacity must
decrease into the opaque hold and increase after it. Returning pulses,
overlapping alternatives and disconnected cues cannot borrow that hold.

The complete family must agree on capped contour widths and surface formatting.
Per-character fill/outline palettes use the existing complete-palette two-RGB-level
rule; wider intentional temporal changes veto reconstruction. Spatial gradients
remain separate character ranges. Foreground/backing roles follow numeric layer
and source order. An active intervening plane or unknown compositing order keeps
the stack rather than inventing an occlusion proof.

The existing opaque producer continues to own the readable hold. New immutable
`MatchedBackingFade` records carry its compatible span paint to fading phases.
They live in `StackedTextContext`, borrow the phase events read-only and expire
with this pass. Candidate phase evidence is distinct from an authorized family.
No serialized marker, global cache, persistent ownership graph or new late pass
is added. The returning-glow sampler remains separate: its blur-only supports do
not meet this stroked-backing admission.

## Emission and movement

`_render_matched_backing_fade()` reuses `SourceCaptionPaint`, the caption renderer
and literal-span serializer. It emits the proved fill/outline with each phase's
actual primary and contour alpha. Narrower and axis-specific contours remain
subject to the existing policy; the two-unit cap is not relaxed.

Each source frame pair becomes one caption at that frame's existing position,
angle, scale, perspective and interval. Original foreground pose support is
handed to the successor. No representative static placement is chosen, and no
motion/jitter bounds or scrolling concurrency settings change. The general v201
guard remains unchanged for composites without this proof. Removed backing
events contribute to the existing stacked-copy counter; no new counter or
wrapper-report schema is introduced.

## Validation workflow

`tests/check_matched_backing_fades.py` covers gradients, uniform paint, shared
entrances/exits, projection, different tag boundaries, split holds, axis widths,
tiny palettes, source immutability and complete-conversion repeat stability.
Counterexamples include different fades, absent/brief opaque support, reversals,
returning pulses, geometry changes, independent paint/shadows, interleaving,
unknown order and original static/animated masks. Behavioral checks retain faint
uncertain planes rather than only inspecting a proof flag.

`tests/check_matched_backing_fades_render.py` compares complete native output
against independently authored unit fades on black, gray and white. It checks
scrolling/projective phases, the hold, fade transitions and both cue boundaries.

The supplied MKV font is internally **Uniform / Bold**. It is the only embedded
Uniform face, so the unset ASS bold flag correctly resolves to that same-family
face. Real rendering explicitly loads the uploaded font directory and verifies
libass's actual Uniform-Bold selection, instead of accepting a silent fallback.

Regenerate v202 with the same installed fonts before comparing production output:

```sh
python validation/run_matched_backing_fade_corpus.py --baseline-only
python validation/run_matched_backing_fade_corpus.py
python validation/render_matched_backing_fades.py
```

The baseline engine must have the recorded v202 hash; its default local snapshot
is under `validation/outline-policy-corpus`. Baseline/current sources, engines,
outputs and font manifests are checked. Every removed/changed record must belong
to an approved phase with unchanged geometry/timing; every added record must also
match the proved per-character paint. Other records remain identical.

Real rendering covers all three captions before and during the fade. Actual
viewport pixels are checked against independently authored expected captions.
Separate, clearly labelled paint crops translate both position and origin solely
for inspection, allowing the offscreen New Land caption to be examined. Converter
outputs and source subtitles retain their original coordinates. Fonts, uploaded
archives, generated subtitles, diagnostic crops and reports remain local assets.

Fresh verification passes all 83 regression scripts, including 121 focused
backing-fade assertions and 210 native synthetic checks. Runtime and harness
inputs remained unchanged throughout the final suite. All 24 real-caption
samples match independently authored expected pixels in the actual viewport and
the translated diagnostic crops; six source/v202/v203 panels were inspected.
The MKV extraction, simplification, remuxing and font-sync smoke workflow passes.

The same-font corpus comparison changes only the three intended captions in
Shangri S01E14: 24 fading pairs each become one event, removing 72 records across
the whole fade, not just the 36 extra records introduced by v201. Dialogue count
changes from 7,240 to 7,168; the stacked-copy counter increases from 1,559 to 1,631.
Every changed record is bound to its approved source geometry/interval and final
span paint. Other statistics and all nine other corpus files remain identical.

Adding the supplied MKV fonts independently makes v202 retain six additional
supporting drawings compared with its older local baseline (one at 09:04.19 and
five at 13:42.34). Regenerating v202 with the same font manifest isolates that
asset change from v203; no drawing change is attributed to this paint handoff.

## After-release evaluation

The change extends the existing opaque stack paint decision at its producer.
Source visibility and compositing evidence survive until that decision; matching
projective planes require no guessed static placement. The implementation needs
no downstream exceptions or larger ownership model. The scrolling concurrency
cap, global API review and pass-local index review remain separate work.
