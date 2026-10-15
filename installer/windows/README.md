# Windows PATH installation

Download and extract the complete repository ZIP, or clone it. Python 3.10+ is
required to run the installer.

```cmd
installer\windows\install.cmd
installer\windows\install.cmd "D:\My Tools"
installer\windows\install.cmd --target "D:\My Tools"
```

Default layout:

```text
C:\Tools\
    bin\
        simplify_subtitles.cmd
        remove_subtitles.cmd
        subtitle_flags.cmd
        sync_fonts.cmd
    simplify-ass\
        simplify_ass.py
        simplify_subtitles.py
        remove_subtitles.py
        subtitle_flags.py
        sync_fonts.py
```

Add **`C:\Tools\bin`** (or your chosen root's `bin` folder) to your user PATH,
then open a new terminal. The installer prints the exact folder; it does not
modify PATH. Rerunning it updates these files and leaves other tools alone.

Python, MKVToolNix, and Python dependencies are installed separately:

```cmd
py -3 -m pip install Pillow fonttools uharfbuzz
```

From a media folder:

```cmd
simplify_subtitles
remove_subtitles -r
subtitle_flags --input "D:\Media\episode.mkv"
sync_fonts -i "D:\Media" -o "D:\Cleaned" -f "D:\Fonts"
```

Launchers default to the current folder. `-i` / `--input` overrides it; other
options pass through unchanged. Use an input option rather than positional input.
Folder scans remain nonrecursive unless `-r` / `--recursive` is supplied.
