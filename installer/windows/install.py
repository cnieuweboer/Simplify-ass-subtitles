#!/usr/bin/env python3
"""Install the Windows PATH launchers and Python tools from this checkout."""

import argparse
import ctypes
import json
import ntpath
import os
from pathlib import Path
import re
import stat
import shutil
import subprocess
import sys
import tempfile


TOOLS = ("simplify_subtitles", "subtitle_tracks", "subtitle_properties", "sync_fonts")
WINDOWS = os.name == "nt"
MAINTENANCE = ("install.py", "subtitle_tools_update.py", "subtitle_tools.py")
OPTIONAL_LAUNCHERS = (*TOOLS, "subtitle_tools_update")
SETTINGS = "install_settings.json"
# Only installations without an ownership inventory use this v213 migration list.
LEGACY_ENGINE_MODULES = ("_simplify_ass/__init__.py", "_simplify_ass/font_metrics.py")
REQUIREMENTS = {"Pillow": "PIL.ImageFont", "fonttools": "fontTools.ttLib", "uharfbuzz": "uharfbuzz"}


def module_path(name):
    """Accept portable Python source paths within the private engine package."""
    if not isinstance(name, str):
        return False
    parts = name.split("/")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
    return (len(parts) >= 2 and parts[0] == "_simplify_ass" and parts[-1].endswith(".py")
            and all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", part)
                    and part.lower() not in reserved and part != "__pycache__"
                    for part in (*parts[:-1], parts[-1][:-3])))


def check_local_path(base, path):
    """Do not follow links/junctions when replacing or deleting managed paths."""
    relative = path.relative_to(base)
    for item in (base, *(base.joinpath(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1))):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError(f"Linked installation/source path is not supported: {item}")
        if item != path and not item.is_dir():
            raise RuntimeError(f"A file occupies an installed package directory: {item}")


def install_settings(target):
    path = target / "simplify-ass" / SETTINGS
    check_local_path(target, path)
    if not path.exists():
        return {"version": 1}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        supported = (*OPTIONAL_LAUNCHERS, "subtitle_tools")
        if (data.get("version") not in (1, 2) or not isinstance(data.get("launchers"), list)
                or any(name not in supported for name in data["launchers"])):
            raise ValueError("invalid launcher preferences")
        if data["version"] == 2:
            names = data.get("engine_modules")
            if (not isinstance(names, list) or not all(module_path(name) for name in names)
                    or "_simplify_ass/__init__.py" not in names
                    or len({name.casefold() for name in names}) != len(names)):
                raise ValueError("invalid engine ownership inventory")
        return data
    except (ValueError, AttributeError, TypeError) as error:
        raise RuntimeError("Cannot read install settings/ownership inventory; restore a valid settings file before retrying.") from error


def owned_modules(target):
    data = install_settings(target)
    return tuple(data["engine_modules"]) if data["version"] == 2 else LEGACY_ENGINE_MODULES


def source_modules(repository):
    package = repository / "_simplify_ass"
    if not (package / "__init__.py").is_file():
        raise RuntimeError("Missing installer source: _simplify_ass/__init__.py. Download or clone the complete repository first.")
    names = []
    check_local_path(repository, package)
    for source in sorted(package.rglob("*")):
        if "__pycache__" in source.relative_to(package).parts:
            continue
        check_local_path(repository, source)
        if source.suffix != ".py" or not source.is_file():
            continue
        name = source.relative_to(repository).as_posix()
        if not module_path(name):
            raise RuntimeError(f"Unsupported engine module path: {name}")
        names.append(name)
    if len({name.casefold() for name in names}) != len(names):
        raise RuntimeError("Engine module paths collide on Windows.")
    return tuple(names)


def installed_files(target):
    return ([target / "simplify-ass" / (tool + ".py") for tool in (*TOOLS, "simplify_ass")]
            + [target / "simplify-ass" / name for name in (*MAINTENANCE, *owned_modules(target))]
            + [target / "bin" / (tool + ".cmd") for tool in (*OPTIONAL_LAUNCHERS, "subtitle_tools")]
            + [target / "simplify-ass" / SETTINGS])


