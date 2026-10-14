# Measurement context and parser bookkeeping — ownership contracts

Migration reviewed in v162, source-cache follow-up in v163; documentation reviewed for v168.

The completed migration preserves the existing matching and rendering policies.
The v162 review corrected stale contract documentation and test harness paths.
The v163 follow-up resolved its first bounded candidate: authored lyric source
caches and row additions are explicit results, applied by the pipeline owner.
Matching and rendering behaviour remain unchanged. The executable AST audit
bounds the follow-up to three functions and two result records.

## Final ownership contracts

| Object | Owner / permitted sharing | Lifetime and edits |
| --- | --- | --- |
| Parsed styles | Document owns catalog and each style dictionary; events borrow them read-only | Text preparation shares the catalog. Measurement preparation copies the map and each style. Native values are immutable scalars. |
| Lines and event field order | Parsed document owns lists; prepared documents borrow them read-only | Rendering constructs new lists. Event indices belong to their own parsed document. |
| Event formatting | Cache owner installs a formatting/continuation pair; consumers borrow it read-only | Timing successors may share the dictionary. Formatting edits use a fresh buffer. Empty cache is unresolved. |
| Document measurement | Frozen record shared by document/events | Canvas requires both authored valid dimensions. Wrapping is inactive until measurement preparation; explicit q wins. Replacements retain context unless a phase/document boundary supplies its successor. |
| Parser continuation | Frozen record paired with the formatting it evaluates | Adjacent blocks and literal spans retain history. Branches share immutable snapshots and own formatting copies. Ordered overrides return successors. |
| Evaluation record | Frozen binding, not a frozen dictionary | Complete evaluation/sampling own buffers. `event_evaluation()` borrows a nonempty cache or returns an uncached fresh parse. |
| Selected static state | Selection owns changed formatting; unchanged early return deliberately borrows the input | Selected continuation follows the chosen branch. Paint voting does not invent parser history. |
| Visibility, pose, settled snapshots | Explicit evidence inputs/results, distinct from rendered formatting | Seed containers are copied locally. Existing snapshot dictionaries are borrowed read-only; new snapshots are independent. Replacement evidence follows the existing proof-preservation rules. |
| Sampled frame-pose support (v200) | Immutable event evidence captured before paint normalization | Paint-only successors retain support for unchanged literal/layout/geometry. Timing clips support; interval extension grants no new exposure. Completed phase joins combine compatible support once. Serialization clears it. |
| Pass caches | Font/cache owner or bounded pass context | No new mutable global parser cache. Vector outline fits and negative results remain pass-local; backed pulse continuation map borrows immutable snapshots. |

A frozen `OverrideEvaluation` cannot guarantee immutability of its dictionary.
The same applies to a mutable Event's cache. Copy before applying overrides to
borrowed state; do not edit event defaults or document style dictionaries. These
contracts use ordinary dictionaries intentionally, without copying whole maps
or adding runtime freezing to every pass.

## Parser and replacement rules

`apply_override()` is the sole single-tag implementation. `evaluate_effective_state()`
starts a complete stream with empty history; `effective_state()` is its useful
formatting-only projection. None reset history differs from an explicit empty or
unknown reset. Named resets remain exact and case sensitive. An invalid first
alignment consumes the latch, which survives resets.

Transform targets own copies. Independent time samples restart from the same
seed. The sampler's historical commit policy remains explicit: target history
commits only fields already present in the base history, immediately when active,
independently of interpolation weight. Its optimized target/default seed rules
are preserved. Sustained geometry still wins over upright fallback.

Text/style replacement reparses complete replacement text and installs both
cache fields; supplied stale state/history does not override that authority.
Timing/layer/source-ID edits retain history and context. Nonempty resolved
paint/geometry edits retain history unless their branch provides its successor.
An empty state clears history. Formatting/layout replacements invalidate source
proof unless the caller explicitly supplies valid evidence. Reparsing reconstructs
styles, context and continuation; transient row/lyric/evidence state does not cross
serialization.

