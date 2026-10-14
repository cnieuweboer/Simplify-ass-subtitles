#!/usr/bin/env python3
"""Simplify embedded ASS/SSA subtitles and write verified MKVs into output/."""

import argparse
import codecs
from collections import Counter
from copy import deepcopy
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


GENERATED_MARKER = "; Simplified by simplify_ass.py"
FLAG_OPTIONS = {
    "default_track": "--default-track-flag",
    "forced_track": "--forced-display-flag",
    "enabled_track": "--track-enabled-flag",
    "flag_hearing_impaired": "--hearing-impaired-flag",
    "flag_visual_impaired": "--visual-impaired-flag",
    "flag_text_descriptions": "--text-descriptions-flag",
    "flag_original": "--original-flag",
    "flag_commentary": "--commentary-flag",
}
STATS_ALIASES = {
    "aggressive_copies": "stacked_text_copies_flattened",
    "aggressive_sequences": "text_effect_sequences_frozen",
    "prototype_vector_candidates": "drawing_candidates",
    "prototype_strips_collapsed": "drawing_strips_collapsed",
    "prototype_vector_duplicates": "drawing_duplicates_removed",
    "prototype_fade_frames": "drawing_fade_frames_removed",
    "prototype_unsupported_drawings": "unsupported_drawings_excluded",
    "prototype_polygons_simplified": "drawing_contours_simplified",
    "prototype_held_scaling_exits": "drawing_scale_exits_frozen",
    "prototype_held_move_entrances": "drawing_move_entrances_frozen",
    "prototype_edge_slivers_detached": "drawing_edge_slivers_detached",
    "prototype_composite_backdrops": "composite_backdrops_built",
    "prototype_scrolling_events_removed": "scrolling_events_dropped",
    "prototype_scrolling_blocks_detected": "scrolling_blocks_detected",
    "prototype_scrolling_blocks_removed": "scrolling_blocks_dropped",
    "prototype_scrolling_blocks_retained": "scrolling_blocks_retained",
    "prototype_scrolling_peak_after_reduction": "scrolling_peak_after_reduction",
    "prototype_scrolling_concurrency_limit": "scrolling_concurrency_limit",
    "prototype_masked_foregrounds_restored": "masked_foregrounds_restored",
    "prototype_shadow_offsets_repaired": "shadow_offsets_repaired",
    "prototype_vectors_capped": "drawing_events_capped",
    "prototype_unmeasured_backdrops": "unmeasured_backdrops_retained",
    "prototype_supports_retained": "supporting_shapes_retained",
    "prototype_textures_removed": "font_textures_removed",
    "prototype_fullscreen_backgrounds": "fullscreen_backgrounds_retained",
    "prototype_adjacent_shapes": "adjacent_shapes_retained"
}


def normalize_stats(stats):
    result = dict(stats)
    for old, new in STATS_ALIASES.items():
        if old in result:
            result.setdefault(new, result[old])
            del result[old]
    return result


def find_tool(name, directory=None):
    executable = name + (".exe" if os.name == "nt" else "")
    if directory is not None:
        candidate = directory / executable
        if candidate.is_file():
            return str(candidate.resolve())
        raise RuntimeError(f"Cannot find {candidate}")
    candidate = Path(__file__).resolve().parent / executable
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(executable)
    if found:
        return str(Path(found).resolve())
    if os.name == "nt":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(variable):
                candidate = Path(os.environ[variable]) / "MKVToolNix" / executable
                if candidate.is_file():
                    return str(candidate)
    raise RuntimeError(f"Cannot find {executable}. Install MKVToolNix and add it to PATH.")


def diagnostic_lines(text):
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if (re.match(r"(?i)^(warning|error|fatal)\b", line)
                or line.startswith(("Exact fonts unavailable", "Font spacing unavailable", "RAQM unavailable"))):
            if line not in lines:
                lines.append(line)
    return lines


