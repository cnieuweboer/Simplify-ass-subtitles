# Full-copy merging on repeated calls — assessment after v248

Assessed runtime `2026.10.22.248` at `2a10a56`. This assessment changes no
production code, matching policy, configuration or wrappers.

## Findings

The remaining direct-call instability is real, but it did not occur at this
stage in the thirteen available corpus tracks. Fresh current-policy conversions
removed 813 full copies: Overlord 586, Solo Leveling 140, Goblin Slayer 78 and
Attack on Titan 9. Probing a second call immediately after the production call
removed zero additional events in every track. Probes returned the first result
to the pipeline; they did not inject the second result. All thirteen output hashes
and complete statistics match the preceding v248 validation. All 124 recorded
font hashes were verified; no missing fonts were accepted or substituted.

Fresh direct checks reproduce 32 repeat-merge variants out of 1,728. Read-only
and ordinary maps duplicate each scenario, leaving sixteen distinct combinations
of fixture, order and visibility mode. Twenty-eight variants have exclusively
positive source durations; four contain a zero-duration event.

Every observed second-call merge has an overlap witness between original sources.
The investigation did not find an observed merge authorized solely by fabricated
union timing. Nevertheless, a literal rerun uses replacement intervals and
replacement paint as its inputs; those are no longer the complete original proof.

For example, three captions at one anchor have intervals `[1.5,4.5]`, `[2,5]`
and `[2.5,5.5]` seconds. The middle original overlaps each neighbor by at least
80% of the shorter duration. The two outer originals do not match each other.
When the first cluster absorbs the middle source, that original can no longer
act as an anchor for discovery. Depending on list order, one call leaves either
one caption or two. The two-caption outcome merges on the next call.

Final complete-copy cleanup and final static-phase merging leave this two-caption
example unchanged: neither event contains the other's whole lifetime, and these
are overlapping captions rather than touching identical phases. This checks those
two final policies directly; it does not claim that every synthetic input reaches
them unchanged through the complete pipeline.

## Paint and rendering

Reusing a rendered replacement is not equivalent to selecting once from the
complete accepted originals. Giving the three sources red, green and blue fills
produces green plus blue after the first call and one blue caption after the
second. Different input orders also produce different single-caption paint.
Complete-original selection is repeatable for fixed original inputs, without
counting an expanded representative's lifetime as fresh source exposure.

Six native libass frame comparisons use the exact Arial regular face. Identical
paint has unchanged pixels outside the overlap, but 534 pixels differ inside it:
rendering duplicate antialiased contours is not equivalent to rendering one copy.
The differing-paint example also changes 1,522 pixels before the overlap when its
selected appearance changes. This is therefore a content/paint/compositing issue,
not just a removal-counter issue. These are bounded synthetic rendering checks,
not evidence that the corpus currently exhibits the fault.

## Recommended next step

One focused release can restore original-anchor family discovery:

1. Discover eligible clusters using original working-event anchors, including
   anchors that would otherwise disappear during earlier removals. Preserve the
   existing grouping and original 80% overlap meaning.
2. Resolve competing family proposals deterministically before replacing events.
   Select representative text and paint once from each complete accepted family;
   pool timing and compatible original pose support through their existing owners.
3. Protect separate cues and existing authored color-phase ownership. Do not
   introduce an exact-paint-equality requirement: representative paint selection
   is already part of this producer's responsibility.
4. Cover order/ID variations, different colors, partial visibility maps, gaps,
   zero-duration sources, intervening content and competing/long-chain families.
   Verify the full pipeline, native rendering, corpus and regression suite.

Thirty of the 32 observed variants have a common original anchor matching every
member of the proposed combined family. Of these, 26 have only positive durations.
The remaining two variants are the read-only/map versions of one randomized
scenario: combining its existing families requires transitive links, with no
single original anchor proving the whole family. Treat that as a separate proof
question, not an automatic connected-component merge. A rolling-chain probe also
shows why eliminating every possible repeat removal is not a sufficient policy.

Do not iterate to a fixed point or extend overlap admission using union lifetimes.
The proposed release should settle proved anchored families, without promising
universal idempotence for ambiguous chains. Reassess the remaining bridge case
afterward; a second implementation release is not currently justified by corpus
evidence.

## Evaluation and evidence limits

No workaround, downstream exception or production dependency was introduced.
The dedicated follow-up is deterministic family discovery and original-source
paint selection; unrestricted transitive-family ownership remains unresolved.
The previous v248 timing repair remains valid and independent of this decision.

Local scripts, manifests, direct snapshots, native hashes and corpus results are
under ignored `validation/full-copy-repeat-assessment/`. Complete runtime manifests
were checked around the fresh probes. The full 119-script regression suite was
not rerun for this documentation-only assessment; it is required for a subsequent
behavior change. These Linux checks do not establish native Windows behavior.
