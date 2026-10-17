# Transform sampling extraction — v218

The six transform-sampling functions now live in
`_simplify_ass/transform_sampling.py`, with direct engine aliases:
`font_size_transform_needs_replay()`, `transform_weight()`,
`interpolate_transform_value()`, `_commit_transform_continuation()`,
`sample_transform_state()` and `sample_transform_states()`. The engine version is
`2026.10.17.218`.

This implements the [bounded assessment](TRANSFORM_SAMPLING_EXTRACTION_ASSESSMENT.md).
All six definitions are AST-identical to v217. The remaining executable engine
AST is unchanged except for imports and version; all existing private modules
are byte-identical. The batch wrapper and delivery code are unchanged.

## Responsibilities and data flow

The dependency direction is engine → sampling → override interpreter. Sampling
imports only `math`, `re`, `typing.Iterable` and the existing interpreter's
`OverrideContinuation`, `OverrideEvaluation`, `apply_font_size()` and
`apply_override()`. It needs no engine import, event model, font class, report,
pass context or resource-path adjustment.

Base formatting, styles, defaults and transform descriptions remain borrowed.
Independent evaluations own their shallow formatting copies. Parser continuation
retains the existing immutable record and historical commit policy. The ordered
sampler remains lazy, materializes sample times when iteration begins, and owns
its color decoding, completed-prefix and per-field caches for that generator's
lifetime. There is no persistent sampler cache. The interpolation helper may
populate an explicitly supplied mutable decoding cache, as before.

The existing `OverrideEvaluation` binding stays frozen while its owned formatting
dictionary stays mutable. Separate samples retain separate buffers. Relative and
repeated size handling, reset/latch semantics, optimized admission, source-order
replay, malformed/nonfinite fallback, interpolation rounding and color spelling
are unchanged.

Static-state selection, upright fallback, text freezing/traversal, event caches,
source paint/pose evidence, diagnostics and event replacements remain with their
engine consumers. No new context, record type, wrapper or forwarding callback
was introduced.

## Test bindings and coverage

The shared interpreter instrumentation now resolves the samplers' defining
modules through engine exports, then patches the matching imported bindings
with one shared replacement. It deduplicates owners and still supports historical
single-file engines. This stays in tests; production functions use ordinary
one-way imports.

The assessment's control showed why this adjustment matters: a passing freeze
script could silently lose sampler-buffer assertions. The current helper observes
engine, interpreter and sampler calls, and checks restoration and historical
owner deduplication. The freeze suite retains all **634,286** checks, including
**5,130** sampler cases, **1,440** selection cases and **576** continued-freeze
steps; the assertions were not relaxed to accommodate the move.

`tests/check_transform_sampling_module.py` adds alias/import/annotation checks,
borrowed-seed and result-buffer checks, lazy ordered-time consumption, optimized
and source-order fallback composition, relative-size interpreter ownership and
explicit decoding-cache ownership. The installed interpreter/module probe also
exercises optimized and replay sampling through the actual installed module,
from an unrelated working directory, before CLI execution and uninstall.

## Validation and provenance

The v217 runtime and all private sources were captured before edits, retaining
sibling-font discovery. Previously verified v217 corpus outputs are reused only
after checking runtime, source, output and font hashes. Current outputs are
regenerated against that baseline.

`validation/check_transform_sampling_extraction.py` audits unchanged moved ASTs,
the remaining engine, existing modules and the new module's imports against the
hash-bound baseline. It is evidence for this release, not a permanent freeze on
future sampling algorithms. Earlier extraction audits remain historical.

The generic [v214 delivery contract](MODULE_DELIVERY.md) discovers the new source
without a filename-list change. A compatibility probe upgrades a real v217
installation through the actual shipped v214 updater, using pinned mock GitHub
responses and real blob verification. It checks failure rollback at the new
module, successful retry, retained launcher choices/user files, isolated installed
sampling and uninstall. This verifies delivery transactions rather than a live
GitHub download.

Fresh final results:

- All **94 regression scripts passed**, including native libass render checks.
  The full runtime manifest and covered harness inputs stayed unchanged
  throughout validation. All **634,286 freeze-continuation checks** were retained.
- All **13 corpus outputs are byte-identical** to v217, with identical complete
  statistics. Source, baseline and output hashes and all **132 font hashes** were
  verified; no missing families were reported.
- All **seven sampling-module checks** and **seven interpreter/module checks**
  passed. The installed probe exercises both optimized and replay sampling.
  Installer checks: **32 passed, two native Windows checks skipped**. Updater
  checks: **10 passed, one native Windows check skipped**.
- Actual shipped-updater delivery, new-module failure rollback, installed imports
  and uninstall passed. The MKV/font smoke check passed. Python and PowerShell
  identify the same seven runtime sources and hashes.

Private evidence is under `validation/transform-sampling-extraction/`:
`baseline-manifest.json`, `baseline-corpus-summary.json`, `audit.json`,
`corpus/summary.json`, delivery/smoke logs, `powershell-manifest.json`, `regression-summary.json` and
`release-verification.json`.

Reproduce the focused and full checks:

```sh
python validation/check_transform_sampling_extraction.py
python validation/run_backend_check.py --backend windows tests/check_transform_sampling_module.py
python validation/run_backend_check.py --backend windows tests/check_override_module.py
python validation/run_backend_check.py --backend windows tests/check_freeze_continuation.py
python validation/run_review_checks.py
python validation/run_caption_glow_phase_corpus.py \
  --baseline-engine validation/transform-sampling-extraction/baseline-runtime/simplify_ass.py \
  --baseline-summary validation/transform-sampling-extraction/baseline-corpus-summary.json \
  --baseline-sha256 95cf3d022042ad6d6a96866a5d57e7f0dfce2d4d33477f7c5f4bbf4cd1f83523 \
  --output-dir validation/transform-sampling-extraction/corpus
```

Restore the baseline runtime from v217 commit `f371919`, retaining package paths,
when reproducing the audit. Fonts, fixtures, baseline outputs and generated
reports stay private under the existing development layout. Linux Windows-font
checks use Pillow BASIC plus real HarfBuzz and native libass rendering; native
Windows CMD/NTFS/self-update behavior requires Windows validation.

## After-release evaluation

Sampling keeps its bounded temporary state, and consumers retain their original
selection, evidence and reporting responsibilities. The extraction needs no
production accommodation for test patches, duplicated proof, new exception or
reverse import. The known instrumentation issue is addressed in the shared
helper with direct coverage of actual sampler calls and owner deduplication.

No new workaround, unclear ownership or unrelated subsystem interaction warrants
a dedicated follow-up review. The deferred global API and pass-local index
reviews remain separate. Choose the next extraction from its actual dependencies
rather than expanding this module into freezing or selection policy.
