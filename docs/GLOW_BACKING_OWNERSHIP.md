# Backing paint follows cue handoffs — v193

v192 preserved settled paint through separate source fades, but the overlap
filter trimmed only foreground events. Retained offset backing text could
appear before its foreground and linger after the next cue arrived. In the
supplied “Numb your senses” cue, foreground ran 165.08–166.12 s while its backing
ran 165.06–166.15 s. The same mismatch affected its neighbors.

The stack coordinator now returns exact retained backing successors in
`TextRow.owned_backing`, under the same source-backed ownership proof that
already admitted their boundary phases. Text, typography, anchors, layers,
coextensive held intervals and matching opacity legs establish ownership; nearby
text or timing does not. Row reconstruction carries the complete backing tuple
when every joined foreground constituent retains its proved core. Virtual rows
cannot authorize trimming.

The overlap filter owns the handoff. After proving and protecting the readable
cores, it clips explicitly owned backing to the corresponding foreground's
resulting interval. It never extends backing, changes paint, changes the
foreground decision, or counts a second cue handoff. Multiple word owners of a
joined backing must agree on the cue interval both before and after trimming.
Incomplete backing lineage, competing foreground claims, removed owners or
changed rendered identities leave the backing untouched. Independent translucent
captions remain independent.

Ownership identity compares the rendered ASS fields except start/end, which belong to
separate timing evidence. Source-row preparation can retain a held-core snapshot
while current paint includes proved boundary phases; identical timing snapshots
are therefore not required. Current intervals bound all clipping. Source events,
shared row inputs, caches and parser continuations remain borrowed and unchanged;
only returned timing successors change. No new production counter is needed.

Focused checks cover foreground/backing handoffs, held-core snapshots with
acquired phases, unchanged paint, independent translucent text, changed copies,
competing owners, complete and incomplete joined backing lineage, and input
immutability. Real checks cover all four “Numb your senses” fragments and both
handoff edges. Historical parity checks now canonicalize absent backing ownership
as an empty tuple; nonempty ownership remains visible to comparisons.

Native lifecycle samples include the first and last five milliseconds inside a
cue, supplementing hold samples. Explicit 165.07 and 166.13 s frames compare with
the previous output after removing only the old cue's stray backing, so a stable
middle frame cannot hide edge residue. The nine established corpus sources are
compared against verified v192 outputs and statistics. The full supplied-track
comparison permits only shrinking backing timings, with identical event count,
text, paint and layers.

The previously documented generated-output reprocessing issue remains a separate
stack/reconstruction ownership follow-up; this release does not claim global
file idempotence.

Fresh verification: all 71 regression scripts pass, including 260 focused checks;
the historical authored-row comparator passed a focused rerun after its empty
ownership adapter was corrected. The initial full-run report and focused retry
are retained separately in `validation/owned-backing-regression-checks.json`.
Runtime and harness hashes match the verified checkout. All nine established
corpus outputs and statistics are byte-identical to v192. The supplied track
remains 324 events: only 44 layer-2 backing timings shrink, with all text, paint,
layers and unrelated styles unchanged. All exact fonts are available. Twenty-three
native lifecycles are stable through their sampled edges, all 14 top-left held
appearances match v192, and both explicit residue frames pass. The ten Python
wrapper checks and environment smoke test also pass.
