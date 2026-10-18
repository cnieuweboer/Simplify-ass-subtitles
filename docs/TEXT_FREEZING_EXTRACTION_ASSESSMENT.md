# Text freezing — bounded extraction assessment

Historical assessment of v222. Implemented in
[v223](TEXT_FREEZING_EXTRACTION.md); the evidence below describes the assessment.

Assessed against v222 (`2026.10.18.222`). Recommend **v223: extract text freezing
into `_simplify_ass/text_freezing.py`**, retaining direct engine aliases. One
implementation release should suffice, with no intended behavior change or
preparatory production release.

Production, tests, the batch wrapper and delivery code remain unchanged by this
assessment. An isolated whole-engine prototype and fresh evidence are private
under `validation/text-freezing-assessment/`.

## Recommended boundary

Move these seven existing definitions together, unchanged:

- `FrozenBlock` and `SAFE_SIMPLE_TAGS`;
- `safe_override()` and `simplify_text()`;
- `_freeze_inputs()`, `freeze_block()` and `simplify_visual_text()`.

Definitions, decorator and whitelist assignment total 205 lines. Keep the
whitelist's explanatory comment with its assignment. Tag serialization already
belongs to v222's caption-rendering module; reuse its existing `render_tag()`.

This subsystem turns override streams into selected static formatting and
serialized headers/text. It owns source-header parsing for selection, reset and
continuation handoffs, drawing/text accounting and serialization relative to
preceding spans/defaults. Preserve both existing routes: simple per-block
simplification, including the visible-only bypass, and continuation-aware visual
freezing. Their different contracts are not a reason to consolidate them.

Keep event admission, `_freeze_event_effects()`, cache installation, source-family
proofs, event replacement, final static compaction and report aggregation in the
engine. Callers still decide which events to freeze, at what stage, with which
source evidence and duration. Do not move adjacent functions merely because they
sit between the selected definitions in the source file.

## Incoming and outgoing dependencies

Incoming calls include pipeline freezing, final compaction, upright-pose handling,
source-row collection/paint, vector-text recovery and supporting-drawing/backdrop
reconstruction. Several consumers use `simplify_text(..., visible_only=True)`
solely to extract literal text. `_source_row_palette()` and
`adjacent_sustained_geometry()` also consume `_freeze_inputs()` directly; preserve
its exact evaluation/transforms/boundaries/reset result rather than inventing a
second parser. Root exports remain direct aliases for all these callers.

The new module needs standard-library `re`, dataclasses and `typing.Iterable`,
plus these existing private dependencies:

- interpreter defaults, numeric/override patterns, continuation/evaluation records,
  tokenization, style resolution and override application;
- `StaticPoseEvidence`, `StaticStateSelection` and `select_static_state()`;
- `render_tag()` from caption rendering.

Dependency direction is engine → text freezing → selector/interpreter/rendering.
The selector already depends on sampling and canonical event records; rendering
already depends on the interpreter/measurement model. No dependency returns to
the engine or freezer. No font backend, event replacement, document I/O, pipeline
context or diagnostic accumulator is needed. No helper uses paths or `__file__`.

Import canonical engine aliases before dependent uses. Keep `FrozenBlock` frozen,
with the same field order and canonical `StaticStateSelection` annotation. Keep
continuation defaults as instances of the existing canonical record. Ordinary
new pickles naturally identify the private defining module; aliases retain legacy
engine class-name lookup without rewriting `__module__`.

## Ownership retained by the move

| Data or responsibility | Preserved owner and contract |
| --- | --- |
| Input formatting, defaults and styles | Borrowed read-only. `_freeze_inputs()` copies initial formatting and owns its local transforms, boundaries and successor evaluation. No cache is installed on an event. |
| Continuation and pose | Existing frozen records are passed through the stream and selector. Adjacent-header rotation handling, reset-dependent pose admission and parser history retain their existing order. No history is reconstructed from serialized output. |
| Selection and source evidence | Selector owns its existing votes, samples and evidence containers. Freezing passes through the exact selection record and preserves borrowed seed snapshot identity. It neither rewrites caller seed containers nor takes over event evidence lifetime. |
| Blur clamping | Freezing clamps its selected formatting after selection. Settled snapshots retain pre-clamp source paint; the selected formatting is independent of the caller's input. Moving this ordering into selection would change the contract and is outside scope. |
| Frozen result | `FrozenBlock` freezes its bindings, not the nested selection state's dictionary. Preserve the current mutability and sharing, rather than adding deep copies or a new immutable model. |
| Output whitelist | `SAFE_SIMPLE_TAGS` remains one shared mutable set, borrowed read-only by production. Keep the engine alias to that object. Its output vocabulary remains separate from the interpreter's broader recognized-tag vocabulary. |
| Serialized results and diagnostics | Functions return the same strings, visible text and drawing-character count. Pipeline callers own event replacement, aggregate counts, warnings and final reports. There is no persistent cache or new diagnostic owner in the extracted group. |

