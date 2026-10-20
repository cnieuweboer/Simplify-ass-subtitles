# Complete sliced-text sequence processing — v243

The boundary assessed in
[SLICED_TEXT_EXTRACTION_ASSESSMENT.md](SLICED_TEXT_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/sliced_text.py`. All sixteen functions and two
existing frozen records moved unchanged: 263 definition lines, including
decorators. Engine names remain direct aliases, preserving signatures, canonical
record identity and historical root pickle lookup. Runtime version:
`2026.10.20.243`. No behavior change is intended.

## Responsibility and ownership

The preparatory commit moves the six-line `rectangle_clip()` read unchanged into
caption geometry, with a direct engine alias. It reads borrowed resolved source
coordinates without parsing or caching an event, transforming geometry or deciding
ownership. Existing numeric syntax, positive extents and inverse/vector/malformed
clip behavior remain unchanged. Caption geometry imports the canonical `NUMBER`
pattern; existing position patterns and geometry definitions are unchanged.
Supporting drawings, panels, outline strips and progressive reveals continue to
use their existing engine alias without depending on sliced-text processing.

The new module owns the complete strip/hold/exit operation: family admission,
source profiling, held/strip/pulse indexes, complete strip coverage and anchor/paint
proof, caption reconstruction, proposal arbitration and authored-lyric timing.
Both complete strip phases are still required. Existing unanimous held paint,
matching pulse requirements, inline font handling and authored timing bounds are
unchanged. General fade synchronization and later row assembly remain separate.

Input events, defaults/styles, source evidence and measurement context remain
borrowed. Source resolution creates local successor events and formatting, with
local continuation replay and move/transform lists; it does not install a cache
on input events. Indexes, sorted peer lists, coverage groups, proposals, ownership
counts and timing successors belong to one invocation. Both frozen records retain
their intentional shallow sharing. The operation creates no FontMetrics instance,
resource owner, persistent cache or diagnostic owner. It uses the recorded canvas
and passes through existing measurement context; shared rendering retains paint
policy and serialization.

Competing ownership claims are rejected before application. Refusal returns the
original list. Accepted output preserves untouched event identity, sorts by
source index and counts actual removed list slots. The caller,
`remove_source_fragment_effects()`, retains source isolation, row evidence,
preceding fragment proofs, the backed-glyph pulse handoff, row adoption and the
`SourceFragmentRemoval` result. Its aggregate remains
`len(removed) + pulses + slices`; reporting and pipeline configuration are unchanged.

The module depends on eight existing private owners and the standard library.
The graph remains acyclic without engine imports, adapters or production
forwarding. Cold supported/refused processing loads neither the engine nor Pillow,
fontTools or HarfBuzz. No path-sensitive discovery moves. Interpreter observers
now include the defining sliced-text consumer; caller observers stay on the actual
engine invocation.

## Validation and delivery

Shared geometry coverage now checks the canonical rectangle alias, borrowed
immutable formatting, signed/fractional source coordinates and refusal classes.
The geometry suite and source-fragment ownership checks passed before extraction.

Eight new module tests cover canonical aliases/annotations/pickle lookup, local
profiles and independent indexes, shallow frozen records, cached and unresolved
input preservation, supported/pulsed sequences, timing/paint/pose/flags and
measurement retention, incomplete coverage, paint/canvas/ownership refusal,
authored timing, duplicate list-slot counting, caller ordering/accounting, and
cold source/installed execution. Installed children run from unrelated working
directories and a path with spaces without optional font backends. Owned uninstall
removes source and bytecode while preserving a user file.

Fresh v242/v243 comparisons cover 426 cases across 142 scenarios and three input
orders. Complete output, counts, original-list and retained-object identity
decisions match. Borrowed input/state identity remains unchanged; all repeated
results are stable with no further removal. Fourteen separate rectangular-clip
reads also match. Historical sliced-text builders supply variations without
reviving obsolete helper counts, single-file traces or historical paint policy.

Native libass probes cover complete, authored-timing, pulsed, incomplete and
competing sequences with the exact Arial regular face. Serialized output and
all 35 frame pairs match across entrance, active and exit boundaries. Authored
pose/timing, retained independent text and repeat behavior also match.

All thirteen corpus tracks retain identical output bytes and complete statistics,
with no required-font diagnostic. All 124 recorded font hashes were verified.
Final-source validation passed all 115 regression scripts using Windows BASIC
plus real HarfBuzz on Linux. The full 28-source runtime and test harness stayed
fixed throughout validation. All 19 moved definition ASTs are unchanged, as are
other root behavior, existing caption-geometry definitions and the 25 other prior
private sources. The production batch wrapper and delivery code remain unchanged
from v242.

The unchanged shipped v214 updater delivers v243 over v242 and rolls back when
either the new sliced-text module or the changed caption-geometry owner is locked,
then retries successfully. User files and launcher choices are preserved. Isolated
installed supported/refused/pulsed sequences, authored timing and unresolved
source processing remain font-free; owned uninstall passes. Recursive Python and
PowerShell runtime manifests agree. Installer checks pass 32 with two native
Windows skips; updater checks pass ten with one native Windows skip. MKV font
extraction, conversion, remux/extraction and font-sync smoke checks pass. Native
Windows filesystem and launcher behavior requires separate Windows testing.

Private evidence remains under ignored `validation/sliced-text-extraction/`.

## After-release evaluation

The complete operation has one owner, shared geometry is independently owned,
and source-fragment orchestration retains its existing responsibilities. No
adapter, duplicated proof, local production exception or downstream repair was
needed. No new dedicated follow-up review was identified.

The scrolling iterator contract and global API/index reviews remain separate;
Pillow compatibility was resolved in v241. Reassess the next boundary from the
resulting dependencies rather than prescribing a final module hierarchy here.
