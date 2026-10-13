# Final static-tag compaction — v189

Standard conversion now invokes the existing `compact_static_overrides()` once
more at final serialization, after support ownership/layering, shadow lettering,
color normalization, redundant copies and static phases have finished. It
reduces spelling left by late generators without repeating effect selection,
reconstruction or any removal/merging pass.

The new `final=True` mode has a narrower responsibility than the existing
compaction used during text simplification:

- Static Dialogue records only. Moving, transformed, faded, karaoke, explicit
  event effects and empty/reversed intervals are retained unchanged.
- Adjacent recognized override headers are resolved together, so superseded
  intermediate paint before a literal span need not be serialized. Headers
  separated by literal text remain distinct; gradients retain their per-span
  colors and geometry.
- Inline annotations and unsupported override syntax remain unchanged. Comment
  events retain their identity. Literal text, drawing payloads, escapes, event
  fields, timing, actor, layer, margins and list order remain intact.
- Final serialization does not clamp blur or remove origins. The ordinary
  resolver generates a candidate, which is accepted only if it is shorter and
  every literal span has equivalent formatting and identical parser continuation.
  Precision loss, first-alignment latch changes and reset-history changes reject
  the candidate. No source numeric value is coarsened to enable compaction.
- The equivalence proof recognizes implicit zero blur/edge blur and axes equal
  to their uniform border/shadow value. All other paint/geometry, reset history,
  document measurement and literal payload remain exact. Adjacent equivalent
  literal runs are compared together.

This uses the existing canonical override resolver and serializer, rather than
introducing a separate ASS interpretation. Existing early callers retain their
previous behavior. The final pass returns successors with reparsed formatting
and continuation and explicitly preserves source evidence for proven equivalent
edits. Input events, caches and catalogs remain borrowed read-only. It can also
compact unpositioned text without introducing a position or changing collision
participation.

It runs after ownership consumers have finished; it does not rewrite their
proof relationships or infer new ownership. Output/event/concurrency statistics
are unchanged. No filter contribution counter is added for this serialization
operation, and the Windows wrapper catalog and CLI are unchanged. Legacy mode
retains its established path.

## Validation

```sh
python validation/run_backend_check.py --backend windows tests/check_final_static_compaction_render.py
python validation/run_review_checks.py
python validation/run_final_static_compaction_corpus.py
python validation/render_final_static_compaction_corpus.py
```

The new focused check covers adjacent paint, style defaults, gradients, uniform
and axis restoration, resets, relative font sizes, precision, origins, drawings,
mixed drawing/text, bold italic lettering, alpha shorthand, alignment history,
animations, unknown syntax, comments, unpositioned text and immutable inputs.
Thirteen native libass comparisons protect rendering; an actual Demon Slayer
conversion checks the final handoff and stable final spelling. Its ordinary and
bold italic Volkhov faces are verified before font-dependent comparisons.

The corpus runner verifies v188 engine/source/output hashes before regenerating
all nine original sources with the same exact fonts. Only the final serializer's
proven edits are allowed. It checks every changed record's literal formatting,
continuation, event fields and unchanged statistics; compaction itself reaches
stable spelling, and no additional final copy/phase cleanup remains in this
corpus. The render runner samples changed intervals plus the Demon Slayer ending
gradient. Assets, converted subtitles, images and reports remain local/ignored.

Historical whole-file byte oracles use `historical_final_tag_policy()` only within
their older comparison scope. It omits final v189 serialization while leaving
live pass logic and direct compaction checks enabled. The relative-size check now
compares resolved literal formatting/history rather than requiring redundant
font-size tag spelling. The new focused check and full corpus exercise the
unmodified current pipeline. This avoids treating historical spelling as an
intended behavioral constraint.

Stable final spelling is not whole-conversion idempotence. Different styling
phases and other previously documented second-conversion decisions remain
separate work; compaction does not flatten those intentional differences. The
broader API and pass-local index reviews remain deferred.

Fresh v189 verification passed all 70 regression scripts and 191 focused checks,
including 13 pixel-identical focused render pairs. All nine full-corpus
comparisons pass without missing fonts: 739 records compact, saving 24,610 tag
characters, with unchanged event counts, ordering, timing and statistics.
Twenty-four additional corpus render pairs, including the sampled Demon Slayer
ending gradient, are pixel-identical. PowerShell's 72 reporting checks and the
MKV extraction/simplification/remux/font-sync smoke test also pass. Windows BASIC
plus real HarfBuzz ran on Linux; native Windows wrapper execution remains
separate validation.
