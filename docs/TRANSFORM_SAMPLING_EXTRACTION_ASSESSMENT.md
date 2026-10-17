# Transform sampling — bounded extraction assessment

The recommended next implementation is **v218: extract transform sampling** into
`_simplify_ass/transform_sampling.py`, retaining direct engine aliases. Six
functions form a 177-line dependency boundary; no preparatory production release
or API redesign is needed.

This is an assessment of v217, not an implementation. Production, tests, the batch
wrapper and delivery code remain unchanged. Disposable probes are private under
`validation/transform-sampling-assessment/`.

## Why this candidate

Sampling already consumes explicit formatting, transform descriptions, sample
times, styles, defaults and parser continuation. It returns the interpreter's
existing evaluation records. Its responsibilities fit between the extracted
interpreter and the engine's static-state, pose, paint and reconstruction policy.

The event-based row-fitting functions left after v217 still involve position
syntax, event annotations and report ownership. Extracting those remains possible,
but requires additional boundary decisions described in the
[glyph-placement assessment](GLYPH_PLACEMENT_EXTRACTION_ASSESSMENT.md). Drawing
normalization likewise mixes geometry with event replacement and position syntax:
`flatten_rectangular_border()` calls `normalize_drawing_alignment()` and
`replace_event()`, while alignment normalization also uses `get_pos()`. Neither
family needs to be forced into an extraction before the closed sampler group.
This assessment does not prescribe their eventual module hierarchy.

## Incoming and outgoing dependencies

| Definition | Source lines | Role and consumers |
| --- | ---: | --- |
| `font_size_transform_needs_replay()` | 14 | Classifies state/order-dependent size updates; used only by the two samplers. |
| `transform_weight()` | 3 | Shared timing/acceleration arithmetic for both samplers. |
| `interpolate_transform_value()` | 31 | Shared numeric, tuple, color and discrete-field interpolation for both samplers. |
| `_commit_transform_continuation()` | 14 | Preserves historical reset/alignment commit policy for the single-time sampler. |
| `sample_transform_state()` | 37 | Source-order single-time evaluation and the ordered sampler's fallback. |
| `sample_transform_states()` | 78 | Ordered timeline evaluation with bounded local caches and fallback. |

The new module would depend on `math`, `re`, `typing.Iterable` and four existing
interpreter exports: `OverrideContinuation`, `OverrideEvaluation`,
`apply_override()` and `apply_font_size()`. All other calls are built-ins or calls
within this group. It needs no engine constants, `Event`, measurement class,
report, filesystem path or pass context. Runtime annotations resolve without
importing the engine.

The engine's incoming consumers are:

- `upright_transform_pose()`: samples candidate transforms; retains pose policy.
- `_sample_static_state_intervals()`: consumes ordered samples; retains interval
  evidence, opaque-span recording and selection inputs.
- `_source_row_palette()`: samples source paint at the requested time; retains
  caption/span and paint-ownership decisions.
- `adjacent_sustained_geometry()`: retains sustained-neighbor geometry policy.
- `infer_vector_text_cues()`: retains vector/text cue matching and reconstruction.

The dependency direction becomes engine → sampling → override interpreter, while
the engine continues to use interpreter exports directly. There is no reverse
import. Keep all six engine aliases, including helpers, rather than adding
forwarding wrappers or passing interpreter functions as callbacks.

## Ownership of data, caches, diagnostics and results

| Item | Existing owner and required preservation |
| --- | --- |
| Base formatting, styles, defaults, transform descriptions | Borrowed inputs. Single-time evaluation and every yielded sample own a shallow formatting copy. Do not introduce deep copying, input normalization or event mutation. |
| Parser continuation | Existing immutable interpreter record; independent evaluations borrow the seed and return the appropriate successor. Preserve absent versus explicit reset/latch state and the historical immediate commit rule. |
| Ordered sample times | The generator materializes its own list when iteration begins. Preserve its lazy evaluation, sample order, repeated times and fallback behavior. |
| Color decoding, completed prefixes and per-field targets | Owned by one ordered-sampler generator and discarded with it. No global cache or new pass context. |
| Optional `color_channels` argument to interpolation | Explicit caller-supplied mutable cache. Interpolation may populate it; it is not a borrowed read-only formatting dictionary. The ordered sampler owns the cache it supplies. |
| Evaluation results | Reuse `OverrideEvaluation`; its binding is frozen but its owned formatting dictionary remains mutable. Independent samples must not share that dictionary. |
| Diagnostics, counters and edit application | No diagnostics/counters belong to these six functions. Existing engine callers retain reporting, static-state selection, evidence recording and event replacements. |

