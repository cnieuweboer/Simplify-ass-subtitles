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
            ass_overrides.py
            font_metrics.py
            font_outlines.py
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

## Implementation modules and ownership (v214)

The installer discovers Python sources recursively under `_simplify_ass/`;
the updater downloads those sources from its pinned GitHub tree. New modules and
nested packages need no installer filename-list changes. Module/directory names
must be portable Python identifiers, excluding `__pycache__` and Windows device
names. The top-level package `__init__.py` is required. Data files and caches are
not runtime delivery inputs; ship a complete repository rather than a partial
selection of files. As before, updating executes code from this repository.

`install_settings.json` version 2 records launcher preferences and the relative
`engine_modules` paths owned by the installation. An update stages new sources,
settings, backups, and removal of retired owned sources and their bytecode as
one transaction. Failure restores the old files and settings; newly created
nested directories are removed when empty. Uninstall uses this same inventory.
Unrelated files, caches and nonempty directories are preserved. A new module
whose destination is occupied by an unowned file causes an error before changes;
move that file aside deliberately and retry. Managed paths must not be symlinks
or Windows junctions. Case-only module renames are rejected for portability.

Keep this settings file with the installed tools; do not delete or hand-edit the
ownership inventory. Invalid settings stop updates and uninstall before changes.
Restore a valid backup before retrying. Version 1 settings (and older installs
without settings) migrate using only the two known v213 module paths; the
installer never claims all existing Python files in the installed package.

## Upgrading older installations

**Installations with the v214 updater can update normally**, including the new
`font_outlines.py` in v215 and `ass_overrides.py` in v216. The v214 preparation
release kept the same two modules
as v213, allowing the fixed-list v213 updater to install that preparation. Current
`main` now includes the additional module: clients still running v213 must use
the complete-repository installer below. Newer updaters discover later module
additions and removals automatically.

Updaters from before v213 cannot download the implementation package. Clients
that **skip v214** and still run the v213 fixed-list updater also cannot download
modules added by a later extraction. For either situation, download/extract the
**complete current repository** and rerun its installer against the existing
target; do not rely on the old update command to bridge that change:

```cmd
installer\windows\install.cmd --target "D:\My Tools" --keep-launchers
```

Choose **Reinstall / update**. `--keep-launchers` preserves the saved launcher
selection and does not recreate manually removed optional launchers. PATH and
package-installation changes retain their existing prompts. This is also the
recovery route if an old updater has already installed an incomplete runtime.
A preparation release cannot change the download rules of a client that never
installed it.

Keep the implementation directory beside `simplify_ass.py` when moving an
installation. See [the v214 delivery review](../../docs/MODULE_DELIVERY.md) for
validation evidence and the boundary retained for future extractions.
