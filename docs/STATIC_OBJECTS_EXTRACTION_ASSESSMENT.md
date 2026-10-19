# Static-object matching and phase-merging extraction assessment

Assessed against v226 (`2026.10.19.226`, commit `c40b300`). Recommended next
release: **v227 — Extract static-object matching and phase merging**.
This assessment does not change production code or tracked tests.

## Recommended boundary

Move these unchanged definitions into `_simplify_ass/static_objects.py`:

- Frozen `StaticSpanSignature` record.
- `geometry_key()`.
- `static_object_key()`.
- `_merge_static_phase_round()`.
- `merge_static_timed_copies()`.

These are four functions and one existing record, totaling 184 definition lines
including the dataclass decorator, with 32 engine callers. This boundary includes
the complete-span representation and the ordered merging algorithm that directly
consumes it. It is now closed because event replacement, measured bounds and
source-pose support already have independent owners.

The module provides shared static-object identity as well as safe temporal
consolidation. `geometry_key()` is the vector-token representation used by drawing
payloads and clips in those signatures; other vector consumers retain direct
engine aliases to the same primitive. It is not a new geometry approximation or
a phase-specific copy of a general helper.

Keep `state_key()`, placement/layout fingerprints and unrelated reduction passes
in their current owners. Their precision, exclusions and matching purposes differ
from complete static-span identity. No signature unification is proposed.

## Incoming and outgoing dependencies

Two pipeline callers invoke the merger: `_finalize_text_layout()` before remaining
row reconstruction, and `simplify_ass()` after caption-support ownership settles.
Their invocation points and arguments remain unchanged. Other callers use static
identity for literal paint alignment, freezing, copy proofs, fragment/row
reconstruction, vector recovery, supporting-drawing matching, caption-panel
ownership, color normalization and final compaction.

`_finished_static_key()` and `remove_redundant_text_copies()` also construct
`StaticSpanSignature` records. They must import the same canonical record through
the existing engine alias; do not create parallel representations.

The module's outgoing dependencies are:

| Owner | Borrowed functionality |
| --- | --- |
| Standard library | `re`, `dataclasses.dataclass` |
| `ass_overrides` | Canonical `NUMBER`, override pattern, continuation record, style resolution, tokenization and ordered interpretation |
| `event_model` | Canonical `Event` |
| `caption_geometry` | `get_pos()`, `caption_bounds()` |
| `font_metrics` | Canonical `FontMetrics` annotation; no owner is instantiated |
| `event_operations` | `replace_event()` |
| `frame_pose` | `_preserve_frame_pose_support()` |

The graph is engine → static objects → existing private owners. No dependency
returns to the engine. There is no dependency on caption rendering, static paint
selection, text freezing or pipeline configuration. Cold importing and processing
without measurements requires no optional font backend or file access.

Keep direct engine aliases for all five definitions. Preserve the record's frozen
status, field order, continuation type and equality/hash semantics. Its defining
module changes naturally; old root-name lookup still resolves through the alias.
Do not rewrite `__module__`, add adapters or redesign result types.

## Data, caches, diagnostics and results

| Concern | Responsibility after extraction |
| --- | --- |
| Styles, defaults and events | Remain document/caller-owned and borrowed. Signature construction parses into fresh local formatting buffers, not event caches. |
| Complete span identity | Module retains exact literal/paint/layout and continuation-sensitive spans, vector-token normalization, metadata and measurement context distinctions. |
| Signature records | The existing frozen record moves intact. No broad dataclass consolidation or inheritance is needed. |
| Merge working state | Groups, layer/slot indexes, overlap membership, bounds cache, replacement map and removed-slot set stay local to each round. |
| Font measurements | The supplied metrics owner retains its reusable caches and diagnostics; the merger only requests conservative bounds for eligible peers. |
| Compositing proof | Existing algorithm uses actual list slots and each displaced phase's lifetime. Source IDs remain identities, not ordering authority. |
| Pending row roles | Engine supplies the borrowed `row_sources` set. Module retains the existing row/eligibility distinctions and whole-row slot protection. |
| Source evidence | Timing-only replacement borrows existing caches/history. Compatible pose support aggregates at completed-run emission; original contour/opaque-span proofs are not extended. |
| Results | Return a list and removed count. Existing successor creation and cache sharing remain intact; a zero removal count is not a promise of original event-object identity when source support is handed off. |
| Reporting and sequencing | Callers retain both invocation points, `static_merged` aggregation, stage transitions, support ownership and diagnostics. |

