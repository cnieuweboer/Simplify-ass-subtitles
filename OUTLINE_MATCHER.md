# Exact-font outline matcher

Extraction completed in v165 and final wiring in v166; reviewed for v168.

Step 2 of the FontSpacing responsibility review extracted the decoder without
changing its algorithm. The matcher now owns profiles and borrows font operations.

## Interface and ownership

`FontOutlineMatcher(metrics)` borrows one existing FontMetrics owner. Its
`decode_cubic_outline(face, path, fs, unit, alphabet)` method returns the same
unambiguous string or None as the former FontSpacing method. Unsupported font
measurements retain their existing exception propagation; cue inference retains
its existing catch/rejection boundary.

The matcher owns its private profiles. The CLI constructs one with its shared
FontMetrics before the input loop. Separate matchers have independent profiles
even when they share metrics. Python callers supply a matcher for batch reuse;
otherwise each conversion uses a local matcher.

infer_vector_text_cues() calls outline_matcher.decode_cubic_outline() directly.
FontSpacing is removed in v166. The matcher does not discover fonts, create a
catalog or copy font bytes, faces, instances, shaping or raw-outline caches.
Source-specific evidence remains in the existing vector-text passes.

| Data | Owner and cache scope |
| --- | --- |
| Exact face identity, coverage, raw contours, advances, instantiated bytes | Existing shared FontMetrics owner; unchanged in this release |
| Alphabet-specific contour/advance profiles | FontOutlineMatcher, keyed by exact face key and sorted admitted character tuple |
| Source drawing path, font size, fitting tolerance, decoder search state | Local to one decoder call; not retained as reusable profile evidence |
| Source/text fit success or rejection | Existing VectorTextFitContext cache, local to vector reconstruction |
| Caption timing, opacity activation, paint, replacement events and claims | Existing vector-text passes; never stored in matcher profiles |

Cached profile lists are matcher-owned internal containers. They borrow immutable
font contour tuples and contain character/contour/em/advance measurements, not
Event objects or source IDs. Consumers do not mutate these cached containers.

## Preserved decisions

The searchable characters remain printable ASCII plus literal input characters,
filtered by whitespace and exact-face coverage. Equivalent alphabet ordering,
already included ASCII and whitespace produce the same cache key. NonASCII
additions and requested variable coordinates distinguish keys as before.

Stamp/grain exclusion, unsupported-outline handling, empty negative profiles,
and retry behavior after an exception while building an incomplete profile are
unchanged. Nominal ASS size, scale/baseline continuity, measured spaces, geometric
error tolerance and ambiguity rejection are unchanged. Size and source placement
remain per-call evidence; they do not belong in the profile cache key.

The search still rejects more than 4,096 examined nodes or more than 32 pending
options. No language model, word list, guessed cue timing or new matching heuristic
is introduced. Raw outline inspection and fragmented-glyph measurement remain in
FontMetrics; cue creation and effect-removal authorization remain in the passes.

## Verification

The v165 extraction compared the unchanged decoder against v164 after normalizing
only the profile-cache name. In v166 the whole FontOutlineMatcher implementation
is AST-identical to v165. Its focused suite passes 1,235 checks over 91 search cases
and 249 integration cases, cache/error/lifetime assertions, real-font contours and
two focused conversions. The complete bounded caller audit now lives in the row
suite; numeric matching assertions and integration scenarios remain covered.

Run `python validation/run_review_checks.py` for current regression results.
README.md records current release verification; historical extraction harnesses
remain separately inventoried.

## Responsibility review complete

Step 3 removed FontSpacing and separated row geometry/reporting. See ROW_GEOMETRY.md
for final API, report ownership and batch/failure contracts. The broader catalog/text
replacement API and pass-local index reviews remain deferred.
