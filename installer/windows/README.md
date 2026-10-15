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

The installer unblocks the files it installs and asks whether to add your `bin`
folder to your **user PATH**. It preserves existing PATH entries and avoids
duplicates. Restart your terminal after a PATH change. These steps normally
need no administrator rights; the install destination must be writable.

If files are already installed, choose **Reinstall / update**, **Remove**, or
**Cancel**. Removal deletes only this project's nine files and removes `bin`
and `simplify-ass` only when empty. Other files and tools are preserved.

When removing, the installer offers to remove `bin` from your user PATH if it
is present. If other files remain in `bin`, it warns that removing that PATH
entry may stop those tools working by command name. PATH changes default to No.

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
