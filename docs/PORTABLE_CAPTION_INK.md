# Portable caption ink — v173

The supplied Sword S01E01 track 3 simplified subtitle is reproduced exactly
(after newline normalization) by v172 with Pillow forced to BASIC and real
uharfbuzz available. The Skill Bank backdrop at 04:15.86–04:18.86 is absent.
The RAQM result already contained the panel: the reconstruction fix had not
been removed, but its exact caption-ink refinement was RAQM-only.

Without that refinement the conservative vertical bounds are 251–487, outside
the composite's 273–474 bounds. Direct HarfBuzz now supplies actual shaped glyph
extents from the same measured face, with glyph offsets, advances, baseline y
conversion and outward rounding. Horizontal bounds also retain advance space
and overhangs, matching the established Pillow convention. It reuses the
existing shaping font; there is no new font lookup, cache or public interface.

Only FontMetrics.line_ink_metrics changes production behavior. Missing fonts,
unmeasured faces, unsupported direction, missing glyphs/extents, vertical
advances and empty ink remain unknown. Blank lines keep their slots. Existing
font selection, width shaping, row reconstruction, panel grouping, colour
admission, containment, timing, vector budgets and caption ordering rules are
unchanged. More accurate ink can intentionally recover other supports on this
backend; no global cross-backend byte-equivalence guarantee is assumed.

Verification:

- At the v173 regression update, all 56 scripts passed on the required Windows-style
  backend and RAQM, with real uharfbuzz installed. The current v174 suite has 57 scripts.
- 86 portable ink checks include the actual Skill Bank source, full focused
  conversion, measured/raster bound comparisons on three fonts and controlled
  rejection/rounding/offset cases.
- All eight complete RAQM conversions and statistics match v172 exactly.
- Full Sword conversion with BASIC/HarfBuzz restores the same Skill Bank
  rectangle as RAQM. The only other change is insertion of an existing Set
  Skills support before an additional associated caption; its geometry, timing
  and layer are unchanged.
- The restored frame was rendered with libass at 04:17 and visually inspected.

The new actual-source fixture and Nyala font are bundled. Historical structural
audits retain their closing-stage contracts; the new regression separately
proves that this release changes just the ink method and release identity.
