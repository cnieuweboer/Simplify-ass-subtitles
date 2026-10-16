# MKV Subtitle Tools

Simplify ASS/SSA subtitles and manage subtitle tracks and fonts in MKV files.

## Windows quick start

Install Python 3.10+ and MKVToolNix, with MKVToolNix on PATH. Download and extract
the complete repository ZIP, then run:

```cmd
installer\windows\install.cmd
```

The default location is `C:\Tools`; append `"D:\My Tools"` to choose another.
The installer offers to install missing Python packages and add `<installation folder>/bin` to your
user PATH. Restart your terminal afterward.

Run `subtitle_tools` (`subtitle_tools.cmd`) from a folder containing MKV files. Or with the -i argument to point to a folder or individual MKV file 

```cmd
subtitle_tools
subtitle_tools -i "D:\Media" -o "D:\Cleaned" -r
```

Menu: **1** simplify, **2** add/remove tracks, **3** rename/edit flags,
**4** fonts, **5** update.

- `-i` / `--input`: folder or one MKV; defaults to the current folder.
- `-o` / `--output`: output folder; defaults to `output/` beside each MKV.
- `-r` / `--recursive`: include subfolders; off by default.
- `-f` / `--fonts-dir`: loose-font folder for simplification or font sync.
- `--help`: show options for the tool selected in the menu.

Property changes edit originals in place and do not require or accept `-o`.

| Script | Task |
| --- | --- |
| `simplify_subtitles.py` | Simplify embedded ASS/SSA subtitles |
| `subtitle_properties.py` | Rename tracks or set/clear flags **in place** |
| `subtitle_tracks.py` | Add or remove subtitle tracks |
| `sync_fonts.py` | Remove unused fonts and optionally add missing fonts |

For file/folder drag-and-drop targets, see [dnd helper](dnd%20helper/README.md).

## Setup

Install Python 3.10+ and MKVToolNix, with its tools on PATH.

```console
python -m pip install Pillow fonttools uharfbuzz
```

`sync_fonts.py` needs fonttools; the simplifier also needs Pillow and uharfbuzz.
The properties and track tools use Python's standard library.

The end-user Python tools work on Windows, Linux, and macOS.
Use `python3` instead of `python` where needed. Double-clicking a Python file
requires a Python file association.

Without arguments, they scan beside the script without visiting subfolders.
Use `-r` / `--recursive` to include subfolders; `output/` folders are excluded.
Simplification, track additions/removals, and font sync write to `output/` beside each source MKV,
preserving originals and skipping existing outputs. Property changes edit the originals.
All four tools accept a folder or one MKV via `-i` / `--input` or positional input.
For one MKV, output defaults to its parent folder's `output/`.

```console
python simplify_subtitles.py -i media/episode.mkv
python simplify_subtitles.py --input media --recursive --output cleaned
```

With explicit output, subfolder paths are relative to the input: `media/B/C/Y.mkv`
becomes `cleaned/B/C/Y.mkv`. Without `--output`, it becomes `media/B/C/output/Y.mkv`.

## Simplify subtitles

Keep `simplify_ass.py`, its `_simplify_ass/` implementation directory, and
`simplify_subtitles.py` together. Download or install the complete tool set;
copying only the engine script is no longer sufficient.

```console
python simplify_subtitles.py
python simplify_subtitles.py -i media -o cleaned -f fonts --recursive
python simplify_subtitles.py -i media --replace-originals --process-all-tracks
python simplify_subtitles.py -i media --scroll-concurrency-limit 32
python simplify_subtitles.py -i media --workers 4
```

The menu offers adding simplified tracks or replacing originals, with either
all ASS/SSA tracks or **>50,000 bytes and >10% fewer events**. Filtered add mode
keeps groups consistent across the batch: if any member qualifies, add simplified
copies wherever that name/language/format group exists. Filtered replace mode
uses the thresholds per track. Filename/group mismatches warn before confirmation.
Unchanged MKVs are copied; marked simplified tracks are skipped.
Scrolling-text dropping is disabled by default (`0`); enable it explicitly
with `--scroll-concurrency-limit`. `-f` adds fonts alongside embedded fonts.
`--temp-dir scratch` can choose temporary storage; video is never cached there.

Press **1** to use all defaults, then **y** to start. Choose **2** to adjust
original-track handling, which ASS/SSA tracks to process, scrolling, or minimum
caption color hold. Command-line values stay fixed; `--yes` skips the menus.

`--color-phase-change-interval` is CLI-only and defaults to `0` (unlimited).

Use `--yes` to run without prompts (default: keep originals, filtered tracks)
and `--report run.json` for a JSON report.

For individual subtitle files:

```console
python simplify_ass.py input.ass --fonts-dir fonts
python simplify_ass.py input.ass --font-mkv episode.mkv
```

Default output: `input.simple.ass`. Current converter version: **2026.10.14.190**.

## Subtitle properties

```console
python subtitle_properties.py
python subtitle_properties.py -i media --recursive
python subtitle_properties.py -i media/episode.mkv
```

Choose **1** for default/forced flags or **2** to rename tracks. Select groups by
number, then accept or replace each suggested name; `-` clears a name. Review the
changes before confirming. Both actions edit originals in place.

## Add or remove subtitle tracks

```console
python subtitle_tracks.py
python subtitle_tracks.py -i media -o cleaned --recursive
python subtitle_tracks.py -i media/episode.mkv
```

Choose **1** to remove or **2** to add. Place external subtitles beside their MKVs:

```text
Episode 01.mkv
Episode 01.en.1.srt
Episode 01.en.2.ass
Episode 02.mkv
Episode 02.en.1.srt
Episode 02.en.2.ass
```

Complete groups match by basename first, then by natural filename order within each
folder. The preview shows every pairing; enter a group number to edit its language/name,
`x NUMBER` to exclude/include it, or `y` to remux. New tracks have default/forced off.
Single-file input matches its basename only. Incomplete or ambiguous groups are skipped.

At manual removal selection:

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

Without `-f`, loose fonts are read beside each source MKV. Font folders themselves
are not scanned recursively; logs are off by default.

## Development

- [Development guide](docs/DEVELOPMENT.md)
- [Technical documentation](docs/)
- [Tests](tests/) and [validation tools](validation/)
