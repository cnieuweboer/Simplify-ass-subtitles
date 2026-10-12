# Parser continuation ownership

Migration completed in v163; contracts reviewed for v168.

Subtasks 2–6 of Measurement context and parser bookkeeping are complete.
Document measurement context and event/row evidence ownership remain unchanged.

## State and ownership

| Value / API | Ownership and lifetime |
| --- | --- |
| `OverrideContinuation` | Immutable active reset name and first-alignment latch. Branches share snapshots until an override returns a successor. |
| `apply_override()` | Mutates the caller's local formatting buffer; borrows defaults/styles; returns continuation for the next ordered tag. |
| `Event.state` / `Event.continuation` | Resolved event formatting and its immutable parsing history are installed together by cache owners. |
| `event_evaluation()` | Borrows a nonempty cache and its history, or returns a fresh complete parse without editing the event. |
| `OverrideEvaluation` | Separately binds formatting and continuation. Complete evaluation and sampling own their result dictionaries; event cache views can borrow formatting. |
| `effective_state()` | Returns formatting alone when no further parser continuation is needed. |
| `sample_transform_state()` / `sample_transform_states()` | Borrow clean base formatting and explicit continuation. Return independent `OverrideEvaluation` snapshots. |
| `StaticStateSelection` | Selected formatting, selected continuation, pose proof, opaque intervals and settled geometry/paint snapshots are distinct fields. |
| `FrozenBlock` | Serialized overrides and the exact selection record used for serialization. |
| `StaticSpanSignature` | Frozen resolved fields plus immutable parser continuation; both participate in matching. |

Formatting defaults and style dictionaries contain resolved ASS fields. Parser
history does not live in canonical freeze/sampling buffers. None reset history
means no reset; `''` means explicit empty/unknown reset. A known name is exact
and case sensitive. None alignment means no override; True consumes the first
alignment, including an invalid tag. Explicitly false legacy seeds are retained;
legacy numeric seeds preserve their truth-value behaviour.

## Freeze and literal continuation

`_freeze_inputs()` returns the evaluated base and continuation together, plus
transforms, interval boundaries and the last authored literal reset used for
serialization. Transform event-level alignment/position/origin tags retain
their previous ordered header treatment. Literal resets and fixed tags advance
the local continuation in source order.

`freeze_block(..., continuation=...)` passes this continuation to selection.
`simplify_visual_text()` retains the selected continuation for the next block;
literal text never restarts it. Adjacent headers still use their existing
combination rules. Rendering retains border/shadow field insertion order and
the same style-relative serialization.

Literal resets clear inherited pose proof exactly as before. They do not clear
the first-alignment latch. Parser continuation, `prior_pose`, opaque spans and
settled snapshots have distinct input/result ownership.

## Transform branches and commit semantics

Each transform target copies formatting and starts from the current immutable
continuation. Ordered target overrides return local successors. Weighted
relative font-size replay uses that target's active reset style; it does not
look for history in a formatting dictionary.

`_commit_transform_continuation()` preserves the historical sampler policy:

- If a history field was absent in the base, a newly introduced target field
  does not become committed history.
- If it already existed, an active transform commits its target history
  immediately, independently of formatting interpolation weight.
- A transform before its start has no effect. Each independent time sample
  starts from the original base continuation.

The target reset can therefore govern font/default evaluation within that
transform without establishing an absent base history field. This subtask
preserves this existing policy; it does not reinterpret reset animation.

The optimized multi-time sampler preserves its existing admission rules and
completed-prefix arithmetic. It evaluates independent formatting targets with
the original reset-default seed policy. Context-dependent changes, unordered
times and nonfinite inputs still use the scalar evaluator. Each yielded
formatting dictionary is independent; sharing immutable continuation is safe.

## Selection and upright fallback

Every ranked interval carries its formatting and continuation together. Geometry
settledness and hold-voting probes copy a sample's formatting and borrow its
continuation for an independent target branch. Probe history is not committed
back into the sampled interval.

The chosen interval, an existing settled upright hold, or a complete upright
crossing supplies the returned continuation. Upright angle-only searches and
full-pose sampling share the same explicit base continuation. Representative
paint restoration, colour dwell voting and sustained geometry protection change
formatting without inventing another parsing history.

With no transforms and no event-paint input, selection retains both the original
formatting dictionary and continuation object identities. It accumulates visibility
and geometry evidence in local containers and returns it separately, preserving
the existing boundary rules without appending to caller-owned seeds. A freeze call owns its parsed formatting copy and passes through
the exact selection record; blur clamping does not rewrite evidence snapshots.

## Pose, visibility and settled evidence

`StaticPoseEvidence` remains immutable and explicitly inherited through
`prior_pose`. Opaque spans remain optional, separately returned millisecond
intervals. Disabled (`None`) and enabled-but-empty evidence remain distinct.

Settled snapshots are independent dictionaries of sampled geometry/paint.
Parser entries previously present in these dictionaries had no production
consumers: `upright_text_holds()` reads only resolved geometry/paint. New
snapshots therefore contain no parser history. The selected state's history is
fully preserved in `selection.continuation` and compared independently in tests.

