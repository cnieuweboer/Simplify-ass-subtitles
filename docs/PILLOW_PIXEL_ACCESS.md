# Pillow pixel access — v241

The settled-paint sampler now reads its grayscale masks with `Image.tobytes()`
instead of deprecated `Image.getdata()`. Every mask is mode `L`, so each byte
is exactly one pixel value in the existing row order. Indexing, weights, arithmetic,
layer ordering, rounding, sampled paint and refusal behavior are unchanged.
The buffers remain call-local, and Pillow remains a lazy dependency.

This uses a longstanding Pillow API rather than requiring the newer
`get_flattened_data()`, raising dependency requirements or adding a version-based
fallback. Three affected rendering checks also use byte-based RGB channel
iteration; the white-core comparison reads the corresponding pixel directly.
Archived reference engines remain historical snapshots.

The existing sampler module check now verifies successful, identical sampling
with both flattened-pixel APIs made unavailable. Compatibility probes on Pillow
10.4.0, 11.3.0 and 12.3.0 confirm identical grayscale and RGB values and order,
including antialiased/blurred/resized masks. All nine module checks pass under
each version with deprecations treated as errors. The first two versions lack
`get_flattened_data()`.

Native v240/v241 probes using the exact Volkhov regular face produce identical
caption bytes and all fifteen frame pairs across active/start/end boundaries.
The production wrapper, installer and updater remain unchanged.

All 1,253 captured sampling/pooling decisions match v240 exactly, with borrowed
inputs unchanged. All thirteen corpus tracks retain identical output bytes and
complete statistics; all 124 recorded font hashes were verified, with no missing
required-font diagnostics. All 113 regression scripts pass using Windows BASIC
plus real HarfBuzz on Linux, with no `getdata()` deprecation warnings. The full
26-source runtime and test harness stayed fixed throughout validation. Native
Windows filesystem behavior remains outside this Linux validation. Private
reports stay under ignored
`validation/pillow-pixel-access/`.

The compatibility follow-up identified in v239 is resolved. No adapter, local
exception, duplicated paint logic or new dedicated follow-up review is needed.
This change does not resume modularization or alter the separate scrolling
iterator and global API/index review items.
