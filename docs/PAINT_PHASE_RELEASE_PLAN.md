# Source paint and configurable caption color phases

User-approved direction after v207: restore representative source paint, then
preserve a bounded amount of intentional whole-caption color change. Tuning must
be configurable, with explicit reporting when the limits remove changes.
This is a plan, not a claim that the implementation or validation is complete.

## Agreed default policy

- Minimum retained phase duration: **1.0 second**.
- Change budget: **one change per 2.0 seconds** of the caption's own proved
  display duration. For duration D, allow floor(D / 2.0) meaningful changes.
- No additional fixed two-change cap. A 6.67-second caption can retain three
  changes and four sustained phases; this fits the observed final opening cue.
- Rate and minimum-hold settings are independent and configurable. Document
  disable/unlimited semantics explicitly; disabling both restrictions preserves
  all structurally proved whole-caption phases. Disabling tuning does not waive
  text, geometry, visibility, paint ownership or compositing proofs.
- Count a synchronized fill/outline palette switch once, independently of the
  number of color channels, source layers or text fragments.
- These are whole-caption paint phases, including outline-only changes and
  switches involving an intentional spatial gradient. Karaoke sweeps, particles,
  flashes and continuous color animation keep their distinct simplification rules.

The duration belongs to the caption, not the song, sum of layer lifetimes or
number of fragments. Do not let incidental downstream interval extension create
an artificial change budget. Compare source timing at appropriate ASS precision;
retain exact shared handoffs without gaps or overlapping copies.

## 1. v208 — Restore representative paint ownership and backing handoffs

### Work

1. Trace and correct early source-row paint normalization. Resolve corresponding
   foreground and sharp backing strokes using source order and existing span/
   contour concepts, instead of pooling decorative glows and unrelated contour
   colors into one ambiguous vote. Preserve intentional gradients, transparency,
   borderless spans and the established two-unit reconstructed-outline cap.
2. Carry proved source relationships through reconstruction. Retain original
   paint/timing evidence until its consumers finish; avoid serializing away the
   evidence needed for later phase selection. Keep fill and outline selection
   coherent with an actual source appearance. Reuse the established font owner,
   source records and paint-proof concepts; do not start a general API refactor.
3. Correct the unequal-lifetime backing handoff. Investigate the existing stack
   producer's ability to own a foreground appearing inside a longer backing
   interval, then pass that ownership to the sequence consumer. The consumer must
   not carry an outline color while dropping its supporting width. Do not solve
   this by loosely equating timestamps or adding a late outline-restoration pass.
4. Keep these affected captions on representative static paint in this release.
   Establish dependable paint and evidence handoffs before introducing
   configurable temporal emission.
   Ordinary static source paint must not become eligible for neutral contrast
   replacement merely because decorative layers have another color.

### Evidence and validation

- Opening top row: white completed fills with source-colored contours, while
  suppressing the staggered reveal and transient particle colors.
- Bottom row: static colored contours, animated contour representative selection,
  `Soar above and put on` at 02:03.27 and `Even if my life ends, carry on` at
  02:19.87. Their foreground starts 40 ms after its backing.
- Synthetic complete/fragmented captions, gradients, source order, independent
  foregrounds, differing source intervals, transparency, partial support,
  obstructing content and genuine borderless text. Include immutable-input checks.
- Native comparisons with exact fonts; repeat conversion of changed examples;
  full current regression suite and fresh exact-font corpus comparison. Explain
  every changed output and preserve unaffected text, timing and geometry.

### After-release evaluation

Confirm that the responsible producers establish paint ownership and consumers
retain it, without exceptions in later filters. Identify any duplicated proof,
unclear source lifetime or downstream repair. Broaden the review only if the
existing ownership model cannot express the needed relationship cleanly.

## 2. v209 — Preserve configurable whole-caption color phases

### Work

1. Derive a caption's source paint timeline before destructive freezing or
   representative-phase removal. Prove corresponding complete text spans,
   compatible geometry, coverage, compositing and synchronized abrupt changes.
   Support fill-only, outline-only and coupled changes, including intentional
   spatial gradients. A change in fragmentation alone is not a color phase.
2. Distinguish whole-caption changes from ordered karaoke activation and other
   effects. Preserve representative completed karaoke paint while allowing an
   independently proved global palette change in that same caption. Reuse the
   existing sweep and source-alternation proofs where applicable.
3. Apply the configurable duration budget and minimum hold to the complete
   family. Use the existing tiny-color policy when deciding which changes are
   meaningful, without flattening intentional gradients. Initially, if the family
   exceeds either limit, retain one coherent representative source appearance
   across the cue; do not keep an arbitrary first N changes. Record the reason.