def bytecode_files(target, sources):
    found = []
    for source in sources:
        cache = source.parent / "__pycache__"
        check_local_path(target, cache)
        if cache.is_dir():
            for path in sorted(cache.glob(source.stem + ".*.pyc")):
                check_local_path(target, path)
                if path.is_file():
                    found.append(path)
    return found


def prune_empty_folders(target, paths):
    folders = {path.parent / "__pycache__" for path in paths if path.suffix == ".py"}
    for path in paths:
        folders.update(parent for parent in path.parents if parent != target and target in parent.parents)
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        try:
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError:
            # Empty-directory tidying is optional; never turn a committed update
            # into a reported failure because Windows still holds a directory.
            pass


def selected_launchers(target, individual):
    if individual is not None:
        return {"subtitle_tools", *OPTIONAL_LAUNCHERS} if individual else {"subtitle_tools"}
    data = install_settings(target)
    supported = (*OPTIONAL_LAUNCHERS, "subtitle_tools")
    present = {tool for tool in supported
               if (target / "bin" / (tool + ".cmd")).is_file()}
    if "launchers" in data:
        present.intersection_update(data["launchers"])
    return {"subtitle_tools", *present}


def missing_packages():
    code = ("import importlib,json\nmissing=[]\n"
            f"for package,module in {REQUIREMENTS!r}.items():\n"
            " try: importlib.import_module(module)\n"
            " except Exception: missing.append(package)\n"
            "print(json.dumps(missing))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Could not check Python package requirements: " + result.stderr.strip())
    try:
        missing = json.loads(result.stdout.strip().splitlines()[-1])
        if not isinstance(missing, list) or any(package not in REQUIREMENTS for package in missing):
            raise ValueError("invalid package list")
        return missing
    except (ValueError, IndexError, TypeError) as error:
        raise RuntimeError("Could not read Python package check results.") from error


def offer_dependencies():
    missing = missing_packages()
    if not missing:
        print("Required Python packages are available.")
        return
    print("Missing or unavailable Python packages: " + ", ".join(missing))
    if prompt_key("Install missing Python packages? (y/N): ", ("y", "n")) != "y":
        print("Skipped package installation. Install later with:")
        print(f'  "{sys.executable}" -m pip install ' + " ".join(missing))
        return
    command = [sys.executable, "-m", "pip", "install"]
    if sys.prefix == sys.base_prefix:
        command.append("--user")
    command.extend(missing)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Python package installation failed (exit {error.returncode}).") from error
    remaining = missing_packages()
    if remaining:
        raise RuntimeError("Python packages are still unavailable: " + ", ".join(remaining))
    print("Required Python packages are available.")


def unblock(path):
    if WINDOWS:
        marker = Path(str(path) + ":Zone.Identifier")
        if marker.exists():
            marker.unlink(missing_ok=True)


def prompt_key(prompt, allowed):
    if WINDOWS and sys.stdin.isatty():
        import msvcrt
        print(prompt, end="", flush=True)
        while True:
            answer = msvcrt.getwch()
            if answer in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue
            if answer == "\x03":
                raise KeyboardInterrupt
            if answer in ("\r", "\n") and "n" in allowed:
                print("n")
                return "n"
            if answer.lower() in allowed:
                print(answer.lower())
                return answer.lower()
    while True:
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            answer = ""
        if not answer:
            return "n" if "n" in allowed else "q"
        if answer in allowed:
            return answer


def path_key(value):
    return ntpath.normcase(ntpath.normpath(ntpath.expandvars(value.strip().strip('"'))))


def has_path(value, folder):
    return any(entry.strip() and path_key(entry) == path_key(str(folder)) for entry in value.split(";"))


def updated_path(value, folder, adding):
    if adding:
        if has_path(value, folder):
            return value
        return value + ("" if not value or value.endswith(";") else ";") + str(folder)
    return ";".join(entry for entry in value.split(";")
                    if not (entry.strip() and path_key(entry) == path_key(str(folder))))


def read_user_path():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            value, kind = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        return "", winreg.REG_EXPAND_SZ
    if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        raise RuntimeError("User PATH has an unsupported registry type; leaving it unchanged.")
    return value, kind