def run(command, context, *, cwd=None, capture=False, warnings_ok=True):
    result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8-sig",
                            errors="replace", capture_output=True)
    diagnostics = diagnostic_lines((result.stdout or "") + "\n" + (result.stderr or ""))
    if result.returncode not in ((0, 1) if warnings_ok else (0,)):
        detail = "\n".join(diagnostics)
        if not detail:
            detail = "\n".join(((result.stderr or result.stdout or "").strip()).splitlines()[-8:])
        raise RuntimeError(f"{context} failed (exit {result.returncode}). {detail}")
    if result.returncode == 1:
        print(f"  WARNING: MKVToolNix warning during {context}; checking the result.")
    for line in diagnostics:
        # The wrapper prints structured scrolling warnings once, with track IDs.
        if context == "subtitle simplification" and "for scrolling text blocks." in line:
            continue
        print("  " + (line if re.match(r"(?i)^(warning|error|fatal)\b", line) else "WARNING: " + line))
    return result.stdout if capture else None


def stage(message):
    print("  " + message, flush=True)


def count_stage(label, completed, total, *, final=False):
    text = f"  {label}... [{completed}/{total}]"
    if sys.stdout.isatty():
        print("\r" + text, end="\n" if final else "\r", flush=True)
    else:
        print(text, flush=True)


def reduction_text(before, after):
    if type(before) is not int or type(after) is not int:
        return "unavailable"
    change = f" ({100.0 * (after - before) / before:+.1f}%)" if before else ""
    return f"{before} -> {after}{change}"


def track_summary(track, stats, selected):
    number = track["id"]
    name = track.get("properties", {}).get("track_name") or "(unnamed)"
    name = " ".join(name.split())
    events = reduction_text(stats.get("original"), stats.get("output"))
    concurrency = reduction_text(stats.get("max_concurrent_in"), stats.get("max_concurrent_out"))
    suffix = "" if selected else "; below reduction threshold"
    print(f"  Track {number} ({name}): events {events}; peak concurrency {concurrency}{suffix}")


def identify(merge, path):
    info = json.loads(run([merge, "-J", str(path)], "identification", capture=True))
    if info.get("errors"):
        raise RuntimeError("; ".join(info["errors"]))
    if not info.get("container", {}).get("recognized") or not info["container"].get("supported"):
        raise RuntimeError(f"Unsupported or unrecognized input: {path}")
    for warning in info.get("warnings", []):
        print(f"  Warning: {warning}")
    ids = [track["id"] for track in info["tracks"]]
    if any(type(value) is not int or value < 0 for value in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("Invalid or duplicate track IDs")
    return info


def stamp(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def has_generated_marker(path):
    # Match the engine's Unicode header marker, not Dialogue text.
    with path.open("rb") as stream:
        prefix = stream.read(4)
    encoding = ("utf-32" if prefix.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)) else
                "utf-16" if prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig")
    in_script_info = False
    with path.open(encoding=encoding, errors="replace") as stream:
        for line in stream:
            stripped = line.lstrip("\ufeff").strip()
            if stripped == GENERATED_MARKER:
                return True
            if stripped.startswith("[") and stripped.endswith("]"):
                if stripped.casefold() == "[script info]":
                    in_script_info = True
                elif in_script_info:
                    break
    return False


def extract_items(extract, source, mode, items, directory):
    if not items:
        return
    command = [extract, str(source), mode, *[f"{number}:{path.name}" for number, path in items]]
    options = directory / (mode + "-options.json")
    options.write_text(json.dumps(command[1:], ensure_ascii=False), encoding="utf-8")
    label = "Extracting fonts" if mode == "attachments" else "Extracting subtitles"
    count_stage(label, 0, len(items))
    run([extract, "@" + str(options)], f"extract {mode}", cwd=directory)
    for _, path in items:
        if not path.is_file():
            raise RuntimeError(f"Extraction did not create {path.name}")
    count_stage(label, len(items), len(items), final=True)


def font_targets(info, directory):
    mime_suffixes = {
        "application/x-truetype-font": ".ttf", "application/vnd.ms-opentype": ".otf",
        "application/x-font-ttf": ".ttf", "application/x-font-opentype": ".otf",
        "font/ttf": ".ttf", "font/otf": ".otf", "font/collection": ".ttc",
        "application/font-sfnt": ".ttf",
    }
    result = []
    for attachment in info.get("attachments", []):
        suffix = Path(attachment.get("file_name", "")).suffix.lower()
        if suffix not in (".ttf", ".otf", ".ttc", ".otc"):
            suffix = mime_suffixes.get(attachment.get("content_type", "").lower())
        if suffix:
            number = attachment["id"]
            result.append((number, directory / f"font-{number}{suffix}"))
    return result


def find_files(root, output, recursive):
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name.casefold() != "output"
                         and not (Path(directory) / name).resolve().is_relative_to(output))
        files.extend(Path(directory) / name for name in names
                     if Path(name).suffix.lower() == ".mkv" and (Path(directory) / name).is_file()
                     and not (Path(directory) / name).resolve().is_relative_to(output))
        if not recursive:
            break
    return sorted(files, key=lambda path: str(path.relative_to(root)).casefold())


