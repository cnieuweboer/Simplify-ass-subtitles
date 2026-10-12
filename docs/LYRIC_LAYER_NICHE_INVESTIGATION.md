# Matching lyric layer investigation

Original investigation of runtime **2026.10.12.181**; the follow-up fix is in
**2026.10.12.182**, described below.
The user's full MKV collection reported zero contributions from this pass.
These synthetic cases establish capability and weaknesses, not prevalence in
real releases.

## Reproduce

From the repository root, with the local font assets restored:

```sh
source /workspace/.setup/simplify-ass/activate.sh
python validation/run_backend_check.py --backend windows validation/investigate_lyric_layer_niche.py
```

The experiment generator requires exact Volkhov regular and
FOT-MatisseMinori Pro-En B bold/nonitalic. The latter was supplied by the user
and resolves correctly. Missing exact fonts abort the experiment.
Generated ASS files, JSON results and comparison PNGs are kept locally under
`validation/lyric-layer-niche/`. They are ignored by Git.

The diagnostic harness records oracle violations rather than asserting that
the current policy is correct. The follow-up regression entry point adds the
agreed assertions to the routine suite. Harness assertions verify pipeline execution,
equal inputs at the target pass, counter attribution, exact-font prerequisites,
input immutability, and libass font selection for active text.

## Fixture construction and independent expectations

Every source is a normal ASS document; the harness never assigns lyric or row
flags. Full captions have paired fill/outline copies at nearby horizontal
anchors, modeling shadow or jitter stacks. Fragments have paired paint copies.
All fragments use exact-font advances, rather than arbitrary letter spacing.
The normal simplifier performs its source preparation and all later passes.

Each of 22 fixtures runs through the complete default pipeline with the target
filter enabled and disabled. Only its returned events/removal count are bypassed
in the disabled configuration. Both outputs are then simplified a second time.
Expected authored full-line text, anchor, alignment, font, size, fill and outline
are checked independently of the outputs. Positive cases require preservation
of the complete row's readable exposure, including fragment-only intervals.
Negative cases require retention of differently placed/sized/fonted text or
literal capitalization/spacing. Equal normalized wording is insufficient proof
that those fixtures are disposable copies.

## Results

All **22 experiments completed**, with no missing fonts. These are policy
observations, not 22 correctness passes.

| Case family | Filter contribution | Final on/off difference |
| --- | --- | --- |
| Letters, full-copy offsets 0.1–12 px | Removes 12 fragments in all six cases | Extra reconstructed copy remains without the filter at 0.1 px; other five outputs identical |
| Three words / four syllables | Removes 3 / 4 fragments | Disabled output has 5 / 6 events; enabled has 2 |
| Ordinary full line / exactly equal intervals | No contribution | Both configurations agree; ordinary line reduces to one event |
| One-centisecond inset | Removes 12 | Later code reaches the identical final output without it |
| Fragment-only entrance, exit, or both | Removes 12 and extends retained line | Disabling it loses 0.1 seconds of readable text at the corresponding ends |
| 79% / 80% / 81% overlap | 0 / 12 / 12 | Below threshold both retain exposure; at/above threshold disabling loses the fragment-only exit |
| Different position, size, font, capitalization, spacing | Removes 12 in all five cases | Enabled output loses required distinct content; disabled output preserves it |

The filter contributes a nonzero counter in 19 cases, but changes the final
output in only **13**. Eight differences exercise useful cleanup or readable
timing preservation; five demonstrate unjustified deletion.

The authored full-caption text, geometry and white fill / `403020` outline
remain intact in all 44 first-pass outputs. The five negative-case oracles fail
with the filter enabled. The five fragment-only-exposure oracles fail with it
disabled. Thus neither configuration is a satisfactory replacement policy.

There are **45 sampled source/on/off render comparisons (135 frames)** using
FFmpeg/libass on Linux, including holds and differing entrance/exit intervals.
Font selection is recorded. Changed outputs were rendered, and the hold images
for the tiny-offset, word, syllable and all five negative cases, plus the exit
comparison, were visually inspected. They confirm the structural findings.
These samples do not prove all-frame equivalence or native Windows behavior.

## Second simplification

