#!/usr/bin/env python3
"""Sync MKV fonts: remove unused attachments and optionally add missing fonts. Python 3.9+."""
import argparse
import collections
import hashlib
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


def run(command, log, cwd=None):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8-sig", errors="replace", cwd=cwd)
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


def timestamp_seconds(value):
    match = re.fullmatch(r"\s*(\d+):(\d+):(\d+)[.,](\d+)\s*", value)
    if not match:
        return None
    hours, minutes, seconds, fraction = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(fraction) / 10 ** len(fraction)


def format_timestamp(seconds):
    if seconds is None:
        return "timestamp unavailable"
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{fraction:02d}"


def record_font(usage, font, timestamp):
    if font not in usage or (timestamp is not None and
                            (usage[font] is None or timestamp < usage[font])):
        usage[font] = timestamp


def variant_label(weight, italic):
    weights = {100: "thin", 200: "extra light", 300: "light", 400: "regular",
               500: "medium", 600: "semibold", 700: "bold", 800: "extra bold", 900: "black"}
    label = weights.get(weight, f"weight {weight}")
    return label + (" italic" if italic else "")


def requirement_key(font, weight, italic):
    return normalize(font), weight, bool(italic)


def ass_tags(block):
    """Yield font-relevant tags, preserving transform boundaries and tag order."""
    position = 0
    while position < len(block):
        position = block.find("\\", position)
        if position < 0:
            return
        position += 1
        match = re.match(r"t\s*\(", block[position:])
        if match:
            start = position + match.end()
            end, depth = start, 1
            while end < len(block) and depth:
                depth += (block[end] == "(") - (block[end] == ")")
                end += 1
            if depth:
                raise ValueError("Unclosed ASS transform.")
            yield "t", block[start:end - 1]
            position = end
            continue
        end = block.find("\\", position)
        if end < 0:
            end = len(block)
        token = block[position:end].strip()
        position = end
        if token.startswith("fn"):
            yield "fn", token[2:].strip()
        elif token.startswith("r"):
            yield "r", token[1:].strip()
        elif re.fullmatch(r"[bip]\s*[-+]?\d*\s*", token):
            yield token[0], token[1:].strip()


def ass_fonts(path, with_usage=False):
    """Track font, weight and italic state for event text and transform endpoints."""
    styles = {}
    events = []
    section = ""
    fields = None
    used = {}
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
                    styles[row["name"].strip().casefold()] = (
                        row["fontname"].strip(),
                        700 if int(row.get("bold", "0")) else 400,
                        bool(int(row.get("italic", "0"))))
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
                    events.append((row["style"].strip(), row["text"],
                                   timestamp_seconds(row.get("start", ""))))
    def resolve_style(name):
        state = styles.get(name.casefold())
        if state is None:
            # ASS renderers can fall back to Default for an undefined style.
            state = styles.get("default")
        if not state:
            raise ValueError(f"Cannot resolve ASS style {name!r}.")
        return state
    for style, text, timestamp in events:
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
        base = resolve_style(style)
        reset = base
        states, drawing = {base}, 0
        def apply(block, states, reset, drawing):
            for tag, value in ass_tags(block):
                if tag == "t":
                    targets, _, _ = apply(value, set(states), reset, drawing)
                    states |= targets  # Animation can use both endpoint faces.
                elif tag == "r":
                    reset = resolve_style(value or style)
                    states, drawing = {reset}, 0
                elif tag == "fn":
                    states = {(value or reset[0], w, i) for _, w, i in states}
                elif tag == "b":
                    weight = int(value) if value else reset[1]
                    weight = 700 if weight in (1, -1) else 400 if weight == 0 else max(1, min(1000, weight))
                    states = {(f, weight, i) for f, _, i in states}
                elif tag == "i":
                    italic = bool(int(value)) if value else reset[2]
                    states = {(f, w, italic) for f, w, _ in states}
                elif tag == "p":
                    drawing = int(value or 0)
            return states, reset, drawing
        for piece in re.split(r"(\{[^{}]*\})", text):
            if piece.startswith("{") and piece.endswith("}"):
                states, reset, drawing = apply(piece[1:-1], states, reset, drawing)
            elif piece.strip() and not drawing:
                for state in states:
                    record_font(used, state, timestamp)
    return used if with_usage else {font for font, _, _ in used}


