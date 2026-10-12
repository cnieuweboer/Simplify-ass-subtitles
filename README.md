# MKV Subtitle Simplification Tools — version 177

Release **2026.10.12.177** reconstructs complete opening letter lifecycles into static lines. Attack on Titan S02E01 retains 21 romanized opening lines alongside its 21 translated lines; the v176 ending cleanup is preserved. GLYPH_LIFECYCLES.md describes ownership, geometry, paint selection and limits. Windows is the routine regression target.

The production workflow is `simplify_ass.bat` → `simplify_ass.ps1` →
`simplify_ass.py`. Place the launcher and scripts beside your MKV files and run
`simplify_ass.bat`. The wrapper offers keeping original subtitle tracks or
replacing them. Preserve originals when you need reversibility. MKVToolNix and
Python must be accessible from the command line.

Routine regressions use Windows-style Pillow BASIC with real uharfbuzz. RAQM is
an explicit occasional check. See [DEVELOPMENT.md](DEVELOPMENT.md) for Codex/cloud
setup, test assets, batch-test wrappers and the deferred API/index reviews.

## Running the converter

Python 3.10 or newer is required. Processing without optional font measurements
uses the standard library. Install font measurement support with:

```console
python -m pip install Pillow fonttools uharfbuzz
python simplify_ass.py input.ass --fonts-dir fonts
```

RAQM provides shaping when available; uharfbuzz supplies a fallback on hosts
without RAQM. Exact font measurements enable spacing, outline decoding and
geometry proofs; uncertain fragments retain their positions. Requested variable
font variants follow the subtitle. No substitute font or word dictionary is used.

Use `--font-mkv episode.mkv` to read font attachments through MKVToolNix, or repeat
`--fonts-dir` for extracted font folders. Output defaults to `input.simple.ass`.
`--stats-json report.json` adds per-input statistics and removed-text warnings.
`--scroll-concurrency-limit 32` controls the last-resort scrolling-block policy;
`0` disables that text-dropping fallback. `--help` lists all options. The BAT
launchers use standard simplification; deprecated legacy mode remains available
through the existing compatibility parameters.

## Current structure and contracts

The public `simplify_ass()` entry point reads a document, runs named text stages,
normalizes the result in memory, then reconstructs caption supports from the
original drawing source. The render/reparse boundary intentionally rebuilds
indices and formatting and clears transient text proof. Shared I/O remains in
one document reader/writer.

| Documentation | Current subject |
| --- | --- |
| FINAL_STRUCTURAL_REVIEW.md | Closure of the five structural goals in v167; final visibility result interfaces. |
| VISIBILITY_OWNERSHIP.md | Borrowed maps, private overlays, returned assignments and pipeline application. |
| CONTEXT_OWNERSHIP_REVIEW.md | Style/event/cache ownership, replacement rules and deferred API/index reviews. |
| DOCUMENT_MEASUREMENT_CONTEXT.md | Canvas proof, wrapping activation and event context propagation. |
| PARSER_CONTINUATION.md | Ordered reset/alignment history, sampling branches, selection and matching. |
| AUTHORED_LYRIC_OWNERSHIP.md | Source-cache successors, alias application and row additions. |
| FONT_METRICS.md | Reusable font operations and backend/measurement contracts. |
| WORD_ECHOES.md | Source-owned word echoes and v176 validation. |
| COMPLETE_LINE_JITTER.md | Complete literal frame families, paint stacks and v175 validation. |
| SHADOW_LETTERING.md | Final shadow lettering normalization and v174 validation. |
| PORTABLE_CAPTION_INK.md | Direct HarfBuzz ink and the restored Skill Bank backdrop in v173. |
| REGRESSION_BACKENDS.md | Default Windows testing and optional RAQM coverage. |
| OUTLINE_MATCHER.md | Exact-font decoding, bounded search and profile-cache lifetime. |
| ROW_GEOMETRY.md | Row fitting, explicit diagnostics and batch/failure reporting. |
| STATIC_OUTLINE_COLOR.md | Static outline and tolerated hex suffix introduced in v169. |
| WRAPPING_HANDOFF.md | Explicit wrapping retention and existing source-fade handoffs in v171. |
| OUTLINE_KARAOKE.md | Complete outline palettes and the shared ordered karaoke completion proof. |
| OUTLINE_PARSING_REUSE.md | Pass-local source tokens, shared evaluation/validation, equivalence and timings in v172. |
| FONTSPACING_RELEASE_PLAN.md | Historical plan completed in v164–v166; retained prompts. |

The original structural plan is complete. Simultaneous catalog/text-style
replacement and backed-pulse index payloads remain deferred to their separate
API and pass-local index reviews.

## Verification

Run `python validation/run_review_checks.py` from the repository root after
restoring the local `test-data` and `fonts` folders. The current inventory has
61 scripts; the default Windows font backend uses Pillow BASIC and real
uharfbuzz. This checks font behavior on Linux but does not replace native Windows
PowerShell/batch testing. See [REGRESSION_BACKENDS.md](REGRESSION_BACKENDS.md).

The supplied v177 snapshot includes historical evidence for 84 focused glyph
lifecycle checks, nine full-corpus comparisons and 12 render samples. These are
prior results; current validation must execute the checks with the current
runtime and exact input files. The technical notes describe the associated
ownership, geometry, paint and fallback contracts.

## Other MKV utilities

The existing `sync_fonts.py` / `.bat` tools inspect font attachments and can
remove unused fonts or add supplied fonts. Start with `sync_fonts.py --preview`.
The repository also retains scripts for removing subtitles and setting or
clearing default/forced flags. `remove_simplified_subtitles.bat` can remove added
simplified tracks only when the originals were retained; it cannot recover
original tracks that were replaced.
