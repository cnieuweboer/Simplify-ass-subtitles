# ASS override interpreter extraction — v216

The seven style/override functions, two existing frozen records and six
supporting constants assessed in
[OVERRIDE_PARSER_EXTRACTION_ASSESSMENT.md](OVERRIDE_PARSER_EXTRACTION_ASSESSMENT.md)
now live in `_simplify_ass/ass_overrides.py`. The engine version is
`2026.10.16.216`; existing engine names remain direct aliases, including the actual
shared `DEFAULT_STATE` dictionary and `STYLE_TAGS` map.

## Responsibility and data flow

The new module depends on `re`, `dataclasses.dataclass`, `typing.Iterable` and
postponed annotations. It has no engine/font dependency, resource lookup or
reverse import. Its nine definitions are AST-identical to v215, including the
frozen records, signatures, reset semantics, first-alignment latch, relative
font sizes, malformed paint handling and formatting ownership.

The interpreter owns an explicit vocabulary containing the same 51 recognized
tags, matched longest-first and case-insensitively. `SAFE_SIMPLE_TAGS` remains in
the engine with the original output policy. A contract check requires every
permitted simple tag to be recognized while allowing recognized effect tags
that the simplifier does not retain unchanged. Vocabulary initialization is the
only substantive dependency-wiring adjustment inside the moved code; neither
recognition nor output admission changes.

Event caches and replacements, `StaticSpanSignature`, transform sampling and
continuation commitment, font-size replay decisions, effect-admission bounds,
freezing/compaction, rendering, geometry and reconstruction stay in the engine.
`NUM`, position parsing and both font modules are unchanged. The remaining engine
executable AST differs only by the extraction import and version. The production
batch wrapper, installer/updater code and test wrappers are untouched.

The existing ownership contracts remain in
[CONTEXT_OWNERSHIP_REVIEW.md](CONTEXT_OWNERSHIP_REVIEW.md). The interpreter mutates
caller-owned formatting, borrows style/default catalogs and returns immutable
continuation snapshots. A frozen evaluation binding still contains an ordinary
formatting dictionary. Complete evaluation owns a fresh buffer; event cache
borrowing remains the event owner's responsibility. No new global parser cache,
processing context, callback plumbing or forwarding API was added.

## Test boundaries

`tests/override_module_test_helpers.py` patches the actual callable's defining
binding and the engine's borrowed binding with one shared replacement. Historical
single-file engines have one binding, so the helper wraps it once. The inline,
freeze and effect-continuation checks retain their complete ordered traces,
clean-buffer assertions and successor/borrowing checks. Their focused assertion
counts remain unchanged. Parsing-reuse checks now observe or reject parsing
through both bindings; their frozen v171/v172 audits remain unchanged.

The live single-tag source audit reads the actual function definition rather
than assuming it is in the root file. No source-lookup or call-count assertion
was removed. Test instrumentation follows the interpreter without production
code consulting engine globals to imitate the old layout.

`tests/check_override_module.py` adds six checks covering all 15 aliases, shared
constant identity, frozen records with owned mutable formatting, independent
standard-library import, vocabulary/output-policy boundaries, token reuse,
borrowed styles, call tracing across both bindings and deduplication when they
coincide. Installed execution runs from an unrelated working directory, without
the checkout on the import path, in a target with spaces; it exercises the actual
interpreter, CLI conversion and managed source/bytecode removal while retaining
user files. The existing installed-font checks continue to use the full runtime.

## Delivery and validation

The v214 inventory discovers the new private source without delivery-list edits.
A separate probe uses the unchanged shipped v214 updater with the actual new
engine/module sources and mocked pinned GitHub responses with real blob hashes.
It covers upgrade from the complete v215 runtime, failure at `ass_overrides.py`
with restoration of the old tree, successful retry, preserved launcher choices
and user files, isolated imports and uninstall. Older fixed-list clients still
need the documented complete-repository installer migration.

The pre-extraction v215 runtime was copied intact, with its relative package paths
and original sibling-font fallback. Its source manifest agrees with v215's
validated thirteen-track outputs. New corpus conversions compare against those
verified outputs; the pre-extraction outputs were not regenerated for this release.

`validation/check_override_module_extraction.py` is a one-release audit against
the hash-bound v215 engine. It checks unchanged definitions, five unchanged
constant initializers, unchanged existing private sources, identical complete
recognized vocabulary, unchanged output whitelist and remaining engine AST,
and standard-library-only module imports. It does not freeze future parser work.

Fresh final results:

- All **92 regression scripts passed**, including native libass rendering and
  the six new interpreter-module checks. Runtime source hashes and covered test
  inputs stayed unchanged throughout the run.
- All **13 newly converted corpus tracks are byte-identical to v215**, with
  identical complete statistics. Source/baseline/output hashes and all **132 font
  hashes** were reverified; no missing font families were reported.
- Existing focused counts remain unchanged: **632,304** override-continuation,
  **51,222** inline-continuation, **634,286** freeze-continuation, **179,958**
  effect-continuation and **219** parsing-reuse checks. The full suite also
  preserves relative font size, context, event ownership and paint/render checks.
- Installer: **32 passed, two native-Windows checks skipped**. Updater:
  **10 passed, one native-Windows check skipped**. The actual v214-to-v216
  delivery/rollback/uninstall probe and MKV/font smoke check passed.
- PowerShell and Python identify the same five runtime sources and hashes.
  No production batch-wrapper or test-wrapper change was needed.

Private evidence is in `validation/override-module-extraction/`: `audit.json`,
`baseline-manifest.json`, `corpus/summary.json`, `regression-summary.json`,
`powershell-manifest.json`, delivery/smoke probes and `release-verification.json`.
The copied baseline runtime and source/font assets remain private. No runtime
source cleanup followed the complete validation run.

Reproduce the checks from the repository root:

```sh
python validation/check_override_module_extraction.py
python validation/run_backend_check.py --backend windows tests/check_override_module.py
python validation/run_backend_check.py --backend windows tests/check_override_continuation.py
python validation/run_backend_check.py --backend windows tests/check_outline_parsing_reuse.py
python validation/run_review_checks.py
python tests/check_windows_installer.py
python tests/check_windows_updater.py
python validation/run_caption_glow_phase_corpus.py \
  --baseline-engine validation/override-module-extraction/baseline-runtime/simplify_ass.py \
  --baseline-summary validation/font-outline-extraction/corpus/summary.json \
  --baseline-sha256 a4319191ab65a378ce37f51f714b125dcaa50842f5cdf7331324c63079fb7545 \
  --output-dir validation/override-module-extraction/corpus
```

The default audit baseline is restored from v215 (`07e012a`, also unchanged in
the assessment commit `19a8d33`). Runtime snapshots, subtitle/font assets and
generated evidence remain private. Linux BASIC/HarfBuzz and native libass checks
do not replace native Windows CMD, self-update or NTFS validation.

## After-release evaluation

The assessed boundary fits without changing algorithms or surrounding owners.
Vocabulary and output-policy lists overlap intentionally because they answer
different questions; their relationship is tested. The single-tag implementation
remains unique. The small shared helper belongs to test instrumentation and
avoids duplicated patch logic or double-counted calls across the new boundary.

No new production workaround, unclear owner or unrelated subsystem interaction
currently warrants a dedicated follow-up review. Global API and pass-local index
reviews remain separate. Select the next extraction from its dependencies rather
than expanding this interpreter to include nearby sampling or effect policy.
