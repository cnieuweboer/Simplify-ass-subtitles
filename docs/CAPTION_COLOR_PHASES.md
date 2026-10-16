# Configurable whole-caption color phases — v209

Whole-caption paint changes can remain as ordinary sequential ASS captions.
Each phase has complete text, the same recovered layout, source-owned fill and
contours, and a shared exact boundary with its neighbors. The two-unit cap on
reconstructed outlines remains unchanged. No hidden/protective tags are written.

## Controls

The engine `simplify_ass.py` accepts:

| Option | Default | Meaning of zero |
| --- | --- | --- |
| `--color-phase-min-hold SECONDS` | `1.0` | Disable the minimum hold restriction |
| `--color-phase-change-interval SECONDS` | `0.0` | Unlimited number of proved changes |

The immutable engine `SimplifyConfig` exposes the corresponding
`color_phase_min_hold` and `color_phase_change_interval` fields. Values must be
finite and nonnegative. The batch script passes the effective values to the
engine. Wrapper defaults are configured separately. Both maintained PowerShell
test wrappers expose `-ColorPhaseMinHold` and `-ColorPhaseChangeInterval`, with
the same zero semantics.
Native argument formatting uses invariant culture.

Since v212, the engine defaults to the one-second minimum hold alone. The
overall change budget is disabled unless explicitly enabled with a positive
`--color-phase-change-interval`.

When enabled, for a caption lasting D seconds, the change budget is
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

## Matched outer-contour ownership — v210

The existing source timeline producer can also prove an outer caption plane
whose contour color follows the foreground fill. The phase decision then applies
to both planes. Rapid cycling becomes one coherent appearance, while accepted
slow changes keep synchronized foreground and contour phases. The settings,
disable semantics and caption-based reporting are unchanged; paint layers do not
multiply the reported number of removed changes.

The proof uses complete static captions with identical resolved literal/glyph
geometry and matching placement, margins and measurement context. Style names
may differ. Every source boundary is checked, so different event splitting
cannot hide an independent change. Foreground ink and its contour must be opaque,
the lower contour must be an expanded or blurred version of the same glyphs,
and its corresponding colors must follow foreground fill within the existing
two-level tolerance. Spatial gradients remain spatial gradients. Continuous
coverage, numeric layer order, exact-font clearance and unique ownership protect
other content. The shared clearance helper now reuses one implicit-margin anchor
resolver; it never changes serialized placement or collision policy.

Contour opacity, stroke and blur must remain stable. Clipping, shadow offsets,
uncertain wrapping, differing geometry, gaps, overlong backing lifetimes and
intervening ink do not acquire companion authority. Unsupported animated or
projective layouts remain protected. This is a complete-caption paint-plane
proof, not a new fragment or moving-caption matcher.

Immutable companion records carry source identities and the fill exposure
beneath the opaque foreground. Earlier effect-sequence merging can discard that
exposure, so the consumer must not infer it from the remaining first frame.
Fill exposure must be stable within each foreground phase; unrelated underlying
fill colors or mid-phase exposure changes do not confer ownership. When limits
select one palette, its earliest source occurrence supplies the companion's
other fill paint as well. Retained blur, contour width/opacity and geometry stay
with the simplified plane. The foreground's existing two-unit reconstruction cap
is unchanged. Already-flattened stacks stay flattened; no layer is resurrected.

Emission uses this producer evidence after layout, alongside existing foreground
emission. It requires complete surviving source lineage, the original cue union
and unchanged shared geometry. It does not discover new matches downstream or
add exceptions to frame/effect matchers. Ordinary sequential output retains its
paint, geometry, timing and compositing on repeat conversion without hidden tags.

`tests/check_caption_color_phases.py` includes different styles, event splits,
gradients, rotation, implicit placement, accepted/limited/disabled phases, retained
blur, source fill exposure, already-flattened stacks and uncertain counterexamples.
Native references check accepted authored phases and static limited composites.

Fresh corpus and real-scene commands:

```sh
python validation/run_caption_glow_phase_corpus.py
ASS_REGRESSION_FONT_BACKEND=windows \
PYTHONPATH="$PWD/validation/backend_startup:$PWD" \
python validation/check_caption_glow_phase_scene.py
```

