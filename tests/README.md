# Regression checks

Run checks from the repository root. Python checks and their shared helpers live
here; production modules remain at the root. `test_paths.py` makes production
modules importable when a check is executed directly.

```sh
python validation/run_backend_check.py --backend windows tests/check_glyph_lifecycles.py
python validation/run_review_checks.py
```

Restore local fonts and fixtures as described in
[the development guide](../docs/DEVELOPMENT.md). The suite inventory under
`validation/` distinguishes current checks from historical harnesses.

Windows batch-testing and PowerShell reporting scripts are in `windows/`.
They look for `simplify_ass.py` beside themselves, at the repository root, then
on PATH (including the Windows installer's `bin` layout). `-Simplifier` overrides
lookup. The step-two BAT defaults to `cache/` and `results/` beside the BAT.

```powershell
.\tests\windows\check_simplifier_lookup.ps1
.\tests\windows\check_test_settings.ps1
```

Standalone track/property checks:

```sh
python tests/check_subtitle_tracks.py
python tests/check_subtitle_properties.py
python tests/check_sync_fonts_validation.py
```

These cover automatic detection, manual selection, review/cancellation, output
exclusions, source changes, error cleanup, and warning/verification handling.
With `mkvmerge` on PATH they also create temporary MKVs and exercise real remuxes
with subtitles, audio, attachments, and chapters (plus video when FFmpeg is
available). No corpus fixtures or user media are required or modified.

Font validation checks use generated fonts to cover readable outlines with
nonconforming optional tables, damaged required tables, and font collections.

Historical parser/ownership comparisons may explicitly exclude contour fields
that changed in v198; they run the current renderer. Full input-immutability
checks and current-policy paint/native checks retain contour values. See
[the v199 coverage notes](../docs/CURRENT_POLICY_INTEGRATION_COVERAGE.md).

Windows simplification test wrappers use the engine's own scrolling/color defaults.
Set optional overrides in PowerShell or the blank fields near the top of the step-two BAT.
