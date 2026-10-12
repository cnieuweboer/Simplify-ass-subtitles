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
```

The converter writes `input.simple.ass` by default. Exact fonts help prove line
geometry; uncertain fragments are retained. Use `--help` for all options.
Current converter version: **2026.10.12.180**.

## Development

- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): setup, regression commands and planned reviews.
- [docs/](docs/): technical notes and historical review documents.
- [tests/](tests/): Python regression checks and helpers.
- [tests/windows/](tests/windows/): batch-testing wrappers and PowerShell reporting checks.
- [validation/](validation/): suite runners, corpus comparison and render diagnostics.

Fonts, subtitle fixtures and generated reports are local development assets.
See the development guide for restoring them and running tests.
