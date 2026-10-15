# Reconstructed outline widths — v202

## Decision

Retain the two-ASS-script-unit limit on each axis of a **reconstructed,
source-proved caption contour**. Preserve narrower widths, borderless spans,
outline color and independent outline transparency. The limit is deliberate
simplification, not a claim that two units reproduce every authored contour or
that two units are an experimentally optimal hardware threshold.

This is not a global subtitle rewrite: ordinary retained static events keep
their authored widths. The uncertain reconstruction fallback and the measured
backing/glow approximations still use their established two-unit contours;
those approximations do not acquire authority to copy a decorative thick stroke.
Blurred glow, clipped outlines and conflicting layers need their existing paint
and ownership proofs, not an increased border allowance.

## Evidence and tradeoff

`validation/run_outline_policy_review.py --compare-authored` converts all ten
restored sources twice: current production policy, and an ignored experimental
engine differing only in whether proved source widths are capped. Original
source files and v201 output baselines are hash-verified. The candidate never
changes the production runtime. Rendering uses the actual resulting subtitles,
not a paint substitution in integration tests.

The authored-width candidate makes thicker lettering more faithful in weight.
There is a real readability benefit on some map labels: the thicker white stroke
around “Wall Sina” separates its dark fill more clearly from gray. This is not a
uniform improvement across the inspected captions. On synthetic Volkhov
captions, large contours visibly close spaces and create
heavy connected outlines. Axis-specific translucent contours retain a softer
appearance, but that benefit alone does not justify relaxing all source widths.
Native panels compare gray and white backgrounds; no source video was available
for judging integration with the scene.

The uncapped candidate also retains incidental width animation. Attack on Titan
S02E01 grows from 351 to 684 dialogue events. Around 12:05, “Wall Sina” retains
separate frames with widths 4.515, 4.500, 4.470, 4.455, etc. Preserving those tiny
changes defeats useful frame reduction. Overlord S04E02 grows from 2,089 to 2,090
events, loses one shared-interval row join and three reduced tails around
02:13.15–02:13.40. Other corpus event counts remain unchanged. Representative
native comparisons also cover Demon Slayer S04E02 at 21:45 and Sword S01E01
track 6 at 22:30. Those two samples are pixel-identical between policies: their
selected reconstruction routes do not obtain a larger proved authored contour.
They serve as controls, not evidence that a six-unit source effect was preserved.

The decision therefore trades some authored weight/separation for useful event
reduction and established row assembly. It does not dismiss the map-sign benefit.
Retaining that benefit without preserving the width animation needs an explicit
representative-width policy, rather than copying every frame's authored value.

These are general source structures: animated stroke widths and wider ink
footprints, not anime-specific admission rules. A future proposal could select a
representative stable stroke independently of frame splitting, then revisit its
footprint. Simply deleting the cap does not establish that policy. It would need
evidence that the improvement warrants the additional geometry/occlusion work.

## Geometry ownership and correction

Source grouping and compositing checks must use **original source extents**.
Measuring a selected thin contour cannot prove that a discarded thicker source
was redundant. Reconstruction then emits its chosen capped paint; later caption/
panel containment checks measure that **actual emitted state**. Neither side
should substitute the other side's width.

The shared-interval pass already collects maximum inline border, shadow, blur
and edge-softening extents before measuring a uniform-layout caption. Its handoff
had a defect: replacing both text and state in one `replace_event` call reparsed
the stripped text and overwrote the accumulated state. A wide middle span
followed by a narrow/borderless span could consequently lose its footprint.
v202 reparses the measurement text first, then installs the accumulated extent
state. This fixes the responsible handoff without changing parser semantics,
weakening geometry admission, or adding downstream exceptions. Input events
remain borrowed and unchanged; the bounds cache stays pass-local.

Anchor-based row grouping continues to use font height and source positions.
Actual coverage, interleaving and backdrop decisions use their existing measured
footprints. Static-outline strip detection deliberately separates foreground ink
from surrounding contour evidence; its fill measurement is not a claim that the
whole stroke is covered. Unknown inline layout or unsupported projection remains
unknown rather than guessed. Drawing/vector stroke policy is unchanged.

## Checks and after-release evaluation

`tests/check_outline_policy_render.py` checks independent axes, widths above and
below the limit, transparent contours, source immutability, repeat rendering,
native capped pixels, and containment of emitted and original inline ink. It
includes a panel that contains the capped output but not its thicker source,
and verifies that ordinary static text retains its authored thick outline.
The shared-interval checks also cover a distant interleaved caption whose wide
middle span reaches the row. It blocks an unsafe join, while narrower, disjoint
versions still reconstruct. The inline continuation check retains historical
parser/history comparisons and replaces obsolete lost-extent parity with direct
border/shadow/soft-edge assertions.

Fresh v202 verification passes all 81 current regression scripts, including 92
outline-policy/native geometry assertions, 212 shared-interval assertions and
51,222 inline continuation assertions. The runtime and test harness remained
unchanged throughout the final suite. All ten production-policy corpus outputs
retain v201 bytes and statistics, with no missing fonts. Twenty fresh conversions
cover both policies; twelve native panels compare real and synthetic captions.
The MKV extraction/simplification/remux and font-sync smoke check also passes.
The fixed handoff matters to the synthetic counterexamples without imposing
unrelated changes on the restored real examples. Generated subtitles,
experimental engines, fonts, panels and reports stay ignored local assets.

The chosen policy is explicit, source/output footprint ownership is distinct,
and the identified handoff is corrected at its owner. Keeping the cap avoids
substantial changes to row assembly or occlusion reasoning. A broader review is
not required for this release; authored-width preservation would require a
separate representative-stroke and geometry proposal supported by real evidence.
