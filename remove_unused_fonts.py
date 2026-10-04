#!/usr/bin/env python3
"""Keep MKV font attachments referenced by remaining subtitles. Python 3.9+."""
import argparse
import collections
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata


def normalize(name):
    return " ".join(unicodedata.normalize("NFC", name).strip().lstrip("@").split()).casefold()


def find_tool(name):
    executable = name + (".exe" if os.name == "nt" else "")
    candidates = [Path(__file__).resolve().parent / executable]
    if os.name == "nt":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(variable):
                candidates.append(Path(os.environ[variable]) / "MKVToolNix" / executable)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    result = shutil.which(executable)
    if not result:
        raise RuntimeError(f"Cannot find {executable}. Install MKVToolNix or put its tools on PATH.")
    return result


def run(command, log):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8-sig", errors="replace")
    log.append(result.stdout)
    if result.returncode not in (0, 1):  # MKVToolNix: 1 means warning, 2 means error.
        raise RuntimeError(f"{Path(command[0]).name} failed:\n{result.stdout.strip()}")
    if result.returncode == 1:
        print("  MKVToolNix returned a warning.")
    return result.stdout


def identify(merge, source, log):
    data = json.loads(run([merge, "-J", str(source)], log))
    if not data.get("container", {}).get("recognized") or not data["container"].get("supported"):
        raise RuntimeError("Input container is not recognized or supported.")
    return data


def ass_fonts(path):
    """Read only event-used styles, named resets and inline font overrides."""
    styles = {}
    events = []
    section = ""
    fields = None
    used = set()
    with path.open(encoding="utf-8-sig", errors="strict") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                section, fields = line.casefold(), None
                continue
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key = key.strip().casefold()
            if section in ("[v4+ styles]", "[v4 styles]"):
                if key == "format":
                    fields = [x.strip().casefold() for x in value.split(",")]
                elif key == "style":
                    if not fields or "name" not in fields or "fontname" not in fields:
                        raise ValueError("Missing/unsupported ASS style format.")
                    values = value.lstrip().split(",", len(fields) - 1)
                    if len(values) != len(fields):
                        raise ValueError("Malformed ASS style.")
                    row = dict(zip(fields, values))
                    styles[row["name"].strip().casefold()] = row["fontname"].strip()
            elif section == "[events]":
                if key == "format":
                    fields = [x.strip().casefold() for x in value.split(",")]
                elif key == "dialogue":
                    if not fields or fields[-1] != "text" or "style" not in fields:
                        raise ValueError("Missing/unsupported ASS event format.")
                    values = value.lstrip().split(",", len(fields) - 1)
                    if len(values) != len(fields):
                        raise ValueError("Malformed ASS dialogue.")
                    row = dict(zip(fields, values))
                    events.append((row["style"].strip(), row["text"]))
    def add_style(name):
        font = styles.get(name.casefold())
        if font is None:
            # ASS renderers can fall back to Default for an undefined style.
            font = styles.get("default")
        if not font:
            raise ValueError(f"Cannot resolve ASS style {name!r}.")
        used.add(font)
    for style, text in events:
        blocks = re.findall(r"\{([^{}]*)\}", text)
        overrides = "".join(blocks)
        # A static rectangular clip with no area cannot display any text.
        # Do not infer invisibility if clipping is animated, inverted or repeated.
        clips = re.findall(r"\\i?clip\s*\(", overrides)
        rectangle = re.search(
            r"\\clip\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", overrides)
        if len(clips) == 1 and rectangle and not re.search(r"\\t\s*\(", overrides):
            x1, y1, x2, y2 = map(int, rectangle.groups())
            if x1 == x2 or y1 == y2:
                continue
        add_style(style)
        for block in blocks:
            # Also catches tags within transforms; retaining these fonts is conservative.
            for match in re.finditer(r"\\fn([^\\{}()]*)", block):
                font = match.group(1).strip()
                if font:
                    used.add(font)
            for match in re.finditer(r"\\r([^\\{}()]*)", block):
                add_style(match.group(1).strip() or style)
    return used


def font_names(path):
    from fontTools.ttLib import TTCollection, TTFont
    with path.open("rb") as handle:
        collection = handle.read(4) == b"ttcf"
    container = TTCollection(str(path), lazy=True) if collection else TTFont(str(path), lazy=True)
    try:
        faces = container.fonts if collection else [container]
        names = set()
        for face in faces:
            # Ask fontTools to parse all tables, not just the family name table.
            face.ensureDecompiled()
            face_names = set()
            for record in face["name"].names:
                # Family, full, PostScript, typographic and WWS family names; all languages.
                if record.nameID in (1, 4, 6, 16, 21):
                    value = record.toUnicode().strip()
                    if value:
                        face_names.add(value)
            if not face_names:
                raise ValueError("A font face has no readable names.")
            names.update(face_names)
        return names
    finally:
        container.close()


