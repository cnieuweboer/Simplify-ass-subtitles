# Bounded override parser extraction assessment — after v215

The resulting [v216 extraction](OVERRIDE_PARSER_EXTRACTION.md) is documented
separately. This assessment records the pre-extraction boundary and evidence.

The next extraction is suitable for one implementation release, proposed as
**v216**. Move the existing ASS style/override interpreter into
`_simplify_ass/ass_overrides.py`, retaining direct aliases in `simplify_ass.py`.
This assessment changes documentation only; the runtime remains
`2026.10.16.215`. The disposable prototype described below is private evidence,
not a production extraction or a substitute for post-extraction validation.

## Proposed boundary

The dependency trace identifies nine existing definitions and six constants,
covering approximately 235 source lines including their documentation:

| Move together | Reason |
| --- | --- |
| `OverrideContinuation`, `OverrideEvaluation` | Existing parser history and evaluation results; retain the frozen dataclasses, fields and ownership contracts unchanged. |
| `tokenize_override()` | Recognizes ordered ASS tags and balanced parenthesized payloads. |
| `resolve_event_style()`, `parse_styles()` | Resolve style defaults and construct style catalogs from source lines, without document/event objects. |
| `apply_font_size()`, `apply_override()` | Existing ordered single-tag interpretation, including resets, first-alignment handling, relative font sizes, paint and placement. |
| `evaluate_effective_state()`, `effective_state()` | Complete-stream evaluation and its formatting-only projection. |
| `OVERRIDE_RE`, `TAG_NAMES`, `TAG_RE`, `NUMBER`, `DEFAULT_STATE`, `STYLE_TAGS` | Interpreter grammar, numeric syntax and formatting/style defaults. |

After the vocabulary separation below, the module needs only `re`,
`dataclasses.dataclass`, `typing.Iterable` and postponed annotations. It needs no
engine import, font module, event model, file path, renderer or processing context.
There is no `__file__` resource adjustment. The dependency direction remains
engine → interpreter; the existing font modules remain independent.

The name `resolve_event_style()` does not imply an `Event` dependency: its inputs
are a style catalog, a name and an optional fallback dictionary. Conversely,
`parse_styles()` also reads the authored Kerning setting; retain that behavior
and the distinct implicit libass Default style rather than simplifying it during
the move.

All nine definitions and all six supporting names should remain available as
engine aliases. In particular, alias the actual `DEFAULT_STATE` dictionary and
`STYLE_TAGS` map rather than making copies. Frozen result bindings do not freeze
their formatting dictionaries. Preserve all copying/borrowing behavior described
in [CONTEXT_OWNERSHIP_REVIEW.md](CONTEXT_OWNERSHIP_REVIEW.md).

## Separate vocabulary from output policy

The one dependency crossing the proposed boundary is:

```text
SAFE_SIMPLE_TAGS → TAG_NAMES → TAG_RE → tokenize_override
```

`SAFE_SIMPLE_TAGS` is the simplifier's output whitelist. Its production uses are
the current vocabulary initializer and `freeze_block()`'s permitted output tags.
The interpreter recognizes 51 names, including tags the simplifier does not emit
unchanged. Recognition does not grant permission to retain a tag.

Keep `SAFE_SIMPLE_TAGS` and the freezer's output decisions in the engine. Give the
interpreter an explicit recognized vocabulary containing exactly today's 51
names, retaining longest-name-first matching and case-insensitive recognition.
Do not pass the whitelist into a factory, import it back from the engine, or move
simplification policy into the interpreter to preserve the current initializer.
The overlapping names express different responsibilities; they need a contract
check, not a new shared configuration abstraction.

Check that every permitted simple tag is recognized, that the complete recognized
set is unchanged and that tokenization decisions match. Same-length alternatives
have distinct literal names, so their incidental set iteration order does not
select different tokens. Protect the recognition behavior rather than requiring
an identical spelling of the compiled regular expression.

This explicit vocabulary initialization is the only intended adjustment beyond
import/export wiring. Keep the seven function implementations and both frozen
records unchanged. Do not simultaneously consolidate the existing `NUM` and
`NUMBER` names or change mutable constants into different types.

## Keep outside this extraction

- `Event`, `StaticSpanSignature`, `event_evaluation()` and `replace_event()`:
  event cache ownership, source evidence and successor rules remain in the engine.
- `sample_transform_state()`, `sample_transform_states()`, interpolation and
  continuation commitment: sampling time and branch history are distinct from
  single-tag interpretation. Preserve the existing root callers and continuation
  defaults; no sampler redesign is needed.
- `font_size_transform_needs_replay()`: this decides whether a sampler can use an
  optimized path; it is not required by the interpreter.
- `parse_effect_transform()` and `parse_effect_move()`: these validate source
  evidence for effect matchers. The former contains the 50 ms endpoint bound,
  finite/forward timing requirements, acceleration checks and caller-supplied
  allowed-tag policy. Their parser-like names do not make them pure grammar.
- `get_pos()`, `set_pos()`, `POS_RE`, `NUM`, rendering, static freezing/compaction,
  paint selection, row reconstruction and source preparation: none is an outgoing
  dependency of the proposed interpreter.

Position helpers may be assessed with a later geometry boundary. This extraction
removes some low-level dependencies from the engine but does not by itself make
all row-fitting functions independent of the event/report owners.

