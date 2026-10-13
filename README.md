# MKV Subtitle Tools

Scripts for simplifying ASS/SSA subtitles and managing subtitle tracks and fonts
in MKV files. Simplification reduces karaoke, animated lettering and other
complex effects for TVs and embedded players, preserving readable text and
representative colors where possible.

## End-user scripts

All production scripts are together at the repository root. Copy the desired
launcher and its companion scripts into a folder containing your MKVs, then
double-click the `.bat` file.

| Launcher | Task | Companion scripts |
| --- | --- | --- |
| `simplify_ass.bat` | Simplify ASS/SSA tracks; keep originals or replace them | `simplify_ass.ps1`, `simplify_ass.py` |
| `sync_fonts.bat` | Inspect fonts, remove unused attachments, optionally add missing fonts | `sync_fonts.py` |
| `remove_simplified_subtitles.bat` | Remove added simplified tracks | `remove_simplified_subtitles.ps1` |
| `remove_subtitles.bat` | Remove selected subtitle tracks | — |
| `set_default_subtitles.bat` | Set default subtitle flags | — |
| `no_default_subtitles.bat` | Clear default subtitle flags | — |
| `set_forced_subtitles.bat` | Set forced subtitle flags | — |
| `no_forced_subtitles.bat` | Clear forced subtitle flags | — |

Keeping original subtitle tracks preserves the option to remove the added
simplified versions later. Replaced original tracks cannot be recovered by these
scripts.

## Requirements

Install MKVToolNix and Python 3.10 or newer and make them accessible from the
command line. For font measurement and reconstruction support:

```console
python -m pip install Pillow fonttools uharfbuzz
```

On Linux, invoke the Python scripts directly; the `.bat` launchers use Windows
PowerShell.

```console
python simplify_ass.py input.ass --fonts-dir fonts
python simplify_ass.py input.ass --font-mkv episode.mkv
python sync_fonts.py /path/to/media --preview
python subtitle_flags.py /path/to/media
```

The converter writes `input.simple.ass` by default. Exact fonts help prove line
geometry; uncertain fragments are retained. Use `--help` for all options.
Current converter version: **2026.10.13.189**.

### Subtitle default and forced flags

`subtitle_flags.py` combines the four default/forced flag scripts in a Python
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
The four original `.bat` flag scripts remain available for existing workflows.

## Development

- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): setup, regression commands and planned reviews.
- [docs/](docs/): technical notes and historical review documents.
- [tests/](tests/): Python regression checks and helpers.
- [tests/windows/](tests/windows/): batch-testing wrappers and PowerShell reporting checks.
- [validation/](validation/): suite runners, corpus comparison and render diagnostics.

Fonts, subtitle fixtures and generated reports are local development assets.
See the development guide for restoring them and running tests.
