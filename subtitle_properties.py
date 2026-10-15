#!/usr/bin/env python3
"""Edit MKV subtitle names or default/forced flags in place using MKVToolNix."""

import argparse
from collections import Counter
from copy import deepcopy
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


def subtitle_groups(info, duplicate_keys=()):
    """Map subtitle IDs to metadata groups, separating duplicates by occurrence."""
    seen = Counter()
    groups = {}
    for track in info.get("tracks", []):
        if track["type"] != "subtitles":
            continue
        key = subtitle_key(track)
        seen[key] += 1
        groups[track["id"]] = (*key, seen[key]) if key in duplicate_keys else key
    return groups


def subtitle_catalog(infos):
    """Use the same occurrence keys throughout the batch, including missing peers."""
    layouts = [tuple(subtitle_key(track) for track in info.get("tracks", [])
                     if track["type"] == "subtitles") for info in infos]
    duplicates = {key for layout in layouts for key, count in Counter(layout).items()
                  if count > 1}
    catalog = sorted({key for info in infos
                      for key in subtitle_groups(info, duplicates).values()})
    if duplicates:
        print("\nIdentical subtitle metadata found; duplicate entries use occurrence in subtitle track order.")
        print("Track order cannot confirm the contents of unnamed or identically named subtitles.")
        if any(layout != layouts[0] for layout in layouts[1:]):
            print("WARNING: Subtitle names, languages, formats, counts, or order differ across MKVs.")
            print("Cannot verify subtitle groups across this batch. Check each file before confirming;")
            print("process individual files separately if their track order does not correspond.")
    return catalog, duplicates


def group_label(key):
    name, language, codec = key[:3]
    suffix = f" [occurrence {key[3]}]" if len(key) == 4 else ""
    return f"[{language}] {name or '(unnamed)'} [{codec}]{suffix}"


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


def desired_flags(info, clear_default, clear_forced, defaults, forced, duplicate_keys=()):
    """Return expected flags for every subtitle, preserving unselected flags."""
    expected = {}
    groups = subtitle_groups(info, duplicate_keys)
    for track in info.get("tracks", []):
        if track["type"] != "subtitles":
            continue
        props = track["properties"]
        number = props.get("number")
        if not isinstance(number, int) or number < 1 or number in expected:
            raise RuntimeError("Missing or duplicate subtitle track number")
        key = groups[track["id"]]
        expected[number] = (
            key in defaults or (not clear_default and bool(props.get("default_track", True))),
            key in forced or (not clear_forced and bool(props.get("forced_track", False))),
        )
    return expected


def edit_file(path, info, clear_default, clear_forced, defaults, forced, duplicate_keys=(),
              renames=None, source_stamp=None):
    if source_stamp is not None and file_stamp(path) != source_stamp:
        raise RuntimeError("Source changed since scanning; rerun to review the current tracks")
    expected = desired_flags(info, clear_default, clear_forced, defaults, forced, duplicate_keys)
    names = desired_names(info, renames, duplicate_keys)
    args = ["mkvpropedit", str(path)]
    for track in info.get("tracks", []):
        if track["type"] != "subtitles":
            continue
        props = track["properties"]
        default, force = expected[props["number"]]
        changes = []
        name = names[props["number"]]
        if name != (props.get("track_name") or ""):
            changes.extend(["--set", f"name={name}"])
        if default != bool(props.get("default_track", True)):
            changes.extend(["--set", f"flag-default={int(default)}"])
        if force != bool(props.get("forced_track", False)):
            changes.extend(["--set", f"flag-forced={int(force)}"])
        if changes:
            args.extend(["--edit", f"track:@{props['number']}", *changes])
    if len(args) == 2:
        print("  Already matches requested properties.")
        return False
    result = subprocess.run(args, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or
                           f"mkvpropedit returned {result.returncode}")
    if result.returncode == 1:
        print(f"  MKVToolNix warning: {result.stdout.strip()} {result.stderr.strip()}")
    after = identify(path)
    verify_properties(info, after, expected, names)
    print("  Verified subtitle properties.")
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


