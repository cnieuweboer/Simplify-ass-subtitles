# Technical documentation

Start with [DEVELOPMENT.md](DEVELOPMENT.md) for setup, tests and future work.


The public `simplify_ass()` entry point reads a document, runs named text stages,
normalizes the result in memory, then reconstructs caption supports from the
original drawing source. The render/reparse boundary intentionally rebuilds
indices and formatting and clears transient text proof. Shared I/O remains in
one document reader/writer.

| Documentation | Current subject |
| --- | --- |
| [FINAL_STRUCTURAL_REVIEW.md](FINAL_STRUCTURAL_REVIEW.md) | Closure of the five structural goals in v167; final visibility result interfaces. |
| [VISIBILITY_OWNERSHIP.md](VISIBILITY_OWNERSHIP.md) | Borrowed maps, private overlays, returned assignments and pipeline application. |
| [CONTEXT_OWNERSHIP_REVIEW.md](CONTEXT_OWNERSHIP_REVIEW.md) | Style/event/cache ownership, replacement rules and deferred API/index reviews. |
| [DOCUMENT_MEASUREMENT_CONTEXT.md](DOCUMENT_MEASUREMENT_CONTEXT.md) | Canvas proof, wrapping activation and event context propagation. |
| [PARSER_CONTINUATION.md](PARSER_CONTINUATION.md) | Ordered reset/alignment history, sampling branches, selection and matching. |
| [AUTHORED_LYRIC_OWNERSHIP.md](AUTHORED_LYRIC_OWNERSHIP.md) | Source-cache successors, alias application and row additions. |
| [FONT_METRICS.md](FONT_METRICS.md) | Reusable font operations and backend/measurement contracts. |
| [WORD_ECHOES.md](WORD_ECHOES.md) | Source-owned word echoes and v176 validation. |
| [COMPLETE_LINE_JITTER.md](COMPLETE_LINE_JITTER.md) | Complete literal frame families, paint stacks and v175 validation. |
| [SHADOW_LETTERING.md](SHADOW_LETTERING.md) | Final shadow lettering normalization and v174 validation. |
| [PORTABLE_CAPTION_INK.md](PORTABLE_CAPTION_INK.md) | Direct HarfBuzz ink and the restored Skill Bank backdrop in v173. |
| [REGRESSION_BACKENDS.md](REGRESSION_BACKENDS.md) | Default Windows testing and optional RAQM coverage. |
| [OUTLINE_MATCHER.md](OUTLINE_MATCHER.md) | Exact-font decoding, bounded search and profile-cache lifetime. |
| [ROW_GEOMETRY.md](ROW_GEOMETRY.md) | Row fitting, explicit diagnostics and batch/failure reporting. |
| [STATIC_OUTLINE_COLOR.md](STATIC_OUTLINE_COLOR.md) | Static outline and tolerated hex suffix introduced in v169. |
| [WRAPPING_HANDOFF.md](WRAPPING_HANDOFF.md) | Explicit wrapping retention and existing source-fade handoffs in v171. |
| [OUTLINE_KARAOKE.md](OUTLINE_KARAOKE.md) | Complete outline palettes and the shared ordered karaoke completion proof. |
| [OUTLINE_PARSING_REUSE.md](OUTLINE_PARSING_REUSE.md) | Pass-local source tokens, shared evaluation/validation, equivalence and timings in v172. |
| [FONTSPACING_RELEASE_PLAN.md](FONTSPACING_RELEASE_PLAN.md) | Historical plan completed in v164–v166; retained prompts. |

The original structural plan is complete. Simultaneous catalog/text-style
replacement and backed-pulse index payloads remain deferred to their separate
API and pass-local index reviews.


[COLOR_NORMALIZATION.md](COLOR_NORMALIZATION.md) describes the guarded v178 near-color pass.
