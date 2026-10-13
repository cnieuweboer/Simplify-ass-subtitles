# Development principles

These are the user's standing development preferences, clarified after v185.
They apply to future changes and reviews of existing code.

- Prefer semantic subtitle concepts: paint layers, echoes, complete-line
  jitter, letter phases, caption/background ownership and similar structures.
  A particular show's override spelling or event arrangement is evidence of
  a concept, not its definition. Runtime policy must generalize to other
  subtitles with the same relevant structure.
- Investigate upstream behavior first when an older stage obstructs a newer
  one. Look for a clean correction or explicit handoff in that stage before
  adding downstream exceptions, workarounds or another function. Document why
  an upstream correction is impractical when choosing a workaround.
- Preserve useful original-event information until its consumers have finished.
  Destructive transformations and normalization boundaries need deliberate
  ownership and handoff contracts. Do not clear protective metadata merely to
  make another filter apply.
- Keep passes responsible for distinct concepts. Related passes may cooperate
  or share proof logic; their placement in the pipeline is not sufficient reason
  to accumulate unrelated special cases in one pass.
- Require reasonably strong evidence for destructive heuristic simplification:
  removed content should be redundant or reconstructable. With limited examples,
  choose sensible bounds and account for reasonable variations. Avoid becoming
  unnecessarily conservative because of hypothetical false positives. Explain
  each restriction in terms of a real semantic ambiguity or renderer behavior.
- Keep algorithms readable. Simple caches and indexes are useful; substantial
  additional complexity needs a measured performance benefit. Keep broad API
  and pass-local index reviews separate from concrete failure-case work.
- Treat regression examples as evidence, not specifications. Overlord, Demon
  Slayer, Attack on Titan and other corpus sources demonstrate behavior classes.
  Include variations and counterexamples to test generalization.
- Test intended behavior: readable text, representative paint, timing,
  multiplicity, compositing, source ownership and useful reductions. Historical
  AST/scope audits can document a release, but exact function counts, helper
  names or pass placement should not obstruct a justified structural change.

## Review of v183–v185

All three changes use general runtime evidence. No show names, episode names,
specific lyric wording, particular font families or show-specific colors select
their behavior. Corpus-specific names and expected counts belong to validation.
Their tests establish the observed cases and selected variations; they do not
prove that every reasonable variation is covered.

**v183: final caption/background layering.** Caption paint and retained support
geometry become final after earlier layer checks. Finalizing their relationship
at that point is appropriate, and considering all qualifying supports together
avoids incremental layer changes across repeated conversions. It preserves
separate foreground masks. The new helper still overlaps earlier promotion and
covered-support logic; investigate sharing those ownership/coverage proofs
rather than treating the late helper as permanently separate. Exact style/actor
matching and near-equal panel footprints are conservative evidence guards,
not universal definitions of caption/background ownership.

**v184: late complete-copy cleanup.** Protective lyric metadata remains available
through its existing consumers. Once final captions and paint exist, the new
pass removes only wholly covered, nearly coincident copies with matching spans.
The old sign-copy filter also performs broader effect/paint selection, so
rerunning it was not an equivalent safe deduplication operation. Separate strict
redundancy proof is justified, although shared matching/order infrastructure
should be investigated. The inherited 6% bound and the two-alphanumeric-character
admission rule are heuristics; the latter is a proxy for excluding glyph work,
not a semantic proof that a record is a complete caption.

**v185: late static phases.** Matching literal spans and touching lifetimes is a
general concept. Checking a displaced phase's own lifetime corrects the older
whole-union ordering guard; a peer which ended at the handoff cannot affect that
phase. Actual final list order handles reconstructed source-ID namespaces.
However, this release adds another merger while leaving
`merge_static_timed_copies()` in place. The implementation does not establish
that improving or sharing the existing merger is impractical. This falls short
of the user's preference to fix older infrastructure before adding another
implementation of the same concept.

The recommended next structural investigation is to consolidate static phase
matching and ordering proofs, with explicit stage ownership/handoffs. An early
invocation and a final invocation may still be needed because later generators
create new phases. That timing need does not itself justify duplicated merger
algorithms. Preserve original evidence contracts; do not blindly substitute
the late implementation into earlier source-dependent stages.

The recent releases solve their demonstrated failure classes. They do not
establish general whole-file second-conversion idempotence: differing styling
phases, final tag spelling and other previously documented behavior remain.

The v186 follow-up implements a shared phase merger and explicit stage ownership;
see [STATIC_PHASE_MERGING.md](STATIC_PHASE_MERGING.md). The assessment above
remains a historical review of v183–v185.
