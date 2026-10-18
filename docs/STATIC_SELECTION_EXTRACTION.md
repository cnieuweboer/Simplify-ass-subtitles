# Static-state selection extraction — v220

Static geometry and representative paint selection now live in
`_simplify_ass/static_selection.py`. This implements the
[bounded assessment](STATIC_SELECTION_EXTRACTION_ASSESSMENT.md). The engine
version is `2026.10.18.220`; no selection or simplification policy changes.

## Boundary and responsibilities

The module contains the existing `select_static_state()`, twelve internal
selection helpers, the upright-pose search and two shared state predicates,
plus the five existing records: `StaticStateContext`, `StaticStateEvidence`,
`StaticStateSamples`, `StaticPoseEvidence` and `StaticStateSelection`.

These definitions and decorators moved unchanged. The engine imports direct
aliases before dependent classes/functions are defined. `FrozenBlock` and the
freeze/rendering consumers bind to those actual records and functions; there
are no forwarding wrappers, replacement result types or callback adapters.

Dependency direction is engine → static selection → canonical event model,
override interpreter and transform sampler. Other imports are standard library
only. The module imports independently of the engine and optional font backends.
Existing private modules are byte-identical. The batch wrapper and delivery
code are unchanged.

The selector owns interval ranking, readable upright selection, sustained
position/size protection, representative color voting and selection-local
evidence. It neither constructs replacement events nor installs formatting in
event caches. Source admission, `_freeze_inputs()`, `freeze_block()`,
`simplify_visual_text()`, serialization and pipeline orchestration remain with
their existing engine owners. In particular, nearby animated-shadow source
admission was not pulled into the selector simply because of its source location.

## Data flow and ownership

- Base formatting, transforms, styles, defaults and paint events remain borrowed
  caller inputs. The unchanged early result deliberately returns the original
  base dictionary; sampled selections own their changed formatting.
- Opaque/settled seed containers are copied locally. Existing snapshot dictionaries
  remain borrowed; new snapshots are independent. Disabled evidence and an
  enabled but empty collection remain distinct.
- Hold votes, sampled candidates, color dwell and upright-search caches remain
  call-local. No new persistent state or global parser cache was introduced.
- Parser continuation follows the selected branch. Pose proof remains separate
  and frozen, with its existing tuple protection. Neither paint voting nor this
  extraction invents parser history or extends source-proof lifetime.
- The five records retain their original frozen declarations and field factories.
  Frozen bindings do not recursively freeze formatting buffers. Consumers retain
  the existing reset, replacement and serialization handoffs.
- The selector produces no font diagnostics or counters. Reports and result
  application remain with the callers that already owned them.

Ordinary new pickles refer to the defining private module. Existing engine aliases
continue resolving historical class names without changing `__module__` or adding
a persistence mechanism.

## Test observation and delivery

The test-only interpreter binding helper now observes the actual selector owner
alongside the engine, interpreter and sampler. Identity deduplication prevents
double wrapping where several exports resolve to one module. No production call
was routed through the engine to accommodate instrumentation. The continuation
check retains its complete 634,286 assertions rather than silently losing the
selector's direct interpreter calls.

The new module check covers independent import, canonical aliases and runtime
annotations, result factories, borrowed seed snapshots, unchanged-state identity,
sample buffer independence, continuation, frozen bindings, tuple-protected pose,
interpreter observation/restoration, pickle lookup and actual installed use.
The installed probe freezes animated text and runs the CLI from an unrelated
directory, then checks owned source/bytecode removal and preservation of user files.

The [generic delivery contract](MODULE_DELIVERY.md) discovers the new module
without any filename-list change. A separate private probe upgrades a real v219
installation through the actual shipped v214 updater using pinned mock GitHub
tree/blob responses. It checks rollback when the new selector file cannot be
installed, a successful retry, unchanged launcher choices/user files, installed
canonical result types/freezing and uninstall. This is not a live network update
or native Windows validation.

`validation/check_static_selection_extraction.py` is a one-release structural
audit against the exact v219 baseline. It compares moved definitions/decorators,
the remaining executable engine AST and unchanged existing private sources.
Its fixed release scope does not constrain future justified policy changes.

## Fresh validation

Before editing production, all eight v219 runtime sources were captured with a
complete manifest. Thirteen baseline conversions were regenerated from the
actual supplied subtitles/fonts. Current conversions are independently generated;
both sets stop if a reconstruction producer reports a required missing font.
Source, font, baseline/output and complete runtime hashes are verified.

Fresh final results:

- All **96 regression scripts passed**, including native libass render checks.
  Complete runtime and harness hashes remained unchanged during validation.
  The continuation check retained all **634,286 assertions**.
- All **13 v219/v220 corpus pairs have byte-identical output and identical
  complete statistics**. All **124 supplied font-file hashes** were verified;
  neither baseline nor current conversions reported a missing required font.
- All **eight module checks passed**, including actual installed selector/result
  identity, freezing, CLI processing and owned source/bytecode uninstall.
- Installer: **32 passed, two native Windows checks skipped**. Updater:
  **10 passed, one native Windows check skipped**. The shipped-updater
  installation/rollback/retry/uninstall probe and MKV/font smoke check passed.
- Python and PowerShell agree on all **nine runtime source hashes**. The batch
  wrapper and installer/updater source files remain byte-identical to v219.

Private evidence and reproducible drivers are under
`validation/static-selection-extraction/`: `baseline-manifest.json`,
`corpus-inputs.json`, `baseline-corpus/summary.json`, `corpus/summary.json`,
`audit.json`, regression/delivery/smoke logs and `release-verification.json`.
Fonts, subtitle fixtures, conversions and reports remain local and ignored.

Reproduce focused checks and the full suite from the repository root:

```sh
python validation/check_static_selection_extraction.py
python validation/run_backend_check.py --backend windows tests/check_static_selection_module.py
python validation/run_backend_check.py --backend windows tests/check_freeze_continuation.py
python validation/run_backend_check.py --backend windows tests/check_freeze_consumers.py
python validation/run_review_checks.py
```

Linux checks use Pillow BASIC with real HarfBuzz and native libass render checks.
Native Windows CMD/NTFS/self-update checks require a Windows host; their skips
must remain distinct from passes.

## After-release evaluation

The extraction moves a cohesive processing responsibility without changing its
policy, data flow or caller-owned state. No production adapter, reverse import,
duplicated proof, local exception or new cache owner was introduced. The bounded
test-observation change keeps checks at the real owner instead of weakening them.

No dedicated follow-up review is needed for this extraction. Subsequent candidates
should be assessed from the resulting dependencies, including larger processing
subsystems; this release neither prescribes their hierarchy nor absorbs the
deferred global API and pass-local index reviews.
