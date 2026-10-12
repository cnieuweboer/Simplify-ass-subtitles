# Synchronized handoffs (v181)

The late fade-overlap filter now chooses a shared boundary when a separate
positioned text row changes in the overlap window. It continues to protect all
source-proven readable cores and all exposure outside the original collision.

A clean, touching reference pair supplies its exact authored boundary only when
its outgoing/incoming captions respectively cover the target's readable cores.
The boundary must lie in the target's permitted source-fade handoff interval.
The reference pair stays unchanged.

When both rows overlap, each must independently qualify for the fade filter.
Their outgoing cores must overlap each other in time, as must their incoming
cores. A common boundary must lie in every collision and every protected-core
gap. The filter chooses a representable centisecond in that common interval.
This also works for more than two compatible rows.

Matching requires distinct vertical rows, intersecting horizontal anchor spans,
and actual text changes. Top/bottom translations and different alignment bands
can match. Font size determines the minimum separation between visual rows;
there is no arbitrary maximum vertical distance. Static singleton captions with
finite positions and sizes qualify. Drawings, scrolling, movement, clipping,
transforms, live fades, karaoke, multiline captions and ambiguous provenance do
not supply reference transitions. Existing filter groups without explicit
positions, or with multiple separately painted events, retain independent timing.

There must be at most one candidate transition per lane in a connected group.
Conflicting clean boundaries, competing transitions, incompatible core windows
and an authored reference shared by competing groups retain the old independent
handoffs. The algorithm reads one snapshot and assigns shared boundaries before
applying any edits, so input order cannot cause one lane to influence another
through an already modified event. Inputs, source evidence, styles and row cores
remain immutable; returned event successors change timing only.

`tests/check_synchronized_handoffs.py` covers clean references, two overlapping
rows, top/bottom placement, alignment bands, ambiguity, safe-core preservation,
ownership and idempotence. It also converts the actual AoT opening against frozen
v180: all 20 English/romanized transitions share exactly the same centisecond.
Historical conversion equivalence and v180 staggered-core checks explicitly
retain their earlier timing policy while the new check runs the production
pipeline without that adjustment.
