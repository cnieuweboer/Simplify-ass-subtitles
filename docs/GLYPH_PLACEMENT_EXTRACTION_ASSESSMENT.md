# Exact-font row fitting and glyph placement — extraction assessment

Historical assessment of v216. The smaller boundary was implemented in
[v217](GLYPH_PLACEMENT_EXTRACTION.md); the evidence below describes the assessment.

After examining all six functions, the recommended next implementation is
**v217: extract the three independent glyph-placement functions** into
`_simplify_ass/glyph_placement.py`, with direct engine aliases. They form a
117-line dependency boundary. The complete 354-line family needs additional
position, event-type and report decisions; those are unnecessary prerequisites
for the smaller extraction.

This is an assessment only. Production remains `2026.10.16.216`, with no changes
to the converter, batch wrapper, tests, installer/updater or existing modules.
The disposable probes described below remain private development evidence.

## Recommended boundary

| Function | Inputs and result | Dependency outside the three functions |
| --- | --- | --- |
| `fit_fragment_anchor()` | Borrows metrics, formatting, recorded x coordinates and literal fragments; returns an authored anchor or rejection. | `FontMetrics`, `unicodedata`, built-ins. |
| `authored_glyph_positions()` | Borrows metrics, formatting, text, an anchor and script-unit tolerance; returns a new list of nonspace character/anchor pairs or rejection. | `FontMetrics`, `unicodedata`, built-ins. |
| `matches_authored_glyph_positions()` | Compares recorded coordinates with the shared authored-position model; returns a boolean. | `authored_glyph_positions()`, `FontMetrics` for its annotation, built-ins. |

The module would import only the existing private measurement owner,
`unicodedata` and postponed annotations. It needs no engine import, `Event`,
position-tag parser, report, renderer or pass context. Its annotations resolve
without importing the engine. No `__file__` or sibling-font adjustment is needed.
The font owner continues to own resource discovery and measurement caches.

The numerical methods and signatures should move unchanged, including tracking,
separate-glyph and exact-size options, ASS scaling, whitespace treatment,
contextual-shaping/bidirectional/combining-character rejection and tolerances.
The functions borrow input state and coordinates; they retain no event evidence
and create no cache. The metrics owner's existing caches may still populate.
There is no new result dataclass, context, protocol or wrapper.

Keep these functions together because the boolean proof uses the same authored
position model, and fragment fitting interprets the same exact-font advance/
alignment convention. Keep contour decoding and alphabet-profile ownership in
`font_outlines.py`; that subsystem has a different contract. These are engine
implementation functions, so they belong under `_simplify_ass/`, not `shared/`.

## Why the full family is a wider task

| Function retained in the engine | Current additional dependency or behavior |
| --- | --- |
| `recover_font_row()` | Reads borrowed events' `.state` and `.text`, obtains anchors through `get_pos()`, and may add a missing exact family to the supplied report even when the proposal ultimately fails. |
| `recover_tracked_font_row()` | Reads `.duration`, delegates to spacing recovery, and uses `dataclasses.replace()` to create temporary records with a fresh zero-tracking state dictionary. The original records and their evidence remain borrowed. |
| `fit_fullwidth_run()` | Reads event formatting/position tags, writes selective missing-font diagnostics, and has the concrete annotation `ordered: list[Event]`. |

The first two do not construct `Event` directly. `dataclasses.replace()` retains
the actual input dataclass type and existing fields; substituting a new minimal
row object to remove that dependency would change the operation. Temporary
zero-tracking records are fitting views, not event successors applied to the
pipeline. Preserve that distinction in future work.

Position parsing is a real outgoing dependency of these functions:
`get_pos()` reads `POS_RE`, whose construction uses `NUM`. The new override
interpreter does not currently own those helpers. Avoid copying the parser into
a fitting module or adding callbacks just to make this extraction appear closed.
A future position-syntax boundary can be assessed on its own responsibilities.

The event annotation is postponed, so a module can initially import without an
`Event` binding. However, a disposable full-family probe demonstrated that
`typing.get_type_hints(fit_fullwidth_run)` then raises `NameError: Event`, whereas
it resolves to the current event type in the engine. No repository consumer was
found relying on that introspection; this demonstrates an interface difference,
not a production failure. A type-checking-only engine import does not preserve
runtime resolution. Dropping/changing the annotation, injecting engine globals
or adding a reverse runtime import is unnecessary for this structural step.

`Event` itself refers to `EventEvidence`, `DocumentMeasurementContext` and the
existing parser continuation record. A neutral model boundary may be viable,
but moving those types deserves its own assessment rather than being folded
into a numerical extraction for the sake of an annotation. This assessment does
not declare the complete family unextractable or prescribe that future hierarchy.

## Reporting remains with the current callers

`FontProcessingReport` stays in the engine for the recommended extraction. Its
physical location does not change the caller-owned lifetime described in
[ROW_GEOMETRY.md](ROW_GEOMETRY.md) and
[CONTEXT_OWNERSHIP_REVIEW.md](CONTEXT_OWNERSHIP_REVIEW.md).