def notify_environment():
    from ctypes import wintypes
    notify = ctypes.windll.user32.SendMessageTimeoutW
    notify.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t))
    notify.restype = wintypes.LPARAM
    environment = ctypes.create_unicode_buffer("Environment")
    result = ctypes.c_size_t()
    return bool(notify(0xffff, 0x001a, 0, ctypes.cast(environment, ctypes.c_void_p).value,
                       0x0002, 5000, ctypes.byref(result)))


def write_user_path(value, kind):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, kind, value)
    if not notify_environment():
        print("PATH was saved, but Windows could not notify all applications of the change.")


def offer_path_change(bin_dir, adding):
    if not WINDOWS:
        if adding:
            print(f"Add this folder to your user PATH manually:\n  {bin_dir}")
            print("PATH was not changed; automatic PATH updates are available on Windows.")
        return
    value, kind = read_user_path()
    present = has_path(value, bin_dir)
    if adding and present:
        print(f"Already in your user PATH: {bin_dir}")
        return
    if not adding and not present:
        print(f"Not in your user PATH: {bin_dir}")
        return
    if not adding and bin_dir.is_dir() and any(bin_dir.iterdir()):
        print(f"WARNING: Other files or folders remain in {bin_dir}.")
        print("Removing this folder from PATH may stop those tools working by command name.")
    action = "Add" if adding else "Remove"
    direction = "to" if adding else "from"
    if prompt_key(f"{action} {bin_dir} {direction} your user PATH? (y/N): ", ("y", "n")) != "y":
        print("PATH was not changed.")
        return
    # Re-read after confirmation so other PATH edits made during the prompt survive.
    value, kind = read_user_path()
    replacement = updated_path(value, bin_dir, adding)
    if replacement != value:
        write_user_path(replacement, kind)
        print("User PATH updated. Restart your terminal to pick up the change.")
    else:
        print("User PATH already matches the requested setting.")


def remove(target):
    removed = 0
    managed = installed_files(target)
    caches = bytecode_files(target, [p for p in managed if p.suffix == ".py"])
    # Validate the entire removal set before deleting any files.
    for path in (*managed, *caches):
        check_local_path(target, path)
    for path in (*managed, *caches):
        if path.is_file():
            path.unlink()
            removed += 1
    prune_empty_folders(target, (*managed, *caches))
    print(f"Removed {removed} installed file(s). Unrelated files were preserved.")


