# Caption/background ownership — v188

Support selection, final caption layering and support association now cooperate
through one measured containment proof and explicit enclosing-panel ownership.
This consolidation preserves the established admission and rendering policy.

`caption_panel_contains()` checks matching style/actor, containment of the
measured ink in both the current and original contour, and any rectangular panel
clip. Support selection, texture coverage and final layering use this same
spatial proof. It deliberately does not imply opacity, timing coverage or paint
order: each caller supplies the obligations appropriate to its operation.

`CaptionPanelOwnership` records a measured relationship between an enclosing
panel and a caption. It borrows their records without changing them. Support selection returns its already proved measured relationships; it does not
remeasure font bounds or repeat polygon containment to classify them. The support
pipeline installs these proofs in `CaptionSupportResult.ownership` after support
selection and vector budgeting, before nearly coincident shadow lettering becomes
ordinary opaque text. Adjacent arrows, fullscreen fills, unknown geometry,
clipped/translucent shapes and unmeasured supports establish no such ownership.
An associated caption is not automatically an owner.

Final layering consumes these relationships. It normalizes the ownership
caption's shadow lettering consistently with the output, rechecks containment
of the finished ink, and requires whole-lifetime panel coverage before promoting
text. The new layer is above every eligible version of the owned panel in one
call. Existing style/actor guards and the small rectangle footprint allowance
are unchanged. A different overlaid card remains a mask, including when painted
later in the same layer. Repeated final-layer evaluation previously let rebuilt
associations adopt such masked text and expose it; explicit ownership fixes that
handoff error without changing the first evaluation. Exact matching nonrectangular footprints can authorize
promotion; bounding-box similarity alone cannot.

Layer successors receive corresponding ownership successors. If a lower panel's
fill is completely hidden and removed, its original footprint can still be
needed to distinguish its caption's own background from an independent card.
That proof survives as context, without reinserting the hidden drawing. Later
association rebuilding describes retained supports; it cannot create a new
ownership claim. Repeated final-layer calls therefore retain the original
relationship rather than deriving it from an increasingly broad association.

The public `select_caption_supports()` two-result interface is unchanged. The
production caller consumes the internal selection result with ownership and
filters its proofs along with vector budgeting.

Direct callers using the older six-field `CaptionSupportResult` constructor can
establish ownership once through the same proof. Production always supplies the
explicit list. An explicit empty list means no enclosing ownership; it does not
request inference from current associations.

## Distinct responsibilities

`_covered_caption_panels()` separately proves redundant rectangular fills. It
requires opaque supported geometry, higher layer, matching family, full fill and
lifetime coverage, and no lower stroke/shadow. Partial geometry, partial timing,
blurred/unsupported shapes and exposed effects remain. This destructive proof
is independent of deciding which panel owns text.

The earlier text-stage source-order restoration remains separate. It uses the
original authored ordering and a contained anchor to keep reconstructed lyrics
above a source mask. It does not establish measured whole-caption enclosure.
Replacing it with final support admission would lose useful source evidence and
change unknown-font/baked-video-mask handling. Legacy vector occlusion is also
separate: it can cover arbitrary drawing bounds without establishing a caption
owner. Neither is rerun as a late ownership heuristic.

Caption selection still retains the uppermost enclosing support separately for
each occupied interval. Positive overlap can justify retaining a background;
only whole-lifetime coverage can justify moving a caption above it. These timing
obligations are intentionally different. No new Event/font classification, global
cache, command-line option or report counter is introduced. Source records,
formatting/parser caches, evidence, styles and input containers remain borrowed;
result proof lists, associations and counters belong to their result owner.
Small pass-local caches share geometry and shadow normalization for repeated
relationships to the same borrowed record; they end with that invocation.

## Validation

```sh
python validation/run_backend_check.py --backend windows tests/check_caption_backdrop_layers_render.py
python validation/run_review_checks.py
python validation/run_caption_ownership_corpus.py
ASS_REGRESSION_FONT_BACKEND=windows PYTHONPATH="$PWD/validation/backend_startup" \
python validation/render_caption_ownership_handoff.py
```

The extended focused check covers explicit ownership and its absence, original
contours, hidden-owner evidence, independent masks, same/different polygon
footprints, stroke/rounding variation, font sizes, partial timing, blur, opacity,
clipping and input immutability. The complete Sword conversions trace the actual
production handoff and compare first/second/third sampled rendering against the
verified readable v182 oracle.

The standalone render diagnostic reproduces that same-layer handoff error with
a dark independent card. The first v188 frame matches v187; second and third
v188 frames remain pixel-identical, while v187 visibly exposes the masked text
on repeated final-layer evaluation. This is a proof-stage regression, not a claim
that all whole-file repeated conversions are idempotent.

The new corpus runner checks v187 engine, source and output hashes, regenerates
all nine sources with the same exact fonts, and requires identical output bytes
and statistics with no missing fonts. Generated reports and assets remain local.
Final static-tag compaction and the broader API/index reviews remain separate.

Fresh v188 verification passed all 69 regression scripts, including the expanded
105-check caption/backdrop test. All nine corpus outputs and statistics match
v187 without missing fonts. The six-frame same-layer handoff diagnostic, 72
PowerShell reporting checks and MKV extraction/simplification/remux/font-sync
smoke test also passed. Windows BASIC plus real HarfBuzz ran on Linux; native
Windows wrapper execution remains separate validation.

An alternating eight-sample comparison on Sword S01E03 included both support
selection and final layering. Median time was 1.521 s for v187 and 1.538 s for
v188 under concurrent validation load; events, supports, associations and counters
were identical. Reusing selection's proofs avoids the earlier prototype's
repeated containment work. This release makes no general speed improvement claim.