The v200 sampled frame-pose support has a narrower automatic handoff: paint-only
formatting changes retain it when `_frame_pose_key()` proves unchanged literal,
geometry, layout and measurement context. This does not retain historical contour
or opaque-span proofs. See [REPRESENTATIVE_FRAME_POSES.md](REPRESENTATIVE_FRAME_POSES.md)
for capture, clipping and completed-run ownership.

The v201 inline paint producer resolves corresponding literal ranges with the
existing static-span parser. Its uniform-geometry admission stays separate from
paint ownership. A local frozen set of approved source identities authorizes the
frame merger to match resolved span paint; descendants retain a contributing
identity. This proof does not outlive that merge call or cross serialization.
Original span visibility supplies source exposure before fade restoration. See
[INLINE_PAINT_OWNERSHIP.md](INLINE_PAINT_OWNERSHIP.md).

`dataclass_replace()` is intentionally lower-level: it preserves fields by default
and does not reparse or invalidate evidence. Its production formatting probes
carry corresponding branch/span continuation, retain source history for derived
measurement states, or explicitly use empty continuation for formatting-only
proof records. Callers using it to install a complete parse supply both fields.

## Matching and wrappers

`static_object_key()` includes literal formatting, continuation and document
context. Literal coalescing retains reset/latch distinctions, including absent
versus explicit empty reset and inactive versus explicit mode-zero wrapping.
`state_key()` deliberately continues to ignore parser history and compares
resolved paint/geometry. Event dataclass equality continues to exclude these
internal records. Pre-migration matching regressions verify decisions, rather
than simply dropping the newly typed values during comparison.

The short helpers remain useful:

- `effective_state()` gives formatting-only readers a clear complete-parse API.
- `event_evaluation()` centralizes cache borrowing versus independent parsing.
- `_commit_transform_continuation()` names a nontrivial historical animation rule.
- `_normalize_text_result()` names the intentional serialize/reparse measurement
  boundary, including regenerated indices and cleared transient proof.
- `load_subtitle_events()` retains the established resolved-reader interface used
  by tools/tests. It is unrelated to the removed parser compatibility adapters.

These helpers name distinct parsing, cache or normalization contracts. No surviving
parser compatibility adapter or legacy-key access remains. Docstrings for `Event`,
`OverrideEvaluation` and `apply_override()` state ownership accurately; old documentation claiming
parser bookkeeping still lived inside formatting has been corrected.

## Follow-up status

1. **Authored lyric source cache and row evidence — resolved in v163.**
   Both passes now return source updates and row additions. The pipeline applies
   them before reconstruction/coverage and adopts exact timing-source aliases.
   See `AUTHORED_LYRIC_OWNERSHIP.md` for preservation and opt-in rules.
2. **Simultaneous catalog and text/style replacement.**
   `replace_event()` resolves a text/style replacement against the original event's
   catalog and overwrites supplied defaults. No production caller combines text/
   style replacement with a catalog swap. This preserves prior behaviour, but the
   general API should eventually either explicitly reject that combination or
   define successor-catalog precedence. Treat it as a separate API decision, not
   an incidental cleanup in this behaviour-preserving review.
3. **Backed pulse index payload.**
   `BackedPulseContext.details` and `.continuations` use parallel source-ID keys.
   Producers and consumers agree. Continuation snapshots are immutable; formatting
   dictionaries and transform lists in the payload are borrowed read-only by
   convention. If this index changes, consider one typed payload carrying formatting, transforms, fade and
   continuation. There is no correctness reason to restructure it now.

## Verification and reproducibility

Run `python validation/run_review_checks.py` from the extracted directory. It
executes the current scripts listed in `validation/regression-inventory.json` and
records exits, summaries and runtime hash in `validation/complete-regression-checks.json`. Three rendering
checks perform 115 pixel-identical libass comparisons. The final contract test
performs 2,500 checks over 100 override streams using read-only catalogs/caches,
branch-buffer identity, phase ownership and full-cache/static-key parity.

