#!/usr/bin/env python3
"""Interactively clear/set MKV subtitle flags in place using MKVToolNix."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess


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


def choice(prompt, options):
    print(f"\n{prompt}")
    for number, label in enumerate(options, 1):
        print(f"  {number}. {label}")
    while True:
        answer = input("Choose a number (q to cancel): ").strip()
        if answer.lower() == "q":
            raise EOFError
        if answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer)
        print("Enter one of the listed numbers.")


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path,
                        default=Path(__file__).resolve().parent,
                        help="folder of MKVs (default: beside this script; not recursive)")
    args = parser.parse_args(argv)
    folder = args.folder.resolve()
    if not folder.is_dir():
        print(f"ERROR: Not a directory: {folder}")
        return 1
    missing = [tool for tool in ("mkvmerge", "mkvpropedit") if not shutil.which(tool)]
    if missing:
        print(f"ERROR: Install MKVToolNix and add to PATH: {', '.join(missing)}")
        return 1
    files = sorted((path for path in folder.iterdir()
                    if path.is_file() and path.suffix.lower() == ".mkv"),
                   key=lambda path: path.name.casefold())
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
        if input("Proceed? (y/N): ").strip().lower() not in ("y", "yes"):
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
