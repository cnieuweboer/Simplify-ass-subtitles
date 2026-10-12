# FontSpacing responsibility review — completed historical plan

This plan was written for engine 2026.10.11.163 (canonical file version 165).
It was implemented in v164 (FontMetrics), v165 (FontOutlineMatcher) and v166
(row geometry, reporting and FontSpacing removal). The steps and prompts below
are retained as historical planning context, not instructions for unfinished work.
Current contracts are in FONT_METRICS.md, OUTLINE_MATCHER.md and ROW_GEOMETRY.md.

## Goal and limits

Separate reusable exact-font operations from subtitle reconstruction policy. Use normal readability and maintainability as the priority. Keep the existing single-file distribution; this work does not require a module/package redesign or one class per cache.

At the time of this plan, FontSpacing combined:
- font discovery, internal-name matching, collection faces and variable-font selection;
- font bytes, instantiated faces, Pillow/HarfBuzz shaping and font metric caches;
- contour extraction and fragmented-glyph inspection;
- bounded interpretation of drawing contours as text;
- recovery/fitting of positioned subtitle fragments;
- mutable missing-font diagnostics and accepted-row counters.

A font operation may interpret ASS font size and requested weight/style. It should not decide event ownership, caption timing, which rows to replace, or whether an effect may be removed.

## Release 1 — Establish the font measurement boundary

Extract the cohesive discovery/loading/measurement implementation into a FontMetrics owner. Keep discovery, matching_face(), requested_weight(), variable_coordinates(), codepoints(), face_data(), open_face(), measure() and ass_em_scale() together. Keep exact-face outline extraction and fragmented-glyph inspection with this owner: they inspect font data; deletion decisions remain in subtitle passes.

Migrate low-level callers with the extraction. In particular, caption_bounds() currently reaches into loaded and ImageFont and dynamically installs _caption_line_metrics; provide a narrow measurement interface for ink bounds and line ascent instead. CLI capability checks should use an explicit capability interface rather than inspect harfbuzz directly.

Keep caption positioning, wrapping, paint/shadow offsets, padding and coverage policy in caption_bounds(). Preserve its current RAQM-only ink refinement and unavailable-backend fallbacks; do not introduce new HarfBuzz ink behavior during this refactor. open_face() remains a useful leased-resource interface for the masked-glyph pass, whose outline canonicalization and open-font lifetime remain pass-local.

The remaining FontSpacing temporarily retains its actual reconstruction/decoding logic and uses the shared metrics owner. Do not add a facade containing one forwarding method per extracted operation. Settle the minimal dependency wiring in this release so later steps can reuse it.

Preserve directory priority, exact font aliases, collection indices, requested variable variants, negative cache results, shaping flags and cache reuse across a CLI batch. No changes to font matching policy.

**Prompt**

Please establish an explicit font measurement boundary in simplify_ass.py. Extract FontSpacing's font discovery, face selection, loading, shaping, metrics and exact-face outline inspection into one cohesive owner. Migrate low-level consumers, including caption_bounds() ink measurements and CLI capability checks, without exposing backend caches. Keep subtitle placement and effect policy outside it, avoid pass-through compatibility wrappers, preserve backend and font-selection behavior, and run focused and full regression checks.

## Release 2 — Separate outline decoding from font data

Move decode_cubic_outline() and its alphabet-specific outline_profiles cache into a dedicated outline-matching component. It borrows the same FontMetrics owner; it must not rediscover fonts or duplicate face, byte, shaping or raw-outline caches.

Keep cubic_outline() and fragmented_glyph() as reusable exact-font operations. Keep contour sequence search, its 4096/32 bounds, scale/baseline consistency, spacing tolerances and ambiguity rejection in the matcher. Update infer_vector_text_cues() and directly related consumers together.

The matcher returns geometric text evidence. Event construction, cue timing, paint selection, ownership and _fit_vector_text_outline()'s source-dependent fit cache remain in their existing passes. Explicitly preserve the useful lifetime of alphabet-profile caching rather than silently rebuilding profiles for every drawing or mixing source-dependent evidence into a font cache.

**Prompt**

Please separate exact-font outline decoding from FontMetrics. Move decode_cubic_outline() and its alphabet-profile cache into a focused matcher using the shared font owner, and update vector-text consumers together. Keep event-specific fit caches, ownership, paint and timing in the existing passes. Preserve contour, spacing, ambiguity and bounded-search decisions, avoid duplicate font caches, and run focused and full regression checks.

## Release 3 — Finish row fitting, reporting and integration

Move recover(), recover_tracked(), fragment_anchor(), authored_glyph_positions(), matches_authored_glyph_positions() and fit_fullwidth_run() into a cohesive row-geometry section using FontMetrics explicitly. Ordinary functions are the default: these algorithms do not need a second cache-owning service. Keep the useful relationship between authored_glyph_positions() and its validation helper; do not mechanically inline every small helper.

Migrate callers and remove the remaining FontSpacing abstraction in the same release. Keep renderer choices, source ownership, timing and accepted-caption construction with the passes. Preserve existing result semantics, guards and numerical thresholds; introduce result records only where added diagnostic evidence makes them useful.

Move merged and missing reporting out of font caches. Preserve all four accepted-row increment sites and the existing missing-font discovery sites, including unsuccessful proposals. Missing is currently selective: a failed matching_face() call does not always generate a diagnostic. Do not broaden that policy or equate rows joined with events removed. Use explicit pass results or an explicitly owned reporting collector, choosing the simpler fit for the existing callers.

Define per-conversion evidence and CLI-batch aggregation, including repeated use and failed conversions. Preserve current externally visible counts and diagnostic output; font caches may remain shared across files. Incorporate the final contract review and documentation in this release, rather than scheduling a separate cleanup release.

**Prompt**

Please finish separating subtitle row geometry and reporting from font measurement. Move the remaining FontSpacing row-recovery and anchor-fitting algorithms into a coherent section using FontMetrics explicitly, update callers, and remove FontSpacing without forwarding shims. Give row-join counts and selective missing-font diagnostics explicit ownership, preserving rejected-proposal evidence and batch reporting behavior. Review the final dependency and cache contracts, document them, and run focused and full regression checks.

## Verification required in every release

Run focused checks for affected behavior, the complete current regression suite, and all seven full subtitle comparisons against the immediately preceding release. Compare output bytes, statistics and relevant diagnostic behavior; exclude only version identity and measured execution duration. Extend checks for new cache/report ownership boundaries and unavailable backend paths. Test harnesses should follow the new interfaces without weakening semantic assertions.

Keep numeric algorithms, thresholds, cache keys and admission decisions unchanged unless an independently demonstrated bug requires a separately explained fix.

## Why three releases

Font discovery and caching belong in the same release as their backend-access consumers. Outline decoding is independently bounded and has a distinct cache lifetime, so it deserves its own release. Row algorithms, their reporting side effects, final naming and integration must migrate together; dividing them would prolong transitional APIs. Initial inventory is completed by this plan, and final documentation/review belongs with release 3.

The deferred catalog/text replacement API review and pass-local indexes review remain outside this work.

