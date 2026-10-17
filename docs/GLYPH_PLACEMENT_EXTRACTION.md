# Glyph placement extraction — v217

`fit_fragment_anchor()`, `authored_glyph_positions()` and
`matches_authored_glyph_positions()` now live in
`_simplify_ass/glyph_placement.py`. The engine re-exports all three as direct
aliases. The engine version is `2026.10.17.217`.

This implements the smaller boundary recommended by the
[bounded assessment](GLYPH_PLACEMENT_EXTRACTION_ASSESSMENT.md). The three moved
definitions are AST-identical to v216. The remaining engine executable AST is
unchanged except for the import and version; all existing private modules remain
byte-identical. The batch wrapper and installer/updater are unchanged.

## Responsibility and dependencies

The dependency direction is engine → glyph placement → font measurements. The
new module imports only the existing `FontMetrics`, `unicodedata` and postponed
annotations. It imports independently of the engine and optional font packages,
and its public annotations resolve at runtime.

Formatting dictionaries, text, coordinates and measurements remain explicit
inputs. The placement functions borrow those inputs, retain no event evidence
and own no cache. Measurement discovery, exact-face selection and measurement
caches remain with `FontMetrics`; the extraction adds no resource path.
`matches_authored_glyph_positions()` calls the position model in its defining
module rather than forwarding through engine globals.

Event-based `recover_font_row()`, `recover_tracked_font_row()` and
`fit_fullwidth_run()` stay in the engine, together with their existing event,
position-parser and diagnostic dependencies. Row assembly, paint selection,
timing, source ownership, report lifetime and edit application remain unchanged.
There is no new data model, context, wrapper, protocol or pipeline stage.

## Validation and provenance

The private pre-extraction runtime was captured before edits, including every
private Python source and the original sibling-font fallback. The v216 corpus
outputs were captured from the previous verified run; runtime, source, output
and font hashes were checked before reusing them as baselines. Current outputs
are generated afresh against those baselines.

`validation/check_glyph_placement_extraction.py` provides the one-release AST and
import audit against that hash-bound runtime. It does not freeze future algorithm
changes. The earlier extraction audits remain historical evidence for their own
releases.

`tests/check_glyph_placement_module.py` checks direct aliases, independently
resolvable annotations/imports, borrowed input preservation, fresh result lists,
known glyph positions/anchor fitting, silent rejection and internal model reuse.
The installed-font check now exercises the actual installed placement module
with an exact synthetic font and compiles every installed private source. It
retains the existing CLI and uninstall checks. Existing caller suites need no
functional test-double adaptation; their engine-export lookup remains valid.

The [v214 delivery contract](MODULE_DELIVERY.md) discovers the new file without
changes to delivery code. A compatibility probe uses the actual shipped v214
updater, a real v216 install and pinned mock GitHub responses with blob hash
verification. It checks rollback when writing the new module fails, successful
retry, preserved launcher preferences/user files, isolated installed imports
and uninstall. This is a transaction/delivery check, not a live GitHub download.

Fresh final results:

- All **93 regression scripts passed**, including the native libass render
  checks. Complete runtime and covered harness hashes stayed unchanged
  throughout validation.
- All **13 corpus outputs are byte-identical** to v216, with identical complete
  statistics. Source, baseline and output hashes and all **132 font hashes** were
  verified; no missing families were reported.
- All **five placement-module checks** and **five installed-font/module checks**
  passed. Installer checks: **32 passed, two native Windows checks skipped**.
  Updater checks: **10 passed, one native Windows check skipped**.
- Actual v214 updater delivery, write-failure rollback, installed imports and
  uninstall passed. The MKV/font smoke check passed, and Python/PowerShell
  reported the same six runtime sources and hashes.

Private evidence is retained under `validation/glyph-placement-extraction/`:
`baseline-manifest.json`, `baseline-corpus-summary.json`, `audit.json`,
`corpus/summary.json`, delivery/smoke logs, `powershell-manifest.json`, `regression-summary.json` and
`release-verification.json`.

Reproduce the module and structural checks, full suite and corpus comparison:

```sh
python validation/check_glyph_placement_extraction.py
python validation/run_backend_check.py --backend windows tests/check_glyph_placement_module.py
python validation/run_backend_check.py --backend windows tests/check_font_module.py
python validation/run_review_checks.py
python validation/run_caption_glow_phase_corpus.py \
  --baseline-engine validation/glyph-placement-extraction/baseline-runtime/simplify_ass.py \
  --baseline-summary validation/glyph-placement-extraction/baseline-corpus-summary.json \
  --baseline-sha256 d23c1883b2c698f7326b2721c2e29372c169038ef8f806f3931664cc7bb8c499 \
  --output-dir validation/glyph-placement-extraction/corpus
```

Restore the baseline runtime from v216 commit `327f503`, retaining relative
package paths, when reproducing the audit. Fonts, fixtures, baseline outputs and
generated reports remain private. Linux runs use Pillow BASIC plus real HarfBuzz
and native libass rendering; they do not replace native Windows CMD/NTFS or
self-update validation.

## After-release evaluation

The extraction preserves responsibilities and one-way dependencies without a
production shim, duplicated proof or downstream exception. Existing caller and
report contracts retain their ownership; the new tests follow actual defining
bindings rather than imposing the old physical layout on production.

No new workaround, unclear ownership or unrelated subsystem interaction warrants
a dedicated follow-up review. The remaining event-based fitting functions need
a separate dependency assessment when selected for extraction. The broader API
and pass-local index reviews remain separate work.