Evidence seed containers are borrowed. The pass copies its local accumulators,
preserves identity of existing seed snapshots, and never edits them. New
snapshots cannot alias the chosen formatting buffer. No whole visibility map or
row-evidence collection is copied as part of this migration.

## Event caches, replacement and reparsing

Event formatting contains resolved fields only. Complete source parsers return
`OverrideEvaluation`; any owner installing a cache installs formatting and
continuation together. An empty event state is unresolved, and its stale
continuation cannot seed a complete reparse. `event_evaluation()` does not modify
an unresolved event; source-cache owners apply its pair only to owned successors. Authored lyric
matching now returns those successors as a sparse delta; the pipeline applies
that delta to its source map and exact timing aliases before reconstruction.
The source-fragment pass still isolates unresolved events before lazy caching.

`replace_event()` follows these rules:

| Edit | Continuation rule |
| --- | --- |
| Text or style | Recompute from the complete replacement text and resolved style. This supersedes any supplied state/continuation, preserving the previous authoritative-text policy. |
| Timing, layer, source index or nonformatting metadata | Retain the immutable snapshot. |
| Nonempty resolved state, defaults or styles | Retain the snapshot unless the caller explicitly supplies its branch continuation. These edits do not replay tags. |
| Empty state | Clear continuation, including an explicitly supplied stale snapshot. |
| Document reparse / measurement preparation | Evaluate independently from the new authored text and install both fields; never inherit source parsing history. |

Document measurement context survives independently. Historical drawing/opacity
evidence retains the existing preservation/invalidation rules. Pose and settled
geometry/paint evidence remain separate from continuation.

Validation targets copy formatting and start from an explicit immutable snapshot.
Ordered overrides advance only that local branch. Shared destination probes
that previously restarted from a held base for each component continue to do so;
sequential effect destinations retain their existing cumulative order. A backed
pulse index owns a local continuation map alongside its existing formatting/
transform/fade details, preserving original indexed event identities and borrowing
inputs without caching into them.

Boundary profiles and vector runs carry their freshly evaluated source history.
Scalar vector opacity sampling uses the continuation associated with that exact
run base. Instant opacity-switch probes that historically started from style
defaults still start with empty continuation.

Literal paint/geometry probes use the corresponding `StaticSpanSignature`
continuation, and per-glyph paint records carry their literal continuation to
probe events. Foreground-only and shadow timing geometry records contain
formatting alone; temporary event wrappers explicitly invalidate continuation
because those records do not promise a whole-event parser successor. Derived
paint/size measurement probes retain their source history without replaying tags.

All temporary compatibility adapters are removed. No production definition
contains any of the four legacy dictionary keys. Renderers consume formatting;
continuation is used only where ordered parsing or matching requires it.

## Matching and remaining work

Static-object signatures retain the established matching policy. Equality and literal coalescing
include formatting and continuation, preserving absent/empty reset and
consumed/unconsumed alignment distinctions. Geometry/paint readers consume
resolved fields without reconstructing parser history into formatting.

The final review found no remaining parser compatibility path or matching-policy
change. `state_key()` still compares resolved geometry/paint without parser history;
`static_object_key()` retains history and document context as matching distinctions.
Event equality continues to exclude cache, continuation, context and evidence.
See `CONTEXT_OWNERSHIP_REVIEW.md` for wrapper decisions, alias rules and bounded
remaining ownership candidates.

## Verification

Run `python validation/run_review_checks.py` for the current suite; README.md
records current release checks. The following describes the migration regressions.

Lifecycle regressions compare complete event formatting and parser
history against immutable v160, including timing/layer edits, resolved state
changes, cache invalidation, explicit branch history, text/style replacement,
comments and serialization/reparse. Event comparison reconstructs the historical
representation only inside test helpers; it does not discard history differences.

Effect regressions reuse established semantic cases without requiring obsolete
implementation call traces. They compare complete returned events, membership,
reconstruction, input ownership and reset/default/latch branches. Clean-buffer
assertions run while overrides execute. Prior override, inline, static-signature,
freeze, pose, measurement and evidence tests remain active.

The v163 release ran 45 regression scripts, including
additional reconstruction, frame application, fade, full-copy and translated
phase checks, plus actual libass rendering comparisons. The final contract test
adds 2,500 checks with read-only styles/caches. Earlier semantic tests still
compare against pre-migration override, matching and freeze references.

The v163 release preserved seven complete subtitle outputs and statistics against
both v162 and v156.
The six fixture diagnostics/logs and summary match v162 after excluding engine
identity and duration. The v163 AST audit bounds edits to the lyric matcher, full-line reduction,
their pipeline caller and two result records. Canonical parsing, static matching,
measurement, sampling, freeze and the then-existing FontSpacing definitions were
unchanged by that follow-up. FontSpacing was subsequently removed in v166; see
ROW_GEOMETRY.md for the current font boundaries.
Historical extraction/call-trace harnesses remain archived, explicitly
listed in `validation/regression-inventory.json`; they are not counted as passing
current tests.

See `AUTHORED_LYRIC_OWNERSHIP.md` for returned cache/row updates and opt-in rules.
