# Text-copy reduction — v270

Eight existing functions, 217 definition lines, live in
`_simplify_ass/text_copy_reduction.py`. Names, signatures, defaults, annotations,
comments and bodies move unchanged. The engine retains direct aliases for every
name. Runtime: `2026.10.25.270`.

## Boundary and dependencies

The closed call graph covers exact positioned duplicates, strict whole-lifetime
redundancy and early representative-paint selection for nonlyric signs. These
remain three distinct operations. Strict redundancy preserves complete literal
spans, paint, parser history, document context, timing coverage and compositing;
the early sign selector deliberately permits its existing paint/layer variation.
Pending lyrics retain their source/row handoff before final redundancy checks.

Dependencies are existing override interpretation, static-span identity and
caption geometry, plus standard-library helpers. No engine-local dependency
remains. No preparatory change, adapter, callback, new record or policy change is
required. Imports remain one-way and no private module imports the engine.
Installer/update discovery includes the new source automatically.

## Ownership and data flow

| Resource | Preserved responsibility |
| --- | --- |
| Inputs | Events, visibility maps, styles, formatting caches and document measurement context remain borrowed. |
| Local state | Interpreter continuations, opacity checks, seen maps, geometry/rank indexes, wrapping flags, retained anchors and removal sets belong to one invocation. |
| Evidence | Partial-alpha compositing, unpositioned collision placement, complete-span identity, intervening peers and whole-lifetime bounds retain their existing guards. Removed anchors cannot authorize cumulative spatial drift. |
| Results | Existing `(events, removed_count)` tuples preserve retained Event identity and original ordering. Exact/removal counts, source-ID sets and list-slot removal sets keep their distinct existing semantics. No Event replacement or timing extension is introduced. |
| Callers | Consolidation, final layout and final cleanup retain invocation order, lyric eligibility/handoffs and aggregate duplicate reporting. |
| Resources | No font resources, persistent caches, diagnostics, result records or report owner move into this module. |

Other source-family, glyph-copy and layered-paint proofs keep their established
owners. The wrapper, CLI, configuration and report catalog are unchanged.

## Validation

The existing collision-duplicate check now passes 40 assertions. Its boundary
coverage protects canonical aliases and annotations, historical root lookup,
borrowed Event identity/cache immutability, repeated calls, strict versus early
paint selection, pending lyrics and retained-anchor chains. Cold checkout and
installed imports perform actual reductions without loading the engine or
optional font backends. Delivery/removal is tested in a directory with spaces,
preserving an unrelated private file.

All 51,222 inline-continuation checks pass. Interpreter observers follow the
defining copy consumer without production forwarding. Existing translucent and
late-copy checks retain their semantic guards and full-pipeline coverage;
inactive historical scope/helper-count audits are not reactivated.

Local release evidence lives in `validation/text-copy-extraction/`. Its structure
audit compares all eight moved definitions and the remaining engine against v269,
checks all existing private sources and wrapper byte-for-byte, and verifies
acyclic imports. Runtime manifests identify all 57 Python sources. Fixtures,
fonts, outputs and generated reports remain ignored local assets.

All 121 regression scripts passed, including all 258 late-copy checks and their
18 full-pipeline reduction fixtures, plus native source-phase, paint, source-pose,
fade/handoff, contour-order and caption/backdrop rendering. Fresh comparison of
all thirteen corpus tracks against the hash-bound v269 baseline found every output
byte and complete statistics record identical. Exact fonts and source bytes are
unchanged, with no missing required font families. Runtime and test/harness hashes
stayed unchanged throughout validation. `release-verification.json` binds the
structure audit, full regression report and corpus comparison. Checks use Pillow
BASIC plus real HarfBuzz on Linux, including native libass; they do not establish
native Windows filesystem/PowerShell behavior.

## After-release evaluation

The extraction preserves separate copy proofs and stage roles while giving their
existing shared opacity/containment checks one owner. It adds no workaround,
duplicated proof or matching exception. No behavioral issue requiring a dedicated
follow-up review was uncovered.
