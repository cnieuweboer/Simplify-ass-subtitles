# Representative frame poses — v200

The frame freezer now selects geometry from immutable source-frame support,
independently of normalized output paint or a replacement's extended lifetime.
The same selection policy serves ordinary sequential text effects, complete-line
jitter and vector/text frame sequences. Eligibility and compositing remain the
responsibility of their existing proofs.

## Cause and selection policy

Additional paint normalization joined more frames of the tracked Attack on Titan
signs. The old selector ranked current alpha, current event duration and source
index. Normalization erased the alpha differences; nominal 50 ms durations at
large timestamps differed in floating-point subtraction. Consequently, incidental
paint grouping or frame splitting could change the selected placement.

The new policy groups actual candidate poses, including font/layout, literal,
measurement context and clipping. Numeric geometry uses the renderer's existing
six-significant-digit precision. It ranks each pose by source exposure: interval
length multiplied by actual opacity. Primary paint is authoritative when visible;
outline-only and shadow-only objects use their active visible channel. Unused
outline/shadow channels cannot win a vote. Coincident copies contribute maximum
opacity, rather than multiplying support. Gaps remain gaps.

Equal exposure prefers a pose covering the visibility-weighted temporal median,
then the nearest exposure centroid, earliest support and a deterministic geometry
key. Intervals are rounded to microseconds to prevent float subtraction from
breaking nominal duration ties. Selection retains an existing candidate pose;
it does not average geometry. A sustained readable hold can outweigh a brief
fully opaque flash.

Geometry and final paint are separate decisions. Frame sequences already match
static paint apart from alpha. They retain their established visible/unfaded paint
owner while using the source-supported geometry. Other reconstruction routes keep
their existing paint proof. Simultaneous paint/effect alternatives retain their
compositing representative: their overlap does not establish a sequential motion
timeline. Clipped reconstructions, scale trails and proved upright boundary holds
retain their distinct geometry/ownership proofs.

## Evidence and handoffs

`EventEvidence.frame_pose_intervals` stores absolute interval endpoints and
primary/outline/shadow alpha. The pipeline captures it after individual event
sampling/freezing and before stack paint normalization. It describes sampled or
frozen frame support, not a claim that every original transform held that geometry
for its entire authored interval. Existing within-event sustained-pose and
entrance/exit proofs continue to select those individual frozen poses.

Paint-only edits preserve this evidence when literal/layout/geometry are unchanged.
Changed fonts, positioning, clips, inline layout or measurement context invalidate
it. Existing contour and opaque-span invalidation rules remain independent.
Stack collapse, complete-copy collapse and phase joins explicitly pass compatible
support to successors. Timing consumers clip support to the surviving event;
extending an output cue does not invent source exposure. Static-phase joins collect
support at completed-run emission, avoiding repeated copies of an expanding list.
The evidence is immutable, pipeline-local, absent from serialized ASS and has no global
parser cache.

Near-static admission uses a fixed source anchor to prevent cumulative drift.
The selected final pose must also pass the existing two-percent text-height bound
against every constituent hold. Pose selection runs at completed-run emission,
rather than repeatedly rebuilding exposure for every candidate. This keeps
placement selection separate from the geometry admission proof.

## Validation and evaluation

`tests/check_frame_pose_selection.py` checks source-opacity preservation, splitting,
redundant copies, source-ID/order changes, normalized fades, timing extensions,
active paint channels, geometry invalidation, jitter bounds and full conversion.
`tests/check_frame_pose_selection_render.py` compares native libass output with
independently authored expected poses on gray/white backgrounds and verifies
upright entrance/exit holds and exact boundaries. Existing regressions continue
to exercise clipped captions, moving signs, phase joins and compositing.

`validation/run_frame_pose_corpus.py` regenerates all ten restored corpus sources
against hash-verified v198 outputs. It requires identical content, paint, font,
layer and timing visibility, and traces changed poses to supplied source/derived
candidates. Local outputs, fonts, timing measurements and render panels remain
ignored development assets.

The general frame policy is explicit and shared. It requires no show-specific
recognition or downstream compatibility paint substitution. Whole-span inline
paint ownership and thick-outline geometry remain separate follow-up releases;
this change does not expand their scope.

The fresh ten-source comparison retained all 14,134 output records and every
production statistic. Six outputs remained byte-identical; four had 51 changed
poses in total. Content, paint, font, timing, layer and multiplicity timelines
were unchanged. Changes included sustained tracked-sign positions, bounded lyric
jitter and a sign previously held partly below the viewport. All changed poses
were traced to supplied candidates. The 1,000-hold jitter stress case completed
in approximately 0.21 seconds, compared with 0.15 seconds for v198 on this host.

All 78 regression scripts passed, including 66 focused source-support assertions
and 42 native expected-pose checks. Runtime and harness inputs remained unchanged
throughout that run. The MKV extraction/simplification/remuxing and font-sync smoke
workflow also passed without changing its source inputs.

Native corpus validation produced 102 source/v198/v200 comparison panels, covering
all 51 changed captions on gray and white backgrounds. Each selected held caption
remained visible and pixel-stable through its own cue interval. Unchanged short
paint phases are kept separate from that stability check. After rebasing onto the
latest utility changes, all 76 wrapper/utility tests across eight suites and the
MKV smoke workflow passed again; engine-suite inputs were unaffected by the rebase.

After-release evaluation: selection is explicit, repeatable and independent of
incidental paint grouping in the tested reconstruction routes. Source evidence
survives the responsible upstream handoffs; no downstream paint substitution is
needed. The current corpus and equivalent-input tests reveal no conflicting frame
selection routes requiring a larger review. Inline paint ownership remains v201's
distinct task, while the global API and pass-local index reviews stay deferred.
