# Connected original full-copy families — v250

Local version `2026.10.23.250` implements the
[transitive-copy assessment](TRANSITIVE_COPY_ASSESSMENT.md).
Publication is pending the exact-font visual check described below.

## Admission and ownership

Full-copy cleanup retains its existing text/style/actor/placement grouping and
80% shorter-original overlap test. Connected components are discovered from
positive-duration original working events before any removal. There is no common
anchor requirement, all-pairs requirement, paint equality requirement or family
size/duration cap. A zero-duration record can join one unambiguous containing
component, but cannot create a connection between components. Touching and gapped
cues remain separate.

Each accepted family selects text and representative paint once from its complete
originals in source-ID order. Replacement timing uses their full union. Compatible
original pose support retains original exposure, rather than inventing dwell over
the expanded replacement. The existing producer-owned color timeline remains
available to its later emitter. No output caption becomes fresh matching evidence.

Visibility stays a borrowed history plus sparse returned updates; callers retain
level gating, stage order, unconditional delta adoption and aggregate reporting.
Untouched events preserve identity and actual list-slot order.

## Independent compositing

Connected matching alone is insufficient. Independent content between copies in
ASS layer/list order can obscure a flattened caption. This already affected v249's
anchored families; larger components would extend the damage.

The producer compares the replacement's side of active independent ink with
original foreground coverage over that peer's lifetime. Lower effect planes do
not block a merge when original upper planes already cover the whole relevant
interval. Nonconcurrent content and unchanged foreground ordering need no font
measurement. Shared exact-font clearance allows distant content, including
conservatively bounded scale/stroke animation. When separation cannot be proved,
original copies are partitioned onto their original sides of the independent ink.
Each child is checked again because its preferred source geometry can change.
Unknown measurement does not authorize a crossing.

Output layer zero remains the ordinary simplification where normalization preserves
order or measured separation. Otherwise the retained original's layer survives.
This prevents normalization itself from defeating the same ordering proof.

No later cleanup repairs ordering, and no show names, lyric strings, source-ID
patterns or special font names select production behavior.

## Shared proof boundary

`_simplify_ass/caption_clearance.py` owns the existing implicit-anchor read and
measured replacement-clearance implementation, extracted without body changes.
The engine exposes direct aliases for existing consumers. The caption-paint tag
vocabulary moves unchanged to `caption_rendering`, also directly aliased.

Full-copy admission borrows caller-owned metrics and invokes the shared primitive
directly. It owns only its family/proposal buffers. There is no callback adapter,
engine import from a private module, new global context, cache owner or diagnostic.
Geometry probes do not perform representative-paint selection or claim sources.

## Validation

Fresh evidence is kept under ignored `validation/transitive-copy-fix/`, separately
from assessment prototypes and older release reports. Runtime evidence covers the
engine and all private Python sources; source/font hashes are checked around corpus
conversion. The regression backend uses Pillow BASIC plus real HarfBuzz on Linux.
It does not claim a native Windows platform run.

The direct matrix covers 1,728 variants with complete event snapshots, mutable
and read-only visibility, borrowed-input/state identity and repeat calls. The
24 focused module cases include connected chains of 20 and 100 sources,
interleaved ink, original foreground coverage and gaps, mixed layers, distant
and animated peers, matched-fade color phases, cold delivery and uninstall.

The 13-track corpus comparison has nine byte-identical outputs. Changed tracks:

- Overlord: original ordering retains 30 additional output events (2,088 → 2,118;
  peak concurrency 32 → 34). Full-copy removals change from 586 to 157; later
  effect/row processing still reduces the retained source layers.
- Attack on Titan: four additional sign events (351 → 355), with source-supported
  timing and representative pose changes. The affected signs at
  12:07.79–12:09.20 require **Señor Domingo, bold** for native rendering. That exact
  family is absent from the supplied local and archived fonts; this visual check
  remains pending and no substitute is accepted.
- Solo Leveling: output count/text/timing are unchanged; several isolated edge
  contours now agree with their neighboring reconstructed gradient spans.
- Goblin Slayer: only the two next-preview captions' layers change (0 → 2),
  preserving their representative paint and all statistics.

Native exact-Arial checks cover 150 source/reference frame pairs. Three changed
corpus tracks additionally have 48 source/v249/v250 frames rendered with their
active fonts.

All 119 current regression entrypoints pass: 117 results from the complete run,
plus focused rechecks of the two isolated historical assertions updated during
that run. The engine/private-source manifest and common test dependencies are
unchanged; both corrected entrypoints are rechecked against the final harness.
The original run report is preserved alongside the explicit combined report at
`validation/transitive-copy-fix/final-regression-checks.json`. Module delivery is
also checked through the shipped updater, including failure rollback, preserved
user files/choices, cold processing and uninstall.

The release remains local, pending the missing-font visual check. No fallback
font was substituted and `simplify_subtitles.py` is unchanged.

## After-release evaluation

The implementation extends the existing producer and shares its measured proof;
it introduces no late repair, local show exception or duplicate geometry algorithm.
Necessary layering can reduce the removal count relative to v249: that is the
intended protection of independent ink, rather than a new family-length bound.
A dedicated follow-up is warranted for coordination between independent caption
families. In two variants of one synthetic arrangement, accepting one family
removes an intervening plane that blocked another family. That other family can
merge on a second call. All twelve v249 repeat variants caused by incomplete
original chains are resolved; these two variants expose a separate dependency
between families. Do not fix it by feeding rendered unions back into discovery
or by adding arbitrary family bounds. General whole-file second-conversion
stability also remains distinct from this producer's contract.

Several historical integration tests assumed unrelated final cleanup still
matched old whole-file output. This release checks the actual producer handoff,
immutable inputs, retained identity and timing-only edits instead, retaining
historical target parity for equivalent incoming evidence. The remaining
historical tests deserve the same stage-boundary discipline when future behavior
changes expose that coupling.
