#!/usr/bin/env python3
"""Install the Windows PATH launchers and Python tools from this checkout."""

import argparse
import ctypes
import json
import ntpath
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


TOOLS = ("simplify_subtitles", "subtitle_tracks", "subtitle_properties", "sync_fonts")
WINDOWS = os.name == "nt"
MAINTENANCE = ("install.py", "subtitle_tools_update.py", "subtitle_tools.py")
OPTIONAL_LAUNCHERS = (*TOOLS, "subtitle_tools_update")
SETTINGS = "install_settings.json"
# Keep the independently downloaded updater's required module list in sync.
ENGINE_MODULES = ("_simplify_ass/__init__.py", "_simplify_ass/font_metrics.py")
REQUIREMENTS = {"Pillow": "PIL.ImageFont", "fonttools": "fontTools.ttLib", "uharfbuzz": "uharfbuzz"}


def installed_files(target):
    return ([target / "simplify-ass" / (tool + ".py") for tool in (*TOOLS, "simplify_ass")]
            + [target / "simplify-ass" / name for name in (*MAINTENANCE, *ENGINE_MODULES)]
            + [target / "bin" / (tool + ".cmd") for tool in (*OPTIONAL_LAUNCHERS, "subtitle_tools")]
            + [target / "simplify-ass" / SETTINGS])


def selected_launchers(target, individual):
    if individual is not None:
        return {"subtitle_tools", *OPTIONAL_LAUNCHERS} if individual else {"subtitle_tools"}
    settings = target / "simplify-ass" / SETTINGS
    supported = (*OPTIONAL_LAUNCHERS, "subtitle_tools")
    present = {tool for tool in supported
               if (target / "bin" / (tool + ".cmd")).is_file()}
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            names = data["launchers"]
            if data.get("version") != 1 or not isinstance(names, list) or any(
                    not isinstance(name, str) or name not in supported for name in names):
                raise ValueError("invalid launcher preferences")
            present.intersection_update(names)
        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError("Cannot read launcher preferences; reinstall to select them again.") from error
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
    for path in managed:
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1
    # Remove only bytecode corresponding to managed source names. Other user
    # files/caches keep their directories; never recursively remove the tree.
    cache_dirs = {p.parent / "__pycache__" for p in managed if p.suffix == ".py"}
    for source in (p for p in managed if p.suffix == ".py"):
        cache = source.parent / "__pycache__"
        if cache.is_dir() and not cache.is_symlink():
            for path in cache.glob(source.stem + ".*.pyc"):
                if path.is_file() or path.is_symlink():
                    path.unlink()
                    removed += 1
    folders = {*cache_dirs, target / "simplify-ass/_simplify_ass",
               target / "simplify-ass", target / "bin"}
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        if not folder.is_symlink() and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    print(f"Removed {removed} installed file(s). Unrelated files were preserved.")


def install(repository, target, individual_launchers=None):
    launchers = repository / "installer" / "windows" / "bin"
    tool_dir = target / "simplify-ass"
    bin_dir = target / "bin"
    selected = selected_launchers(target, individual_launchers)
    files = [(repository / (tool + ".py"), tool_dir / (tool + ".py")) for tool in TOOLS]
    files.append((repository / "simplify_ass.py", tool_dir / "simplify_ass.py"))
    files.extend((repository / name, tool_dir / name) for name in ENGINE_MODULES)
    files.extend((launchers.parent / name, tool_dir / name) for name in MAINTENANCE)
    files.extend((launchers / (tool + ".cmd"), bin_dir / (tool + ".cmd"))
                 for tool in sorted(selected))
    # Check the complete source set before creating or updating anything.
    for source, destination in files:
        if not source.is_file():
            raise RuntimeError(f"Missing installer source: {source}. Download or clone the complete repository first.")
        if destination.parent.exists() and not destination.parent.is_dir():
            raise RuntimeError(f"A file occupies an installed package directory: {destination.parent}")
        if destination.is_dir():
            raise RuntimeError(f"A folder occupies an installed file's path: {destination}")
    bin_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".subtitle-tools-install-", dir=target))
    preserve_staging = False
    try:
        pending = []
        settings = staging / SETTINGS
        settings.write_text(json.dumps({"version": 1, "launchers": sorted(selected)}, indent=2) + "\n", encoding="utf-8")
        files.append((settings, tool_dir / SETTINGS))
        if (tool_dir / SETTINGS).is_dir():
            raise RuntimeError("A folder occupies the install settings path.")
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
        # Remove unselected optional launchers in the same transaction.
        removals = [bin_dir / (tool + ".cmd") for tool in OPTIONAL_LAUNCHERS if tool not in selected]
        for destination in removals:
            if destination.is_file():
                backup = staging / ("removed-" + destination.name)
                shutil.copy2(destination, backup)
                pending.append((None, destination, backup))
        created_directories = []
        try:
            for replacement, destination, backup in pending:
                if replacement is None:
                    destination.unlink()
                else:
                    if not destination.parent.exists():
                        destination.parent.mkdir()
                        created_directories.append(destination.parent)
                    replacement.replace(destination)
            for _, destination in files:
                unblock(destination)
        except BaseException:
            failed = []
            for replacement, destination, backup in reversed(pending):
                if (replacement is not None and replacement.exists()) or (replacement is None and destination.exists()):
                    continue
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
