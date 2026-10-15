# Optional drag-and-drop targets

Copy the target you want **beside its corresponding Python script**.
The `dnd helper` folder is just a place to download them from; it does not need
to be installed beside the scripts. Python 3.10+ and the usual dependencies
are required.

Drop **MKV files or folders containing MKVs** onto a target. A file drop processes
only that MKV; a folder drop scans only that folder's MKVs, without subfolders.
Use the Python tool with `-r` / `--recursive` to include subfolders. Track/font/simplification
outputs go to `output/` under the input folder or the dropped file's parent.
For example, dropping `A/X.mkv` onto a helper in `B/` writes `A/output/X.mkv`.
The properties helper edits names/flags in the selected originals in place.
Keep `simplify_ass.py` beside `simplify_subtitles.py` when using its helper.

## Windows

Copy `windows/subtitle_tracks.bat` beside `subtitle_tracks.py`
(and similarly for the other tools), then drop an MKV or folder onto the BAT.

## macOS

Build the Finder droplets once:

```sh
sh "dnd helper/macos/setup-macos.command"
```

Copy the desired generated `.app` from `macos/` beside its Python script.
Drop MKVs or folders onto the app; menus open in Terminal. Approve Terminal control
if macOS asks. Double-clicking the app opens a folder picker.

## Linux

Create launchers next to whichever Python tools are installed in your chosen
folder:

```sh
sh "dnd helper/linux/setup-linux.sh" /path/to/python/tools
```

Alternatively, copy `setup-linux.sh` beside the Python scripts and run it
without a folder argument. Setup creates a `.sh` wrapper and a `.desktop`
target for each tool found. Allow launching/trust the targets if requested,
then drop MKVs or folders onto them. Rerun setup after moving their folder.

Drag-and-drop support depends on the desktop/file manager; Linux has no
universal drop handler. If necessary, use **Open With** or run the optional
wrapper directly:

```sh
sh /path/to/python/tools/subtitle_tracks.sh /path/to/media
```

Native Windows/macOS drag-and-drop still needs testing on those systems.
