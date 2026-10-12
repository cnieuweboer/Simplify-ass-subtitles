# Authored wrapping and fade handoffs — v171

The bottom ending captions “But deep down, I always knew” and “Those awful days
that I lived through—” originally overlap from 22:31.91 to 22:31.95. Their
150 ms entrance and 200 ms exit fades soften that interval. Simplification
removes the fades, making the overlapping captions fully visible.

The original foregrounds specify `\q2`, while `render_simplified_caption()`
previously omitted q. `_faded_cue_slot()` includes wrapping in its source-layout
identity, so `_prove_faded_source_core()` correctly rejected the mismatched
captions despite finding their original fade evidence. The later overlap call
is conditional on new translated/fragment phase rows; this episode produces
none. It is not a universal second scan of every caption.

## Change and contracts

Add q to the existing caption renderer's selected formatting tags. Preserve
every resolved explicit mode; an absent q does not become an explicit override
from document measurement context. Canonical override evaluation still governs
order and resets. Caption replacement reparses the serialized q through the
existing replacement contract. Inputs and document context remain borrowed.

No new function, overlap detector, parser rule, measurement boundary or matching
exception is introduced. The existing fade check now identifies both cues and
chooses 22:31.93, inside the original collision and between fully visible cores.
It preserves exposure outside the collision. The corresponding top pair is
also repaired through the same source-evidence logic. Genuine wrapping
mismatches still prevent trimming.

## Verification

- 53 current regression scripts pass.
- 43 focused assertions cover all four explicit modes, absent overrides,
  script wrapping independence, canonical override/reset behavior, input
  ownership, the actual source failcase and refusal of a genuine mismatch.
- Four independent libass comparisons verify pixels for manually authored and
  rebuilt captions, with a narrow viewport that exposes wrapping differences.
  Together with existing checks, 138 libass pixel comparisons pass.
- Eight full conversions use the complete existing font catalog. Demon Slayer,
  Overlord, Shangri-La Frontier and Witch Hat Atelier are byte-identical to v170.
  Sword S01E01, S01E03, S01E01 track 6 and S01E02 track 5 restore wrapping in
  48, 38, 48 and 38 captions and repair 1, 6, 1 and 6 handoffs respectively.
- Full comparison checks each paired boundary against the old collision and
  original foreground fades. Text, paint, all other formatting, positions,
  event counts and peak concurrency remain unchanged. Only the existing
  `cue_overlaps_trimmed` statistic increases.
- The production executable-definition audit permits only
  `render_simplified_caption()` to change. Historical extraction AST audits
  remain anchored to their immutable stages. The authored ownership comparator
  adds q only to its historical renderer's tag list; all ownership/scaffold
  algorithms remain historical. Frozen v170 separately reproduces the bug.

Use `python validation/run_review_checks.py` for the packaged focused suite.
`validation/check_full_caption_wrapping.py` checks the external full originals
and saved v170/current outputs. See `validation/full-conversion-comparison.json`,
`validation/caption-wrapping-checks.json` and the production patch.
