#!/usr/bin/env python3
"""Simplify complex ASS/SSA subtitles for limited hardware renderers.

Main goals:
  * remove expensive ASS animation/effect tags
  * collapse duplicate effect layers (e.g. dozens of clipped copies of one syllable)
  * flatten frame-by-frame moving signs into one static event
  * drop vector-drawing-only events
  * preserve ordinary dialogue, styles, static positioning, fonts/colors and basic formatting

No third-party packages are required.
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
                not e.style.startswith(("OP_", "ED_")) or pos is None or len(visible) > 4):
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
                       space_map: dict[tuple, set[float]]) -> tuple[list[Event], int]:
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
            repeated_syllables = (style == "OP_ROM" and
                                  all(1 <= len(part) <= 3 for part in ordered) and
                                  all(len(positions[x]) >= 2 for x in positions))
            if len(ordered) < 5 or not (single_letters or repeated_syllables):
                continue
            blanks = space_map.get((start, end, style, name, band), set())
            pieces = []
            xs = sorted(positions)
            inferred_spaces: set[int] = set()
            if not blanks and style.startswith(("OP_", "ED_")) and len(xs) >= 8:
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
             e.style.startswith(("OP_", "ED_")) and
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
        if (e.kind == "Dialogue" and e.style.startswith(("OP_", "ED_")) and
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
            replacements[first.source_index] = replace(
                first, layer="0", start=format_time(earlier), end=format_time(later),
                start_s=earlier, end_s=later, effect="",
                text=visible_map[best.source_index])
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


def simplify_ass(path: Path, output: Path, max_blur: float,
                 short_duration: float, short_gap: float) -> dict[str, int]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = raw.splitlines()

    parsed_by_line: dict[int, Event] = {}
    simplified_events: list[Event] = []
    visible_map: dict[int, str] = {}
    space_map: dict[tuple, set[float]] = {}
    dropped_drawings = 0
    original_dialogues = 0
    blank_events: list[Event] = []

    for idx, line in enumerate(lines):
        e = parse_dialogue(line, idx)
        if e is None:
            continue
        parsed_by_line[idx] = e
        if e.kind != "Dialogue":
            simplified_events.append(e)
            continue
        original_dialogues += 1
        # The Grain font is used as a moving texture inside letter-shaped
        # vector clips. Removing its clip would expose the texture's carrier
        # string as random text, so discard that decorative layer first.
        if (e.effect.lower() == "fx" and
                re.search(r"\\fnGrain(?=\\|})", e.text, re.I) and
                re.search(r"\\clip\(\s*(?:\d+\s*,\s*)?m\s", e.text, re.I)):
            dropped_drawings += 1
            continue
        new_text, visible = simplify_text(e.text, max_blur=max_blur)
        visible_map[idx] = visible
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

    # Reconstruct each glyph's complete lifetime before trying to assemble rows.
    simplified_events, phase_merged = coalesce_lyric_phases(
        simplified_events, visible_map)
    joined_blanks, _ = coalesce_lyric_phases(blank_events, visible_map)
    for e in joined_blanks:
        pos = get_pos(e.text)
        key = (e.start, e.end, e.style, e.name, round(pos[1] / 25))
        space_map.setdefault(key, set()).add(round(pos[0], 1))

    # Work in chronological/source order. Effect-layer dedup is safe regardless of adjacency.
    simplified_events, deduped = deduplicate_layers(simplified_events, visible_map)
    simplified_events, lyric_merged = merge_timed_lyrics(simplified_events, visible_map, space_map)
    simplified_events, overlap_removed = collapse_matching_lyric_layers(
        simplified_events, visible_map)
    simplified_events, full_copies_removed = collapse_full_lyric_copies(
        simplified_events, visible_map)
    simplified_events, merged = merge_frame_animation(
        simplified_events, visible_map,
        max_piece_duration=short_duration,
        max_gap=short_gap,
    )

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
        "deduped": deduped,
        "lyric_merged": lyric_merged,
        "overlap_removed": overlap_removed,
        "full_copies_removed": full_copies_removed,
        "merged": merged,
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
        description="Simplify complex ASS/SSA subtitles for hardware/TV renderers."
    )
    ap.add_argument("inputs", nargs="+", help="ASS/SSA file(s) or folder(s)")
    ap.add_argument("-r", "--recursive", action="store_true", help="scan folders recursively")
    ap.add_argument("--suffix", default=".simple", help="output suffix before extension (default: .simple)")
    ap.add_argument("--max-blur", type=float, default=0.0,
                    help="retain/clamp blur up to this amount; default 0 removes blur")
    ap.add_argument("--short-duration", type=float, default=0.16,
                    help="max duration of a frame-animation piece in seconds (default 0.16)")
    ap.add_argument("--short-gap", type=float, default=0.08,
                    help="max gap between frame-animation pieces in seconds (default 0.08)")
    args = ap.parse_args()

    inputs = iter_inputs(args.inputs, args.recursive)
    if not inputs:
        ap.error("No .ass/.ssa files found")

    total_in = total_out = 0
    for src in inputs:
        dst = src.with_name(src.stem + args.suffix + src.suffix)
        stats = simplify_ass(src, dst, args.max_blur, args.short_duration, args.short_gap)
        total_in += stats["original"]
        total_out += stats["output"]
        print(f"{src.name} -> {dst.name}")
        print(
            f"  dialogue events: {stats['original']} -> {stats['output']} "
            f"(duplicate layers removed: {stats['deduped']}, "
            f"lyric fragments merged: {stats['lyric_merged']}, "
            f"glyph phases merged: {stats['phase_merged']}, "
            f"overlapping effects removed: {stats['overlap_removed']}, "
            f"full lyric copies removed: {stats['full_copies_removed']}, "
            f"frame pieces merged: {stats['merged']}, drawings/effects dropped: {stats['dropped']})"
        )

    if len(inputs) > 1:
        print(f"Total dialogue events: {total_in} -> {total_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