def font_faces(path):
    from fontTools.ttLib import TTCollection, TTFont
    with path.open("rb") as handle:
        collection = handle.read(4) == b"ttcf"
    container = TTCollection(str(path), lazy=True) if collection else TTFont(str(path), lazy=True)
    try:
        faces = container.fonts if collection else [container]
        metadata = []
        for face in faces:
            # Ask fontTools to parse all tables, not just the family name table.
            face.ensureDecompiled()
            face_names, families, fullnames = set(), set(), set()
            for record in face["name"].names:
                # Family, full, PostScript, typographic and WWS family names; all languages.
                if record.nameID in (1, 4, 6, 16, 21):
                    value = record.toUnicode().strip()
                    if value:
                        face_names.add(value)
                        (families if record.nameID in (1, 16, 21) else fullnames).add(normalize(value))
            if not face_names:
                raise ValueError("A font face has no readable names.")
            os2 = face.get("OS/2")
            head = face.get("head")
            post = face.get("post")
            flags = getattr(head, "macStyle", 0)
            selection = getattr(os2, "fsSelection", 0)
            weight = getattr(os2, "usWeightClass", 700 if flags & 1 else 400)
            italic = bool(selection & 1 or flags & 2 or getattr(post, "italicAngle", 0))
            metadata.append({"names": face_names, "families": families, "fullnames": fullnames,
                             "weight": int(weight), "italic": italic,
                             "variable": "fvar" in face,
                             "aliasable": os2 is not None and head is not None})
        return metadata
    finally:
        container.close()


def font_names(path):
    return set().union(*(face["names"] for face in font_faces(path)))


def face_matches(face, key):
    name, weight, italic = key
    # An explicit full/PostScript name identifies its face, even with bold off.
    if name in face["fullnames"] and name not in face["families"]:
        return True
    return name in face["families"] and (face["weight"], face["italic"]) == (weight, italic)


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
            run_extract(extract, source, "attachments", [(a["id"], p) for a, p in paths], log)
            print(f"  Checking {len(fonts)} font attachments...")
            for attachment, path in paths:
                try:
                    readable.append((attachment, font_faces(path)))
                except Exception as error:
                    hint = text_hint(path)
                    invalid.append((attachment, str(error), hint))
                    log.append(f"FONT CHECK FAILED {attachment['id']}: "
                               f"{attachment.get('file_name', '(unnamed)')} | {hint} | {error}\n")
    print(f"  Font check: {len(readable)} passed, {len(invalid)} failed.")
    scan = {"before": before, "readable": readable, "invalid": invalid, "log": log,
            "signature": (stat.st_size, stat.st_mtime_ns)}
    scan.update(analyze_subtitles(source, before, readable, extract, log))
    return scan


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


def srt_fonts(path, with_usage=False):
    used = {}
    class FontReader(HTMLParser):
        def __init__(self):
            super().__init__()
            self.state = (None, 400, False)
            self.stack = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get("style"):
                raise ValueError("SRT contains inline CSS; cannot safely resolve fonts.")
            if tag not in ("font", "b", "strong", "i", "em"):
                return
            self.stack.append((tag, self.state))
            font, weight, italic = self.state
            if tag == "font" and attrs.get("face"):
                font = attrs["face"].strip()
            elif tag in ("b", "strong"):
                weight = 700
            elif tag in ("i", "em"):
                italic = True
            self.state = font, weight, italic
        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    self.state = self.stack[index][1]
                    del self.stack[index:]
                    break
        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)
        def handle_data(self, text):
            if self.state[0] and text.strip():
                record_font(used, self.state, self.timestamp)
    for cue in re.split(r"\r?\n\s*\r?\n", path.read_text(encoding="utf-8-sig", errors="strict")):
        reader = FontReader()
        timing = re.search(r"(\d+:\d+:\d+[.,]\d+)\s*-->", cue)
        reader.timestamp = timestamp_seconds(timing.group(1)) if timing else None
        reader.feed(cue)
        reader.close()
    return used if with_usage else {font for font, _, _ in used}


def subtitle_label(track):
    properties = track.get("properties", {})
    name = properties.get("track_name")
    if name:
        return name
    language = properties.get("language_ietf") or properties.get("language") or "unknown language"
    return f"<unnamed subtitle, {language}>"


