# Bounded assessment: font measurement extraction

This assesses the v212 engine at commit `1ce8136`. It proposes no new
matching or rendering policy and does not prescribe the eventual module tree.
The assessment leaves implementation, wrappers, tests and installers unchanged.

## Decision and exact first boundary

Proceed with one small implementation extraction, subject to the acceptance
checks below. Keep production entry points at the repository root for this
increment. Add only:

```text
_simplify_ass/
    __init__.py
    font_metrics.py
```

Use an ordinary package with an empty initializer. Do not introduce `shared/`,
move tools into `subtitle_tools/`, or combine this with an API/index review.

Move these existing definitions together, without changing their fields,
algorithms, public method signatures or frozen status:

| Definition | v212 source lines, including decorators | Responsibility |
| --- | --- | --- |
| `FontFace` | 8768–8779 | Exact face/collection index, coverage and variable coordinates |
| `FontCapabilities` | 8782–8787 | Available measurement/shaping backends |
| `FontLineInkMetrics` | 8790–8794 | Immutable baseline-relative ink results |
| `FontMetrics` | 8797–9257 | Discovery, selection, instances, shaping, outlines and measurement caches |

This is approximately 490 lines, rather than the entire adjacent font-related
section. `FontMetrics` has twelve methods. Its only project-defined runtime
global references are itself and the three records moving with it. It does not
call a parser, consume `Event`, inspect subtitle timing, or select paint.
The static dependency inventory counts 86 other engine definitions referring
to these four classes, including annotations; that is not a count of runtime
callers.
An attribute-reference audit found no use of the measurement owner's sixteen
private attribute names elsewhere in the engine; no consumer cache access
needs to be redesigned as part of this move.

The extracted module needs `from __future__ import annotations`, `dataclass`,
`BytesIO`, `Path`, `math` and `unicodedata`. Imports of `os`, Pillow, fontTools,
HarfBuzz and the fontTools pen/instancing helpers currently occur inside methods;
keep their placement and failure behavior. In particular, importing the engine
must still work without optional font packages. Do not eagerly initialize a
font catalog or add a module-global owner/cache.

Leave these responsibilities in `simplify_ass.py`:

- `FontOutlineMatcher` and its profile cache. It calls `fit_cubic_points()`, which
  also serves vector reconstruction. Pulling them into this extraction would
  widen the boundary without being necessary.
- `FontProcessingReport`, row/anchor recovery, exact-font reconstruction proofs,
  resource-owner creation, CLI/MKV font extraction and pipeline coordination.
- `_FontTimestampFilter` and its existing logger registration, unchanged at
  engine import time. They have no dependency on the extracted classes. Moving
  logging initialization is unnecessary for this first boundary.

## Imports, discovery and ownership contracts

The dependency direction must be:

```text
simplify_ass -> _simplify_ass.font_metrics -> standard library / optional backends
```

Explicitly import the four names into `simplify_ass.py` before the engine's
dependent definitions. Existing `simplify_ass.FontMetrics` and related imports
must remain aliases of the actual definitions, not wrappers or subclasses.
Do not import the engine from the new module, use wildcard imports, copy globals
between modules, or rewrite `__module__` to disguise the extraction.

The classes' defining module will change. No repository persistence contract
using pickled font owners/results was found. Test helper dispatch does depend on
that metadata, however; address it as described below. For version comparisons,
use separate processes rather than loading two future package versions under
different engine aliases and accidentally sharing one implementation package.

`FontMetrics.__init__` currently appends
`Path(__file__).resolve().parent / 'fonts'` after explicit directories, followed
by platform font locations. In the new module, anchor that fallback to its
parent package's parent, preserving the directory beside `simplify_ass.py`.
For this fixed layout a direct parent adjustment is sufficient; no generic
resource-location service or new public constructor parameter is needed.
Preserve search order, alias deduplication and deterministic file iteration.
Keep input-adjacent font discovery in the existing engine caller.

Preserve the existing single-owner lifecycle:

- One `FontMetrics` may be reused across a conversion batch.
- Face identities, variable-instance bytes, shaping and measurement caches stay
  on that owner, with the existing keys and lifetimes.
- Consumers borrow immutable faces/results. An `open_face()` caller still closes
  its leased face. No new file writes or persistent font caches.
- Reports and outline matchers retain their separate owners. The existing
  matcher/catalog identity guard remains in the engine.

## Concrete supporting changes required for extraction

### Test adaptation

`tests/font_geometry_test_helpers.py:row_test_call()` currently locates engine
row functions through `sys.modules[type(metric).__module__]`. Once the class
moves, that would incorrectly look for row reconstruction inside the measurement
module. Existing vector, fragment, translated-phase and moving-glyph checks use
this helper.

Make the helper's engine-function selection explicit in test code; retain its
historical method-based route for immutable old engines. Preserve the existing
recording/failure doubles and report propagation. Do not add reconstruction
functions to the new module to satisfy this helper.

The large AST comparisons in `check_font_metrics.py` and
`check_font_row_geometry.py` compare immutable v163/v165/v173 snapshots, rather
than requiring the current `FontMetrics` definition to occupy the root file.
Leave those historical comparisons intact. Add or adapt a narrowly scoped
live-definition comparison for the extraction, allowing only the necessary
font-root adjustment. Do not treat the whole suite as needing AST rewrites.

Pillow/features/import patches target their backend modules or Python's import
mechanism and should continue to work. Verify this using the existing missing-
dependency, BASIC/HarfBuzz and variable-font checks. Add meaningful coverage for
an unrelated working directory, the unchanged fallback font root, imported
aliases and the installed engine.

### Distribution and updates

