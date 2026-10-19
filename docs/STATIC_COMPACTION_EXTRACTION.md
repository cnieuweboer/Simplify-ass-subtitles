# v228 — Static override compaction extraction

Runtime version: `2026.10.19.228`.

Following the [bounded assessment](STATIC_COMPACTION_EXTRACTION_ASSESSMENT.md),
`_simplify_ass/static_compaction.py` owns the unchanged
`_finished_static_key()`, `_join_finished_static_headers()` and
`compact_static_overrides()` functions. Direct engine aliases preserve existing
callers. Both early and final serialization modes move together; all seven calls
in the four engine consumers retain their stage positions and arguments.

## Responsibilities and data flow

The module depends only on the standard library and existing private owners for
override interpretation, event records/replacement, complete static-span
identity, unrotated-state recognition and text freezing. No module imports the
engine, and no forwarding adapters, new contexts, dataclasses or result
hierarchies were introduced. Font measurements, pipeline configuration and report
records remain with their existing owners.

Events, defaults, style catalogs, measurement context and source evidence remain
borrowed. Output lists and parsing/serialization buffers stay call-local. Early
compaction retains its blur/outline policy, unrotated-origin removal and ordinary
replacement invalidation. Compatible source-pose support can survive through
event operations, while historical contour and opaque-span proofs expire.
Final mode retains finished blur and origins, accepts only shorter complete-span
equivalent candidates, and explicitly preserves evidence after that proof.

Literal spans, drawing payloads, gradients, resets, parser continuation, metadata,
timing, multiplicity and list order retain their established behavior. Unknown
syntax, live effects and unsupported final candidates remain protected.
Callers still choose serialization/evidence boundaries and own reporting.
`simplify_subtitles.py`, installer/updater implementations and CLI settings are
unchanged.

## Associated test changes

`patch_interpreter_bindings()` now discovers the compaction consumer alongside
its existing owners. The inline-continuation check uses this same helper for its
`simplify_visual_text` stub, so historical single-file and current private-module
engines exercise the same isolated operation. Expected traces and assertions are
unchanged. The final pipeline-handoff spy remains on the caller's engine alias.

Seven new module checks cover canonical aliases/types and old root pickle
lookup; final evidence retention versus early invalidation; borrowed input and
cache immutability; origins/blur in both modes; complete gradients, drawings,
resets and continuation; refusal of unknown syntax/live effects; comments, list
order and repeated final compaction. Cold and installed execution run from an
unrelated directory without optional font backends. Installed paths contain
spaces; owned uninstall removes the module/cache while retaining a user file.

## Validation

`validation/check_static_compaction_extraction.py` records this release's exact
movement audit: identical moved definitions, unchanged remaining engine AST
except import/version, and byte-identical pre-existing private modules. This
historical audit is excluded from the routine inventory and does not constrain
future justified changes.

Acceptance requires the full 104-script Windows BASIC plus real HarfBuzz suite
on Linux, including native libass checks; fresh paired v227/v228 conversions of
all 13 corpus tracks with identical bytes and complete statistics; required-font
guards and unchanged runtime/harness manifests throughout validation.

Delivery validation covers recursive Python/PowerShell manifests and the actual
shipped v214 updater against a v227 installation, including a simulated locked
new module, exact rollback, successful retry, preserved launcher choices/user
files, isolated installed compaction and owned uninstall. Native Windows-only
checks remain distinct skips on this Linux host.

Fresh source/input hashes, reports and logs are local to the ignored directory
`validation/static-compaction-extraction/`. Fixtures, fonts and generated
conversions remain local assets.

Completed validation against the final 17-source runtime manifest: all 104
regression scripts passed, including the seven new module checks, the unchanged
51,222-check inline trace comparison and 191 final-compaction checks with 13
pixel-identical render pairs. All 13 fresh v227/v228 corpus pairs were
byte-identical with identical complete statistics. All 124 font hashes were
verified, with no missing required fonts. Runtime and test inputs stayed unchanged
through the run.

Installer checks passed 32 with two native Windows skips; updater checks passed
10 with one native Windows skip. Actual shipped-updater rollback/retry, isolated
installed processing/uninstall, Python/PowerShell manifest agreement and the MKV
extraction/simplification/remux/font-sync smoke test all passed. Native Windows
filesystem and launcher behavior remains unverified on this Linux host.

## After-release evaluation

Both modes retain one owner with explicit caller-selected evidence boundaries.
No production workaround, duplicate proof, downstream repair or unrelated
subsystem change was needed. The two planned observer/stub binding adjustments
are confined to testing. No dedicated corrective review is currently indicated;
the broader API and pass-local index reviews remain separate.
