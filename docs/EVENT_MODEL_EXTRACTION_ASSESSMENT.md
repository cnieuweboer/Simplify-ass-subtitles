# Core event records — bounded extraction assessment

Historical assessment of v218. The proposed boundary was implemented in
[v219](EVENT_MODEL_EXTRACTION.md); the evidence below describes the assessment.

The recommended next release is **v219: move `Event`, `EventEvidence` and
`DocumentMeasurementContext` into `_simplify_ass/event_model.py`**, preserving
direct engine aliases. Their unchanged definitions and decorators total 82 lines.
This is a concrete preparatory extraction: it establishes a canonical dependency
for event-based modules without moving their policies or redesigning their API.

This document assesses v218. Production, tests, the wrapper and delivery code are
unchanged. Private prototypes and fresh evidence remain under
`validation/event-model-assessment/`.

## Why this boundary now

The same dependency has appeared in multiple assessments. Event-based row
fitting uses borrowed records and has concrete event annotations; static-state
selection accepts event-based paint evidence; document parsing constructs events
and document measurement context. Importing these records from the engine would
create reverse dependencies when those subsystems move out.

The three record definitions already form a closed group. A passive core-record
module gives those consumers a one-way import without changing how evidence is
produced, retained or invalidated. This is useful independently of which consumer
moves next. It avoids either postponing every event-based candidate or inventing
callbacks, minimal substitute row objects or engine-global injection to close one
particular extraction.

This does not prove that row fitting, document I/O or static selection is ready
to extract immediately afterward. Row fitting still has position syntax and
report dependencies. Static selection has its own contexts, pose helpers and
paint/geometry responsibilities. Assess the selected consumer again after the
record move rather than prescribing a hierarchy or automatic v220 release now.

## Incoming and outgoing dependencies

| Record | Definition lines, excluding decorator | Outgoing dependencies |
| --- | ---: | --- |
| `EventEvidence` | 24 | `dataclass`, built-ins; its existing post-init protects source containers by converting them to tuples. |
| `DocumentMeasurementContext` | 11 | `dataclass`, built-ins; canvas/wrapping data only. |
| `Event` | 44 | `dataclass`, `field`, both records above, existing `OverrideContinuation`, built-ins. |

The new module needs only `dataclasses`, postponed annotations and the existing
interpreter continuation record. It has no parsing/sampling function dependency,
font/backend dependency, event-replacement helper, path discovery, diagnostic or
pipeline import. It imports independently of the engine and optional packages.

Incoming uses include:

- `parse_dialogue()` constructs `Event`; document parsing creates the authored
  measurement context. Parsing, timestamps, line indices and styles stay with
  those producers.
- `replace_event()` and supporting-drawing finalization construct/reset event
  evidence. Their proof-preservation/invalidation decisions remain in the engine.
- `Event` uses factories for evidence, measurement and continuation;
  `SubtitleDocument` also has a measurement-context factory. Caption rendering
  has a measurement-context default. These bindings must all reference the same
  canonical records after extraction.
- Many pass contexts, results and matching functions reference `Event`, usually
  in annotations. A static scan finds 416 top-level definitions mentioning it;
  that is not a claim of 416 runtime construction sites. The only explicit
  production `Event(...)` call is in `parse_dialogue()`; replacements also create
  successors through `dataclasses.replace()`.

The dependency direction becomes engine → event model → interpreter records.
Existing measurement, outline, placement and sampling modules need no change.
Future event-based modules can import the model directly. Keep all three engine
aliases so existing callers still use the actual canonical classes.

## Data, cache, diagnostic and result ownership

Moving definitions does not transfer document or pipeline ownership to the model:

| Data | Owner and preserved contract |
| --- | --- |
| Authored event fields, duration and serialization fields | Document/pipeline owns mutable events. Preserve constructor order, fields, equality flags, `duration` and fresh `fields()` lists. Add no validation, timing normalization or new base class. |
| `state` | Event cache owner installs resolved formatting and continuation together. Consumers borrow a nonempty cache; timing successors may share it. Record construction has its existing fresh empty dictionary. |
| `defaults` and `styles` | Fresh empty defaults at construction; prepared events borrow document-owned dictionaries. No deep copying or runtime freezing of document catalogs. |
| Historical evidence | Existing frozen `EventEvidence`. Preserve tuple protection and absent-versus-empty evidence. Source proof, retention and invalidation remain with producers and `replace_event()`. |
| Measurement context | Existing frozen `DocumentMeasurementContext`. Parsing/measurement boundaries establish canvas and active wrapping; the record itself infers neither. Sharing/replacement rules stay unchanged. |
| Parser continuation | Existing frozen interpreter record; same class and default factory. Pairing with resolved state stays with cache owners. |
| Diagnostics, counters and pass results | No new owner here. Font reports, reconstruction result records, pass caches and edit application remain where they are. |