def install(repository, target, individual_launchers=None):
    launchers = repository / "installer" / "windows" / "bin"
    tool_dir = target / "simplify-ass"
    bin_dir = target / "bin"
    previous_modules = set(owned_modules(target))
    modules = source_modules(repository)
    selected = selected_launchers(target, individual_launchers)
    previous_spelling = {name.casefold(): name for name in previous_modules}
    if any(name.casefold() in previous_spelling and previous_spelling[name.casefold()] != name for name in modules):
        raise RuntimeError("Case-only engine module renames are not portable to Windows; use a distinct module name.")
    files = [(repository / (tool + ".py"), tool_dir / (tool + ".py")) for tool in TOOLS]
    files.append((repository / "simplify_ass.py", tool_dir / "simplify_ass.py"))
    files.extend((repository / name, tool_dir / name) for name in modules)
    files.extend((launchers.parent / name, tool_dir / name) for name in MAINTENANCE)
    files.extend((launchers / (tool + ".cmd"), bin_dir / (tool + ".cmd"))
                 for tool in sorted(selected))
    obsolete = [tool_dir / name for name in sorted(previous_modules - set(modules))]
    removals = [bin_dir / (tool + ".cmd") for tool in OPTIONAL_LAUNCHERS if tool not in selected]
    removals.extend(obsolete)
    removals.extend(bytecode_files(target, obsolete))
    for name in modules:
        destination = tool_dir / name
        if (name not in previous_modules and destination.exists()
                and (repository / name).resolve() != destination.resolve()):
            raise RuntimeError(f"An unrelated file occupies a new engine module path: {destination}")
    # Check the complete source set before creating or updating anything.
    for destination in (*removals, *(destination for _, destination in files), tool_dir / SETTINGS):
        check_local_path(target, destination)
        if destination.is_dir():
            raise RuntimeError(f"A folder occupies an installed file's path: {destination}")
    for source, destination in files:
        if not source.is_file():
            raise RuntimeError(f"Missing installer source: {source}. Download or clone the complete repository first.")
    bin_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".subtitle-tools-install-", dir=target))
    preserve_staging = False
    try:
        pending = []
        settings = staging / SETTINGS
        settings.write_text(json.dumps({"version": 2, "launchers": sorted(selected),
                                        "engine_modules": list(modules)}, indent=2) + "\n", encoding="utf-8")
        files.append((settings, tool_dir / SETTINGS))
        # Stage all replacements and backups before touching installed files.
        for index, (source, destination) in enumerate(files):
            if source.resolve() == destination.resolve():
                continue
            replacement = staging / f"new-{index}"
            shutil.copy2(source, replacement)
            backup = None
            if destination.exists():
                backup = staging / f"old-{index}-{destination.name}"
                shutil.copy2(destination, backup)
            pending.append((replacement, destination, backup))
        # Retired owned modules, bytecode and optional launchers share rollback.
        for index, destination in enumerate(removals):
            if destination.is_file():
                backup = staging / f"removed-{index}-{destination.name}"
                shutil.copy2(destination, backup)
                pending.append((None, destination, backup))
        created_directories = []
        applied = []
        try:
            for replacement, destination, backup in pending:
                if replacement is None:
                    destination.unlink()
                else:
                    missing = []
                    parent = destination.parent
                    while not parent.exists():
                        missing.append(parent)
                        parent = parent.parent
                    for directory in reversed(missing):
                        directory.mkdir()
                        created_directories.append(directory)
                    replacement.replace(destination)
                applied.append((replacement, destination, backup))
            for _, destination in files:
                unblock(destination)
        except BaseException:
            failed = []
            for replacement, destination, backup in reversed(applied):
                try:
                    if backup is None:
                        destination.unlink(missing_ok=True)
                    else:
                        backup.replace(destination)
                except OSError:
                    failed.append(str(destination))
            for directory in reversed(created_directories):
                try:
                    if directory.is_dir() and not any(directory.iterdir()):
                        directory.rmdir()
                except OSError:
                    failed.append(str(directory))
            if failed:
                preserve_staging = True
                raise RuntimeError("Could not restore these files after installation failed: " + ", ".join(failed)
                                   + f". Recovery copies were kept in {staging}")
            raise
    finally:
        if not preserve_staging:
            shutil.rmtree(staging)
    prune_empty_folders(target, removals)
    return bin_dir, tool_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, help="installation root (default: C:\\Tools)")
    parser.add_argument("--target", type=Path, help="installation root instead of C:\\Tools")
    parser.add_argument("--keep-launchers", action="store_true",
                        help="preserve the installed launcher selection when reinstalling")
    args = parser.parse_args(argv)
    if args.folder is not None and args.target is not None:
        parser.error("Specify the installation root positionally or with --target, not both.")
    target = (args.target or args.folder or Path(r"C:\Tools")).expanduser().resolve()
    repository = Path(__file__).resolve().parents[2]
    try:
        if any(path.exists() or path.is_symlink() for path in installed_files(target)):
            print(f"Existing installation found: {target}")
            print("  1. Reinstall / update\n  2. Remove\n  q. Cancel")
            action = prompt_key("Choose 1 or 2 (q to cancel): ", ("1", "2", "q"))
            if action == "q":
                print("Cancelled.")
                return 0
            if action == "2":
                remove(target)
                offer_path_change(target / "bin", adding=False)
                return 0
        individual = None if args.keep_launchers else prompt_key("Install individual launchers? (y/N): ", ("y", "n")) == "y"
        bin_dir, tool_dir = install(repository, target, individual_launchers=individual)
        print(f"Installed Python tools: {tool_dir}")
        print(f"Installed CMD launchers: {bin_dir}")
        if WINDOWS:
            print("Installed files unblocked.")
        offer_path_change(bin_dir, adding=True)
        offer_dependencies()
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 0
    except (OSError, RuntimeError) as error:
        print(f"Installer failed: {error}")
        return 1
    print("\nRequired: Python 3.10+ and MKVToolNix on PATH.")
    print("\nCommands default to the current folder. Override it with -i / --input.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
