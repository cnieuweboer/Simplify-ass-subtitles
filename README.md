# MKV Subtitle Simplification Tools

A collection of scripts for simplifying complex ASS/SSA subtitles embedded in MKV files.

The main goal is to make subtitles easier to render on TVs and other lower-powered playback devices that may stutter or struggle with heavily styled subtitles, karaoke effects, vector drawings, and other complex ASS features.

The repository also includes several utility scripts for setting or removing the **default** and **forced** flags on subtitle tracks.

## Usage

Copy the desired `.bat` file and its corresponding `.ps1` and `.py` files into a folder containing your MKV files.

Then simply double-click the `.bat` file.

The scripts process the MKV files in that folder automatically.

## Subtitle Simplification

The simplification scripts can reduce or remove complex ASS/SSA formatting while preserving normal subtitle text and simpler styling where possible.

The **Partial** option is intended for subtitles that contain actual ASS vector drawings, such as translated signs, UI elements, or background graphics.

This mode makes several assumptions about how those drawings are constructed. It has only been tested against a limited number of subtitles, so results may vary considerably between releases or fansub groups.

If you do not need vector drawings, the normal simplification options are safer.

## Removing Simplified Subtitles

`remove_simplified_subtitles.bat` can remove subtitle tracks previously added by the simplification scripts.

It only works when the original subtitle tracks were preserved and the simplified versions were added as additional tracks.

If you chose to replace the original subtitles during simplification, those original tracks cannot be restored by this script.

## Requirements

- MKVToolNix
- Python
- Pillow
- fontTools

Install the required Python packages with:

```text
python -m pip install Pillow fonttools
```

MKVToolNix and Python must also be installed and accessible from the command line.
