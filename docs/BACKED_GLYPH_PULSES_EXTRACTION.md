# Backed-glyph pulse processing — v240

The boundary assessed in
[BACKED_GLYPH_PULSES_EXTRACTION_ASSESSMENT.md](BACKED_GLYPH_PULSES_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/backed_glyph_pulses.py`. All eighteen functions and
two existing frozen records moved unchanged: 410 definition lines, including
decorators. Engine names remain direct aliases, preserving signatures, defaults,
record identity and historical root pickle lookup. Runtime version:
`2026.10.20.240`. No behavior change is intended.

## Responsibility and ownership

The module owns the complete backed-glyph pulse operation: admission, backing
indexes, common held-pose selection, foreground coverage, returning transform and
frame proofs, complete exits, representative paint, proposal arbitration and
ordered application. It reconstructs glyph events; later row assembly still
owns spacing and complete-line reconstruction.

The caller, `remove_source_fragment_effects()`, retains source isolation, row
evidence, pipeline position, the subsequent sliced-text pass and aggregate
reporting. Its count remains `len(removed) + pulses + slices`. Pulse removal
continues to count actual original-list slots rather than distinct objects.
Untouched event identity/order and original-list returns on refusal are preserved.

Events, maps, cached formatting, continuations and supplied metrics remain
borrowed. Uncached reads use the existing event evaluator without installing
formatting on input events. Eligibility indexes, resolved-detail maps, replayed
destinations, pose buckets, proposals and replacement buffers remain pass-local.
The existing frozen records intentionally retain shallow sharing of mutable
containers. Calls do not share newly created buffers.

Shared paint sampling stays in its v239 owner; caption rendering retains
serialization and paint policy, and FontMetrics retains font discovery, resource
and measurement caches. This operation retains the evidence authorizing sampling
and reconstruction, including its existing fallback when metrics or paint are
unavailable. No diagnostics, persistent cache or result hierarchy was added.

All nine private dependencies point to existing owners. The graph remains
acyclic without engine imports, adapters or production forwarding. Cold imports
and supported/refused font-free proofs do not load optional font backends.
No path-sensitive discovery moves. The interpreter-observation test helper now
includes the actual defining consumer.

## Validation and delivery

Eight module tests cover canonical aliases, annotations and pickle lookup,
shallow record sharing, borrowed state, independent buffers, supported and refused
rows, exact-metric paint and optional-metric fallback, arbitration, duplicate
list-slot counts, caller ordering/reporting and isolated installed execution.
They use the exact corpus Volkhov regular face when measurement is required.
Cold children also exercise supported/refused proofs before loading font
backends, from unrelated working directories and installation paths with spaces.
Owned uninstall removes source and bytecode while preserving user files/fonts.

Fresh v239/v240 comparisons cover 186 cases across 62 scenarios in three input
orders, preserving complete output, counts, input state and identity decisions.
Repeat conversion is inert. Additional native libass probes cover complete,
incomplete and competing rows with the exact Volkhov face: output bytes and all
15 frame pairs match across start, active and end boundaries. Existing backing,
source-fragment, paint and continuation integration checks remain active.

The unchanged shipped v214 updater delivers v240 over v239, rolls back a locked
new module, retries successfully, preserves launcher choices/user files, and
passes isolated installed proofs, exact-paint checks and owned uninstall.
Python and PowerShell recursive manifests agree. Installer checks pass 32 with
two native Windows skips; updater checks pass ten with one native Windows skip.
MKV extraction, simplification, remux/extraction and font-sync smoke checks pass.
Native Windows filesystem and launcher behavior still requires Windows testing.

Final-source validation passed all 113 regression scripts using Windows BASIC
plus real HarfBuzz on Linux. All thirteen fresh v239/v240 corpus pairs have identical output bytes and
complete statistics, with no required-font diagnostic. All 124 recorded font
hashes were verified. The full 26-source runtime and test harness stayed fixed
during validation. All twenty moved definition ASTs are unchanged; other root
behavior is unchanged apart from aliases/imports/version, and all 24 prior
private sources remain byte-identical. The production batch wrapper and delivery
code remain unchanged from v239. Private reports remain under ignored
`validation/backed-glyph-pulses-extraction/`.

## After-release evaluation

The complete operation now has one owner while its caller and shared services
retain their responsibilities. No preparatory production change, duplicated
proof, adapter, local exception or downstream repair was needed. No new item
requires a dedicated follow-up review.

The previously recorded Pillow `Image.getdata()` compatibility work, scrolling
iterator contract and global API/index reviews remain separate. This extraction
does not prescribe the remaining module hierarchy.
