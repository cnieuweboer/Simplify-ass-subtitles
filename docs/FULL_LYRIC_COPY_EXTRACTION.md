# Complete full-lyric-copy cleanup — v247

`collapse_full_lyric_copies()` now lives in
`_simplify_ass/full_lyric_copies.py`, with a direct engine alias. The complete
58-line definition moved unchanged. Runtime version: `2026.10.22.247`.
No matching, paint, timing, visibility, evidence or reporting change is intended.

## Boundary and ownership

The operation owns normalized-literal grouping, overlap clustering, representative
caption/paint selection, interval union, source-pose support and sparse visibility
assignments. It borrows resolved working events, visibility history, style/default
catalogs and measurement context. Groups, removal IDs, replacements and the pending
ChainMap overlay stay local to one invocation. Pending accepted text remains visible
to later clusters without mutating or copying the caller's historical map.

Keep accepted equal-value assignments, source-ID counting, original output ordering
and untouched Event identity. The existing frozen `TextVisibilityResult` remains
in `text_visibility.py`; no type or field moved. Result payloads retain their
intentional shallow sharing. Refusal retains Event identity but does not promise
input-list identity. Font caches, measurement policy and diagnostics keep their
existing owners; this module introduces none.

`_consolidate_text_events()` retains level-one gating, stage order, output/count
adoption and unconditional visibility-delta application before frame merging.
Earlier matching lyric layers, progressive reveals and later row reconstruction
remain distinct owners. Selection, source-paint rendering, canonical replacement
and frame-pose support retain their existing policies and modules.

All eight outgoing dependencies already have private owners: event records,
caption geometry, static selection, caption rendering, event operations, frame
pose, subtitle documents and the shared visibility result. The graph is acyclic,
without engine imports, callbacks or production forwarding. No path-sensitive
code moves. No preparation was necessary: v244 already established the shared
result boundary. The production wrapper and delivery code are unchanged.

## Validation

Seven new module checks protect the canonical alias/result type and historical
lookup; representative text, paint, geometry and timing; borrowed state/history;
pending and equal-value visibility updates; refusal identity; original pose
intervals and obsolete-coverage expiry; the real caller's visibility handoff; and
cold source/installed execution with owned uninstall. Supported processing works
without importing the engine or optional font backends.

The existing selector observer now patches the defining full-copy consumer. Its
assertions remain intact. Existing 864 historical comparisons and 53 visibility-
ownership assertions pass, including lookup-only history and failure isolation.
Those historical checks remain distinct from fresh current-policy comparisons.

Fresh v246/v247 comparisons cover 1,728 direct cases: 72 scenarios, three input
orders, four visibility-map modes and mutable/read-only maps. Complete results,
selector calls, sparse updates, untouched identity and repeat decisions match.
Both focused whole conversions retain identical output hashes, complete statistics
and font reports under current paint/timing policy, without historical substitutions.

All 119 current regression scripts pass on Linux using Pillow BASIC plus real
HarfBuzz. Runtime and harness manifests remain fixed throughout the run. All
thirteen strict-font corpus tracks retain identical output bytes and complete
statistics; all 124 recorded font hashes are verified, with no missing required
fonts. Native libass compares 66 identical frame pairs with exact Arial across
complete, chained, independent-position, separated-time, source-pose and borderless
families, including timing boundaries and independent text. The six native families
also settle on a repeated direct call; this is not a general idempotence claim.

The unchanged recursive installer/updater discover the module without a filename
list. The shipped v214 updater is exercised from a v246 installation, including
rollback on a locked new module or engine alias file, retry, preserved launcher
choices/user files, cold installed processing and owned uninstall. Python and
PowerShell manifests agree on all 34 runtime sources. Installer tests pass 32 with
two native Windows skips; updater tests pass ten with one native Windows skip.
The MKV extraction/simplification/remux/font-sync smoke check passes with sources
preserved. Native Windows filesystem/launcher behavior remains unverified here.

Fresh reports, generated files and the pinned v246 runtime remain ignored under
`validation/full-lyric-copy-extraction/`.

## After-release evaluation

One module owns the complete operation, and its caller retains ordering, adoption
and reporting. No adapters, local exceptions, duplicated proofs or ownership changes
were needed.

A dedicated overlap-cluster timing review is warranted by fresh synthetic evidence,
identical in v246 and v247:

- In a three-copy chain, input lifetimes `[1,4]`, `[1.5,4.5]` and `[2,5]`
  can produce only `[1.5,5]`, losing the first 500 ms. The retained source is
  reused by a later cluster, whose replacement overwrites the previously
  accumulated union using original event timing.
- **32 of 1,728 direct variants** allow one additional merge on a second call.
  This includes valid-duration crossing families, not just zero-duration cases.
  A separate three-caption example with complete visibility reproduces it.

Neither observation is caused by extraction. The complete first/repeated results,
case names and two minimal three-copy reproductions are retained in the direct
reports and `followup.json`. Before changing matching, review accumulated caption
bounds/source support and whether later cleanup already settles repeated-merge
families. Do not introduce blind iteration or broaden removal authority merely to
force idempotence. These examples establish a producer-level timing issue; they do
not establish a new whole-file corpus regression. Broader API/index and scrolling-
iterator reviews remain separate.
