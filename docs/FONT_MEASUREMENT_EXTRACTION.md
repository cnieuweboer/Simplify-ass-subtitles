# Font measurement extraction — v213

The engine's exact-font measurement owner now lives in
`_simplify_ass/font_metrics.py`. The four moved definitions are `FontFace`,
`FontCapabilities`, `FontLineInkMetrics` and `FontMetrics`. Existing imports such
as `simplify_ass.FontMetrics` remain direct aliases of those definitions.

This follows the [bounded assessment](FONT_MEASUREMENT_EXTRACTION_ASSESSMENT.md).
Production scripts remain at the repository root. There is no new shared-tool
library, processing context, pipeline abstraction or result-type hierarchy.

## Boundary and behavior

The implementation depends on the standard library and its existing optional
font backends. It does not import the engine. The package initializer is empty.
Optional imports remain inside the existing methods; importing the engine or the
private module does not eagerly require Pillow, fontTools or HarfBuzz.

All four class definitions are unchanged except the font-root expression. Its
extra parent traversal preserves discovery of `fonts/` beside `simplify_ass.py`,
including an installed or relocated engine. Explicit-directory priority, system
font discovery, face selection, shaping, instance bytes, measurement algorithms
and owner-local caches are unchanged. The remaining engine executable AST is
identical to v212 after accounting for the extraction import and version.

Row reconstruction, `FontOutlineMatcher`, `FontProcessingReport`, logging setup,
font extraction from MKVs, and pipeline ownership remain in the engine. No
consumer of the private measurement caches needed a production adaptation.
The test-only `row_test_call()` now resolves reconstruction functions through
the engine instead of inferring their location from the measurement class's
defining module. Its historical method-based route and existing doubles remain.
The live outline-matcher AST audit reads the actual moved definition and
normalizes only the font-root wiring; its numerical comparison remains intact.

## Installation and update migration

The Windows installer now stages and installs the two package files, creates the
package directory, and rolls back first-package upgrades as well as replacements
of existing modules. Backup identities include a staging index to avoid filename
collisions. Uninstall removes managed source/cache files and empty directories,
preserving unrelated package contents and caches.

The updater explicitly selects and requires both package files, using the same
revision, blob verification, syntax checks and installation transaction as the
other tools. A missing or invalid module fails before installed files change.

**Pre-v213 installations need the new installer once.** Their old updater cannot
download paths it does not select. Download/extract the complete repository and
run its installer against the existing target with `--keep-launchers`; choose
Reinstall / update. This preserves launcher selection and respects manually
removed optional launchers. Subsequent updates use the new module-aware updater.
See the [Windows installation guide](../installer/windows/README.md).

No behavior or menu settings in `simplify_subtitles.py` were changed.

## Validation and provenance

`validation/runtime_manifest.py` records deterministic relative source paths and
SHA-256 hashes for the engine and its sibling implementation package. Historical
engines without a sibling package retain a single-file manifest. Entry-point
hashes remain in reports for compatibility; they alone no longer identify the
current implementation.

The regression runner verifies the manifest and harness inputs before/after its
whole run, including native rendering checks. `measure_one.py` verifies it around
each conversion and resolves sibling imports independently of the working
directory. The corpus runner checks child manifests and records the complete
current identity. Historical reports are not rewritten or silently treated as
multi-file evidence.

Both maintained PowerShell test wrappers also retain `SimplifierSHA256` and add
`SimplifierRuntimeManifest`, `CurrentSimplifierRuntimeManifest` and
`RuntimeSourcesUnchanged` to JSON, with matching text-report source hashes.
Their shared helper covers standalone engines and the private package. A module
edit during a run is reported explicitly; raw track statistics and contribution
catalogs remain unchanged. The production batch wrapper remains untouched.

Checks for this release:

