# Caption rendering extraction — v222

Source-paint resolution and reconstructed caption rendering now live in
`_simplify_ass/caption_rendering.py`. This implements the
[bounded assessment](CAPTION_RENDERING_EXTRACTION_ASSESSMENT.md). The engine
version is `2026.10.18.222`; caption selection and rendering policy are unchanged.

## Boundary and responsibilities

The module contains the existing frozen `SourceCaptionPaint` record,
`MAX_PROVED_CAPTION_BORDER`, `render_tag()`, `_source_caption_paint()` and
`render_simplified_caption()`. Their definitions, decorators and constant moved
unchanged. Engine exports are direct aliases imported before dependent
annotations and defaults; there are no forwarding functions or callback adapters.

Dependency direction is engine → caption rendering → interpreter/event model.
Other dependencies are standard library only. Independent import does not load
the engine or optional font backends. No paths, font discovery or `__file__`
behavior moved. All existing private sources are byte-identical. The batch
wrapper, installer and updater sources are unchanged.

The engine retains source-family selection, literal-span correspondence,
geometric/timing compatibility, compositing clearance, matched-fade proofs,
row reconstruction, event replacement and emission. Those producers supply the
complete compatible state family; the moved paint resolver does not discover
or match events. Moving a shared consumer does not move its callers' proof or
source-evidence lifetime decisions.

## Ownership and preserved behavior

- Resolver and renderer borrow state dictionaries, context and supplied evidence
  read-only. Working dictionaries, contour sets and serialized output are local
  to each call. No event cache, pass index or diagnostic accumulator moves.
- The resolver retains the existing contour-compatibility rules, uncertainty
  rejection, authored low-contrast color, independent contour transparency,
  borderless evidence, coupled fade settlement and two-unit reconstruction cap.
- `SourceCaptionPaint` retains its frozen fields, positional constructor and
  default border tuple. The renderer's measurement default uses the canonical
  `DocumentMeasurementContext`; no alternate context or paint model was added.
- Explicit source paint retains precedence over uncertain-paint contrast repair.
  The existing off-canvas foreground-to-shadow transfer keeps its bounded
  position/paint behavior and invalidates foreground paint proof before output.
  This policy remains inside the same unchanged renderer.
- `render_tag()` also serves freezing and ordinary tag serialization. Its scalar,
  tuple, alpha and BGR formatting remains independent of caption reconstruction.
- Source evidence, font caches, reports/counters, cache installation and
  replacement/invalidation remain with their existing owners. The renderer
  returns the same string; no result hierarchy or pipeline context was added.

Ordinary new paint-record pickles identify the private defining module. Engine
aliases retain historical class-name lookup without rewriting `__module__` or
introducing a persistence API.

## Tests and delivery

The new `check_caption_rendering_module.py` covers canonical aliases,
annotations/defaults, frozen record shape and pickle lookup, cold import and
rendering without the engine/optional backends, borrowed-input isolation,
contour/alpha policy, foreground-proof invalidation during shadow transfer,
independent tag serialization and installed use from an unrelated directory.
Installation/uninstall checks preserve user files while removing owned source
and compiled bytecode. Existing tests needed no observer retargeting or source
substitution.

The generic delivery contract discovers the new module without filename-list
changes. A private probe installs the exact v221 runtime and upgrades it through
the actual shipped v214 updater using pinned mock GitHub tree/blob responses.
It verifies complete rollback when the new module cannot be installed, successful
retry, preserved launcher choices/user files, installed module/record/default
identity, actual caption rendering and uninstall. It does not claim a live
network update or native Windows execution.

`validation/check_caption_rendering_extraction.py` audits this release against
the exact v221 baseline: moved definitions/decorators/constant and the remaining
executable engine AST are identical except import/version; existing private
sources are unchanged. This bounded historical audit must not constrain future
justified rendering or processing changes.

## Validation

All **98 regression scripts passed**, including native libass rendering checks.
The complete runtime and test/harness hashes remained unchanged throughout the
final run. The continuation check retained all **634,286 assertions**.

All **13 fresh v221/v222 corpus pairs have byte-identical output and identical
complete statistics**. All **124 supplied font-file hashes** were verified;
neither conversion set reported a missing required font. All seven new module
checks passed, including installed rendering and owned bytecode removal.

Installer checks: **32 passed, two native Windows checks skipped**. Updater
checks: **10 passed, one native Windows check skipped**. The actual shipped
updater rollback/retry/uninstall probe and MKV/font smoke check passed. Python
and PowerShell agree on all **eleven runtime source hashes**.

Fresh validation evidence is recorded privately under
`validation/caption-rendering-extraction/`: complete baseline/runtime manifests,
`corpus-inputs.json`, fresh baseline/current corpus summaries, `audit.json`,
regression/delivery/smoke logs and `release-verification.json`. Corpus drivers
stop immediately when reconstruction reports a missing required font. Font,
source, output, complete runtime and regression harness hashes are verified.
Fixtures, fonts and generated outputs remain ignored local assets.

Run the focused module check, historical movement audit and full suite from the
repository root:

```sh
python validation/check_caption_rendering_extraction.py
python validation/run_backend_check.py --backend windows tests/check_caption_rendering_module.py
python validation/run_review_checks.py
```

Linux checks use Pillow BASIC with real HarfBuzz and native libass rendering.
Native Windows CMD/NTFS/self-update checks require Windows; platform skips remain
separate from passes.

## After-release evaluation

The extraction preserves the existing rendering responsibility without moving
source-family proofs or evidence lifetime decisions into a shared consumer.
There is no reverse engine import, adapter, duplicate proof, new cache owner,
local exception or test-observer workaround. No dedicated corrective review is
needed. Choose subsequent boundaries from the resulting dependency graph;
the deferred global API and pass-local index reviews remain separate work.
