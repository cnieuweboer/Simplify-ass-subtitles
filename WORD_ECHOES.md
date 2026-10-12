# V176: owned word echoes

Remove explicit fading or jittering word frames only after stage 1 accepts their complete caption. Complete-line consolidation returns its accepted caption owners directly; no formatting state stores ownership.

The focused matcher reuses exact FontMetrics, authored_glyph_positions, index_fragment_spans and fit_fragment_anchor. It returns CoveredFragmentRemoval, and adds removals to the existing covered_fragments statistic. It runs before generic frame coalescing loses source lifetimes. No general opacity protection or paint selection changes.

A family must have uniform authored paint and layout, original literal text and timing, at least three distinct consecutive short frames and eight samples total. Frames are at most short_duration (default 0.16 seconds). Overlapping copies must agree on primary alpha. A fade increases monotonically from alpha at most 128 to at least 224, with a rise of at least 64; otherwise a faint jitter family requires alpha at least 128 and two direction reversals. Static opacity alone is insufficient.

Displacement is bounded over the entire family to 0.06 of font height on each axis, and every anchor must fit one exact substring occurrence within the same tolerance. The supplied word frames span almost 4 script pixels at height 78; the limit is 4.68 pixels. Repeated words are separate measured positions. Contiguous literal matching prevents crossing authored spaces. No substituted font authorizes deletion.

A family begins inside its retained cue and overlaps it by at least min(0.16s, half the family span). Only faint frames (alpha at least 128) may continue after it, by at most 0.8s. The family may last longer while its parent remains active: the supplied `me` fade lasts 2.63s. The caption's own interval is unchanged. Competing full-line/substring owners preserve the whole family.

Missing exact fonts, animation tags, clips, rotations, inline gradients, mismatched geometry/layout, inconsistent or incomplete frames and ambiguous ownership retain existing behavior.

The original IM FELL English PRO Roman OpenType font, version 3.00, is included with its embedded license and provenance; no font data was modified. The Fell Types are digitally reproduced by Igino Marini. www.iginomarini.com

Validation uses Windows BASIC plus real HarfBuzz. Full sources, font hashes, focused checks, corpus reports and libass diagnostics are bundled. The archived Witch Hat input differs from the current full original, so that fixture uses a fresh v175 reference conversion of the same current source. Other baselines reuse their verified saved output bytes.

The opening glyph lifecycle pass remains stage 3. No color normalization is added here.
