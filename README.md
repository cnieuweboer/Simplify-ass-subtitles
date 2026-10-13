# MKV Subtitle Tools

Simplify ASS/SSA subtitles and manage subtitle tracks and fonts in MKV files.

| Script | Task |
| --- | --- |
| `simplify_ass.bat` | Simplify embedded ASS/SSA subtitles |
| `subtitle_flags.py` | Set or clear default and forced flags **in place** |
| `remove_subtitles.py` | Remove selected or added simplified subtitles |
| `sync_fonts.py` | Remove unused fonts and optionally add missing fonts |

## Setup

Install Python 3.10+ and MKVToolNix, with its tools on PATH.

```console
python -m pip install Pillow fonttools uharfbuzz
```

`sync_fonts.py` needs fonttools; the simplifier also needs Pillow and uharfbuzz.
The flag and removal tools use Python's standard library.

The three standalone Python tools work on Windows, Linux, and macOS.
Use `python3` instead of `python` where needed. Double-clicking a Python file
requires a Python file association.

Without arguments, they scan beside the script. Removal and font sync write to
`output/` under the input folder, preserving originals and skipping existing
outputs. Flag changes edit the originals.

## Simplify subtitles

On Windows, double-click `simplify_ass.bat`; keep `simplify_ass.ps1` and
`simplify_ass.py` beside it. Keep-original mode allows removing added simplified
tracks later; replaced originals cannot be recovered by these tools.

For individual subtitle files:

```console
python simplify_ass.py input.ass --fonts-dir fonts
python simplify_ass.py input.ass --font-mkv episode.mkv
```

Default output: `input.simple.ass`. Current converter version: **2026.10.13.189**.

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
jp          Remove all Japanese subtitles (ja/jpn also work)
k eng, ger  Keep only English and German subtitles
k eng, 3    Keep all English subtitles and group 3
```

Language codes select all names and formats; `eng` includes regional tags such
as `en-US`. Blank input cancels. Files with none of the selected keep tracks
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
