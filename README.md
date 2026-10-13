# MKV Subtitle Tools

Scripts for simplifying ASS/SSA subtitles and managing subtitle tracks and fonts
in MKV files. Simplification reduces karaoke, animated lettering and other
complex effects for TVs and embedded players, preserving readable text and
representative colors where possible.

## End-user scripts

All production scripts are at the repository root. The subtitle flag, removal,
and font tools are standalone Python files: copy the desired `.py` file into
your MKV folder and run it with Python. They default to scanning beside the
script; command-line options can select other folders.

For simplification on Windows, copy all three `simplify_ass` files into your
MKV folder and double-click `simplify_ass.bat`. Its launcher calls
`simplify_ass.ps1`, which uses `simplify_ass.py`.

| Entry point | Task | Companion scripts |
| --- | --- | --- |
| `simplify_ass.bat` | Simplify ASS/SSA tracks; keep originals or replace them | `simplify_ass.ps1`, `simplify_ass.py` |
| `subtitle_flags.py` | Clear or set default and forced subtitle flags in place | — |
| `remove_subtitles.py` | Remove selected tracks or added simplified tracks | — |
| `sync_fonts.py` | Inspect fonts, remove unused attachments, optionally add missing fonts | — |

Keeping original subtitle tracks preserves the option to remove the added
simplified versions later. Replaced original tracks cannot be recovered by these
scripts.

## Requirements

Install MKVToolNix and Python 3.10 or newer and make them accessible from the
command line. For font measurement and reconstruction support:

```console
python -m pip install Pillow fonttools uharfbuzz
```

The three standalone tools run with Python on Windows, Linux, and macOS.
The `simplify_ass.bat` launcher uses Windows PowerShell for the batch MKV
workflow. Invoke `simplify_ass.py` directly to convert individual subtitle files.

```console
python simplify_ass.py input.ass --fonts-dir fonts
python simplify_ass.py input.ass --font-mkv episode.mkv
python sync_fonts.py /path/to/media --preview
python sync_fonts.py -i /path/to/media -f /path/to/fonts -o /path/to/cleaned
python subtitle_flags.py /path/to/media
python remove_subtitles.py /path/to/media --recursive
```

The converter writes `input.simple.ass` by default. Exact fonts help prove line
geometry; uncertain fragments are retained. Use `--help` for all options.
Current converter version: **2026.10.13.189**.

### Subtitle default and forced flags

`subtitle_flags.py` manages default and forced subtitle flags through a Python
menu, using only the standard library and MKVToolNix. Run it on Windows, Linux,
or macOS. Without a folder argument it scans beside the script; with an argument
it scans that folder. Subfolders are not scanned.

It scans all MKVs first, then asks which flags to clear and whether to set default
and forced flags together, separately, or neither. When setting flags, select
from a combined numbered list using commas or spaces. Entries are grouped by
track name, language (IETF tag when available), and subtitle format. Every matching
track is selected, including duplicate tracks within one file. Blank selections
set no flags; `q` cancels any menu. A final summary asks before editing.

Clearing happens before setting. Flags not cleared or selected are preserved,
and files without a selected track still receive requested clearing. Multiple
default or forced tracks are allowed. `mkvpropedit` writes flags **in place**;
there is no remux or output folder. Subtitle flags are verified after each edit.
Unreadable files are reported and skipped; editing failures are reported while
remaining files continue, with a nonzero exit status if any file failed. An
editing or verification failure does not roll back an in-place change.

### Remove subtitle tracks

`remove_subtitles.py` is a standalone Python 3.10+ script requiring only MKVToolNix
(`mkvmerge` on PATH). It combines manual subtitle removal and automatic removal
of added simplified tracks without importing any other project scripts.

```console
python remove_subtitles.py
python remove_subtitles.py /path/to/media --recursive
python remove_subtitles.py /path/to/media --output-dir /path/to/cleaned
```

With no folder argument it scans beside the script. Use `--recursive` to scan
subfolders. Output folders are excluded from scanning; the default destination
is the input folder's `output/`, preserving relative subfolder paths.

When removable simplified pairs exist, choose manual selection or automatic
simplified removal. Otherwise, the script goes straight to manual selection.
The combined manual list groups tracks by name, language, and subtitle format,
using the same comma/space multiselection as `subtitle_flags.py`. All matching
tracks are selected, including duplicate entries within one MKV.

Automatic detection matches `Name (Simplified)` to `Name` in the same MKV and
language, with case-insensitive names. A track named `Simplified` matches an
unnamed original of the same language. Format may differ between an original
and its simplified copy. Simplified-looking tracks without a matching original
are retained. This uses metadata only; embedded subtitle comments are not read.

Before confirmation, the preview lists subtitle track IDs and names marked
REMOVE or KEEP for each affected file, including matched original IDs in
automatic mode. Enter `m` to switch to manual selection or revise the selection,
then review the new preview. Blank manual input or `q` cancels; confirmation
defaults to no. No output files or directories are created before confirmation.

Original MKVs remain untouched. Files without matching tracks and existing
outputs are skipped. Remuxing retains other tracks, their default/forced flags,
attachments, and chapters. Each output is written to a temporary file and its
retained track identities, names, languages, formats, flags, attachment metadata,
and chapter counts are checked before it receives the final filename. Failed
partial outputs are discarded; remaining files continue. Scan/remux failures
produce a nonzero exit status. Metadata checks do not prove payload identity or
that a named track was actually generated by the simplifier.

### Font synchronization

`sync_fonts.py` defaults to the folder containing the script for both MKVs and
loose font files, and writes to that folder's `output/`. On Windows, opening the
`.py` file directly requires a Python file association. A no-argument launch in
a Windows console pauses at the end so results or missing-dependency messages
remain visible.

Use `-i` / `--input-dir` to choose the folder containing MKVs and loose fonts,
`-f` / `--fonts-dir` to select a separate folder of loose fonts, and `-o` /
`--output-dir` to choose the output folder. Without `-f`, fonts are read from
the input folder. Font scanning is not recursive. The default output follows
the chosen input folder. Existing positional input syntax, `--preview`, and
`--log` remain supported; logging is off by default. Relative command-line
paths are resolved from the working directory. Invocations with arguments do
not pause on exit. The output folder must differ from the input folder.

## Development

- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): setup, regression commands and planned reviews.
- [docs/](docs/): technical notes and historical review documents.
- [tests/](tests/): Python regression checks and helpers.
- [tests/windows/](tests/windows/): batch-testing wrappers and PowerShell reporting checks.
- [validation/](validation/): suite runners, corpus comparison and render diagnostics.

Fonts, subtitle fixtures and generated reports are local development assets.
See the development guide for restoring them and running tests.
