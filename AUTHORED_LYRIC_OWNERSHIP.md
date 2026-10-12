# Authored lyric source cache and row evidence

Ownership migration completed in v163; contracts reviewed for v168.

The first bounded candidate from the v162 review is resolved. Source evaluation
and row collection now return explicit updates. Matching, paint, timing and
reconstruction decisions retain their previous behaviour.

## Results and caller responsibilities

| Pass | Result | Caller responsibility |
| --- | --- | --- |
| `match_authored_lyric_rows()` | `AuthoredLyricRowsResult(removed_sources, row_additions, source_updates)` | Adopt matched source IDs/rows and apply the source-cache delta before later state readers. |
| `remove_letters_over_full_lines()` | `FullLineCopyResult(events, removed_count, row_additions, source_updates)` | Adopt retained captions, keep row additions for coverage, and apply source updates. |
| `_consolidate_text_events()` | Existing pipeline result | Applies source updates to its source map and exact aliases in its timing-source map before reconstruction/coverage. |

`collect_rows=True` replaces the old mutable row-list argument. It enables
static scaffold row collection and, when a source map is supplied, authored
moving-row matching. Its default is false, preserving the former no-evidence
path. Supplying a source map alone still does not enable authored-row matching.
No existing evidence list is passed into the pass or modified. Returned row
additions include both authored moving-letter rows and static scaffold rows.

## Cache and alias ownership

Resolved source events are reused read-only, with no redundant field assignments.
An eligible unresolved source receives one private successor, evaluated from its
complete text; a stale continuation on an empty cache cannot seed that parse.
The cache edit retains source text, timing, evidence, measurement context and
borrowed styles/defaults. `dataclass_replace()` installs the paired state and
continuation without invalidating unrelated historical proof.

A pass-local identity map contains only newly resolved successors. A final scan
maps their source keys, including aliases, into the sparse update delta. It does
not copy the source map or build an index for every unmodified event. Source
entries that fail later matching guards still receive the same evaluated cache
that the previous implementation installed before those guards.

When an input event also aliases an unresolved source, the pass uses the same
private successor for its proof and retained output. All source-map aliases share
that successor. The pipeline updates timing evidence only where it points to
that exact original object; a separate rewrite with the same source ID survives.
Removed source entries remain available as historical evidence.

Exceptions during matching/rendering leave borrowed events, source maps and row
containers unchanged. Result containers belong to the recipient; their frozen
record bindings do not make dictionaries/lists immutable.

## Migration verification

These are the recorded v163 results. README.md and validation/ record current
release verification; `validation/run_review_checks.py` reruns the active suite.

`check_authored_lyric_ownership.py` performs 7,014 checks over 740 differential
cases against immutable v162, plus five focused conversions. It covers cached
and unresolved sources, reset history, source/event aliases, duplicate map aliases,
rejected/incomplete/colliding rows, scaffold paint and tracking, input order,
collection opt-ins, external ownership and failed rendering. An Event setter
guard rejects even same-value assignments into borrowed objects. A direct
pipeline fixture proves row collection and caller-applied source/timing updates.

The v163 release passed 45 regression scripts, including 115 pixel-identical libass
comparisons. Seven full subtitle outputs and statistics match v162 and the saved
v156 baseline. Fixture diagnostics/logs/summary match v162 excluding engine
identity and duration. The AST audit allows changes only to the two passes and
the pipeline caller, plus two result records; the then-existing FontSpacing and all matching,
measurement, freeze, parser and row-reconstruction helpers are unchanged.

## Remaining candidates

Candidate 2, simultaneous catalog/text replacement policy, and candidate 3,
the backed-pulse index payload, are unchanged and remain separate tasks.