def analyze_subtitles(source, before, readable, extract, log):
    references, blockers = {}, []
    with tempfile.TemporaryDirectory(prefix="mkv-subtitle-fonts-") as temp:
        text_tracks = []
        for track in before.get("tracks", []):
            if track["type"] != "subtitles":
                continue
            codec = track.get("properties", {}).get("codec_id", "")
            if codec in ("S_TEXT/ASS", "S_TEXT/SSA", "S_TEXT/UTF8"):
                ass = codec != "S_TEXT/UTF8"
                path = Path(temp) / f"track-{track['id']}.{'ass' if ass else 'srt'}"
                text_tracks.append((track, path, ass_fonts if ass else srt_fonts))
            elif codec not in ("S_HDMV/PGS", "S_VOBSUB", "S_DVBSUB"):
                blockers.append(f"{subtitle_label(track)}: {codec or 'unknown codec'} not analyzed")
        if text_tracks:
            # Relative extraction names avoid drive-letter colons in MKVToolNix's ID:path syntax.
            run_extract(extract, source, "tracks", [(t["id"], p) for t, p, reader in text_tracks], log)
            for track, path, reader in text_tracks:
                try:
                    usage = reader(path, with_usage=True)
                    label = subtitle_label(track)
                    summary = ", ".join(f"{f} [{variant_label(w, i)}]" for f, w, i in sorted(usage))
                    log.append(f"Subtitle {label}: {summary or '(no font references)'}\n")
                    for (font, weight, italic), first in usage.items():
                        references.setdefault(requirement_key(font, weight, italic), []).append(
                            {"font": font.lstrip("@"), "weight": weight, "italic": italic, "subtitle": label,
                             "language": track.get("properties", {}).get("language", ""),
                             "first": first})
                except Exception as error:
                    blockers.append(f"{subtitle_label(track)}: cannot analyze: {error}")
    wanted = set(references)
    matched, unused_ids = set(), set()
    variable_requests, static_matches = set(), set()
    wanted_names = {key[0] for key in wanted}
    available = {key: set() for key in wanted}
    for attachment, faces in readable:
        names = set().union(*(face["names"] for face in faces))
        matched.update(key for key in wanted if any(face_matches(face, key) for face in faces))
        static_matches.update(key for key in wanted if any(
            not face.get("variable", False) and face_matches(face, key) for face in faces))
        variable_requests.update(key for key in wanted if (key[1] >= 700 or key[2]) and any(
            face.get("variable", False) and
            (key[0] in face["families"] or face_matches(face, key)) for face in faces))
        for key in wanted:
            available[key].update((face["weight"], face["italic"]) for face in faces
                                  if key[0] in face["families"])
        # Keep all faces of referenced names, including potential renderer fallbacks.
        if not ({normalize(n) for n in names} & wanted_names):
            unused_ids.add(attachment["id"])
        log.append(f"FONT {attachment['id']}: {attachment.get('file_name', '(unnamed)')} | "
                   f"names: {', '.join(sorted(names))}\n")
    unmatched = wanted - matched
    variable_warnings = variable_requests - static_matches
    warnings = {key: tuple(sorted(available[key])) for key in unmatched - variable_warnings
                if available[key]}
    return {"references": references, "missing": unmatched - warnings.keys() - variable_warnings,
            "variable_warnings": variable_warnings,
            "variant_warnings": warnings,
            "unused_ids": unused_ids, "blockers": blockers}


def run_extract(extract, source, mode, items, log):
    if not items:
        return
    directory = items[0][1].parent
    command = [extract, str(source), mode] + [f"{ident}:{path.name}" for ident, path in items]
    return run(command, log, cwd=str(directory))


def local_font_catalog(directory, cache):
    catalog = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_file() or path.suffix.casefold() not in (".ttf", ".otf", ".ttc", ".otc"):
            continue
        stat = path.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        cached = cache.get(path)
        if cached is None or cached[0] != signature:
            try:
                faces = font_faces(path)
                names = set().union(*(face["names"] for face in faces))
                with path.open("rb") as handle:
                    collection = handle.read(4) == b"ttcf"
                cached = (signature, names, None, collection, faces)
            except Exception as error:
                cached = (signature, set(), str(error))
            cache[path] = cached
        if cached[2]:
            print(f"  Local font skipped: {path.name}: {cached[2]}")
        else:
            catalog.append({"path": path, "names": cached[1], "signature": signature, "collection": cached[3], "faces": cached[4]})
    return catalog


