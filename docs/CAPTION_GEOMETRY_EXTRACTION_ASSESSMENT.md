# Caption geometry — bounded extraction assessment

Historical assessment of v223. Implemented in
[v224](CAPTION_GEOMETRY_EXTRACTION.md); the evidence below describes the assessment.

Assessed against v223 (`2026.10.18.223`). Recommend **v224: extract explicit
caption anchors and conservative measured bounds into
`_simplify_ass/caption_geometry.py`**, retaining direct engine aliases. One
implementation release should suffice, with no intended behavior change or
preparatory API change.

Production, tests, the batch wrapper and delivery code are unchanged by this
assessment. The isolated prototype and fresh evidence remain private under
`validation/caption-geometry-assessment/`.

## Recommended boundary

Move these six existing definitions together, unchanged:

- `NUM` and compiled `POS_RE`;
- `get_pos()` and `set_pos()`;
- `inline_layout_key()`;
- `caption_bounds()`.

The definitions and assignments total 128 lines. Anchor reading/writing share
one existing numeric pattern; measured bounds consume the anchor reader and
inline-layout guard. This is an existing closed dependency group with a useful
contract: conservative caption footprints and the explicit anchors they use.
It introduces no general geometry framework or utility collection.

Keep nominal `text_height()`, state/layout fingerprints, vector tokenization,
row grouping, replacement and effect-specific geometry proofs with their
existing owners. Nominal height is a different estimate from measured ink;
`state_key()` includes paint. Do not move them merely because they contain
geometry-related values or would shorten a later extraction.

## Incoming and outgoing dependencies

Incoming uses include caption/support containment and layering, shared-interval
source extents, static-phase compositing checks, glyph replacement/occlusion,
whole-caption phase clearance and scrolling edge proofs. Many effect/pose
consumers also use the original inline-span guard. Row reconstruction and
implicit-anchor handling use `set_pos()`; position reading serves many more
processing passes.

Several engine consumers also read `NUM` or use `POS_RE` directly, including a
high-precision glyph-anchor rewrite. Retain canonical engine aliases for both
constants as well as the functions. Preserve their distinct spelling/precision
contracts; do not replace `NUM` with the interpreter's separate `NUMBER` pattern
or route every position rewrite through the two-decimal setter.

The new module needs standard-library `math`/`re`, the interpreter's existing
`OVERRIDE_RE`, and canonical `Event`/`FontMetrics` types for annotations. There
is no selector, rendering, document I/O, event replacement or engine dependency.
The font-metrics owner remains independently importable without optional font
packages; importing geometry does not initialize a metrics service.

Dependency direction is engine → caption geometry → interpreter/event model/
font metrics. No existing private module needs a source change, and no edge
returns to the engine. Import direct aliases before dependent uses. No moved
helper uses `__file__` or a filesystem path; font discovery stays with metrics.
No model, result dataclass, context or function signature needs alteration.

## Ownership and preserved policy

| Data or responsibility | Preserved owner and contract |
| --- | --- |
| Event text and formatting | Borrowed read-only. Anchor readers and inline guards do not resolve/cache state. `set_pos()` returns a string and never edits an event; it preserves its existing first-match, insertion, rounding and `None` behavior. |
| Inline layout evidence | The existing guard preserves complete original syntax when a later header separates literal spans, including paint-only headers. Do not reinterpret it as a new span correspondence proof. |
| Font measurements and caches | Caller supplies the existing metrics instance. Face lookup, shaping and ink measurement may populate that owner's caches. Geometry creates no metrics object, font cache or diagnostic report and does not inspect backend internals. |
| Missing or uncertain bounds | Existing rejection rules return `None` for absent measurements/faces/glyphs, unsupported inline layout, clips, drawings and incompatible projective poses. Missing-font handling stays silent here; selective font reporting remains caller-owned elsewhere. |
| Measured footprint | Preserve explicit/document wrapping, line/ink alignment, spacing, scale, authored stroke/shadow extents, overhang clearance, rotation/shear and finite-result checks. The helper uses the event supplied by the caller; it does not choose source versus reconstructed paint or impose the reconstruction outline cap. |
| Shadow-painted captions | The existing branch adjusts a local position and copied state when visible ink is painted by an offset shadow. It does not rewrite source formatting or count the shadow offset twice as padding. |
| Adjacency mode | The existing bounded near-front-facing estimate retains its separate clearance and admission rules. Callers still distinguish proximity estimates from full coverage proofs. |
| Bounds results and pass caches | Return the same four-coordinate tuple or `None`. Contexts such as shared-interval reconstruction retain their own bounds caches, source-span extent preparation and evidence lifetime. No cache moves into this module. |
| Proofs and reports | Geometry measures supplied events; callers decide containment, redundancy, compositing, scrolling membership/removal, event replacement and counters/warnings. Those decisions do not move with the helper. |

