# Static paint normalization — v271

Three existing functions, 141 definition lines, live in
`_simplify_ass/paint_normalization.py`: `normalize_near_text_colors`,
`_bounded_text_color` and `normalize_shadow_lettering`. Names, signatures,
defaults, annotations, comments and bodies move unchanged. The engine retains
direct aliases for every name. Runtime: `2026.10.25.271`.

## Boundary and dependencies

The module owns static-paint normalization policy: bounded fill/outline palettes
choose an observed representative color, and narrowly admitted shadow lettering
transfers its actual paint/anchor into primary text. These remain separate
operations with their existing admission rules and call sites. Inline frame
paint and matched backing fades reuse the bounded palette rule; final output and
layer settling retain their existing normalizer calls.

Dependencies are existing override interpretation, static-span identity, caption
geometry, event replacement and tag rendering, plus the standard library. No
engine-local dependency remains. No preparation, adapter, callback, new context,
cache, record or policy change is required. Imports remain acyclic and no private
module imports the engine. Installer/update discovery includes the new source
automatically. Consumer extraction is left for reassessment after this release.

## Ownership and data flow

| Resource | Preserved responsibility |
| --- | --- |
| Inputs | Events, styles, defaults, formatting and supplied color votes remain borrowed. |
| Local state | Palette votes, blocked style/channels, representatives, parser continuations and serialization buffers belong to one invocation. |
| Color policy | The complete style/channel palette must fit the existing two-level bounds. No transitive clustering or generated representative color is introduced. Intentional wider gradients, unsafe transparency and drawing/animation guards retain their existing treatment. |
| Shadow transfer | The admitted single static span keeps actual shadow color, alpha and subpixel anchor. Ordinary shadows, outlined/multispan text and uncertain geometry retain their refusal behavior. |
| Results | Existing `(events, changed_count)` tuples preserve untouched Event identity, order and fresh output buffers. Edited Events use canonical replacement and its existing evidence invalidation. |
| Producers | Source/paint ownership, geometry matching, representative-pose selection and family admission keep their existing owners. |
| Callers | Evidence requirements, stage order, final cleanup and aggregate reporting remain at existing call sites. No font resource, persistent cache or diagnostic owner moves. |

The wrapper, CLI, configuration, thresholds and report catalog are unchanged.

## Validation

The existing color-normalization check now passes 76 assertions. Added boundary
coverage protects canonical aliases/annotations, historical root helper lookup,
borrowed votes/formatting, observed-color bounds, untouched Event identity and
independent result containers. Cold checkout and installed imports perform real
color and shadow normalization without loading the engine or optional font
backends. Delivery/removal is checked in a directory with spaces, preserving an
unrelated private file. Existing shadow-lettering, whole-span paint, current
paint-handoff and rendering checks retain behavioral coverage. Interpreter
observers follow the defining normalizer consumer without production forwarding;
inactive historical scope/helper-count audits are not reactivated.

Local release evidence lives in `validation/paint-normalization-extraction/`.
Its structure audit compares all three moved definitions and the remaining
engine against v270, checks all existing private sources and the wrapper
byte-for-byte, and verifies acyclic imports. Runtime manifests identify all 58
Python sources. Fixtures, fonts, outputs and generated reports remain ignored
local development assets.

All 121 regression scripts passed, including all 69 shadow-lettering checks and
native source-phase, paint, source-pose, fade/handoff, contour-order and
caption/backdrop rendering. Fresh comparison of all thirteen corpus tracks
against the hash-bound v270 baseline found every output byte and complete
statistics record identical. Exact fonts and source bytes are unchanged, with no
missing required font families. Runtime and test/harness hashes stayed unchanged
throughout validation. `release-verification.json` binds the structure audit,
full regression report and corpus comparison. Checks use Pillow BASIC plus real
HarfBuzz on Linux, including native libass; they do not establish native Windows
filesystem/PowerShell behavior.

## After-release evaluation

The extraction establishes a shared static-paint policy owner without moving
producer proofs or changing individual normalization rules. It adds no workaround,
duplicated proof or matching exception. No behavioral issue requiring a dedicated
follow-up review was uncovered.