def scan_local_fonts(inspections):
    """Finish local-font validation and exact matching before any prompts."""
    catalogs, cache = {}, {}
    for source, scan in inspections.items():
        if source.parent not in catalogs:
            catalogs[source.parent] = local_font_catalog(source.parent, cache)
        catalog = catalogs[source.parent]
        scan["local_fonts"] = catalog
        scan["local_matches"] = {
            key: [item for item in catalog if any(face_matches(face, key) for face in item["faces"])]
            for key in scan["missing"] | scan.get("variant_warnings", {}).keys()}


def display_missing(source, scan):
    print("\n" + source.name)
    print("  Font references without a matching attachment:")
    for key in sorted(scan["missing"]):
        references = scan["references"][key]
        print("    Font name: " + references[0]["font"])
        print("      Requested variant: " + variant_label(key[1], key[2]))
        for reference in references:
            print(f"      Subtitle: {reference['subtitle']}")
            print(f"      First referenced event: {format_timestamp(reference['first'])}")


def choose_substitute(requested, key, catalog):
    # Every choice represents one required face, not a whole font family.
    weight, italic = key[1:]
    candidates = [item for item in catalog if not item["collection"] and item["faces"][0]["aliasable"]]
    def matching(item):
        face = item["faces"][0]
        return (face["weight"], face["italic"]) == (weight, italic)
    candidates.sort(key=lambda item: (not matching(item), item["path"].name.casefold()))
    print(f"\n  Font name: {requested}; requested variant: {variant_label(weight, italic)}")
    print("    0. Skip replacement (use the player's fallback)")
    for index, item in enumerate(candidates, 1):
        face = item["faces"][0]
        status = "matching variant" if matching(item) else "VARIANT MISMATCH"
        print(f"    {index}. {item['path'].name} [{variant_label(face['weight'], face['italic'])}; {status}] "
              f"({', '.join(sorted(item['names']))})")
    if not candidates:
        print("  No readable single-face TTF/OTF files available; skipping replacement.")
        return []
    print("  This selection applies to all MKVs in this batch missing this font and variant.")
    while True:
        try:
            selection = input("  Choose one file number [default 0]: ").strip() or "0"
        except EOFError:
            selection = "0"
        try:
            index = int(selection)
            if not 0 <= index <= len(candidates):
                raise ValueError
        except ValueError:
            print("  Enter one valid file number, or 0 to skip.")
            continue
        if index == 0:
            return []
        item = candidates[index - 1]
        if not matching(item):
            face = item["faces"][0]
            print(f"  Variant mismatch: selected {variant_label(face['weight'], face['italic'])}; "
                  f"requested {variant_label(weight, italic)}.")
            print("  The copy's metadata will be relabelled, but its glyph shapes will stay unchanged.")
            print("  This can prevent libass from synthesizing the requested bold or italic appearance.")
            try:
                confirmed = input("  Use this mismatched variant anyway? [y/N]: ").strip().casefold()
            except EOFError:
                return []
            if confirmed not in ("y", "yes"):
                continue
        return [item]


def supply_font(key, scan, choices):
    """Resolve and remember one final addition/skip choice, including exact files."""
    requested = scan["references"][key][0]["font"]
    if key in choices:
        selected = choices[key]
        print(f"  Reusing batch font choice for {requested} [{variant_label(key[1], key[2])}]: " +
              (", ".join(item["path"].name for item in selected) if selected else "skip addition"))
    else:
        exact = scan["local_matches"][key]
        if exact:
            print(f"  Exact match for {requested} [{variant_label(key[1], key[2])}]: {exact[0]['path'].name}")
            selected = [dict(exact[0], requested=requested, weight=key[1], italic=key[2], substitute=False)]
        else:
            selected = [dict(item, requested=requested, weight=key[1], italic=key[2], substitute=True)
                        for item in choose_substitute(requested, key, scan["local_fonts"])]
        choices[key] = selected
    if not selected:
        scan["log"].append(f"NO ADDITION {requested} [{variant_label(key[1], key[2])}]: player's fallback\n")
    return [dict(item, requested=requested) for item in selected]