## Preparation and larger subsystems

No separate preparatory production change is needed for this extraction. The
canonical event and metrics types already supply a useful boundary. Direct
imports close the graph without wrappers, callbacks, alternate event records or
changes to data shape.

This extraction is itself useful preparation for larger processing subsystems:
it removes shared bounds/position/inline-guard dependencies from the engine.
The assessment also checked the remaining dependencies of concrete candidates:

- Scrolling still needs its nominal-height and resolved-state fingerprint helpers;
  its tracking, voting, report and cap policy should stay cohesive when extracted.
- Static-phase merging still needs event replacement, static-span/vector
  identities and frame-pose evidence preservation.
- Event replacement still needs its existing frame-pose identity proof. Keep
  source-proof invalidation attached to that edit operation rather than adding
  callbacks to bypass its dependency.
- Exact-font row recovery still needs the cross-pass font report type; moving
  that report into a row-specific owner solely to close imports is not justified.

Reassess those boundaries after v224; this does not prescribe a final hierarchy
or claim that all remaining processing dependencies are already closed.

Current spies on the engine's `caption_bounds()` observe engine call sites in
shared-interval and event-evidence checks. They remain correct there. No test
observer adjustment or production forwarding was needed in the prototype.

## Prototype evidence

The isolated whole-engine prototype moves all six definitions unchanged and
imports canonical aliases during engine initialization. Moved ASTs and remaining
engine executable AST match; every existing private source is byte-identical.

Independent import and processing load neither the engine nor optional font
packages. Alias/type/pattern identity, position reading/writing, unchanged input
objects, supplied metrics use, unknown-versus-adjacency bounds and local shadow
offsets pass focused checks. A deterministic metric double exercises cold
processing; existing exact-font and native tests validate actual ink separately.

Eight existing scripts are run against both baseline and prototype, without test
source substitutions or observer changes:

| Script | Result for each engine |
| --- | --- |
| `check_measurement_context.py` | 12,221 measurement/context checks. |
| `check_font_metrics.py` | 1,459 measurement, backend/cache ownership and parity checks. |
| `check_portable_caption_ink.py` | 49 portable ink checks with real HarfBuzz. |
| `check_simplify_ass.py` | 275 checks, including wrapping, shadow paint, scrolling edge proofs and cap behavior. |
| `check_inline_continuation.py` | 51,222 continuation checks; engine bounds spy remains at its actual call site. |
| `check_event_evidence.py` | 42 event-evidence ownership checks. |
| `check_outline_policy_render.py` | 92 outline/footprint and native geometry checks. |
| `check_caption_backdrop_layers_render.py` | 107 caption/backdrop checks, including real signs and stable one-run layering. |

All **16 executions passed**, retaining every assertion. No observer changes or
test source substitutions were needed. All run through the Windows BASIC/real
HarfBuzz runner; native rendering uses the available exact-font fixtures.

The production manifest still matches the fully validated v223 runtime; tracked
tests/helpers are unchanged. Full regression and corpus conversions belong to
implementation acceptance and were not rerun for this documentation-only
assessment. Linux Windows-backend/native-libass checks do not establish native
Windows filesystem behavior. Evidence is in private `audit.json`,
`alternatives.json`, `assessment.json`, `checks.json`, `identity.log`, paired logs
and prototype/drivers.

## Proposed v224 acceptance and evaluation

Extract the group unchanged, retain canonical constants/aliases, and add direct
module and installed-use checks. Preserve position precision/first-match behavior,
input borrowing, caller-supplied metrics ownership, unknown bounds, wrapping,
shadow offsets, actual source/output stroke extents and adjacency distinctions.
Keep the batch wrapper and generic delivery code unchanged.

Run the full suite and fresh baseline/current corpus comparisons, requiring
identical output and complete statistics. Verify independent and installed use
from unrelated working directories, updater discovery/rollback/uninstall and
complete Python/PowerShell runtime manifests. Record native Windows skips
separately from passes.

After release, confirm that the module measures supplied caption footprints while
callers retain their geometry proofs, caches, source-evidence lifetimes and
reporting. This assessment needed no adapter, duplicated proof, local exception
or new cache/diagnostic owner. No dedicated corrective review emerged; the
deferred global API and pass-local index reviews remain separate work.
