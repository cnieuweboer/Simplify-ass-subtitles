# Optional drag-and-drop targets

Copy the target you want **beside its corresponding Python script**.
The `dnd helper` folder is just a place to download them from; it does not need
to be installed beside the scripts. Python 3.10+ and the usual dependencies
are required.

Drop **folders containing MKVs** onto a target. The selected tool scans those
folders normally; removal/font outputs go to each input folder's `output/`.

## Windows

Copy `windows/remove_subtitles.bat` beside `remove_subtitles.py`
(and similarly for the other tools), then drop a folder onto the BAT.

## macOS

Build the Finder droplets once:

```sh
sh "dnd helper/macos/setup-macos.command"
```

Copy the desired generated `.app` from `macos/` beside its Python script.
Drop folders onto the app; menus open in Terminal. Approve Terminal control
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
then drop folders onto them. Rerun setup after moving their folder.

Drag-and-drop support depends on the desktop/file manager; Linux has no
universal drop handler. If necessary, use **Open With** or run the optional
wrapper directly:

```sh
sh /path/to/python/tools/remove_subtitles.sh /path/to/media
```

Native Windows/macOS drag-and-drop still needs testing on those systems.