The current code has four accepted-join increment sites, all outside these six
fitting functions. They commit accepted stage operations. There are four direct
missing-family insertion sites: spacing recovery, fullwidth fitting, glyph-slot
width discovery and vector-outline measurement. Tracked recovery inherits the
spacing diagnostic. These are selective discoveries, with their existing trim
rules; failed proposals can still contribute them. Reports accumulate across a
batch and after a later conversion failure, and are not rolled back.

The three recommended functions take no report and intentionally stay silent on
missing faces. Keep reporting, rendering, row assembly, timing, paint selection,
source evidence and edit application in their existing owners. Do not broaden
those responsibilities while moving the placement code.

## Consumer and test implications

The placement functions already receive their required evidence explicitly.
Consumers include translated phases, moving/boundary glyphs, glyph lifecycles,
source-caption correspondence, word echoes and vector cues. Keep their root calls,
signatures, pass ordering and existing results unchanged through direct aliases.

`tests/font_geometry_test_helpers.py` already dispatches current row calls through
the engine exports rather than inferring ownership from `FontMetrics.__module__`.
A simulated private-module boundary passed the current caller checks without a
functional adaptation to that helper. Its comment about physical function
location should reflect engine exports if touched during implementation.

Recorded/failure doubles are test behavior, not a reason to add row methods to
`FontMetrics` or forward private module calls through the engine. The internal
`matches_authored_glyph_positions()` → `authored_glyph_positions()` call will
resolve in the new module. If new instrumentation needs to intercept it, patch
that real binding as well as any relevant root alias; keep production independent
of monkeypatches. No existing selected test required such a repair in this probe.

The older broad row AST comparisons read frozen v165/v173 stages. Keep those
historical audits bounded to their releases. Add a v217 extraction audit against
the actual pre-extraction runtime and leave earlier one-release audits historical.

## Evidence collected

A disposable module contains the three unchanged definitions, importing the
existing measurement class and `unicodedata`. It imports from an unrelated working
directory without loading the engine, Pillow, fontTools or HarfBuzz; annotation
resolution also succeeds. The full-family probe adds position syntax and a copied
report declaration solely to expose the remaining event annotation dependency;
it is not a proposed production implementation.

The three-function prototype matched **2,016 exact-font comparisons** using the
available Arial face across alignments, sizes, tracking, whitespace, non-ASCII
text, unsupported text and fitting options. The authored-position probes included
**180 accepted cases**. Formatting inputs stayed unchanged and the prototype's
resolved annotations agree with the current functions.

Six current scripts also ran twice: once against the unchanged engine and once
with only the three root aliases temporarily rebound to the disposable module
inside isolated child processes. Both runs passed with the same summaries/counts:

- `check_font_row_geometry.py`: **4,925** checks, including all **1,080** algorithm
  cases, report/batch/failure contracts and focused conversions.
- `check_font_metrics.py`: **1,459** measurement ownership/parity checks.
- `check_translated_phases.py`: **138** comparisons, all 14 helpers exercised and
  eight cache assertions.
- `check_authored_lyric_ownership.py`: **7,014** checks over 740 cases and five
  focused conversions.
- `check_source_caption_alternation.py`: **130** source/lyric-boundary checks.
- `check_row_geometry.py`: **26** geometry checks.

These twelve executions exercise Windows BASIC plus real HarfBuzz on Linux.
They are not native Windows platform validation. The simulated aliases and
prototype are private probes; no production or test source was edited.

Private evidence is under `validation/glyph-placement-assessment/`:
`assessment.json`, `focused-checks.json`, disposable modules/drivers and logs.
Runtime and covered test-source hashes stayed unchanged. The full 92-script suite
and thirteen-track corpus were freshly validated for v216, with the same runtime
manifest; they were not rerun for this documentation-only assessment.

## Recommended v217 acceptance

One implementation release can extract the three functions without a preparation
release or a new model/position/report abstraction:

1. Capture the exact v216 runtime and verified corpus baseline. Move the three
   definitions unchanged; import the existing measurement owner and retain direct
   engine aliases. Keep annotations resolvable and other modules unchanged.
2. Add or extend focused checks for alias identity, independent import, annotation
   resolution, borrowed input preservation and internal model reuse. Reuse the
   existing measurement/row/caller coverage and adapt test lookup only where the
   actual move proves necessary.
3. Verify moved ASTs and the remaining engine against the baseline. Run the full
   Windows-font-backend suite and thirteen-track exact-font corpus comparison;
   require unchanged output and complete meaningful statistics.
4. Verify actual installed execution and v214-or-newer updater delivery, failure
   rollback, uninstall and complete Python/PowerShell runtime manifests. The
   existing generic delivery handles another private module. Native Windows
   CMD/NTFS checks remain a separate platform limitation.

After-release evaluation should confirm the functions remain stateless borrowers,
all original numerical/admission behavior survives and no new engine/model/report
coupling was introduced. The other three functions can remain where they are
until their real dependencies support another bounded extraction.

Assessment evaluation: the proposed smaller boundary is ready. The wider family's
position, model and reporting dependencies are recorded rather than hidden behind
adapters. No new runtime bug or separate corrective review was established. The
remaining modularization choices and deferred global API/pass-local index reviews
are future work, not prerequisites for v217.
