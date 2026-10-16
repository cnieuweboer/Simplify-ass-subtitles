# Configurable whole-caption color phases — v209

Whole-caption paint changes can remain as ordinary sequential ASS captions.
Each phase has complete text, the same recovered layout, source-owned fill and
contours, and a shared exact boundary with its neighbors. The two-unit cap on
reconstructed outlines remains unchanged. No hidden/protective tags are written.

## Controls

Both `simplify_ass.py` and `simplify_subtitles.py` accept:

| Option | Default | Meaning of zero |
| --- | --- | --- |
| `--color-phase-min-hold SECONDS` | `1.0` | Disable the minimum hold restriction |
| `--color-phase-change-interval SECONDS` | `2.0` | Unlimited number of proved changes |

The immutable engine `SimplifyConfig` exposes the corresponding
`color_phase_min_hold` and `color_phase_change_interval` fields. Values must be
finite and nonnegative. The batch script passes the effective values to the
engine. Both maintained PowerShell test wrappers expose `-ColorPhaseMinHold`
and `-ColorPhaseChangeInterval`, with the same defaults and zero semantics.
Native argument formatting uses invariant culture.

For a caption lasting D seconds, the change budget is
`floor(D / color_phase_change_interval)`. This uses the source caption's own
proved interval, not summed layer/glyph lifetimes or later interval extension.
There is no fixed two-change ceiling. A 6.67-second caption may retain three
changes and four phases; a sufficiently long caption may retain 25 changes.
The minimum hold applies independently to every retained source phase.

If either restriction fails, the complete family becomes one coherent
representative palette, weighted by source phase duration. The engine does not
keep an arbitrary first N changes. Equal exposure favors the earlier palette.
Both settings at zero preserve every structurally proved, ASS-representable
phase; disabling limits does not waive ownership, visibility or geometry checks.
Color-step clocks are canonicalized at ASS centisecond precision before
classification, so sub-centisecond source differences cannot create artificial
micro-phases. Emission uses one shared rounded boundary per handoff.

Examples:

```sh
python simplify_ass.py episode.ass --fonts-dir fonts
python simplify_ass.py episode.ass --color-phase-min-hold 1.5 --color-phase-change-interval 3
python simplify_subtitles.py episodes --color-phase-min-hold 0 --color-phase-change-interval 0 --yes
```

## Source ownership and classification

The source-row/stack producers capture immutable `CaptionPaintTimeline` records
before representative freezing or removal of alternating source planes. These
records borrow original source events and retain absolute phase timing and one
proved fill/contour appearance per non-space literal character.

The v208 normalizer and ordered contour proof supply paint. Whole-line, word
and glyph fragmentation share the existing exact-font alternation proof.
Stable single-plane rows can own authored contours as well. Coextensive static
paint planes are resolved together before sequential-frame timelines are built;
a backing's black fill cannot replace its foreground's real fill simply because
it has an earlier source ID. Existing clearance checks reject intervening paint
when layered ownership cannot be proved.

A synchronized palette step changes at least 80% of corresponding literal ink,
allowing fixed gradient anchors while rejecting staggered glyph activations.
A source row rejected as a sweep cannot re-enter as independently changing
words. Continuous ramps, uncertain transparency, unsupported geometry animation
and incomplete correspondence do not acquire temporal ownership. Sampling also
checks original opacity: settling a fade's paint does not prove that an invisible
color was ever displayed. Decorative blurred planes do not own the retained ink.
Tiny differences use the existing two-level RGB bound without transitive color
chaining; corresponding spatial gradients retain their literal paint.

The text-stage owner carries timelines independently of geometry reconstruction.
Once layout and lyric boundaries settle, it materializes the producer's paint
onto the complete retained caption. It requires unchanged source bounds and
complete literal/geometry correspondence; it cannot extend a caption across the
next cue or recreate missing text. Existing static color sequences enter the
same source proof before sequence merging, so repeated conversion preserves
accepted phases without serialized markers or downstream matching exceptions.
Final support reconstruction, paint compaction and serialization keep these
ordinary disjoint captions.

## Reporting

