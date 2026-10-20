# Masked-glyph font resource cleanup — v236

The resource-lifetime gap found during the v235 extraction assessment is fixed
at the existing masked-glyph owner in `simplify_ass.py`. The runtime version is
`2026.10.20.236`; this release does not extract or redesign the subsystem.

## Ownership and failure behavior

Previously, `_masked_glyph_outline()` opened an exact font and evaluated
`getGlyphSet()` before placing the handle in `MaskedGlyphContext.fonts`. If
initialization raised, the existing conservative refusal caught the error but
normal pass cleanup could not see or close that handle.

A nested cleanup guard now retains local ownership until glyph-set initialization
and cache registration succeed. A failure closes the newly opened handle and
re-raises into the existing unsupported-outline handling. Interruptions also
close that temporary handle and propagate. Only successfully initialized handles
transfer to the existing pass-owned cache.

The related cleanup boundary is now explicit: `remove_masked_glyph_effects()`
closes registered handles in `finally`, including an unexpected proof error or
interruption. Normal cleanup remains before output-list construction. This keeps
resource ownership with the producer that opened the fonts; the supplied metrics
owner remains borrowed.

Exact-font matching, contour/anchor proofs, source lifetimes, deletion admission,
per-glyph negative caching and retry behavior remain unchanged. A failed glyph
still cannot authorize removal, while another glyph may initialize successfully
on a later attempt. No face-level failure cache, new result/context, downstream
repair, diagnostic or reporting counter is introduced.

## Validation

The extended `tests/check_masked_glyphs.py` first failed against v235 because an
opened handle had no matching close after glyph-set initialization failed.
Nine current-policy resource cases now cover:

- Successful shared-handle reuse and cached draw failure.
- Opening failure without a returned handle.
- Repeated initialization failure for one glyph, distinct failed glyphs and a
  later successful glyph after an initialization failure.
- Initialization interruption, later proof failure and later proof interruption.

The checks use a generated exact font and injected failures, verify close counts,
unchanged input events and visibility, conservative retention, recovery and
exception propagation. These resource assertions are separate from the existing
686 historical behavior/call comparisons and two focused conversions. The old
comparisons retain their existing failure modes and call-count expectations;
the leaking historical behavior is not used as a desired resource oracle.

Acceptance requires the full 109-script Windows BASIC plus real HarfBuzz suite
on Linux, including native rendering, and fresh v235/v236 conversions of all 13
corpus tracks with identical bytes and complete statistics. Required-font guards
and 124 recorded font hashes protect corpus prerequisites. Complete runtime and
harness manifests must remain fixed throughout validation. Private evidence
remains under ignored `validation/masked-font-cleanup/`.

Completed final-source validation: all 109 regression scripts passed, including
native libass rendering, all nine resource lifecycle cases, 686 historical
masked-glyph comparisons and two focused conversions. Runtime and harness inputs
stayed unchanged throughout the run. Only the two resource-owning functions and
the root version differ from v235; all 21 private modules and the batch wrapper
and delivery code remain unchanged.

All 13 fresh v235/v236 corpus pairs are byte-identical with identical complete
statistics. All 124 recorded font hashes were verified, with no missing
required-font diagnostics. Installed resource proofs, shipped-updater
rollback/retry, owned uninstall, Python/PowerShell runtime-manifest agreement
and the MKV extraction/conversion/remux/font-sync smoke workflow passed.
Installer checks passed 32 with two native Windows skips; updater checks passed
ten with one native Windows skip. Native Windows filesystem and launcher
behavior remains unverified on this Linux host.

## After-release evaluation

The fix establishes temporary-to-pass handle ownership at its existing producer
and unconditional cleanup at the pass boundary. It needs no workaround, duplicate
cache, matching exception or unrelated subsystem change. The related pass-exit
cleanup was addressed in this release; no further dedicated review was identified.
The previously recorded scrolling single-use iterator contract remains separate.