They require the private v209 engine and corpus summary/outputs under
`validation/kill-color-phase-investigation`, the original eleven corpus assets,
and the uploaded `blood-color-phase-investigation` / `kill-color-phase-investigation`
subtitle/font folders. The runners verify source, engine, font and baseline
hashes. Real-scene references hold a genuine source appearance, simplified by
v209 independently of the new ownership proof, with the foreground's established
two-unit reconstruction cap made explicit. Generated reports, media and fonts
remain ignored development assets.

### Fresh v210 results and follow-up evaluation

All **90** regression scripts pass with unchanged runtime/harness inputs,
including **275** focused phase checks. The **63** PowerShell reporting checks and MKV
extraction/simplification/remux/font-sync smoke test pass. The thirteen-file
exact-font comparison has no missing fonts. **Twelve outputs are byte-identical
to v209**, including Blood+ and Demon Slayer. Kill la Kill changes only its two
matched outer-contour styles: **142 frame events become 14 held events**, taking
the full output from **592 to 464** dialogue events. Foreground records remain
identical, peak concurrency stays four, and reporting still counts **128 changes
across 14 captions**. Timing, complete text, contour transparency and geometry
remain intact.

**35** native held-source reference samples cover all seven lyric pairs, including
the original rapid-change boundaries. Five original/v209/v210 comparison panels
show the now-coherent foreground and outer contour. Accepted synthetic phases
also match authored rendering with retained blur; disabling limits preserves
the full proved palette progression.

The ownership extension is upstream and semantic. It preserves source fill
exposure that earlier sequence merging could otherwise lose, reuses measured
clearance, and adds no per-show conditions or late matcher exceptions. The
fourteen matched captions retain paint, geometry, timing and compositing on
repeat conversion.

One **separate follow-up** was uncovered: Kill la Kill's **2:30.79–2:34.38**
“omoi wa kitto hitotsu” / “We must be one in spirit.” Every source color phase
has a fade tail (142 ms; 271 ms for the last phase). The original fade-bearing
sequence has no static phase authority; after simplification removes the fades,
repeat conversion recognizes two captions with four changes each. Hash-bound
v209 already changes their foreground on repeat. v210 additionally keeps their
glows coherent when that later proof becomes available. This is not whole-file
idempotence: the real-scene runner explicitly records the older fade difference
and requires every other record's paint, geometry, timing and compositing to
remain stable. A dedicated source-fade/timeline evidence handoff investigation
is warranted; it is not a reason to change the accepted duration defaults.

## Fading whole-caption phases — v211

The source timeline producer now admits otherwise static complete-caption phases
with a simple global entrance/exit fade. `CaptionPhaseSource` borrows the original
event and owns a separate static paint view, the original fade durations and the
actual non-fading interval. The complete paint phase must supply a finite positive
readable hold; isolated fade fragments may borrow that evidence from other parts
of the same phase. Entirely fading phases remain unproved. Working events and
original pose/opacity evidence are not rewritten. The existing simple
fade parser is shared with boundary-glyph handling under its general name,
`_parse_simple_source_fade`.

Authored adjacent boundaries remain the sharp handoffs: outgoing formatting
continues through its exit fade until the next phase starts. Genuine gaps split
the source timeline. Overlapping phases may join only when their readable cores
leave a safe gap. They reuse the existing centisecond handoff clock, now shared
with lyric overlap handling. No protected readable interval is cut. Source layer
and source order choose the actual foreground core of coextensive planes.
Nested/returning layers, overlapping readable cores, uncertain compositing and
unrepresentable cutoffs do not acquire handoff authority.

Matched glow planes use the same source views. Their global fade factors must
agree on every linear segment, independently of their intrinsic transparency
(for example, opaque foreground over a translucent contour). Different event
splitting may express the same opacity envelope. Different fades, independent
contour opacity, stroke changes, missing readable support and incomplete families
retain the existing route. Uniform-glyph exact-font clearance is shared between
phase families and glow ownership rather than duplicated. Complex `\fade`,
opacity transforms, motion and karaoke remain outside this new source-view proof;
their existing reconstruction policies are unchanged.

