# Preserve accepted full-copy timing — v248

Runtime `2026.10.22.248` fixes accumulated timing and source-pose handoff in
`collapse_full_lyric_copies()`. A family with lifetimes `[1,4]`, `[1.5,4.5]`
and `[2,5]` could lose its first 500 ms when a later cluster overwrote an earlier
replacement. The equivalent reversed-time case could lose its end. The family
now retains `[1,5]` in one call wherever those sources were actually accepted.

## Cause and change

Matching correctly continued to use original working events, but replacement
construction also reused only their original intervals. When the same retained
source participated in another cluster, the new caption forgot previously
absorbed sources. Transferring a retained caption to another source ID had the
same underlying ownership risk. Pose pooling likewise saw only the latest cluster.

The producer now retains a call-local catalog of each accepted caption's original
source family. An accepted cluster consumes its members' catalogs, retains their
full authored timing union, and transfers the catalog to its chosen output ID.
Only one live family owns those original references; borrowed events and visibility
history remain unchanged. No new pass, persistent cache, result type or diagnostic
owner is introduced.

Matching still uses the original groups, original times and 80% overlap rule.
Representative text and paint selection still receive exactly the original
cluster, preserving the existing color/opacity votes. Accumulated intervals never
become new matching evidence. Output order, removal counts and sparse visibility
adoption keep their existing owners and contracts.

Pose support comes only from compatible original members of the complete family,
through the existing canonical pose key and pooling helper. A previously accepted
caption may supply the target reference when pending spaced text differs from
its original literal. A currently matching original source takes precedence:
a prior caption with different font geometry must not mask valid current proof.
The pool never treats an expanded replacement's display lifetime as authored dwell,
and obsolete contour/opacity coverage continues to expire under canonical edits.

## Checks

The existing module check now contains twelve tests. Added coverage includes
144 combinations of input order, retained-source ID order and time reversal;
36 combinations of exact original pose exposure; pending spaced text whose
unspaced sources cannot supply whole-line pose proof; and a changed-font-size
handoff. An isolated mutation confirms the font-size test rejects unconditional
use of the pending caption reference. Explicit crossing-family coverage confirms
that this release does not add iteration or enlarge matching eligibility.

Historical checks compare all previous content, paint, removal, visibility,
identity and selector-call expectations. Timing is checked independently against
the exact union of the connected families authorized by observed source proofs,
rather than reproducing the old lost-start output. No historical production policy
is substituted to accommodate the fix.

Fresh v247/v248 comparison covers 1,728 direct variants. Eighteen have corrected
timing and eight have changed pose support; first-call matching, counts, order,
content, paint, visibility, identity and selection calls remain identical. All
added pose intervals have original-source witnesses. Both focused conversions
retain identical output hashes, complete statistics and font reports. The same
32 direct variants still merge further on a second explicit call, with no change
to their removal counts.

Native libass checks use exact Arial across repaired starts/ends and ordinary,
source-pose, independent-position and separated-time families. Of 78 frame pairs,
72 are unchanged and six restore only the previously lost start/end window.
Restored pixels match the caption's ordinary held appearance; independent text,
paint and unrelated timing remain unchanged.

The full 119-script suite uses Pillow BASIC plus real HarfBuzz on Linux, with
fixed runtime/harness manifests. All thirteen strict-font corpus tracks retain
identical output bytes and complete statistics; all 124 font hashes are verified. Complete results and the final verification
record are retained locally under ignored `validation/full-copy-timing-fix/`.
The existing wrapper, reporting and module-delivery code are unchanged. Native
Windows filesystem/launcher behavior remains outside this Linux validation.

## Evaluation

This corrects the producer's source-family handoff. It needs no downstream repair,
local matching exception or shared-helper policy change. The font-geometry case
is covered within that same handoff, rather than patched in a later consumer.
No new dedicated corrective review was uncovered.

The already identified second-call merging behavior remains a separate assessment.
Do not iterate this pass blindly or use its expanded intervals to authorize more
removals. The timing loss is fixed without deciding whether those additional
merges preserve original cue/paint ownership.
