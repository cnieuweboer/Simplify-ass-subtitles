# Comments and documentation review — v168

The review covered the production script's comments and docstrings, current
contract documents, release notes, historical plan and launcher documentation.
The changes describe existing behavior; no simplification policy or API changed.

## Corrections

- Visibility documentation now covers all five completed result contracts,
  including accepted equal-value assignments, protected row adoption and the
  shared-interval pass's private overlay. Pending updates are isolated on failure;
  explicitly caller-owned font reporting retains its separate accumulation rule.
- Parser documentation describes returned evidence accumulation without suggesting
  that selection appends to caller-owned seeds. Immutable continuation is
  distinguished from mutable formatting containers borrowed read-only.
- Font documentation describes the completed FontMetrics, FontOutlineMatcher and
  row/report boundaries. Matcher sharing is explicit: CLI batch reuse and optional
  Python caller reuse, otherwise conversion-local ownership. Backend fallback is
  described without promising identical measurements on every backend.
- The FontSpacing plan is explicitly historical and completed. Release-specific
  validation remains labeled with its original release; README.md records current
  validation and links the current contracts.
- Older source comments now distinguish the basic text tag whitelist from visual
  freezing, and the text-stage drawing candidate pool from later reconstruction.
  Contour evidence continues into support selection without serialization. Support
  insertion uses source and normalized-document index spaces. Enclosing-panel
  language makes no assumption about the backdrop's color or material.

Correct existing explanations of thresholds, proof guards, parser order,
replacement rules and rendering choices were retained. Intentional historical
report-key aliases and deprecated legacy code remain documented as such.

## Evidence and scope

`check_documentation_only.py` compares the complete current executable AST with
immutable v167. It excludes only leading module/class/function docstrings and the
version assignment; all other literals, signatures, expressions, guards and
statements remain significant. The AST is identical. Older extraction audits now
use the same test-only docstring normalization, preserving their algorithm and
bounded-change assertions.

All 50 current regression scripts pass, including 115 pixel-identical libass
comparisons. Seven complete subtitle outputs/statistics are identical to v167 and
v156; six fixture diagnostics/logs/summary match v167 apart from engine identity
and duration. Full conversions used the established complete font catalog.

BAT changes are release banners only; PowerShell wrappers and fixture inputs are
unchanged. Validation checks source hashes, Python syntax and the archive manifest.
The canonical engine identifies itself as **2026.10.11.168**. Evidence is in
`validation/documentation-only-checks.json`, `complete-regression-checks.json`,
`full-conversion-comparison.json` and `package-checks.json`.
