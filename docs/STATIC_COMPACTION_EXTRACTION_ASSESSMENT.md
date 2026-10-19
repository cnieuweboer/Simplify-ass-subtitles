# Static override compaction extraction assessment

Assessed against v227 (`2026.10.19.227`, commit `075249f`). Recommended next
release: **v228 — Extract static override compaction**. This is an assessment;
production sources and tracked tests remain unchanged.

## Boundary and dependencies

Move three existing functions, unchanged, into
`_simplify_ass/static_compaction.py`: `_finished_static_key()`,
`_join_finished_static_headers()` and `compact_static_overrides()`.
Together they contain 95 definition lines. Retain direct engine aliases.

This is a complete event-level serialization responsibility, covering both early
compaction and final proof-checked compaction. Keep both modes together: they
share the serializer but deliberately differ in evidence lifetime, origin
handling and final equivalence checks. Do not move invocation points or combine
this pass with static-object matching merely because it consumes that proof.

Incoming dependencies are seven calls in four engine functions:
`_render_inline_stacked_text_caption()`, `_flatten_stacked_text_group()`,
`_finalize_text_layout()` and `simplify_ass()`. Existing tests also use the engine
aliases for compaction and final identity. Pipeline callers retain stage order,
configuration, eligibility and reporting.

| Outgoing owner | Dependency |
| --- | --- |
| Standard library | `math`, `re` |
| `ass_overrides` | Defaults, recognized tag pattern, canonical continuation, style resolution, tokenization and interpretation |
| `event_model` | Canonical `Event` annotation |
| `event_operations` | `replace_event()` and its established invalidation policy |
| `static_objects` | Canonical `StaticSpanSignature` and complete-span identity |
| `static_selection` | `unrotated_text_state()` |
| `text_freezing` | `simplify_visual_text()` |

Every outgoing runtime dependency already has a private owner. None imports the
engine or needs the compactor. The graph stays one-way, with no callbacks,
adapters, duplicate representations or circular imports. Cold import needs no
font backend or file access. No dataclass moves or new context/result types are
needed.

## Ownership and retained behavior

- Events, defaults, style catalogs, measurement context and source evidence stay
  caller-owned and borrowed. Formatting/default/continuation buffers and the
  result list are local; no persistent cache is introduced.
- Final mode first proves complete static identity, joins only recognized adjacent
  headers, and accepts only a shorter candidate with equivalent formatting and
  continuation. It retains finished blur and origins, literal/drawing payloads,
  inline gradients, resets and unknown-syntax refusal.
- Earlier mode retains its existing blur/outline policy and removal of origins
  only for proven unrotated literal spans. It uses ordinary event replacement
  invalidation. Final mode explicitly retains source evidence; keep that
  distinction rather than broadly preserving evidence for every text edit.
- Timing, ordering, multiplicity and event metadata remain unchanged. Comments
  and rejected/unchanged candidates retain their existing object behavior.
- The return value remains a list of events. There are no diagnostics, counters,
  reusable measurement caches or report records to relocate.

**No preparatory production change is necessary.** v227 closed the remaining
complete-span proof dependency. A single extraction release is sufficient.

## Associated test binding changes

Two test bindings need to follow the defining consumer:

1. Add `compact_static_overrides` to the existing interpreter observer's consumer
   list in `tests/override_module_test_helpers.py`.
2. In the inline-continuation test, patch the compactor's actual
   `simplify_visual_text` binding as well as the historical engine binding.
   The existing binding helper can already do this once the consumer is listed.

The ignored prototype uses precisely those adjustments. It changes no expected
values or assertions and adds no production forwarding. The real final pipeline
handoff spy still observes the engine alias where callers invoke it.

## Alternatives and scope

Frame-echo processing is a larger cohesive candidate, but still depends on
engine-owned `text_layout_key()`, `text_height()` and `state_key()`. Moving those
shared helpers into an echo-specific module would assign misleading ownership.
Broader frame-animation processing also retains source-family and inline-paint
proof dependencies. Keep assessing those boundaries independently; this release
does not prescribe their final layout or perform the deferred global API review.

## Assessment evidence

An ignored prototype contains exact moved definitions, a direct engine import and
byte-identical existing private sources. AST checks confirm the remaining engine
is unchanged apart from that import. All 16 production runtime source hashes
still match the verified v227 release.

Static-continuation (68,770), inline-continuation (51,222) and parser-consumer
(9,894) checks passed on both baseline and prototype using Windows BASIC plus
real HarfBuzz on Linux. Inline checks use only the binding adjustments above.
An isolated process also passed cold import without optional font backends,
canonical alias/type-hint checks, comment identity and header syntax guards.

The native final-compaction check also passed on both versions: 191 assertions
and 13 pixel-identical before/after render pairs per version, including the real
Demon Slayer final pipeline handoff with required-font checks. All 124 recorded
font hashes remain unchanged. There were eight successful script/version runs.

Local evidence and prototype: `validation/static-compaction-assessment/`.
The full regression suite, paired corpus and native Windows delivery checks are
reserved for implementation; this assessment does not claim a fresh full run.

## Proposed v228 validation and after-release evaluation

Add focused module/import/installed coverage for direct aliases, borrowed input
ownership, evidence distinctions, both modes, syntax refusal and repeated
compaction. Retain existing continuation and native-render checks, including
actual final pipeline handoff coverage. Run the full suite and fresh paired
conversions of all 13 corpus tracks, requiring byte-identical output and complete
statistics. Verify recursive delivery, updater rollback/retry and owned uninstall;
leave `simplify_subtitles.py` unchanged and identify native Windows limitations.

Afterward, confirm the caller still chooses serialization/evidence boundaries and
both modes preserve their distinct contracts. The two bounded observer/stub
binding updates belong in the extraction release. No production workaround,
duplicated proof or ownership conflict currently warrants a dedicated corrective
review.
