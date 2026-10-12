# Complete-line jitter and paint layers — v175

## Behavior

The new `flatten_complete_line_jitter()` filter runs at the start of standard
text consolidation, before short-frame evidence is consumed by phase merging.
Its eight new definitions (one immutable family proof and seven functions)
share existing static span parsing, exact layout keys, colour dwell selection,
caption rendering and event replacement. Only `_consolidate_text_events()`
changes among existing definitions. Deprecated legacy mode bypasses the filter.
The established scale-trail/sequence pass remains unchanged: its admission
contract does not fit explicitly positioned jitter frames with staggered layers.

A proved complete caption becomes static opaque text with the existing simple
caption paint policy: the actual foreground's sustained fill, a supported
contrasting outline or black/white fallback, border 2 and no blur/shadow. This
is intentional effect flattening. For this ending, black `000000` foreground
with alpha 87 becomes opaque black with a white outline. Its pale backing is
removed, rather than averaged into foreground colour. Fonts and layout remain
selected from an authored foreground hold. Word echoes remain in this release.

## Admission bounds

- Exact literal text, font, size/scales, alignment, paragraph layout, style,
  actor, margins and document measurement context; uniformly styled spans.
- Positioned static source frames, no animation tags, clipping, rotation,
  vertical font or box style. Original source is checked as well as frozen text, including exact literal
  identity and unchanged frame timing; reconstructed fragment rows cannot enter.
- At least eight consecutive samples, each no longer than configured
  `short_duration` (default 0.16 seconds). Overlapping samples in one sequence
  reject admission. Real gaps split candidates.
- Whole-family horizontal and vertical extent at most 0.05 of font height.
  This subtitle's largest measured extent is 0.0358333 of height (2.795 pixels
  at 78 pixels). Small pairwise steps cannot widen the whole-family box.
- At least two direction reversals on an axis, ignoring steps no larger than
  0.001 of height. Monotonic travelling text is rejected even inside the box.
- A consecutive unchanged readable paint hold lasting at least twice
  `short_duration` (default 0.32 seconds), with primary alpha below 128.
  Qualifying separate holds remain separate coverage evidence. Fade-only echoes
  and inline gradients fall through to existing processing.

Stack ownership requires a complete family continuously witnessing the entire
caption interval, compatible placement within 0.05 of height, distinct
compositing layers, no overlapping copies within a layer, nearly matching layer
envelopes (endpoints within `short_duration`), and at least 80% actual readable
coverage. Shared readable coverage also requires 80%; the 0.011-second allowance
accounts for centisecond boundaries. A foreground interruption can be removed
while its complete backing stays readable, as in the first “Blow today”. A gap
in every layer remains a gap. Failed stack proofs retain independently proved
captions; unrelated opacity protection remains in force.

Ownership and replacement maps are pass-local. Borrowed source events and
visibility maps are not changed. Accepted families replace only their members.
No exact font measurement is needed to prove identical literal/layout/anchor
identity, so a missing font does not force guessed geometry. Per-span gradient
normalization, substring echoes and opening glyph reconstruction are deferred.

## Validation

The default suite runs all 59 scripts on Windows-style BASIC with real HarfBuzz,
then on RAQM: 118 script executions. The 78 new proof checks and 10 exact-font rendering checks cover admission/geometry/timing
boundaries, opacity, gaps, repeated captions, interrupted foregrounds, source
animation, missing fonts, gradients, unrelated overlays, ownership and
idempotence. Exact bundled Arial rendering checks prove a constant retained
image over the cue, source timing boundaries and bounded font/pose footprint.
The prior shadow audit uses its frozen v174 reference; live shadow behavior and
real scene rendering remain checked. The context audit covers the new 24th
caption-rendering call.

Full runs compare all eight existing subtitle fixtures and Attack on Titan on
both backends. Existing eight outputs and statistics are byte-for-byte unchanged.
AoT changes only its complete ED-R captions: 49 copies become 24, ED-R goes from
4,462 to 4,437 dialogue events, and total dialogue events from 7,929 to 7,904.
All 4,413 word echoes, opening events, other captions and timing gaps remain
unchanged. Both backends produce identical output bytes for every fixture.
Peak full-episode active events remains 26; this step does not address the
opening's remaining letter phases. Existing counters record frame reduction
under `text_effect_sequences_frozen` and layer reduction under
`stacked_text_copies_flattened`.

`validation/full-jitter-comparison-v175.json` contains per-fixture hashes,
conversion timings and dialogue additions while other events are active.
Timings are single runs, not a controlled repeated benchmark.
`validation/jitter-render-checks.json` covers 32 original/v174/v175 timestamps,
including cue starts, ends and gaps. The exact IM FELL English PRO font is not
available here; that episode render uses the same Arial fallback throughout and
is a diagnostic, not exact-font visual proof. Subtitle font names are retained.
The exact Arial regression supplies independent real-font render coverage.

TV playback remains the final practical check. The provided subtitle intentionally
retains word echoes for v176 and opening letter phases for v177.
