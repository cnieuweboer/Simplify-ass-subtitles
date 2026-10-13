# Development workflow

The migration imports runtime **2026.10.12.177**, launchers, PowerShell wrappers,
regression checks and technical notes from the supplied work-project snapshot.
The original ZIP is preserved outside the checkout. All 881 included files
matched its SHA-256 manifest. The separate test-data and font uploads restored
the remaining 107 entries; all 988 manifest entries were verified. Imported
reports describe earlier runs and do not establish current
readiness. The migration does not change the converter's policy. Production scripts remain
at the repository root; Python checks/helpers are in `tests/`, Windows test
wrappers in `tests/windows/`, runner tools in `validation/`, and notes in `docs/`.
All commands below run from the repository root.

## Tools

Use Python 3.10 or newer, MKVToolNix, Pillow, fontTools and uharfbuzz. Render checks
also need FFmpeg with the libass filter. The optional lifecycle frame diagnostic
uses NumPy and the system libass shared library. In this prepared cloud environment:

```sh
source /workspace/.setup/simplify-ass/activate.sh
cd /workspace/Simplify-ass-subtitles
python -m pip check
python /workspace/.setup/simplify-ass/validate.py
```

The activation selects the workspace virtual environment and local MKVToolNix.
The smoke check uses temporary synthetic subtitles and an embedded font to test
extraction, simplification, remuxing, font parsing/shaping and font-sync preview.
It complements the project regressions rather than replacing them.

Elsewhere, install MKVToolNix and FFmpeg through the operating system's package
manager and install the Python packages in a virtual environment:

```sh
python -m venv .venv
# Activate .venv using the command appropriate for your shell.
python -m pip install Pillow fonttools uharfbuzz
```

## Regression assets and commands

The supplied `test-data` and `fonts` folders are restored at the repository root
in this cloud environment. Restore them from the supplied ZIPs in a fresh clone.
Tests use both subtitle fixtures and historical `simplify_ass-vNNN-reference.py`
engines. Exact font files are needed for geometry and outline proofs. The
snapshot's manifest permits byte-for-byte verification of these assets. These
folders are kept locally; generated `outputs` and validation reports are also
ignored by Git. Existing media and font files must not be overwritten blindly.

The routine suite deliberately selects the Windows font backend, using Pillow
BASIC and real HarfBuzz even on Linux:

```sh
python validation/run_backend_check.py --backend windows tests/check_glyph_lifecycles.py
python validation/run_review_checks.py
```

The two JSON audit inputs retained under `validation` are test data, rather than
generated pass reports: `masked-extraction-blocks.json` and
`covered-fragment-helper-list.json`.

The suite inventory lists 67 current scripts. The runner uses three workers for
ordinary checks and serializes render checks. It records runtime/harness hashes
and writes fresh logs and summaries under `validation/backend-runs/windows`.
Inspect script exit codes and `validation/complete-regression-checks.json`.
Missing inputs, failed checks and skipped checks must be reported distinctly.

RAQM is an occasional explicit check:

```sh
python validation/run_review_checks.py --backend raqm
```

The following corpus runner preserves the historical v177 migration assertions;
later color and timing changes can legitimately fail its unchanged-output checks.
For that historical comparison, first produce the isolated opening output,
then regenerate both historical v176 and current outputs for all nine sources:

```sh
mkdir -p outputs
ASS_REGRESSION_FONT_BACKEND=windows \
PYTHONPATH="$PWD/validation/backend_startup${PYTHONPATH:+:$PYTHONPATH}" \
python simplify_ass.py test-data/Attack-on-Titan-S02E01-opening-source.ass \
  --fonts-dir fonts --suffix .migration --stats-json outputs/opening-probe.json
cp test-data/Attack-on-Titan-S02E01-opening-source.migration.ass outputs/opening-probe.ass
python validation/run_corpus_checks.py
```

The comparison runner validates source checksums, writes both sets of new
conversions under `validation/migration-corpus/windows`, and checks identical
output/statistics for the other eight sources. For Attack on Titan it requires
21 romanized opening lines matching the isolated conversion, unchanged events
outside that family, and the expected 3,491 → 354 total events.
Its report records runtime, reference-engine, source and output hashes.

An additional exact-font lifecycle render diagnostic uses NumPy and libass:

```sh
python -m pip install numpy
python validation/probe_lifecycle_render.py
```

