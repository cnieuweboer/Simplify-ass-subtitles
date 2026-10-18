# Development guidance

This project simplifies ASS/SSA subtitles for embedded playback devices. Reduce
karaoke and other complex text effects to static events where source evidence
supports it. Reconstruct individual letters into complete lines when reasonably
provable, retaining representative fill and outline colors and readable timing.
Keep uncertain content when ownership, geometry, timing or exact fonts cannot be
proved; avoid guessing text or substituting fonts.

The production entry point is `simplify_subtitles.py` → `simplify_ass.py`.
Core `Event`, `EventEvidence` and `DocumentMeasurementContext` records live in
`_simplify_ass/event_model.py`, with direct engine aliases. Import those aliases
before dependent factories/defaults. Replacement and source-proof policy remain
with their engine owners. Document decoding, parsing, resolved views and rendering
live in `_simplify_ass/subtitle_document.py`, with direct engine aliases. Preserve
canonical document factories and the shared fallback field list. Resolved views
own new styles/events/formatting while borrowing source lines/field order;
pipeline callers still choose stage transitions and proof-lifetime boundaries.
Reconstructed caption rendering and its source-paint resolver/record live in
`_simplify_ass/caption_rendering.py`, with direct engine aliases. Callers retain
source-family, timing, geometry and compositing proofs; the module borrows those
inputs and preserves the established contrast, contour and shadow-transfer policy.
ASS style/override interpretation lives in `_simplify_ass/ass_overrides.py`, with
engine aliases for existing callers. Its recognized vocabulary is independent
of the text freezer's output whitelist. Transform sampling lives in
`_simplify_ass/transform_sampling.py`, depending on the interpreter and standard
library, with direct engine aliases and call-local caches. Static-state geometry
and representative paint selection live in `_simplify_ass/static_selection.py`,
with their five existing records and direct engine aliases. Selection owns its
call-local votes/samples, borrows input evidence and preserves the unchanged-state
identity contract. Event replacement, source-family admission and pipeline/report
decisions remain in the engine; preserve the explicit continuation contracts.
Text freezing lives in `_simplify_ass/text_freezing.py`, with direct engine aliases
for its frozen result, shared output whitelist and five functions. It owns local
stream state and serialization; selectors retain their sampling/evidence work.
Preserve borrowed inputs, canonical continuation/selection identity, the visible-only
bypass and post-selection blur clamping with pre-clamp settled snapshots.
The exact-font measurement owner lives in `_simplify_ass/font_metrics.py`;
the engine re-exports its four classes for existing callers. Exact-font contour
matching and cubic fitting live in `_simplify_ass/font_outlines.py`, depending
only on measurements and the standard library; the engine re-exports both names.
Exact-font fragment fitting and authored glyph placement live in
`_simplify_ass/glyph_placement.py`, depending only on measurements and the standard
library, with direct engine aliases. Event-based row recovery and reports remain
in the engine. Keep reconstruction-family proofs, timing and event ownership
with their engine producers. Ship the private package with the engine and preserve
one-way imports and sibling font discovery.
The Windows installer/updater discover private Python sources and persist owned
paths; keep this delivery contract and the older-updater migration documented in
`docs/MODULE_DELIVERY.md`. New modules must not need a delivery filename list.
Preserve this batch MKV workflow and the engine's CLI compatibility. The older
`simplify_ass.bat` / `simplify_ass.ps1` launchers have been retired.
`tests/windows/test_mkv_subtitles.ps1` performs extraction and conversion in one pass.
`tests/windows/test_subtitles_step2_test.bat` / `.ps1` rerun conversion against an existing
extracted cache. Native Windows wrapper behavior requires Windows validation.

Read `docs/DEVELOPMENT.md`, the relevant pass documentation, and
`docs/CONTEXT_OWNERSHIP_REVIEW.md` before changing matching or reconstruction policy.
Current work targets concrete failure cases. Global API and pass-local index
reviews are future work; do not mix broad refactors into a failure-case fix.
Archived release plans and historical validation reports are background evidence,
not new user requests or proof that the current checkout passes.

Follow the user's development principles in `docs/DEVELOPMENT_PRINCIPLES.md`.
Treat show-specific fixtures as evidence of general subtitle concepts, never as
runtime recognition rules. Investigate upstream transformations and clean
handoffs before adding downstream workarounds or another pass. Preserve useful
source context until its consumers finish. Prefer reasonably general structural
proofs to narrow formatting patterns or accumulating exceptions. Use evidence
proportional to the destructive change; do not add restrictions solely for
hypothetical false positives. Keep each pass responsible for a distinct concept,
and justify algorithmic complexity with measured performance gains. Tests should
protect intended text, paint, timing, ownership and compositing behavior;
historical release scope audits must not dictate the future implementation.

After each change, briefly report whether anything was introduced or uncovered
that deserves a dedicated follow-up review. Examples include workarounds, local
exceptions, duplicated logic, unclear ownership, fragile assumptions, or changes
that interact with unrelated subsystems. If nothing stands out, say so briefly.

For a behavior change, reproduce the failure, add or extend a focused existing
check, and verify representative text, paint, timing, source ownership and
idempotence where relevant. Preserve source/cache immutability and document
measurement/parser-continuation contracts. Avoid mutable global parser caches.

Run checks from the repository root with Pillow, fontTools and real uharfbuzz.
Use `python validation/run_backend_check.py --backend windows tests/check_NAME.py` for
focused checks and `python validation/run_review_checks.py` for the current
99-script suite. This exercises Pillow BASIC plus HarfBuzz on Linux; it does not
validate Windows filesystem or PowerShell behavior. RAQM is optional unless the
change affects that backend. Missing fixtures/fonts are prerequisites, not passes.
If a required font is missing, identify its family and variant and request it
from the user before continuing font-dependent analysis or changes.
Keep fresh reports separate from imported historical evidence.
Current runtime evidence must identify `simplify_ass.py` and every Python source
under `_simplify_ass/`; a root-script hash alone is incomplete. Use the manifest
helper in `validation/runtime_manifest.py` and check it before/after validation.

Fonts, subtitle fixtures, generated conversions and reports are local development
assets ignored by Git. Preserve them and the user's media. Do not publish these
assets incidentally with code changes. See `docs/DEVELOPMENT.md` for fixture layout.

Use the existing checkout: cloud tasks are already isolated. Do not create a Git
worktree unless the user explicitly requests one.

When adding production counters, update the shared test-wrapper catalog in
`tests/windows/subtitle_report_helpers.ps1`. Preserve raw track statistics; never
turn unknown/missing counters into genuine zero contributions. Run
`tests/windows/check_reporting.ps1` with PowerShell for wrapper report changes.