Preserve optimized versus replay admission, source-order overlap handling,
relative/reset/repeated font-size behavior, malformed/nonfinite fallback,
rounding, color casing and tuple/discrete interpolation unchanged. This is not a
review of whether historical sampling policy should change.

Keep `select_static_state()`, freezing/text traversal, upright fallback, event
caches and evidence/context dataclasses in the engine. Adding those would expand
the dependency boundary into selection and reconstruction policy.

## Isolation and caller probes

A disposable module contains all six unchanged definitions. A fresh isolated
Python process imports it from an unrelated working directory without loading
the engine, Pillow, fontTools or HarfBuzz. All six annotations resolve. Symbol-table
analysis confirms the outgoing dependencies listed above.

Six current scripts ran against both the unchanged engine and a prototype whose
six engine aliases were rebound only inside child processes:

- `check_freeze_continuation.py`: **634,286** checks, **5,130** sampler cases,
  **1,440** selection cases and **576** continued-freeze steps.
- `check_relative_font_size.py`: **282** checks.
- `check_context_contracts.py`: **2,500** checks.
- `check_effect_continuation.py`: **179,958** checks across **3,144** effect cases.
- `check_static_strip_outline.py`: **80** checks, including **10** pixel-identical
  native libass syntax comparisons.
- `check_frame_pose_selection.py`: **66** source-pose checks.

All twelve executions passed with matching baseline/prototype summaries and
counts after adapting test instrumentation in the private driver. The runtime
manifest and all covered test-source hashes stayed unchanged. These use the
Windows font backend on Linux; they are not native Windows platform validation.
The full 93-script suite and thirteen-track corpus already passed for this same
v217 runtime; they were not rerun for this assessment.

### Required test-instrumentation adjustment

`patch_interpreter_bindings()` currently patches the engine alias and the
interpreter's defining binding. A sampler module would hold a third imported
binding. Existing instrumentation must observe that binding too, sharing one
replacement and deduplicating identical owners.

A control probe left instrumentation unadapted: the freeze check still exited
successfully, but its count fell from **634,286** to **153,794** because sampler
calls escaped the clean-buffer assertions. The unchanged **5,130** sampler cases
alone therefore did not prove equivalent instrumentation coverage. Restoring the
sampler binding restored the full baseline count. This is a test lookup issue,
not a demonstrated production behavior difference; do not solve it with runtime
forwarding, engine-global injection or a parser-to-sampler dependency.

Update the shared test helper and its instrumentation check as part of v218.
Cover calls through engine aliases, internal sampling and interpreter functions,
including deduplication for historical single-file engines. Preserve meaningful
assertions rather than accepting lower coverage counts.

## Preparation and implementation recommendation

No small production preparation currently establishes a boundary that is missing:
the inputs and results are already explicit, the interpreter types already live
in a dependency-neutral module, and v214 delivery discovers additional private
sources. Test-binding updates belong with the extraction, not in a separate
preparatory release. No event-model move or global API review is needed first.

One v218 implementation release should:

1. Capture the exact v217 runtime and verified corpus baseline. Move the six
   definitions unchanged, importing the existing interpreter objects and keeping
   direct engine aliases. Leave selection, freezing and reconstruction in place.
2. Update defining-binding instrumentation and add focused checks for independent
   import, aliases, annotations, input/result ownership, lazy sampling and
   sampler-to-interpreter composition. Exercise both optimized and fallback paths.
3. Audit moved definitions and the remaining engine against the baseline. Run the
   full current regression suite and exact-font corpus comparison; require
   unchanged outputs and complete meaningful statistics.
4. Verify actual installed execution, generic updater delivery and rollback,
   uninstall, and complete Python/PowerShell runtime manifests. Report native
   Windows checks separately where this Linux environment cannot run them.

After-release evaluation should confirm that sampling still owns only temporary
sampling state, consumers retain selection/evidence/reporting, and test patches
observe real bindings without production accommodation.

Assessment evaluation: the boundary is ready for one release. The instrumentation
coverage gap is a concrete item to address within that release, not a reason for
broader structural preparation. No new runtime bug or separate architectural
review was established. Global API and pass-local index reviews remain separate.