4. Emit accepted phases as two or more ordinary static captions with disjoint
   exact timing, shared placement, complete text and source-owned paint. Carry
   their authority through reconstruction, effect/frame merging, lyric handoffs
   and final compaction so later passes cannot collapse the decision or extend
   a repeated letter across the next cue. No serialized protective tags.
5. Expose settings in the engine configuration/CLI and `simplify_subtitles.py`,
   with the same defaults and actual pass-through. Update test-wrapper options
   where needed. Validate finite, nonnegative values; document units, budget
   rounding, disable semantics and interaction with the minimum hold.
6. Add explicit limit-contribution reporting: captions with reduced color changes
   and meaningful whole-caption changes removed by the limits, with effective
   settings and the reason (rate, hold, or both). Preserve per-track JSON and
   aggregate consistently through the shared Windows report catalog and both
   test wrappers. Display a clear reduction notice when limits remove changes,
   following the existing scrolling-limit reporting pattern. Report genuine
   zero contributions; missing counters from older engines remain unavailable.
   Do not count layers, glyphs, karaoke sweeps or unproved candidates as changes
   removed by this limiter.

### Real examples and expected decisions

| Example | Source phase lengths | Default expectation |
| --- | --- | --- |
| Opening Moonlight, 01:34.74–01:40.71 | 2.626 / 3.344 s | Keep the outline-only switch near 01:37.37 |
| Opening Under the sunlight, 01:57.43–02:03.27 | 2.582 / 3.258 s | Keep gold/orange then white/turquoise near 02:00.01 |
| Opening The miracle, 02:24.92–02:31.59 | 1.170 / 2.127 / 1.793 / 1.580 s | Keep all three proved switches |
| Ending earlier whole-line to gradient, 21:59.01–22:04.26 | 2.569 / 2.681 s | Re-evaluate as a proved whole-caption paint switch; preserve both if the temporal proof applies |

For the ending, v207 currently chooses the longer gradient phase for the whole
cue. Preserve its exact-font family proof, paint ownership, complete-text and
next-cue boundary safeguards. Temporal policy changes its representative-only
emission, not those protections. Inspect the rest of the ending for equivalent
changes rather than assuming this is the only example intended by the user.

### Validation

- Whole lines, words, glyphs and equivalent frame splitting; 1, 2, 3 and 25
  switches; long and short captions; clustered transitions; exact-threshold and
  near-threshold durations; tiny color differences; real spatial gradients.
- Sweep versus global switch, combined effects, flashes, ramps, fade tails,
  independent opacity, incomplete correspondence and intervening paint.
- Default, stricter, relaxed and disabled restrictions. Verify rate and hold
  independently, and coherent fallback with exact contribution counts.
- Engine/batch configuration parity and actual subprocess arguments; per-track
  and aggregate reports; older-engine missing-counter behavior. Run PowerShell
  reporting checks and distinguish native Windows coverage from Linux checks.
- Both opening rows and ending phases with source fonts, including samples on
  either side of each handoff. Check complete text, colors, contour width,
  placement, timing and concurrency. Whole-file repeat conversion must preserve
  accepted phase decisions.
- Full current regression suite, batch/MKV smoke test and fresh exact-font corpus
  comparison, accounting for every changed output and contribution count.

### After-release evaluation

Confirm that tuning affects only how much proved temporal paint is retained, and
that every limit-caused removal is visible in reports. Check that early producers
and later mergers share the same phase ownership instead of re-detecting intent
from simplified output. A broader review is warranted if preserving phases
requires several downstream exceptions, conflicting ownership rules or unstable
repeat conversion; otherwise report that no dedicated follow-up is needed.

## Scope and rollout

Two releases separate restoration of existing paint intent from a new temporal
retention policy and its public configuration/reporting contract. Keep the v209
feature, controls and reporting together. Do not split those across releases.
After each release, give the user a short evaluation of anything introduced or
uncovered that deserves a dedicated follow-up review. Global API and pass-local
index reviews remain separate unless concrete evidence makes one necessary.

Detailed v207 investigation evidence is local under
`validation/demon-opening-diagnosis/INVESTIGATION.md`; source/media assets remain
ignored and must not be published incidentally.

## v208 implementation

The source-row/stack ownership and representative-palette work is implemented
in v208. See [REPRESENTATIVE_SOURCE_PAINT.md](REPRESENTATIVE_SOURCE_PAINT.md) for
the producer/consumer contracts and validation entry points. v209's configurable
multi-phase emission remains the next planned step.