The fixed point remains confined to this same proof. Each contributing round
reduces records; it does not rerun paint selection or reconstruction. Keep the
current refusal of gaps, overlapping-copy collapse, uncertain bounds and unsafe
intervening content. Preserve numeric layer aliases, malformed-peer obstruction,
unpositioned-collision handling, text-only admission and row-source semantics.

## Preparatory work and associated test change

**No preparatory production change is needed.** The identity representation and
its merger can move together with their current APIs. The key/record have shared
consumers, and the merger's remaining dependencies already point to private
owners. One release is sufficient for this extraction.

One test observer needs to follow the new owner. The existing
`tests/override_module_test_helpers.py::patch_interpreter_bindings()` explicitly
enumerates interpreter consumers. Append `static_object_key` to that list so
`inspect.getmodule()` discovers the new binding. This retains historical
single-file handling and observes the same calls once. No production forwarding,
trace-value changes or weakened assertions are needed.

The unchanged prototype initially failed the inline-continuation trace comparison
because that observer missed interpreter calls in the new module. A local copy
of the helper with this one consumer-list addition restored all 51,222 checks.
The adjustment belongs in the implementation release alongside module coverage;
it does not warrant a separate architectural preparation release.

## Alternatives considered

- Identity alone is a closed smaller boundary, but the merger now depends only
  on that representation and existing private owners. The combined subsystem
  remains cohesive and moves an actual processing algorithm in the same release.
- Scrolling still depends on the shared `state_key()` and `text_height()` helpers.
  Those should not become scrolling-owned solely to permit an extraction.
- Broader frame-effect processing still has source-family and inline-paint proof
  dependencies. Keep that assessment independent of static-object consolidation.
- Exact-font row recovery still shares caller-owned diagnostics with other font
  routes. Do not relocate that report incidentally into a row-specific owner.

No final module tree, general matching API or global processing context is needed.

## Fresh assessment evidence

An ignored prototype moved the exact four functions and decorated record, with
direct aliases. AST comparison verified identical moved definitions, unchanged
remaining engine code except the import, and byte-identical existing private
modules. The engine version stayed v226 throughout the assessment.

Eight existing checks passed on both v226 and the prototype: **16 successful
final script/version runs**, using Windows BASIC plus real HarfBuzz on Linux:

| Check | Results per version |
| --- | --- |
| Static continuation | 68,770 checks |
| Inline continuation | 51,222 checks, with the described observer update for the prototype |
| Parser effect consumers | 9,894 checks |
| Static-phase handoff | 69 checks |
| Final visibility ownership | 1,154 checks |
| Outline parsing reuse | 219 checks |
| Source frame poses | 66 checks |
| Native late static phases | 1,798 checks, 31 Overlord joins and 36 pixel-identical order/boundary samples |

The static-phase handoff check retains its existing historical-finalization
bracket for its distinct v185 consumer-role comparison. The native late-phase
check exercises the actual current pipeline and paint policy, with and without
final joining. No new rendering or paint substitution was introduced.

A separate isolated-process check passed cold imports, canonical aliases/types,
frozen/pickle signatures, continuation-sensitive identity, vector normalization,
animation/unpositioned admission, full input immutability, successor cache
sharing, source-support handoff, repeat stability, pending-row protection,
unknown-bounds refusal and preservation of overlapping copies.

Local evidence is in `validation/static-objects-assessment/assessment.json`,
with the prototype, source manifests, dependency audit, logs and observer-helper
copy. The initial missing-trace attempt is retained separately. All 15 production
source hashes match the fully verified v226 release; tracked tests/harnesses and
all 124 recorded font hashes are unchanged. The full suite and corpus were not
rerun for this assessment. Production code and output remain unchanged.

## Proposed v227 validation and after-release evaluation

Add focused module/cold/installed coverage for canonical record identity and
pickle lookup, borrowed inputs, span/history distinctions, vector identity,
pending-row protection, measured and unknown bounds, slot ordering, overlap/gap
refusal, source support and fixed-point behavior. Apply the one observer-owner
update, retaining existing assertions.

Run the full current suite and fresh paired conversions for all 13 corpus
tracks, requiring byte-identical output and complete statistics. Verify recursive
delivery/manifests, shipped-updater rollback/retry and owned uninstall. Leave
`simplify_subtitles.py` unchanged and identify native Windows skips explicitly.

Afterward, confirm both stages still invoke one merger with explicit caller-owned
roles and that source caches/proofs retain their existing lifetimes. The bounded
observer update is the only associated change identified. No production adapter,
duplicated proof, local exception or ownership conflict requires a dedicated
corrective review. Broader API and pass-local index reviews remain separate.
