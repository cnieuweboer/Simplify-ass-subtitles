# Shared settled-paint sampling — v239

The boundary assessed in
[CAPTION_PAINT_SAMPLING_EXTRACTION_ASSESSMENT.md](CAPTION_PAINT_SAMPLING_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/caption_paint_sampling.py`. The two existing helpers,
`_settled_caption_paint_samples()` and `_pool_source_caption_paint()`, moved with
all 91 definition lines unchanged. Engine names remain direct aliases, preserving
signatures and historical root pickle lookup. The unused root `BytesIO` import
was removed. Runtime version: `2026.10.20.239`.

## Responsibility and ownership

The module owns bounded settled-plane raster estimation and weighted complete-row
paint pooling. Glow and backed-glyph producers retain source-family, geometry,
timing, ordering, complete-row and ownership proofs, fallback decisions, evidence
lifetime and reporting. Plausible sampled paint does not authorize removal or
reconstruction. Neither producer depends on the other or repeats the estimator.

Events, styles/defaults, continuations, plane lists, metrics and accepted sample
lists remain borrowed. Transform replay uses private state copies. Masks, resized
ink, core/contour weights, settled-plane sorting and accumulators stay call-local.
Metrics retains font discovery, font-byte and em-scale caches. No persistent
sampling cache, resource abstraction, diagnostic owner or result hierarchy was
introduced. The metrics owner's existing interface is unchanged.

The canonical frozen `SourceCaptionPaint` stays in `caption_rendering` with its
existing border default and engine alias. The sampler imports that record in one
direction; caption serialization does not import the sampler. Both the weighted
tuple representation and producer-owned pooling preconditions remain unchanged.
Compositing still uses numeric layer/source order, independent of supplied list
order. BASIC mask layout, supersampling, shape refusals, size/blur limits, contour
width, rounding, alpha bounds and exception/refusal boundaries are unchanged.

The private import graph remains acyclic without engine imports, callbacks or
production forwarding. Pillow imports remain function-local; cold imports and
pooling do not import the engine or optional font backends. No `__file__` path or
font discovery policy moves. The existing interpreter observer now includes the
actual sampler consumer; its callers still use the engine aliases.

## Validation and delivery

Eight new module tests exercise canonical aliases/annotations/pickle lookup and
result ownership, known weighted pooling, exact synthetic-font sampling, settled
transform replay, borrowed input/state preservation, numeric layer/source order,
unsupported layout/paint, existing metric error boundaries, independent buffers,
actual interpreter observation and cold source/installed execution. A generated
font has its own exact family and face; these tests require no user-font
substitution. Cold children run from an unrelated directory with spaces in the
installation path. Owned uninstall removes source and bytecode while retaining a
user file.

Fresh paired v238/v239 backing/glow checks capture 1,253 identical sampling/pooling
decisions (194 backing, 1,059 glow) and unchanged borrowed inputs. Native and integration checks
remain active. A separate observer probe compares six actual transform calls and
the resulting sample. Additional exact-generated-font probes cover settled paint,
equal-layer source ordering and unsupported-layout refusal, checking numerical
results, identical serialized output and 15 pixel-identical native frame pairs
at active/start/end boundaries.

The unchanged shipped v214 updater installs v239 over v238, including rollback
when the new module is locked, retry, preserved user files/launcher choices,
isolated installed sampling/pooling and owned uninstall. Recursive Python and
PowerShell runtime manifests agree. Installer checks pass 32 with two native
Windows skips; updater checks pass ten with one native Windows skip. MKV font
extraction, conversion, remux/extraction and font-sync smoke checks pass.

Final-source validation passed all 112 regression scripts using Windows BASIC
plus real HarfBuzz on Linux. All thirteen fresh v238/v239 corpus pairs have
identical output bytes and complete statistics, with no required-font diagnostic.
All 124 recorded font hashes were verified. The full 25-source runtime and test
harness stayed fixed throughout validation. Both moved definition ASTs are
unchanged, all other root behavior is unchanged apart from aliases/imports/version,
and all 23 prior private sources remain byte-identical. The production batch
wrapper and delivery code also remain unchanged from v238. Private evidence stays
under ignored `validation/caption-paint-sampling-extraction/`. Native Windows
filesystem and launcher behavior requires separate Windows validation.

## After-release evaluation

Shared computation has a direct owner while both producers retain their distinct
proofs and handoffs. No adapter, duplicated proof, local production exception or
downstream repair was needed. The backed-glyph pulse subsystem can now be
reassessed with these shared dependencies outside the engine; this release does
not move it or prescribe the remaining module hierarchy.

One separate compatibility follow-up was observed: Pillow 12.3 emits a deprecation
warning for the existing three `Image.getdata()` calls in this sampler, scheduled
for removal in Pillow 14. Replace those calls and update affected rendering
checks in a bounded compatibility change, accounting for the project's supported
older Pillow versions and requiring identical samples/paint/rendering. This extraction deliberately preserves their
behavior. No structural corrective review was identified. The previously recorded
scrolling-iterator contract and global API/index reviews remain separate work.

The Pillow pixel-read follow-up is resolved in [v241](PILLOW_PIXEL_ACCESS.md).