**18 of 22 fixtures change on a second simplification in each configuration.**
For example, two surviving nearby full copies become one after reload; the
synthetic lyric flags are no longer present, allowing static-copy reduction to
claim them. This is independent of enabling this specific pass and is a
separate pipeline issue. JSON results retain the second-pass event details.

## Recommended next change

Do not delete this capability outright: the word/syllable cases and timing
tests demonstrate work that later passes do not consistently reproduce.
Do not keep its existing admission policy unchanged either: it ignores font,
font size and exact glyph positions, and normalizes away meaningful case and
spacing when deciding ownership.

Use these fixtures to replace or constrain its matching with exact-font layout
and literal-text ownership proof. Preserve useful word/syllable removal and
readable exposure while rejecting the five controls. Avoid a broad refactor or
mixing the separate second-pass duplicate issue into that change. After a fix,
promote the agreed expected behavior into focused assertions and run the
normal regression suite and corpus checks.

## Follow-up fix: v182

The pass remains in its original pipeline position and keeps its report counter.
It now borrows the pipeline's `FontMetrics` owner. No exact metrics means no
removal. Candidate rows still need the existing fragmented-effect evidence,
three spatial columns and 80% timing overlap; this change does not broaden
admission to ordinary captions.

Complete-row matching is case-sensitive. Each column must spell the next
literal span of the retained line; omitted spaces between fragments are checked
through their actual font advances. Each fragment's glyph positions must match
the complete line's glyph positions at its held font size, scales, tracking and
alignment. The proof checks every copy in each column, including vertical
anchors, identical layout/placement/measurement context and fill/outline paint.
It rejects incomplete, moving, transformed, faded, clipped, sheared, rotated,
inline-formatted, translucent and invalid/nonfinite candidates. Unsupported
members reject the phase rather than authorizing partial removal.

Nearby equivalent full-copy witnesses are chosen by smallest anchor error then
source index. Matching fragment exposure extends the chosen caption; separate
accepted phases accumulate both ends rather than overwriting an earlier
extension. Borrowed events, formatting/history caches and visibility remain
unchanged. The independent second-pass duplicate issue is not part of this fix.

`tests/check_matching_lyric_layers_render.py` asserts all 22 authored oracles,
the useful removal counts, and retention of the five controls. It also exercises
missing/unavailable fonts, paint differences, incomplete rows, unsupported
effects, invalid geometry, source ownership, order independence, cumulative
timing and idempotence of this pass's own output. It bounds runtime edits against
frozen v181 to this pass and its caller. The older v180/v181 handoff integration
audit remains bounded to those frozen releases; its live behavior tests still
exercise the current engine.

Rerun the focused regression with:

```sh
python validation/run_backend_check.py --backend windows tests/check_matching_lyric_layers_render.py
```

Fresh diagnostic results and PNGs are now placed under a version-specific
`validation/lyric-layer-niche/2026.10.12.182/` directory. This prevents later
runs from replacing earlier release evidence. The corpus comparison command is
`python validation/run_lyric_layer_corpus.py`; it reconverts frozen v181 and the
current engine with identical fonts, verifies source hashes and reports missing
families explicitly rather than treating incomplete conversions as passes.

## v182 verification

- All **65 routine regression scripts** passed on the Windows BASIC/real
  HarfBuzz backend on Linux, including **101 focused lyric-layer checks**.
- All 22 revised-policy synthetic oracles passed; 45 source/on/off render
  comparisons (135 frames) were generated. The corrected different-font hold
  was visually inspected and retains the independently authored text.
- All **nine full corpus sources** produced byte-identical output and identical
  statistics against fresh v181 conversions using the same current fonts.
  There were no missing fonts. Source checksums were verified.
- All **72 PowerShell reporting checks** passed on PowerShell 7.4.6/Linux.
- The environment's MKV font extraction, simplification, remux/extraction and
  font-sync preview smoke test passed; source files were preserved.

Reports are local under `validation/complete-regression-checks.json`,
`validation/matching-lyric-layer-checks.json`, and
`validation/lyric-layer-corpus/windows/summary.json`. Native Windows execution
is not established by these Linux checks. The previously recorded global
second-simplification duplicate issue remains separate and unchanged.
