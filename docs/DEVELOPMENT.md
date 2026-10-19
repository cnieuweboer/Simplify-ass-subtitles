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

The first implementation module is documented in
[FONT_MEASUREMENT_EXTRACTION.md](FONT_MEASUREMENT_EXTRACTION.md), following the
[bounded assessment](FONT_MEASUREMENT_EXTRACTION_ASSESSMENT.md). The measurement
owner moved into `_simplify_ass/`; production script locations and reconstruction
policy are unchanged. Distribution must include that private package.
[v214 module delivery](MODULE_DELIVERY.md) discovers its sources and tracks
installed ownership; future extractions do not need delivery filename lists.
[v215 font-outline extraction](FONT_OUTLINE_EXTRACTION.md) moves contour matching
and cubic fitting behind that delivery contract, retaining engine aliases.
The [v216 override interpreter extraction](OVERRIDE_PARSER_EXTRACTION.md) follows
its [bounded assessment](OVERRIDE_PARSER_EXTRACTION_ASSESSMENT.md), preserving
continuation, event-cache and sampling ownership.
The [v217 glyph-placement extraction](GLYPH_PLACEMENT_EXTRACTION.md) follows its
[bounded assessment](GLYPH_PLACEMENT_EXTRACTION_ASSESSMENT.md), moving three
stateless fitting functions; event-based recovery remains in the engine.
The [v218 transform-sampling extraction](TRANSFORM_SAMPLING_EXTRACTION.md) follows
its [bounded assessment](TRANSFORM_SAMPLING_EXTRACTION_ASSESSMENT.md), retaining
call-local sampling state and caller-owned selection/evidence.
The [v219 core event-record extraction](EVENT_MODEL_EXTRACTION.md) follows its
[bounded assessment](EVENT_MODEL_EXTRACTION_ASSESSMENT.md), preserving canonical
factory/default identity and caller-owned cache/evidence policy.
The [v220 static-state selection extraction](STATIC_SELECTION_EXTRACTION.md)
follows its [bounded assessment](STATIC_SELECTION_EXTRACTION_ASSESSMENT.md), moving
geometry selection, representative paint voting and their existing evidence
records while retaining caller-owned inputs, caches and serialization.
The [v221 subtitle document extraction](SUBTITLE_DOCUMENT_EXTRACTION.md) follows
its [bounded assessment](SUBTITLE_DOCUMENT_EXTRACTION_ASSESSMENT.md), moving
decoding, document parsing/resolution and rendering while retaining engine-owned
stage transitions and proof-lifetime decisions.
The [v222 caption rendering extraction](CAPTION_RENDERING_EXTRACTION.md) follows
its [bounded assessment](CAPTION_RENDERING_EXTRACTION_ASSESSMENT.md), moving
source-paint resolution and reconstructed caption rendering while retaining
caller-owned family proofs and the current paint policy.
The [v223 text freezing extraction](TEXT_FREEZING_EXTRACTION.md) follows its
[bounded assessment](TEXT_FREEZING_EXTRACTION_ASSESSMENT.md), retaining selector
evidence, parser continuation and caller-owned event processing/reporting.
The [v224 caption geometry extraction](CAPTION_GEOMETRY_EXTRACTION.md) follows
its [bounded assessment](CAPTION_GEOMETRY_EXTRACTION_ASSESSMENT.md), retaining
caller-owned proofs, pass caches and font measurements.

The [v225 event operations extraction](EVENT_OPERATIONS_EXTRACTION.md) follows
its [bounded assessment](EVENT_OPERATIONS_EXTRACTION_ASSESSMENT.md), moving resolved
evaluation, event replacement and their shared pose-validity key while preserving
cache/history and source-evidence contracts without adapters.

The [v226 representative frame-pose extraction](FRAME_POSE_EXTRACTION.md) follows
its [bounded assessment](FRAME_POSE_EXTRACTION_ASSESSMENT.md), moving source
exposure, duplicate-safe pose selection and compatible evidence handoff while
keeping route-specific paint selection and admission with callers.

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

The suite inventory lists 102 current scripts. The runner uses three workers for
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

Run `simplify_subtitles.py` beside MKV inputs for the production batch workflow.
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

Follow [DEVELOPMENT_PRINCIPLES.md](DEVELOPMENT_PRINCIPLES.md) for the user's
standing preferences on semantic generalization, upstream handoffs, evidence,
pass responsibilities and behavior-focused tests. It also records the structural
follow-up identified when reviewing v183–v185.

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

See [LATE_STATIC_PHASES.md](LATE_STATIC_PHASES.md) for exact final phase joins
(v185), their lifetime-specific compositing proof and Overlord validation.

See [STATIC_PHASE_MERGING.md](STATIC_PHASE_MERGING.md) for the consolidated
static-phase merger and explicit reconstruction/support handoffs (v186).

See [REDUNDANT_TEXT_COPIES.md](REDUNDANT_TEXT_COPIES.md) for strict redundant-record
matching shared between early and final stages, separate representative sign
paint selection, and the reconstruction handoff (v187).

See [CAPTION_BACKGROUND_OWNERSHIP.md](CAPTION_BACKGROUND_OWNERSHIP.md) for shared
measured containment, explicit enclosing-panel ownership and its final-layer
handoff (v188).

See [FINAL_STATIC_TAG_COMPACTION.md](FINAL_STATIC_TAG_COMPACTION.md) for final
serialization after all proofs, its exact per-span guard and corpus rendering
comparisons (v189).

See [GLOW_PULSE_PAINT.md](GLOW_PULSE_PAINT.md) for source-proved returning
highlights, persistent glow contours and fragment ownership in the stack pass (v190).