def passed_reduction(stats, minimum):
    original, output = stats.get("original"), stats.get("output")
    if type(original) is not int or type(output) is not int or original < 0 or output < 0:
        raise RuntimeError("Missing or invalid event counts")
    reduction = 100.0 * (original - output) / original if original else 0.0
    return reduction > minimum, reduction


def converted_codec(path):
    # Plain ASS/SSA identification omits codec_id; Matroska identification has it.
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            key, separator, value = line.strip().partition(":")
            if separator and key.casefold() == "scripttype":
                version = value.strip().casefold()
                if version in ("v4.00", "v4.00+"):
                    return "S_TEXT/ASS" if version.endswith("+") else "S_TEXT/SSA"
            if line.strip().casefold() == "[events]":
                break
    raise RuntimeError("Converted subtitle has no supported ASS/SSA ScriptType")


def signature(track, include_uid=False):
    properties = track.get("properties", {})
    return (track["type"], properties.get("codec_id", track.get("codec")),
            properties.get("track_name") or "",
            (properties.get("language_ietf") or properties.get("language") or "und").casefold(),
            tuple(bool(properties.get(key, key in ("default_track", "enabled_track")))
                  for key in FLAG_OPTIONS), properties.get("uid") if include_uid else None)


def verify_output(before, after, expected):
    tracks = after["tracks"]
    if len(tracks) != len(expected):
        raise RuntimeError("Output verification failed: track count differs")
    for index, (actual, (wanted, retained)) in enumerate(zip(tracks, expected)):
        if signature(actual, retained) != signature(wanted, retained):
            raise RuntimeError(f"Output verification failed: track {index} order, metadata, or flags differ")
    def attachments(info):
        # mkvmerge strips embedded directory components from attachment names.
        return Counter((a.get("file_name", "").replace("\\", "/").rsplit("/", 1)[-1],
                        a.get("content_type"), a.get("size"), a.get("description", ""))
                       for a in info.get("attachments", []))
    if attachments(before) != attachments(after):
        raise RuntimeError("Output verification failed: attachments differ")
    if before.get("chapters", []) != after.get("chapters", []):
        raise RuntimeError("Output verification failed: chapter counts differ")
    if before.get("global_tags", []) != after.get("global_tags", []):
        raise RuntimeError("Output verification failed: global tag counts differ")


def flag_args(track, track_id=None, added=False):
    number = track["id"] if track_id is None else track_id
    properties = track.get("properties", {})
    result = []
    for key, option in FLAG_OPTIONS.items():
        if key not in properties and key not in ("default_track", "forced_track", "enabled_track"):
            continue
        value = bool(properties.get(key, key in ("default_track", "enabled_track")))
        if added and key in ("default_track", "forced_track"):
            value = False
        result.extend([option, f"{number}:{int(value)}"])
    return result


