# Rotating entrance fade tolerance — v195

Rotating entrance glyphs may specify a fade-in that finishes up to 50 ms beyond
their source event's duration. Flying exit glyphs already allowed this bounded
source-parameter overrun; entrance classification now uses the same allowance.
This accommodates approximately one frame of authoring or timestamp rounding.
It is a fixed 50 ms allowance, not a frame-rate-dependent calculation.

The classifier still uses the actual event boundary. It does not extend events,
shift a held word, bridge blank intervals, or relax readable-core timing. The
existing boundary matching allowance and fade-parameter allowance each validate
their own condition; neither adds time to the other.

Removal still requires a complete, ordered glyph family owned by one static
held word, with matching literal, exact font geometry, anchor and compatible
paint. Entrances must settle from rotation into an upright state with supported
formatting. Missing or repeated glyphs, competing parents, incorrect anchors or
literals, unavailable exact geometry, and unsupported paint animation remain
unproven and are retained. There are no subtitle-, show-, font- or color-specific
recognition rules.

## Verification

`tests/check_rotating_entrance_fades.py` checks entrance and exit families at
0, 10, 40, 50, 51 and 60 ms overruns. It checks ownership failures, borrowed input
immutability, preserved held-word timing, unsupported transformations, normal
pipeline conversion and repeat stability. Its 197 assertions use the supplied
exact Volkhov font for synthetic geometry; that font is not a runtime condition.

`validation/run_rotating_entrance_corpus.py` generates fresh conversions and
compares output bytes and statistics against hash-verified v194 baselines for
nine established corpus sources and the full supplied Goblin Slayer track.
Reports and media remain ignored local assets. The change addresses a supported
synthetic class; it does not imply that the existing corpus contains this niche.

Fresh v195 verification: all ten corpus outputs and statistics are byte-identical
to v194, with no missing fonts. The production MKV smoke test and all 12 Python
wrapper checks also pass.
The full 72-script Windows font-backend suite passes, including native libass
render comparisons. Runtime and harness hashes match the tested files.
