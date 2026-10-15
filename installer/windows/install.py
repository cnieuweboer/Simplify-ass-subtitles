#!/usr/bin/env python3
"""Install the Windows PATH launchers and Python tools from this checkout."""

import argparse
import ctypes
import ntpath
import os
from pathlib import Path
import shutil
import sys
import tempfile


TOOLS = ("simplify_subtitles", "remove_subtitles", "subtitle_flags", "sync_fonts")
WINDOWS = os.name == "nt"


def installed_files(target):
    return ([target / "simplify-ass" / (tool + ".py") for tool in (*TOOLS, "simplify_ass")]
            + [target / "bin" / (tool + ".cmd") for tool in TOOLS])


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
    for path in installed_files(target):
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1
    for folder in (target / "simplify-ass", target / "bin"):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    print(f"Removed {removed} installed file(s). Unrelated files were preserved.")


def install(repository, target):
    launchers = repository / "installer" / "windows" / "bin"
    tool_dir = target / "simplify-ass"
    bin_dir = target / "bin"
    files = [(repository / (tool + ".py"), tool_dir / (tool + ".py")) for tool in TOOLS]
    files.append((repository / "simplify_ass.py", tool_dir / "simplify_ass.py"))
    files.extend((launchers / (tool + ".cmd"), bin_dir / (tool + ".cmd")) for tool in TOOLS)
    # Check the complete source set before creating or updating anything.
    for source, destination in files:
        if not source.is_file():
            raise RuntimeError(f"Missing installer source: {source}. Download or clone the complete repository first.")
        if destination.is_dir():
            raise RuntimeError(f"A folder occupies an installed file's path: {destination}")
    bin_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.mkdir(parents=True, exist_ok=True)
    for source, destination in files:
        if source.resolve() == destination.resolve():
            unblock(destination)
            continue
        # Replace individual files only after their copies are complete.
        with tempfile.NamedTemporaryFile(prefix=".install-", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        unblock(destination)
    return bin_dir, tool_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, help="installation root (default: C:\\Tools)")
    parser.add_argument("--target", type=Path, help="installation root instead of C:\\Tools")
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
        bin_dir, tool_dir = install(repository, target)
        print(f"Installed Python tools: {tool_dir}")
        print(f"Installed CMD launchers: {bin_dir}")
        if WINDOWS:
            print("Installed files unblocked.")
        offer_path_change(bin_dir, adding=True)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 0
    except (OSError, RuntimeError) as error:
        print(f"Installer failed: {error}")
        return 1
    print("\nRequired: Python 3.10+ and MKVToolNix on PATH.")
    print("Install Python dependencies with your chosen interpreter:")
    print("  py -3 -m pip install Pillow fonttools uharfbuzz")
    print("Use python instead of py -3 if that is your Python command.")
    print("\nCommands default to the current folder. Override it with -i / --input.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