- `validation/check_font_measurement_extraction.py`: one-release AST comparison
  against the private, hash-verified v212 snapshot. It permits only the font-root
  adjustment in moved classes and import/version wiring in the engine. It is
  evidence for this extraction, not a permanent freeze on future font algorithms.
- `tests/check_font_module.py`: public aliases, independent private imports,
  missing optional backends, manifest changes and actual installed-tree CLI/
  font measurements from an unrelated working directory without the checkout
  on the import path. It also exercises removal of generated package bytecode.
- Existing font selection, measurement, row, reconstruction and native-render
  checks continue to exercise the actual implementation.
- Installer/updater checks cover missing/corrupt modules, staged rollback,
  first-package upgrades, preserved launcher choices and unrelated user files.

Fresh final results:

- All **91 regression scripts passed**, including installed-tree isolation and
  native libass rendering checks. The complete runtime manifest and covered
  harness inputs were unchanged throughout the successful run.
- All **13 exact-font corpus outputs are byte-identical to v212**, with identical
  complete statistics. Source/baseline/output hashes and all **132 font hashes**
  were reverified; no missing font families were reported.
- **1,459** focused measurement checks, **4,925** row-geometry/reporting checks
  and **1,235** outline-matcher checks passed in the suite. The one-release
  extraction audit confirms the remaining engine executable AST is unchanged.
- Installer checks: **26 passed, two native-Windows checks skipped**. Updater
  checks: **eight passed, one native-Windows check skipped**.
- PowerShell: **71 reporting**, **86 settings** and **11 lookup** checks passed.
  The PowerShell and Python runtime manifests match exactly. Locale-sensitive
  settings checks ran with .NET globalization enabled, including `de-DE`.
- The font/MKV extraction, simplification, remuxing and font-sync smoke check
  passed with source files preserved.

The initial full run exposed the live outline audit's physical-file assumption
and was stopped. That audit was adapted as described above; the complete suite
then passed with the final Python harness. No production algorithm fix was
required. Private evidence is in `validation/font-measurement-extraction-corpus/`,
including `summary.json`, `regression-summary.json`, `parity-verification.json`
and `release-verification.json`. The AST audit is
`validation/font-measurement-extraction-audit.json`; detailed logs use the
`validation/v213-` prefix.

Final whitespace checking removed one extra EOF blank line in the new module.
`final-formatting-verification.json` retains both source manifests and verifies
that the compiled module code is byte-identical before/after that cleanup; raw
suite/corpus fingerprints remain unchanged. The five installed-module checks
and the extraction AST audit passed again against the final source.

Reproduce the corpus comparison against the saved v212 baseline:

```sh
python validation/check_font_measurement_extraction.py
python validation/run_review_checks.py
python tests/check_windows_installer.py
python tests/check_windows_updater.py
python validation/run_caption_glow_phase_corpus.py \
  --baseline-engine validation/font-extraction-assessment/simplify_ass_v212.py \
  --baseline-summary validation/font-extraction-assessment/corpus/summary.json \
  --baseline-sha256 40cb8760e69be3f8917e8817fc2c4aef8ccc7f73d5646858b33b806720541e0f \
  --output-dir validation/font-measurement-extraction-corpus
```

Fonts, subtitle sources, baseline snapshots and generated reports remain private
ignored assets. Native Windows CMD, NTFS and self-update checks require a Windows
host; BASIC/HarfBuzz plus native libass rendering on Linux does not replace them.

## After-release evaluation

The existing measurement ownership fits this boundary without reverse imports,
production compatibility wrappers, copied global environments or algorithm
changes. The discovered test dispatch, resource-root, distribution and provenance
requirements are addressed at their responsible boundaries. The one-time
installer migration is explicit rather than hidden in engine import handling.

No new workaround, duplicated reconstruction proof or unclear production owner
requires a dedicated follow-up review. The native Windows checks remain an
explicit platform-validation limitation, not a claimed pass.

Select the next subsystem only after reviewing this result. No broader API,
pass-local index or processing-context redesign is justified by this extraction.