def choose_variant(key, scan, decisions):
    requested = scan["references"][key][0]["font"]
    wanted = variant_label(key[1], key[2])
    available = ", ".join(variant_label(w, i) for w, i in scan["variant_warnings"][key])
    print("\n  Warning: the font is included, but its requested native variant is not.")
    for reference in scan["references"][key]:
        print(f"    Subtitle track: {reference['subtitle']}")
        print(f"    Requires font: {requested} {wanted}; included: {requested} {available}.")
        print(f"    First referenced event: {format_timestamp(reference['first'])}")
    if key in decisions:
        print("  Reusing batch variant choice: " +
              ("add requested variant" if decisions[key] else "let libass use the included variant"))
        return decisions[key]
    print(f"\n  1. Let libass automatically fall back to {requested} {available}")
    print(f"  2. Add {requested} {wanted} font")
    while True:
        try:
            answer = input("Choose [1/2, default 1]: ").strip() or "1"
        except EOFError:
            answer = "1"
            print("\nNo input available; using the included variant.")
        if answer in ("1", "2"):
            decisions[key] = answer == "2"
            return decisions[key]
        print("Enter 1 or 2.")


def acknowledge_variable_font(key, scan, acknowledged):
    requested = scan["references"][key][0]["font"]
    wanted = variant_label(key[1], key[2])
    print("\n  Warning: this font is supplied by an included variable font.")
    for reference in scan["references"][key]:
        print(f"    Subtitle track: {reference['subtitle']}")
        print(f"    Requires font: {requested} {wanted}.")
        print(f"    First referenced event: {format_timestamp(reference['first'])}")
    print("    Libass may use the default instance and synthesize the requested style.")
    print("    Keeping the variable font unchanged; no replacement will be added.")
    if key in acknowledged:
        print("  Already acknowledged for this font and variant in this batch.")
    else:
        try:
            input("Press Enter to continue: ")
        except EOFError:
            print("\nNo input available; continuing.")
        acknowledged.add(key)
    scan["log"].append(f"VARIABLE FONT {requested} [{wanted}]: KEEP UNCHANGED\n")


def choose_missing_fonts(inspections, preview):
    plans, font_choices, variant_decisions = {}, {}, {}
    variable_acknowledged = set()
    for source, scan in inspections.items():
        additions = []
        plan = {"additions": additions}
        plans[source] = plan
        warnings = scan.get("variant_warnings", {})
        variable_warnings = scan.get("variable_warnings", set())
        if not scan["missing"] and not warnings and not variable_warnings:
            continue
        if scan["missing"]:
            display_missing(source, scan)
        else:
            print("\n" + source.name)
        if scan["blockers"]:
            print("  Some subtitle tracks could not be analyzed; their fonts will be preserved.")
        if preview:
            print("  Preview only: no MKV will be created.")
        for key in sorted(variable_warnings):
            acknowledge_variable_font(key, scan, variable_acknowledged)
        for key in sorted(scan["missing"] & font_choices.keys()):
            additions.extend(supply_font(key, scan, font_choices))
        undecided = scan["missing"] - font_choices.keys()
        if undecided:
            while True:
                print("\n  1. Add remaining missing fonts: use exact local fonts and choose replacements")
                print("  2. Do not add remaining missing fonts")
                try:
                    answer = input("Choose [1/2, default 2]: ").strip() or "2"
                except EOFError:
                    answer = "2"
                    print("\nNo input available; skipping these new missing fonts.")
                if answer in ("1", "2"):
                    break
                print("Enter 1 or 2.")
            if answer == "1":
                for key in sorted(undecided):
                    additions.extend(supply_font(key, scan, font_choices))
                scan["log"].append("New missing fonts: user chose ADD\n")
            else:
                for key in undecided:
                    font_choices[key] = []
                scan["log"].append("New missing fonts: user chose NO ADDITIONS\n")
        for key in sorted(warnings):
            if key in font_choices:
                variant_decisions[key] = bool(font_choices[key])
            add = choose_variant(key, scan, variant_decisions)
            if add:
                supplied = supply_font(key, scan, font_choices)
                additions.extend(supplied)
                if not supplied:
                    variant_decisions[key] = False  # Picker skip equals keeping renderer fallback.
                    add = False
            requested = scan["references"][key][0]["font"]
            scan["log"].append(f"VARIANT {requested} [{variant_label(key[1], key[2])}]: " +
                               ("ADD\n" if add else "USE INCLUDED VARIANT\n"))
        # One exact file can satisfy multiple missing names/variants, e.g. a collection.
        unique = {}
        for item in additions:
            key = (item["path"], requirement_key(item["requested"], item["weight"], item["italic"])
                   if item["substitute"] else "exact")
            unique[key] = item
        plan["additions"] = list(unique.values())
        for item in plan["additions"]:
            scan["log"].append(f"SUPPLY {item['requested']} [{variant_label(item['weight'], item['italic'])}]: {item['path'].name} | substitute={item['substitute']}\n")
    return plans


