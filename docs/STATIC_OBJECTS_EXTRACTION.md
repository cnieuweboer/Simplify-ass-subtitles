# v227 — Static-object matching and phase-merging extraction

Runtime version: `2026.10.19.227`.

Following the [bounded assessment](STATIC_OBJECTS_EXTRACTION_ASSESSMENT.md),
`_simplify_ass/static_objects.py` owns the unchanged frozen `StaticSpanSignature`
record and four functions: `geometry_key()`, `static_object_key()`,
`_merge_static_phase_round()` and `merge_static_timed_copies()`.
Direct engine aliases preserve existing callers. Matching, paint, geometry,
timing, compositing and source-evidence policy are unchanged.

## Responsibilities and data flow

The module depends on standard-library helpers and existing private interpreter,
event, geometry, measurement, replacement and source-support owners. No reverse
engine imports, forwarding adapters, new contexts or result hierarchies were
introduced. The record keeps its fields, frozen status, continuation type and
equality/hash behavior. Its defining module changes naturally; old root-name
lookup still resolves through the engine alias, including pickle lookup.

Static identity parses into fresh local formatting buffers and borrows document
styles and events. It preserves exact literal/paint/layout, continuation, vector
payload/clip identity, metadata and measurement context. Other vector consumers
retain the same `geometry_key()` primitive. General resolved-state and placement
fingerprints remain with their existing owners.

The merger retains local grouping, slot indexes, overlap membership, bounds cache,
replacement maps and removal sets. Supplied metrics keep their reusable font
caches and diagnostics. The algorithm uses actual list slots and each displaced
phase's lifetime, retaining pending-row protection and conservative unknown
bounds. It preserves gaps, overlapping multiplicity and intentional paint changes.
Its fixed point repeats only this same merging proof.

Timing successors retain borrowed caches/history and the established source
evidence policy. Compatible pose support is aggregated at completed-run emission;
contour/opaque-span proofs are not extended. Existing support handoff can create
successors even when the removal count is zero; no new identity guarantee is
introduced. Source inputs remain unchanged.

Both pipeline invocation points, row eligibility, evidence boundaries, support
ownership and `static_merged` reporting remain caller-owned. No configuration or
counter changed. `simplify_subtitles.py` and delivery code are unchanged.

## Associated test update

The existing `patch_interpreter_bindings()` helper now includes
`static_object_key` in its dynamically resolved consumer list. This observes
interpreter calls in the new owner while retaining historical single-file
handling. No trace assertions were weakened, paint policies substituted or
production adapters added.

## Validation

`validation/check_static_objects_extraction.py` records this release's movement
audit: identical moved definitions including the frozen decorator, unchanged
remaining engine AST except import/version, and byte-identical pre-existing
private modules. This historical audit does not constrain future justified
policy changes.

Nine focused module checks cover canonical aliases/types and pickle lookup,
frozen signatures, continuation-sensitive spans, vector identity, static
admission, borrowed caches and inputs, source support, gap/overlap/paint refusal,
actual slots, row roles, numeric layers, malformed peers, supplied measurements
and bounds-cache lifetime. Cold and installed processing run from unrelated
directories without optional font backends; installed paths include spaces.
Owned removal deletes the module and its cache while retaining a user file.

Release acceptance requires the full 103-script Windows BASIC plus real HarfBuzz
suite on Linux, including native libass checks; fresh paired v226/v227 conversions
for all 13 corpus tracks with identical bytes and complete statistics; and
unchanged runtime/harness manifests. Required-font guards stop conversions rather
than accepting a missing exact face.

Delivery checks exercise recursive Python/PowerShell manifests and the actual
shipped v214 updater against a v226 installation, including a simulated locked
new module, exact rollback, successful retry, preserved launcher choices/user
files, isolated installed merging/pickle identity and owned uninstall. Native
Windows-only checks remain separately identified skips on this Linux host.

Fresh manifests, input hashes and logs live locally in the ignored directory
`validation/static-objects-extraction/`. The release verification report records
completed results. Subtitle fixtures, fonts and generated conversions remain
local development assets.

Completed validation against the final 16-source runtime manifest: all 103
regression scripts passed, including all nine new module checks, the full
51,222-check inline continuation trace comparison and native rendering checks.
All 13 fresh v226/v227 corpus pairs were byte-identical with identical complete
statistics; all 124 recorded font hashes were verified with no required-font
diagnostics. Installer checks passed 32 with two native Windows skips; updater
checks passed ten with one native Windows skip. Actual shipped-updater
rollback/retry/uninstall, Python/PowerShell manifest parity and MKV/font smoke
checks passed. Runtime and harness hashes remained unchanged throughout validation.
No additional observer corrections or expectation changes were required.

## After-release evaluation

The extraction follows the assessed boundary without preparatory production
changes, duplicated proofs or local exceptions. The bounded tracer-owner update
is the associated change identified in the assessment. Both stages still share
one merger with explicit caller-owned roles; caches and source proofs retain
their existing lifetimes. No broader corrective review is indicated. Global API
and pass-local index reviews remain separate work.
