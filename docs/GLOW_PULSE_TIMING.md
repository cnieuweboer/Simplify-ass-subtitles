# Bounded timing slack for returning-highlight copies — v194

Two returning-highlight chant cues retained grey fade pieces and timed letter
copies because their last letters dissolved 40 ms after the held event ended.
Pulse correspondence already admitted approximately 50 ms timing differences,
but a separate strict containment check rejected the final word. Complete-row
ownership then correctly rejected the whole row, leaving the ordinary fallback.

The existing stack matcher now uses its source-pulse timing slack for candidate
containment too. A dissolving copy may start or finish approximately 50 ms beyond
the held cue. Pulse endpoint correspondence and held-cue overhang are bounded
independently: their allowances cannot accumulate into a 100 ms overhang. The
limit remains 51 ms, preserving the existing approximately 50 ms convention and
its small precision margin. This is a fixed source-matching allowance, not a
claim that every ASS file has a 24 fps frame rate.

The remaining proof is unchanged: exact fonts, complete literal glyph/whole-word
coverage, matching authored anchors and layout, supported opacity/blur/scale
animation ending transparent, fixed paint, coherent ordered returning pulses,
one persistent glow and unique ownership. Missing or multiply owned content and
changed paint/layout still reject the complete row. These are decorative copies
of the retained words; admitting them does not extend a held interval or fill a
blank between captions. The existing boundary ownership and cue-overlap handoff
handle entrances, exits and backing under their own proofs.

Focused synthetic checks cover 40/50 ms tail overhangs, an early 40 ms copy,
whole-word copies, 60 ms rejection, combined offsets producing a 100 ms overhang,
missing letters, changed paint, moved anchors, cyclic foregrounds, unchanged
held timing, borrowed input immutability and repeat stability. The two real
chant cues must retain complete text, opaque settled fill and subdued contour,
without short timed highlight copies. Native lifecycle checks now require settled
paint for all 11 chant cues instead of skipping the two fallback cases; the 14
left-side lyrics and their already-corrected handoffs remain unchanged.

This release changes only returning-highlight copy admission. The timing review's
separate entrance/exit fade-validation asymmetry and karaoke-completion endpoint
admission mismatch remain follow-up candidates. No new pass, production counter,
font requirement or dependency is introduced. The known generated-output
reprocessing contour issue remains separate; global file idempotence is not
claimed by these focused coordinator checks.

Fresh verification: all 71 regression scripts pass, including 309 focused checks.
All nine established corpus outputs/statistics are byte-identical to v193. The
supplied track drops from 324 to 279 events and peak concurrency from 38 to 26;
all non-chant styles remain unchanged. Every required font is available. Native
samples cover 25 stable lifecycles (14 left lyrics and all 11 chant cues), with
pixel-identical left-lyric held appearances and preserved previously corrected
handoff edges. The two reported chant cues retain their complete text and steady
paint through their sampled entrances, holds and exits.
The concurrent wrapper-output update is preserved after rebasing; its 12 checks
and the environment smoke test also pass. Rebased runtime/harness hashes are
unchanged from the full regression run.