def file_stamp(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def property_action():
    selected = choice("Subtitle properties", ["Set/remove default and forced flags", "Rename subtitle tracks"])
    return "flags" if selected == 1 else "rename"


def language_names():
    """Use MKVToolNix's language catalog for readable name suggestions."""
    result = subprocess.run(["mkvmerge", "--ui-language", "en_US", "--list-languages"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    names = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) == 4 and re.fullmatch(r"[a-z]{3}", cells[1]):
                names.update({code: cells[0] for code in cells[1:] if code})
    if not names:
        print("Warning: Could not read language names; suggestions will use the displayed codes.")
    return names


def suggested_names(catalog, languages):
    counters = Counter()
    used = {(key[1], key[0]) for key in catalog if key[0]}
    suggestions = {}
    for key in catalog:
        name, language, _ = key[:3]
        if name:
            suggestions[key] = name
            continue
        label = languages.get(language.split("-")[0].lower(), language)
        while True:
            counters[language] += 1
            suggestion = f"{label} {counters[language]}"
            if (language, suggestion) not in used:
                break
        suggestions[key] = suggestion
        used.add((language, suggestion))
    return suggestions


def rename_selection(catalog):
    print("\nAvailable subtitle groups")
    for number, key in enumerate(catalog, 1):
        print(f"  {number}. {group_label(key)}")
    selected = selection("Select subtitle groups to rename", catalog)
    if not selected:
        return {}
    languages = language_names() if any(not key[0] for key in selected) else {}
    suggestions = suggested_names(catalog, languages)
    renames = {}
    for number, key in enumerate(catalog, 1):
        if key not in selected:
            continue
        print(f"\n{number}. {group_label(key)}")
        answer = input(f"New name [{suggestions[key]}] (Enter to accept; - to clear; q to cancel): ")
        answer = answer.strip()
        if answer.lower() == "q":
            raise EOFError
        renames[key] = "" if answer == "-" else answer or suggestions[key]
    return renames


def desired_names(info, renames=None, duplicate_keys=()):
    renames = renames or {}
    groups = subtitle_groups(info, duplicate_keys)
    return {track["properties"]["number"]:
            renames.get(groups[track["id"]], track.get("properties", {}).get("track_name") or "")
            for track in info.get("tracks", []) if track["type"] == "subtitles"}


def preview_renames(items, folder, renames, duplicate_keys, failures):
    print("\nReview track renames before editing:")
    changed_files = changed_tracks = 0
    for path, info in items:
        expected = desired_names(info, renames, duplicate_keys)
        changes = [(track, expected[track["properties"]["number"]])
                   for track in info.get("tracks", []) if track["type"] == "subtitles"
                   and expected[track["properties"]["number"]] != (track["properties"].get("track_name") or "")]
        if not changes:
            continue
        changed_files += 1
        changed_tracks += len(changes)
        print(f"  {path.relative_to(folder)}")
        groups = subtitle_groups(info, duplicate_keys)
        for track, name in changes:
            print(f"    ID {track['id']}: {group_label(groups[track['id']])} -> {name or '(unnamed)'}")
    print(f"Rename {changed_tracks} track(s) in {changed_files} file(s) in place; {failures} scan failure(s).")
    return changed_tracks


def property_signature(track):
    props = track.get("properties", {})
    return (track["id"], track["type"], track.get("codec"), props.get("codec_id"),
            props.get("number"), props.get("uid"), props.get("track_name") or "",
            (props.get("language") or "und").casefold(),
            (props.get("language_ietf") or "").casefold(),
            *(bool(props.get(key, key in ("default_track", "enabled_track"))) for key in
              ("default_track", "forced_track", "enabled_track", "flag_hearing_impaired",
               "flag_visual_impaired", "flag_text_descriptions", "flag_original", "flag_commentary")))


def verify_properties(before, after, flags, names):
    expected = deepcopy(before["tracks"])
    for track in expected:
        if track["type"] != "subtitles":
            continue
        props = track["properties"]
        props["default_track"], props["forced_track"] = flags[props["number"]]
        props["track_name"] = names[props["number"]]
    if [property_signature(track) for track in expected] != [
            property_signature(track) for track in after["tracks"]]:
        raise RuntimeError("Verification failed: track names, flags, or other track metadata differ")
    for key in ("attachments", "chapters", "global_tags", "track_tags"):
        if before.get(key, []) != after.get(key, []):
            raise RuntimeError(f"Verification failed: {key.replace('_', ' ')} differ")


def flag_options(items, catalog):
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
        for number, key in enumerate(catalog, 1):
            print(f"  {number}. {group_label(key)}")
        if setting == 1:
            defaults = selection("Select subtitles for both default and forced", catalog)
            forced = defaults.copy()
        else:
            defaults = selection("Select default subtitles", catalog)
            forced = selection("Select forced subtitles", catalog)
    return clear_default, clear_forced, defaults, forced


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
    items, stamps = [], {}
    failures = 0
    print(f"Scanning {len(files)} MKV file(s) in {folder}...")
    for path in files:
        try:
            stamp = file_stamp(path)
            info = identify(path)
            if file_stamp(path) != stamp:
                raise RuntimeError("Source changed during scanning")
            desired_flags(info, False, False, set(), set())
            items.append((path, info))
            stamps[path] = stamp
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            print(f"ERROR reading {path.name}: {exc}")
            failures += 1
    catalog, duplicate_keys = subtitle_catalog([info for _, info in items])
    if not catalog:
        print("No subtitle tracks found.")
        return int(bool(failures))
    try:
        action = property_action()
        renames = None
        clear_default = clear_forced = False
        defaults, forced = set(), set()
        if action == "rename":
            renames = rename_selection(catalog)
            if not preview_renames(items, folder, renames, duplicate_keys, failures):
                print("No track names need changing.")
                return int(bool(failures))
        else:
            clear_default, clear_forced, defaults, forced = flag_options(items, catalog)
        if action == "flags":
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
    try:
        for path, info in items:
            print(f"Processing: {path.name}")
            try:
                updated += edit_file(path, info, clear_default, clear_forced, defaults, forced,
                                     duplicate_keys=duplicate_keys, renames=renames,
                                     source_stamp=stamps[path])
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                print(f"  ERROR: {exc}")
                failures += 1
    except KeyboardInterrupt:
        print("\nStopped. Completed property edits remain in place.")
        failures += 1
    print(f"Updated files: {updated}; failures: {failures}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