def text_hint(path):
    """Describe possible text content; never use this heuristic to delete files."""
    data = path.read_bytes()
    if not data:
        return "empty attachment"
    encodings = ["utf-8-sig"]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    elif len(data) % 2 == 0:
        # Without a BOM, try UTF-16 only when alternating NUL bytes suggest it.
        for parity, encoding in ((1, "utf-16-le"), (0, "utf-16-be")):
            part = data[parity::2]
            if part and part.count(0) / len(part) > 0.2:
                encodings.append(encoding)
    for encoding in encodings:
        try:
            text = data.decode(encoding, errors="strict")
        except UnicodeError:
            continue
        if text and "\x00" not in text:
            printable = sum(c.isprintable() or c in "\r\n\t" for c in text)
            if printable / len(text) >= 0.98:
                return f"appears to be text ({encoding.replace('-sig', '').upper()})"
    return "does not clearly appear to be UTF-8/UTF-16 text"


def confirm_invalid(invalid, log, preview):
    print("  Attachments that could not be validated as fonts:")
    for attachment, error, hint in invalid:
        label = f"{attachment['id']}: {attachment.get('file_name', '(unnamed)')}"
        print(f"    {label} - {hint}\n      {error}")
        log.append(f"FONT CHECK FAILED {label} | {hint} | {error}\n")
    if preview:
        print("  Preview: your answer only affects the removal plan.")
    while True:
        try:
            answer = input(f"  Remove these {len(invalid)} attachments from the output copy? [y/N] ").strip().casefold()
        except EOFError:
            answer = "n"
            print("\n  No input available; keeping these attachments.")
        if answer in ("", "n", "no", "y", "yes"):
            remove = answer in ("y", "yes")
            log.append("Failed font checks: user chose " + ("REMOVE\n" if remove else "KEEP\n"))
            return {a["id"] for a, error, hint in invalid} if remove else set()
        print("  Enter Y to remove them or N to keep them.")


def inspect_fonts(source, merge, extract):
    log = [f"Input: {source}\n"]
    stat = source.stat()
    before = identify(merge, source, log)
    fonts = [a for a in before.get("attachments", []) if is_font(a)]
    readable, invalid = [], []
    if fonts:
        with tempfile.TemporaryDirectory(prefix="mkv-font-check-") as temp:
            paths = [(a, Path(temp) / f"attachment-{a['id']}.font") for a in fonts]
            run([extract, str(source), "attachments"] + [f"{a['id']}:{p}" for a, p in paths], log)
            print(f"  Checking {len(fonts)} font attachments...")
            for attachment, path in paths:
                try:
                    readable.append((attachment, font_names(path)))
                except Exception as error:
                    hint = text_hint(path)
                    invalid.append((attachment, str(error), hint))
                    log.append(f"FONT CHECK FAILED {attachment['id']}: "
                               f"{attachment.get('file_name', '(unnamed)')} | {hint} | {error}\n")
    print(f"  Font check: {len(readable)} passed, {len(invalid)} failed.")
    return {"before": before, "readable": readable, "invalid": invalid, "log": log,
            "signature": (stat.st_size, stat.st_mtime_ns)}


def choose_removals(inspections, preview):
    affected = [(source, scan) for source, scan in inspections.items() if scan["invalid"]]
    choices = {source: set() for source in inspections}
    if not affected:
        print("\nScan complete. No font attachments failed validation.")
        return choices
    count = sum(len(scan["invalid"]) for source, scan in affected)
    print(f"\nScan complete. {count} attachments failed validation in {len(affected)} MKVs:")
    for source, scan in affected:
        print("\n  " + source.name)
        for attachment, error, hint in scan["invalid"]:
            print(f"    {attachment['id']}: {attachment.get('file_name', '(unnamed)')} - {hint}\n      {error}")
    if preview:
        print("\nPreview: your choices only affect removal plans; no MKVs will be created.")
    print("\n  1. Remove all listed attachments from all affected MKVs")
    print("  2. Choose separately for each affected MKV")
    print("  3. Keep all listed attachments")
    while True:
        try:
            answer = input("Choose [1/2/3, default 3]: ").strip()
        except EOFError:
            answer = "3"
            print("\nNo input available; keeping all listed attachments.")
        if answer in ("", "1", "2", "3"):
            break
        print("Enter 1, 2 or 3.")
    for source, scan in affected:
        if answer == "1":
            choices[source] = {a["id"] for a, error, hint in scan["invalid"]}
            scan["log"].append("Failed font checks: user chose REMOVE ALL\n")
        elif answer == "2":
            print("\n" + source.name)
            choices[source] = confirm_invalid(scan["invalid"], scan["log"], preview)
        else:
            scan["log"].append("Failed font checks: user chose KEEP ALL\n")
    return choices


