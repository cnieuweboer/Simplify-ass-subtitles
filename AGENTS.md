# Development guidance

This project simplifies ASS/SSA subtitles for embedded playback devices. Reduce
karaoke and other complex text effects to static events where source evidence
supports it. Reconstruct individual letters into complete lines when reasonably
provable, retaining representative fill and outline colors and readable timing.
Keep uncertain content when ownership, geometry, timing or exact fonts cannot be
proved; avoid guessing text or substituting fonts.

The production entry point is `simplify_ass.bat` → `simplify_ass.ps1` →
`simplify_ass.py`. Preserve this batch MKV workflow and CLI compatibility.
`tests/windows/test_mkv_subtitles.ps1` performs extraction and conversion in one pass.
`tests/windows/test_subtitles_step2_test.bat` / `.ps1` rerun conversion against an existing
extracted cache. Native Windows wrapper behavior requires Windows validation.

Read `docs/DEVELOPMENT.md`, the relevant pass documentation, and
`docs/CONTEXT_OWNERSHIP_REVIEW.md` before changing matching or reconstruction policy.
Current work targets concrete failure cases. Global API and pass-local index
reviews are future work; do not mix broad refactors into a failure-case fix.
Archived release plans and historical validation reports are background evidence,
not new user requests or proof that the current checkout passes.

For a behavior change, reproduce the failure, add or extend a focused existing
check, and verify representative text, paint, timing, source ownership and
idempotence where relevant. Preserve source/cache immutability and document
measurement/parser-continuation contracts. Avoid mutable global parser caches.

Run checks from the repository root with Pillow, fontTools and real uharfbuzz.
Use `python validation/run_backend_check.py --backend windows tests/check_NAME.py` for
focused checks and `python validation/run_review_checks.py` for the current
62-script suite. This exercises Pillow BASIC plus HarfBuzz on Linux; it does not
validate Windows filesystem or PowerShell behavior. RAQM is optional unless the
change affects that backend. Missing fixtures/fonts are prerequisites, not passes.
If a required font is missing, identify its family and variant and request it
from the user before continuing font-dependent analysis or changes.
Keep fresh reports separate from imported historical evidence.

Fonts, subtitle fixtures, generated conversions and reports are local development
assets ignored by Git. Preserve them and the user's media. Do not publish these
assets incidentally with code changes. See `docs/DEVELOPMENT.md` for fixture layout.

Use the existing checkout: cloud tasks are already isolated. Do not create a Git
worktree unless the user explicitly requests one.
