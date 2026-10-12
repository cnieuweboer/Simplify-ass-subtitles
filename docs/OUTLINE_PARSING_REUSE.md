# Outline parsing reuse — v172

This release optimizes the v169/v170 outline-preservation path without changing
its proof or paint policy. The malformed-color regex optimization is separate
and is not included here. Attack on Titan's reported slow track was not supplied
and was not part of this benchmark.

## Local ownership and lifetime

`_collect_outline_strip_evidence()` parses each strip's source once while
building the coverage proof. `OutlineStripEvidence.tokens_for()` then reuses
those immutable token tuples for the transition and fade checks, lazily adding
only foreground sources needed by that same family. The private entries retain
the borrowed source objects and use their identities. A replacement with the
same source index gets a separate entry. Each family starts with a fresh cache,
and the proof and tokens expire after that family's rendering decision.

Sources, styles, visibility maps and their resolved state remain borrowed and
unchanged. Tokens are not attached to events, formatting or shared maps. An
initial pass-wide cache trial retained roughly 25–34 MB of extra token data and
gave mixed timings; the released design deliberately limits reuse to one family.

If source formatting is already resolved, its existing cache remains authoritative.
Otherwise, `_collect_outline_strip_evidence()` resolves it from the cached token
stream through `evaluate_effective_state()`. Returned formatting still has its
own buffer and continuation. The existing coverage evidence retains initial
strip formatting for subsequent static paint and transition checks. No global
formatting cache or new source-evidence lifetime is introduced.

## Shared parsing and validation

`evaluate_effective_state()` accepts optional complete ordered tokens of the
same text. Ordinary callers continue parsing block by block. Both routes use the
same `apply_override()` implementation and preserve resets, alignment latching,
unknown/empty reset behavior and continuation across blocks/literals. Provided
streams are borrowed and may be iterators; the formatting result is owned.

The coverage proof now records whether its admitted original strips contain
transforms. The stack renderer routes that single proof to the static or animated
consumer; the static consumer accepts the proof directly. This removes the
previous separate transform-presence scans and any repeated coverage setup.

The animation proof reuses source tokens for transition and fade checks.
Each transform's payload is parsed once, used for the existing color-channel
classification, then lent to `parse_effect_transform(parsed_changes=...)`.
The validator still performs all timing, acceleration, allowed-tag and endpoint
checks. The supplied payload must belong to this exact transform; it is not
modified. When provided, the returned changes list is that same pass-owned list,
consumed read-only by the outline transition proof. No transform payload cache
survives the proof or an event replacement.

Original movement, fades, karaoke, unsupported transform channels, incomplete
coverage, layer/layout mismatches, ambiguous sweeps and missing fonts retain the
existing rejection behavior. Reversed endpoints are still normalized only in
the outline transition proof. Destination-paint and source-fade timing policy
remain in their existing shared consumers.

## Verification

All 54 current regression scripts pass, including the existing 138 pixel-identical
libass comparisons. The new check has 219 assertions and a complete executable
AST audit against v171. It verifies parsing exactly once, parser/validator parity,
replacement and pass identity, unresolved source formatting, borrowed state,
static/karaoke pass output and unchanged reduction counts. There are eight changed
production definitions and no added or removed definitions.

## Measured results against v171

The eight available full subtitles have identical output bytes, statistics,
event counts and peak concurrency. Two usable sequential fresh-process samples
per version and file were used, with version order counterbalanced. The first
four pairs overlapped the discarded cache-retention trial and were repeated;
all 40 raw measurements are retained, and those eight timings are explicitly
excluded. Original inputs, font catalog and production code stayed fixed.

| Subtitle | v171 seconds | v172 seconds | Time reduction |
|---|---:|---:|---:|
| Sword-S01E01 | 12.10 | 11.51 | +4.9% |
| Sword-S01E03 | 16.53 | 16.29 | +1.4% |
| Shangri-S01E14 | 7.84 | 8.09 | -3.2% |
| WitchHat-S01E02 | 36.69 | 36.19 | +1.3% |
| DemonSlayer-S04E02 | 13.21 | 12.72 | +3.7% |
| Overlord-S04E02 | 23.18 | 22.24 | +4.1% |
| Sword-S01E01-track6 | 10.88 | 11.39 | -4.7% |
| Sword-S01E02-track5 | 15.69 | 14.10 | +10.2% |
| Sum of means | 136.12 | 132.54 | +2.6% |

Positive reductions indicate faster conversion. The aggregate gain is modest;
Shangri and Sword's signs-only episode 1 track were slower in these two-sample
means. The samples show noticeable timing variation, so they do not establish
small per-file differences as repeatable regressions or promise a collection-wide
speedup. Peak memory on the Sword fixtures is again near v171's level.

The Sword S01E01 profile confirms the intended work reduction:
`event_override_tokens()` calls fell from **48,186 to 19,534**
(**59.5% fewer**); total `tokenize_override()` calls fell from
**262,685 to 194,740** (**25.9% fewer**).
The counts of coverage proofs (217), transition proofs (12,567) and sweep proofs
(177) are unchanged. The optimization therefore reuses parsing rather than
skipping those checks. Profiled runtime is kept separate from unprofiled timings.

Raw samples, hashes, the complete equivalence report, focused checks and profile
summary are in `validation/`. Timings exclude engine import and initial font
catalog setup; each conversion uses a fresh font owner. This host uses Linux
and Pillow RAQM, with the same installed backends for both versions. The user's
Windows full-collection tester was not run here. Full-fixture benchmark scripts
refer to the existing workspace corpus; the packaged regression suite uses its
own included fixtures and fonts.