def srt_fonts(path):
    class FontReader(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get("style"):
                raise ValueError("SRT contains inline CSS; cannot safely resolve fonts.")
            if tag == "font" and attrs.get("face"):
                used.add(attrs["face"].strip())
        handle_startendtag = handle_starttag
    used = set()
    reader = FontReader()
    reader.feed(path.read_text(encoding="utf-8-sig", errors="strict"))
    reader.close()
    return used


def is_font(attachment):
    suffix = Path(attachment.get("file_name", "")).suffix.casefold()
    mime = attachment.get("content_type", "").casefold()
    return suffix in (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2", ".pfa", ".pfb") or "font" in mime


def verify(before, after, kept):
    # Track order, UIDs, codec, language, names and important flags must survive the remux.
    keys = ("uid", "codec_id", "track_name", "language", "language_ietf", "default_track",
            "forced_track", "enabled_track", "hearing_impaired", "visual_impaired",
            "text_descriptions", "original", "commentary")
    def tracks(data):
        return [(t["type"], tuple(t.get("properties", {}).get(k) for k in keys))
                for t in data.get("tracks", [])]
    if tracks(before) != tracks(after):
        raise RuntimeError("Output validation failed: track order or properties changed.")
    def attachments(items):
        return collections.Counter((a.get("file_name"), a.get("size"), a.get("description", ""))
                                   for a in items)
    if attachments(kept) != attachments(after.get("attachments", [])):
        raise RuntimeError("Output validation failed: attachment list differs from plan.")


def process(source, output_dir, merge, extract, preview, write_logs=False,
            inspection=None, approved_removals=None):
    log = list(inspection["log"]) if inspection else [f"Input: {source}\n"]
    report = output_dir / (source.name + ".fonts.txt")
    destination = output_dir / source.name
    partial = None
    try:
        if destination.exists():
            print("  Skipped: output file already exists.")
            return "skipped"
        if inspection is None:
            inspection = inspect_fonts(source, merge, extract)
            log = list(inspection["log"])
        stat = source.stat()
        if (stat.st_size, stat.st_mtime_ns) != inspection["signature"]:
            raise RuntimeError("Input changed since the font scan. Rerun the script to scan it again.")
        before = inspection["before"]
        attachments = before.get("attachments", [])
        fonts = [a for a in attachments if is_font(a)]
        if not fonts:
            print("  No font attachments; no copy needed.")
            log.append("No font attachments; no copy created.\n")
            return "unchanged"
        tracks = [t for t in before.get("tracks", []) if t["type"] == "subtitles"]
        used = set()
        blockers = []
        with tempfile.TemporaryDirectory(prefix="mkv-fonts-") as temp:
            temp = Path(temp)
            readable, invalid = inspection["readable"], inspection["invalid"]
            if approved_removals is None:
                approved_removals = confirm_invalid(invalid, log, preview) if invalid else set()
            text_tracks = []
            for track in tracks:
                codec = track.get("properties", {}).get("codec_id", "")
                if codec in ("S_TEXT/ASS", "S_TEXT/SSA"):
                    text_tracks.append((track, temp / f"track-{track['id']}.ass", ass_fonts))
                elif codec == "S_TEXT/UTF8":
                    text_tracks.append((track, temp / f"track-{track['id']}.srt", srt_fonts))
                elif codec in ("S_HDMV/PGS", "S_VOBSUB", "S_DVBSUB"):
                    continue  # Bitmap subtitles do not use font attachments.
                else:
                    # WebVTT and other formats may contain CSS; do not guess.
                    blockers.append(f"Track {track['id']}: {codec or 'unknown codec'} not analyzed")
            if text_tracks:
                run([extract, str(source), "tracks"] +
                    [f"{t['id']}:{p}" for t, p, reader in text_tracks], log)
                for track, path, reader in text_tracks:
                    try:
                        names = reader(path)
                        used.update(names)
                        log.append(f"Subtitle track {track['id']}: {', '.join(sorted(names)) or '(no dialogue)'}\n")
                    except Exception as error:
                        blockers.append(f"Track {track['id']}: cannot analyze: {error}")
            log.append("Referenced fonts: " + (", ".join(sorted(used)) or "(none)") + "\n")
            if blockers:
                log.extend("KEEP REMAINING FONTS: " + reason + "\n" for reason in blockers)
                print("  Keeping remaining fonts: a subtitle track could not be analyzed.")
                for reason in blockers:
                    print("    " + reason)
            wanted = {normalize(n) for n in used}
            matched = set()
            unused_ids = set()
            for attachment, names in readable:
                label = f"{attachment['id']}: {attachment.get('file_name', '(unnamed)')}"
                aliases = {normalize(n) for n in names}
                hits = aliases & wanted
                matched.update(hits)
                if not hits:
                    unused_ids.add(attachment["id"])
                log.append(f"FONT {label} | names: {', '.join(sorted(names))}\n")
            missing = wanted - matched
            if missing:
                # Do not discard potential fallback fonts when requested fonts are missing.
                log.append("KEEP REMAINING FONTS: no attachment matched: " + ", ".join(sorted(missing)) + "\n")
                print("  Keeping remaining fonts: no attachment matched " + ", ".join(sorted(missing)))
            remove_ids = approved_removals | (unused_ids if not blockers and not missing else set())
            for attachment in fonts:
                log.append(f"{'REMOVE' if attachment['id'] in remove_ids else 'KEEP'} "
                           f"{attachment['id']}: {attachment.get('file_name', '(unnamed)')}\n")
            kept = [a for a in attachments if a["id"] not in remove_ids]
            removed_bytes = sum(a.get("size", 0) for a in fonts if a["id"] in remove_ids)
            message = f"Remove {len(remove_ids)}/{len(fonts)} fonts ({removed_bytes / 1048576:.2f} MiB)."
            print("  " + message)
            log.append(message + "\n")
            if not remove_ids:
                log.append("Nothing to remove; no copy created.\n")
                return "unchanged"
            if preview:
                log.append("Preview only; no MKV created.\n")
                return "preview"
            # Use an option file to avoid Windows' command line length limit.
            descriptor, name = tempfile.mkstemp(prefix=".fonts-", suffix=".partial.mkv", dir=output_dir)
            os.close(descriptor)
            partial = Path(name)
            options = ["-o", str(partial)]
            order = before.get("tracks", [])
            if order:
                options += ["--track-order", ",".join(f"0:{t['id']}" for t in order)]
            options += ["--attachments", "!" + ",".join(str(i) for i in sorted(remove_ids)), str(source)]
            option_file = temp / "merge-options.json"
            option_file.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
            run([merge, "@" + str(option_file)], log)
            after = identify(merge, partial, log)
            verify(before, after, kept)
            if destination.exists():
                raise RuntimeError("Output appeared during processing; refusing to overwrite it.")
            partial.rename(destination)
            partial = None
            print("  Saved: " + str(destination))
            log.append(f"Saved and validated: {destination}\n")
            return "written"
    except Exception as error:
        print("  ERROR: " + str(error))
        log.append("ERROR: " + str(error) + "\n")
        return "failed"
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
        if write_logs:
            report.write_text("\n".join(log), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--preview", action="store_true", help="Analyze without remuxing")
    parser.add_argument("--log", action="store_true", help="Write per-file font reports (off by default)")
    args = parser.parse_args()
    try:
        from fontTools.ttLib import TTFont  # noqa: F401
        merge, extract = find_tool("mkvmerge"), find_tool("mkvextract")
    except ImportError:
        print("Install the required font reader once: python -m pip install fonttools")
        return 2
    except RuntimeError as error:
        print(error)
        return 2
    directory = args.directory.resolve()
    if not directory.is_dir():
        print("Input directory does not exist.")
        return 2
    sources = sorted((p for p in directory.iterdir() if p.is_file() and p.suffix.casefold() == ".mkv"),
                     key=lambda p: p.name.casefold())
    if not sources:
        print("No MKV files found in " + str(directory))
        return 0
    output = directory / "output"
    output.mkdir(exist_ok=True)
    counts = collections.Counter()
    inspections = {}
    print("Scanning all MKVs before asking about failed font checks...")
    for index, source in enumerate(sources, 1):
        print(f"\n[Scan {index}/{len(sources)}] {source.name}")
        if (output / source.name).exists():
            print("  Skipped: output file already exists.")
            counts["skipped"] += 1
            continue
        try:
            inspections[source] = inspect_fonts(source, merge, extract)
        except Exception as error:
            print("  ERROR during font scan: " + str(error))
            counts["failed"] += 1
            if args.log:
                (output / (source.name + ".fonts.txt")).write_text(
                    f"Input: {source}\nERROR during font scan: {error}\n", encoding="utf-8")
    choices = choose_removals(inspections, args.preview)
    for index, (source, inspection) in enumerate(inspections.items(), 1):
        print(f"\n[Process {index}/{len(inspections)}] {source.name}")
        counts[process(source, output, merge, extract, args.preview, args.log,
                       inspection, choices[source])] += 1
    print("\nFinished: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print("Output: " + str(output))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(130)
