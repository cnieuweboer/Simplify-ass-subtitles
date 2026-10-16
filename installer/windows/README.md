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
        subtitle_tools.cmd
    simplify-ass\
        simplify_ass.py
        _simplify_ass\
            __init__.py
            font_metrics.py
        simplify_subtitles.py
        subtitle_tracks.py
        subtitle_properties.py
        sync_fonts.py
        install.py
        subtitle_tools_update.py
        subtitle_tools.py
        install_settings.json
```

`Install individual launchers? (y/N)` defaults to No. Choosing Yes also installs
the four tool launchers and `subtitle_tools_update.cmd`. Reinstalling with No
removes those optional project launchers; unrelated files are preserved.

The installer unblocks the files it installs and asks whether to add your `bin`
folder to your **user PATH**. It preserves existing PATH entries and avoids
duplicates. Restart your terminal after a PATH change. These steps normally
need no administrator rights; the install destination must be writable.

If files are already installed, choose **Reinstall / update**, **Remove**, or
**Cancel**. Removal deletes only this project's installed files and removes `bin`
and `simplify-ass` only when empty. Other files and tools are preserved.

When removing, the installer offers to remove `bin` from your user PATH if it
is present. If other files remain in `bin`, it warns that removing that PATH
entry may stop those tools working by command name. PATH changes default to No.

Python and MKVToolNix must be installed separately. The installer checks Pillow,
fonttools, and uharfbuzz in its Python interpreter and offers to install missing
packages (default No). It uses a user install outside virtual environments;
inside a virtual environment it installs there. Manual alternative:

```cmd
py -3 -m pip install Pillow fonttools uharfbuzz
```

From a media folder, start the single-key tool menu:

```cmd
subtitle_tools
subtitle_tools -i "D:\Media" -r
```

Press `1` simplify, `2` add/remove tracks, `3` rename/edit flags, `4` fonts,
or `5` update; `q` cancels. Processing options
pass unchanged to the selected tool; its own confirmation still applies.
The properties tool edits names/flags in place and does not accept `-o`. Update always updates
this installation and ignores media-processing options.

Launchers default to the current folder. `-i` / `--input` overrides it; other
options pass through unchanged. Use an input option rather than positional input.
Folder scans remain nonrecursive unless `-r` / `--recursive` is supplied.

Choose **5. Update** in the menu to update from GitHub `main`. With optional
individual launchers enabled, you can also use:

```cmd
subtitle_tools_update
subtitle_tools_update --target "D:\My Tools"
```

The update command finds its own installation by default, regardless of the
current folder. It downloads one fixed GitHub revision and verifies all files
before replacing anything. Replacement failures roll back the changes; if a
file cannot be restored, the error identifies the retained recovery folder.
PATH, Python packages, MKVToolNix, and unrelated files are unchanged.
Updates preserve the saved launcher selection and do not recreate manually
removed optional launchers. Older installations without saved preferences keep
their existing launchers until you choose differently during reinstall.
Rerun the installer and answer No to remove existing individual launchers.

## Upgrading an installation from before v213

Older installed updaters do not download the new `_simplify_ass/` directory.
For this transition, download/extract the complete current repository and rerun
its installer against your existing target:

```cmd
installer\windows\install.cmd --target "D:\My Tools" --keep-launchers
```

Choose **Reinstall / update**. `--keep-launchers` preserves the saved launcher
selection and does not recreate manually removed optional launchers. PATH and
package-installation changes retain their existing prompts. Subsequent updates
using the newly installed updater include the implementation modules, verify
their contents and stage them with the other tool files. Missing modules fail
before any installed file is replaced.

Keep the implementation directory beside `simplify_ass.py` when moving an
installation. Uninstall removes only managed sources and their generated Python
bytecode; unrelated files and nonempty directories remain.
