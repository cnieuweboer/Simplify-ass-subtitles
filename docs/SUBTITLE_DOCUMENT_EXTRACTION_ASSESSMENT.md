# Subtitle documents — bounded extraction assessment

Historical assessment of v220. Implemented in
[v221](SUBTITLE_DOCUMENT_EXTRACTION.md); the evidence below describes the assessment.

Assessed against v220 (`2026.10.18.220`). Recommend **v221: extract the existing
subtitle document subsystem into `_simplify_ass/subtitle_document.py`**, retaining
direct engine aliases. This is one implementation release, with no intended
behavior change or preparatory production release.

Production, tests, the batch wrapper and delivery code are unchanged by this
assessment. The isolated prototype and fresh evidence remain private under
`validation/subtitle-document-assessment/`.

## Recommended boundary

Move `SubtitleDocument`, `EVENT_FIELDS`, `GENERATED_MARKER` and these 13 functions:

- `parse_time()`, `format_time()`, `peak_concurrent_events()`;
- `parse_dialogue()`, `script_resolution()`, `parse_subtitle_document()`;
- `read_subtitle()`, `read_subtitle_document()`, `_resolve_document_state()`;
- `mark_generated()`, `render_subtitle_document()`, `write_subtitle_document()`;
- `load_subtitle_events()`.

The definitions, decorators and two constant assignments total 228 lines.
They form a complete responsibility: strict decoding, document records and
metadata, independent resolved document views, serialized-time concurrency,
event-region rendering and output encoding. Keep the established algorithms,
record shape and function signatures unchanged.

Keep pipeline preparation, `_normalize_text_result()`, event replacement,
effect selection, caption/support processing, generated-file admission, CLI file
protection, discovery and counter reporting in the engine. The caller still
chooses when to resolve or serialize/reparse a document. Moving the document
producer does not move those stage decisions into the document record.

Text freezing is another closed candidate after v220: its six functions,
`FrozenBlock` and output whitelist could depend on the interpreter and selector.
It remains viable, but has more nested freeze/selection test-observer bindings.
The document boundary already has an explicit read/prepare/render contract and
can move as one coherent unit. Event-based row fitting still needs the root's
position parser and report definition; echo/effect subsystems still need engine
replacement, paint rendering and layout helpers. Do not import the engine back
into a proposed module or introduce callbacks to hide those dependencies.

## Incoming and outgoing dependencies

Incoming engine uses include:

- `simplify_ass()` and `_simplify_text_and_vectors()` read/write documents;
- `_normalize_text_result()` renders, reparses and resolves the serialization
  boundary, retaining responsibility for ending transient proof lifetimes;
- document preparation and pass/result annotations use `SubtitleDocument`;
- many reconstruction/timing consumers use `format_time()`; source paint
  timelines also use `parse_time()`;
- scrolling/support stages read resolution or serialized-time concurrency;
- `has_generated_marker()` reads the same marker constant for CLI admission.

The new module needs only the standard library (`codecs`, dataclasses, `math`,
`pathlib`, `re`, typing), the canonical `Event`/`DocumentMeasurementContext` records
and existing interpreter exports (`DEFAULT_STATE`, `parse_styles()`,
`resolve_event_style()`, `evaluate_effective_state()`). There is no font backend,
selection, replacement, rendering-policy or pipeline dependency.

Dependency direction is engine → subtitle document → event model/interpreter.
Existing private modules need no change. Import canonical aliases before all
dependent declarations. The fallback `EVENT_FIELDS` list must remain one shared
object, not be copied into a second root constant. Keep the same marker string
and root export. No helper uses `__file__`; explicit input/output paths retain
their meaning from unrelated working directories.

## Data, cache, diagnostic and result ownership

| Data | Preserved owner and contract |
| --- | --- |
| Parsed document | The returned document owns its line list, style catalog, event map and parsed event records. Their indices belong to that document. Input text is immutable; no hidden current-document state is introduced. |
| Event formatting | Parsing leaves event caches unresolved. Parsed events borrow document styles/defaults. `_resolve_document_state()` creates a new style map and individual style dictionaries, new events and fresh formatting/continuation pairs; it does not install them into the input document. |
| Resolved document metadata | Resolution borrows the original lines/field order read-only while replacing styles/events/measurement. Preserve these deliberate sharing boundaries; do not deep-copy the whole document. |
| Measurement context | Parsing records a canvas only when both authored dimensions are valid, with wrapping inactive. Resolution creates the existing successor context with script wrapping active. Unit/fallback resolution and authored canvas evidence have distinct contracts; do not combine their parsing just to reduce duplication. |
| Source evidence | Immutable event evidence retains existing sharing through `dataclasses.replace()`. Cache installation, text preparation and serialization/reparse invalidation remain at their current boundaries. This move does not extend proof lifetimes. |
| Field order and markers | Explicit format records supply their own lists. Documents without them retain the existing shared fallback list, borrowed read-only. The marker is shared with engine admission through a direct alias. No production mutation of the fallback list was found. |
| Rendering and writing | Renderer borrows document/events and constructs output; it does not mutate source lines, styles or events. Preserve iterable order, SSA aliases, metadata/event-region boundaries, newline policy and UTF-8 BOM output. Writer receives its path explicitly; CLI overwrite/alias protections remain in the engine. |
| Counters and caches | Parsed peak concurrency is ordinary document metadata computed on serialized half-open intervals. No report accumulator, font cache or persistent parser cache belongs to this subsystem. Conversion statistics and font-report lifetime stay with existing callers. |

