# Event-based row fitting — v253

`recover_font_row()`, `recover_tracked_font_row()` and `fit_fullwidth_run()` now
live in `_simplify_ass/row_fitting.py`. Their complete definitions and signatures
moved unchanged. The existing mutable `FontProcessingReport` definition moved
unchanged into `_simplify_ass/font_reporting.py`. The engine retains direct
aliases for all four names, imported before dependent declarations. The version
is `2026.10.23.253`.

## Dependencies and ownership

Dependency direction is engine → row fitting → caption geometry, event model,
font measurements and the shared report record. Font reporting depends only on
the standard library. There are no engine imports, callbacks or forwarding
adapters. The stateless `glyph_placement.py` algorithms retain their existing
role; its module description now identifies the separate event-fitting owner.

Callers provide borrowed events, literal fragments, measurement resources and
an optional report. Fitting returns the existing geometry tuples or `None`.
Candidate fits, measured widths, prefixes and temporary event views remain
call-local. The zero-tracking views use the existing `dataclasses.replace()`
operation and preserve its shallow sharing; this is not an event replacement or
source-evidence invalidation. Rendering, timing, family admission, compositing
and edit application stay with producers.

Font discovery, exact-face selection and reusable measurement caches remain
with the supplied `FontMetrics`. No resource paths or `__file__` behavior move.
The caller still chooses report lifetime and may accumulate one report over a
batch or omit it. Missing-face findings from unsuccessful fits remain recorded;
completed diagnostics survive later conversion failures. The four accepted-join
counter writes remain at their reconstruction commit sites. Glyph-phase and
vector-outline missing-font reporting also retain their producer ownership.
The report's mutable fields and independent per-instance set are unchanged.

The report has a neutral home because consumers beyond row fitting use it.
Placing its definition there does not transfer ownership of run diagnostics to
the module. No new context, result hierarchy, cache or pipeline stage is added.
The production batch wrapper, CLI options and Windows reporting are unchanged.

## Validation

The existing geometry/reporting check also exercises canonical aliases,
resolvable event/measurement/report annotations, report pickle and legacy class
lookup, and independent imports without the engine or optional font backends.
Test doubles bind the engine aliases and defining event-fitting consumer;
production code has no test-observer forwarding.

Local evidence is retained under `validation/row-fitting-extraction/`, including
complete baseline/current runtime manifests, an unchanged-definition and
remaining-engine AST audit, focused results, full-suite results and the corpus
comparison. The runtime now comprises 37 Python sources. New module delivery
uses the existing dynamic installer/updater discovery contract.

Fresh final validation passed all 121 regression scripts, including the 4,936
geometry/reporting checks across 1,080 algorithm cases and the native libass
rendering checks. The full suite exercised Pillow BASIC plus real HarfBuzz on
Linux; it does not claim native Windows filesystem or PowerShell validation.
All runtime and covered test-harness hashes remained unchanged during the suite.

All 13 corpus outputs are byte-identical to the verified v252 outputs, with
identical complete statistics. Baseline/current manifests, source/output hashes
and exact font hashes were verified. No missing families were reported. The
wrapper is byte-identical to v252, and the installer/module delivery checks pass
with both new files. `final-regression-checks.json`, `corpus-summary.json` and
`release-verification.json` retain the fresh results.

## After-release evaluation

The extraction preserves fitting, diagnostics and caller responsibilities without
new policies, duplicated proofs or downstream exceptions. No new dedicated
behavioral follow-up is needed. Larger processing subsystems can now import
event-based fitting and shared diagnostics without reaching into the engine.
Existing unrelated second-conversion ambiguity remains outside this release.