def build_remux(before, replacements, added, partial, source):
    by_id = {candidate["track"]["id"]: (index, candidate)
             for index, candidate in enumerate(replacements, 1)}
    options = ["-o", str(partial)]
    if not added:
        removed = set(by_id)
        remaining = [track["id"] for track in before["tracks"]
                     if track["type"] == "subtitles" and track["id"] not in removed]
        options.extend(["--subtitle-tracks", ",".join(map(str, remaining))] if remaining else ["--no-subtitles"])
    for track in before["tracks"]:
        if added or track["id"] not in by_id:
            options.extend(flag_args(track))
    options.append(str(source))
    for candidate in replacements:
        track = candidate["track"]
        properties = track.get("properties", {})
        language = properties.get("language_ietf") or properties.get("language") or "und"
        name = properties.get("track_name") or ""
        if added:
            name = name + " (Simplified)" if name else "Simplified"
        options.extend(["--language", "0:" + language, "--track-name", "0:" + name])
        options.extend(flag_args(track, 0, added))
        options.append(str(candidate["output"]))
    order, expected = [], []
    for track in before["tracks"]:
        replacement = by_id.get(track["id"])
        if replacement is None or added:
            order.append(f"0:{track['id']}")
            expected.append((track, True))
        if replacement is not None:
            index, candidate = replacement
            order.append(f"{index}:0")
            wanted = deepcopy(track)
            properties = wanted.setdefault("properties", {})
            properties["codec_id"] = candidate["codec"]
            if added:
                properties["track_name"] = (properties.get("track_name") + " (Simplified)"
                                            if properties.get("track_name") else "Simplified")
                properties["default_track"] = properties["forced_track"] = False
            expected.append((wanted, False))
    options.extend(["--track-order", ",".join(order)])
    return options, expected


