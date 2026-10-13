# Settled paint for returning highlights — v191

v190's ownership proof correctly recognized returning highlights and their
persistent glow, but chose the temporary highlight color for the finished fill.
It also turned the raw glow color into an opaque outline. The regression check
protected that mistaken palette instead of the intended resting appearance.

The proof still distinguishes returning pulses from genuine one-way completion
sweeps. Paint selection now evaluates the known coextensive stack after its
transforms have settled, using the shared before/after foreground color. Pulse
duration does not vote the temporary highlight back into the finished caption.
The existing one-way karaoke completion policy is unchanged.

A small mask from the exact font estimates coverage in the glyph core and a
two-script-unit contour band. Source opacity and blur determine each copy's
contribution, composited in source layer/order on transparency. The core supplies
an opaque representative fill; the contour supplies representative color and
constant alpha. Measurements are pooled over the complete proved row, so glyph
thickness does not independently color each word. No video/background color is
baked into either paint. There are no new events or animated alpha effects.

The Gaussian footprint is an appearance approximation, not a pixel-exact libass
renderer or an ownership test. BASIC masks use the established ASS Windows
font-size scaling. Tracking, kerning, combining/RTL shaping, decoration, additional
stroke/shadow channels and excessive masks remain unsupported and keep the
ordinary stack fallback. Exact-font discovery/shaping APIs are unchanged. Masks
and accumulators expire inside this pass; source events/catalogs remain borrowed
and untouched. No new library beyond the existing Pillow dependency is required.

v190's exact text/geometry ownership, foreground compositing order and cleanup
remain in place. Row reconstruction preserves the finished paint. Other caption
renderers keep the ordinary contrast and opacity policies; this route supplies
its explicitly measured contour alpha. Existing near-color normalization can
still consolidate small palette differences after reconstruction.

The focused check now protects closeness to the resting base, subdued contour
strength, nonwhite bases, returning versus cyclic/independent effects, source
immutability and stable output, rather than asserting the temporary highlight's
hex value. Its real fixture is required; a missing original is a prerequisite
failure. The corpus runner compares all nine established sources against verified
v190 outputs. Native samples check nonempty static holds in the supplied opening.

Fresh verification: all 71 regression scripts pass, including 184 focused checks;
all nine established corpus outputs/statistics are byte-identical to v190.
The supplied track remains 660 events, with all required fonts available.
Fourteen native pairs retain stable holds. A settled first-word core comparison
against the original improves mean channel error from 34.1 to 10.1 levels on
black, 35.6 to 7.7 on gray and 38.5 to 4.9 on white. These samples support the
appearance correction; they do not establish pixel-exact glow reconstruction.
The added cost in the isolated supplied-track run is about three seconds over
v190; ordinary stacks do not create these masks.