`Event` remains mutable. The two supporting records remain frozen. Keep all
existing field factories, `compare`/`repr` flags, methods and post-init behavior
unchanged. This is not a global `ProcessingContext`, dataclass consolidation,
result hierarchy or an opportunity to revise evidence policy.

Keep `event_evaluation()`, `replace_event()`, parsing/rendering functions,
`SubtitleDocument`, `StaticSpanSignature`, `TextRow`, `StaticPoseEvidence` and
pass-specific contexts/results in the engine. They are outside this closed group;
their presence near these definitions is not a reason to move them together.

## Identity and compatibility probes

A whole-engine private prototype moves the three definitions unchanged and
imports them before dependent classes and function defaults are defined. Its
remaining executable AST is identical, and existing private sources are copied
unchanged. The prototype retains the original sibling-font fallback through a
private symlink.

Rebinding engine aliases after import would be an inadequate probe: existing
factories and constructed defaults could still reference the old classes. The
whole-engine prototype instead verifies:

- Independent model import and runtime annotation resolution without the engine,
  Pillow, fontTools or HarfBuzz.
- Root/model class identity, event evidence/context factories, the document's
  context factory and the caption renderer's already-constructed context default.
- Concrete event annotations in row fitting, document records and static selection.
- Fresh per-event dictionaries, existing equality/frozen behavior, tuple-protected
  evidence, shallow replacement sharing and deep-copy independence.
- Ordinary new pickle round trips and loading an old pickle that names engine
  exports. Existing aliases resolve those old names without a shim. New pickles
  name the private model and require that package; do not rewrite `__module__` to
  imitate the former location. No repository production pickle consumer was found.

Eight existing scripts ran against both the unchanged engine and the complete
prototype, without adapting production calls or test helpers:

| Check script | Matching results in both executions |
| --- | --- |
| `check_event_evidence.py` | 42 event-evidence ownership checks. |
| `check_measurement_context.py` | 12,221 measurement-context checks. |
| `check_document_boundary.py` | 42 document-boundary checks. |
| `check_context_contracts.py` | 2,500 final context-contract checks. |
| `check_font_row_geometry.py` | 4,925 row/reporting checks; 1,080 algorithm cases, batch/failure contracts and focused conversions. |
| `check_row_reconstruction_ownership.py` | 61 ownership checks and two focused conversions. |
| `check_frame_pose_selection.py` | 66 source-pose checks. |
| `check_inline_continuation.py` | 51,222 inline-continuation checks. |

All sixteen executions passed with matching summaries/counts. Production,
prototype and covered test-source hashes stayed unchanged during the run.
These use the Windows font backend on Linux, not native Windows validation.
The v218 release documentation records a 94-script suite and thirteen-track
corpus pass. Those are historical results, not new assessment checks. The saved
private release manifests are absent from this workspace, so they were not
reverified here; the older local aggregate report is not current evidence.
The fresh assessment verifies working runtime bytes against tracked v218 and
uses its own isolated contracts and sixteen caller executions. It does not claim
a full prototype suite or corpus comparison.

## Implementation and preparation recommendation

The record extraction itself is the useful small preparation. It needs no prior
API redesign or additional production adapter, and should be one release:

1. Capture the exact v218 runtime and regenerate a fresh corpus baseline from
   actual fixtures/fonts if the previous private manifests are unavailable.
   Move the three
   records with unchanged decorators and definitions. Import their aliases before
   dependent declarations so factories and constructed defaults bind correctly.
2. Add focused module checks for import/annotation isolation, class/factory/default
   identity, constructors, equality, borrowing, replacement/copying and existing
   frozen status. Reuse the ownership/context tests; add no behavior shim for
   test lookup or serialization.
3. Audit moved definitions, the remaining engine and existing modules. Run the
   full then-current suite and exact-font corpus comparison, requiring unchanged
   output and complete meaningful statistics. Broad incoming use warrants this
   validation even though the moved code is small.
4. Exercise actual installed constructors/replacement/document processing, generic
   updater delivery and rollback at the new module, uninstall and complete
   Python/PowerShell manifests. No delivery filename list should change. Report
   native Windows checks separately where unavailable.

After-release evaluation should confirm one canonical set of classes, consistent
factories/defaults, unchanged record mutability and caller-owned cache/evidence
policy, and no reverse engine import. Reassess the next consumer afterward.

Assessment evaluation: this is now a justified preparatory boundary, based on
recurring concrete dependencies rather than a speculative model layer. The
identity/default-factory risk is explicit and the prototype addresses it without
adapters. No runtime bug or separate architectural review was established.
Global API and pass-local index reviews remain separate work.
