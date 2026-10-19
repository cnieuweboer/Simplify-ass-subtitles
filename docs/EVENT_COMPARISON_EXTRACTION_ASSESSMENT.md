# Shared event comparison ownership assessment

Assessed against v229 (`2026.10.19.229`, commit `cb7ab9f`). Recommended next
release: **v230 — Establish shared event comparison owners**.
This is a bounded preparatory extraction, with no intended behavior change.
Production sources and tracked tests remain unchanged in this assessment.

## Why this next step

v229 closed the drawing-geometry boundary. The full supporting-drawing subsystem
still depends on shared resolved-state comparison, strict effect parsers and the
general frame-sequence reducer. The latter also consumes lyric-boundary and
near-static pose evidence. Moving all those dependencies into supporting
drawings would give shared policy a pass-specific owner; importing the engine or
passing callbacks would conceal the same dependency.

The next useful preparation is to put five small shared functions in existing
foundational owners. This is independently useful: their 29 definition lines
serve 116 distinct engine functions across drawing, text, rows, echoes, scrolling
and phase processing. The benefit is an explicit dependency direction for future
subsystems, rather than the number of lines moved.

## Recommended boundary and dependencies

| Function | Defining owner after v230 | External engine consumers |
| --- | --- | --- |
| `text_height()` | `_simplify_ass/caption_geometry.py` | 54 |
| `placement_key()` | `_simplify_ass/caption_geometry.py` | 32 |
| `text_layout_key()` | `_simplify_ass/caption_geometry.py` | 52 |
| `compatible_text_layout()` | `_simplify_ass/caption_geometry.py` | 1: `select_static_sign_paint()` |
| `state_key()` | `_simplify_ass/event_operations.py` | 30 |

Counts exclude calls among moved functions; consumers overlap. Keep direct
engine aliases for all five names and preserve signatures/defaults. No new
module, dataclass, processing context or result hierarchy is needed.

The four layout helpers borrow canonical `Event`, `DEFAULT_STATE` and the
existing `inline_layout_key()` in caption geometry. Only the canonical
`DEFAULT_STATE` import is added to that owner. `state_key()` needs only the
existing `Event` annotation and built-ins. There are no other outgoing runtime
dependencies.

The graph remains engine → event operations → caption geometry → event model /
interpreter / measurements, with direct engine → caption geometry imports.
Event operations already borrows the inline-layout guard for pose validity;
this preparation adds no reverse edge or engine import. No callbacks, forwarding
adapters, duplicate helpers or circular imports are required.

## Responsibilities and distinctions to preserve

| Concern | Owner and contract |
| --- | --- |
| Events, resolved formatting, defaults and metadata | Remain document/caller-owned and borrowed. These helpers read the supplied cache as-is; they do not resolve source text or install a cache. |
| Nominal text height | Keep the existing unit floor and absolute font-size/vertical-scale formula. It is a layout estimate, not an exact glyph measurement or caption-coverage proof. |
| Placement identity | Keep explicit margin versus resolved-style inheritance, clips and raw inline-layout distinctions. Do not normalize margins or discard inline history to broaden matching. |
| Exact layout identity | Keep the current field list and default fallbacks. Paint exclusion does not prove that copies are visually redundant. |
| Tolerant layout compatibility | Keep placement equality, case-insensitive font matching, exact orientation and existing 5% size/scale comparison. This remains distinct from exact layout identity. |
| General resolved-state identity | Keep sorted entries, caller-supplied omissions, underscore exclusions and existing six-decimal numeric/one-level tuple normalization. Do not add recursive canonicalization, defaults or parser continuation. |
| Caches and indexes | Remain with each consuming pass. No module-level cache, extra parsing, memoization or index redesign is introduced. |
| Source evidence, diagnostics and reporting | Stay with producers/consumers. No evidence lifetime, font cache, diagnostic owner, counter or stage order changes. |
| Results | Return the same tuples, boolean and float values. Input dictionaries, omit sets, events and measurement context remain unchanged. |

Do not combine these keys with `static_object_key()` or `_frame_pose_key()`.
Complete-span identity includes continuation and literal formatting; pose validity
uses its own geometry/literal and numeric representation. Similar-looking fields
serve different proofs. This release moves existing functions without creating
a universal comparison API or revising any tolerance.

## Preparatory work and later boundaries

**This move is the preparatory change; it needs no earlier production change.**
One release is sufficient. Keep row grouping/assignment, deduplication, frame
admission, scrolling recognition and supporting-drawing orchestration in the
engine for now. No current observer/stub adjustment has been identified.

This removes a shared dependency obstacle for several future subsystem
assessments. It does not make the entire supporting-drawing pass immediately
closed: strict effect parsing and shared frame-sequence processing still need
independent assessment. Likewise, do not relocate lyric-boundary evidence into a
vector-only owner simply to extract the reducer. Choose the next boundary from
the resulting graph; no final hierarchy or multi-release implementation plan is
prescribed here. The broader API and pass-local index reviews remain separate.

## Assessment evidence

An ignored prototype appends the exact five definitions to their proposed
owners and replaces root definitions with direct aliases. AST checks verify
identical moved definitions, unchanged remaining engine code except added
imports, and unchanged existing owner implementation except the added canonical
default-state import. All other private sources remain byte-identical. The
prototype retains the v229 version.

An isolated process passed cold import without optional font backends, canonical
aliases, inherited/explicit margins, inline protection, exact versus tolerant
layout distinctions, height floors, state rounding/omissions, borrowed inputs and
absence of cache installation.

Nine existing checks passed unchanged on baseline and prototype: **18 successful
script/version runs**, using Windows BASIC plus real HarfBuzz on Linux.

| Check | Results per version |
| --- | --- |
| Existing caption-geometry module contracts | 7 tests |
| Existing event-operations module contracts | 8 tests |
| Positioned row geometry | 26 checks |
| Frame-echo replacements | 16 comparisons |
| General simplifier, including scrolling fallback | 275 checks |
| Source frame poses | 66 checks |
| Parser effect consumers | 9,894 checks |
| Exact-font row geometry/reporting | 4,925 checks across 1,080 algorithm cases |
| Native source poses | 42 checks |

No test helpers, observers, assertions or expected outputs were changed. All 18
production source hashes still match verified v229; tracked harness inputs and
all 124 recorded font hashes were also verified unchanged after the checks.
The local `assessment.json` records these hashes and final results.

Local manifests, dependency audit, prototype and logs are in
`validation/event-comparison-assessment/`. Full regressions and fresh paired
corpus/delivery validation belong to implementation; this assessment does not
claim a new full run.

## Proposed v230 validation and after-release evaluation

Extend the existing caption-geometry and event-operations module checks with the
new canonical aliases and their distinct read-only contracts. Include empty
caches, inherited/explicit margins, inline layouts, default fields, font case,
size/scale boundaries, omission sets and mixed numeric/vector state. Cover cold
and installed processing, function lookup, manifest agreement and owned removal.

Run the full current regression suite and all 13 fresh paired corpus conversions,
requiring identical bytes and complete statistics. Keep row/font geometry,
echo/scrolling, source-pose and native rendering checks. Verify the actual
shipped updater's rollback/retry, installed processing/uninstall and MKV smoke
test. Leave `simplify_subtitles.py` unchanged and identify native Windows skips.

Afterward, confirm that consumers still choose which comparison is appropriate,
with no new owner mutating source evidence or caching pass results. Broaden the
review only if moving the helpers exposes conflicting consumers or requires
adapters. No dedicated corrective follow-up is currently indicated; the
remaining larger subsystem boundaries are planned modularization work.