Additional active checks cover row-reconstruction ownership, frame replacement
order/identity, fade handoffs, complete lyric copies, masked glyphs and translated
phases. Older boundary/reconstruction semantic references remain active through
the established tests. The general pipeline test now compares the complete
current reader representation with the immutable v166 reference; the earlier
formatting/history boundary comparators remain active in their dedicated regressions.

The v162 review restored the standalone fade runner's event-comparison import and
helper inventories needed by the masked/covered runners, which had been missing
from earlier bundles. These remain packaged. The full-copy harness uses its
immutable reference for parser-call tracing; the visibility tests keep their older
semantic reference. Executable assertions remain active independently of docstrings.

The package retains 21 historical extraction/call-trace harnesses for reference,
listed separately in `validation/regression-inventory.json`. They encode earlier
function decomposition, APIs or mutation contracts and are not current test-suite
entry points. Their reusable scenarios feed current semantic tests where listed;
none are reported as successful current runs.

Current full conversions are compared with the preceding release and the saved
v156 baseline from before this higher-level migration. Six fixture reports, logs
and the suite summary exclude only engine identity and duration. README.md records
the current release results. Source inputs are hash-checked. See
`validation/full-conversion-comparison.json` and `validation/structure-audit.json`.

The v163 follow-up adds 7,014 lyric/source/row ownership checks over 740 cases,
with five focused conversions and explicit caller-application/exception checks.

## Historical font measurement follow-up — v164

Release v164 moved reusable font/cache ownership to FontMetrics. At that stage,
row fitting and outline decoding retained FontSpacing; the following releases
completed their extraction. See FONT_METRICS.md.
The catalog/text replacement and backed-pulse index candidates are deferred to
the broader API and pass-local index reviews respectively.

## Historical outline matching follow-up — v165

FontOutlineMatcher now owns the alphabet-specific profiles and unchanged decoder.
Its font owner is the same shared FontMetrics instance; source-specific evidence
and vector fit caches remain in the existing passes. See OUTLINE_MATCHER.md.

## Final font responsibility boundary — v166

FontSpacing is removed. FontMetrics owns font caches; FontOutlineMatcher owns
profiles; row geometry functions borrow FontMetrics explicitly. Passes retain
source evidence, fitting authorization and edit accumulators. An explicit caller
FontProcessingReport retains the original selective discovery and commit sites,
including batch/failure behavior. See ROW_GEOMETRY.md for final contracts.
Deferred catalog/text replacement and pass-local index reviews remain outside scope.

## Original structural plan closure — v167

The three deferred visibility writers from VISIBILITY_OWNERSHIP.md now return
explicit updates. The pipeline applies them; shared-interval rounds retain
pending generated text in a private overlay. The unused SubtitleDocument.raw
member is removed. FINAL_STRUCTURAL_REVIEW.md records final contracts and
verification. Separate API and pass-local index candidates remain deferred.

## Caption/background handoff — v188

`CaptionSupportResult.ownership` owns its list of frozen
`CaptionPanelOwnership` bindings. Each binding borrows its panel and caption
records, catalogs, caches and original-contour evidence read-only. Frozen bindings
do not make those borrowed Event objects immutable. Final layer edits use
successors and return new proof bindings. A hidden panel can survive in proof
context after its output fill is removed, preserving the distinction between
the owned background and an independent card. Rebuilt support associations do
not authorize new ownership. These proofs live only in the support result;
serialization does not persist them or add role flags to Event/font resources.

The v197 backing-paint handoff borrows the existing font owner and original
backing/foreground states. `SourceCaptionPaint` contains only immutable scalar
paint values; renderer consumers borrow it. Samples are pass-local, replacements
own newly parsed paint tags, and the proof does not survive serialization.

v198 extends `SourceCaptionPaint` with immutable border-width values. Producers
establish contour authority/absence before rendering; the renderer borrows that
proof. Source-aware span serialization and held-glyph matching retain the same
formatting decision. Shadow transfer changes paint origin and invalidates a
foreground proof. No event-history lifetime or replacement-invalidation rule changes.