## Consumers and test implications

The interpreter has many consumers, but they are incoming dependencies. Direct
aliases let existing engine callers keep their current signatures and pass
ordering. Do not add forwarding functions or a mechanism that redirects private
module globals through the engine to preserve old monkeypatch behavior.

Tests need to observe where calls actually resolve:

| Check | Required adaptation in the implementation release |
| --- | --- |
| `check_override_continuation.py` | Its live AST lookup currently expects `apply_override()` in the root source. Inspect the defining function/module instead, retaining the no-private-dictionary-key assertion. |
| `check_outline_parsing_reuse.py` | Patch the tokenizer binding used by the complete evaluator as well as root consumers when proving no reparsing or counting all parsing. Keep its frozen v171/v172 audits unchanged. |
| `check_inline_continuation.py`, `check_freeze_continuation.py`, `check_effect_continuation.py` | Trace the real canonical evaluator across both module boundaries where needed, retaining ordered calls, clean buffers, successor history and borrowed-input assertions. |
| Context, relative-font-size and undefined-style checks | Root aliases should preserve their behavioral use directly; keep their existing assertions. |

A test may need to patch both the defining module and a borrowed root binding.
When a historical engine uses one module for both, avoid double-wrapping the same
binding and accidentally counting calls twice. Adapt this test instrumentation
at the test boundary; do not create a production compatibility layer for it.
Inspect the reusable scenario prefixes too, since current tests execute selected
parts of older harnesses. Historical source audits are evidence for their own
releases, not requirements to keep the current implementation in one file.

Add or extend focused module-boundary coverage for direct aliases, unchanged
frozen records/shared constant identity, standalone import without optional
backends, supplied-token reuse, and actual installed-engine execution without the
checkout on the import path. Exercise the complete evaluator under the real
interpreter rather than substituting an old implementation.

## Evidence collected for this assessment

A disposable module was assembled from the nine unchanged definitions and their
supporting constants, replacing only the vocabulary initializer with an explicit
recognized-name set. Its isolated import/evaluation succeeded from an unrelated
directory without importing the engine, Pillow, fontTools or HarfBuzz.

Against the unchanged v215 engine it matched:

- **2,321 token streams**, including recognized names, malformed values, nested
  payloads and deterministic combinations.
- **4,642 complete evaluations**, with ordinary parsing and borrowed pre-parsed
  tokens, checking fresh output buffers and unchanged style catalogs.
- **1,664 single-tag cases**, varying reset history, alignment latches, placement
  modes and tags; ordered state fields, successor values and identity agreed.
- **Three style catalogs**, including implicit defaults, authored colors/alpha,
  legacy alignment and Kerning.

Eight fresh focused scripts passed on the unchanged engine:
`check_override_continuation.py` (632,304 checks),
`check_relative_font_size.py` (282), `check_undefined_styles.py` (156),
`check_context_contracts.py` (2,500), `check_outline_parsing_reuse.py` (219),
`check_parser_effect_consumers.py` (9,894), `check_inline_continuation.py` (51,222)
and `check_freeze_continuation.py` (634,286).

Private evidence is in `validation/override-extraction-assessment/`:
`assessment.json`, `baseline-checks.json`, the disposable source/probe and logs.
The complete production source manifest and covered test inputs stayed unchanged.
No production file, batch wrapper, installer, updater or engine version changed.

The full 91-script suite and thirteen-track corpus were last freshly validated
for v215; they were not rerun for this documentation-only assessment. Their
recorded runtime manifest agrees with the assessed runtime. The disposable
prototype is evidence that the boundary closes, not proof that an eventual
integrated extraction passes those checks.

## Recommended implementation and acceptance

One release can perform the move, vocabulary separation and necessary test
adaptations together. A separate delivery preparation is unnecessary: v214's
inventory already handles another private Python module. The older-updater
migration documented in [MODULE_DELIVERY.md](MODULE_DELIVERY.md) still applies.

1. Capture the exact pre-extraction runtime and baseline evidence. Move the core
   and retain aliases without changing algorithms, dataclasses or caller flow.
2. Establish the explicit vocabulary and test its relationship to the unchanged
   output whitelist. Adapt source lookup/call tracing without weakening tests.
3. Compare moved definitions and the remaining engine against the baseline,
   allowing only vocabulary ownership and import/version wiring. Verify the
   resulting module imports independently and has no reverse dependency.
4. Run focused parser/continuation/font-size checks, then the full Windows-font-
   backend suite and thirteen-track exact-font corpus comparison. Require
   unchanged output and complete meaningful statistics, source/catalog/cache
   immutability, token reuse and continuation identity where promised.
5. Verify installed execution, v214-updater delivery, rollback, uninstall and
   complete runtime manifests. Native Windows CMD/NTFS checks still require a
   Windows host; Linux font-backend/render checks do not replace them.

After the implementation, briefly evaluate whether ownership and instrumentation
remain clean. Broaden the review only if the extraction requires reverse imports,
new callback/context plumbing, production monkeypatch shims or changed sampling/
reconstruction policy.

Assessment evaluation: the candidate is suitable. The grammar/whitelist coupling
and test binding assumptions are concrete extraction tasks that fit in that same
release; neither requires a preceding redesign. No new runtime bug or separate
follow-up review was established. The broader API and pass-local index reviews
remain deferred.
