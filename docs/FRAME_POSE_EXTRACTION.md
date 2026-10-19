# v226 — Representative frame-pose extraction

Runtime version: `2026.10.19.226`.

Following the [bounded assessment](FRAME_POSE_EXTRACTION_ASSESSMENT.md),
`_simplify_ass/frame_pose.py` owns five unchanged functions:
`_frame_paint_alphas()`, `_frame_pose_intervals()`, `_visible_pose_support()`,
`_preserve_frame_pose_support()` and `_representative_frame_pose()`.
The engine retains direct aliases for all five. Matching, admission, paint,
geometry, timing and compositing policy are unchanged.

## Responsibilities and data flow

The module depends only on standard-library helpers, canonical `Event` and the
pose-validity key in `event_operations`. No reverse engine imports, adapters,
new records or shared context objects are needed. The canonical key stays with
replacement validation; it is neither moved nor duplicated.

Inputs remain borrowed. Source exposure is clipped to the surviving lifetime,
with existing microsecond rounding. Local endpoint counters accumulate maximum
opacity, so coincident copies cannot multiply dwell and gaps remain gaps.
Selection returns an existing candidate and immutable interval tuple using the
same exposure ranking and deterministic tie rules. It does not average geometry.

Support handoff admits only matching literal/layout identity, combines compatible
peers' deduplicated source intervals, and retains the successor's other evidence.
A mismatched successor is returned unchanged by identity. Event replacement
retains its own invalidation policy; extending output timing invents no dwell.

Callers still admit source families, choose evidence-capture boundaries, select
route-specific paint, render and install results, and aggregate diagnostics.
The frame freezer keeps `_frame_sequence_paint_owner()`. Its visible paint
selection remains independent of source-supported geometry. Inline reconstruction
retains its span-specific source-exposure proof. No persistent cache, font owner,
report or counter moved. `simplify_subtitles.py` and delivery code are unchanged.

## Validation

`validation/check_frame_pose_extraction.py` records this release's movement audit:
unchanged moved definitions, unchanged remaining engine AST except import/version,
and byte-identical pre-existing private modules. This historical audit does not
constrain future justified changes to the selection policy.

Eight module checks cover canonical aliases/types/key identity, actual visible
channels, source capture and clipping, empty support, rounding, maximum-opacity
aggregation, gaps, candidate identity, input immutability, duplicate/split/order
invariance, compatible evidence handoff and separate output paint selection.
Cold imports and processing require neither the engine nor optional font backends.
Installed processing runs from an unrelated directory with spaces in the install
path; owned removal deletes the module and its cache while retaining a user file.

Release acceptance requires the full 102-script Windows BASIC plus real HarfBuzz
suite on Linux, including native libass rendering checks; fresh v225/v226 pairs
for all 13 corpus tracks with byte-identical output and complete statistics;
and unchanged source/harness manifests. Corpus required-font guards stop rather
than accepting a missing exact face.

Delivery checks exercise recursive Python/PowerShell manifests and the actual
shipped v214 updater against a v225 install, with a simulated lock on the new
module, exact rollback, successful retry, preserved launcher choices and user
files, isolated installed policy use and owned uninstall. Native Windows-only
checks remain separately identified skips on this Linux host.

Fresh manifests, input hashes and logs live in the ignored local directory
`validation/frame-pose-extraction/`. The release verification report records
completed outcomes; subtitle fixtures, fonts and generated conversions remain
local assets.

Completed validation against the final 15-source runtime manifest: all 102
regression scripts passed, including the eight new module checks and native
rendering checks. All 13 fresh v225/v226 corpus pairs were byte-identical with
identical complete statistics; all 124 recorded font hashes were verified with
no required-font diagnostics. Installer checks passed 32 with two native Windows
skips; updater checks passed ten with one native Windows skip. Actual shipped
updater rollback/retry/uninstall, Python/PowerShell manifest parity and MKV/font
smoke checks passed. Runtime and harness hashes remained unchanged throughout
validation. Existing tests needed no observer corrections or substitutions.

## After-release evaluation

The extraction follows the assessed boundary without preparatory API changes,
adapters, duplicated proofs or local exceptions. Producers retain evidence
boundaries, callers retain family admission, and the module owns only source
exposure, pose selection and compatible support handoff. No newly exposed
ownership conflict requires a dedicated corrective review. Assess the next
boundary from the resulting graph; the global API and pass-local index reviews
remain separate work.
