# Structural review closure — v167

This release finishes the three previously deferred visibility contracts and
removes the unused raw document buffer. It preserves simplification policy.
The scope fits one release: all three passes feed the same final-layout stage,
and document-buffer removal is independent.

## Visibility interfaces

| Pass | Result | Pipeline application |
| --- | --- | --- |
| `collapse_translated_phase_rows()` | `TextPhaseRowsResult(events, removed_count, rows, visibility_updates)` | Apply accepted text before fragment-phase matching. |
| `collapse_fragment_phase_rows()` | `TextPhaseRowsResult(events, removed_count, rows, visibility_updates)` | Adopt events, combine protected rows and apply text before fade handoffs and reconstruction. |
| `merge_shared_interval_rows()` | `SharedIntervalRowsResult(events, rows_joined, tails_retained, visibility_updates)` | Adopt events/counts and apply generated-ID visibility after all rounds finish. |

Events and visibility inputs are borrowed. Results have immutable bindings and
caller-owned working collections. Deltas retain the former accepted assignments,
including equal-value assignments; removed source entries remain history. No pass
copies or traverses the entire input map. Separate calls return independent delta
dictionaries. Pipeline application copies assignments into its own map.

Translated and fragment passes collect proposals before accepting replacements;
they need no internal overlay. Shared-interval merging owns one `ChainMap` overlay
across four bounded rounds. Its private one-round helper explicitly takes a
pass-owned mutable map. Generated captions and tails remain readable in later
rounds without modifying borrowed visibility. Its round and proposal helpers and
local edit accumulators remain useful; no compatibility wrappers are introduced.

The pipeline applies each delta at the former mutation boundary. Protected
`phase_core` evidence and overlap trimming, compaction, static reconstruction,
touching-copy merging and shared-interval ordering are preserved. Phase counts
still mean removed events; shared counts mean accepted rows and retained tails.
Explicit font reports retain commit/discovery behavior, including completed work
before later failures. Visibility applies only after successful pass completion;
font reporting is not rolled back.

These three Python pass APIs intentionally change from tuples to named results.
Direct callers must adopt fields and apply visibility before later consumers.
The public conversion API, CLI and launcher behavior remain unchanged.

## Document and original-plan contracts

`SubtitleDocument` owns parsed records, styles, event indices, field names and
measurement metadata. Parsing still receives source text but does not retain a
second unused `raw` member. Document/event/style isolation and CR/LF records are
unchanged. Shared I/O and in-memory render/reparse normalization preserve timing
precision, event renumbering and clearing text proof state before backdrops.

| Original goal | Final boundary |
| --- | --- |
| Explicit entry points | One public `simplify_ass()`, distinct text/vector and legacy entry points, and named pipeline stages. |
| Shared I/O and text/backdrop boundary | Shared document reader/writer, explicit text result and in-memory normalization, separate original drawing source. |
| Cohesive algorithms | Meaningful proof, fitting and ownership helpers; readable coordinators; redundant wrappers consolidated. |
| Explicit state ownership | Separate formatting, immutable evidence, measurement and continuation; explicit row/source/visibility results and named cache owners. |
| Font responsibilities | `FontMetrics` for reusable font operations, `FontOutlineMatcher` for decoding/profiles, functions for row geometry, caller-owned `FontProcessingReport`. |

No general splitting or module extraction is needed to close this plan. The
catalog/text-style replacement API and backed-pulse index payload remain agreed
separate reviews. Deprecated legacy code and the regression-reader API retain
their callers and are intentionally preserved.

## Recorded v167 verification

This report records structural-plan closure in v167. README.md and
DOCUMENTATION_REVIEW.md describe the subsequent documentation-only release.
The interfaces and ownership contracts above remain current.

All 49 current regression scripts pass, including 1,154 new ownership/source
checks and 115 pixel-identical libass comparisons. Direct v166 comparisons cover
phase admission/rejection, geometry, protected row evidence, timing, counts, font
reporting, generated IDs, retained tails, event ordering and applied visibility.
Lookup-only maps reject whole-history copying; failures after real acceptance
leave caller events/maps unchanged. Later rounds can read pending generated text.

The AST audit permits exactly 15 changed existing definitions and two new result
classes. All unrelated definitions match v166, including numerical and matching
proof algorithms. Earlier font-extraction audits retain their numeric/caller-policy
assertions; only subsequently changed contracts use their immutable v166 extraction
reference. A separate current audit verifies this release's bounded changes.

Seven full conversions preserve output bytes and statistics against v166 and
pre-migration v156. Six fixture reports, logs and summary match after excluding
engine identity and duration. Full conversions use the established complete fixture
font catalog; the unchanged smaller packaged font subset serves focused tests.
BAT banners advance to v167, PowerShell files remain byte-identical, all packaged
Python scripts compile, and the archive's SHA-256 manifest verifies every entry.

Run `python validation/run_review_checks.py` from the extracted package. See
`validation/final-visibility-ownership-checks.json`,
`validation/final-visibility-structure-audit.json`,
`validation/complete-regression-checks.json` and
`validation/full-conversion-comparison.json` for recorded evidence.