`SubtitleDocument` remains a mutable dataclass with the same field order and
measurement factory. No new document hierarchy, processing context, validation
layer, alternate record or result adapter is required.

## Is preparation useful independently?

No preparatory production change is needed for this boundary. The event-model
and interpreter extractions already provide canonical, independently importable
dependencies. Moving timing helpers and the two constants with their document
consumer closes the graph directly; a separate timestamp/constants module would
add another step without solving a remaining dependency here.

One test-only observation change belongs with the implementation:
`check_document_boundary.py` currently patches the engine's `read_subtitle`
binding. After extraction, the reader calls the new module's binding. Observe
`inspect.getmodule(current.read_subtitle)` instead, retaining the assertion that
a real conversion performs exactly one source read and writes only final output.
Do not forward production calls through the engine to accommodate this spy.

The existing font-report failure tests patch the engine's write entry point;
that remains the actual pipeline call site and needs no adapter or retargeting.

## Prototype evidence

A whole-engine isolated prototype moves all 16 names unchanged and imports
canonical aliases before dependent declarations. The moved ASTs and remaining
engine executable AST match; existing private sources are byte-identical. This
tests the import from initial engine construction, not aliases rebound after
dataclass/default creation.

Independent import, runtime annotations, canonical class/factory identity,
source/style isolation, wrapping activation, newline behavior, shared fallback
field identity and ordinary/legacy pickle lookup all pass. No optional font
package or engine is loaded by the document module's independent import. New
pickles naturally identify its private defining module; root aliases still
resolve historical class names without rewriting `__module__`.

Fresh baseline and prototype runs both passed:

| Existing script | Result for each engine |
| --- | --- |
| `check_document_boundary.py` | 42 checks, including encoding/conversion parity, normalization, ownership, one read and final-only write. Prototype uses the private observer correction above; all assertions remain. |
| `check_measurement_context.py` | 12,221 measurement/context checks. |
| `check_event_continuation.py` | 4,099 continuation checks. |
| `check_measurement_effects.py` | 2,078 measurement/effect checks. |
| `check_event_model_module.py` | Nine canonical model checks. Its installed subtest uses the real v220 checkout, so it is not delivery validation of the proposed module. |
| `check_file_safety.py` | 117 file-safety checks. |
| `check_pipeline_equivalence.py` | 144 pipeline comparisons. |
| `check_font_row_geometry.py` | 4,925 checks, including 1,080 algorithm cases and batch/failure reporting contracts. |

All **16 executions passed**. Seven script pairs use the Windows BASIC/real
HarfBuzz runner; the prototype's document-boundary execution is a backend-independent
I/O check. This is Linux validation, not native Windows filesystem validation.

The production manifest still matches the freshly validated v220 runtime, and
production plus covered test/helper sources match Git byte-for-byte. Full
regression and corpus conversions were not rerun for this documentation-only
assessment. Evidence is in `audit.json`, `assessment.json`, `checks.json`,
`identity.log`, the prototype/drivers and paired logs under the private folder.

## Proposed v221 acceptance and evaluation

Extract the bounded group unchanged, retain aliases/factories/constants, correct
the reader observer and add direct module/installed-document checks. Verify
encoding/BOM handling, malformed input errors, SSA field aliases, comments,
newlines, document-local indices, source isolation, active wrapping and actual
read/write behavior. Keep wrapper and generic delivery code unchanged.

Run the full current suite and fresh baseline/current corpus comparisons,
requiring byte-identical output and complete statistics. Verify installed use
from an unrelated directory, updater discovery/rollback/uninstall and full
Python/PowerShell runtime manifests. Native Windows platform skips remain
separate from passes.

After release, confirm that the module creates documents and independent resolved
views while callers still control stage transitions, cache installation and
proof lifetime. No adapter, reverse dependency, new cache owner or ownership
correction was needed in this assessment. No separate corrective review is
warranted; broader API/index reviews remain separate future work.
