# Drag-and-drop helpers

Keep this folder beside `subtitle_flags.py`, `remove_subtitles.py`, and
`sync_fonts.py`. Python 3.10+ and the tools' usual dependencies are required.

Drop **folders containing MKVs** onto the target for the desired tool.
Each folder gets its own scan and options. Defaults are the same as running
the Python tool on that folder; removal/font outputs go to its `output/`.

## Windows

Drop a folder onto one of the three `.bat` files in `windows/`.

## macOS

Run once from Terminal:

```sh
sh "dnd helper/macos/setup-macos.command"
```

This builds three AppleScript `.app` droplets in `macos/`. Drop folders onto
those apps in Finder. Menus open in Terminal; approve Terminal control if macOS
asks. Double-clicking an app opens a folder picker.

## Linux

```sh
sh "dnd helper/linux/setup-linux.sh"
```

This creates three `.desktop` launchers in `linux/`. Allow launching/trust them
if your file manager asks. Rerun setup after moving the repository or changing
your Python installation.

Folder drops onto launchers depend on the desktop/file manager. Linux has no
universal drag target, and `.py` files usually are not drop targets. If drops
are unsupported, use a file manager's **Open With** launcher selection or:

```sh
python3 "dnd helper/dnd_helper.py" remove_subtitles /path/to/media --pause
```

Native Windows/Finder/desktop integration needs testing on the target OS.