def process_file(source, destination, args, merge, extract, engine, report):
    source_stamp = stamp(source)
    stage("Reading MKV...")
    before = identify(merge, source)
    partial = None
    try:
        with tempfile.TemporaryDirectory(prefix="simplify-subtitles-") as temp:
            work = Path(temp)
            candidates = []
            for track in before["tracks"]:
                codec = track.get("properties", {}).get("codec_id")
                if track["type"] == "subtitles" and codec in ("S_TEXT/ASS", "S_TEXT/SSA"):
                    suffix = ".ssa" if codec == "S_TEXT/SSA" else ".ass"
                    path = work / f"track-{track['id']}{suffix}"
                    candidates.append({"track": track, "input": path,
                                       "output": path.with_name(path.stem + ".simple" + path.suffix)})
            extract_items(extract, source, "tracks", [(c["track"]["id"], c["input"]) for c in candidates], work)
            eligible = []
            marked, small = 0, 0
            for candidate in candidates:
                if has_generated_marker(candidate["input"]):
                    marked += 1
                elif not args.process_all_tracks and candidate["input"].stat().st_size <= args.minimum_subtitle_bytes:
                    small += 1
                else:
                    eligible.append(candidate)
            if marked or small:
                stage(f"Selected {len(eligible)} track(s); skipped {marked} already simplified and {small} below size threshold.")
            replacements = []
            if eligible:
                if args.level == 1 and not getattr(args, "font_dependencies_checked", False):
                    code = ("import PIL.ImageFont; import fontTools.ttLib; from PIL import features\n"
                            "if not features.check_feature('raqm'): import uharfbuzz")
                    try:
                        run([sys.executable, "-c", code], "font measurement dependencies",
                            capture=True, warnings_ok=False)
                    except RuntimeError as error:
                        raise RuntimeError("Font measurement needs Pillow, fonttools, and RAQM or uharfbuzz. "
                                           "Install with: python -m pip install Pillow fonttools uharfbuzz") from error
                    args.font_dependencies_checked = True
                fonts = work / "fonts"
                fonts.mkdir()
                if args.level == 1:
                    targets = font_targets(before, fonts)
                    extract_items(extract, source, "attachments", targets, fonts)
                    if not targets:
                        stage("Embedded fonts: [0/0]; using supplied or installed fonts.")
                stats_path = work / "stats.json"
                command = [sys.executable, str(engine), "--level", str(args.level), "--suffix", ".simple",
                           "--scroll-concurrency-limit", str(args.scroll_concurrency_limit),
                           "--stats-json", str(stats_path)]
                if args.level == 1:
                    for folder in [fonts, *args.fonts_dir]:
                        command.extend(["--fonts-dir", str(folder)])
                command.extend(["--", *[str(candidate["input"]) for candidate in eligible]])
                stage(f"Simplifying {len(eligible)} subtitle track(s)...")
                run(command, "subtitle simplification", warnings_ok=False)
                records = json.loads(stats_path.read_text(encoding="utf-8-sig"))["tracks"]
                for candidate in eligible:
                    matches = [record for record in records if Path(record["input"]).resolve() == candidate["input"]]
                    if len(matches) != 1 or matches[0].get("error") or not isinstance(matches[0].get("stats"), dict):
                        raise RuntimeError(f"Missing or invalid statistics for track {candidate['track']['id']}")
                    if not candidate["output"].is_file():
                        raise RuntimeError("Simplifier did not create its subtitle output")
                    record = matches[0]
                    stats = normalize_stats(record["stats"])
                    track_report = {"File": str(source), "Output": str(destination), "Track": candidate["track"]["id"],
                                    "Name": candidate["track"].get("properties", {}).get("track_name"),
                                    "Stats": stats, "Warnings": record.get("warnings", []), "SelectedForRemux": False}
                    report["Tracks"].append(track_report)
                    dropped = stats.get("scrolling_events_dropped")
                    if dropped is not None and dropped > 0:
                        message = (f"Dropped {dropped} events due to exceeding concurrent event limit "
                                   f"{stats.get('scrolling_concurrency_limit', 'unknown')} for scrolling text blocks.")
                        print(f"  WARNING: {source.name}, track {candidate['track']['id']}: {message}")
                        report["ScrollingDropWarnings"].append({
                            "File": str(source), "Track": candidate["track"]["id"], "Name": track_report["Name"],
                            "Events": dropped, "Limit": stats.get("scrolling_concurrency_limit"),
                            "Blocks": stats.get("scrolling_blocks_dropped"), "Peak": stats.get("scrolling_peak_after_reduction"),
                            "Message": message})
                    passed = True
                    if not args.process_all_tracks:
                        passed, _ = passed_reduction(stats, args.minimum_event_reduction_percent)
                    track_summary(candidate["track"], stats, passed)
                    if not passed:
                        continue
                    converted = identify(merge, candidate["output"])["tracks"]
                    if len(converted) != 1 or converted[0]["type"] != "subtitles":
                        raise RuntimeError("Invalid converted subtitle track")
                    candidate["codec"] = converted_codec(candidate["output"])
                    track_report["SelectedForRemux"] = True
                    replacements.append(candidate)
            destination.parent.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(prefix=".simplify-", suffix=".partial.mkv", dir=destination.parent)
            os.close(handle)
            partial = Path(name)
            if stamp(source) != source_stamp:
                raise RuntimeError("Source changed since scanning")
            if replacements:
                options, expected = build_remux(before, replacements, args.mode == "add", partial, source)
                option_file = work / "remux-options.json"
                option_file.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
                stage(f"Remuxing {len(replacements)} simplified track(s)...")
                run([merge, "@" + str(option_file)], "MKV remux")
                if not partial.stat().st_size:
                    raise RuntimeError("Remux did not create a nonempty MKV")
                stage("Verifying output...")
                verify_output(before, identify(merge, partial), expected)
            else:
                stage("Copying unchanged MKV...")
                shutil.copy2(source, partial)
                if partial.stat().st_size != source_stamp[0]:
                    raise RuntimeError("Incomplete unchanged-file copy")
            if stamp(source) != source_stamp:
                raise RuntimeError("Source changed during processing")
            if destination.exists() or destination.is_symlink():
                raise RuntimeError("Output appeared during processing; refusing to overwrite it")
            partial.rename(destination)
            partial = None
            outcome = "simplified" if replacements else "copied unchanged"
            print(f"  Saved ({outcome}).")
            return outcome
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def choice(prompt, options):
    print("\n" + prompt)
    for index, label in enumerate(options, 1):
        print(f"  {index}. {label}")
    while True:
        answer = input("Choose 1 or 2 (q to cancel): ").strip().lower()
        if answer in ("", "q"):
            raise EOFError
        if answer in ("1", "2"):
            return int(answer)
        print("Enter 1 or 2.")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("folder", nargs="?", type=Path, help="input folder (legacy positional syntax)")
    result.add_argument("-i", "--input-dir", type=Path, help="MKV folder (default: beside this script)")
    result.add_argument("-o", "--output-dir", type=Path, help="output folder (default: INPUT/output)")
    result.add_argument("-f", "--fonts-dir", action="append", type=Path, default=[], help="extra font folder; repeatable")
    result.add_argument("-r", "--recursive", action="store_true")
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--keep-originals", "--add-simplified-subtitles", dest="mode", action="store_const", const="add")
    mode.add_argument("--replace-originals", dest="mode", action="store_const", const="replace")
    policy = result.add_mutually_exclusive_group()
    policy.add_argument("--process-all-tracks", dest="process_all_tracks", action="store_const", const=True)
    policy.add_argument("--filtered", dest="process_all_tracks", action="store_const", const=False)
    result.add_argument("--minimum-subtitle-bytes", type=int, default=50000)
    result.add_argument("--minimum-event-reduction-percent", type=float, default=10)
    result.add_argument("--scroll-concurrency-limit", type=int, default=0, help="0 disables text dropping (default)")
    result.add_argument("--level", "--simplification-level", type=int, choices=(1, 2), default=1, help="2 is deprecated legacy mode")
    result.add_argument("--simplifier", type=Path, help="engine path (default: simplify_ass.py beside this script)")
    result.add_argument("--mkvtoolnix-dir", "--mkvtoolnix-folder", type=Path)
    result.add_argument("--report", "--report-path", type=Path, help="write a JSON run report")
    result.add_argument("-y", "--yes", action="store_true", help="run without prompts; default: keep originals, filtered tracks")
    return result


