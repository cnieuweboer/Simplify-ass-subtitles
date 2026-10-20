# v233 — Frame-echo processing extraction

`_simplify_ass/frame_echoes.py` now owns the sixteen existing echo-processing
functions and five frozen records identified in the bounded assessment. All 21
names remain direct aliases in `simplify_ass.py`. The 277 definition lines moved
unchanged, including record decorators, signatures, thresholds and defaults.

## Responsibilities and dependencies

The owner performs one complete operation: admit corresponding frame-exit echoes,
prove either matching paint stacks or flattened copies following an opaque hold,
then construct and apply replacements. It retains candidate preparation,
recorded-source movement, temporal ambiguity, paint continuity and ordered
application together. General frame freezing and stacked-copy reconstruction
remain separate operations.

The engine's `_prepare_stacked_text_copies()` still chooses inputs, invokes echoes
before held-paint reduction/grouping and aggregates the returned contribution.
The private owner imports established override, event, geometry, source-effect
validation and caption-rendering primitives plus the standard library. No private
module imports the engine back; no adapter, duplicated proof or global context
was introduced. `simplify_subtitles.py`, installer/updater implementations and
CLI/reporting policy are unchanged.

Working events, original source maps, styles and measurement context remain
borrowed. The subsystem owns call-local grouping, frame timelines, position
buckets, profiles, ambiguity sets, removal IDs and replacement dictionaries.
Each family owns its positive/negative recorded-motion cache for stable frames
and source evidence. No such cache survives into another invocation.

Frozen record fields remain frozen while contained dictionaries, sets, lists and
event references retain their identities and mutability. Their defining module
changes naturally; direct aliases preserve historical root lookup without
metadata rewriting. Original source evidence remains distinct from working
frames, including missing-source refusal, lifetime bounds and move endpoint slack.

The preceding caption supplies representative paint/pose and row/lyric flags;
the frame sample supplies its lifetime and minimum contributing source ID.
Paint reconstruction and event-evidence invalidation retain their existing
owners. Retained events keep identity in a new output list in supplied order.
Application remains source-ID based, including duplicate-ID behavior; its count
remains removed IDs minus replacements rather than a new list-length definition.

## Validation

The historical `validation/check_frame_echo_extraction.py` audit verifies all
21 moved definitions against v232, unchanged remaining engine AST except the
import/version, and byte-identical existing private modules. This release audit
is excluded from the routine inventory and does not constrain future policies.

Eleven new current-policy module checks cover both proof paths/chains, complete
representative paint/pose/timing/flags, reordered input and retained identity,
long-frame motion proofs/refusals, source lifetime mismatches, nonuniform paint
or layout, incomplete stacks, flattened-hold ambiguity, contour animation,
positive/negative family caches, repeated calls and all five shallow frozen
records. They use a small fixture builder without historical production doubles.

The existing sixteen replacement-application comparisons retain every assertion,
including duplicate/unlisted IDs. Their indexing/collapse stubs now target the
function's defining module, also supporting the historical single-file reference.
No production forwarding was added for those stubs. The old stage-trace harness
remains historical; its broader proof-path coverage gap is addressed by the new
behavioral checks rather than restoring obsolete paint or call-order expectations.

Cold source and installed checks run from an unrelated directory with spaces in
the installation path, exercising both paths and source-backed long exits before
importing the engine or optional font backends. They verify canonical owner
identity and owned module/cache removal while preserving a user file.

Acceptance requires the full 108-script Windows BASIC plus real HarfBuzz suite on
Linux, including native rendering, and fresh paired v232/v233 conversions of all
13 corpus tracks with identical bytes and complete statistics. Required-font
guards and all 124 recorded font hashes protect exact-font prerequisites. Runtime
and harness manifests must stay unchanged throughout validation.

Delivery checks exercise the actual shipped v214 updater adding the module to a
v232 installation: a locked new owner must roll back exactly before a successful
retry. Installed echo proofs, preserved launcher choices/user files and owned
uninstall are checked. Recursive Python/PowerShell manifests, installer/updater
suites and the MKV extraction/conversion/remux/font-sync smoke workflow complete
Linux validation. Native Windows filesystem/launcher behavior remains a separate
limitation. Fresh logs and private outputs stay under ignored
`validation/frame-echo-extraction/`.

Completed validation against the final 21-source runtime: all 108 regression
scripts passed, including eleven new module checks, the sixteen retained
replacement-application comparisons and all native rendering checks. All 13 fresh
v232/v233 corpus pairs were byte-identical with identical complete statistics;
all 124 font hashes were verified with no missing required-font diagnostics.
Runtime and harness inputs stayed unchanged.

Installer checks passed 32 with two native Windows skips; updater checks passed
10 with one native Windows skip. Actual shipped-updater rollback/retry, installed
proofs/uninstall, Python/PowerShell manifest agreement and the MKV smoke test
passed. Native Windows filesystem and launcher behavior remains unverified on
this Linux host.

## After-release evaluation and follow-ups

The complete echo operation moved without a preparatory redesign, local runtime
exceptions, duplicate proofs or downstream repairs. The caller retains pipeline
placement, source selection and reporting. The identified observer binding and
behavioral coverage gap were addressed within this release.

A new boundary fixture exposed an existing numeric edge case in the unchanged
shared move validator: for a source from 2.0 to 2.4 seconds, subtraction produces
`0.3999999999999999`; adding the 50 ms endpoint allowance yields
`449.9999999999999` ms, so a 450 ms authored move endpoint is rejected. Both the
v232 baseline and v233 reproduce it. The accepted positive fixture stays one
millisecond inside the boundary; the undesired exact-boundary rejection is kept
as local bug evidence, not a desired regression expectation. A separate bounded
fix should tolerate arithmetic rounding without meaningfully widening authored
slack. No production tolerance changed during this structural extraction.

The numeric boundary follow-up is resolved in
[v234](EFFECT_ENDPOINT_ROUNDING.md); exact-boundary acceptance now has direct
validator and source-backed echo regression coverage.

The previously recorded scrolling single-use iterator issue and deferred global
API/pass-local index reviews also remain separate. These findings do not block the extraction; no source-proof tolerance or input
contract changed in this release.
