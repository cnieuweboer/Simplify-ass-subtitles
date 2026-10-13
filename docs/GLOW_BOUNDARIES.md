# Settled paint through separate fade phases — v192

Returning-highlight stacks can encode entrances and exits as separate events.
Freezing each exit's opacity independently produces a dim tail after the held
caption. v192 extends the proved stack's settled formatting over those matching
phases, including retained offset backing text, before ordinary row joining.
The existing phase merger joins the resulting equal-paint events.

Boundary ownership uses original source opacity transitions, not temporal
proximity or a subtitle title. Each word needs one stationary same-layer,
same-anchor, same-text and same-layout boundary adjoining its held interval.
The opacity transform must run across the phase and connect transparent primary
paint to the held opacity, or the reverse, without changing its colors or layout. Matching boundary legs of the exact
paint copies already collapsed into the held caption are removed under that
same ownership; they cannot become a second outlined caption in the fade.
The complete foreground row must agree on the boundary interval. Entrances and
exits are proved independently, so a cue may have only one supported side.
Missing words, changed paint, moved anchors, gaps beyond the centisecond join
tolerance, geometry animation or competing
candidates retain the ordinary fallback. Lower retained paint follows its own
held formatting rather than inheriting foreground paint.

Explicit phase-family membership admits these events to the existing merger
without changing global lyric classification. Separate cues containing the same
word remain separate families. The stack coordinator returns events, reductions,
phase joins and row evidence; joins contribute to the existing phase counter.
The compatibility tuple interface still reports total reductions.

The original held interval travels as `TextRow.phase_core`. Row reconstruction
can propagate a core only when every joined constituent has evidence; it protects
the union of those intervals. The existing fade-family collector also accepts
complete, unchanged current groups with these explicit cores. This lets the late
cue-overlap filter trim flattened fades without requiring the original held text
to have been fully opaque or authored with a single `\\fad`. One-sided cores are
valid. Overlapping readable cores and conflicting provenance remain protected.
Sources, event inputs, visibility maps and parser continuations are borrowed and
unchanged. No new pass or production counter is introduced.

Validation extends the returning-highlight check with both-sided and exit-only
lifecycles, rejection cases, counter accounting, repeat stability, preserved core
handoff and overlapping-cue behavior. The real fixture checks settled paint across
every held word. The corpus comparison uses verified v191 baselines; native
samples include entrances, holds and exits rather than only the held middle.

Fresh verification: all 71 regression scripts pass, including 236 focused
checks, as do the 10 Python wrapper checks and environment smoke test. All nine
established corpus outputs and statistics are
byte-identical to v191. The supplied track falls from 660 to 324 events, and peak
concurrency from 43 to 38. All styles outside the opening lyrics and chant remain
unchanged. Existing phase joins increase from 18 to 360; stack reductions from
909 to 1,267; four cue overlaps are trimmed. Every required font is available.
Native samples cover all 14 top-left lyric lifecycles and nine accepted chant
stacks; the former also preserve pixel-identical held appearance against v191.
Unproved neighboring chant families retain the existing effect fallback and are
not claimed as static lifecycle successes. Recorded supplied-track CPU time is
23.1 seconds versus 22.1 seconds for v191 on this host.

The boundary coordinator is repeat-stable, but the complete supplied file is not
globally idempotent. Reprocessing generated output drops the contour of some
joined captions through the older stack reducer (for example the first cue's
“onto me my adolescent” span). Reproduced with the immutable v191 engine and its
verified output: the same span becomes layer 0 without its green contour. v192
also exhibits that separate behavior. Do not count the full second conversion
as an idempotence pass; this release verifies fresh-source single-run lifecycles.
The upstream stack/reconstruction ownership for generated joined captions needs
a focused follow-up rather than a boundary-specific exception.
