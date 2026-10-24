# Text-effect sequence processing — v260

Complete text-effect sequence processing lives in
`_simplify_ass/text_effect_sequences.py`: fourteen functions and the existing
frozen `TextEffectSequenceContext`, `TextEffectSequenceGeometry` and
`TextEffectSequenceProfile` records, about 417 definition lines. Shared
`LyricBoundaryIndex` and its two helpers live in `_simplify_ass/lyric_boundaries.py`,
another 79 definition lines. All twenty definitions moved unchanged, including
signatures, defaults, fields, decorators and bodies. The engine retains direct
aliases for every moved name. Its version is `2026.10.24.260`.

## Boundary and preparation

The processing module keeps exact-position and scale-trail sequence reduction
together: candidate grouping, per-bucket geometry, connected components, source
admission, readable candidates, representative pose and sustained paint, caption
construction and final movement/karaoke/exact-position handoffs. Existing clipping,
real-gap, authored-margin, complete-family and lyric-boundary protections remain
unchanged. The representative pose and paint policies retain their existing owners.

The small shared-boundary extraction is included in the same release. Glyph
coalescing, frame/vector merging and sequence processing already consume this
evidence. Its neutral owner builds and reads surrounding-row signatures without
owning caption reconstruction. The engine still captures the index before glyph
reduction. The same supplied index survives subsequent joins and recursive
sequence processing; standalone callers retain their existing fallback capture.
No consumer borrows a reconstructed lifetime as new original boundary evidence.

One complete processing module and one shared proof owner reduce unrelated
engine code while keeping the sequence algorithm's cooperating stages together.
The helper interface is already sufficient; no preparatory policy redesign or
separate release is required. Both modules are internal to this engine rather
than shared between top-level subtitle tools.

Dependencies point from the engine to these owners and existing event, geometry,
override/freezing, pose/paint selection, rendering, movement and karaoke modules.
The shared boundary owner needs only Event, raw position reads and the standard
library. Imports are acyclic and no private module imports the engine. No adapters,
callbacks, new contexts or result hierarchies are introduced. Independent importing
needs neither the engine nor optional font backends.

## Preserved ownership and handoffs

| Resource | Responsibility |
| --- | --- |
| Working events and source inputs | Events, visibility, styles, animation IDs and original source maps remain borrowed. Resolved source hold probes do not populate borrowed caches. |
| Boundary signatures | Construction creates fresh maps/sets. The frozen record retains shallow sharing; consumers borrow the supplied index unchanged. The engine chooses its capture point and evidence lifetime. |
| Geometry and profiles | Position/height/layout dictionaries remain bucket-local. Components, anchors, visible candidates, profiles and output buffers remain local to a processing call. |
| Measurement resources | The supplied metrics object retains font/shaping caches and resource ownership. No font discovery or measurement policy moves into sequence processing. |
| Diagnostics | The caller retains the supplied report and its lifetime. Existing recursive forwarding remains unchanged; no new report writes, counters or rollback rules are added. |
| Results | Existing list/count returns, untouched Event identity, source-index sorting and removed-member counts are unchanged. The engine retains adoption and aggregate statistics. |

Both exact-position recursive invocations retain their existing absence of font
metrics. The scale route still performs initial exact consolidation, sequence
proof/reconstruction, movement recovery, karaoke normalization and final exact
consolidation in the same order. Original source maps, reports and boundary
evidence retain their existing forwarding contracts. Movement and karaoke remain
distinct algorithms with their existing owners.

`_consolidate_text_events()` retains level gating, boundary capture, glyph
coalescing, frame merging, the sequence invocation and aggregate reporting.
Other boundary consumers keep their original call sites. Every remaining engine
definition and executable statement is unchanged apart from imports and version.
No CLI, batch-wrapper, resource-path or report-catalog change is required.
Installer/updater discovery includes both private modules automatically.

## Validation

The active source-caption alternation check retains real-font reconstruction,
gradient paint, next-cue timing, repeat conversion and different fragmentation
coverage. Added assertions protect canonical aliases, resolved annotations,
frozen/shallow record contracts, caller-owned metrics/reports and independent
imports. Both recursion routes must retain the exact supplied boundary object;
an attempted recapture fails the check. The expanded check passes 168 assertions.

The active moving-glyph module check targets the defining sequence consumer for
its caller handoff. It checks movement, karaoke and exact-pass order, aggregate
counts, source/metric identity, report/boundary identity and exact-pass metric
omission. It also exercises source/installed processing, automatic module delivery
and ownership-preserving uninstall. Interpreter observers follow the defining
sequence consumer. Production has no forwarding for test spies.

The focused freeze-consumer check passed 16,704 assertions, including 428 sequence
cases. Historical helper-count/call-trace audits remain historical rather than
constraining this boundary. One-release AST evidence verifies all twenty unchanged
definitions and the remaining engine algorithm. Every existing private source
and `simplify_subtitles.py` remains byte-identical to v259. Fresh manifests cover
all 47 runtime Python sources; local evidence lives under
`validation/text-sequence-extraction/`.

Fresh full-track comparison regenerated all thirteen tracks against the v259
baseline bound by its saved release-verification record. Every output is
byte-identical and every complete statistics record matches. Original baseline
metadata is retained. Required exact fonts and source bytes are unchanged, with
no missing font families. The fresh corpus runtime manifest covers the complete
47-source implementation.

All 121 regression scripts passed, including native libass rendering. The
expanded source-caption check passed 168 assertions, and its native companion
passed 80 native source-phase/lyric-handoff checks. Runtime and covered harness
hashes stayed unchanged throughout the complete run. `structure-checks.json`,
`final-regression-checks.json`, `corpus-summary.json` and
`release-verification.json` retain the fresh evidence.

Required validation uses the Windows font backend (Pillow BASIC plus real HarfBuzz)
on Linux, including native libass rendering. This does not claim native Windows
filesystem or PowerShell validation. Source fixtures and fonts remain ignored
development assets.

## After-release evaluation

The boundary keeps complete sequence processing and its recursive handoffs
together. Shared lyric-boundary evidence has a neutral owner, while capture timing,
pipeline adoption and aggregate reporting remain with the engine. No workaround,
duplicated proof, local exception or new dedicated behavioral review was needed.
Previously documented unrelated issues remain outside this structural release.
