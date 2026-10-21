# Complete shrinking glyph-row processing — v245

The boundary assessed in
[SHRINKING_ROW_EXTRACTION_ASSESSMENT.md](SHRINKING_ROW_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/shrinking_rows.py`. Nine functions and three existing
frozen records moved unchanged: 237 definition lines including decorators.
The existing eleven-line `nearby_boundary_groups()` query has a neutral owner in
`_simplify_ass/boundary_groups.py`. Engine names remain direct aliases, preserving
signatures, canonical record identity and historical root pickle lookup.
Runtime version: `2026.10.21.245`. No behavior change is intended.

## Responsibility and ownership

The operation keeps source admission, resolved profiles, current-policy held-caption
freezing, shrinking/moving glyph proof, exact-font complete-row ownership,
ambiguity arbitration, caption extension and terminal-fade handoffs together.
Held paint, geometry, authored timing, source-ID counting and conservative refusal
remain unchanged. Later row reconstruction and general fade synchronization are
separate owners.

The shared query performs bisection around one fixed boundary. It preserves the
existing `(sorted_times, groups_by_time)` contract, inclusive `.05 + 1e-6` window,
authored times, ordering and original group-list references. It neither builds an
index nor owns a producer's payloads or acceptance rules. Shrinking-row matching
still applies its stricter exact/tiny-rounding boundary checks, rejecting actual
gaps and partial overlap. Boundary-glyph and departing-glyph matching retain their
own proofs through the same engine alias. No universal 50 ms matching tolerance
was introduced.

Inputs and their style/default catalogs, evidence, measurement context and supplied
metrics remain borrowed. Evaluated formatting, successor events, token/move/transform
lists, held-caption and glyph indexes, ownership claims, proposals, removal IDs and
replacements belong to one call. The three frozen records retain their intentional
shallow sharing. Font discovery, shaping and measurement caches stay with the
supplied FontMetrics; normal cache population is permitted. No metrics instance,
font handle, persistent cache, diagnostic owner or new result type is introduced.

Canonical event replacement still invalidates old contour/opacity coverage on a
formatting edit. Valid source-pose support can survive, retaining its original
intervals rather than acquiring the caption's extended lifetime. The extraction
does not override that evidence policy.

`_prepare_source_text()` retains level-one gating, configuration, vector/rotation
stage order, working-map adoption, later glyph/source-row processing and aggregate
reporting. Its pre-collapse `timing_sources` snapshot remains outside the producer.
Later resolved formatting is adopted only for the same authored object; an extended
caption cannot overwrite its source's original timing. The result remains the
existing `(event_mapping, removed_source_count)` tuple, preserving refusal mapping
identity, insertion order, untouched Event identity and unique-source-ID counting.

The module depends on eleven private owners and the standard library. The query
module depends only on standard-library bisection. The graph is acyclic without
engine imports, production adapters or forwarding. No path-sensitive code moves.

## Validation and delivery

Nine new module tests protect canonical aliases, annotations and historical
pickle lookup; shared read-only fixed-boundary queries and an existing boundary
consumer; local resolution/index ownership and shallow frozen records; complete
rows with held paint, geometry, context, ordering and input-cache preservation;
incomplete, ambiguous, gapped and unavailable-fit refusal; terminal-fade cutoffs,
real gaps and uncertain visible predecessors; evidence expiry and retained source
pose intervals; actual caller timing history, level gating and accounting; and
cold source/installed execution from unrelated paths containing spaces, with
owned uninstall preserving a user file.

Interpreter observers now include the defining shrinking-row consumer. The existing
effect-continuation check installs its recording/failed-fit double at that consumer's
actual fit binding, scoped to its shrinking scenarios. All original assertions
remain; production imports do not forward through test spies.

Fresh v244/v245 comparisons cover 3,504 cases across 73 scenarios, three input
orders, four measurement modes, two blur limits and resolved/unresolved input
states. Complete output, source-ID counts, mapping/key order, retained identity,
fit attempts and repeat decisions match. Input values and cache identity remain
unchanged; bounded repeat calls remove nothing further. Twenty shared-query
comparisons also match. Both focused whole-file conversions retain identical bytes,
complete statistics and font reports under actual current paint/timing policy.
Native libass output matches across all sixty frame pairs for complete, terminal-
fade, real-gap, partial, gapped and ambiguous rows with exact Arial regular.
A deliberate mutation confirms that the caller test rejects replacing historical
timing with extended captions.

All 117 current regression scripts passed with Windows BASIC plus real HarfBuzz
on Linux. Full runtime and harness manifests remained fixed throughout the final
validation run.

Fresh comparison and native-render evidence uses the actual v244/v245 implementations.
Archived builders provide variations without historical fade/paint substitutions
or obsolete single-file helper-count/trace requirements. Complete runtime manifests
and the regression harness identify the final validated sources. Required fonts
are prerequisites; strict-font corpus conversion stops on a missing required face.
All thirteen corpus tracks retain identical output bytes and complete statistics,
with no missing required-font diagnostic. All 124 recorded font hashes were verified.

The unchanged recursive installer/updater deliver both modules without a filename
list. Delivery checks exercise rollback when either new owner is locked, retry,
preserved launcher choices/user files, cold installed exact-font processing and
owned uninstall. Python and PowerShell recursive manifests cover the whole runtime.
Installer checks pass 32 with two native Windows skips; updater checks pass ten
with one native Windows skip. MKV extraction, conversion, remux/extraction and
font-sync smoke pass. Native Windows filesystem and launcher behavior requires
separate Windows validation.

Fresh reports remain under ignored `validation/shrinking-row-extraction/`; the
production wrapper, report counters and delivery implementation are unchanged.

## After-release evaluation

The complete shrinking-row proof and handoff have one owner. The shared query owns
no producer's indexes, while the caller retains original timing, stage orchestration
and aggregate reporting. No adapter, duplicated proof, local production exception
or downstream repair was needed. No new dedicated follow-up review was identified.

The scrolling iterator contract and global API/index reviews remain separate.
