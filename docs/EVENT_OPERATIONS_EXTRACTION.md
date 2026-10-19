# v225 — Event operations extraction

Runtime version: `2026.10.19.225`.

Following the [bounded assessment](EVENT_OPERATIONS_EXTRACTION_ASSESSMENT.md),
`_simplify_ass/event_operations.py` owns three unchanged functions:
`event_evaluation()`, `replace_event()` and `_frame_pose_key()`. The engine retains
direct aliases for all three. No matching, reconstruction, paint, timing or
source-evidence policy changed.

## Boundary and ownership

The module depends on the existing override interpreter, passive event records,
inline-layout helper and standard-library dataclass replacement. Dependencies
remain one-way. There are no reverse engine imports, callback adapters, new
context objects or new result types.

Resolved reads borrow event state and continuation. Unresolved reads perform a
fresh complete parse without installing a cache or seeding it from stale history.
Text/style edits resolve and parse their replacement completely. Explicit state
edits retain history unless replaced; clearing state clears its continuation.

Replacement preserves its existing selective evidence invalidation. Paint-only
edits may retain source frame exposure when literal/layout identity agrees;
other historical contour/visibility proofs still expire. Explicit caller evidence
remains authoritative. Timing/layer changes preserve existing sharing without
extending or inventing source exposure. The canonical pose key retains its
numeric precision, measurement context and inline-layout distinctions.

Callers still own cache installation, source-family proof admission, exposure
production/clipping, representative-pose selection, pipeline transitions and
diagnostics. The event records remain passive. No document/font cache moved.
`simplify_subtitles.py` and installer/updater implementation are unchanged.

## Validation

The release-specific audit in `validation/check_event_operations_extraction.py`
compares against the saved v224 engine. It checks unchanged moved definitions,
unchanged remaining engine AST except imports/version, and byte-identical
pre-existing private modules. This historical movement audit is evidence for
this release, not a restriction on future justified policy changes.

Eight module checks exercise canonical identity/types, borrowed and fresh reads,
complete replacement parsing, history clearing, timing-only sharing, selective
proof retention, geometry/context invalidation and explicit proof authority.
They also import and process events cold without the engine or optional font
backends, then verify canonical aliases. Installed checks run from an unrelated
directory with spaces in the install path and verify owned removal of both the
module and its generated cache while retaining a user file.

Release acceptance requires the full 101-script suite with Windows BASIC and
real HarfBuzz on Linux, including native libass rendering checks; fresh v224/v225
conversion pairs for all 13 corpus tracks with exact output/statistics parity;
and recursive Python/PowerShell manifest and installed delivery checks.
Required-font guards stop corpus conversions rather than accepting substitution.
Fonts, subtitle fixtures and generated evidence remain ignored local assets.

The actual shipped v214 updater is exercised against a v224 installation,
including a simulated locked new module, exact rollback, successful retry,
preserved launcher choices/user files, isolated installed operations and owned
uninstall. Native Windows filesystem/launcher checks remain separately identified
skips on this Linux host.

Fresh logs, complete runtime manifests, input hashes and summarized results are
stored locally in `validation/event-operations-extraction/`. The release
verification report records the completed outcomes.

Completed validation against the final 14-source runtime manifest: all 101
regression scripts passed, including all eight new module checks and native
rendering checks. All 13 fresh v224/v225 corpus pairs were byte-identical with
identical complete statistics; all 124 font hashes were verified with no required
font diagnostics. Installer checks passed 32 with two native Windows skips;
updater checks passed ten with one native Windows skip. Actual shipped-updater
rollback/retry/uninstall, PowerShell manifest parity and MKV/font smoke checks
passed. Runtime and harness hashes remained unchanged throughout the final run.

## After-release evaluation

This extraction uses the assessed boundary without preparatory API changes,
adapters, duplicated proofs or downstream exceptions. No newly exposed ownership
conflict requires a dedicated corrective review. The high-fanout edit dependency
is now available to future processing modules; assess the next subsystem from
the resulting graph. The broader API and pass-local index reviews remain
separate work.
