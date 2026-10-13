# Redundant text copies and reconstruction handoff — v187

Standard simplification distinguishes two responsibilities that previously
shared the older sign-copy filter:

- `remove_redundant_text_copies()` proves that an entire static text record is
  redundant, with exactly matching literal text, geometry and paint apart from
  a small explicit anchor offset.
- `select_static_sign_paint()` chooses representative paint from near-coincident
  nonlyric effect copies. This deliberately allows different paint and layers,
  and retains the established five-percent font-size/scale allowance. Emphasis,
  spacing, wrapping, origin, border style and encoding must agree.

`reduce_static_sign_copies()` is the early orchestration point: strict redundancy
first, representative sign paint second. Both proofs share whole-lifetime
coverage and the existing six-percent text-height anchor bound. Neither extends
timing or walks through removed anchors to justify further displacement. The
paint selector retains its candidate-position index; its ranking remains fill
alpha, higher layer, longer duration, then source order.

Strict matching compares every literal span through `static_object_key()`,
including parser continuation and document measurement. All spans must have one
explicit anchor. Moving, animated, faded, karaoke, clipped, drawing and partly
translucent records remain excluded. Automatically wrapped records can only
match at exactly the same anchor. Equivalent numeric layer spellings share an
ordering relation. Active same-layer intervening records block removal; an
unknown-layer intervening record also blocks a proof. Longer holds win, followed
by actual list order. Styles, caches, source evidence and input records are
borrowed without mutation.

## Handoff

The early invocation uses `pending_lyrics=True`. Lyric records remain available
to glyph, row, coverage and timing consumers; this restriction applies to both
strict removal and representative-paint selection. The pipeline retains the
original source document separately. Its existing serialize/reparse boundary
produces reconstructed caption records and intentionally ends transient lyric
and row roles. No pass globally clears those roles to make deduplication work.

After caption/backdrop layering, shadow-lettering restoration and bounded color
normalization, `remove_late_complete_copies()` invokes the same strict proof on
finished records. Reconstruction and paint finalization can make copies eligible
that were intentionally protected earlier. The late invocation performs no
representative-paint selection and never invokes the older sign selector.

The former two-alphanumeric-character threshold is removed. Exact whole-record
matching and full lifetime coverage establish redundancy for a single character,
punctuation, a short word or a longer line. This does not declare a fragment to
be a complete caption: a shorter literal cannot cover a longer literal, nearby
repeated letters at different glyph positions remain distinct, and overlapping
letter phases without complete lifetime coverage remain separate. Unfinished
lyric fragments still retain their source/row roles.

Both invocation sites contribute to the existing `deduped` statistic. There are
no wrapper counter or command-line changes. Legacy simplification is unchanged.

## Validation

```sh
python validation/run_backend_check.py --backend windows tests/check_late_complete_copies.py
python validation/run_review_checks.py
python validation/run_redundant_copy_handoff_corpus.py
```

The extended focused check covers short records, partial fragments, pending
lyrics, paint selection, emphasis/spacing, numeric layer aliases, malformed
ordering, gradients, alpha, wrapping and drift. Its existing 22 exact-font lyric
fixtures and 54 rendered comparisons protect the reconstructed first-conversion
result, including all 18 demonstrated redundant-copy leftovers. The existing
complete-line jitter and static-phase checks protect the neighboring concepts.

The new corpus runner verifies the v186 engine, source and output hashes before
regenerating all nine sources with the same fonts. It requires unchanged output
bytes and statistics, no missing fonts, and settled final copy/phase proofs.
Generated reports, subtitle assets and fonts remain local and ignored.

Fresh v187 verification passed all 69 regression scripts and 258 focused copy
checks, including the 54 existing render comparisons. All nine full-corpus
outputs and statistics match v186, with no missing fonts. The 72 PowerShell
reporting checks and extraction/simplification/remux/font-sync smoke test also
passed. Windows BASIC plus real HarfBuzz ran on Linux; native Windows wrapper
execution remains separate validation.

An alternating eight-sample timing comparison on the actual 359-record early
input of the focused Overlord fixture produced identical early results. Median
filter time was 3.9 ms for v186 and 8.6 ms for v187. This small absolute overhead
buys the additional strict proof; this release makes no speed improvement claim.
