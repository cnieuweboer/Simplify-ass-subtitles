#!/usr/bin/env python3
"""Interactively clear/set MKV subtitle flags in place using MKVToolNix."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def identify(path):
    result = subprocess.run(
        ["mkvmerge", "-J", str(path)], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or
                           "mkvmerge could not read the file")
    if result.returncode == 1:
        print(f"  Warning reading {path.name}: {result.stderr.strip()}")
    info = json.loads(result.stdout)
    if info.get("errors"):
        raise RuntimeError("; ".join(info["errors"]))
    return info


def subtitle_key(track):
    props = track.get("properties", {})
    return (props.get("track_name") or "",
            props.get("language_ietf") or props.get("language") or "und",
            props.get("codec_id") or track.get("codec") or "unknown")


def single_key(prompt, allowed):
    """Read only a listed key; restore terminal settings even on cancellation."""
    if not sys.stdin.isatty():
        while True:
            answer = input(prompt).strip().lower()
            if not answer:
                raise EOFError
            if answer in allowed:
                return answer
    if sys.platform == "win32":
        import msvcrt
        def read_key():
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()  # Consume the extended key's scan code.
                return ""
            return key
        restore = None
    else:
        import termios
        import tty
        import select
        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
        def restore():
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        def read_key():
            raw = os.read(fd, 1)
            if not raw:
                raise EOFError
            key = raw.decode("utf-8", errors="ignore")
            if key == "\x1b":
                # Ignore escape/arrow/function keys, including numeric parameters.
                if select.select([fd], [], [], 0.05)[0]:
                    prefix = os.read(fd, 1)
                    if prefix in (b"[", b"O"):
                        while select.select([fd], [], [], 0.05)[0]:
                            part = os.read(fd, 1)
                            if not part or 0x40 <= part[0] <= 0x7e:
                                break
                return ""
            return key
    try:
        if sys.platform != "win32":
            tty.setcbreak(fd)
        print(prompt, end="", flush=True)
        while True:
            key = read_key()
            if key == "\x03":
                raise KeyboardInterrupt
            if key == "\x04":
                raise EOFError
            if key.lower() in allowed:
                print(key.lower(), flush=True)
                return key.lower()
    finally:
        if restore is not None:
            restore()


def choice(prompt, options):
    print(f"\n{prompt}")
    for number, label in enumerate(options, 1):
        print(f"  {number}. {label}")
    answer = single_key("Choose a number (q to cancel): ",
                        tuple(str(number) for number in range(1, len(options) + 1)) + ("q",))
    if answer == "q":
        raise EOFError
    return int(answer)


def selection(prompt, catalog):
    while True:
        answer = input(f"{prompt} (commas/spaces; blank for none; q to cancel): ").strip()
        if answer.lower() == "q":
            raise EOFError
        if not answer:
            return set()
        if not re.fullmatch(r"[0-9]+(?:[\s,]+[0-9]+)*", answer):
            print("Enter numbers separated by commas or spaces.")
            continue
        numbers = {int(token) for token in re.split(r"[\s,]+", answer)}
        if any(number < 1 or number > len(catalog) for number in numbers):
            print("A number is outside the list.")
            continue
        return {catalog[number - 1] for number in numbers}


def desired_flags(info, clear_default, clear_forced, defaults, forced):
    """Return expected flags for every subtitle, preserving unselected flags."""
    expected = {}
    for track in info.get("tracks", []):
        if track["type"] != "subtitles":
            continue
        props = track["properties"]
        number = props.get("number")
        if not isinstance(number, int) or number < 1 or number in expected:
            raise RuntimeError("Missing or duplicate subtitle track number")
        key = subtitle_key(track)
        expected[number] = (
            key in defaults or (not clear_default and bool(props.get("default_track", True))),
            key in forced or (not clear_forced and bool(props.get("forced_track", False))),
        )
    return expected


def edit_file(path, info, clear_default, clear_forced, defaults, forced):
    expected = desired_flags(info, clear_default, clear_forced, defaults, forced)
    args = ["mkvpropedit", str(path)]
    for track in info.get("tracks", []):
        if track["type"] != "subtitles":
            continue
        props = track["properties"]
        default, force = expected[props["number"]]
        changes = []
        if default != bool(props.get("default_track", True)):
            changes.extend(["--set", f"flag-default={int(default)}"])
        if force != bool(props.get("forced_track", False)):
            changes.extend(["--set", f"flag-forced={int(force)}"])
        if changes:
            args.extend(["--edit", f"track:@{props['number']}", *changes])
    if len(args) == 2:
        print("  Already matches requested flags.")
        return False
    result = subprocess.run(args, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or
                           f"mkvpropedit returned {result.returncode}")
    if result.returncode == 1:
        print(f"  MKVToolNix warning: {result.stdout.strip()} {result.stderr.strip()}")
    after = identify(path)
    actual = desired_flags(after, False, False, set(), set())
    if actual != expected:
        raise RuntimeError("Verification failed: subtitle flags do not match requested flags")
    print("  Verified subtitle flags.")
    return True


def find_files(root, recursive):
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name.casefold() != "output")
        files.extend(Path(directory) / name for name in names
                     if Path(name).suffix.casefold() == ".mkv" and (Path(directory) / name).is_file())
        if not recursive:
            break
    return sorted(files, key=lambda path: str(path.relative_to(root)).casefold())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path,
                        help="MKV file or folder (default: beside this script)")
    parser.add_argument("-i", "--input", type=Path,
                        help="MKV file or folder (default: beside this script)")
    parser.add_argument("-r", "--recursive", action="store_true", help="include subfolders, excluding output folders")
    args = parser.parse_args(argv)
    if args.folder is not None and args.input is not None:
        parser.error("Specify input positionally or with -i, not both.")
    source = (args.input or args.folder or Path(__file__).resolve().parent).resolve()
    single_file = source.is_file()
    folder = source.parent if single_file else source
    if not source.is_dir() and not (single_file and source.suffix.casefold() == ".mkv"):
        print(f"ERROR: Input must be an existing MKV file or folder: {source}")
        return 1
    missing = [tool for tool in ("mkvmerge", "mkvpropedit") if not shutil.which(tool)]
    if missing:
        print(f"ERROR: Install MKVToolNix and add to PATH: {', '.join(missing)}")
        return 1
    files = [source] if single_file else find_files(folder, args.recursive)
    if not files:
        print(f"No MKV files found in {folder}.")
        return 1
    items = []
    failures = 0
    print(f"Scanning {len(files)} MKV file(s) in {folder}...")
    for path in files:
        try:
            info = identify(path)
            desired_flags(info, False, False, set(), set())
            items.append((path, info))
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            print(f"ERROR reading {path.name}: {exc}")
            failures += 1
    catalog = sorted({subtitle_key(track) for _, info in items
                      for track in info.get("tracks", []) if track["type"] == "subtitles"})
    if not catalog:
        print("No subtitle tracks found.")
        return int(bool(failures))
    try:
        existing_flags = [pair for _, info in items
                          for pair in desired_flags(info, False, False, set(), set()).values()]
        has_default = any(default for default, _ in existing_flags)
        has_forced = any(forced for _, forced in existing_flags)
        clear_default = clear_forced = False
        if has_default and has_forced:
            options = [("Remove default and forced", True, True),
                       ("Remove forced", False, True), ("Remove default", True, False),
                       ("Keep default and forced", False, False)]
        elif has_default:
            options = [("Remove default", True, False), ("Keep default", False, False)]
        elif has_forced:
            options = [("Remove forced", False, True), ("Keep forced", False, False)]
        else:
            options = []
            print("No default or forced subtitle flags found; skipping removal options.")
        if options:
            remove = choice("Option 1: Remove existing subtitle flags", [label for label, _, _ in options])
            _, clear_default, clear_forced = options[remove - 1]
        setting = choice("Option 2: Set default/forced flags", [
            "Set default and forced together", "Set default and forced separately",
            "Do not set default or forced",
        ])
        defaults, forced = set(), set()
        if setting != 3:
            print("\nOption 3: Available subtitles across all scanned MKVs")
            for number, (name, language, codec) in enumerate(catalog, 1):
                print(f"  {number}. [{language}] {name or '(unnamed)'} [{codec}]")
            if setting == 1:
                defaults = selection("Select subtitles for both default and forced", catalog)
                forced = defaults.copy()
            else:
                defaults = selection("Select default subtitles", catalog)
                forced = selection("Select forced subtitles", catalog)
        print(f"\nClear default: {clear_default}; clear forced: {clear_forced}")
        for label, selected in (("Set default", defaults), ("Set forced", forced)):
            print(f"{label}: " + (", ".join(str(i) for i, key in enumerate(catalog, 1)
                                           if key in selected) or "none"))
        print(f"Edit {len(items)} file(s) in place; {failures} scan failure(s).")
        if single_key("Proceed? (y/N): ", ("y", "n")) != "y":
            print("Cancelled. No files changed.")
            return int(bool(failures))
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No files changed.")
        return int(bool(failures))
    updated = 0
    for path, info in items:
        print(f"Processing: {path.name}")
        try:
            updated += edit_file(path, info, clear_default, clear_forced, defaults, forced)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            print(f"  ERROR: {exc}")
            failures += 1
    print(f"Updated files: {updated}; failures: {failures}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
