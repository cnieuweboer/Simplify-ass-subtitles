# Core event-record extraction — v219

`Event`, `EventEvidence` and `DocumentMeasurementContext` now live in
`_simplify_ass/event_model.py`. The engine imports them as direct aliases before
any dependent record, factory or function default is defined. The engine version
is `2026.10.18.219`.

This implements the [bounded assessment](EVENT_MODEL_EXTRACTION_ASSESSMENT.md).
The three definitions and decorators are AST-identical to v218. The remaining
engine executable AST is unchanged except for its import and version. Existing
private modules, the batch wrapper and installer/updater are unchanged.

## Responsibilities and dependency direction

The model imports only dataclasses, postponed annotations and the existing
interpreter's `OverrideContinuation`. It imports independently of the engine,
font backends and pipeline policy. The dependency direction is engine → event
model → interpreter record. Existing measurement, outline, placement and sampling
modules require no change.

`Event` remains mutable. The two supporting records remain frozen. Constructor
order, field factories, equality/repr flags, `duration`, fresh `fields()` lists
and the evidence post-init tuple protection remain unchanged. All engine users
see the actual model classes, not wrappers or replacement record types.

Moving record definitions does not change who owns their contents:

- Document/pipeline callers own events and install resolved formatting/history
  caches together. Timing successors may retain their existing shared cache.
- Defaults and style catalogs remain borrowed from documents after preparation;
  independently constructed events retain fresh empty dictionaries.
- Evidence remains immutable source information. Producers and `replace_event()`
  retain their existing proof, invalidation and successor rules.
- Measurement producers establish canvas/wrapping context at the same boundaries.
  The context record itself infers neither viewport coverage nor active wrapping.
- Parser continuation keeps its existing type, factories and cache pairing.
  Pass caches, font diagnostics, result application and selection stay with their
  current owners.

`event_evaluation()`, `replace_event()`, document parsing/rendering, `TextRow`,
`StaticSpanSignature`, `StaticPoseEvidence` and pass-specific records remain in
the engine. This is a small canonical dependency boundary for future event-based
extractions, not a general model hierarchy or context redesign.

## Identity and contract coverage

The new module check covers direct aliases and runtime annotations; event and
document factories; the caption renderer's constructed measurement default;
independent import; constructor/equality behavior; fresh dictionaries; immutable
nested evidence; shallow replacement and deep copying; parser/replacement cache
policy; ordinary pickle round trips and legacy engine class lookup.

Factory checks run against the complete engine import. Rebinding aliases after
classes were created would miss stale factories/defaults and is not used as a
production technique. The actual installed probe exercises model identity,
constructors, document processing, replacement, CLI execution and owned-bytecode
uninstall from an unrelated directory. Existing ownership checks needed no test
adapter or relaxed assertion.

New pickles identify the private model module, so they require its package.
Existing root aliases resolve legacy engine class names without rewriting
`__module__` or introducing a compatibility shim. No production pickle API or
persistence mechanism was added.

## Fresh validation inputs

Previous private full-release manifests were unavailable. The exact working v218
runtime and all seven Python sources were captured before editing production.
Thirteen v218 corpus baselines were regenerated from actual supplied sources and
fonts before moving the records; current outputs are generated independently.

The later uploads were restored to ignored development paths, including the
four additional corpus tracks, their font bundles, the supplied Uniform bundle
and individual fonts. Existing different content was not overwritten. Input,
output and font hashes are recorded in the new private evidence.

A broad source-font inventory includes unavailable faces in ordinary captions;
those are not automatically reconstruction prerequisites. Corpus measurements
use a guarded report set that stops immediately if a reconstruction producer
reports a missing required family. Neither baseline nor current conversion
reported one. No measurement font was substituted and no matching policy was changed.

`validation/check_event_model_extraction.py` audits the three moved definitions
and decorators, remaining engine AST, unchanged private modules and model imports.
It is a one-release movement audit, not a permanent constraint on future models.
Historical extraction audits remain bounded to their own versions.

The generic [v214 delivery contract](MODULE_DELIVERY.md) discovers the new file
without a filename-list change. A real v218 installation was upgraded through
the actual shipped v214 updater, using pinned mock GitHub responses with blob
verification. The probe covers failure rollback at the new model file, successful
retry, preserved launcher choices and user files, installed class/factory identity
and uninstall. It does not claim a live GitHub download.

Fresh final results:

- All **95 regression scripts passed**, including native libass render checks.
  Runtime and covered harness hashes stayed unchanged throughout the run.
- All **13 freshly generated v218/v219 corpus pairs have byte-identical output
  and identical complete statistics**. All **124 supplied font-file hashes** and
  source/baseline/output hashes were verified; no required-font diagnostic fired.
- All **nine event-model checks passed**, including actual installed constructors,
  factories/defaults, document processing, replacement, CLI and uninstall.
- Installer checks: **32 passed, two native Windows checks skipped**. Updater
  checks: **10 passed, one native Windows check skipped**. Actual shipped-updater
  delivery/rollback/uninstall and the MKV/font smoke check passed.
- Python and PowerShell report the same **eight runtime sources and hashes**.
  The batch wrapper and delivery code remain byte-identical to the baseline.

Private evidence is under `validation/event-model-extraction/`:
`restored-upload-manifest.json`, `corpus-inputs.json`, `baseline-manifest.json`,
`baseline-corpus/summary.json`, `corpus/summary.json`, `audit.json`,
`regression-summary.json`, `powershell-manifest.json`, delivery/smoke logs and
`release-verification.json`.

Reproduce the focused checks and full suite:

```sh
python validation/check_event_model_extraction.py
python validation/run_backend_check.py --backend windows tests/check_event_model_module.py
python validation/run_backend_check.py --backend windows tests/check_event_evidence.py
python validation/run_backend_check.py --backend windows tests/check_measurement_context.py
python validation/run_review_checks.py
```

The audit baseline is the complete v218 runtime from commit `c247b01`, retaining
relative package paths and original font discovery. Corpus inputs/fonts and generated reports stay
private. The capture/comparison drivers are retained under
`validation/event-model-extraction/`; they regenerate outputs rather than relying
on imported historical summaries.

Linux checks use Pillow BASIC plus real HarfBuzz and native libass rendering.
Native Windows CMD/NTFS/self-update behavior requires Windows validation; the
platform-specific skips remain distinct from passes.

## After-release evaluation

There is one canonical set of record classes, and dependent factories/defaults
bind to those same classes from the start. Mutability, equality, cache sharing,
source-proof lifetime and caller-owned diagnostics remain unchanged. No adapter,
reverse engine import, duplicated proof or new policy exception was introduced.

No new architectural issue warrants a dedicated follow-up review. Restoring
private validation assets and generating a fresh baseline addressed the missing
historical evidence without changing production behavior. Future event-based
extractions still need their own dependency assessment; this release does not
choose their hierarchy or absorb the deferred API/pass-local index reviews.
