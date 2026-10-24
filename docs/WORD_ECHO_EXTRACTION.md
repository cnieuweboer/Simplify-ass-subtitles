# Source-owned word-echo cleanup — v263

Five existing functions, 151 definition lines, live in
`_simplify_ass/word_echoes.py`. Their names, signatures, defaults, annotations,
comments and bodies move unchanged. The engine retains direct aliases for all
five. The runtime version is `2026.10.24.263`.

## Boundary and dependencies

The operation consumes complete captions already accepted by complete-line
jitter processing. It groups original short word frames, proves a dense fade or
faint jitter family, and requires unique exact-font ownership by one retained
caption before removing the family atomically. Repeated words are disambiguated
by their authored position. Missing exact fonts, competing owners and incomplete
proof preserve the family. Accepted faint tails never extend the parent's cue.

Complete-line jitter retains caption admission, representative paint, geometry
and construction. The consolidation caller retains that producer's exact caption
tuple, original source-map selection, stage conditions, result adoption and
aggregate reporting. The word-echo module constructs no captions and changes no
retained paint, geometry, timing or evidence.

Dependencies are the existing event evaluation, caption geometry, static identity,
static geometry validation, literal fragment matching, exact-font glyph placement
and neutral row-result owners. No private module imports the engine; imports are
acyclic. No adapter, callback, new record, global context or global cache is added.
Existing automatic module delivery includes the new source without a filename
list. The CLI, wrapper, settings and reporting catalog do not change.

## Preserved ownership

| Resource | Responsibility |
| --- | --- |
| Inputs | Working Events, visible text, accepted caption objects, original sources, formatting, styles and supplied metrics remain borrowed. |
| Source resolution | Empty source formatting is evaluated into temporary successors. Caller caches and original Events remain untouched. |
| Local state | Owner buckets, nearby frame families, anchor caches, match lists and source removal IDs belong to one invocation. |
| Fonts | Existing glyph helpers borrow the supplied metrics. Measurement resources, font caches and diagnostics retain their existing owners. |
| Result | The unchanged frozen `CoveredFragmentRemoval` stays in `row_evidence`, shared with covered-fragment cleanup. Returned rows remain empty. Removal counts retain unique-source-ID semantics. |
| Identity and order | Early refusal returns the original working list. Otherwise the ordered result list borrows untouched Event objects; the exact accepted parent remains retained. |
| Pipeline | The caller retains jitter/echo sequencing, duration configuration, output adoption and contribution to `covered_fragments`. |

## Validation

The active word-echo check retains fade/jitter admission, exact-font refusal,
whole-family bounds, parent timing, repeated literals, competing owners,
unresolved source immutability, real-source reduction, parent paint/geometry and
byte-identical repeat conversion. Extraction checks additionally protect direct
aliases and annotations, canonical result ownership, read-only maps, retained
object identity, independent output containers, early-return list identity,
anchor-failure isolation and independent importing without the engine or optional
font backends. The check passes 106 assertions and removes 4,413 real source
frames while preserving all accepted captions and byte-identical repeat
conversion. Failure injection targets the defining module; pipeline spies
continue to observe the engine alias.

Fresh local evidence lives under `validation/word-echo-extraction/`. Its one-release
structure audit compares all five functions and the remaining engine algorithm
against v262, verifies unchanged existing private modules and wrapper, and checks
acyclic imports. Runtime manifests identify all 50 Python sources. Fonts,
fixtures, converted output and generated reports remain ignored local assets.

Fresh comparison regenerated all thirteen corpus tracks against the hash-bound
v262 baseline. Every output byte and complete statistics record is identical;
source bytes and exact fonts are unchanged, with no missing font families.
All 121 regression scripts passed, including native paint, pose, phase,
fade/handoff and caption/backdrop rendering checks. Complete runtime and harness
hashes stayed unchanged throughout the final run. `release-verification.json`
binds the structure audit, complete regression report and corpus comparison.
Validation uses Pillow BASIC plus real HarfBuzz on Linux, including native libass
rendering checks; it does not establish native Windows filesystem or PowerShell
behavior.

## After-release evaluation

The subsystem keeps family evidence, exact ownership proof and atomic removal
together. Its existing shared result already has a neutral owner, so no
preparatory migration or producer/consumer adapter is needed. No new workaround,
local matching exception, duplicated proof or dedicated behavioral follow-up
is introduced. Final suite and corpus results are recorded with the release.
