# Subtitle document extraction — v221

Document decoding, parsing, resolved views and serialization now live in
`_simplify_ass/subtitle_document.py`. This implements the
[bounded assessment](SUBTITLE_DOCUMENT_EXTRACTION_ASSESSMENT.md). The engine
version is `2026.10.18.221`; document and simplification policy are unchanged.

## Boundary and responsibilities

The module contains the existing mutable `SubtitleDocument` record,
`EVENT_FIELDS`, `GENERATED_MARKER` and 13 functions: timestamp parsing/formatting,
serialized-time concurrency, dialogue/document parsing, strict decoding,
resolution lookup, independent resolved document views, marker placement,
document rendering/writing and the established resolved-reader interface.

The functions, record/decorator and constants moved unchanged. Engine exports
are direct aliases imported before dependent declarations. The measurement
factory uses the canonical event-model record, and the fallback field list
remains one shared object. There are no forwarding wrappers, callback adapters,
replacement records or alternate parsing paths.

Dependency direction is engine → subtitle document → event model/override
interpreter. Other imports are standard library only. Independent import does
not load the engine or optional font backends. No moved helper uses `__file__`;
paths remain explicit and sibling font discovery stays with the existing font
owner. All existing private modules are byte-identical. The batch wrapper,
installer and updater sources are unchanged.

The engine still owns processing-stage transitions, `_prepare_text_document()`,
`_normalize_text_result()`, event replacement, source-proof admission/lifetimes,
effect selection, caption/support processing, generated-file admission, CLI file
protection, input discovery and counter reporting. The caller chooses when to
resolve or render/reparse a document. The document record gains no processing
methods, global context or hidden cache.

## Ownership and behavior

- Parsing creates document-owned lines, styles, events and indices. Events borrow
  document styles/defaults and remain unresolved until a caller prepares them.
- `_resolve_document_state()` returns a new document view with a new style map
  and individual style dictionaries, new events and fresh formatting/continuation
  pairs. Source lines and field order remain borrowed read-only. Immutable event
  evidence keeps its existing sharing; the source document is not modified.
- Parsing records authored valid canvas dimensions with wrapping inactive.
  Resolution supplies the existing successor measurement context with script
  wrapping active. Unit fallback and authored-canvas evidence retain their
  distinct semantics; their resolution readers were not consolidated.
- Explicit format records retain their own lists. Missing-format documents borrow
  the existing shared `EVENT_FIELDS` list; the engine alias points to that same
  object. Constructor field order, mutability and default factory are unchanged.
- Rendering borrows the document/event iterable, preserves its supplied event
  order and builds output without changing the inputs. Metadata/event-region
  boundaries, SSA Actor/Marked aliases, comments, literal Unicode separators,
  terminal-newline policy, marker relocation and UTF-8 BOM output are unchanged.
- Peak concurrency still uses serialized half-open intervals, ignoring comments
  and empty/reversed lifetimes and aggregating touching boundaries. Cached numeric
  event times do not override that representation.
- The subsystem creates no font report, conversion counter accumulator or
  persistent parser cache. Diagnostics and accepted-join counts stay with their
  existing callers. Decode errors retain the original type and useful path/encoding
  context; CLI file protection is not duplicated inside I/O helpers.

Ordinary new document pickles identify the private defining module. Direct engine
aliases resolve historical class names without changing `__module__` or adding
a persistence API.

## Tests and delivery

The existing document-boundary check now observes `read_subtitle` at its actual
defining module through `inspect.getmodule()`. All 42 assertions remain, including
one source read, final-output-only writing and no temporary ASS disk roundtrip.
Production calls do not forward through the engine for this test. Font-report
failure checks still patch the engine's actual write entry point and need no
retargeting or adapter.

The new module check covers canonical aliases, runtime annotations and factories,
the shared fallback list, independent import, source/style/cache isolation,
measurement activation, mutable record and pickle lookup, SSA metadata, comments,
literal separators, newline handling, strict decoding/errors, serialized-time
concurrency and installed use. An actual installation reads a UTF-16 source,
resolves/writes a document and runs the CLI from an unrelated directory before
removing owned source/bytecode and preserving a user file.

The [generic delivery contract](MODULE_DELIVERY.md) discovers the module without
adding a filename list. A separate private probe installs the exact v220 runtime
and upgrades it through the actual shipped v214 updater with pinned mock GitHub
tree/blob responses. It checks complete rollback when the new document module
cannot be installed, successful retry, preserved launcher choices and user files,
canonical installed document/factory identity, parsing/resolution/rendering and
uninstall. This does not claim a live network update or native Windows execution.

`validation/check_subtitle_document_extraction.py` audits this release's movement
against the exact v220 baseline. Moved definitions/decorators/constants and the
remaining executable engine AST are identical except import/version; existing
private sources are unchanged. Its bounded historical scope must not constrain
future justified document or processing changes.

## Fresh validation

Before production editing, all nine v220 runtime sources were captured with a
complete manifest. Thirteen baseline conversions were regenerated from the actual
supplied subtitles and fonts. Current conversions are independently generated.
Both sets stop if a reconstruction producer reports a missing required font.
Source, font, baseline/output and complete runtime hashes are verified.

Fresh final results:

- All **97 regression scripts passed**, including native libass render checks.
  Complete runtime and harness hashes remained unchanged during the final run.
  The continuation check retained all **634,286 assertions**.
- All **13 v220/v221 corpus pairs have byte-identical output and identical
  complete statistics**. All **124 supplied font-file hashes** were verified;
  neither baseline nor current conversions reported a missing required font.
- All **eight document-module checks** and all **42 document-boundary checks**
  passed, including installed document processing, CLI execution and owned
  source/bytecode uninstall. The read/write assertions were retained.
- Installer: **32 passed, two native Windows checks skipped**. Updater:
  **10 passed, one native Windows check skipped**. The shipped-updater
  rollback/retry/uninstall probe and MKV/font smoke check passed.
- Python and PowerShell agree on all **ten runtime source hashes**. The batch
  wrapper and installer/updater sources remain byte-identical to v220.

Private evidence and reproducible drivers remain under
`validation/subtitle-document-extraction/`: `baseline-manifest.json`,
`corpus-inputs.json`, `baseline-corpus/summary.json`, `corpus/summary.json`,
`audit.json`, regression/delivery/smoke logs and `release-verification.json`.
Fonts, fixtures, generated conversions and reports are ignored local assets.

Run focused checks and the full suite from the repository root:

```sh
python validation/check_subtitle_document_extraction.py
python validation/run_backend_check.py --backend windows tests/check_subtitle_document_module.py
python validation/run_backend_check.py --backend windows tests/check_document_boundary.py
python validation/run_backend_check.py --backend windows tests/check_measurement_context.py
python validation/run_review_checks.py
```

Linux checks use Pillow BASIC with real HarfBuzz and native libass rendering.
Native Windows CMD/NTFS/self-update checks require Windows; platform skips must
remain distinct from passes.

## After-release evaluation

Document creation, independent resolved views and serialization now form one
closed subsystem. Their mutable/borrowed buffers, canonical factory/constant
identity and explicit stage handoffs retain the existing responsibilities.
No production adapter, reverse import, new cache owner, duplicated proof or local
exception was introduced. The single test-observer correction preserves the
meaningful read/write assertion rather than weakening it.

No dedicated follow-up review is needed for this extraction. Future module
assessments should continue from the resulting dependency graph, including larger
processing subsystems. The deferred global API and pass-local index reviews
remain separate work.
