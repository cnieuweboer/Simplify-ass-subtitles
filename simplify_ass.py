#!/usr/bin/env python3
"""Simplify ASS/SSA subtitles at two levels for limited renderers.

Level 1 favors maximum reduction; level 2 retains static sign styling and
manageable vector shapes. No third-party packages are required.
"""

from __future__ import annotations

import argparse
import re
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

OVERRIDE_RE = re.compile(r"\{([^}]*)\}")
POS_RE = re.compile(r"\\pos\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)", re.I)
MOVE_RE = re.compile(
    r"\\move\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,"
    r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)"
    r"(?:\s*,\s*\d+\s*,\s*\d+)?\s*\)", re.I
)

# Tags we retain when they are static.  Everything else is discarded.
# Alpha tags are intentionally omitted: animation-heavy tracks often use nearly invisible
# base layers which only become visible via \t(), and keeping those alphas would hide text.
SAFE_SIMPLE_TAGS = {
    "an", "a",
    "b", "i", "u", "s",
    "fn", "fs", "fsp",
    "fscx", "fscy",
    "frz", "fr",
    "bord", "xbord", "ybord",
    "shad", "xshad", "yshad",
    "c", "1c", "2c", "3c", "4c",
    "q", "r",
}

# Parenthesized tags that are safe enough to retain. \fad is deliberately kept;
# it is cheap compared with transform/clip animation and widely supported.
SAFE_FUNCTION_TAGS = {"pos", "fad"}


def is_lyric_style(style: str) -> bool:
    return bool(re.match(r"^(?:OP|ED)(?:\d+)?(?:[_ -]|$)", style, re.I))


@dataclass
class Event:
    kind: str
    layer: str
    start: str
    end: str
    style: str
    name: str
    margin_l: str
    margin_r: str
    margin_v: str
    effect: str
    text: str
    start_s: float
    end_s: float
    source_index: int

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s

    def fields(self) -> list[str]:
        return [
            self.layer, self.start, self.end, self.style, self.name,
            self.margin_l, self.margin_r, self.margin_v, self.effect, self.text,
        ]


