# Merged-caption rendering — v252

`render_caption_spans()` and `render_merged_caption()` now live in the existing
`_simplify_ass/caption_rendering.py` owner. Their complete definitions and
signatures moved unchanged; `simplify_ass.py` retains direct aliases. The engine
version is `2026.10.23.252`.

The first helper maps selected formatting onto recovered literal characters.
It preserves exact correspondence or the caller's whitespace-insensitive row
mapping, and replays emitted overrides with their continuation so border and
shadow base tags reset their axes correctly. The second serializes an already
proved row using the existing animated/static paint policy, optional original
paint spans, recovered placement and explicit tracking/no-wrap output.

## Dependencies and ownership

Dependency direction is engine → caption rendering → event model/interpreter.
The added dependencies are canonical `Event` annotations and existing override
interpretation functions. Independent import needs neither the engine nor
optional font backends. No paths, discovery rules or delivery files change.

Callers retain source-family admission, row fitting, recovered text, geometry,
timing, paint-family ownership, compositing proofs and event edits. The renderer
borrows those inputs and returns the same string or refusal (`None`). Its local
formatting and serialization buffers remain local; there are no new caches,
diagnostics, counters, contexts or result records. Existing event/cache reads
retain their established ownership. The batch wrapper is unchanged.

The interpreter test observer now includes the defining rendering consumer.
This preserves trace coverage without production forwarding. The existing span
check also verifies canonical aliases, resolvable event annotations and import
without optional font packages.

## Validation

Local evidence is kept under `validation/merged-caption-rendering-extraction/`.
`structure-checks.json` verifies identical moved function ASTs, the unchanged
remaining executable engine AST apart from imports/version, and the unchanged
batch wrapper. Complete runtime manifests identify all 35 Python sources.

Fresh validation passed all 121 regression scripts with the Windows font backend
(Pillow BASIC plus real HarfBuzz on Linux), including native libass checks. The
span check passes 29 assertions and inline continuation passes 51,222 checks.
Runtime and harness hashes remained unchanged throughout the completed suite.
This does not claim native Windows filesystem or PowerShell validation.

All 13 full-track corpus conversions are byte-identical to the verified v251
outputs, with identical statistics and unchanged exact fonts. Source/output
hashes and complete baseline/current runtime manifests bind the comparison.
`final-regression-checks.json`, `corpus-summary.json` and
`release-verification.json` retain the fresh evidence. No changed examples
required an additional rendering investigation.

## After-release evaluation

The extraction extends an established rendering owner without changing proof
responsibilities or introducing adapters, duplicated policies or engine imports.
No new behavioral follow-up is required. Event-based row fitting and its shared
diagnostics remain a separate future boundary; the previously documented
inter-family barrier-removal/second-call ambiguity is unaffected.
