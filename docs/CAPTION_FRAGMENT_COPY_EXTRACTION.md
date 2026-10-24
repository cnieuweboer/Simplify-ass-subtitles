# Caption fragment-copy processing — v265

Six existing functions and three existing frozen records, 553 definition lines,
live in `_simplify_ass/caption_fragment_copies.py`. Names, signatures, defaults,
annotations, comments and bodies move unchanged. The engine retains direct
aliases for every moved name. The runtime version is `2026.10.24.265`.

## Boundary and dependencies

The subsystem proves redundant glyph/word copies against retained text. It
matches nested glyph copies, near-coextensive complete rows and paired authored
entrance/exit rows. It also proves complete fragment ownership around a full-line
scaffold and renders that caption's foreground paint through the existing caption
renderer. Missing, extra, multiply owned or otherwise uncertain copies retain
their established refusal behavior.

The module borrows working events, visibility, optional original sources and
optional exact-font metrics. Dependencies are the existing event operations,
static identity/geometry, literal interpretation, exact glyph placement and
caption rendering owners. It introduces no adapter, callback, context abstraction,
record consolidation, global cache or new diagnostic/resource owner. Imports are
acyclic and no private module imports the engine. No preparatory migration is
needed. Existing installation/update discovery includes the new module.

Whole-caption copy-family consolidation retains its own owner. Caption rendering
keeps its paint policy. `_consolidate_text_events()` retains invocation order,
source and timing-map adoption, row handoffs, reconstruction and reporting. The
CLI, wrapper, configuration and report catalogs do not change.

## Preserved ownership

| Resource | Responsibility |
| --- | --- |
| Inputs | Working/source Events, visibility, styles and metrics remain borrowed. Existing resolved caches are reused without copying. |
| Private source views | One successor is created per evaluated unresolved source object. Source-map aliases share it; unrelated Events with the same source ID remain distinct. Sources are not populated in place. |
| Local proof state | Family/timing indexes, collision sets, proposals, column representatives, removal IDs and replacement maps belong to one invocation. |
| Proof and results | Existing `AuthoredLyricRowsResult`, `FullLineCopyProof` and `FullLineCopyResult` keep their fields, frozen bindings and shallow sharing. New row models carry borrowed event evidence; retained events keep original order and identity except accepted replacements/private source views. |
| Source deltas | Evaluated source updates remain meaningful with zero removals. The entry point rebinds exact working aliases; the caller adopts source/timing-map deltas before later readers. No source-ID-only rebinding is introduced. |
| Captions | Retained authored text, timing and geometry remain authoritative. Scaffold foreground selection uses the unchanged ownership proof and existing renderer. Canonical event replacement keeps its existing evidence invalidation. |
| Fonts and reporting | Metrics retains exact fonts, measurement caches and resource lifetimes. The module creates no report object or counter owner; callers retain aggregate reporting. |

## Validation

The active authored ownership check retains its historical contract comparison,
read-only maps, rejected borrowed-Event writes, source-cache aliases, scaffold
paint, failure isolation and pipeline source/timing adoption. Extraction checks
also protect canonical aliases/annotations, historical record lookup, meaningful
zero-removal deltas, exact source successors, independent per-call views/results,
historical evidence identity, frozen result bindings and independent importing
without the engine or optional font backends. It passes 7,039 assertions across
740 cases and five focused conversions.

Measurement-effect checks cover authored and exact-font staggered placement;
current paint-handoff checks exercise live paint policy. Interpreter observers,
exact-fit doubles, proof/render spies and failure injection follow the defining
consumer. Pipeline observers continue to target the engine alias. Production has
no forwarding for test instrumentation, and historical inactive helper-count
audits are not reactivated.

Fresh local evidence lives under `validation/caption-fragment-extraction/`.
Its one-release structure audit compares all nine moved definitions and the
remaining engine algorithm against v264, verifies byte-identical existing private
sources and wrapper, and checks acyclic imports. Runtime manifests identify all
52 Python sources. Fonts, fixtures, converted output and generated reports remain
ignored local development assets.

Fresh comparison regenerated all thirteen corpus tracks against the hash-bound
v264 baseline. Every output byte and complete statistics record is identical;
source bytes and exact fonts are unchanged, with no missing font families.
All 121 regression scripts passed, including native source-phase, paint, pose,
fade/handoff and caption/backdrop rendering. Complete runtime and harness hashes
stayed unchanged throughout the final run. `release-verification.json` binds the
structure audit, complete regression report and corpus comparison. Validation
uses Pillow BASIC plus real HarfBuzz on Linux, including native libass rendering;
it does not establish native Windows filesystem or PowerShell behavior.

## After-release evaluation

The boundary keeps caption/fragment ownership proof and application together,
with explicit source/row updates preserving existing data flow. No workaround,
local matching exception, duplicated proof, adapter or new resource/diagnostic
owner is introduced. No behavioral issue requiring a dedicated follow-up review
was uncovered. Final validation outcomes are recorded with the release.
