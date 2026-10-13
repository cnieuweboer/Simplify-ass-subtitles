# MKV Subtitle Tools

Simplify ASS/SSA subtitles and manage subtitle tracks and fonts in MKV files.

| Script | Task |
| --- | --- |
| `simplify_subtitles.py` | Simplify embedded ASS/SSA subtitles |
| `subtitle_flags.py` | Set or clear default and forced flags **in place** |
| `remove_subtitles.py` | Remove selected or added simplified subtitles |
| `sync_fonts.py` | Remove unused fonts and optionally add missing fonts |

For folder drag-and-drop targets, see [dnd helper](dnd%20helper/README.md).

## Setup

Install Python 3.10+ and MKVToolNix, with its tools on PATH.

```console
python -m pip install Pillow fonttools uharfbuzz
```

`sync_fonts.py` needs fonttools; the simplifier also needs Pillow and uharfbuzz.
The flag and removal tools use Python's standard library.

The end-user Python tools work on Windows, Linux, and macOS.
Use `python3` instead of `python` where needed. Double-clicking a Python file
requires a Python file association.

Without arguments, they scan beside the script. Simplification, removal, and
font sync write to `output/` under the input folder, preserving originals and
skipping existing outputs. Flag changes edit the originals.

## Simplify subtitles

Keep `simplify_ass.py` beside `simplify_subtitles.py`.

```console
python simplify_subtitles.py
python simplify_subtitles.py -i media -o cleaned -f fonts --recursive
python simplify_subtitles.py -i media --replace-originals --process-all-tracks
python simplify_subtitles.py -i media --scroll-concurrency-limit 32
```

The menu offers adding simplified tracks or replacing originals, with either
all ASS/SSA tracks or the default thresholds: **>50,000 bytes and >10% fewer
events**. Unchanged MKVs are copied; marked simplified tracks are skipped.
Scrolling-text dropping is disabled by default (`0`); enable it explicitly
with `--scroll-concurrency-limit`. `-f` adds fonts alongside embedded fonts.

Use `--yes` to run without prompts (default: keep originals, filtered tracks)
and `--report run.json` for a JSON report.

For individual subtitle files:

```console
python simplify_ass.py input.ass --fonts-dir fonts
python simplify_ass.py input.ass --font-mkv episode.mkv
```

Default output: `input.simple.ass`. Current converter version: **2026.10.14.190**.

## Subtitle flags

```console
python subtitle_flags.py
python subtitle_flags.py media
```

## Remove subtitles

```console
python remove_subtitles.py
python remove_subtitles.py -i media -o cleaned --recursive
```

At manual selection:

```text
1,3         Remove groups 1 and 3
ja       Remove subtitles listed as [ja]
k en, de Keep subtitles listed as [en] or [de]
k en, 3  Keep [en] subtitles and group 3
```

Use the exact language codes shown in the list; `[en]` and `[en-US]` are
separate selections. Codes select all matching names and formats. Blank input cancels. Files with none of the selected keep tracks
have all subtitles removed; review the preview.

Automatic removal requires a matching original of the same language in each
MKV. At the removal preview, enter `m` to switch to manual selection.

## Sync fonts

```console
python sync_fonts.py
python sync_fonts.py -i media -f fonts -o cleaned
python sync_fonts.py -i media --preview
python sync_fonts.py -i media --log
```

Without `-f`, loose fonts are read from the input folder. Font scanning is not
recursive; logs are off by default.

## Development

- [Development guide](docs/DEVELOPMENT.md)
- [Technical documentation](docs/)
- [Tests](tests/) and [validation tools](validation/)