def main(argv=None):
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if args.folder is not None and args.input_dir is not None:
        argument_parser.error("Specify input positionally or with -i, not both.")
    if (args.minimum_subtitle_bytes < 0 or args.scroll_concurrency_limit < 0 or
            not math.isfinite(args.minimum_event_reduction_percent) or
            not 0 <= args.minimum_event_reduction_percent <= 100):
        argument_parser.error("Byte/scroll limits must be nonnegative; event reduction must be between 0 and 100.")
    root = (args.input_dir or args.folder or Path(__file__).resolve().parent).resolve()
    output = args.output_dir.resolve() if args.output_dir else root / "output"
    engine = args.simplifier.resolve() if args.simplifier else Path(__file__).resolve().parent / "simplify_ass.py"
    args.fonts_dir = [path.resolve() for path in args.fonts_dir]
    if args.mkvtoolnix_dir:
        args.mkvtoolnix_dir = args.mkvtoolnix_dir.resolve()
    report = {"Simplifier": str(engine), "Level": args.level, "Failures": 0,
              "ScrollConcurrencyLimit": args.scroll_concurrency_limit, "ScrollingDropWarnings": [], "Tracks": [], "Files": []}
    try:
        if not root.is_dir() or any(not folder.is_dir() for folder in args.fonts_dir):
            raise RuntimeError("Input and extra font folders must exist")
        if root.is_relative_to(output) or (output.exists() and not output.is_dir()):
            raise RuntimeError("Output must be a separate folder and cannot contain the input folder")
        if not engine.is_file() or engine.resolve() == Path(__file__).resolve():
            raise RuntimeError("Choose the simplify_ass.py engine, separate from this wrapper")
        files = find_files(root, output, args.recursive)
        if args.report:
            args.report = args.report.resolve()
            protected = {path.resolve() for path in files} | {output / path.relative_to(root) for path in files}
            protected.update([engine.resolve(), Path(__file__).resolve()])
            if args.report in protected or args.report.suffix.lower() in (".mkv", ".ass", ".ssa", ".py"):
                raise RuntimeError("Report must be separate from media and Python scripts")
        if not files:
            print(f"No MKV files found in {root}.")
            return 0
        merge = find_tool("mkvmerge", args.mkvtoolnix_dir)
        extract = find_tool("mkvextract", args.mkvtoolnix_dir)
        help_text = run([sys.executable, str(engine), "--help"], "engine options", capture=True, warnings_ok=False)
        for option in ("--stats-json", "--suffix", "--scroll-concurrency-limit"):
            if option not in help_text:
                raise RuntimeError(f"The simplifier must support {option}; use the current simplify_ass.py")
        if args.mode is None:
            args.mode = "add" if args.yes else ("add" if choice("Original subtitle tracks", [
                "Keep originals and add simplified subtitles", "Replace originals with simplified subtitles"]) == 1 else "replace")
        if args.process_all_tracks is None:
            args.process_all_tracks = False if args.yes else choice("ASS/SSA tracks to process", [
                f"Only tracks > {args.minimum_subtitle_bytes} bytes with > {args.minimum_event_reduction_percent:g}% fewer events",
                "All ASS/SSA tracks"]) == 2
        print(f"\nInput: {root}\nOutput: {output}\nFiles: {len(files)}")
        print("Original tracks: " + ("keep and add simplified copies" if args.mode == "add" else "replace qualifying tracks"))
        print("Track policy: " + ("all ASS/SSA" if args.process_all_tracks else "size and event-reduction thresholds"))
        print(f"Scrolling concurrency limit: {args.scroll_concurrency_limit} (0 disables text dropping)")
        if not args.yes and input("Proceed? (y/N): ").strip().lower() not in ("y", "yes"):
            print("Cancelled. No files changed.")
            return 0
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No files changed.")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}")
        return 2
    counts = Counter()
    try:
        for file_number, source in enumerate(files, 1):
            destination = output / source.relative_to(root)
            if destination.exists() or destination.is_symlink():
                print(f"Skipping existing output: {destination}")
                counts["skipped"] += 1
                report["Files"].append({"File": str(source), "Output": str(destination), "Status": "skipped"})
                continue
            print(f"\n[{file_number}/{len(files)}] {source.relative_to(root)}", flush=True)
            file_report = {"File": str(source), "Output": str(destination)}
            try:
                outcome = process_file(source, destination, args, merge, extract, engine, report)
                counts[outcome] += 1
                file_report["Status"] = outcome
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                print(f"  ERROR: {error}")
                counts["failed"] += 1
                report["Failures"] += 1
                file_report.update(Status="failed", Error=str(error))
            report["Files"].append(file_report)
    except KeyboardInterrupt:
        print("\nStopped. Completed outputs remain; the current partial output was discarded.")
        report["Failures"] += 1
    finally:
        for limit in sorted({item["Limit"] for item in report["ScrollingDropWarnings"]}, key=str):
            warnings = [item for item in report["ScrollingDropWarnings"] if item["Limit"] == limit]
            print(f"WARNING: RUN SUMMARY: {sum(item['Events'] for item in warnings)} scrolling events dropped "
                  f"in {len(warnings)} track(s), limit {limit}.")
        if args.report:
            try:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"Report: {args.report}")
            except OSError as error:
                print(f"ERROR writing report: {error}")
                report["Failures"] += 1
    print("\nFinished: " + ", ".join(f"{value} {key}" for key, value in counts.items()))
    return int(bool(report["Failures"]))


def cli(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        return main(arguments)
    finally:
        if sys.platform == "win32" and not arguments and sys.stdin.isatty():
            try:
                input("\nPress Enter to close: ")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(cli())
