# Source letter/syllable replacement lifecycles — v205

The existing pre-freeze glyph lifecycle producer now recognizes a stationary
caption whose individual letters are temporarily replaced by a whole highlighted
syllable. Source timing, exact-font advances and paint planes establish ownership;
no subtitle names, font families, effect annotation strings or target colors
select production behavior. Ordinary frame lifecycles retain their existing proof.

## Source evidence and responsibility

The shared endpoint index normalizes original single-letter anchors with exact
font metrics. It retains both one-sided fade endpoints, including exits which
cannot touch an entrance because a syllable occupies that interval. Original
styles, events, formatting, continuation and cached evidence remain borrowed.

ASS `Banner`, `Scroll up` and `Scroll down` remain ineligible. Other Effect-field
annotations do not themselves move text and no longer obstruct stationary
lifecycle evidence. They are cleared only on an authorized reconstructed caption.

A replacement syllable must be readable, centered, positioned and upright, with uniform
literal formatting. It shrinks monotonically and ends in a supported fade to
transparency. Target-free transforms are inert, not timing/paint evidence.
Movement, masks, perspective, rotation, size reversals, independent text, unknown
transforms and unsupported shaping remain protected. Pulse size is not limited
to one example's percentage; exact-font destination geometry proves the match.

Interior letters require corresponding entrance and exit anchors, compatible
layout, timing and numeric layer order. Matched stacks establish a cue's bounds
and observed before/after paint relation. An immediately highlighted initial
syllable can lack its entrance. A terminal syllable can lack a post-highlight
hold only when its fade begins at the proved cue end. Missing terminal paint
requires one unambiguous observed paint relation; independent spatial variation
with complete endpoints remains per-character paint, not a pooled palette.
There is no fabricated source event or inferred character identity.

Each replacement's required source IDs include its whole syllable and the cue
evidence borrowed for boundary completion. They authorize nothing until the
existing complete-row reconstruction owns them all. Missing or competing phases,
extra nearby text and overlapping claims retain the original family atomically.
The source glyph contour proof remains `_source_caption_paint()`; reconstruction
retains authored thin contours and the existing two-unit cap.

## Geometry, compositing and timing handoff

Original anchor precision survives intermediate paint rendering. The existing
font-row fit has an explicit `fit_scale` option: replacement rows retain its
calibrated horizontal advance scale within the existing five-percent admission.
The final whole-caption glyph-position check uses that selected scale. Existing
callers keep their previous behavior. Geometry is never inferred from paint.

Independent content between the retained foreground and replacement planes must
have a disjoint measured footprint during the common readable core. This includes
other styles and implicit-position captions. Fixed-font scale/stroke transforms
use a conservative component envelope, allowing provably distant animated
content while protecting peers that can grow into the row. Unknown geometry
and uncertain/wrapping footprints reject.
Measurement of an already-proved row uses common geometry plus the union of its
contour footprints, so genuine inline paint variation does not erase the proof.

A pulse's trailing fade can extend beyond the ordinary letter hold. Its actual
exposure is retained; no gap is bridged by enlarging the source timing tolerance.
Endpoint matching keeps the existing 11 ms allowance. The existing fade-core and
handoff consumers trim neighboring cue tails after reconstruction. No new late
filter, timing exception, counter or serialized ownership marker is introduced.

## Shared parser correction

Libass accepts hexadecimal override values with an optional `H` after `&`:
`\alpha&ff&` has the same transparency as `\alpha&HFF&`. `apply_override()` now
handles both spellings for the existing color/alpha channels, including transform
targets. Unrecognized trailing garbage remains ignored. Native comparisons test
both canonical and shorthand source fades on black, gray and white backgrounds.

## Validation and local assets

- `tests/check_syllable_lifecycles.py`: complete and boundary replacements,
  annotation handling, pulse variation, literal/geometry/paint/timing ownership,
  gradients, missing/competing phases, intervening content, source immutability,
  reordered input, and full synthetic/real repeat conversion.
- `tests/check_syllable_lifecycles_render.py`: independently authored static
  output, native shorthand alpha comparisons and unchanged static holds while
  the real source swaps letters/syllables. The exact embedded Century Gothic
  face is checked; generated panels are diagnostic, not new production output.
- `validation/run_syllable_lifecycle_corpus.py`: fresh v204/current conversions
  of the ten existing corpus sources and the new supplied episode, with identical
  fonts, runtime/source/output hashes and checks for unrelated event preservation.

Restore the supplied source as `test-data/Solo-Leveling-S01E02-source.ass` and its
font bundle as `test-data/Solo-Leveling-S01E02-fonts/`. These local assets and
all generated reports/renders remain ignored by Git. The v204 snapshot used by
the corpus runner is also an ignored validation asset; its hash is pinned there.

## After-release evaluation

The change extends the existing source producer before effect freezing. Shared
syllable claims and boundary paint donors are checked by the existing complete-row
ownership gate; original evidence is not reconstructed in a late cleanup. The
small shared-parser correction and fitted-scale handoff address information
loss at their responsible stages. No show-specific runtime rule, downstream
exception or additional simplification pass was needed.

The supplied romanized ending becomes 16 complete static captions instead of
754 retained events; the whole track becomes 404 instead of 1,142. Other styles
are identical. A hash-bound same-font comparison leaves all event fields and
statistics identical for the ten established corpus cases. Source assets remain
unchanged, and the supplied episode is stable on repeat conversion.

No mandatory structural follow-up was identified for this release. Independent
motion, unsupported shaping/geometry, incomplete families and ambiguous boundary
paint remain deliberate refusal cases. Global API and pass-local index reviews
remain separate work; these results do not establish behavior for every future
subtitle family.

Final validation: all 85 regression scripts pass, including 160 focused
behavioral and 115 native rendering assertions for this feature. The final
runtime/harness hashes are unchanged throughout the suite. All 11 same-font
corpus comparisons pass; the final current outputs were regenerated against
hash-verified v204 baselines with unchanged source/font manifests. The MKV
extraction, conversion, remux/extraction and font-sync smoke check also passes.
