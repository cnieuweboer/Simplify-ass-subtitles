# Representative source paint and backing handoffs

v208 extends the existing ordered contour proof into early source-row
normalization and source color steps. It still emits one representative
appearance per caption. Configurable temporal phase retention belongs to v209;
see [PAINT_PHASE_RELEASE_PLAN.md](PAINT_PHASE_RELEASE_PLAN.md).

## Producers establish paint before serializing

Confirmed dense source rows previously pooled foreground, sharp contour and
wide glow colors. Competing contours could trigger neutral contrast fallback
before the ordinary stack producer had a chance to establish ownership.
The source-row producer now groups corresponding literal glyphs by resolved
geometry and inspects source paint order. It borrows the same ordered contour
proof used for complete stacked captions. The nearest sharp stroke beneath an
opaque borderless foreground owns its contour; lower broad glows do not vote
against it. Covered borderless fills may be skipped, but blur, shadows, masks,
translucency or unknown source geometry do not become trustworthy through
freezing.

A sharp foreground can own its own complete contour through the existing
`_source_caption_paint` policy. This also handles terminal fragments that have
no separate completed foreground. The existing dense-row completion proof owns
the shared completed fill for fragments lacking that higher foreground plane;
fragments with their own completed foreground retain intentional fill variation.
The two-unit reconstructed-outline cap and authored thinner/axis-specific
widths remain unchanged.

Normalized source-row successors retain the original `paint_rows` and
`foreground` records, including their text, transforms and individual lifetimes.
The original source/timing catalogs remain read-only and are never replaced by
the sampled paint views. Later consumers can still inspect that source evidence.
Row assembly explicitly retains the producer's per-fragment paint, including
static source contour gradients. Static assembly must not inherit only the
first fragment's paint simply because the producer has already removed effects.

## Select one coherent source-time palette

Discrete source color transforms supply absolute palette boundaries. Resolve
all relevant literal spans and planes at the same time. Accumulate duration for
identical complete palettes, so repeated palettes and no-op subdivisions cannot
split their exposure into competing votes. Choose the palette with the greatest
held exposure; ties prefer the earlier palette. This tie rule remains stable
when a no-op tag subdivides an otherwise unchanged hold. Fill and contour therefore come from one actual source-time
palette, rather than independent channel votes.

Source rows choose the time across the confirmed caption before normalizing
individual fragments. Complete stacks use their common source interval. The
separate karaoke completion proof supplies completed text/fill; staggered reveal
starts do not count as independent whole-caption color changes. Continuous color
ramps and unsupported geometry animation remain with their existing consumers.
Color-step admission does not loosen opacity admission: matching coupled opacity
progressions still go through the established source contour proof.

This release deliberately settles the whole-caption steps. It does not emit
multiple color phases or introduce new tuning/report counters.

## A foreground inside a held backing

The stack producer can group a foreground whose interval lies inside one held
backing family, with at most 50 ms at either endpoint. This is a frame-scale
admission bound, not timestamp equality. It additionally requires:

- One unambiguous overlapping interval family with matching literal text and
  resolved geometry, including corresponding inline spans.
- Original ordered opaque foreground/backing paint satisfying the existing
  contour proof. Independent stroked foregrounds, uncertain composites,
  incomplete support, masks and geometry differences do not qualify.
- No potentially overlapping intervening content in paint order. Existing exact
  font bounds can prove unrelated content spatially separate; unknown bounds
  refuse ownership when such intervening content exists.

The producer stores the accepted contour and containing interval together.
Rendering consumes that proof directly and emits one caption over the containing
interval. Its contour color, alpha and width travel together. The effect-sequence
consumer no longer receives a borderless foreground plus a separate held stroke
for these families. No late outline-restoration pass is involved.

## Validation

`tests/check_stacked_contour_paint.py` exercises source-time palette selection,
no-op subdivisions, gradients, contained intervals, refusal cases, original-input
immutability, terminal completion and repeat conversion, alongside the existing
ordered contour cases. Its native companion checks authored plain-caption
references, including lead-in and end boundaries.

Run `validation/run_representative_paint_corpus.py` with the hash-bound private
v207 corpus baseline, then `validation/check_representative_paint_scene.py` for
real opening text/timing/geometry, source-colored contours, spatial gradients,
full-file repeat conversion and exact-Mikadan native samples. These runners
require private restored source/font assets and retain generated files locally.

## After-release evaluation

Ownership is established at the source-row/stack producers. Both reuse the
existing contour and span concepts; assembly and serialization consume their
paint rather than rediscovering it. The terminal-fill behavior remains part of
the existing dense-row completion proof. No show-specific conditions, downstream
repair, global cache or new contrast exception was added.

The planned v209 temporal emitter still needs to consume the retained source
phase evidence and apply configurable limits. That is the existing next release,
not a newly required workaround review. Full-suite/corpus/native results and any
newly discovered concerns are recorded with the release validation.

Fresh v208 validation passed all **89** routine regression scripts with unchanged
runtime/harness inputs, including **260** ordered/source-paint checks and **95**
native contour checks. All eleven exact-font corpus conversions reported no
missing fonts; ten outputs are byte-identical to v207. Demon Slayer changes only
17 opening lyric paint records, preserving all 24 cues' text, timing and geometry
and the overall event count. The ending and other styles remain unchanged.
Native source-paint references pass at ten real sample times, including both
40 ms handoffs; three further panels cover restored source contour gradients.
The complete Demon Slayer output is byte-identical on repeat conversion.
