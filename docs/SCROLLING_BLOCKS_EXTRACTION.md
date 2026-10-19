# v231 — Residual scrolling-block extraction

`_simplify_ass/scrolling_blocks.py` now owns the existing nine scrolling-track,
profile, block-matching and removal functions plus `ScrollingBlockMatch`.
All ten names remain direct aliases in `simplify_ass.py`. This is a structural
extraction: signatures, thresholds, ordering and behavior are unchanged.

## Responsibilities and dependencies

The private module imports the existing override interpreter, caption geometry,
event model, resolved-state comparison, font measurement type and document peak
counter. Dependencies remain one-way; no private module imports the engine.
No context, callback adapter, global cache or extra pipeline pass was introduced.

Events, styles, source evidence and continuations remain borrowed. The supplied
measurement owner retains its caches and diagnostics. Local frame groups,
nearest-neighbor buffers, tracks, profiles, common intervals, confirmed indices,
removal sets and report dictionaries last for one call. Retained output events
are the original objects, in input order, in a new list. `ScrollingBlockMatch`
still holds profile indices and a common proof interval; its fields are frozen
but its borrowed `indices` list remains mutable. Its defining module changes
naturally, while historical root pickle lookup remains available through the alias.

The edge proof still makes a local `dataclasses.replace` view, borrowing the
continuation while flattening perspective for the existing conservative measured
bounds check. It does not install evidence or change source geometry. Unknown
bounds cannot establish edge travel. Spatially distinct voters remain separate
from coincident paint copies, and three voters must agree over a shared interval.

The optional policy still compares each confirmed block's unique remaining
source-event peak against its own limit. Unrelated captions and total frame count
cannot trigger removal. The default is 32; removal requires a strictly greater
peak. Zero disables removal while retaining block detection and reporting.
Negative limits are rejected before reading input. Movement, angles and frame
timing remain intact; this extraction introduces no static scrolling replacement.

`_limit_scrolling_text()` remains in the engine. It owns the late residual-stage
invocation, script resolution lookup, configuration and aggregate counters.
`_faded_cue_is_scrolling()` remains with its distinct source-admission proof.
CLI/reporting and `simplify_subtitles.py` remain unchanged.

## Validation

The historical `validation/check_scrolling_blocks_extraction.py` audit compares
all ten definitions against the v230 runtime, including the dataclass decorator.
It checks that the remaining engine AST changes only by import/version and that
all existing private modules are byte-identical. This release audit is excluded
from the routine inventory and does not constrain future implementations.

Seven new module checks cover canonical aliases and annotations, historical root
pickle lookup, shallow freezing, track construction, strict cap and zero semantics,
borrowed event/measurement ownership, unknown-bound refusal, spatial voters,
unrelated captions, call-local buffers and negative validation. Cold source and
installed checks work from an unrelated directory with spaces in the installation
path, without optional font backends. They exercise actual scrolling recognition
and removal, then verify owned module/cache cleanup preserves a user file.
Existing scrolling behavior and real-font/rendering checks remain unchanged.

Acceptance uses the full 106-script Windows BASIC plus real HarfBuzz suite on
Linux and fresh paired conversions of all 13 corpus tracks against v230. Output
bytes and complete statistics must match, with all 124 recorded font hashes
verified and no missing required-font diagnostics. Runtime and harness manifests
must stay unchanged during validation.

Delivery checks cover the actual shipped v214 updater adding the new module to a
v230 installation, failure rollback when its write is locked, successful retry,
isolated installed processing, preserved launcher choices/user files and owned
uninstall. Recursive Python and PowerShell manifests must agree. Installer/updater
suites and the extraction/conversion/remux/font-sync MKV smoke test complete the
prepared Linux validation; native Windows filesystem/launcher checks remain
explicit skips. Fresh artifacts stay local under the ignored directory
`validation/scrolling-blocks-extraction/`.

Completed validation against the final 19-source runtime: all 106 regression
scripts passed, including all seven new module checks and the native rendering
checks. All 13 fresh v230/v231 corpus pairs were byte-identical with identical
complete statistics; all 124 font hashes were verified without missing required
fonts. Runtime and harness inputs stayed unchanged. Installer checks passed 32
with two native Windows skips; updater checks passed 10 with one native Windows
skip. Actual shipped-updater rollback/retry, installed processing/uninstall,
Python/PowerShell manifest agreement and the MKV smoke test passed. Native Windows
filesystem and launcher behavior remains unverified on this Linux host.

## Follow-up evaluation

The assessed boundary moved without preparatory changes, adapters, duplicated
proofs, late repairs or changes to unrelated subsystems. There is one known,
pre-existing issue reserved for a dedicated follow-up: a single-use iterator is
consumed while building tracks and then read again for output filtering, so it
can lose retained events even with removal disabled. Production supplies lists
and is unaffected. This release preserves that behavior rather than mixing a
contract change into extraction. A separate change should decide whether to
materialize all iterables once or explicitly require/reject non-reiterable input.
The exhausted-output behavior is bug evidence, not an intended regression oracle.