def parse_time(value: str) -> float:
    h, m, s = value.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def format_time(seconds: float) -> str:
    # ASS convention normally uses centiseconds.
    seconds = max(0.0, seconds)
    centis = int(round(seconds * 100))
    h, rem = divmod(centis, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def parse_dialogue(line: str, index: int) -> Event | None:
    if not (line.startswith("Dialogue:") or line.startswith("Comment:")):
        return None
    kind, rest = line.split(":", 1)
    parts = rest.lstrip().split(",", 9)
    if len(parts) != 10:
        return None
    try:
        start_s = parse_time(parts[1])
        end_s = parse_time(parts[2])
    except ValueError:
        return None
    return Event(kind, *parts, start_s, end_s, index)


def remove_function_tag(s: str, name: str) -> str:
    """Remove occurrences of \name(...) with balanced nested parentheses."""
    needle = "\\" + name
    out = []
    i = 0
    lower = s.lower()
    while i < len(s):
        j = lower.find(needle.lower(), i)
        if j < 0:
            out.append(s[i:])
            break
        # Avoid matching prefixes, e.g. \t in a hypothetical \tagname.
        k = j + len(needle)
        if k >= len(s) or s[k] != "(":
            out.append(s[i:k])
            i = k
            continue
        out.append(s[i:j])
        depth = 0
        p = k
        while p < len(s):
            if s[p] == "(":
                depth += 1
            elif s[p] == ")":
                depth -= 1
                if depth == 0:
                    p += 1
                    break
            p += 1
        i = p
    return "".join(out)


def strip_expensive_functions(block: str) -> str:
    # Remove transforms first because they may contain nested expensive tags.
    for name in ("t", "clip", "iclip"):
        block = remove_function_tag(block, name)
    return block


def tokenize_override(block: str) -> list[tuple[str, str]]:
    """Very small ASS override tokenizer after complex function tags have been removed."""
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(block):
        if block[i] != "\\":
            i += 1
            continue
        i += 1
        start = i
        # Optional numeric channel prefix, then alphabetic tag name.
        while i < len(block) and block[i].isdigit():
            i += 1
        while i < len(block) and block[i].isalpha():
            i += 1
        name = block[start:i].lower()
        if not name:
            continue
        val_start = i
        if i < len(block) and block[i] == "(":
            depth = 0
            while i < len(block):
                if block[i] == "(":
                    depth += 1
                elif block[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        else:
            while i < len(block) and block[i] != "\\":
                i += 1
        tokens.append((name, block[val_start:i]))
    return tokens


def safe_override(block: str, max_blur: float = 0.0) -> str:
    # Preserve a static midpoint when \move is used without \pos.
    original = block
    pos_match = POS_RE.search(original)
    move_match = MOVE_RE.search(original)

    block = strip_expensive_functions(block)
    kept: list[str] = []

    if not pos_match and move_match:
        x1, y1, x2, y2 = map(float, move_match.groups()[:4])
        kept.append(f"\\pos({(x1+x2)/2:.2f},{(y1+y2)/2:.2f})")

    # \move itself is never retained.
    block = remove_function_tag(block, "move")

    for name, value in tokenize_override(block):
        lname = name.lower()
        if lname in SAFE_FUNCTION_TAGS and value.startswith("("):
            kept.append("\\" + lname + value)
            continue
        if lname == "blur" or lname == "be":
            if max_blur > 0:
                try:
                    amount = float(value.strip() or "0")
                except ValueError:
                    continue
                kept.append(f"\\blur{min(amount, max_blur):g}")
            continue
        if lname in SAFE_SIMPLE_TAGS:
            # Generated karaoke often starts at 1% scale and animates to 100%.
            # Keeping 1% after removing the transform makes the text disappear.
            if lname in {"fscx", "fscy"}:
                try:
                    if float(value.strip()) < 10:
                        continue
                except ValueError:
                    pass
            # Keep shadows static but clamp extreme values which can be expensive/ugly.
            if lname in {"shad", "xshad", "yshad"}:
                try:
                    v = float(value.strip())
                    v = max(-4.0, min(4.0, v))
                    value = f"{v:g}"
                except ValueError:
                    pass
            kept.append("\\" + lname + value)

    # Keep only the last occurrence of state-like tags where practical, while retaining
    # order for reset tags. This prevents giant blocks from surviving in another form.
    result: list[str] = []
    last_index: dict[str, int] = {}
    for tag in kept:
        m = re.match(r"\\([1-4]?[A-Za-z]+)", tag)
        key = m.group(1).lower() if m else tag
        if key == "r":
            result.append(tag)
            last_index.clear()
            continue
        if key in last_index:
            result[last_index[key]] = tag
        else:
            last_index[key] = len(result)
            result.append(tag)
    return "".join(result)


def simplify_text(text: str, max_blur: float = 0.0) -> tuple[str, str]:
    """Return (simplified ASS text, visible text). Removes vector drawing sections."""
    parts = re.split(r"(\{[^}]*\})", text)
    drawing_mode = 0
    output: list[str] = []
    visible: list[str] = []

    for part in parts:
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            block = part[1:-1]
            # Track \p drawing mode from original block.
            p_matches = list(re.finditer(r"\\p(\d+)", block, re.I))
            if p_matches:
                drawing_mode = int(p_matches[-1].group(1))
            safe = safe_override(block, max_blur=max_blur)
            # Never retain \p itself (not in whitelist).
            if safe:
                output.append("{" + safe + "}")
        else:
            if drawing_mode > 0:
                continue
            output.append(part)
            visible.append(part)

    simplified = "".join(output)
    # Drop empty override blocks and custom pseudo-blocks such as {=0}.
    simplified = re.sub(r"\{\s*\}", "", simplified)
    simplified = re.sub(r"\{[^\\{}][^{}]*\}", "", simplified)
    vis = "".join(visible)
    vis = vis.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
    vis = re.sub(r"\s+", " ", vis).strip()
    return simplified, vis


STATIC_TAGS = re.compile(
    r"\\(fn|r|(?:fscx|fscy|xbord|ybord|xshad|yshad|frz|frx|fry|fax|fay|fsp|"
    r"bord|shad|alpha|blur|fs|an|q|1a|2a|3a|4a|1c|2c|3c|4c|c|"
    r"b|i|u|s|p)(?=[^a-zA-Z]|$))", re.I)


def visual_override(block: str, max_blur: float, duration: float | None = None) -> str:
    """Freeze simple transforms at a visible state, keep static sign styling."""
    transformed: list[str] = []
    at = 0
    while True:
        m = re.search(r"\\t\(", block[at:], re.I)
        if m is None:
            break
        start = at + m.start()
        depth, end = 1, start + 3
        while end < len(block) and depth:
            if block[end] == "(":
                depth += 1
            elif block[end] == ")":
                depth -= 1
            end += 1
        transformed.append(block[start + 3:end - 1])
        at = end
    base = strip_expensive_functions(block)
    move = MOVE_RE.search(base)
    if move and not POS_RE.search(base):
        x1, y1, x2, y2 = map(float, move.groups()[:4])
        base += f"\\pos({x2:g},{y2:g})"
    for tag in ("move", "fad", "fade", "clip", "iclip"):
        base = remove_function_tag(base, tag)

    def tokens(source: str) -> list[tuple[str, str]]:
        result = []
        i = 0
        while i < len(source):
            if source[i:i + 5].lower() == "\\pos(":
                j = source.find(")", i + 5)
                if j != -1:
                    result.append(("pos", source[i:j + 1])); i = j + 1; continue
            m = STATIC_TAGS.match(source, i)
            if m:
                j = source.find("\\", m.end())
                if j < 0:
                    j = len(source)
                result.append((m.group(1).lower(), source[i:j]))
                i = j
            else:
                i += 1
        return result

    chosen: dict[str, str] = {}
    for name, value in tokens(base):
        chosen[name] = value
    for transform in transformed:
        # A late color fade must not recolor the entire event to its exit
        # color. Prefer the endpoint with the longer static hold. Untimed
        # transitions have no endpoint hold, so preserve the base color.
        timing = transform.split("\\", 1)[0].strip().rstrip(",")
        times = [v.strip() for v in timing.split(",")] if timing else []
        keep_color_target = False
        if duration is not None and len(times) in (2, 3):
            try:
                begin_ms, end_ms = float(times[0]), float(times[1])
                event_ms = duration * 1000
                keep_color_target = (0 <= begin_ms <= end_ms
                                     and max(0, event_ms - end_ms) > min(begin_ms, event_ms))
            except ValueError:
                pass
        for name, value in tokens(transform):
            if name in {"pos", "p", "r", "fn"}:
                continue
            if name in {"c", "1c", "2c", "3c", "4c"} and not keep_color_target:
                continue
            if name in {"1a", "2a", "3a", "4a", "alpha"}:
                # A fade-out's final transparent frame should not hide the sign.
                def opacity_tag(tag: str) -> int:
                    m = re.search(r"&H([\dA-F]{2})&", tag, re.I)
                    return int(m.group(1), 16) if m else 255
                if opacity_tag(value) < opacity_tag(chosen.get(name, "&HFF&")):
                    chosen[name] = value
            else:
                chosen[name] = value
    for name in list(chosen):
        value = chosen[name]
        if name == "blur":
            try:
                if max_blur <= 0 or float(value[5:]) <= 0:
                    del chosen[name]; continue
                chosen[name] = f"\\blur{min(float(value[5:]), max_blur):g}"
            except ValueError:
                del chosen[name]
        if name in {"bord", "xbord", "ybord", "shad", "xshad", "yshad"}:
            try:
                amount = float(value[len(name) + 1:])
                limit = 4 if "bord" in name else 2
                chosen[name] = f"\\{name}{max(-limit, min(limit, amount)):g}"
            except ValueError:
                del chosen[name]
    return "".join(chosen.values())


def simplify_visual_text(text: str, max_blur: float,
                         duration: float | None = None) -> tuple[str, str, int]:
    parts = re.split(r"(\{[^}]*\})", text)
    drawing = False
    output, visible = [], []
    drawing_chars = 0
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            p = list(re.finditer(r"\\p(\d+)", part, re.I))
            if p:
                drawing = int(p[-1].group(1)) > 0
            simplified = visual_override(part[1:-1], max_blur, duration)
            if simplified:
                output.append("{" + simplified + "}")
        elif part:
            output.append(part)
            if drawing:
                drawing_chars += len(part)
            else:
                visible.append(part)
    vis = "".join(visible).replace(r"\N", " ").replace(r"\n", " ").replace(r"\h", " ")
    return "".join(output), re.sub(r"\s+", " ", vis).strip(), drawing_chars


def get_pos(text: str) -> tuple[float, float] | None:
    m = POS_RE.search(text)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def set_pos(text: str, pos: tuple[float, float] | None) -> str:
    if pos is None:
        return text
    repl = f"\\pos({pos[0]:.2f},{pos[1]:.2f})"
    if POS_RE.search(text):
        return POS_RE.sub(lambda _m: repl, text, count=1)
    # Add to first override block, or create one.
    if text.startswith("{"):
        return text.replace("{", "{" + repl, 1)
    return "{" + repl + "}" + text


def event_identity_for_dedup(e: Event, visible: str) -> tuple:
    pos = get_pos(e.text)
    rounded_pos = None if pos is None else (round(pos[0], 1), round(pos[1], 1))
    return (
        e.layer, e.start, e.end, e.style, e.name,
        e.margin_l, e.margin_r, e.margin_v,
        visible, rounded_pos,
    )


def deduplicate_layers(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Collapse simultaneous effect layers with same visible text and position."""
    seen: dict[tuple, Event] = {}
    output: list[Event] = []
    removed = 0
    for e in events:
        if e.kind != "Dialogue":
            output.append(e)
            continue
        visible = visible_map.get(e.source_index, "")
        key = event_identity_for_dedup(e, visible)
        if key in seen:
            removed += 1
            continue
        seen[key] = e
        output.append(e)
    return output, removed


def reduce_static_sign_copies(events: list[Event], visible_map: dict[int, str],
                              originals: dict[int, Event]) -> tuple[list[Event], int]:
    """In aggressive mode, fold slightly offset effect copies into their fill."""
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or is_lyric_style(e.style) or get_pos(e.text) is None:
            continue
        visible = visible_map.get(e.source_index, "")
        if visible:
            groups.setdefault((e.style, e.name, e.margin_l, e.margin_r,
                               e.margin_v, visible), []).append(e)

    def alpha(e: Event) -> int:
        raw = originals[e.source_index].text
        base = strip_expensive_functions(raw)
        values = re.findall(r"\\(?:1a|alpha)&H([0-9a-f]{2})&", base, re.I)
        return int(values[-1], 16) if values else 0

    def rank(e: Event) -> tuple:
        return (alpha(e), -int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
                -e.duration, e.source_index)

    removed: set[int] = set()
    for group in groups.values():
        ranks = {e.source_index: rank(e) for e in group}
        for e in group:
            x, y = get_pos(e.text)
            for other in group:
                if other is e or ranks[other.source_index] >= ranks[e.source_index]:
                    continue
                ox, oy = get_pos(other.text)
                # Only remove a copy covered for its entire lifetime by an
                # almost coincident copy of the same complete text.
                if (other.start_s <= e.start_s + 0.001
                        and other.end_s >= e.end_s - 0.001
                        and abs(ox - x) <= 3 and abs(oy - y) <= 3):
                    removed.add(e.source_index)
                    break
    return [e for e in events if e.source_index not in removed], len(removed)


def coalesce_lyric_phases(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Join touching phases of one positioned glyph, keeping lyric rows separate."""
    groups: dict[tuple, list[Event]] = {}
    starts: dict[tuple, set[tuple]] = {}
    ends: dict[tuple, set[tuple]] = {}
    output = []
    for e in events:
        pos = get_pos(e.text)
        visible = visible_map.get(e.source_index, "")
        if (e.kind != "Dialogue" or e.effect.lower() != "fx" or
                not is_lyric_style(e.style) or pos is None or len(visible) > 4):
            output.append(e)
            continue
        key = (e.style, e.name, e.layer, e.margin_l, e.margin_r, e.margin_v,
               round(pos[0], 1), round(pos[1], 1), visible)
        groups.setdefault(key, []).append(e)
        row = (e.style, e.name, e.layer, round(pos[1] / 25))
        glyph = (round(pos[0], 1), visible)
        starts.setdefault((*row, round(e.start_s, 2)), set()).add(glyph)
        ends.setdefault((*row, round(e.end_s, 2)), set()).add(glyph)
    # Identical letters can occupy the same position in consecutive lyrics.
    # A change in the surrounding glyphs marks a real lyric boundary.
    boundaries = {key for key in starts.keys() & ends.keys()
                  if min(len(starts[key]), len(ends[key])) >= 5 and
                  starts[key] != ends[key]}
    removed = 0
    for group in groups.values():
        group.sort(key=lambda e: (e.start_s, e.end_s, e.source_index))
        current = group[0]
        for e in group[1:]:
            pos = get_pos(e.text)
            boundary = (e.style, e.name, e.layer, round(pos[1] / 25), round(e.start_s, 2))
            if (e.start_s <= current.end_s + 0.011 and
                    not (abs(e.start_s - current.end_s) <= 0.011 and boundary in boundaries)):
                end = max(current.end_s, e.end_s)
                current = replace(current, end=format_time(end), end_s=end,
                                  source_index=min(current.source_index, e.source_index))
                removed += 1
            else:
                output.append(current)
                current = e
        output.append(current)
    return sorted(output, key=lambda e: e.source_index), removed


def merge_timed_lyrics(events: list[Event], visible_map: dict[int, str],
                       space_map: dict[tuple, set[float]], level: int = 1) -> tuple[list[Event], int]:
    """Turn positioned lyric fragments sharing time/style into one plain ASS line."""
    comments: dict[tuple[str, str, str], list[str]] = {}
    for e in events:
        if e.kind == "Comment" and e.effect.lower() == "karaoke":
            _, lyric = simplify_text(e.text)
            comments.setdefault((e.start, e.end, e.style), []).append(lyric)

    groups: dict[tuple[str, str, str, str, int], list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or e.effect.lower() != "fx":
            continue
        pos = get_pos(e.text)
        if pos is None or not visible_map.get(e.source_index):
            continue
        # Separate top/bottom lines, even when they share the same style and time.
        key = (e.start, e.end, e.style, e.name, round(pos[1] / 25))
        groups.setdefault(key, []).append(e)

    removed: set[int] = set()
    replacements: dict[int, Event] = {}
    for (start, end, style, name, band), group in groups.items():
        positions: dict[float, list[Event]] = {}
        for e in group:
            positions.setdefault(round(get_pos(e.text)[0], 1), []).append(e)
        if len(positions) < 3 or len(positions) > 80:
            continue
        # Only merge actual fragments with one text per horizontal position.
        ordered = []
        for x in sorted(positions):
            variants = {visible_map[e.source_index] for e in positions[x]}
            if len(variants) != 1:
                break
            ordered.append(next(iter(variants)))
        if len(ordered) != len(positions):
            continue
        joined = "".join(ordered)
        candidates = comments.get((start, end, style), [])
        norm = lambda s: "".join(s.split()).casefold()
        lyric = next((s for s in candidates if norm(s) == norm(joined) or
                      any(norm(s) == norm(visible_map[e.source_index]) for e in group)), None)
        if lyric is None:
            # Some openings have no full-line Comment. Their short fragments
            # are repeated at the same x position in several effect layers.
            # For OP_ROM this also includes romanized syllables (yu, bi, wo).
            single_letters = all(len(part) == 1 for part in ordered)
            repeated_syllables = ((style == "OP_ROM" if level == 1
                                   else "ROM" in style.upper()) and
                                  all(1 <= len(part) <= (3 if level == 1 else 6)
                                      for part in ordered) and
                                  all(len(positions[x]) >= 2 for x in positions))
            if len(ordered) < 5 or not (single_letters or repeated_syllables):
                continue
            blanks = space_map.get((start, end, style, name, band), set())
            pieces = []
            xs = sorted(positions)
            inferred_spaces: set[int] = set()
            if not blanks and is_lyric_style(style) and len(xs) >= 8:
                # Some letter-by-letter generators omit the blank glyphs. A
                # large gap relative to neighboring glyph widths marks a word
                # boundary. Use this only for opening letter rows.
                def width(c: str) -> float:
                    return {
                        "i": .55, "l": .55, "I": .7, "j": .6,
                        "t": .8, "f": .8, "r": 1.0,
                        ".": .3, ",": .3, "'": .3, "!": .3,
                        "m": 1.3, "w": 1.3, "M": 1.3, "W": 1.3,
                    }.get(c, 1.0)

                ratios = [
                    (xs[i] - xs[i-1]) /
                    ((sum(map(width, ordered[i-1])) + sum(map(width, ordered[i]))) / 2)
                    for i in range(1, len(xs))
                ]
                typical = statistics.median(sorted(ratios)[:max(1, int(len(ratios) * 0.7))])
                inferred_spaces = {i for i, ratio in enumerate(ratios, 1)
                                   if ratio > typical * (1.2 if repeated_syllables else 1.3)}
                if repeated_syllables:
                    # The separate particle "wo" almost always has a word
                    # boundary after it even when the visual gap is small.
                    inferred_spaces.update(i for i in range(1, len(ordered))
                                           if ordered[i - 1].casefold() == "wo")
            for index, x in enumerate(xs):
                if index and (index in inferred_spaces or
                              any(xs[index-1] < b < x for b in blanks)):
                    pieces.append(" ")
                pieces.append(ordered[index])
            lyric = "".join(pieces)
        first = min(group, key=lambda e: e.source_index)
        # The style supplies normal alignment/margins. The original positions,
        # per-word colors and 1%-scale animation must not survive on this line.
        if level == 2 and "ED1" in style.upper():
            y = statistics.median(get_pos(e.text)[1] for e in group)
            lyric = f"{{\\an9\\pos(1856,{y:g})}}" + lyric
        merged = replace(first, layer="0", effect="", text=lyric)
        replacements[first.source_index] = merged
        removed.update(e.source_index for e in group if e.source_index != first.source_index)
        visible_map[first.source_index] = lyric

    output = []
    for e in events:
        if e.source_index in replacements:
            output.append(replacements[e.source_index])
        elif e.source_index not in removed:
            output.append(e)
    return output, len(removed)


def collapse_matching_lyric_layers(events: list[Event],
                                   visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Remove a nearby positioned syllable row when a full lyric line matches it."""
    def norm(s: str) -> str:
        return "".join(s.split()).casefold()

    lines = [e for e in events if e.kind == "Dialogue" and e.effect == "" and
             is_lyric_style(e.style) and
             len(norm(visible_map.get(e.source_index, ""))) >= 10]
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or e.effect.lower() != "fx":
            continue
        pos = get_pos(e.text)
        if pos is not None and visible_map.get(e.source_index):
            key = (e.start, e.end, e.style, e.name, round(pos[1] / 25))
            groups.setdefault(key, []).append(e)

    removed: set[int] = set()
    extended: dict[int, Event] = {}
    for (start, end, style, name, _band), group in groups.items():
        positions: dict[float, set[str]] = {}
        for e in group:
            positions.setdefault(round(get_pos(e.text)[0], 1), set()).add(visible_map[e.source_index])
        if len(positions) < 3 or any(len(v) != 1 for v in positions.values()):
            continue
        assembled = norm("".join(next(iter(positions[x])) for x in sorted(positions)))
        for line in lines:
            if line.style != style or line.name != name or norm(visible_map[line.source_index]) != assembled:
                continue
            overlap = min(line.end_s, group[0].end_s) - max(line.start_s, group[0].start_s)
            if overlap < 0.8 * min(line.duration, group[0].duration):
                continue
            removed.update(e.source_index for e in group)
            earlier = min(line.start_s, group[0].start_s)
            later = max(line.end_s, group[0].end_s)
            extended[line.source_index] = replace(line, start=format_time(earlier),
                end=format_time(later), start_s=earlier, end_s=later)
            break

    output = [extended.get(e.source_index, e) for e in events if e.source_index not in removed]
    return output, len(removed)


def collapse_full_lyric_copies(events: list[Event],
                               visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Collapse overlapping full-line copies of the same opening/ending lyric."""
    def norm(value: str) -> str:
        return "".join(value.split()).casefold()

    grouped: dict[tuple[str, str, str, int | None], list[Event]] = {}
    for e in events:
        visible = visible_map.get(e.source_index, "")
        if (e.kind == "Dialogue" and is_lyric_style(e.style) and
                len(norm(visible)) >= 12):
            pos = get_pos(e.text)
            band = round(pos[1] / 25) if pos is not None else None
            grouped.setdefault((e.style, e.name, norm(visible), band), []).append(e)

    removed: set[int] = set()
    replacements: dict[int, Event] = {}
    for group in grouped.values():
        for e in group:
            if e.source_index in removed:
                continue
            cluster = [other for other in group if other.source_index not in removed and
                       min(e.end_s, other.end_s) - max(e.start_s, other.start_s) >=
                       0.8 * min(e.duration, other.duration)]
            if len(cluster) < 2:
                continue
            # Prefer the author's spaced lyric when both a generated row and a
            # full-line copy exist, rather than keeping the inferred spacing.
            best = max(cluster, key=lambda item: (
                visible_map[item.source_index].count(" "),
                item.effect == "", -item.source_index))
            first = min(cluster, key=lambda item: item.source_index)
            earlier = min(item.start_s for item in cluster)
            later = max(item.end_s for item in cluster)
            text = visible_map[best.source_index]
            if "ED1" in first.style.upper():
                positions = [get_pos(item.text) for item in cluster]
                positions = [pos for pos in positions if pos is not None]
                if positions:
                    y = statistics.median(pos[1] for pos in positions)
                    text = f"{{\\an9\\pos(1856,{y:g})}}" + text
            replacements[first.source_index] = replace(
                first, layer="0", start=format_time(earlier), end=format_time(later),
                start_s=earlier, end_s=later, effect="",
                text=text)
            visible_map[first.source_index] = visible_map[best.source_index]
            removed.update(item.source_index for item in cluster if item != first)

    return [replacements.get(e.source_index, e) for e in events
            if e.source_index not in removed], len(removed)


def can_merge_short(a: Event, b: Event, vis_a: str, vis_b: str,
                    max_piece_duration: float, max_gap: float) -> bool:
    if a.kind != "Dialogue" or b.kind != "Dialogue":
        return False
    if vis_a == "" or vis_a != vis_b:
        return False
    if (a.layer, a.style, a.name, a.margin_l, a.margin_r, a.margin_v) != \
       (b.layer, b.style, b.name, b.margin_l, b.margin_r, b.margin_v):
        return False
    if a.duration > max_piece_duration or b.duration > max_piece_duration:
        return False
    gap = b.start_s - a.end_s
    return -0.03 <= gap <= max_gap


def merge_frame_animation(events: list[Event], visible_map: dict[int, str],
                          max_piece_duration: float = 0.16,
                          max_gap: float = 0.08,
                          min_pieces: int = 3) -> tuple[list[Event], int]:
    """Flatten runs of tiny contiguous events carrying the same text."""
    output: list[Event] = []
    merged_away = 0
    i = 0
    while i < len(events):
        first = events[i]
        vis_first = visible_map.get(first.source_index, "")
        run = [first]
        j = i + 1
        while j < len(events):
            prev = run[-1]
            cur = events[j]
            if not can_merge_short(prev, cur,
                                   visible_map.get(prev.source_index, ""),
                                   visible_map.get(cur.source_index, ""),
                                   max_piece_duration, max_gap):
                break
            run.append(cur)
            j += 1

        if len(run) >= min_pieces:
            # Pick the middle event's formatting and median position to make motion static.
            representative = run[len(run) // 2]
            positions = [get_pos(x.text) for x in run]
            positions = [p for p in positions if p is not None]
            median_pos = None
            if positions:
                median_pos = (
                    statistics.median(p[0] for p in positions),
                    statistics.median(p[1] for p in positions),
                )
            merged = replace(
                representative,
                start=run[0].start,
                end=run[-1].end,
                start_s=run[0].start_s,
                end_s=run[-1].end_s,
                text=set_pos(representative.text, median_pos),
                source_index=run[0].source_index,
            )
            output.append(merged)
            merged_away += len(run) - 1
            i = j
        else:
            output.extend(run)
            i += len(run)
    return output, merged_away


def freeze_vector_sequences(events: list[Event], short_duration: float = 0.16
                            ) -> tuple[list[Event], int]:
    """Freeze frame-by-frame drawings, including their longer static hold.

    Match actual paths and static paint, not style names or colors specific
    to a show. Overlapping copies are ambiguous and remain separate.
    """
    changing = re.compile(
        r"\\(?:alpha|[1-4]a)&H[0-9a-f]{2}&|"
        r"\\(?:fscx|fscy|frz|frx|fry|fax|fay)-?\d+(?:\.\d+)?", re.I)
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        signature = changing.sub("", POS_RE.sub("", e.text))
        key = (e.kind, e.layer, e.style, e.name, e.margin_l, e.margin_r,
               e.margin_v, signature)
        groups.setdefault(key, []).append(e)

    def transparency(e: Event) -> int:
        channels = [0, 0, 0, 0]
        for tag, value in re.findall(r"\\(alpha|[1-4]a)&H([0-9a-f]{2})&", e.text, re.I):
            if tag.lower() == "alpha":
                channels = [int(value, 16)] * 4
            else:
                channels[int(tag[0]) - 1] = int(value, 16)
        return sum(channels)

    output: list[Event] = []
    removed = 0

    def emit(run: list[Event]) -> None:
        nonlocal removed
        if (len(run) < 3
                or sum(e.duration <= short_duration + 1e-6 for e in run) < 2
                or any(b.start_s < a.end_s - 1e-6 for a, b in zip(run, run[1:]))
                or len({e.text for e in run}) < 2):
            output.extend(run)
            return
        # Prefer the unfaded frame, then the longest-held position. Keeping
        # that event's paint intact preserves intentional transparent fills.
        chosen = min(run, key=lambda e: (transparency(e), -e.duration, e.source_index))
        output.append(replace(chosen, start=run[0].start, start_s=run[0].start_s,
                              end=run[-1].end, end_s=run[-1].end_s,
                              source_index=min(e.source_index for e in run)))
        removed += len(run) - 1

    for group in groups.values():
        ordered = sorted(group, key=lambda e: (e.start_s, e.end_s, e.source_index))
        # Build time-connected components first so simultaneous identical
        # shapes cannot accidentally be connected to one another's frames.
        components: list[list[Event]] = []
        latest_end = -1.0
        for e in ordered:
            if not components or e.start_s > latest_end + 0.011:
                components.append([])
                latest_end = e.end_s
            components[-1].append(e)
            latest_end = max(latest_end, e.end_s)
        for component in components:
            if any(b.start_s < a.end_s - 1e-6 for a, b in zip(component, component[1:])):
                output.extend(component)
                continue
            run: list[Event] = []
            has_hold = False
            for e in component:
                is_hold = e.duration > short_duration + 1e-6
                if is_hold and has_hold:
                    emit(run)
                    run, has_hold = [], False
                run.append(e)
                has_hold |= is_hold
            emit(run)
    return sorted(output, key=lambda e: e.source_index), removed


def reduce_vector_layers(events: list[Event]) -> tuple[list[Event], int]:
    """Keep the geometry and up to two static layers per repeated drawing."""
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        geometry = OVERRIDE_RE.sub("", e.text)
        pos = get_pos(e.text)
        key = (e.start, e.end, e.style, e.name, pos, geometry)
        groups.setdefault(key, []).append(e)
    result = []
    for group in groups.values():
        layers: dict[str, list[Event]] = {}
        for e in group:
            layers.setdefault(e.layer, []).append(e)
        # A pair of different layers may be the outline and fill of a panel.
        for layer in sorted(layers, key=lambda v: int(v) if v.isdigit() else 0)[-2:]:
            choices = layers[layer]
            result.append(choices[len(choices) // 2])
    return sorted(result, key=lambda e: e.source_index), len(events) - len(result)


def remove_covered_vector_glows(events: list[Event]) -> tuple[list[Event], int]:
    """Drop lower decorative copies of a drawing covered by its upper copy.

    Require the same timing, path and position. Never classify a shape by its
    color: an independent colored divider or backdrop can carry real content.
    """
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        key = (e.start, e.end, e.style, e.name, get_pos(e.text),
               OVERRIDE_RE.sub("", e.text))
        groups.setdefault(key, []).append(e)

    color_tag = re.compile(r"\\(?:[1234]c|c)&H[0-9a-f]{6}&", re.I)

    def tags(e: Event) -> str:
        return e.text.split("}", 1)[0]

    def layer(e: Event) -> int:
        try:
            return int(e.layer)
        except ValueError:
            return 0

    def alpha(block: str, channel: int) -> int:
        matches = re.findall(rf"\\(?:{channel}a|alpha)&H([0-9a-f]{{2}})&", block, re.I)
        return int(matches[-1], 16) if matches else 0

    def pose(block: str) -> tuple[str, ...]:
        # A shared path is not enough if the copies are scaled or rotated
        # differently; their visible contours may not overlap.
        return tuple((re.findall(rf"\\{tag}([^\\}}]*)", block, re.I) or [""])[-1]
                     for tag in ("an", "pos", "fscx", "fscy", "frz", "frx", "fry", "fax", "fay"))

    removed: set[int] = set()
    for group in groups.values():
        for lower in group:
            low = tags(lower)
            for upper in group:
                if layer(upper) <= layer(lower):
                    continue
                high = tags(upper)
                if pose(low) != pose(high):
                    continue
                # Identically painted contours with only their colors changed
                # are fully covered by the later copy, including their borders.
                same_paint = color_tag.sub("", low) == color_tag.sub("", high)
                # A mostly transparent fill with a border is also a common
                # glow under an opaque paper fill of the very same geometry.
                outlined_paper = (len(OVERRIDE_RE.sub("", lower.text)) >= 200
                                  and alpha(low, 1) >= 240
                                  and bool(re.search(r"\\(?:x?bord|ybord)[1-9]", low, re.I))
                                  and alpha(high, 1) <= 128
                                  and bool(re.search(r"\\(?:[1-4]c|c)&H", high, re.I)))
                if same_paint or outlined_paper:
                    removed.add(lower.source_index)
                    break
    return [e for e in events if e.source_index not in removed], len(removed)


def cap_vector_cues(events: list[Event], limit: int) -> tuple[list[Event], int]:
    """Bound unusually dense vector effects after repeated shapes are folded."""
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        groups.setdefault((e.start, e.end, e.style), []).append(e)
    output = []
    for group in groups.values():
        if len(group) <= limit:
            output.extend(group)
        else:
            # Preserve the largest contours first, which usually carry the
            # outline of a sign; skip minor decorative flecks and particles.
            output.extend(sorted(group, key=lambda e: len(e.text), reverse=True)[:limit])
    return sorted(output, key=lambda e: e.source_index), len(events) - len(output)


def reduce_text_layers(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    def primary_alpha(e: Event) -> int:
        # ASS primary alpha uses 00 for opaque and FF for invisible. A higher
        # layer can be only a faint glow above a fully visible text layer.
        alphas = re.findall(r"\\(?:1a|alpha)&H([0-9A-F]{2})&", e.text, re.I)
        return int(alphas[-1], 16) if alphas else 0

    def primary_color(e: Event) -> str:
        colors = re.findall(r"\\(?:1c|c)&H([0-9A-F]{6})&", e.text, re.I)
        return colors[-1].upper() if colors else "STYLE_PRIMARY"

    def visible_layer(e: Event) -> tuple[int, int, int]:
        layer = int(e.layer) if e.layer.isdigit() else 0
        return (-primary_alpha(e), layer, -e.source_index)

    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or is_lyric_style(e.style):
            groups.setdefault((e.source_index,), []).append(e)
            continue
        key = (e.start, e.end, e.style, e.name, get_pos(e.text),
               visible_map.get(e.source_index, ""))
        groups.setdefault(key, []).append(e)
    output = []
    for group in groups.values():
        if len({primary_color(e) for e in group}) > 1:
            # Different colors may form a glow and foreground. Prefer the
            # upper visible color, not an almost transparent topmost copy.
            visible = [e for e in group if primary_alpha(e) <= 128]
            chosen = max(visible, key=lambda e: (int(e.layer) if e.layer.isdigit() else 0,
                                                  e.source_index)) if visible else max(group, key=visible_layer)
        else:
            # With the same color, an opaque lower layer carries the text.
            chosen = max(group, key=visible_layer)
        output.append(chosen)
    return sorted(output, key=lambda e: e.source_index), len(events) - len(output)


def texture_carrier_indices(events: list[Event], lines: list[str], level: int = 1) -> set[int]:
    """Infer decorative carrier text from its role, without a font blacklist.

    Require hidden fill/outline, a vector mask, and nearby readable text in
    another font. Aggressive mode also discards long, low-opacity multiline
    text textures when they share a cue with vector art.
    """
    styles: dict[str, dict[str, str]] = {}
    fields: list[str] = []
    section = ""
    for line in lines:
        if line.startswith("["):
            section = line.lower()
        elif section == "[v4+ styles]" and line.startswith("Format:"):
            fields = [v.strip().lower() for v in line.split(":", 1)[1].split(",")]
        elif section == "[v4+ styles]" and line.startswith("Style:") and fields:
            data = dict(zip(fields, (v.strip() for v in line.split(":", 1)[1].split(","))))
            styles[data.get("name", "")] = data

    def describe(e: Event):
        if e.kind != "Dialogue" or re.search(r"\\(?:p[1-9]|r(?=\\|}|[A-Za-z]))", e.text):
            return None
        text = re.sub(r"\s+", " ", OVERRIDE_RE.sub("", e.text)).strip()
        pos = get_pos(e.text)
        if not text or pos is None:
            return None
        base = strip_expensive_functions(e.text)
        style = styles.get(e.style, {})
        fonts = re.findall(r"\\fn([^\\}]+)", base, re.I)
        font = (fonts[-1].strip() if fonts else style.get("fontname", "")).casefold()
        def alpha(channel: int, key: str) -> int:
            value = style.get(key, "&H00FFFFFF").removeprefix("&H").rstrip("&")
            initial = int(value[:2], 16) if re.fullmatch(r"[0-9a-fA-F]{8}", value) else 0
            tags = re.findall(rf"\\(?:alpha|{channel}a)&H([0-9a-f]{{2}})&", base, re.I)
            return int(tags[-1], 16) if tags else initial
        primary = alpha(1, "primarycolour")
        outline = alpha(3, "outlinecolour")
        # An animated reveal is actual lettering, not a hidden carrier.
        reveal = any(int(v, 16) < 240 for v in re.findall(
            r"\\(?:alpha|1a|3a)&H([0-9a-f]{2})&", e.text, re.I))
        hidden = primary >= 240 and outline >= 240 and not reveal
        masked = bool(re.search(r"\\clip\(\s*(?:\d+\s*,\s*)?m\s", e.text, re.I))
        return text, pos, font, primary, hidden, masked

    descriptions = {e.source_index: d for e in events if (d := describe(e)) is not None}
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.source_index in descriptions:
            groups.setdefault((e.start, e.end, e.style, e.name), []).append(e)
    candidates: list[tuple[Event, tuple]] = []
    learned: set[tuple[str, str]] = set()
    for group in groups.values():
        for e in group:
            d = descriptions[e.source_index]
            text, (x, y), font, _, hidden, masked = d
            if not hidden or not font:
                continue
            companions = [descriptions[o.source_index] for o in group if o is not e]
            if not any(p[0] != text and p[2] and p[2] != font and p[3] <= 128
                       and abs(p[1][0] - x) <= 6 and abs(p[1][1] - y) <= 6
                       for p in companions):
                continue
            candidates.append((e, d))
            if masked:
                learned.add((font, text))
    result = {e.source_index for e, d in candidates if d[5] or (d[2], d[0]) in learned}
    if level == 1:
        cue_vectors: dict[tuple, int] = {}
        for e in events:
            if e.kind == "Dialogue" and re.search(r"\\p[1-9]", e.text, re.I):
                key = (e.start, e.end, e.style, e.name)
                cue_vectors[key] = cue_vectors.get(key, 0) + 1
        for e in events:
            d = descriptions.get(e.source_index)
            if d is None or e.source_index in result or d[5]:
                continue
            key = (e.start, e.end, e.style, e.name)
            if cue_vectors.get(key, 0) < 2 or not d[2]:
                continue
            base = strip_expensive_functions(e.text)
            alphas = re.findall(r"\\1a&H([0-9a-f]{2})&", base, re.I)
            if not alphas or int(alphas[-1], 16) < 208:
                continue
            raw = OVERRIDE_RE.sub("", e.text)
            parts = re.split(r"\\[Nn]", raw)
            long_runs = sum(1 for part in parts if
                            re.fullmatch(r"[A-Za-z]{14,}", part.strip()))
            if len(parts) >= 3 and long_runs >= 2:
                result.add(e.source_index)
    return result


def simplify_ass(path: Path, output: Path, max_blur: float,
                 short_duration: float, short_gap: float,
                 max_drawing_chars: int = 8000,
                 max_vectors_per_cue: int = 32,
                 level: int = 1) -> dict[str, int]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = raw.splitlines()

    parsed_by_line = {idx: e for idx, line in enumerate(lines)
                      if (e := parse_dialogue(line, idx)) is not None}
    texture_carriers = texture_carrier_indices(list(parsed_by_line.values()), lines, level)
    simplified_events: list[Event] = []
    vector_events: list[Event] = []
    visible_map: dict[int, str] = {}
    space_map: dict[tuple, set[float]] = {}
    dropped_drawings = 0
    original_dialogues = 0
    blank_events: list[Event] = []

    for idx, line in enumerate(lines):
        e = parsed_by_line.get(idx)
        if e is None:
            continue
        parsed_by_line[idx] = e
        if e.kind != "Dialogue":
            simplified_events.append(e)
            continue
        original_dialogues += 1
        if idx in texture_carriers:
            dropped_drawings += 1
            continue
        if level == 1:
            new_text, visible = simplify_text(e.text, max_blur=max_blur)
            drawing_chars = 0
        else:
            new_text, visible, drawing_chars = simplify_visual_text(e.text, max_blur, e.duration)
        visible_map[idx] = visible
        if drawing_chars:
            if drawing_chars <= max_drawing_chars:
                vector_events.append(replace(e, text=new_text, effect=""))
            else:
                dropped_drawings += 1
            continue
        if not visible:
            # Position-only events in per-character FX mark word spaces in some
            # generated lyrics. Keep their locations for text reconstruction.
            pos = get_pos(new_text)
            if (e.effect.lower() == "fx" and pos is not None and
                    not re.search(r"\\p\d", e.text, re.I)):
                key = (e.start, e.end, e.style, e.name, round(pos[1] / 25))
                space_map.setdefault(key, set()).add(round(pos[0], 1))
                blank_events.append(replace(e, text=new_text))
            # A dialogue event with no remaining text is generally a vector drawing/effect.
            dropped_drawings += 1
            continue
        simplified_events.append(replace(e, text=new_text))

    sign_copies_removed = 0
    if level == 1:
        simplified_events, sign_copies_removed = reduce_static_sign_copies(
            simplified_events, visible_map, parsed_by_line)

    # Reconstruct each glyph's complete lifetime before trying to assemble rows.
    simplified_events, phase_merged = coalesce_lyric_phases(
        simplified_events, visible_map)
    joined_blanks, _ = coalesce_lyric_phases(blank_events, visible_map)
    for e in joined_blanks:
        pos = get_pos(e.text)
        key = (e.start, e.end, e.style, e.name, round(pos[1] / 25))
        space_map.setdefault(key, set()).add(round(pos[0], 1))

    # For visual signs, choose their visible fill before same-layer dedup can
    # discard a brighter effect copy merely because it appeared later.
    text_copies_removed = 0
    if level == 2:
        simplified_events, text_copies_removed = reduce_text_layers(
            simplified_events, visible_map)

    # Work in chronological/source order. Effect-layer dedup is safe regardless of adjacency.
    simplified_events, deduped = deduplicate_layers(simplified_events, visible_map)
    simplified_events, lyric_merged = merge_timed_lyrics(
        simplified_events, visible_map, space_map, level)
    simplified_events, overlap_removed = collapse_matching_lyric_layers(
        simplified_events, visible_map)
    simplified_events, full_copies_removed = collapse_full_lyric_copies(
        simplified_events, visible_map)
    simplified_events, merged = merge_frame_animation(
        simplified_events, visible_map,
        max_piece_duration=short_duration,
        max_gap=short_gap,
    )
    vector_copies_removed = vector_glows_removed = vector_frames_removed = excess_vectors = 0
    if level == 2:
        simplified_events, remaining_copies = reduce_text_layers(simplified_events, visible_map)
        text_copies_removed += remaining_copies
        vector_events, vector_copies_removed = reduce_vector_layers(vector_events)
        vector_events, vector_frames_removed = freeze_vector_sequences(vector_events, short_duration)
        vector_events, vector_glows_removed = remove_covered_vector_glows(vector_events)
        vector_events, excess_vectors = cap_vector_cues(vector_events, max_vectors_per_cue)
        simplified_events = sorted(simplified_events + vector_events, key=lambda e: e.source_index)

    # Rebuild [Events] while preserving all non-dialogue/event metadata lines.
    # We replace Dialogue/Comment lines at their original region with the processed sequence.
    event_line_indices = sorted(parsed_by_line)
    if not event_line_indices:
        output.write_text(raw, encoding="utf-8-sig")
        return {key: 0 for key in ("original", "output", "deduped", "lyric_merged",
                "merged", "dropped", "overlap_removed", "full_copies_removed", "phase_merged")}

    first_event_line = event_line_indices[0]
    last_event_line = event_line_indices[-1]
    before = lines[:first_event_line]
    after = lines[last_event_line + 1:]

    rendered = []
    for e in simplified_events:
        rendered.append(f"{e.kind}: " + ",".join(e.fields()))

    final_lines = before + rendered + after
    output.write_text("\n".join(final_lines) + ("\n" if raw.endswith(("\n", "\r")) else ""),
                      encoding="utf-8-sig")

    output_dialogues = sum(1 for e in simplified_events if e.kind == "Dialogue")
    return {
        "original": original_dialogues,
        "phase_merged": phase_merged,
        "output": output_dialogues,
        "deduped": deduped + sign_copies_removed,
        "lyric_merged": lyric_merged,
        "overlap_removed": overlap_removed,
        "full_copies_removed": full_copies_removed,
        "merged": merged,
        "text_copies_removed": text_copies_removed,
        "vector_copies_removed": vector_copies_removed,
        "vector_glows_removed": vector_glows_removed,
        "vector_frames_removed": vector_frames_removed,
        "vector_output": len(vector_events),
        "excess_vectors": excess_vectors,
        "dropped": dropped_drawings,
    }


def iter_inputs(targets: Iterable[str], recursive: bool) -> list[Path]:
    found: list[Path] = []
    for target in targets:
        p = Path(target)
        if p.is_file():
            if p.suffix.lower() in {".ass", ".ssa"} and not p.name.lower().endswith(".simple.ass"):
                found.append(p)
        elif p.is_dir():
            pattern = "**/*" if recursive else "*"
            for f in p.glob(pattern):
                if f.is_file() and f.suffix.lower() in {".ass", ".ssa"} and not f.name.lower().endswith(".simple.ass"):
                    found.append(f)
        else:
            print(f"Warning: not found: {p}")
    return sorted(set(found))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Simplify ASS/SSA subtitles at level 1 (aggressive) or 2 (retain static visuals)."
    )
    ap.add_argument("inputs", nargs="+", help="ASS/SSA file(s) or folder(s)")
    ap.add_argument("-r", "--recursive", action="store_true", help="scan folders recursively")
    ap.add_argument("--level", type=int, choices=(1, 2), default=1,
                    help="1: maximum reduction (default); 2: preserve static visual elements")
    ap.add_argument("--suffix", default=".simple", help="output suffix before extension (default: .simple; compatible with the MKV wrapper)")
    ap.add_argument("--max-blur", type=float, default=0.0,
                    help="retain/clamp blur up to this amount; default 0 removes blur")
    ap.add_argument("--short-duration", type=float, default=0.16,
                    help="max duration of a frame-animation piece in seconds (default 0.16)")
    ap.add_argument("--short-gap", type=float, default=0.08,
                    help="max gap between frame-animation pieces in seconds (default 0.08)")
    ap.add_argument("--max-drawing-chars", type=int, default=8000,
                    help="maximum vector path length to retain (default 8000)")
    ap.add_argument("--max-vectors-per-cue", type=int, default=32,
                    help="maximum distinct vector paths in one timed cue (default 32)")
    args = ap.parse_args()

    inputs = iter_inputs(args.inputs, args.recursive)
    if not inputs:
        ap.error("No .ass/.ssa files found")

    total_in = total_out = 0
    for src in inputs:
        dst = src.with_name(src.stem + args.suffix + src.suffix)
        stats = simplify_ass(src, dst, args.max_blur, args.short_duration, args.short_gap,
                             args.max_drawing_chars, args.max_vectors_per_cue, args.level)
        total_in += stats["original"]
        total_out += stats["output"]
        print(f"{src.name} -> {dst.name} (level {args.level})")
        print(
            f"  dialogue events: {stats['original']} -> {stats['output']} "
            f"(duplicate layers removed: {stats['deduped']}, "
            f"lyric fragments merged: {stats['lyric_merged']}, "
            f"glyph phases merged: {stats['phase_merged']}, "
            f"overlapping effects removed: {stats['overlap_removed']}, "
            f"full lyric copies removed: {stats['full_copies_removed']}, "
            f"frame pieces merged: {stats['merged']}, "
            f"duplicate sign text: {stats['text_copies_removed']}, "
            f"vector copies: {stats['vector_copies_removed']}, "
            f"covered contours: {stats['vector_glows_removed']}, "
            f"drawing animation frames: {stats['vector_frames_removed']}, "
            f"vectors retained: {stats['vector_output']}, "
            f"excess vector details removed: {stats['excess_vectors']}, "
            f"drawings/effects dropped: {stats['dropped']})"
        )

    if len(inputs) > 1:
        print(f"Total dialogue events: {total_in} -> {total_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
