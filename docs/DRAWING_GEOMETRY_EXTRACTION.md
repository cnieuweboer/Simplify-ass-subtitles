# v229 — Drawing geometry and contour normalization extraction

Runtime version: `2026.10.19.229`.

Following the [bounded assessment](DRAWING_GEOMETRY_EXTRACTION_ASSESSMENT.md),
`_simplify_ass/drawing_geometry.py` owns eight unchanged functions:
`coverage_geometry()`, `polygon_covers_box()`, `drawing_polygon()`,
`fit_rectangular_contour()`, `normalize_drawing_alignment()`,
`flatten_rectangular_border()`, `detach_drawing_edge_slivers()` and
`simplify_drawing_contour()`. Direct engine aliases preserve the 18 existing
engine consumers. No current test observer or existing assertion needed changes.

## Responsibilities and data flow

The module depends on the standard library and existing private owners for
override patterns, anchors, canonical events/replacement and `geometry_key()`.
The latter stays in static objects; it is neither duplicated nor relocated.
There are no reverse engine imports, forwarding adapters, callbacks, new
contexts or result hierarchies. Cold processing needs no optional font backend.

Event/document inputs remain borrowed and buffers stay local. Conservative
footprints preserve drawing scale, stroke/shadow clearance and the distinction
between being coverable and proving opaque coverage. Straight contours, curve
control-point bounds, raw path coordinates and transformed scene coordinates
keep their distinct contracts. Unsupported syntax, uncertain geometry,
unscaled strokes, rotations, interior slivers and independent artwork retain
their existing refusal behavior.

Alignment and border normalization return the same event successors through
canonical replacement/invalidation. Contour reduction returns the same reduced
raw path and original scene-space points. The supporting-drawing producer still
owns freezing, normalization order, source admission, movement, original-contour
storage, grouping, paint composition and counters. Its finalizer attaches
original-contour evidence after group/sequence reduction. Caption support
consumers still prove measured coverage, timing and compositing. Font/cache and
diagnostic ownership remain unchanged; no dataclass moves.

Both production and legacy callers retain their stage points and arguments.
No tolerance, simplification policy, CLI setting or counter changed.
`simplify_subtitles.py` and installer/updater implementations are unchanged.

## Validation

`validation/check_drawing_geometry_extraction.py` records the one-release
movement audit: eight identical moved definitions, unchanged remaining engine
AST except import/version, and byte-identical pre-existing private modules.
This historical audit is excluded from routine checks and does not constrain
future justified changes.

Eight module checks cover canonical aliases/types and old root lookup, drawing
scale/stroke/shadow bounds, hidden paint channels, curves, unknown paths,
boundary contact, alignment/stroke successors, immutable borrowed inputs,
sliver refusal, contour reduction and producer-owned evidence/counter lifetimes.
Cold execution verifies real dependencies without font backends. Installed
execution uses an unrelated working directory and a path containing spaces;
owned uninstall removes the module/cache while preserving a user file.

Release acceptance requires the full 105-script Windows BASIC plus real HarfBuzz
suite on Linux, including native libass checks, and fresh paired v228/v229
conversions of all 13 corpus tracks with identical bytes and complete statistics.
Runtime and harness manifests must remain unchanged during validation, and
required-font guards must reject missing exact faces rather than accepting them.

Delivery checks cover recursive Python/PowerShell manifests and the actual
shipped v214 updater against a v228 installation: a simulated locked new module,
exact rollback, retry, preserved launcher choices/user files, isolated installed
geometry and owned uninstall. Native Windows-only checks remain distinct skips
on this Linux host. The MKV extraction/simplification/remux/font-sync smoke test
also exercises the prepared environment.

Fresh runtime/input hashes, reports and logs are local to the ignored directory
`validation/drawing-geometry-extraction/`. Fixtures, fonts and generated
conversions remain local assets.

Completed validation against the final 18-source runtime manifest: all 105
regression scripts passed, including the eight new module checks and all native
render checks. Existing test assertions and observer bindings were unchanged.
All 13 fresh v228/v229 corpus pairs were byte-identical with identical complete
statistics. All 124 font hashes were verified, with no missing required fonts.
Runtime and test inputs remained unchanged throughout validation.

Installer checks passed 32 with two native Windows skips; updater checks passed
10 with one native Windows skip. Actual shipped-updater rollback/retry, isolated
installed geometry/uninstall, Python/PowerShell manifest agreement and the MKV
smoke test all passed. Native Windows filesystem and launcher behavior remains
unverified on this Linux host.

## After-release evaluation

The extraction retains one contour-processing owner and explicit producer-owned
admission/evidence/reporting boundaries. No production workaround, duplicated
proof, downstream repair, test-binding adaptation or unrelated subsystem change
was needed. No dedicated corrective review is currently indicated. Broader API
and pass-local index reviews remain separate.