def build_remux_plans(inspections, approved_removals, missing_plans):
    """Resolve all removal policy during options; remux only executes the plan."""
    plans = {}
    for source, scan in inspections.items():
        choice = missing_plans[source]
        remove_ids = set(approved_removals[source])
        if not scan["blockers"]:
            remove_ids.update(scan["unused_ids"])
        plans[source] = {
            "remove_ids": frozenset(remove_ids),
            "additions": tuple(choice["additions"])}
    return plans


def choose_plans(inspections, preview):
    approved = choose_removals(inspections, preview)
    missing = choose_missing_fonts(inspections, preview)
    return build_remux_plans(inspections, approved, missing)


def set_variant_metadata(font, weight, italic):
    """Relabel a selected face; this deliberately does not transform its outlines."""
    if "OS/2" not in font or "head" not in font:
        raise ValueError("A substitute needs OS/2 and head tables to describe its variant.")
    bold = weight >= 700
    os2, head = font["OS/2"], font["head"]
    os2.usWeightClass = weight
    # fsSelection: italic, bold, regular and oblique. Keep unrelated flags.
    os2.fsSelection &= ~((1 << 0) | (1 << 5) | (1 << 6) | (1 << 9))
    os2.fsSelection |= int(italic) | (int(bold) << 5) | (int(not italic and not bold) << 6)
    head.macStyle = (head.macStyle & ~3) | int(bold) | (int(italic) << 1)
    angle = -12 if italic else 0
    if "post" in font:
        if italic and font["post"].italicAngle:
            angle = font["post"].italicAngle
        font["post"].italicAngle = angle
    if "CFF " in font:
        for top in font["CFF "].cff.topDictIndex:
            top.ItalicAngle = angle
            top.Weight = variant_label(weight, False).title()


def prepare_supplied_fonts(additions, directory):
    from fontTools.ttLib import TTFont
    prepared = []
    exact_paths = set()
    for index, item in enumerate(additions, 1):
        source = item["path"]
        stat = source.stat()
        if (stat.st_size, stat.st_mtime_ns) != item["signature"]:
            raise RuntimeError(f"Supplied font changed since selection: {source.name}. Rerun the script.")
        if not item["substitute"] and source in exact_paths:
            continue
        with source.open("rb") as handle:
            collection = handle.read(4) == b"ttcf"
        if collection:
            suffix = ".ttc"
            path = directory / f"supplied-{index}{suffix}"
            shutil.copyfile(source, path)
            mime = "font/collection"
        else:
            font = TTFont(str(source), lazy=False)
            try:
                suffix = ".otf" if font.sfntVersion == "OTTO" else ".ttf"
                path = directory / f"supplied-{index}{suffix}"
                mime = "application/vnd.ms-opentype" if suffix == ".otf" else "application/x-truetype-font"
                if item["substitute"]:
                    requested = item["requested"]
                    table = font["name"]
                    weight, italic = item["weight"], item["italic"]
                    set_variant_metadata(font, weight, italic)
                    style = variant_label(weight, italic).title()
                    if weight == 400 and italic:
                        style = "Italic"
                    full = requested if style.casefold() in ("regular", "normal", "roman") else requested + " " + style
                    identity = f"{normalize(requested)}|{weight}|{int(italic)}"
                    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
                    ps = (re.sub(r"[^A-Za-z0-9-]", "", requested)[:35] or "Substitute") + "-" + digest
                    ps_style = re.sub(r"[^A-Za-z0-9-]", "", style)[:12]
                    ps += "-" + (ps_style or "Regular")
                    replacements = {1: requested, 2: style, 3: "MKVSubstitute-" + ps, 4: full, 6: ps,
                                    16: requested, 17: style, 18: full, 20: ps, 21: requested, 22: style, 25: ps}
                    for record in table.names:
                        if record.nameID in replacements:
                            value = replacements[record.nameID]
                            record.string = value.encode(record.getEncoding(), errors="replace")
                    # Always provide Unicode records, independent of the source font's locales.
                    for name_id in (1, 2, 3, 4, 6, 16, 17, 21, 22):
                        table.setName(replacements[name_id], name_id, 3, 1, 0x409)
                        table.setName(replacements[name_id], name_id, 0, 4, 0)
                    if "DSIG" in font:
                        del font["DSIG"]  # Its original signature cannot cover the renamed copy.
                    if "CFF " in font:
                        cff = font["CFF "].cff
                        cff.fontNames = [ps]
                        for top in cff.topDictIndex:
                            top.FamilyName, top.FullName = requested, full
                    font.flavor = None
                    font.save(path)
                else:
                    shutil.copyfile(source, path)
            finally:
                font.close()
        key = requirement_key(item["requested"], item["weight"], item["italic"])
        if not any(face_matches(face, key) for face in font_faces(path)):
            raise RuntimeError(f"Supplied font does not resolve {item['requested']}: {source.name}")
        kind = "substitute" if item["substitute"] else "exact"
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", item["requested"]).strip(" .")[:70] or "font"
        variant = variant_label(item["weight"], item["italic"])
        name = f"supplied-{index}-{stem}-{variant.replace(' ', '-')}{suffix}"
        description = f"{kind} font for {item['requested']} [{variant}]; source {source.name}"
        prepared.append({"path": path, "file_name": name, "size": path.stat().st_size,
                         "description": description, "mime": mime})
        if not item["substitute"]:
            exact_paths.add(source)
    return prepared


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


