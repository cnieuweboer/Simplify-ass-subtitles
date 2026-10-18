# Text freezing extraction — v223

Static override/text freezing now lives in `_simplify_ass/text_freezing.py`.
This implements the [bounded assessment](TEXT_FREEZING_EXTRACTION_ASSESSMENT.md).
The engine version is `2026.10.18.223`; selection, serialization and pipeline
behavior are unchanged.

## Boundary and responsibilities

The module contains the existing frozen `FrozenBlock` record, shared mutable
`SAFE_SIMPLE_TAGS` whitelist and five functions: `safe_override()`,
`simplify_text()`, `_freeze_inputs()`, `freeze_block()` and
`simplify_visual_text()`. All definitions, decorators, defaults and the whitelist
assignment moved unchanged, with the whitelist's explanatory comment. Engine
exports remain direct aliases imported before dependent uses.

Dependency direction is engine → text freezing → interpreter, static selection
and caption rendering. Other imports are standard library only. The freezer
uses the existing `render_tag()` rather than duplicating serialization. There
is no reverse engine import, callback injection or forwarding adapter. No helper
uses paths or `__file__`; independent processing needs neither the engine nor
optional font packages. Existing private module sources are byte-identical.
The batch wrapper, installer and updater sources are unchanged.

The engine retains event admission, pipeline freezing, source-family proofs,
cache installation, replacement/invalidation, final compaction and report
aggregation. Direct consumers of `_freeze_inputs()` retain its exact evaluation,
transforms, boundaries and reset result. No alternate parser was introduced.

## Preserved ownership and behavior

- Initial formatting, defaults, styles and evidence seeds remain borrowed
  read-only. Header parsing owns its copied state, transforms and boundaries;
  visual freezing owns the local stream's state and serialized buffers.
- Continuation and pose use existing canonical records. Reset-dependent pose
  selection, adjacent-header rotation handling, ordered uniform/axis overrides
  and malformed drawing-switch handling retain the existing order and policy.
- The selector retains its votes/samples/evidence responsibility. Freezing
  returns the exact selection record and retains shared seed snapshot identity.
  After selection it clamps selected blur, while settled snapshots retain
  pre-clamp source paint. This ordering did not move into the selector.
- `FrozenBlock` retains its fields, constructor and frozen bindings. Its nested
  selection state remains deliberately mutable; no deep-copying or model
  consolidation was added. Continuation defaults retain canonical type identity.
- `SAFE_SIMPLE_TAGS` remains one shared mutable set, read-only in production,
  with a direct engine alias. It is separate from the interpreter's broader
  recognized-tag vocabulary.
- Simple per-block simplification and continuation-aware visual freezing retain
  their distinct contracts. Visible-only extraction still bypasses freezing,
  excludes drawing payloads and returns the same normalized literal text.
- Return strings, visible text and drawing-character counts are unchanged.
  Callers retain event replacement, counters/warnings and final reporting.
  No persistent cache or diagnostic owner moved into this module.

Ordinary new `FrozenBlock` pickles identify the private defining module. Direct
engine aliases retain historical class-name lookup without rewriting `__module__`
or introducing a persistence API.

## Tests and delivery

The shared interpreter-spy helper now includes the actual defining module of
`freeze_block()` among consumers, deduplicating bindings and retaining historical
single-file support. The frozen-block result check observes selection calls on
that defining module, preserving its exact-result and parsed-base identity
assertions. Every existing assertion remains. The inline-continuation check's
engine compaction spy stays at its actual engine call site; production calls do
not forward through the engine to accommodate spies.

The new `check_text_freezing_module.py` covers aliases, annotations/defaults,
shared whitelist identity, cold processing without optional backends, borrowed
input/seeds, pre-clamp snapshots, frozen binding/mutable selection semantics,
ordinary/legacy pickle lookup, visible-only bypass, drawing accounting, safe
header serialization and installed processing from an unrelated directory.
Owned source/bytecode removal preserves user files.

The generic delivery contract discovers the new module without a filename-list
change. A private probe installs the exact v222 runtime and upgrades it through
the actual shipped v214 updater using pinned mock GitHub tree/blob responses.
It checks complete rollback when the new module cannot be installed, successful
retry, preserved launcher choices/user files, installed aliases/defaults and
actual freezing/evidence behavior, then uninstall. This is not a live network
update or native Windows execution claim.

`validation/check_text_freezing_extraction.py` audits this release against the
exact v222 baseline. Moved definitions/decorator/whitelist and the remaining
executable engine AST are identical except import/version; existing private
sources are unchanged. Its historical scope must not constrain future justified
freezing or processing changes.

## Validation

All **99 regression scripts passed**, including native libass rendering.
Complete runtime and test/harness hashes remained unchanged throughout the run.
The continuation check retained all **634,286 assertions**; observer corrections
retained the existing identity, mutation and accumulated-evidence assertions.

All **13 fresh v222/v223 corpus pairs have byte-identical output and identical
complete statistics**. All **124 supplied font-file hashes** were verified;
neither conversion set reported a missing required font.

All seven new module checks passed, including independent/installed processing
and owned source/bytecode removal. Installer checks: **32 passed, two native
Windows checks skipped**. Updater checks: **10 passed, one native Windows check
skipped**. The actual shipped-updater rollback/retry/uninstall probe and MKV/font
smoke check passed. Python and PowerShell agree on all **twelve runtime source
hashes**.

Fresh evidence is private under `validation/text-freezing-extraction/`: complete
baseline/runtime manifests, `corpus-inputs.json`, fresh baseline/current corpus
summaries, `audit.json`, regression/delivery/smoke logs and
`release-verification.json`. Corpus drivers stop on a missing required-font report.
Source, font, output, runtime and test/harness hashes are verified. Fixtures,
fonts and generated outputs remain ignored local assets.

Run from the repository root:

```sh
python validation/check_text_freezing_extraction.py
python validation/run_backend_check.py --backend windows tests/check_text_freezing_module.py
python validation/run_review_checks.py
```

Linux regression checks use Pillow BASIC with real HarfBuzz and native libass
rendering. Native Windows CMD/NTFS/self-update checks require Windows; platform
skips remain separate from passes.

## After-release evaluation

Freezing now owns a closed stream-processing and serialization subsystem.
Selectors retain evidence selection; event producers and pipeline/report owners
retain their responsibilities. No reverse import, production adapter, duplicated
proof, new cache owner or local exception was introduced. The two observer
corrections retain meaningful assertions at the actual consumers.

No dedicated corrective follow-up review is needed. Choose the next boundary
from the resulting dependency graph; the deferred global API and pass-local
index reviews remain separate work.
