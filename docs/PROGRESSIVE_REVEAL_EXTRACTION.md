# Complete progressive text-reveal processing — v244

The boundary assessed in
[PROGRESSIVE_REVEAL_EXTRACTION_ASSESSMENT.md](PROGRESSIVE_REVEAL_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/progressive_reveals.py`. Thirteen functions and three
existing frozen records moved unchanged: 246 definition lines including decorators.
The existing eleven-line frozen `TextVisibilityResult` has a neutral owner in
`_simplify_ass/text_visibility.py`, shared by reveals and full-lyric-copy cleanup.
Engine names remain direct aliases, preserving signatures, canonical identity and
historical root pickle lookup. Runtime version: `2026.10.21.244`.
No behavior change is intended.

## Responsibility and ownership

The reveal module owns eligible-family admission, literal-prefix and geometry
proof, increasing chains, finishing holds, complete temporal strip-band coverage,
representative foreground selection, opacity restoration and reconstruction over
covered intervals. Actual gaps, source-order ties, bounds and refusal conditions
remain unchanged. Shared rendering retains paint policy and serialization.

Events, visibility history, styles/defaults, evidence and measurement context are
borrowed. Formatting views, profiles, chains, coverage counters, interval buffers,
removals, replacements and sparse deltas belong to one call. The three reveal
records and shared result retain frozen bindings with intentional shallow sharing.
No font cache, handle, metrics instance or diagnostic owner moves.

The result remains a value contract: events, removal count and accepted visibility
assignments. Both independent producers construct the same class. Neither algorithm
owns the other's implementation. Other result records and full-copy matching stay
where they were; no hierarchy, adoption method or general visibility service is
introduced.

`_consolidate_text_events()` retains level-one gating, stage placement after owned
word echoes and before font decorations, event adoption and aggregate reporting.
It adopts visibility updates unconditionally before the next consumer: a zero
removal count can still accompany reconstructed captions when authored gaps are
preserved. Equal-value assignments and unrelated source history remain meaningful.
The later full-copy invocation and its adoption are unchanged.

Retained events preserve object identity. The no-family early return preserves
input-list identity; other refusals may return a fresh list containing original
objects. Failure after partial local work cannot mutate shared input events or
visibility. Do not equate zero removals with no work.

The operation depends on nine private owners and the standard library; the shared
result depends only on dataclasses and the canonical Event model. Imports remain
acyclic without engine imports, callbacks or production forwarding. Cold proofs
load neither the engine nor Pillow, fontTools or HarfBuzz. No path-sensitive code
moves. Test failure injection follows the defining producer module.

## Validation and delivery

Six new module tests cover canonical aliases, annotations and historical pickle
lookup; shared results from both producers and shallow frozen records; complete
and tiled reveals with representative translucent paint; timing, geometry, input
and untouched-event identity; incomplete-strip and rotated refusal; authored gaps
and zero-count deltas; the actual caller handoff; and cold source/installed
processing with owned uninstall from an unrelated path containing spaces.

Fresh v243/v244 comparisons cover 1,008 cases across 84 scenarios, three input
orders and four visibility-map modes. Complete output, counts, sparse deltas,
caller-adopted visibility, original-list/retained-object identity and repeated
pass decisions match. Borrowed input/state identity remains unchanged. Historical
fixture builders supply variations without historical paint substitutions or
obsolete single-file coverage requirements.

One existing direct-pass scenario gains further chain evidence on a second call.
This is unchanged; its complete conversion already settles in one run. This
extraction adds no pass-local fixed-point requirement.

Native libass comparisons cover complete, tiled, incomplete, gapped and translucent
reveals across active, gap and exit boundaries with the exact Arial regular face.
All forty frame pairs and serialized outputs match v243. Independent text, timing,
representative paint and repeat behavior are retained.

All 116 current regression scripts passed with Windows BASIC plus real HarfBuzz
on Linux. Thirteen strict-font corpus tracks retain identical output bytes and
complete statistics, with no missing required-font diagnostic. All 124 recorded
font hashes were verified. Full runtime and harness manifests stayed fixed during
validation. The zero-count handoff assertion also detects a deliberately omitted
caller update.

The unchanged shipped v214 updater delivers both new modules over v243. Locking
either module rolls back the complete update; retry succeeds without changing
user files or launcher choices. Installed cold supported/refused, tiled, gapped
and translucent reveals and owned uninstall pass. Recursive Python and PowerShell
manifests agree. Installer checks pass 32 with two native Windows skips; updater
checks pass ten with one native Windows skip. MKV extraction, conversion,
remux/extraction and font-sync smoke pass. Production wrapper, reporting and
delivery code are unchanged.

Fresh results remain under ignored `validation/progressive-reveal-extraction/`.
Native Windows filesystem and launcher behavior requires separate Windows testing.

## After-release evaluation

Reveal proof and reconstruction now have one owner. The existing shared result
has a neutral owner, while callers retain stage orchestration and visibility
adoption. No adapter, duplicated proof, local production exception or downstream
repair was needed. No new dedicated follow-up review was identified.

The scrolling iterator contract and global API/index reviews remain separate;
Pillow compatibility was resolved in v241. Choose the next boundary from the
resulting dependencies rather than prescribing a final module hierarchy.
