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
                         and not (Path(directory) / name).resolve().is_relative_to(output))
        for name in names:
            path = Path(directory) / name
            if path.suffix.lower() == ".mkv" and path.is_file() and not path.resolve().is_relative_to(output):
                files.append(path)
        if not recursive:
            break
    return sorted(files, key=lambda path: str(path.relative_to(root)).casefold())


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
    for number, (name, language, codec) in enumerate(catalog, 1):
        print(f"  {number}. [{language}] {name or '(unnamed)'} [{codec}]")
    while True:
        answer = input("Select subtitles: numbers or languages (1,3 or en,ja); k to keep; blank or q to cancel: ")
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


def preview(items, root, output, automatic, selected, failures, keep=False):
    print("\nReview removals before remuxing:")
    if keep:
        print("Keep selected subtitle groups; remove all other subtitles from every file.")
    plan = []
    for item in items:
        subtitles = [track for track in item.info["tracks"] if track["type"] == "subtitles"]
        matching = {track["id"] for track in subtitles if subtitle_key(track) in selected}
        relative = item.path.relative_to(root)
        if automatic:
            removed = set(item.pairs)
        elif keep:
            removed = {track["id"] for track in subtitles} - matching
        else:
            removed = matching
        target = output / relative
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
            print(f"    {action} ID {track['id']}: {track_label(track)}")
            if automatic and track["id"] in removed:
                original_ids = ", ".join(str(number) for number in item.pairs[track["id"]])
                print(f"      Matching original subtitle ID(s): {original_ids}")
        plan.append((item, target, removed))
    print(f"\nRemove {sum(len(removed) for _, _, removed in plan)} track(s) from "
          f"{len(plan)} file(s); {failures} scan failure(s).")
    print("Original MKVs remain untouched. Other tracks, attachments, and chapters are retained.")
    return plan


def track_signature(track):
    props = track.get("properties", {})
    return (track["type"], *subtitle_key(track), props.get("uid"),
            bool(props.get("default_track", True)), bool(props.get("forced_track", False)),
            bool(props.get("enabled_track", True)))


def verify_output(before, after, removed):
    expected = Counter(track_signature(track) for track in before["tracks"] if track["id"] not in removed)
    actual = Counter(track_signature(track) for track in after["tracks"])
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
                        help="folder of MKVs (legacy positional syntax; default: beside this script)")
    parser.add_argument("-i", "--input-dir", type=Path,
                        help="folder of MKVs (default: beside this script)")
    parser.add_argument("--recursive", action="store_true", help="include subfolders, excluding output folders")
    parser.add_argument("-o", "--output-dir", type=Path, help="output folder (default: INPUT/output)")
    args = parser.parse_args(argv)
    if args.folder is not None and args.input_dir is not None:
        parser.error("Specify the input folder either positionally or with -i, not both.")
    root = (args.input_dir or args.folder or Path(__file__).resolve().parent).resolve()
    output = args.output_dir.resolve() if args.output_dir else root / "output"
    if not root.is_dir():
        print(f"ERROR: Not a directory: {root}")
        return 1
    if root.is_relative_to(output):
        print("ERROR: Output folder must differ from the input folder and cannot contain it.")
        return 1
    tool = shutil.which("mkvmerge")
    if not tool:
        print("ERROR: Install MKVToolNix and add mkvmerge to PATH.")
        return 1
    items, failures = [], 0
    try:
        files = find_files(root, output, args.recursive)
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
        catalog = sorted({subtitle_key(track) for item in items
                          for track in item.info["tracks"] if track["type"] == "subtitles"})
        if not catalog:
            print("No subtitle tracks found.")
            return int(bool(failures))
        automatic = removal_mode() if any(item.pairs for item in items) else False
        selected, keep = (set(), False) if automatic else manual_selection(catalog)
        while True:
            plan = preview(items, root, output, automatic, selected, failures, keep)
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
    print(f"Saved files: {saved}; failures: {failures}; output folder: {output}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