def process(source, output_dir, merge, preview, write_logs, inspection, plan):
    log = list(inspection["log"])
    report = output_dir / (source.name + ".fonts.txt")
    destination = output_dir / source.name
    partial = None
    try:
        if destination.exists():
            print("  Skipped: output file already exists.")
            return "skipped"
        stat = source.stat()
        if (stat.st_size, stat.st_mtime_ns) != inspection["signature"]:
            raise RuntimeError("Input changed since the font scan. Rerun the script to scan it again.")
        before = inspection["before"]
        attachments = before.get("attachments", [])
        fonts = [a for a in attachments if is_font(a)]
        blockers = inspection["blockers"]
        if blockers:
            print("  Keeping remaining fonts: a subtitle track could not be analyzed.")
            for reason in blockers:
                print("    " + reason)
                log.append("KEEP REMAINING FONTS: " + reason + "\n")
        remove_ids = plan["remove_ids"]
        with tempfile.TemporaryDirectory(prefix="mkv-fonts-") as temp:
            temp = Path(temp)
            additions = prepare_supplied_fonts(plan["additions"], temp)
            for attachment in fonts:
                log.append(f"{'REMOVE' if attachment['id'] in remove_ids else 'KEEP'} "
                           f"{attachment['id']}: {attachment.get('file_name', '(unnamed)')}\n")
            kept = [a for a in attachments if a["id"] not in remove_ids]
            removed_bytes = sum(a.get("size", 0) for a in fonts if a["id"] in remove_ids)
            message = (f"Remove {len(remove_ids)}/{len(fonts)} fonts ({removed_bytes / 1048576:.2f} MiB); "
                       f"add {len(additions)} supplied fonts.")
            print("  " + message)
            log.append(message + "\n")
            if not remove_ids and not additions:
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
            if remove_ids:
                options += ["--attachments", "!" + ",".join(str(i) for i in sorted(remove_ids))]
            options += [str(source)]
            for addition in additions:
                options += ["--attachment-name", addition["file_name"],
                            "--attachment-description", addition["description"],
                            "--attachment-mime-type", addition["mime"],
                            "--attach-file", str(addition["path"])]
            option_file = temp / "merge-options.json"
            option_file.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
            run([merge, "@" + str(option_file)], log)
            after = identify(merge, partial, log)
            verify(before, after, kept + additions)
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
    print("Scanning all MKVs and subtitle font references before asking...")
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
    print("\n[Scan local fonts]")
    scan_local_fonts(inspections)
    print("\n[Options]")
    plans = choose_plans(inspections, args.preview)
    for index, (source, inspection) in enumerate(inspections.items(), 1):
        print(f"\n[Process {index}/{len(inspections)}] {source.name}")
        counts[process(source, output, merge, args.preview, args.log,
                       inspection, plans[source])] += 1
    print("\nFinished: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print("Output: " + str(output))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(130)