The Windows installer enumerates individual top-level scripts. Its managed-file
inventory, copy/staging logic and uninstall handling must include the package's
two source files and create their destination directory. Retain rollback and
unrelated-file protection. Backups currently use destination basenames; use
collision-safe identities if nested files are added. Remove only owned files
and empty owned directories; account for Python-generated package bytecode
without recursively deleting arbitrary user content.

The updater's `selected_file()` currently excludes `_simplify_ass/*.py`, and its
required-file check lists only top-level tools and maintenance/launcher files.
Extend both for the bounded package, preserving path validation, revision/blob
verification and syntax checks. The package must be included in the same staged
installation transaction as the engine. Old installed updaters cannot download
paths they do not select: upgrading a pre-extraction installation therefore
needs a documented bridge (updated updater first, or rerun the new installer).
Choose and test that migration before calling the extraction deployable.
For the first extraction, the simplest recommended migration is to rerun the
new installer against the existing target and preserve its launcher choices.
Document that requirement explicitly. If transparent old-updater migration is
required instead, handle its bootstrap as preparatory distribution work rather
than adding an import workaround to the engine.

The installer/updater tests build synthetic single-file checkouts and downloads;
extend those fixtures to contain the package. Verify clean installation,
upgrade, failed-update rollback and uninstall with unrelated files retained.
Do not change `simplify_subtitles.py` or its configuration/menu behavior.

### Validation provenance

`validation/measure_one.py`, `run_review_checks.py`, corpus runners and native
scene validators currently identify runtime code using the root engine's hash.
After extraction that is incomplete. For the checks used to accept this release,
record a deterministic manifest of relative paths and SHA-256 hashes for the
engine and its implementation package, and verify it before/after execution.
Retain the root hash for existing consumers and historical single-file reports.
Do not require rewriting every historical report or runner before extraction;
clearly distinguish a complete current manifest from a historical root hash.

Loading the engine by `spec_from_file_location()` in `measure_one.py` also needs
an explicit sibling-package search path independent of the working directory.
Preserve support for standalone historical engines. Run installed-tree probes
without the checkout on `PYTHONPATH`, so missing distributed files cannot be
masked by the development environment.

## Pre-extraction baseline

Fresh evidence is stored privately under
`validation/font-extraction-assessment/`; subtitle/font assets and generated
outputs are not part of the published assessment. The directory contains a
dependency inventory and an exact v212 source snapshot. A snapshot relocated
there has a different `__file__` font fallback and is evidence, not an equivalent
executable reference tree without further resource-path handling.

The fresh regression run and thirteen-track exact-font corpus run establish
the unchanged v212 implementation as the baseline for the future extraction.
Corpus results include output hashes, complete statistics, source hashes and a
font manifest. The older v210 comparison is historical context, not the parity
target: v211 fade handling and the v212 default intentionally differ from it.
Use the new v212 outputs/statistics for post-extraction comparisons.

Fresh baseline evidence:

- Thirteen exact-font corpus conversions completed with no reported missing
  families; all 132 font-manifest hashes and source/output hashes were verified.
  All thirteen outputs are byte-identical to the saved v211 outputs. Reporting
  differs only as expected from v212's disabled change budget: effective interval
  `2 -> 0`, and Kill la Kill's sixteen limited captions report `hold` rather than
  `both`, with the rate-limited count `16 -> 0`. The new v212 statistics, including
  these reporting fields, are the parity target.
- Installer checks: 22 passed, two native-Windows checks skipped. Updater checks:
  eight passed, one native-Windows check skipped. These verify today's standalone
  distribution, not the as-yet-unimplemented package migration.
- The MKV/font smoke check passed, including font extraction, simplification,
  remuxing and font-sync preview; source files were preserved.
- All 90 Windows-font-backend regression scripts passed, including the native
  libass render checks. Runtime and harness inputs remained unchanged throughout
  the run; the engine/input manifest and corpus/source/font hashes were
  reverified afterward.

Evidence files include `dependencies.json`, `assessment-inputs.json`,
`corpus/summary.json`, `regression-summary.json` and
`v211-baseline-verification.json` in the private
assessment directory. The exact engine SHA-256 is
`40cb8760e69be3f8917e8817fc2c4aef8ccc7f73d5646858b33b806720541e0f`.
The native CMD, NTFS Zone.Identifier and CMD self-update checks require an
actual Windows host; the Linux BASIC/HarfBuzz backend is not a substitute.

## Acceptance and after-extraction review

1. Compare extracted class implementations with the baseline, allowing only the
   import/resource wiring needed to move them. Confirm no reverse dependency.
2. Run font selection, measurement, row geometry and backend checks, including
   missing optional dependencies and immutable-source/cache contracts.
3. Run the full Windows-font-backend regression suite and compare all thirteen
   corpus outputs byte-for-byte with the fresh v212 baseline; require identical
   meaningful statistics and no missing fonts.
4. Exercise direct CLI/imported execution, native real-subtitle render probes,
   installation, old-to-new update migration, rollback and uninstall. Run actual
   Windows launcher/filesystem validation separately from Linux backend checks.
5. Inspect resulting imports and test adaptations. Confirm that ownership,
   cache lifetimes, fallback paths and optional dependency behavior are intact.

The extraction is complete only when the package is distributed correctly and
the comparisons pass. Select the next extraction afterward. Any need for
reverse imports, production compatibility shims, duplicated proofs or changed
reconstruction behavior warrants revisiting this boundary, not expanding the
first increment to absorb it.

Assessment evaluation: the measurement boundary is suitable. The concrete
follow-up work is test dispatch, nested-file distribution/update migration and
multi-file provenance within the extraction release. No broader processing
context, pipeline redesign or separate font-policy review is justified by this
assessment.
