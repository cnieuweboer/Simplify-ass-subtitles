#!/usr/bin/env python3
"""Select MKV subtitles to remove, preview the changes, and remux into output/."""

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ERRORS = (OSError, ValueError, KeyError, TypeError, RuntimeError)


@dataclass
class ScannedFile:
    path: Path
    info: dict
    stamp: tuple
    pairs: dict


def identify(tool, path):
    result = subprocess.run([tool, "-J", str(path)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or
                           f"mkvmerge returned {result.returncode}")
    info = json.loads(result.stdout)
    if info.get("errors"):
        raise RuntimeError("; ".join(info["errors"]))
    for warning in info.get("warnings", []):
        print(f"  Warning: {warning}")
    if result.returncode == 1 and result.stderr.strip():
        print(f"  Warning: {result.stderr.strip()}")
    ids = [track["id"] for track in info["tracks"]]
    if any(type(track_id) is not int or track_id < 0 for track_id in ids) or len(set(ids)) != len(ids):
        raise RuntimeError("Missing, invalid, or duplicate track IDs")
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


def track_label(track):
    name, language, codec = subtitle_key(track)
    return f"[{language}] {name or '(unnamed)'} [{codec}]"


def simplified_pairs(info):
    """Match added copies to same-language originals within this file.

    Preserve PowerShell's case-insensitive name matching. Format may differ
    because the simplifier can convert SSA to ASS. No subtitle extraction.
    """
    subtitles = [track for track in info["tracks"] if track["type"] == "subtitles"]
    pairs = {}
    for track in subtitles:
        name, language, _ = subtitle_key(track)
        match = re.fullmatch(r"(.*?)\s+\(Simplified\)", name, re.IGNORECASE)
        if match:
            original_name = match[1].rstrip()
        elif name.casefold() == "simplified":
            original_name = ""
        else:
            continue
        originals = [other["id"] for other in subtitles
                     if other["id"] != track["id"]
                     and subtitle_key(other)[0].casefold() == original_name.casefold()
                     and subtitle_key(other)[1].casefold() == language.casefold()]
        if originals:
            pairs[track["id"]] = originals
    return pairs


def file_stamp(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def find_files(root, output, recursive):
    """Exclude output trees; do not follow directory symlinks."""
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name.casefold() != "output"
                         and (output is None or not (Path(directory) / name).resolve().is_relative_to(output)))
        for name in names:
            path = Path(directory) / name
            if (path.suffix.lower() == ".mkv" and path.is_file()
                    and (output is None or not path.resolve().is_relative_to(output))):
                files.append(path)
        if not recursive:
            break
    return sorted(files, key=lambda path: str(path.relative_to(root)).casefold())


def output_path(source, root, output):
    return output / source.relative_to(root) if output is not None else source.parent / "output" / source.name


def parse_selection(answer, catalog):
    answer = answer.strip()
    if not answer or answer.casefold() == "q":
        raise EOFError
    keep = bool(re.match(r"(?i)^k(?:\s|$)", answer))
    if keep:
        answer = answer[1:].strip()
    token_pattern = r"(?:[0-9]+|[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{1,8})*)"
    if not re.fullmatch(token_pattern + r"(?:[\s,]+" + token_pattern + r")*", answer):
        raise ValueError("Enter numbers or language codes separated by commas/spaces; prefix with k to keep.")
    selected = set()
    for token in re.split(r"[\s,]+", answer):
        if token.isdigit():
            number = int(token)
            if not 1 <= number <= len(catalog):
                raise ValueError("A number is outside the list.")
            selected.add(catalog[number - 1])
        else:
            language = token.casefold()
            matching = {key for key in catalog
                        if key[1].casefold() == language}
            if not matching:
                raise ValueError(f"No subtitles found for language code: {token}")
            selected.update(matching)
    return selected, keep


def manual_selection(catalog):
    print("\nOption 2: Available subtitles across all scanned MKVs")
    for number, key in enumerate(catalog, 1):
        print(f"  {number}. {group_label(key)}")
    print("\nSelect subtitles to remove using numbers or listed languages (1,3 or en,ja).")
    print("Use the k prefix to keep only selected subtitles (k 1,3 or k en,ja).")
    print("Blank or q to cancel.")
    while True:
        answer = input("\nSelection: ")
        try:
            return parse_selection(answer, catalog)
        except ValueError as error:
            print(error)


def removal_mode():
    print("\nOption 1: Removal\n  1. Manual track selection\n  2. Remove simplified subtitles")
    while True:
        answer = input("Choose 1 or 2 (q to cancel): ").strip().lower()
        if answer == "q":
            raise EOFError
        if answer in ("1", "2"):
            return answer == "2"
        print("Enter 1 or 2.")


def preview(items, root, output, automatic, selected, failures, keep=False, duplicate_keys=()):
    print("\nReview removals before remuxing:")
    if keep:
        print("Keep selected subtitle groups; remove all other subtitles from every file.")
    plan = []
    for item in items:
        subtitles = [track for track in item.info["tracks"] if track["type"] == "subtitles"]
        groups = subtitle_groups(item.info, duplicate_keys)
        matching = {track["id"] for track in subtitles if groups[track["id"]] in selected}
        relative = item.path.relative_to(root)
        if automatic:
            removed = set(item.pairs)
        elif keep:
            removed = {track["id"] for track in subtitles} - matching
        else:
            removed = matching
        target = output_path(item.path, root, output)
        if not removed:
            print(f"  {relative}: " + ("all subtitles already match the keep selection; skipped."
                                      if keep else "no matching tracks; skipped."))
            continue
        if target.exists() or target.is_symlink():
            print(f"  {relative}: existing output; skipped ({target}).")
            continue
        print(f"\n  {relative} -> {target}")
        if keep and not matching:
            print("    No selected keep tracks found: ALL subtitles will be removed.")
        for track in item.info["tracks"]:
            if track["type"] != "subtitles":
                continue
            action = "REMOVE" if track["id"] in removed else "KEEP"
            print(f"    {action} ID {track['id']}: {group_label(groups[track['id']])}")
            if automatic and track["id"] in removed:
                original_ids = ", ".join(str(number) for number in item.pairs[track["id"]])
                print(f"      Matching original subtitle ID(s): {original_ids}")
        plan.append((item, target, removed))
    print(f"\nRemove {sum(len(removed) for _, _, removed in plan)} track(s) from "
          f"{len(plan)} file(s); {failures} scan failure(s).")
    print("Original MKVs remain untouched. Other tracks, attachments, and chapters are retained.")
    return plan


def track_signature(track, include_ietf=True):
    props = track.get("properties", {})
    name, _, codec = subtitle_key(track)
    return (track["type"], name, codec, props.get("language") or "und",
            (props.get("language_ietf") or "").casefold() if include_ietf else "",
            props.get("uid"),
            bool(props.get("default_track", True)), bool(props.get("forced_track", False)),
            bool(props.get("enabled_track", True)))


def verify_output(before, after, removed):
    retained = [track for track in before["tracks"] if track["id"] not in removed]
    # MKVToolNix adds IETF tags to older files; preserve existing tags and legacy codes.
    ietf_uids = {track.get("properties", {}).get("uid") for track in retained
                 if track.get("properties", {}).get("language_ietf")}
    expected = Counter(track_signature(track, track.get("properties", {}).get("uid") in ietf_uids)
                       for track in retained)
    actual = Counter(track_signature(track, track.get("properties", {}).get("uid") in ietf_uids)
                     for track in after["tracks"])
    if actual != expected:
        raise RuntimeError("Verification failed: retained tracks or their metadata differ")
    def attachments(info):
        return Counter((a.get("file_name"), a.get("content_type"), a.get("size"))
                       for a in info.get("attachments", []))
    if attachments(before) != attachments(after):
        raise RuntimeError("Verification failed: attachments differ")
    if before.get("chapters", []) != after.get("chapters", []):
        raise RuntimeError("Verification failed: chapter counts differ")


def remux(tool, item, target, removed):
    if target.exists() or target.is_symlink():
        print("  Existing output; skipped.")
        return False
    if file_stamp(item.path) != item.stamp:
        raise RuntimeError("Source changed since scanning; rerun to review the current tracks")
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".partial.mkv", dir=target.parent)
    os.close(handle)
    partial = Path(name)
    try:
        args = [tool, "-o", str(partial)]
        kept_subtitles = [track["id"] for track in item.info["tracks"]
                          if track["type"] == "subtitles" and track["id"] not in removed]
        if kept_subtitles:
            args.extend(["--subtitle-tracks", ",".join(map(str, kept_subtitles))])
        else:
            args.append("--no-subtitles")
        # Explicitly preserve flags; mkvmerge otherwise may choose a new default.
        for track in item.info["tracks"]:
            if track["id"] in removed:
                continue
            props = track.get("properties", {})
            args.extend(["--default-track-flag", f"{track['id']}:{int(bool(props.get('default_track', True)))}",
                         "--forced-display-flag", f"{track['id']}:{int(bool(props.get('forced_track', False)))}"])
        args.append(str(item.path))
        result = subprocess.run(args)
        if result.returncode not in (0, 1):
            raise RuntimeError(f"mkvmerge returned {result.returncode}")
        if result.returncode == 1:
            print("  MKVToolNix reported warnings; checking the output.")
        if not partial.stat().st_size:
            raise RuntimeError("mkvmerge did not create a nonempty output")
        verify_output(item.info, identify(tool, partial), removed)
        if file_stamp(item.path) != item.stamp:
            raise RuntimeError("Source changed during remuxing; output discarded")
        if target.exists() or target.is_symlink():
            raise RuntimeError("Output appeared during remuxing; existing output preserved")
        partial.rename(target)
        print(f"  Verified and saved: {target}")
        return True
    finally:
        partial.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path,
                        help="MKV file or folder (default: beside this script)")
    parser.add_argument("-i", "--input", type=Path,
                        help="MKV file or folder (default: beside this script)")
    parser.add_argument("-r", "--recursive", action="store_true", help="include subfolders, excluding output folders")
    parser.add_argument("-o", "--output", type=Path, help="output folder (default: output/ beside each source MKV)")
    args = parser.parse_args(argv)
    if args.folder is not None and args.input is not None:
        parser.error("Specify input positionally or with -i, not both.")
    source = (args.input or args.folder or Path(__file__).resolve().parent).resolve()
    single_file = source.is_file()
    root = source.parent if single_file else source
    output = args.output.resolve() if args.output else None
    if not source.is_dir() and not (single_file and source.suffix.casefold() == ".mkv"):
        print(f"ERROR: Input must be an existing MKV file or folder: {source}")
        return 1
    if output is not None and root.is_relative_to(output):
        print("ERROR: Output folder must differ from the input folder and cannot contain it.")
        return 1
    tool = shutil.which("mkvmerge")
    if not tool:
        print("ERROR: Install MKVToolNix and add mkvmerge to PATH.")
        return 1
    items, failures = [], 0
    try:
        files = [source] if single_file else find_files(root, output, args.recursive)
        print(f"Scanning {len(files)} MKV file(s) in {root}...")
        for path in files:
            try:
                stamp = file_stamp(path)
                info = identify(tool, path)
                if file_stamp(path) != stamp:
                    raise RuntimeError("Source changed during scanning")
                items.append(ScannedFile(path, info, stamp, simplified_pairs(info)))
            except ERRORS as exc:
                print(f"ERROR reading {path}: {exc}")
                failures += 1
        catalog, duplicate_keys = subtitle_catalog([item.info for item in items])
        if not catalog:
            print("No subtitle tracks found.")
            return int(bool(failures))
        automatic = removal_mode() if any(item.pairs for item in items) else False
        selected, keep = (set(), False) if automatic else manual_selection(catalog)
        while True:
            plan = preview(items, root, output, automatic, selected, failures, keep, duplicate_keys)
            prompt = "Remux these files? (y/N; m for manual selection): " if automatic else \
                     "Remux these files? (y/N; m to revise selection): "
            answer = input(prompt).strip().lower()
            if answer == "m":
                automatic = False
                selected, keep = manual_selection(catalog)
                continue
            if answer not in ("y", "yes"):
                print("Cancelled. No files changed.")
                return int(bool(failures))
            if not plan:
                print("No files need remuxing.")
                return int(bool(failures))
            break
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No files changed.")
        return int(bool(failures))
    except ERRORS as exc:
        print(f"ERROR: {exc}")
        return 1
    saved = 0
    try:
        for item, target, removed in plan:
            print(f"\nProcessing: {item.path.relative_to(root)}")
            try:
                saved += remux(tool, item, target, removed)
            except ERRORS as exc:
                print(f"  ERROR: {exc}")
                failures += 1
    except KeyboardInterrupt:
        print("\nStopped. Completed outputs remain; the current partial output was discarded.")
        failures += 1
    print(f"Saved files: {saved}; failures: {failures}; output: {output or 'output/ beside each source MKV'}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
