# Caption geometry extraction — v224

Explicit caption anchors and conservative measured bounds now live in
`_simplify_ass/caption_geometry.py`. This implements the
[bounded assessment](CAPTION_GEOMETRY_EXTRACTION_ASSESSMENT.md). The engine
version is `2026.10.19.224`; position and footprint behavior are unchanged.

## Boundary and dependencies

The module contains the existing `NUM`, compiled `POS_RE`, `get_pos()`,
`set_pos()`, `inline_layout_key()` and `caption_bounds()`. Their assignments and
function definitions moved unchanged. The engine imports direct aliases before
dependent uses, retaining one canonical position pattern and the existing public
entry points. No forwarding functions, new models or callback adapters were added.

Dependency direction is engine → caption geometry → interpreter/event model/
font metrics. Other imports are standard-library `math`/`re`. Independent import
loads neither the engine nor optional font packages and creates no metrics
service. No helper uses paths or `__file__`; font discovery remains with the
existing metrics owner. Existing private module sources are byte-identical.
The batch wrapper, installer and updater sources are unchanged.

The module measures supplied events. Callers still choose source or reconstructed
formatting and decide containment, redundancy, compositing, source-span extents,
scrolling edge evidence, replacement and reporting. Nominal height, state/layout
fingerprints, vector tokenization, row grouping and effect-specific proofs remain
with their existing owners. Geometry did not become a general utility collection.

## Preserved ownership and behavior

- Text/state/context are borrowed read-only. Anchor reading and the inline guard
  do not resolve or install event caches. `set_pos()` returns a string without
  editing an event, preserving first-match replacement, insertion, two-decimal
  formatting and the `None` identity return.
- The engine retains direct uses of `NUM` and `POS_RE`, including high-precision
  glyph-anchor rewriting. The separate interpreter `NUMBER` pattern and the
  high-precision rewrite were not consolidated into the two-decimal setter.
- The inline guard retains the original complete syntax when a later header
  separates literal spans, including paint-only headers. No new span proof or
  relaxed admission policy was introduced.
- Callers supply the metrics instance. Face lookup, shaping and ink measurement
  use that owner's API and caches. Geometry creates no font cache/report, accesses
  no backend internals and retains silent `None` results for uncertain bounds.
- Bounds retain wrapping/context, alignment, exact face/glyph admission, advance
  and ink measurements, spacing/scales, authored stroke/shadow extents, overhang
  clearance, transforms and finite-result checks. The helper imposes no global
  outline cap and does not select representative paint.
- Shadow-painted text retains the existing local position/copied-state adjustment,
  without mutating the source or counting the shadow offset twice as padding.
- Adjacency mode retains its bounded near-front-facing estimate and clearance.
  Callers still distinguish proximity from full coverage proofs. Unsupported
  clips, drawings, inline layout and projective geometry remain unknown.
- Results remain four-coordinate tuples or `None`. Context-local bounds caches,
  source-evidence lifetime, event replacement and counters/diagnostics remain
  caller-owned. No persistent cache or diagnostic owner moved into this module.

## Tests and delivery

The new `check_caption_geometry_module.py` covers canonical aliases/types/patterns,
position replacement/insertion/precision, inline and uncertain bounds, borrowed
inputs and supplied measurements, shadow offsets, adjacency distinctions and
cold processing without optional font backends. A deterministic metric double
isolates contracts; existing exact-font/native checks cover real ink.

The installed-use check creates an exact synthetic font in the installed tools'
sibling `fonts` directory, imports from an unrelated working directory and
measures a resolved caption through the installed module and real metrics owner.
It verifies source immutability and canonical aliases, then removes owned source/
bytecode while preserving a user file. No existing test assertions, observers or
source bindings needed alteration.

The generic delivery contract discovers the new module without a filename-list
change. A private probe installs the exact v223 runtime and upgrades it through
the actual shipped v214 updater using pinned mock GitHub tree/blob responses.
It verifies complete rollback when the new module cannot be installed, successful
retry, preserved launcher choices/user files, installed aliases, position editing
and borrowed-input measurement, then uninstall. It does not claim a live network
update or native Windows execution.

`validation/check_caption_geometry_extraction.py` audits this release against
the exact v223 baseline. The six moved definitions and remaining executable engine
AST match except import/version; existing private sources are unchanged. This
historical audit must not constrain future justified geometry or processing work.

## Validation

All **100 regression scripts passed**, including native libass rendering.
Complete runtime and test/harness hashes remained unchanged throughout the run.
The continuation check retained all **634,286 assertions**. No existing test
assertions or observer bindings changed.

All **13 fresh v223/v224 corpus pairs have byte-identical output and identical
complete statistics**. All **124 supplied font-file hashes** were verified;
neither conversion set reported a missing required font.

All seven new module checks passed, including installed exact-font measurement
and owned source/bytecode removal. Installer checks: **32 passed, two native
Windows checks skipped**. Updater checks: **10 passed, one native Windows check
skipped**. Shipped-updater rollback/retry/uninstall and MKV/font smoke checks
passed. Python and PowerShell agree on all **thirteen runtime source hashes**.

Fresh evidence is private under `validation/caption-geometry-extraction/`:
baseline/runtime manifests, `corpus-inputs.json`, fresh baseline/current corpus
summaries, `audit.json`, regression/delivery/smoke logs and
`release-verification.json`. Corpus drivers stop on a missing required-font report.
Source, font, output, runtime and test/harness hashes are verified. Fixtures,
fonts and generated outputs remain ignored local assets.

Run from the repository root:

```sh
python validation/check_caption_geometry_extraction.py
python validation/run_backend_check.py --backend windows tests/check_caption_geometry_module.py
python validation/run_review_checks.py
```

Linux checks use Pillow BASIC with real HarfBuzz and native libass rendering.
Native Windows CMD/NTFS/self-update checks require Windows; platform skips remain
separate from passes.

## After-release evaluation

Caption measurement is now independently located while font owners, pass contexts
and processing producers retain their caches, proofs and reporting. Position
precision and uncertainty distinctions remain explicit. No reverse import,
production adapter, duplicated proof, local exception or new cache owner was
introduced; existing test observers remain at their actual call sites.

No dedicated corrective follow-up review is needed. Choose the next extraction
from the resulting dependency graph; the deferred global API and pass-local
index reviews remain separate work.
