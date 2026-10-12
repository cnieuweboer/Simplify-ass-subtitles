# Regression targets

Windows is the primary target. Run:

```sh
python validation/run_review_checks.py
```

The default runs the current suite with Pillow BASIC and real uharfbuzz, exercising the Windows font measurement path on this host. A missing uharfbuzz dependency is an error. RAQM is an occasional explicit run:

```sh
python validation/run_review_checks.py --backend raqm
python validation/run_review_checks.py --backend both
```

Install dependencies with `python -m pip install Pillow fonttools uharfbuzz`.
Reports are saved by selected backend. Release verification requires the complete Windows pass and matching runtime/harness hashes; it does not require RAQM.

This exercises the Windows font backend. Native Windows filesystem, process and PowerShell behavior still require Windows execution.