Limits are applied once to the resulting static phase intervals. A readable core
proves that the paint really appeared; it does not shorten the emitted hold or
change source pose dwell. The existing one-second minimum, two-seconds-per-change
budget, zero semantics, representative-palette voting and caption-based reporting
remain unchanged. Accepted phases and glows become ordinary disjoint captions.
For an overlap, the immutable producer-owned handoff authorizes the consumer to
replace the retained interval union; the consumer still requires complete source
lineage, one plane, unchanged glyph geometry and no coverage gaps. It discovers
no new temporal intent downstream.

The previously noted **2:30.79–2:34.38** Kill la Kill cue now settles in the first
conversion. With defaults, both “We must be one in spirit” and “omoi wa kitto
hitotsu” retain one representative appearance and matching glow. With both limits
disabled, each row retains its five source colors, with sharp shared boundaries
at **2:31.54, 2:32.17, 2:32.75 and 2:33.17**, ending at **2:34.38**. The foreground
uses the existing two-unit reconstruction cap, as it previously did on repeat.

### Validation commands

The focused cases remain in `tests/check_caption_color_phases.py`. They cover
adjacent and overlapping fades, split foreground/glow frames, spatial gradients,
limits and disabled limits, unchanged source records, genuine gaps, ambiguous
cores, returning layers, mismatched fades and intervening content. Native checks
compare sharp overlap handoffs with independently static expected captions.

The shared corpus runner now accepts explicit hash-bound baseline arguments:

```sh
python validation/run_caption_glow_phase_corpus.py \
  --baseline-engine validation/faded-color-phase-investigation/simplify_ass_v210.py \
  --baseline-summary validation/faded-color-phase-investigation/v210-corpus-summary.json \
  --baseline-sha256 f1d4fc711a89ecab8cb74984f211da05625b35e0a84058060354796dcd06da88 \
  --output-dir validation/caption-fade-phase-corpus
ASS_REGRESSION_FONT_BACKEND=windows \
PYTHONPATH="$PWD/validation/backend_startup:$PWD" \
python validation/check_faded_caption_phase_scene.py
```

The original v210 runner defaults remain available. Baseline subtitles, sources
and fonts are checked for immutability; comparison output cannot overwrite the
baseline or source. Real-scene references remove only the authored fades, apply
the established foreground cap, and are independently converted with v210.
Both default and unlimited full-file repeat behavior are checked without
excluding the previously unresolved fade family. Assets and reports stay private.

### Fresh v211 results and evaluation

All **90** regression scripts pass with unchanged runtime/harness inputs. The
**394** focused checks include actual shared opacity-envelope counterexamples,
isolated entrance/exit frames, same-layer source order and nested returning layers.
The **63** reporting
checks and MKV extraction/conversion/remux/font-sync smoke test pass.

All thirteen corpus conversions use exact fonts with unchanged sources and
baseline outputs. **Twelve outputs are byte-identical to v210.** Kill la Kill
changes only the two target rows and their two glow styles at **2:30.79–2:34.38**:
**464 → 448** dialogue events, with peak concurrency still four. The report now
counts **136 removed changes across 16 captions**, including the newly proved
eight changes across the two fading rows. Existing warning fields and settings
remain compatible with production and both test wrappers.

The real-scene runner checks **28 native samples** around all original handoffs
and both cue edges, against independently held/static v210 references. With
defaults, each complete row and glow holds one appearance; with limits disabled,
all five source colors retain exact adjacent clocks. Full-file repeated conversion
preserves paint, timing, geometry and compositing under both configurations;
there is no longer an excluded source-fade family. Source records outside this
cue remain identical.

After-release evaluation: the earlier fade-evidence handoff gap is resolved at
the producer. Fade parsing, readable-core handoff timing and uniform caption-plane
clearance are shared; no show-specific conditions, late repairs, matcher
exceptions or serialized authority tags were introduced. Complex fades and
unproved opacity/layout animation remain intentionally outside this bounded
proof. No additional dedicated follow-up review is indicated by this change.
