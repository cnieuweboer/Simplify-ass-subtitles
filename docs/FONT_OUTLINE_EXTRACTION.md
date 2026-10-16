# Font-outline matching extraction — v215

`FontOutlineMatcher` and `fit_cubic_points()` now live together in
`_simplify_ass/font_outlines.py`. `simplify_ass.py` re-exports both as direct
aliases, preserving existing call sites and imports. The engine version is
`2026.10.16.215`.

This is a structural extraction. Both moved definitions are AST-identical to the
pre-extraction runtime. The remaining engine executable AST is unchanged except
for the import and version. `_simplify_ass/font_metrics.py` and the package
initializer are byte-identical; `simplify_subtitles.py` is untouched.

## Responsibility and dependencies

The dependency direction is engine → outline matching → font measurements.
The new module otherwise imports only `math`, `statistics` and postponed
annotations. It can be imported without the engine or optional font backends.
There are no reverse imports, event/context dependencies, new framework classes
or reconstructed global namespaces.

The matcher still borrows the caller's metrics owner and owns its own bounded
alphabet profiles. Exact-face/alphabet keys, profile reuse, negative caching,
search limits, ambiguity rejection, geometric tolerances and exception behavior
are unchanged. The fitter is shared by the decoder and the engine's vector-text
measurement caller through the same function definition.

Row reconstruction, parser state, source-event evidence, caption/paint policy,
reporting and pipeline timing remain in the engine. No cache changes owners.
Font discovery and path-sensitive `__file__` handling stay in the measurement
module, unchanged from v213.

## Tests and delivery

The existing outline matcher check now patches the fitter in the decoder's
actual defining module for both current and historical engines. Its source audit
also reads the actual class definition. It still compares complete decisions,
font calls, profile contents and integration results; no assertions were removed
to accommodate the move. Engine callers that use the fitter alias continue to
resolve it in the engine.

The existing installed-module check now covers both aliases, private imports
without optional backends, and actual contour decoding using a generated exact
font. It installs into a path with spaces, runs from an unrelated working
directory without the checkout on the import path, verifies sibling-font lookup,
performs CLI conversion, and removes all managed package sources/bytecode while
retaining user fonts.

The [v214 delivery contract](MODULE_DELIVERY.md) discovers the new module without
installer/updater changes. A separate compatibility probe used the actual
shipped v214 updater to upgrade a real pre-extraction installation to this engine
through mocked pinned GitHub responses with real blob verification. It verified
failure rollback at `font_outlines.py`, a successful retry, preserved choices and
user files, isolated installed imports, and uninstall. Clients still using a
preparation-skipping fixed-list updater need the complete-repository installer
with `--keep-launchers`, as documented in the
[installation guide](../installer/windows/README.md#upgrading-older-installations).

## Validation and provenance

The private pre-extraction runtime was captured before edits, including its
implementation package and original sibling-font fallback. Thirteen fresh
baseline conversions agree byte-for-byte and in complete statistics with the
previously validated v213 outputs. The current conversions compare against these
fresh baselines, rather than inferring parity from old reports.

A one-release audit, `validation/check_font_outline_extraction.py`, verifies the
hash-bound pre-extraction runtime, unchanged moved definitions, unchanged remaining
engine AST, byte-identical existing modules and the new module's imports. It is
bounded evidence for v215, not a permanent freeze on future outline algorithms.
The v213 measurement extraction audit remains historical evidence for that
release's layout.

Fresh final results:

- All **91 regression scripts passed**, including native libass render checks.
  The complete runtime manifest and covered harness inputs were unchanged
  throughout the run.
- All **13 exact-font corpus outputs are byte-identical** to the freshly
  generated pre-extraction baseline, with identical complete statistics. Source,
  baseline and output hashes and all **132 font hashes** were reverified; no
  missing families were reported.
- **1,235 outline matcher checks** passed, covering 91 bounded-search cases,
  249 vector-integration cases and two focused conversions. The existing
  **1,459 measurement** and **4,925 row-geometry/reporting** checks also passed.
- All **five installed-module checks** passed with the expanded contour probe.
  Installer checks: **32 passed, two native-Windows checks skipped**. Updater
  checks: **10 passed, one native-Windows check skipped**.
- The actual v214-to-v215 update/rollback/uninstall probe and MKV/font smoke
  check passed. PowerShell and Python identify the same four runtime sources
  and hashes without changes to either test wrapper.

Private evidence is under `validation/font-outline-extraction/`: `audit.json`,
`baseline-corpus/summary.json`, `corpus/summary.json`, `regression-summary.json`,
`powershell-manifest.json` and `release-verification.json`. The compatibility
probe and smoke log are retained there too. All evidence refers to the final
runtime; no post-validation source cleanup was needed.

Reproduce the focused checks and full suite:

```sh
python validation/check_font_outline_extraction.py
python validation/run_backend_check.py --backend windows tests/check_outline_matcher.py
python validation/run_backend_check.py --backend windows tests/check_font_module.py
python tests/check_windows_installer.py
python tests/check_windows_updater.py
python validation/run_review_checks.py
python validation/run_caption_glow_phase_corpus.py \
  --baseline-engine validation/font-outline-extraction/baseline-runtime/simplify_ass.py \
  --baseline-summary validation/font-outline-extraction/baseline-corpus/summary.json \
  --baseline-sha256 c04faf4d5d9d8ce497d9b7c54e6e13310ada8b545b400e41fb7f912364171f81 \
  --output-dir validation/font-outline-extraction/corpus
```

Baseline snapshots, fonts, subtitle inputs and generated reports stay private.
The audit's default baseline is restored from the v214 revision `7aaeba4` with
`simplify_ass.py` and its private package retaining their relative paths.
Native Windows CMD/NTFS/self-update checks require Windows; the Linux Windows-font
backend and native libass rendering do not replace that platform validation.

## After-release evaluation

The existing responsibility boundary survives the move without a production
shim, duplicated proof, changed algorithm or downstream exception. Test changes
follow the defining module instead of forcing production globals to imitate the
old layout. Distribution works through the existing inventory and transaction.

No new workaround, unclear ownership or unrelated subsystem interaction currently
warrants a dedicated follow-up review. Broader API and pass-local index reviews
remain separate work. Choose any subsequent extraction from its actual
dependencies; this release does not prescribe a final module hierarchy.
