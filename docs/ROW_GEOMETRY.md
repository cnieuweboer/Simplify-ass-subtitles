# Font row geometry and reporting

Extraction completed in v166; contracts reviewed for v168.

Release v166 completed step 3 of the FontSpacing responsibility review. It removed
the combined class and migrated all callers together. There is no production alias,
forwarding method or replacement service containing the same algorithms.

## Final responsibilities

| Owner | Data and lifetime |
| --- | --- |
| FontMetrics | Reusable catalog and private font caches: discovery, exact variants, bytes, shaping, raw outlines, coverage and ASS metrics. May span a batch. |
| FontOutlineMatcher | Borrows the same metrics owner; owns alphabet-specific profiles. CLI creates one before its input loop. Profiles never contain events or timing. |
| Row geometry functions | Borrow metrics/events/formatting; return geometry or rejection. Do not edit events, row evidence or visibility, or retain source evidence. |
| Subtitle passes | Candidate admission, rendering/paint, timing proofs, ownership and replacements. Retain useful pass-local indexes/edit accumulators. |
| FontProcessingReport | Caller-owned accepted-join count and selective missing-family set. Contexts borrow its explicit reference; caches do not own reporting. |

FontMetrics and FontOutlineMatcher executable implementations are unchanged from
v165. Exact directory/name priority, collection selection, requested variable coordinates,
backend fallbacks and cache keys retain their existing contracts. This does not
switch requested variable variants to libass's regular-only behavior.

## Row interface

The six functions form one section immediately after FontOutlineMatcher. Each takes
`metrics: FontMetrics` first. Rendering remains in the existing caption renderer.

| Function | Return contract |
| --- | --- |
| recover_font_row() | Literal text, horizontal center, x/y scales and centered alignment; None for unproved/ambiguous spacing or geometry. |
| recover_tracked_font_row() | The same fit plus tracking; reuses spacing recovery, then proves separate advances without rescaling glyphs. |
| fit_fragment_anchor() | Authored anchor or None, retaining tracking, separate-glyph, exact-size and size-error options. |
| authored_glyph_positions() | New nonspace character/anchor pairs or None, using held geometry rather than fitting a size. |
| matches_authored_glyph_positions() | Boolean comparison against the shared authored-position model; remains a useful proof helper. |
| fit_fullwidth_run() | Fitted anchor and horizontal scale or None for an unbroken exact-font run. |

Thresholds, ambiguity handling, shaping safeguards, coverage checks, early rejections
and return values are unchanged. All six bodies match v165 after normalizing only
dependency/report ownership and docstring indentation. Every existing caller matches
after normalizing the documented API/resource wiring. Event/evidence policy remains
in the existing passes.

## Reporting contract

`FontProcessingReport()` creates `rows_joined=0` and an independent
`missing_families=set()`. Optional report arguments and report-bearing contexts make
shared mutation visible. No whole evidence map is copied for this change.

Counts increment at the same four commit sites: accepted translated phase rows,
fragment phase rows, shared glyph rows and measured text row joins. They count
accepted stage operations, not removed events, fit attempts or unique source
captions. Rejected proposals never increment the count.

Missing-font discovery stays selective. Spacing recovery and fullwidth fitting
record unavailable exact faces using their existing trimmed family names. Vector
outline fitting retains its untrimmed name. Tracked recovery inherits spacing
recovery's diagnostic. Direct measurements, anchor fitting and authored-position
checks stay silent. Coverage failures, ambiguous spacing and unsupported shaping
do not become missing-font warnings. An unsuccessful proposal may still discover
an unavailable face, as before.

The CLI owns one report, FontMetrics and matcher before its file loop. Counters and
discoveries accumulate across files, including work completed before a later
conversion/write failure. Final summaries, sorted family union, unavailable-backend
behavior and failure reporting remain unchanged. Reports are not rolled back.

Python callers choose a fresh report for independent totals or share one across a
batch. Reusing fonts/matcher does not inherit another report's diagnostics/counts.
Omitting the report discards reporting without changing output or decisions.
Reports contain numbers/strings, never events, indexes or cached formatting.

## Python API and batch reuse

```python
fonts = FontMetrics(font_directories)
matcher = FontOutlineMatcher(fonts)
report = FontProcessingReport()

for source, output in files:
    stats = simplify_ass(
        source, output, config,
        font_metrics=fonts,
        outline_matcher=matcher,
        font_report=report,
    )
```

`font_metrics=None` retains processing without optional font fitting. Without a
supplied matcher, a conversion creates one local matcher and reuses it across
vector measurement phases. Direct vector recovery creates a pass-local matcher
when omitted. Supply a shared matcher to reuse profiles across files, as the CLI
does. Public conversion/vector-recovery boundaries reject a supplied matcher with
a different metrics owner, preventing mixed catalogs/profiles.

The Python `font_spacing` keyword and FontSpacing methods are removed; callers use
`font_metrics` and the six functions. CLI spelling `--no-font-spacing` and launcher
choices remain valid. Immutable historical test references use test-only API
adapters; current production code has none. Recorded/failure doubles are mocked at
the extracted function boundary instead of adding row methods to FontMetrics.

## Verification and remaining work

The focused row suite performs 4,925 checks over 1,080 algorithm cases: return
values, borrowed event/formatting preservation, selective reporting, cache reuse,
fresh-report isolation, omitted reporting, mismatched owners and late failures.
It compares complete focused conversions and real CLI batches with immutable v165.
The source audit covers every existing class/function and all six numeric
algorithms, including unchanged FontMetrics and matcher implementations.

The v166 extraction passed 48 regression scripts and preserved seven full outputs
and statistics against v165 and the pre-migration v156 baseline. Subsequent
visibility-contract changes are checked separately. Run
`python validation/run_review_checks.py` for the current suite; README.md records
current release verification and validation/ holds its evidence.

The host has RAQM but lacks real uharfbuzz. Existing portable backend checks use
a deterministic substitute and do not claim real HarfBuzz pixel parity.

The simultaneous catalog and text/style replacement API review, and the pass-local
index review including backed-pulse payloads, remain deferred. No further
FontSpacing extraction step remains; neither deferred area changed here.

