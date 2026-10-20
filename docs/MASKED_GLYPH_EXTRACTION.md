# Masked-glyph processing — v237

The complete operation assessed in
[MASKED_GLYPH_EXTRACTION_ASSESSMENT.md](MASKED_GLYPH_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/masked_glyphs.py`: eighteen functions and four
existing frozen records, totaling 425 definition lines. All 22 definition ASTs
are unchanged. Engine names remain direct aliases; signatures/defaults, shallow
record freezing and historical root pickle lookup are preserved. The runtime
version is `2026.10.20.237`.

## Responsibility and ownership

The module owns masked-text indexing, literal-copy and exact-font contour proofs,
texture/shadow ownership, readable glyph successor construction and ordered
removal/replacement application. Fragmented-font stamps, caption/background
recovery, general drawing reduction and other passes retain their separate owners.

Events, visibility, animation evidence and metrics remain borrowed. Geometry,
placement/layout caches, per-face/glyph outline results and negative entries,
shadow carriers and temporary proof/replacement buffers remain pass-local.
Opened fonts retain the v236 handoff: local ownership until glyph-set initialization
and registration succeed, then pass ownership with `finally` cleanup. Initialization
failures, interruptions, later proof errors and a later glyph's recovery retain
their existing behavior. No persistent cache, diagnostic owner or resource
abstraction is introduced.

Unchanged events retain identity; replacement glyphs remain new successors. The
result is the existing `(events, removed_count)` tuple, preserving original list
order and confirmed source-ID counting. `_consolidate_text_events()` still invokes
this pass after fragmented-font decoration removal and before stacked-text
flattening, and retains configuration, source selection and `masked_decorations`
report aggregation. The later `font_textures_removed` counter is separate.

The module depends only on six established private owners and standard-library
services. FontTools pen imports remain lazy inside exact outline loading. The
import graph is acyclic and has no reverse engine import or callback adapter.
Font discovery remains with `font_metrics`; no path-sensitive code moves.

## Test ownership and validation

The existing masked-glyph check resolves its defining module for helper tracing,
AST coverage and injected proof failures. Its pipeline conversion observers still
patch the engine entry alias, the actual caller binding. Assertions remain
unchanged; no production forwarding supports test spies.

Eight new module tests cover canonical aliases/annotations/pickle lookup, shallow
record identity, independent caches, real supported and refused masks, preserved
paint/geometry/timing/flags, borrowed input/cache immutability, source-ID counts,
original list order, retained/replacement identities and repeated invocation.
The generated rectangular font and independently authored mask require no user
font substitution. A reconstruction-fallback paint assertion was checked against
frozen v236; both versions retain the same fill and white two-unit contour.
No paint-policy adjustment was needed.

Cold source and installed children run from an unrelated directory with spaces
in the installation path. Font-independent text-copy proof runs before engine or
optional font-backend imports. Exact-font mask proof then uses the generated face,
checks borrowed inputs and visible successors, and confirms inert repeated
simplification. Owned uninstall removes source/compiled cache and preserves a
user file.

Acceptance uses the full 110-script Windows BASIC plus real HarfBuzz suite on
Linux and fresh paired v236/v237 conversions of all 13 corpus tracks with identical
bytes and complete statistics. Required-font guards and 124 recorded font hashes
protect corpus prerequisites; complete runtime and harness manifests must stay
fixed during validation. Existing 686 masked-glyph comparisons, nine resource
lifecycle cases, two focused conversions and all 17 internal helper observations
remain active.

Three additional supported/refused exact-font examples have byte-identical
v236/v237 pass output and twelve pixel-identical native libass frame pairs,
including visible holds and start/end boundaries. The shipped updater passes
locked-new-owner rollback/retry, preserved choices/user files, isolated installed
mask processing and owned uninstall. Recursive Python/PowerShell manifests and
MKV extraction/conversion/remux/font-sync smoke checks complete delivery coverage.

All 13 fresh v236/v237 corpus pairs are byte-identical with identical complete
statistics. All 124 recorded font hashes were verified, with no missing
required-font diagnostics. Installer checks passed 32 with two native Windows
skips; updater checks passed ten with one native Windows skip.

Completed final-source validation against the complete 23-source runtime: all
110 regression scripts passed, including eight new module-boundary tests, all
686 retained masked-glyph comparisons, nine resource lifecycle cases, two focused
conversions and every native rendering check. Runtime and harness inputs stayed
unchanged throughout the run. All 22 moved definition ASTs are unchanged, all other
root behavior is unchanged, and all 21 existing private modules remain byte-identical.
The production batch wrapper and delivery code also remain unchanged from v236.

Private reports and outputs remain under ignored
`validation/masked-glyph-extraction/`. Native Windows filesystem/launcher
behavior requires separate Windows validation.

## After-release evaluation

The complete operation moved with its existing data flow, proof/cache ownership
and resource lifetime intact. No preparatory production release, workaround,
local runtime exception, duplicated proof or downstream repair was needed.
Defining-owner test observations were updated within the extraction. No new
dedicated follow-up was identified. The previously recorded scrolling single-use
iterator contract remains independent work.
