# v230 — Shared event comparison owners

Runtime version: `2026.10.19.230`.

Following the [bounded assessment](EVENT_COMPARISON_EXTRACTION_ASSESSMENT.md),
`text_height()`, `placement_key()`, `text_layout_key()` and
`compatible_text_layout()` now live in `_simplify_ass/caption_geometry.py`;
`state_key()` lives in `_simplify_ass/event_operations.py`. Direct engine
aliases preserve existing callers, signatures and defaults. The five unchanged
definitions serve 116 distinct engine functions. No new module was needed.

## Responsibilities and data flow

This is preparation for later subsystem extraction. It gives widely shared
layout/state operations existing foundational owners without assigning them to
one drawing, echo, scrolling or row pass. The remaining larger subsystem
boundaries still need their own dependency assessments; this release does not
move orchestration, effect parsing or frame-sequence reduction.

The helpers borrow resolved formatting, metadata and inputs as-is. They do not
parse source text, install caches, measure fonts, extend evidence or retain
pass results. `caption_geometry` adds only the canonical `DEFAULT_STATE` import;
`state_key` needs only its existing canonical event annotation and built-ins.
Dependency direction remains one-way. No adapters, callbacks, reverse engine
imports, new contexts, dataclasses or result hierarchies were introduced.

The matching contracts remain separate:

- Nominal height retains the unit floor and absolute font-size/vertical-scale
  formula; it does not establish exact glyph bounds or caption coverage.
- Placement retains explicit/inherited margins, clips and raw inline-layout
  distinctions.
- Exact layout retains its field list and default fallbacks. Tolerant layout
  retains placement equality, case-insensitive font names, exact orientation
  and its existing size/scale comparison.
- Resolved-state identity retains sorted entries, supplied omissions,
  underscore exclusions and six-decimal numeric/one-level tuple normalization.
- Complete-span identity and pose validity retain their separate literal,
  continuation, geometry and numeric contracts. No keys were consolidated.

Callers still select the appropriate comparison and own indexes, font caches,
source evidence, diagnostics, counters and stage order. Existing tuples,
booleans and nominal-height values are returned unchanged. `simplify_subtitles.py`,
installer/updater implementations and CLI settings are unchanged.

## Validation

`validation/check_event_comparison_extraction.py` records this release's movement
audit: identical moved definitions, unchanged remaining engine AST except
imports/version, unchanged owner implementation except the added canonical
default-state import, and byte-identical other private modules. This historical
audit is excluded from routine checks and does not constrain future changes.

Existing caption-geometry and event-operations module checks were extended;
their previous assertions remain intact. Coverage includes canonical aliases,
old root function lookup, explicit/inherited margins, clips and inline guards,
exact versus tolerant layout, orientation and size boundaries, default fields,
height floors, empty caches, state omissions and mixed numeric/vector values.
The differing state/pose precision contracts are checked explicitly. Inputs,
omit sets, document catalogs and source evidence remain borrowed.

Cold checks run without optional font backends. Installed checks use paths with
spaces and an unrelated working directory, exercise all five moved functions,
and verify owned module/cache removal while preserving a user file. Existing
measurement coverage remains in place.

Acceptance requires the full 105-script Windows BASIC plus real HarfBuzz suite
on Linux, including native rendering, and fresh paired v229/v230 conversions of
all 13 corpus tracks with identical bytes and complete statistics. Runtime and
harness manifests must remain unchanged, and required-font guards reject
missing exact fonts rather than accepting fallback results.

Delivery validation covers recursive Python/PowerShell manifests and the actual
shipped v214 updater against a v229 installation. Each modified owner is
separately simulated as locked, requiring exact rollback, followed by successful
retry. Launcher choices/user files, isolated installed comparison behavior and
owned uninstall are verified. Native Windows-only checks remain distinct skips
on Linux; the MKV extraction/simplification/remux/font-sync smoke test exercises
the prepared workflow.

Fresh manifests, reports and logs live locally in the ignored directory
`validation/event-comparison-extraction/`. Fonts, fixtures and generated outputs
remain local development assets.

Completed validation against the final 18-source runtime manifest: all 105
regression scripts passed, including 10 caption-geometry and 9 event-operations
module checks and all native rendering checks. Existing assertions and observer
bindings were retained. All 13 fresh v229/v230 corpus pairs were byte-identical
with identical complete statistics; all 124 recorded font hashes were verified
with no missing required fonts. Runtime and harness inputs stayed unchanged.

Installer checks passed 32 with two native Windows skips; updater checks passed
10 with one native Windows skip. Actual shipped-updater rollback for each
modified owner, retry, isolated installed processing/uninstall, manifest
agreement and the MKV smoke test all passed. Native Windows filesystem and
launcher behavior remains unverified on this Linux host.

## After-release evaluation

The existing owners preserve the distinct comparisons and their read-only
contracts; consumers retain all pass responsibilities. No production workaround,
duplicated proof, observer adaptation or unrelated subsystem change was needed.
No dedicated corrective review is currently indicated. Larger subsystem
extraction and the deferred API/index reviews remain separate planned work.