Per-track JSON retains effective settings and these genuine contribution counts:

- `color_phase_captions_limited`: captions reduced by either limit.
- `color_phase_changes_removed`: meaningful synchronized changes removed.
- `color_phase_rate_limited` / `color_phase_hold_limited`: affected captions by
  reason; a caption can occur in both and is counted once in the first field.
- `color_phase_captions_preserved` / `color_phase_changes_preserved`: retained
  phase families and their switches, not glyphs, paint layers or frame pieces.
- `color_phase_limits`: affected caption text, style, interval, removed count
  and reason (`rate`, `hold` or `both`).

The engine CLI emits a structured warning and readable notice when limits remove
changes. The production batch report retains raw track statistics and structured
`ColorPhaseWarnings` plus aggregated `ColorPhaseTotals`. Both Windows wrappers
use the shared counter catalog, per-track notices and report warning sections,
with the effective settings in text/JSON reports. Older engines omit unsupported
options and report missing counters as unavailable; explicit new settings against
an older engine fail clearly. A genuine zero means the engine reported no such
contribution, not that missing data were silently converted to zero.

## Checks and follow-up evaluation

`tests/check_caption_color_phases.py` covers independent/default/disabled limits,
three and 25 switches, complete text, exact handoffs, source immutability, mixed
contours, ramps, hidden paint, sweeps, interleaved content, frame splitting,
redundant planes, native references and repeat conversion. Existing alternation
checks now exercise both source phases under current policy while retaining the
next-caption safeguards. Historical integration comparisons explicitly assert
zero new phase contributions before excluding only the added reporting fields;
they do not substitute old paint behavior.

Run the current 90-script suite, the production batch checks and the shared
PowerShell reporting check. On the prepared Linux cloud instance, PowerShell
needs writable `XDG_CACHE_HOME`, `XDG_CONFIG_HOME` and `XDG_DATA_HOME`; this is
report/helper coverage, not native Windows process/filesystem validation.
The reporting check also drops its obsolete dependency on the retired production
PowerShell launcher, testing the two maintained wrappers.

`validation/run_caption_color_phase_corpus.py` compares the eleven exact-font
sources with v208. `validation/check_caption_color_phase_scene.py` verifies the
opening's source-colored steps, the ending's whole-line-to-gradient handoff,
unchanged text/geometry, next-cue timing, native rendering and full-file repeat.
Sources, fonts and generated media remain private ignored assets.

The implementation shares source ownership and palette canonicalization across
animated and serialized inputs. No late intent re-detection, per-show condition,
protective tag or new exception in frame/effect mergers is needed. Unproved
composites remain on representative paint. Follow-up evaluation and fresh
validation results belong to the completed release report; the separate global
API and pass-local index reviews remain outside this change.

## Fresh v209 results

All **90** regression scripts passed with unchanged runtime/harness inputs,
including **134** focused phase checks. The **63** PowerShell reporting checks
and the MKV extraction/simplification/remux/font-sync smoke test passed.

All eleven exact-font corpus conversions completed without missing fonts. Ten
outputs are byte-identical to v208. Demon Slayer changes only its four opening/
ending lyric styles: **12 captions retain 16 switches**, adding 16 sequential
events (467 → 483 dialogue events) while peak concurrency stays four. Geometry,
complete text, source cue intervals and the next-caption boundary remain intact.
The requested opening cues retain two, two and four phases respectively in each
row. The ending's whole-line-to-gradient handoff now retains both appearances.

Eleven native reference samples and ten original/v208/v209 comparison panels
cover the real handoffs. The complete output is byte-identical on repeat
conversion. A real CLI run with hold disabled and ten seconds per allowed change
reports exactly **16 changes removed from 12 captions**, all for the rate limit,
with structured warnings and effective settings.

After-release evaluation: source visibility and ASS precision needed explicit
handling, and serialized static sequences needed the same producer proof for
repeat conversion. These are now shared parts of phase ownership, rather than
late repairs or matcher exceptions. Historical statistics comparisons assert
inactive phase behavior before excluding new reporting fields. No additional
dedicated follow-up review is required by this release.