See [SETTLED_GLOW_PAINT.md](SETTLED_GLOW_PAINT.md) for the resting fill and
opacity-aware contour correction to returning highlight stacks (v191).

See [GLOW_BOUNDARIES.md](GLOW_BOUNDARIES.md) for settled paint through separate
source fade phases and preserved cue-core handoffs to overlap trimming (v192).

See [GLOW_BACKING_OWNERSHIP.md](GLOW_BACKING_OWNERSHIP.md) for retained backing
paint ownership through row reconstruction and foreground overlap handoffs (v193).

See [GLOW_PULSE_TIMING.md](GLOW_PULSE_TIMING.md) for bounded overhang admission
within complete returning-highlight ownership, including the chant cues (v194).

The bounded source fade allowance for rotating entrances is documented in
[ROTATING_ENTRANCE_FADES.md](ROTATING_ENTRANCE_FADES.md). Its focused check runs
in the current suite; `python validation/run_rotating_entrance_corpus.py` compares
fresh outputs with the local, verified v194 corpus baselines.

See [KARAOKE_COMPLETION_BOUNDS.md](KARAOKE_COMPLETION_BOUNDS.md) for the aligned
11 ms initial source-phase selection and completion coverage proof (v196).
`python validation/run_karaoke_completion_bound_corpus.py` compares fresh outputs
with the verified local v195 corpus baselines.

See [PROVED_BACKING_PAINT.md](PROVED_BACKING_PAINT.md) for the explicit settled
paint handoff shared by proved backing rows and returning glow stacks (v197).
`python validation/run_proved_backing_paint_corpus.py` compares fresh conversions
with the verified local v196 baselines.

See [CONTRAST_RECONSTRUCTION_FALLBACK.md](CONTRAST_RECONSTRUCTION_FALLBACK.md) for
producer-owned source contours, borderless captions and uncertain-paint contrast
repair (v198). `python validation/run_contrast_fallback_corpus.py` compares fresh
outputs against the local verified v197 baselines, including fill/geometry timelines.

See [CURRENT_POLICY_INTEGRATION_COVERAGE.md](CURRENT_POLICY_INTEGRATION_COVERAGE.md)
for the v199 test release: current rendering in the former legacy-paint checks,
explicit source-contour handoffs, and native phase/backdrop validation.
`python validation/run_current_policy_corpus.py` requires exact output/statistics
parity with saved, hash-verified current-engine results for test-only changes.

See [REPRESENTATIVE_FRAME_POSES.md](REPRESENTATIVE_FRAME_POSES.md) for the v200
source-frame exposure policy, immutable pose evidence, independent paint selection
and bounded-jitter admission. `python validation/run_frame_pose_corpus.py` compares
fresh conversions with verified local v198 outputs, preserving all non-pose
visibility and tracing changed placements to supplied candidates.

See [INLINE_PAINT_OWNERSHIP.md](INLINE_PAINT_OWNERSHIP.md) for v201's corresponding
source spans, retained transparency and invisible spacing, and separate paint/
geometry handoff. `python validation/run_inline_paint_corpus.py` compares fresh
outputs against verified local v200 baselines and traces retained composites.

See [THICK_OUTLINE_POLICY.md](THICK_OUTLINE_POLICY.md) for v202's retained
reconstruction-only outline cap and corrected original inline extent handoff.
`python validation/run_outline_policy_review.py --compare-authored` compares
fresh capped and isolated authored-width conversions against verified v201
baselines; `python validation/render_outline_policy_review.py` renders the
resulting real/synthetic examples. The experimental engine remains local.

See [MATCHED_BACKING_FADES.md](MATCHED_BACKING_FADES.md) for v203's producer-owned
paint handoff through shared foreground/backing fades. The optional scrolling
cap and motion policy are unchanged. Its corpus runner regenerates v202 with the
current fonts before comparing; the native probe verifies the MKV's actual
Uniform Bold face and checks actual viewport pixels separately from paint crops.

Source-aware letter-to-syllable replacements (v205), exact-font ownership,
annotation admission and native shorthand alpha handling are documented in
[SYLLABLE_LIFECYCLES.md](SYLLABLE_LIFECYCLES.md).

See [ORDERED_STACK_CONTOURS.md](ORDERED_STACK_CONTOURS.md) for v206's shared
uniform/inline proof of the immediate supporting stroke and synchronized source
opacity handoff. `python validation/run_ordered_contour_corpus.py` regenerates
all eleven exact-font sources against the hash-bound v205 baseline.

See [SOURCE_CAPTION_ALTERNATION.md](SOURCE_CAPTION_ALTERNATION.md) for complete
source phases across different fragmentations and the shared lyric-boundary
handoff through frame and text-effect merging (v207).

The proposed follow-up release plan is in
[PAINT_PHASE_RELEASE_PLAN.md](PAINT_PHASE_RELEASE_PLAN.md): v208 restores source
paint ownership/handoffs; v209 adds configurable whole-caption color phases and
explicit reporting when duration-based limits remove changes.

See [REPRESENTATIVE_SOURCE_PAINT.md](REPRESENTATIVE_SOURCE_PAINT.md) for v208's
shared source-row/stack contour proof, coherent representative palettes and
containing backing-interval handoff. Source paint/timing records remain borrowed
original evidence; confirmed row assembly retains normalized fragment paint.

See [CAPTION_COLOR_PHASES.md](CAPTION_COLOR_PHASES.md) for v209's source timelines,
bounded sequential emission, engine/batch controls and shared wrapper reporting.
