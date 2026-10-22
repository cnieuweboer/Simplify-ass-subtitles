# Transitive full-copy families — assessment after v249

Assessed on 2026-10-23 against runtime `2026.10.22.249`, commit `a908c53`.
Production code, configuration, wrappers and the runtime version are unchanged.
The connected-family implementation used here is an isolated local prototype.

## Conclusion

A clean extension is feasible without a maximum family size, maximum duration,
common-overlap window, all-pairs matching requirement or exact-paint requirement.
The single-original-anchor condition is a bounded v249 admission policy, not an
essential definition of a redundant copy family.

Use connected components of the existing matches between original positive-
duration working events. Preserve the existing grouping and 80% overlap rule;
never discover links from rendered union intervals. Each component has continuous
temporal coverage through its original links. Select text/paint once from its
complete originals, retaining the v249 source-pose and sparse visibility handoffs.
Zero-duration records cannot connect otherwise separate families.

However, do not ship unguarded graph closure. A synthetic example exposes an
existing compositing weakness in this producer, which wider families amplify.
Correct that shared admission/application proof before extending discovery.
One focused implementation release is reasonable; it does not need an
architecture redesign or a series of numeric tuning releases.

## What the remaining chains mean

The four-caption example uses `[1,4]`, `[1.5,4.5]`, `[2,5]` and `[2.5,5.5]`
seconds at one position. Adjacent originals satisfy the existing overlap rule,
but none matches all four. V249 accepts three and leaves one. Their expanded
representatives match on another call. That rerun changes the available paint
evidence; it is not the right way to discover the family.

The original links already supply a simpler proof. The isolated component
prototype settles all remaining direct repeat merges across 864 variants:
72 scenarios, three input orders and four visibility modes, using a read-only
visibility map for the prototype. Six variants change, corresponding to the two
remaining fixture/mode cases across the three orders. No second-call removals
remain in that bounded matrix. Borrowed state/history are checked through complete
event fields, rather than Event equality, which deliberately ignores caches and
evidence.

Additional synthetic families with 4, 20 and 100 sources settle without a family-
length cap. Gaps, touching color holds, separate positions, different actors and
zero-duration bridges remain separate. Long chains of the same continuous caption
are not by themselves a failure: an arbitrary span cap would leave complexity
without identifying any lost content.

## Paint ownership

A four-source matched-fade example retains three whole-caption color changes
through the actual existing source timeline collector and final emitter. Complete
pipeline conversion is identical under current and prototype discovery. In the
isolated producer/consumer check, complete-family collapse actually enables the
existing timeline handoff where a remaining raw fading event prevented v249's
partial result from being adopted.

Thus different source colors do not justify an equality guard. Representative
effect paint and producer-proved temporal paint remain distinct responsibilities.
Keep the existing timeline evidence and configurable phase policy; do not recreate
intent by inspecting the flattened representative afterward.

A heavily overlapping sequence of static colors without matched readable-core
handoffs is already flattened earlier in both complete-pipeline runs. This
assessment does not classify that as a new transitive-family regression or propose
changing its paint-intent policy as a prerequisite.

## The actual constraint: independent intervening ink

In a native Arial example, four white copies overlap at one anchor. An independent
red text event appears between the second and third copies in ASS paint order.
The later originals paint above that red text. Keeping one representative at the
earliest source position instead puts it below the red text.

At 2.25 seconds, v249's partial merge already turns 164 fully white source pixels
red. At 3.25 seconds, its remaining later copy restores that foreground. The
unguarded component prototype removes that remaining copy and exposes the same
164-pixel loss at this later time. This is actual occlusion, distinct from the
smaller contour/antialias changes expected when redundant copies disappear.

The same independent event placed away from the caption creates no such loss.
The existing `_glyph_replacement_row_is_clear()` accepts the distant placement
and rejects the overlapping one using exact-font geometry. Blanket rejection of
interleaved records would therefore be unnecessarily strict.

A hand-constructed partition keeps the first two copies before the independent
text and the last two after it. It reduces four copies to two and avoids every
tested white-to-red occlusion. This demonstrates the useful repair direction;
it is not a complete implementation of general temporal/layer arbitration.

## Recommended implementation scope

1. Make the producer check whether a proposed replacement can change ordering
   relative to active independent content. Preserve actual layer/list order;
   do not infer that an unrelated record is harmless solely from its style/name.
2. Only for possible order crossings, reuse measured clearance. Distant content,
   content outside the time interval and unchanged compositing order should not
   block reduction. Do not require font measurements or simpler geometry for
   otherwise uncontested families merely because this proof exists.
3. Where independent overlapping ink makes a single replacement unsafe, retain
   compatible subfamilies on their original sides of that content. If timing
   requires multiple representations, preserve those necessary distinctions.
   Apply this to existing anchored families too, not as a chain-only exception.
4. Replace single-anchor proposal arbitration with connected original-source
   discovery inside those ownership/compositing constraints. Select once from
   accepted originals and use the existing timing, pose, rendering and visibility
   owners. Keep current paint timeline adoption intact.

The reusable clearance implementation and `_caption_implicit_anchor()` currently
live in the engine. Their dependencies already have private owners, apart from
the small shared `CAPTION_PAINT_TAGS` vocabulary. A bounded extraction of that
proof and anchor read would allow direct private-module reuse with one-way imports.
Pass the caller-owned metrics rather than introducing a cache owner, callback
adapter, engine import from a private module or new global context.

That preparation can be part of the focused release. Split it only if implementation
reveals a materially wider dependency change; the inspected boundary does not
currently require a larger redesign. Test foreign content before/after all copies,
actual interleaving, distant/animated peers, opacity, source-order changes and
competing temporal ownership, alongside source-connected chains and paint phases.
Then run the full regression suite and corpus comparison.

## Evidence and follow-up evaluation

Fresh full-pipeline prototype runs cover the four corpus tracks that exercised
full-copy removal in v249: Overlord, Attack on Titan, Solo Leveling and Goblin
Slayer. All 813 removals, complete event fields at this stage, output bytes and
complete statistics agree with v249. Exact fonts are supplied; missing required
families stop the probes. The other nine corpus tracks and the full 119-script
suite were not rerun for this assessment. Prior v249 release evidence remains
historical evidence, not a claim of fresh assessment coverage.

Local scripts, original/prototype outputs, native font hashes and results are
under ignored `validation/transitive-copy-assessment/`. Complete runtime manifests
are checked around the probes. Native samples cover isolated copies, overlapping
foreign text and distant foreign text at four times, plus the preserving partition.

No production workaround or new restriction was introduced. The dedicated related
follow-up is the pre-existing full-copy compositing proof. The preferred fix
handles it in the shared producer before generalizing families, rather than adding
strict chain bounds or a late corrective pass.