This checks 12 render samples and a pixel-identical static hold using the freshly
generated isolated opening output. Preserve existing output files before reruns.

Some corpus comparison, profiling and release-packaging helpers preserve the old
work project's sibling release directories and baseline output paths. They are
historical tools and require their documented inputs; do not treat a saved report
or `verify_release.py` alone as a fresh full-corpus run. Full corpus validation
must regenerate outputs from the actual restored sources and compare against a
known engine/baseline. Keep original archive evidence outside fresh report paths.

## Batch testing on Windows

Run `simplify_ass.bat` beside MKV inputs for the production batch workflow.
`tests/windows/test_mkv_subtitles.ps1` scans MKVs recursively, extracts ASS/SSA and fonts,
converts them and writes per-MKV ZIPs and reports without remuxing the originals.
Use explicit input/output paths and a suitable `-MaxParallel` value.

`tests/windows/test_subtitles_step2_test.bat` / `.ps1` operate on the previously extracted cache
without repeating MKV extraction. The first-pass extractor is now available as
`tests/windows/test_subtitles_step1_extract.bat` / `.ps1`. Configure both stages
to use the same cache folder; their launchers currently have different default
cache paths. You can also pass an explicit extraction `-OutputFolder` and
step-two `-InputFolder`.
These PowerShell/batch paths need native Windows execution to validate process,
filesystem and wrapper behavior.

## Next development work

Prioritize reproducing failure cases with exact fonts and source events. Extend
the relevant focused check before adjusting reconstruction. Check complete text,
representative fill/outline, timing boundaries, source ownership and unchanged
unrelated events. `GLYPH_LIFECYCLES.md`, `WORD_ECHOES.md`, `OUTLINE_KARAOKE.md` and
the ownership/context notes explain the existing admission and fallback policy.

Keep the two larger reviews separate from those fixes:

- Global API review: catalog replacement precedence, ownership, explicit inputs
  and result application at pipeline boundaries.
- Pass-local indexes review: cache lifetimes, invalidation and typed payloads,
  including the parallel maps in `BackedPulseContext`.

`CONTEXT_OWNERSHIP_REVIEW.md` records the deferred questions. Earlier structural
work is documented as completed; those notes are context for the new reviews.

Current staggered-fade timing policy and its v179 comparison are documented in
[STAGGERED_FADE_CORES.md](STAGGERED_FADE_CORES.md). The focused check runs the
actual opening through both engines with the same supplied fonts.

See [SYNCHRONIZED_HANDOFFS.md](SYNCHRONIZED_HANDOFFS.md) for shared source-safe
transitions across separate text rows (v181).

## Test-wrapper counter reports

Both Windows wrappers use `tests/windows/subtitle_report_helpers.ps1`; keep that
file beside them when copying the wrappers. Standard-mode summaries list current
filter contributions separately from retained-output and diagnostic counts.
Legacy-only counters and unused compatibility placeholders are excluded. Explicit
legacy mode shows its own active counters. Original per-track `stats.json` files
and conversion behavior remain unchanged.

Active counters retain genuine zeros. Missing counters show `not reported`;
partial totals identify how many successful tracks supplied the statistic.
`report.json` stores nullable `Totals` plus `CounterCoverage`. Unknown counters
remain available in per-track data, rather than being classified as filters.
Update the shared catalog whenever adding a production counter.

The color-normalization counter is sparse in v178 and later: omission means zero
when the converter version confirms that contract. Older or unrecognized versions
show an unavailable statistic instead. No other missing counter is assumed zero.

A zero identifies no recorded contribution, not proof of supersession. A matching
effect may be absent, an earlier pass may have handled it, or font measurements
may be unavailable/disabled. Individual counters can cover multiple functions.

Run the PowerShell reporting checks (including actual summary/report generation)
without converting media:

```powershell
powershell.exe -NoProfile -File tests/windows/check_reporting.ps1
```

PowerShell 7 can also run these checks using `pwsh`. Linux checks do not validate
Windows extraction, job management or filesystem behavior. The existing Python
reporting and statistics-name checks remain independent of the wrapper catalog.

See [LATE_COMPLETE_COPIES.md](LATE_COMPLETE_COPIES.md) for final complete-caption
deduplication after lyric proofs (v184), its strict paint/geometry admission and
focused/corpus validation.
