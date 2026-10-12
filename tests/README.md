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
Their default converter paths point back to the production script at the root;
the step-two batch launcher defaults to root-level `cache/` and `results/`.
