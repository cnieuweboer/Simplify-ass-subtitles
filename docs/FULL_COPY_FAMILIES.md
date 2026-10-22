# Original-anchor full-copy families — v249

Runtime `2026.10.22.249` completes anchored full-copy families before rendering
them. Three copies at `[1.5,4.5]`, `[2,5]` and `[2.5,5.5]` seconds now become
one caption at `[1.5,5.5]` in one invocation, regardless of input-list order.
The middle original proves both neighbors under the existing 80% overlap rule.
Previously, absorbing that original early could hide its remaining match link.

## Discovery and arbitration

The producer scores every positive-duration original anchor before removing any
source. Existing normalized-text, style, actor, row, position and placement
grouping is unchanged, as is the original overlap comparison. Zero-duration
sources may be absorbed by a real caption, but cannot act as anchors joining
separate holds. Negative-duration sources do not supply family members.

Larger original-supported proposals take precedence. Original source ID breaks
ties, independently of the supplied list order. A proposal may claim only still
unowned originals and must retain its own original anchor. Every accepted member,
including the retained output ID, belongs to exactly one family. Its original
references are sorted by source ID for repeatable paint voting. Proposal sizes,
groups and application buffers are call-local; no quadratic reference table,
global cache, persistent family record or new processing context is introduced.

This is a deterministic greedy arbitration policy, not a claim of globally
optimal event reduction. An arbitrary connected overlap graph is not sufficient
proof of one caption. Long rolling chains and competing families can remain
separate when no original anchor proves their complete union.

## Selection and handoff

Each accepted family selects representative text/paint and renders exactly once
from its original working events. The existing preference for authored spacing,
plain effects and earlier source IDs remains. There is no pending rendered
caption, visibility overlay or transfer between partially selected families.
In particular, the producer never votes with an expanded replacement lifetime.
There is no exact-paint-equality restriction; choosing representative source
paint remains this pass's job.

Bounds retain the complete accepted family's time union, preserving the v248
lost-start/end correction. Source-pose support also pools only compatible
original exposure. A compatible original supplies the reference key if the
selector's chosen geometry differs from the preferred text source. The canonical
pose key, replacement/evidence invalidation and rendering policies retain their
existing owners. No synthetic dwell is attributed to the union lifetime.

The family with a preferred 50-point original and two 40-point originals now
keeps the preferred original's selected 50-point pose consistently. It no longer
switches to a later partial cluster's 40-point result. Its pose support comes
only from the compatible original, rather than borrowing incompatible dwell.

Visibility history remains borrowed and supports lookup-only/read-only maps.
Accepted captions return sparse assignments, including equal-value assignments.
Caller adoption, stage order, level gating, counters and wrapper reporting are
unchanged. Refused events retain object identity; output retains original list
slots for surviving source IDs. Separate color holds and independently owned
content remain separate inputs to their existing consumers.

## Checks and evaluation

The module check has sixteen tests, including original-anchor completion across
all six list permutations, once-only complete-original paint voting, 72
order/ID/time-reversal timing combinations, 36 pose-support combinations,
competing rolling-chain families, zero-duration bridges, separate color holds,
interleaved content and cold installed execution. Failure injection now uses two
independent families: rendering a partial family twice is no longer expected.

Historical visibility/consumer checks retain exact parity when the observed
source-cluster and vote order agree. Changed admission cases instead require a
behavioral contract: every selected source is an actual borrowed original,
families are disjoint and have a positive-duration original anchor, output text
and timing belong to that family, updates/counts are accurate, and untouched
events preserve their identity. Historical selection policies are not substituted
into fresh corpus, direct or native checks.

Fresh v248/v249 comparison covers 1,728 direct variants. Fifty-six results change;
all 576 fixture/visibility/map combinations are invariant across the three tested
input orders. Both focused conversions are unchanged. Repeat removals fall from
32 to 12; every remaining candidate needs transitive original links with no common
original anchor. These remaining cases span two fixture/visibility combinations
across three orders and two map types. They are deliberately not a fixed-point
target. These twelve are not simply a subset of the former 32: deterministic
disjoint ownership also keeps apart some transitive chains that the earlier walk
had collapsed through successive partial clusters. An explicit rerun can merge
their expanded representatives, but that is not additional original-source proof.
A separate rolling-chain probe can also merge further if explicitly
rerun; no universal idempotence claim is made.

All thirteen strict-font corpus tracks retain identical bytes and complete
statistics, and all 124 recorded font hashes are verified. Native libass checks
retain 78 unchanged frame pairs for existing families. Another 44 frame pairs
for corrected families match independently authored single-caption references,
including different source colors, source opacity, translucent authored contours,
caption boundaries and interleaved ink. Existing reconstructed-caption policy
makes fill opaque while retaining proved contour alpha; this release does not
change that rendering policy.

All 119 regression scripts pass using Linux Pillow BASIC plus real HarfBuzz,
with unchanged runtime and harness manifests throughout the run. The actual
shipped v214 updater also passes a v248-to-v249 update, locked-file rollback,
retry, preserved user/launcher choices, isolated execution and owned uninstall.
The complete runtime manifest still contains 34 Python sources; only this
private producer and the root version assignment change in production.

The change removes the producer's repeated partial rendering and source-family
transfer, rather than adding a late repair. No downstream exception, forwarding
adapter, new counter or wrapper change was needed. The remaining transitive-chain
ownership question is the already scoped follow-up; corpus evidence does not
currently justify broadening admission for it.

Local baseline runtimes, manifests, snapshots, rendering evidence and regression
reports live under ignored `validation/full-copy-family-fix/`. Linux BASIC plus
HarfBuzz and libass validation does not establish native Windows filesystem or
launcher behavior.
