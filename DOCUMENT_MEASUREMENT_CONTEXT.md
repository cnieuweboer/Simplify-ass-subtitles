# Document measurement context ownership

Migration completed in v162; contracts reviewed for v168.

## Fields and owners

| Value | Owner and lifetime | Production storage |
| --- | --- | --- |
| Explicit viewport | Parsed document; immutable throughout event processing | `DocumentMeasurementContext.canvas` |
| Active script wrapping | Measurement phase; absent during text processing | `DocumentMeasurementContext.script_wrap_mode` |
| Authored WrapStyle | Document metadata, retained before activation | `SubtitleDocument.wrap_mode` |
| Explicit wrapping override | Resolved event formatting; retained across style resets | `state['q']` |
| Unit scaling | Established geometry-unit convention, including fallback resolution | `Event.unit` |

A document and its events share the same frozen context. It contains only
immutable values and can be shared by replacements without copying or coupling
mutable formatting dictionaries. Standalone events and caption rendering default
to an empty context; no viewport or script wrapping is invented.

## Production and phase boundaries

`parse_styles()` resolves style formatting and kerning. It no longer injects
measurement metadata into styles. `parse_subtitle_document()` reads explicit
PlayRes dimensions and binds the resulting context to all events after parsing.
This also handles Script Info occurring after the event section.

Canvas requires both finite, positive authored dimensions. Invalid values do
not overwrite earlier valid values. The last valid occurrence of each dimension
wins, only inside Script Info. Missing one or both dimensions yields `None`.
The established unit-scaling fallback and duplicate-resolution behaviour are
unchanged and deliberately independent of this viewport proof.

Parsed documents and `_prepare_text_document()` retain inactive script wrapping.
`_resolve_document_state()` creates a context successor with the document's
WrapStyle, plus independent event/state/style objects. Events within that successor share
its read-only style catalog and style defaults; their resolved state buffers are
separate from those defaults. Document lines and field lists remain borrowed
read-only. It does not mutate the
input document, events or context. `_normalize_text_result()` retains the
established reparse boundary, reconstructing document context alongside
serialized formatting instead of carrying temporary proof data across it.

## Consumers and precedence

`render_simplified_caption()` takes context explicitly. Production callers pass
the context of the event associated with their selected formatting. Its
visible-shadow transfer uses that viewport without mixing metadata into paint.

`match_authored_lyric_rows()` and `match_staggered_full_line_copies()` retain their
existing missing-canvas and collision guards. `_prove_sliced_text_strip_phases()`
requires explicit viewport width to prove full-width strips.
`is_fullscreen_background()` requires explicit viewport coverage.

`caption_bounds()` uses resolved `q` when present; otherwise it uses the active
context wrap mode. Inactive wrapping has the established mode-zero soft-break
behaviour. Modes other than two turn `\\n` into a space; mode two preserves a
soft line break. `\\N` remains a hard break.

`static_object_key()` keeps its literal run formatting signatures, parser
continuation distinctions and payload. Document context now forms a separate
component before the final runs tuple. This preserves matching distinctions
between absent wrapping and explicit mode zero, and between different canvases,
without placing context back into formatting. Existing final-component consumers
continue to read the runs.

## Replacement policy

Ordinary `replace_event()` and dataclass replacements preserve the immutable
context, including text/style/state edits and timing/source-ID changes. Resolving
new formatting cannot erase document context or replace it with style defaults.
A caller crossing a document or measurement-phase boundary must supply the new
context explicitly. Parsing and measurement preparation are the production
places that establish those boundaries.

Historical EventEvidence preservation/invalidation remains unchanged. Parser
continuation now has its own immutable record, `OverrideContinuation`, and never
lives in formatting dictionaries. See `PARSER_CONTINUATION.md`.

## Final review

The context contains only an optional tuple of finite positive dimensions and an
optional integer wrap mode. Native style values are immutable scalar ASS fields,
so copying the catalog and each style at the measurement boundary is sufficient.
Events do not own or mutate borrowed style defaults. Formatting probes copy their
own buffers; renderers and measurement readers borrow them read-only.

The complete final regression runner is `validation/run_review_checks.py`.
`check_context_contracts.py` exercises the phase boundaries and parsing/measurement
readers with read-only style maps and caches. The seven full subtitle comparisons
retain both output bytes and statistics, including the pre-migration v156 baseline.
See `CONTEXT_OWNERSHIP_REVIEW.md` for the completed review and remaining candidates.
