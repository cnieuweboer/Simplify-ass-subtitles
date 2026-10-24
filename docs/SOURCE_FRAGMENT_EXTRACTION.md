# Source-fragment effect proof and removal — v264

Fourteen existing functions and four existing frozen records, 516 definition
lines, live in `_simplify_ass/source_fragments.py`. Their names, signatures,
defaults, annotations, comments and bodies move unchanged. The engine retains
direct aliases for every moved name. Its version is `2026.10.24.264`.

## Boundary and shared owners

The subsystem uses original text, positions, rows and visibility evidence to
prove redundant layered highlights, translucent particles and repeated glyph
flashes before freezing. It returns retained events, confirmed row successors
and paint-family evidence for reconstruction. Complete or uniquely owned source
families retain their existing proofs; ambiguous content remains intact.

The entry point retains its original isolation of unresolved Events and its
backed-glyph-pulse then sliced-text handoffs. Those two processors retain their
existing private owners. `_prepare_source_text()` retains source collection,
pre-collapse timing capture, row/timeline adoption, reconstruction sequencing and
aggregate reporting. No stage moves or policy changes are introduced.

Two unchanged shared readers receive existing neutral owners in this release:

- `static_text_paint_geometry()` belongs to `static_objects`. It reads canonical
  static spans, preserving continuation-sensitive state and coalescing only
  boundaries differing in caller-selected paint. Other paint, row and timeline
  producers retain their admission/selection rules.
- `_index_source_fragment_visibility()` belongs to `row_evidence`. It groups
  existing source paint rows by opaque-span evidence, preserving row references
  and order. An absent profile falls back to the row interval; an empty profile
  remains empty. Effect removal and caption-paint timelines keep their distinct
  coverage and phase-selection policies.

These small owner moves fit in the extraction release. No adapter, callback,
record consolidation, context abstraction or mutable global cache is needed.
Imports remain acyclic, and no private module imports the engine. Existing
module delivery discovers the new source; CLI, wrapper and report catalogs do
not change.

## Preserved ownership

| Resource | Responsibility |
| --- | --- |
| Inputs | Working source Events, rows, word/position maps, animation evidence, metrics and the optional font report remain borrowed. |
| Private resolution | Each unresolved authored object receives one private successor, reused across the event list, base, pieces, paint rows and foreground. Resolved Events retain identity. Caller formatting caches remain unchanged. |
| Local proof state | Candidate indexes, per-row syllable caches, geometry/visibility evidence, proposals and removal IDs belong to the call or row. Existing frozen records keep their shallow mutable buffers. |
| Shared readers | Geometry uses temporary state dictionaries; visibility groups own new outer containers while borrowing paint rows. Neither reader selects source paint, removes content or edits input evidence. |
| Results | Existing `SourceFragmentRemoval` retains events, independently writable row containers, the removal count and paint-family rows. Historical geometry, timing, visibility and removed paint remain available as evidence. |
| Fonts and diagnostics | Existing fitting helpers borrow the metrics and caller-selected report. Font resources, measurement caches and selective diagnostic writes retain their existing owners. |
| Pipeline | The caller retains configuration, timing snapshots, output/row adoption, paint timeline construction and aggregate reporting. |

## Validation

The active ownership check retains resolved/unresolved input immutability,
consistent successor rebinding, independent nested row containers, historical
proof preservation, reconstruction adoption and failure isolation. Added boundary
checks cover all canonical aliases and annotations, historical record lookup,
shared reader identity, read-only maps, caller-selected reporting, local syllable
caches, frozen bindings and independent importing/empty processing without the
engine or optional font backends. It passes 71 assertions.

Backed-pulse and sliced-text handoff spies and failure injection follow the
source-fragment defining consumer. Interpreter observers and exact-fit doubles
also follow that consumer. Pipeline spies continue to target the engine alias;
there is no production forwarding for test instrumentation. Historical inactive
helper-count audits are not reactivated.

Fresh local evidence lives under `validation/source-fragment-extraction/`.
Its one-release structure audit compares all twenty moved definitions and the
remaining engine algorithm against v263, verifies the existing private algorithms
and untouched wrapper, and checks acyclic imports. Runtime manifests identify all
51 Python sources. Fonts, fixtures, converted output and generated reports remain
ignored local development assets.

Fresh comparison regenerated all thirteen corpus tracks against the hash-bound
v263 baseline. Every output byte and complete statistics record is identical;
source bytes and exact fonts are unchanged, with no missing font families.
All 121 regression scripts passed, including native source-phase, paint, pose,
fade/handoff and caption/backdrop rendering. Complete runtime and harness hashes
stayed unchanged throughout the final run. `release-verification.json` binds the
structure audit, complete regression report and corpus comparison. Validation
uses Pillow BASIC plus real HarfBuzz on Linux, including native libass rendering;
it does not establish native Windows filesystem or PowerShell behavior.

## After-release evaluation

The module keeps source-family proof, private resolution and result construction
together. Its shared readers retain neutral owners and leave policy with producers.
No workaround, local matching exception, duplicated proof or new diagnostic/cache
owner is introduced. No behavioral issue requiring a dedicated follow-up review
was uncovered. Final validation results are recorded with the release.
