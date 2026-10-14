# Karaoke completion source bounds — v196

Initial source-phase selection now permits a phase to start up to 11 ms before
the retained cue or finish up to 11 ms after it. This matches the existing 11 ms
endpoint-coverage proof. Previously, selection allowed only 1 ms outside the cue,
so a one-centisecond source overhang could remove a necessary phase before the
completion proof examined it.

Only these two selection bounds change. The coverage and phase-touching proof,
compatible paint holds, single transition per fragment, shared paint pair,
ordered activation and visible completed hold are unchanged. Cyclic highlights,
competing phases and unsupported transforms still fail the proof. No cue is
extended or shifted, and this is not a 50 ms frame allowance.

The optional outline-strip evidence route is unchanged; this fix applies to the
original-source foreground completion route. Both routes still share the ordered
sweep and replacement policy. Source dictionaries and retained events remain
borrowed read-only, with paint replacements preserving literal, geometry,
metadata, source identity and timing.

## Verification

`tests/check_karaoke_completion_bounds.py` exercises both endpoints, source and
retained event ordering, 10 ms overhangs, both sides of the 11 ms numerical bound,
12/40 ms rejection, internal gaps, missing and duplicate phases, competing
palettes and cyclic transforms. It also checks input immutability, preserved
literal/geometry/timing/identity and stable paint under repeated normalization.
ASS fixtures use centisecond timestamps; direct numerical probes avoid binary
floating-point equality ambiguity at exactly 11 ms. The unchanged coverage
proof retains its existing floating-point comparisons.

The active parser-continuation test now asserts the intended destination paint
for the two historical one-centisecond overhang examples rather than requiring
obsolete output parity. It keeps parser hygiene, immutability and replacement
metadata checks; all other historical comparisons remain unchanged.

`validation/run_karaoke_completion_bound_corpus.py` compares fresh conversions
against hash-verified v195 baselines for nine established sources and the full
supplied Goblin Slayer track. Fixtures, fonts, conversions and reports are local
ignored assets.

Fresh v196 corpus verification: all ten outputs and statistics are identical to
v195, with no missing fonts. The focused bound check passes 812 assertions.
All 73 scripts in the current Windows font-backend suite pass, including native
libass render checks. Runtime and harness hashes match the tested files.