## Preparation and test observation

No preparatory production change is needed. Prior interpreter, selection and
rendering extractions already provide a closed boundary. Moving the record and
whitelist with their consumers avoids a reverse import without an adapter,
callback injection, processing context or dataclass consolidation.

Two test-only observation changes should accompany implementation:

1. Extend `patch_interpreter_bindings()` in
   `tests/override_module_test_helpers.py` to include the defining module of
   `freeze_block()` among actual interpreter consumers. Retain historical
   single-file support and deduplication of shared bindings.
2. In `check_frozen_block_results.py`, observe `select_static_state` on
   `inspect.getmodule(current.freeze_block)`. Retain the assertions for the exact
   selection result and parsed base identity; do not patch the selector's defining
   module when the freezer uses its own imported binding.

The `check_inline_continuation.py` patch of the engine's `simplify_visual_text`
still observes the actual engine compaction call site. Leave it there. Do not
retarget every spy automatically or forward production calls through the engine
for instrumentation.

Larger candidates remain useful but are not closed by v222 alone. Sliced-text
processing still needs engine layout, clipping, effect parsing and replacement.
Static phase merging still needs stroke bounds, frame-pose evidence preservation
and event replacement; scrolling needs caption bounds, pose/state and text-height
helpers. Word echoes still need layout/static-span proof helpers. Exact-font row
recovery still reaches `get_pos()` and annotates the cross-pass font report.
Moving that report into a row module or adding parser callbacks would obscure its
ownership. Those boundaries deserve fresh assessment after this extraction;
there is no independently useful preparatory change required for freezing now.

## Prototype evidence

The prototype moves all seven definitions unchanged and imports aliases during
engine initialization. Moved ASTs and remaining engine executable AST match;
all existing private sources are byte-identical. Cold processing imports neither
the engine nor optional font packages. Canonical aliases, annotations/defaults,
shared whitelist identity, frozen result and ordinary/legacy pickle lookup pass.
Borrowed inputs/seeds, pre-clamp snapshots and the visible-only freeze bypass also
pass independent checks.

Fresh baseline/prototype pairs both passed:

| Script | Result for each engine |
| --- | --- |
| `check_frozen_block_results.py` | 3,360 comparisons and 27 ownership/identity checks. |
| `check_freeze_continuation.py` | 634,286 checks, including 5,130 sampler cases, 1,440 selection cases and 576 continued freeze steps. |
| `check_inline_continuation.py` | 51,222 continuation checks. |
| `check_freeze_consumers.py` | 16,704 checks across static selection, lyric paint and effect sequences. |
| `check_undefined_styles.py` | 156 style-resolution checks. |
| `check_measurement_context.py` | 12,221 measurement/context checks. |
| `check_parser_effect_consumers.py` | 9,894 parser/effect consumer checks. |
| `check_override_module.py` | Seven module checks; its installed subtest uses the actual v222 checkout, not the proposed freezer module. |

All **16 executions passed**, retaining every assertion. The prototype uses only
the two test-observer corrections described above; tracked tests are unchanged.
The frozen-block prototype check runs directly; the other pairs use the Windows
BASIC/real HarfBuzz runner. This is Linux validation, not native Windows execution
or delivery validation of the proposed module.

The production manifest still matches the fully validated v222 release. Full
regression/corpus runs were not repeated for this documentation-only assessment.
Private evidence includes `audit.json`, `alternatives.json`, `assessment.json`,
`checks.json`, `identity.log`, paired logs and prototype/drivers.

## Proposed v223 acceptance and evaluation

Extract the group unchanged, retain aliases/default/whitelist identity, correct
the two test observers and add direct module/installed-use coverage. Preserve
continuation, resets, ordered uniform/axis overrides, adjacent rotation headers,
blur/evidence handoff, drawing switches, visible-only bypass and all return values.
Keep the batch wrapper and generic delivery code unchanged.

Run the full suite and fresh baseline/current corpus comparisons, requiring
identical output and complete statistics. Verify independent and installed use
from an unrelated directory, updater discovery/rollback/uninstall and complete
Python/PowerShell runtime manifests. Record native Windows skips separately.

After release, confirm that freezing owns local stream state and serialization
while selectors, event producers and pipeline/report owners retain their existing
responsibilities. No production workaround, duplicated proof or ownership repair
was needed in this assessment. No dedicated corrective review emerged; the
deferred global API and pass-local index reviews remain separate work.
