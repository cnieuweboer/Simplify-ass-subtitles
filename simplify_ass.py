#!/usr/bin/env python3
"""Simplify ASS/SSA subtitles at two levels for limited renderers.

Level 1 favors maximum reduction; level 2 retains static sign styling and
static vector shapes. No third-party packages are required.

Ambiguous fragments keep their positions; drawing budgets are opt-in.
"""

from __future__ import annotations

import argparse
import re
import statistics
from dataclasses import dataclass, replace, field
from pathlib import Path
from typing import Iterable

__version__ = "2026.09.28.3"

OVERRIDE_RE = re.compile(r"\{([^}]*)\}")
NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
POS_RE = re.compile(r"\\pos\(\s*("+NUM+r")\s*,\s*("+NUM+r")\s*\)", re.I)

# Tags we retain when they are static.  Everything else is discarded.
# Static alpha is resolved alongside transforms; hidden layers are never
# made opaque merely by removing their animation.
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
    state: dict = field(default_factory=dict, compare=False)
    lyric: bool = False
    row: int = 0
    unit: float = 1.0

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


EVENT_FIELDS = ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]


def parse_dialogue(line: str, index: int, fields: list[str] | None = None) -> Event | None:
    line = line.lstrip()
    if ":" not in line:
        return None
    kind, rest = line.split(":", 1)
    if kind.lower() not in {"dialogue", "comment"}:
        return None
    fields = fields or EVENT_FIELDS
    parts = rest.lstrip().split(",", len(fields)-1)
    if len(parts) != len(fields):
        return None
    data = dict(zip(fields, parts))
    try:
        start_s, end_s = parse_time(data["start"]), parse_time(data["end"])
    except (ValueError, KeyError):
        return None
    return Event(kind.title(), data.get("layer", "0").strip(),
                 format_time(start_s), format_time(end_s), data.get("style", "Default").strip(),
                 data.get("name", data.get("actor", "")).strip(),
                 data.get("marginl", "0").strip(), data.get("marginr", "0").strip(),
                 data.get("marginv", "0").strip(), data.get("effect", "").strip(),
                 data.get("text", ""), start_s, end_s, index)


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


# ASS tag names must be recognized before their values: font and reset names
# are alphabetic values, not part of the tag name.
TAG_NAMES = sorted(set(SAFE_SIMPLE_TAGS) | {
    "alpha", "1a", "2a", "3a", "4a", "blur", "be", "p", "pbo",
    "frx", "fry", "fax", "fay", "pos", "move", "org", "clip", "iclip",
    "t", "fad", "fade", "k", "kf", "ko", "kt"}, key=len, reverse=True)
TAG_RE = re.compile(r"\\(" + "|".join(TAG_NAMES) + r")", re.I)
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


def tokenize_override(block: str) -> list[tuple[str, str]]:
    tokens = []
    i = 0
    while i < len(block):
        if block[i] != "\\":
            i += 1
            continue
        match = TAG_RE.match(block, i)
        if match is None:
            i = block.find("\\", i + 1)
            if i < 0:
                break
            continue
        name = match.group(1).lower()
        i = match.end()
        start = i
        if i < len(block) and block[i] == "(":
            depth = 1
            i += 1
            while i < len(block) and depth:
                depth += (block[i] == "(") - (block[i] == ")")
                i += 1
        else:
            while i < len(block) and block[i] != "\\":
                i += 1
        tokens.append((name, block[start:i].strip()))
    return tokens


DEFAULT_STATE = dict(fn="Arial", fs=20.0, fscx=100.0, fscy=100.0, fsp=0.0,
                     an=2.0, bord=0.0, shad=0.0, frz=0.0, frx=0.0, fry=0.0,
                     fax=0.0, fay=0.0, b=0.0, i=0.0, u=0.0, s=0.0, p=0.0,
                     **{"1c": "FFFFFF", "2c": "FFFFFF", "3c": "000000",
                        "4c": "000000", "1a": 0, "2a": 0, "3a": 0, "4a": 0})
STYLE_TAGS = dict(fontname="fn", fontsize="fs", bold="b", italic="i",
                 underline="u", strikeout="s", scalex="fscx", scaley="fscy",
                 spacing="fsp", angle="frz", outline="bord", shadow="shad",
                 alignment="an", marginl="marginl", marginr="marginr", marginv="marginv",
                 borderstyle="borderstyle", encoding="encoding")


def parse_styles(lines: list[str]) -> dict[str, dict]:
    result, fields, section = {}, [], ""
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            section = line.casefold()
        elif section in {"[v4+ styles]", "[v4 styles]"}:
            if line.lower().startswith("format:"):
                fields = [x.strip().casefold() for x in line.split(":", 1)[1].split(",")]
            elif line.lower().startswith("style:") and fields:
                values = dict(zip(fields, [x.strip() for x in line.split(":", 1)[1].split(",")]))
                state = DEFAULT_STATE.copy()
                for key, tag in STYLE_TAGS.items():
                    if key in values:
                        try:
                            state[tag] = values[key] if tag == "fn" else float(values[key])
                        except ValueError:
                            pass
                if section == "[v4 styles]":
                    state["an"] = {1:1,2:2,3:3,5:7,6:8,7:9,9:4,10:5,11:6}.get(int(state["an"]),2)
                for channel, key in enumerate(("primarycolour", "secondarycolour", "outlinecolour", "backcolour"), 1):
                    if key not in values:
                        continue
                    try:
                        value = values[key].strip().upper().rstrip("&")
                        color = int(value[2:], 16) if value.startswith("&H") else int(value)
                        state[f"{channel}c"] = f"{color & 0xffffff:06X}"
                        state[f"{channel}a"] = (color >> 24) & 255
                    except ValueError:
                        pass
                result[values.get("name", "Default")] = state
    return result


def apply_tag(state: dict, name: str, value: str, styles: dict, default: dict) -> None:
    name = {"c": "1c", "fr": "frz"}.get(name, name)
    if name == "r":
        state.clear()
        state.update(styles.get(value, default) if value else default)
    elif name == "fn":
        state[name] = value or default.get(name, "Arial")
    elif name in {"1c", "2c", "3c", "4c", "alpha", "1a", "2a", "3a", "4a"}:
        try:
            v = int(value.upper().removeprefix("&H").rstrip("&"), 16)
        except ValueError:
            return
        if name == "alpha":
            state.update({f"{ch}a": v & 255 for ch in range(1, 5)})
        else:
            state[name] = f"{v & 0xffffff:06X}" if name.endswith("c") else v & 255
    elif name in {"clip", "iclip"}:
        state.pop("iclip" if name == "clip" else "clip", None)
        state[name] = value
    elif name in {"pos", "org"}:
        nums = re.findall(NUMBER, value)
        if len(nums) == 2:
            state[name] = tuple(map(float, nums))
    elif name not in {"t", "clip", "iclip", "move", "fad", "fade"}:
        try:
            number = float(value) if value else default.get(name, 0.0)
        except ValueError:
            return
        if name == "a":
            name, number = "an", {1:1,2:2,3:3,5:7,6:8,7:9,9:4,10:5,11:6}.get(int(number),2)
        state[name] = number
        if name in {"bord", "shad"}:
            for axis in "xy":
                state.pop(axis + name, None)


def effective_state(text: str, default: dict | None = None, styles: dict | None = None) -> dict:
    default = default or DEFAULT_STATE
    state = default.copy()
    for block in OVERRIDE_RE.findall(text):
        for name, value in tokenize_override(block):
            apply_tag(state, name, value, styles or {}, default)
    return state


def render_tag(name: str, value) -> str:
    if name in {"1c", "2c", "3c", "4c"}:
        return f"\\{name}&H{value}&"
    if name in {"1a", "2a", "3a", "4a"}:
        return f"\\{name}&H{round(value):02X}&"
    if isinstance(value, tuple):
        return "\\" + name + "(" + ",".join(f"{x:g}" for x in value) + ")"
    return "\\" + name + (f"{value:g}" if isinstance(value, (float, int)) else str(value))


def safe_override(block: str, max_blur: float = 0.0) -> str:
    frozen = freeze_block(block, 1.0, DEFAULT_STATE, DEFAULT_STATE, {}, max_blur)[0]
    return "".join("\\"+name+value for name,value in tokenize_override(frozen)
                   if name not in {"p","pbo"})


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


def freeze_block(block: str, duration: float, initial: dict, default: dict,
                 styles: dict, max_blur: float) -> tuple[str, dict]:
    """Choose the longest visible stable interval, then resolve all its tags."""
    tokens = tokenize_override(block)
    transforms = []
    base = initial.copy()
    reset = None
    boundaries = {0.0, max(0.0, duration * 1000)}
    for name, value in tokens:
        if name == "t":
            body = value[1:-1]
            prefix, sep, tail = body.partition("\\")
            if not sep:
                continue
            try:
                args = [float(v.strip()) for v in prefix.rstrip(", ").split(",") if v.strip()]
            except ValueError:
                continue
            begin, end, accel = 0.0, duration * 1000, 1.0
            if len(args) == 1:
                accel = args[0]
            elif len(args) >= 2:
                begin, end = args[:2]
                if len(args) > 2:
                    accel = args[2]
            transforms.append((begin, end, max(.01, accel), tokenize_override("\\" + tail)))
            boundaries.update((max(0, min(duration*1000, begin)), max(0, min(duration*1000, end))))
        elif name == "move":
            nums = list(map(float, re.findall(NUMBER, value)))
            if len(nums) in (4, 6):
                base["pos"] = tuple(nums[:2])
                begin, end = nums[4:6] if len(nums) == 6 else (0, duration*1000)
                transforms.append((begin, end, 1, [("pos", f"({nums[2]},{nums[3]})")]))
                boundaries.update((max(0,min(duration*1000,begin)),max(0,min(duration*1000,end))))
        elif name not in {"fad", "fade"}:
            apply_tag(base, name, value, styles, default)
            if name == "r":
                reset = value
    def evaluate(at):
        state = base.copy()
        for begin, end, accel, changes in transforms:
            if at < begin:
                continue
            weight = 1.0 if end <= begin else min(1.0, max(0.0, (at-begin)/(end-begin))) ** accel
            target = state.copy()
            for name, value in changes:
                apply_tag(target, name, value, styles, default)
            for key, finish in target.items():
                start = state.get(key, finish)
                if finish == start:
                    continue
                if isinstance(start, (int,float)) and isinstance(finish,(int,float)):
                    state[key] = start + (finish-start)*weight
                elif isinstance(start,tuple) and isinstance(finish,tuple):
                    state[key] = tuple(a+(b-a)*weight for a,b in zip(start,finish))
                elif key in {"1c","2c","3c","4c"}:
                    state[key] = "".join(f"{round(int(start[i:i+2],16)+(int(finish[i:i+2],16)-int(start[i:i+2],16))*weight):02X}" for i in (0,2,4))
                elif weight >= 1:
                    state[key] = finish
        return state
    times = sorted(boundaries)
    candidates = []
    for start, end in zip(times,times[1:]):
        at = (start+end)/2
        state = evaluate(at)
        visible = (abs(state.get("fscx",100)) > .01 and abs(state.get("fscy",100)) > .01
                   and min(state.get("1a",0),state.get("3a",0),state.get("4a",0)) < 254)
        stable = not any(a < at < b for a,b,_,_ in transforms)
        # Entrance/exit fades often use transparent primary text while an
        # unused shadow channel remains opaque. Prefer the visible fill too.
        strength = 255 - state.get("1a",0)
        candidates.append(((visible, stable, strength > 16, end-start, strength),state))
    state = max(candidates,key=lambda item:item[0])[1] if candidates else base
    for name in ("blur","be"):
        if name in state:
            state[name] = min(max_blur,max(0,state[name]))
    allowed = SAFE_SIMPLE_TAGS | {"pos","org","p","pbo","frx","fry","fax","fay",
                                   "1a","2a","3a","4a","blur","be","clip","iclip"}
    reference = styles.get(reset, default) if reset else (default if reset is not None else initial)
    text = ("\\r" + reset) if reset is not None else ""
    # Keep state dependencies in insertion order, particularly bord/xbord.
    text += "".join(render_tag(k,v) for k,v in state.items()
                    if k in allowed and (k not in reference or v != reference[k]))
    return text,state


def visual_override(block: str, max_blur: float, duration: float | None = None) -> str:
    return freeze_block(block, duration or 1.0, DEFAULT_STATE, DEFAULT_STATE, {}, max_blur)[0]


def simplify_visual_text(text: str, max_blur: float, duration: float | None = None,
                         default: dict | None = None, styles: dict | None = None,
                         level: int = 2) -> tuple[str, str, int]:
    default = default or DEFAULT_STATE
    state = default.copy()
    output, visible = [], []
    drawing_chars = 0
    for part in re.split(r"(\{[^}]*\})", text):
        if part.startswith("{") and part.endswith("}"):
            block,state = freeze_block(part[1:-1],duration or 1, state,default,styles or {},max_blur)
            if level == 1:
                block = re.sub(r"\\p(?:\d+(?:\.\d*)?)(?![A-Za-z])", "", block)
            if block:
                output.append("{"+block+"}")
        elif part:
            if state.get("p",0) > 0:
                if level == 2:
                    output.append(part)
                    drawing_chars += len(part)
            else:
                output.append(part)
                visible.append(part)
    vis = "".join(visible).replace(r"\N"," ").replace(r"\n"," ").replace(r"\h"," ")
    return "".join(output), re.sub(r"\s+"," ",vis).strip(), drawing_chars


def get_pos(text: str) -> tuple[float, float] | None:
    matches = list(POS_RE.finditer(text))
    m = matches[-1] if matches else None
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


def text_height(e: Event) -> float:
    return max(e.unit, abs(e.state.get("fs",20) * e.state.get("fscy",100) / 100))


def x_key(e: Event) -> float:
    return round(get_pos(e.text)[0] / e.unit, 1) * e.unit


def assign_layout(events: list[Event], visible_map: dict[int, str]) -> None:
    """Cluster baselines by font height, then recognize repeated fragment rows."""
    positions = {e.source_index: get_pos(e.text) for e in events}
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind == "Dialogue" and positions[e.source_index] is not None:
            groups.setdefault((e.style,e.name), []).append(e)
    row_id = 0
    for group in groups.values():
        rows: list[list[Event]] = []
        for e in sorted(group, key=lambda item:positions[item.source_index][1]):
            y = positions[e.source_index][1]
            if not rows or abs(y-((positions[rows[-1][(len(rows[-1])-1)//2].source_index][1] + positions[rows[-1][len(rows[-1])//2].source_index][1])/2)) > .20*min(text_height(e),text_height(rows[-1][0])):
                rows.append([])
            rows[-1].append(e)
        for row in rows:
            row_id += 1
            for e in row:
                e.row = row_id
            cues: dict[tuple, list[Event]] = {}
            for e in row:
                cues.setdefault((e.start,e.end),[]).append(e)
            seeds = []
            for cue in cues.values():
                pieces = {}
                for e in cue:
                    text = visible_map.get(e.source_index, "")
                    if text:
                        pieces.setdefault(x_key(e), []).append(e)
                # Repeated layers at multiple positions are evidence of a
                # fragmented effect; short words alone are not.
                if len(pieces) >= 2 and all(
                    len({visible_map[e.source_index] for e in group}) == 1
                    and len(group) >= 2 for group in pieces.values()):
                    seeds.extend(cue)
            evidence = {}
            for seed in seeds:
                evidence.setdefault((x_key(seed), visible_map.get(seed.source_index, "")), []).append(seed)
            for e in row:
                text = visible_map.get(e.source_index, "")
                e.lyric = any(min(e.end_s, seed.end_s) > max(e.start_s, seed.start_s)
                    for seed in evidence.get((x_key(e), text), ()))


def inline_layout_key(e: Event) -> str:
    # A final state cannot describe earlier spans. Preserve their complete
    # tag sequence unless they have been proven identical.
    parts = re.split(r"(\{[^}]*\})", e.text)
    seen_text = changed = False
    for part in parts:
        if part.startswith("{"):
            changed |= seen_text
        elif part:
            if seen_text and changed:
                return e.text
            seen_text = True
    return ""


def placement_key(e: Event) -> tuple:
    return (tuple(float(v) if float(v) else e.state.get(k, 0)
                  for v,k in ((e.margin_l,"marginl"),(e.margin_r,"marginr"),(e.margin_v,"marginv"))),
            e.state.get("clip"), e.state.get("iclip"), inline_layout_key(e))


def text_layout_key(e: Event) -> tuple:
    return tuple((key,e.state.get(key,DEFAULT_STATE.get(key))) for key in
                 ("fn","fs","fscx","fscy","fsp","an","frz","frx","fry","fax","fay",
                  "b","i","u","s","q","org","pbo","borderstyle","encoding"))


def compatible_text_layout(a: Event, b: Event) -> bool:
    if placement_key(a) != placement_key(b):
        return False
    if str(a.state.get("fn","")).casefold()!=str(b.state.get("fn","")).casefold():
        return False
    for key in ("an","frz","frx","fry","fax","fay"):
        if a.state.get(key,DEFAULT_STATE.get(key))!=b.state.get(key,DEFAULT_STATE.get(key)):
            return False
    for key in ("fs","fscx","fscy"):
        x,y=a.state.get(key,DEFAULT_STATE[key]),b.state.get(key,DEFAULT_STATE[key])
        if abs(x-y)>.05*max(abs(x),abs(y),1e-6):
            return False
    return True


def event_identity_for_dedup(e: Event, visible: str) -> tuple:
    pos = get_pos(e.text)
    rounded_pos = None if pos is None else (round(pos[0] / e.unit, 1) * e.unit, round(pos[1] / e.unit, 1) * e.unit)
    return (
        e.layer, e.start, e.end, e.style, e.name,
        e.margin_l, e.margin_r, e.margin_v,
        visible, rounded_pos, text_layout_key(e), e.text,
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
        if e.kind != "Dialogue" or e.lyric or get_pos(e.text) is None:
            continue
        visible = visible_map.get(e.source_index, "")
        if visible:
            groups.setdefault((e.style, e.name, e.margin_l, e.margin_r,
                               e.margin_v, visible), []).append(e)

    def alpha(e: Event) -> int:
        return e.state.get("1a",0)

    def rank(e: Event) -> tuple:
        return (alpha(e), -int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
                -e.duration, e.source_index)

    removed: set[int] = set()
    for group in groups.values():
        ranks = {e.source_index: rank(e) for e in group}
        for e in group:
            x, y = get_pos(e.text)
            for other in group:
                if other is e or ranks[other.source_index] >= ranks[e.source_index] or not compatible_text_layout(e,other):
                    continue
                ox, oy = get_pos(other.text)
                # Only remove a copy covered for its entire lifetime by an
                # almost coincident copy of the same complete text.
                if (other.start_s <= e.start_s + 0.001
                        and other.end_s >= e.end_s - 0.001
                        and abs(ox - x) <= .06*min(text_height(e),text_height(other)) and abs(oy - y) <= .06*min(text_height(e),text_height(other))):
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
        if (e.kind != "Dialogue" or not e.lyric or pos is None ):
            output.append(e)
            continue
        key = (e.style, e.name, e.layer, e.margin_l, e.margin_r, e.margin_v,
               round(pos[0] / e.unit, 1) * e.unit, round(pos[1] / e.unit, 1) * e.unit, visible, text_layout_key(e), placement_key(e))
        groups.setdefault(key, []).append(e)
        row = (e.style, e.name, e.layer, e.row)
        glyph = (round(pos[0] / e.unit, 1) * e.unit, visible)
        starts.setdefault((*row, round(e.start_s, 2)), set()).add(glyph)
        ends.setdefault((*row, round(e.end_s, 2)), set()).add(glyph)
    # Identical letters can occupy the same position in consecutive lyrics.
    # A change in the surrounding glyphs marks a real lyric boundary.
    boundaries = {key for key in starts.keys() & ends.keys()
                  if starts[key] != ends[key]}
    removed = 0
    for group in groups.values():
        group.sort(key=lambda e: (e.start_s, e.end_s, e.source_index))
        current = group[0]
        for e in group[1:]:
            pos = get_pos(e.text)
            boundary = (e.style, e.name, e.layer, e.row, round(e.start_s, 2))
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
    if level == 2:
        return events, 0
    comments: dict[tuple[str, str, str], list[str]] = {}
    for e in events:
        if e.kind == "Comment":
            _, lyric = simplify_text(e.text)
            comments.setdefault((e.start, e.end, e.style), []).append(lyric)

    groups: dict[tuple[str, str, str, str, int], list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or not e.lyric:
            continue
        pos = get_pos(e.text)
        if pos is None or not visible_map.get(e.source_index):
            continue
        # Separate top/bottom lines, even when they share the same style and time.
        key = (e.start, e.end, e.style, e.name, e.row)
        groups.setdefault(key, []).append(e)

    removed: set[int] = set()
    replacements: dict[int, Event] = {}
    for (start, end, style, name, band), group in groups.items():
        positions: dict[float, list[Event]] = {}
        for e in group:
            positions.setdefault(x_key(e), []).append(e)
        if len(positions) < 2:
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
        lyric = next((s for s in candidates if norm(s) == norm(joined)), None)
        if lyric is None:
            # Some openings have no full-line Comment. Their short fragments
            # are repeated at the same x position in several effect layers.
            # Syllable effects may contain several letters per position.
            blanks = space_map.get((start, end, style, name, band), set())
            pieces = []
            xs = sorted(positions)
            if not blanks:
                # Without authored spaces or a matching full line, word
                # boundaries cannot reliably be recovered from proportional
                # glyph advances. Keep one static glyph at each position.
                for x in xs:
                    choices = positions[x]
                    chosen = min(choices, key=lambda e:(e.state.get("1a",0),
                                 -int(e.layer) if e.layer.lstrip("-").isdigit() else 0))
                    replacements[chosen.source_index] = replace(chosen, effect="")
                    removed.update(e.source_index for e in choices if e is not chosen)
                continue
            for index, x in enumerate(xs):
                if index and any(xs[index-1] < b < x for b in blanks):
                    pieces.append(" ")
                pieces.append(ordered[index])
            lyric = "".join(pieces)
        first = min(group, key=lambda e: e.source_index)
        # The style supplies normal alignment/margins. The original positions,
        # per-word colors and 1%-scale animation must not survive on this line.
        xs = [get_pos(e.text)[0] for e in group]
        y = statistics.median(get_pos(e.text)[1] for e in group)
        lyric = f"{{\\an5\\pos({(min(xs)+max(xs))/2:g},{y:g})}}" + lyric
        merged = replace(first, layer="0", effect="", text=lyric)
        replacements[first.source_index] = merged
        removed.update(e.source_index for e in group if e.source_index != first.source_index)
        visible_map[first.source_index] = OVERRIDE_RE.sub("", lyric)

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
             e.lyric and
             bool(norm(visible_map.get(e.source_index, "")))]
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or not e.lyric:
            continue
        pos = get_pos(e.text)
        if pos is not None and visible_map.get(e.source_index):
            key = (e.start, e.end, e.style, e.name, e.row)
            groups.setdefault(key, []).append(e)

    removed: set[int] = set()
    extended: dict[int, Event] = {}
    for (start, end, style, name, _band), group in groups.items():
        positions: dict[float, set[str]] = {}
        for e in group:
            positions.setdefault(x_key(e), set()).add(visible_map[e.source_index])
        if len(positions) < 3 or any(len(v) != 1 for v in positions.values()):
            continue
        assembled = norm("".join(next(iter(positions[x])) for x in sorted(positions)))
        for line in lines:
            if (line.row != _band or line in group or
                    placement_key(line) != placement_key(group[0]) or
                    line.style != style or line.name != name or norm(visible_map[line.source_index]) != assembled):
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
        if (e.kind == "Dialogue" and e.lyric and
                bool(norm(visible))):
            pos = get_pos(e.text)
            band = e.row if pos is not None else None
            grouped.setdefault((e.style, e.name, norm(visible), band, get_pos(e.text), placement_key(e)), []).append(e)

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
            pos = get_pos(best.text)
            if pos is not None:
                text = f"{{\\an5\\pos({pos[0]:g},{pos[1]:g})}}" + text
            replacements[first.source_index] = replace(
                first, layer="0", start=format_time(earlier), end=format_time(later),
                start_s=earlier, end_s=later, effect="",
                text=text)
            visible_map[first.source_index] = visible_map[best.source_index]
            removed.update(item.source_index for item in cluster if item != first)

    return [replacements.get(e.source_index, e) for e in events
            if e.source_index not in removed], len(removed)


def merge_frame_animation(events: list[Event], visible_map: dict[int, str],
                          max_piece_duration: float = 0.16,
                          max_gap: float = 0.08,
                          min_pieces: int = 3) -> tuple[list[Event], int]:
    # Group before joining: source-file event ordering is not rendering order.
    groups: dict[tuple,list[Event]] = {}
    output=[]
    for e in events:
        visible=visible_map.get(e.source_index, "")
        if e.kind != "Dialogue" or not visible:
            output.append(e)
            continue
        groups.setdefault((e.style,e.name,e.layer,visible),[]).append(e)
    removed=0
    for group in groups.values():
        frozen,count=freeze_vector_sequences(group,max_piece_duration,max_gap)
        output.extend(frozen)
        removed+=count
    return sorted(output,key=lambda e:e.source_index),removed


def freeze_vector_sequences(events: list[Event], short_duration: float = 0.16,
                            max_gap: float = 0.011) -> tuple[list[Event], int]:
    """Freeze frame-by-frame drawings, including their longer static hold.

    Match actual paths and static paint, not style names or colors specific
    to a show. Overlapping copies are ambiguous and remain separate.
    """
    changing = {"pos","fscx","fscy","frz","frx","fry","fax","fay",
                "1a","2a","3a","4a"}
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        key = (e.kind,e.layer,e.name,geometry_key(e.text),state_key(e,changing),placement_key(e))
        groups.setdefault(key,[]).append(e)

    def transparency(e: Event) -> int:
        return sum(e.state.get(f"{c}a",0) for c in range(1,5))

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
            if not components or e.start_s > latest_end + max_gap + 1e-6:
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


def geometry_key(text: str) -> tuple:
    """Compare vector tokens, not whitespace or decimal spelling."""
    raw = OVERRIDE_RE.sub("",text)
    return tuple(float(t) if re.fullmatch(NUMBER,t) else t.lower()
                 for t in re.findall(NUMBER+r"|[A-Za-z]",raw))


def state_key(e: Event, omit: set[str] | None = None) -> tuple:
    omit = omit or set()
    return tuple(sorted((k,tuple(round(x,6) for x in v) if isinstance(v,tuple)
                         else round(v,6) if isinstance(v,(int,float)) else v)
                        for k,v in e.state.items() if k not in omit))


def reduce_vector_layers(events: list[Event]) -> tuple[list[Event], int]:
    # No arbitrary two-layer limit. Only remove exact opaque duplicates.
    seen, result = set(), []
    for e in sorted(events,key=lambda x:(-int(x.layer) if x.layer.lstrip("-").isdigit() else 0,x.source_index)):
        key = (e.start,e.end,geometry_key(e.text),state_key(e),placement_key(e))
        opaque = all(e.state.get(f"{c}a",0)==0 for c in (1,3,4))
        if opaque and key in seen:
            continue
        if opaque:
            seen.add(key)
        result.append(e)
    return sorted(result,key=lambda e:e.source_index),len(events)-len(result)


def remove_covered_vector_glows(events: list[Event]) -> tuple[list[Event], int]:
    """Remove a lower shape only when the same footprint is painted opaquely.

    Partial transparency is not evidence of coverage. Different stroke widths,
    transforms, offsets, or drawing modes are retained.
    """
    paint = {f"{c}{kind}" for c in range(1,5) for kind in "ca"}
    groups: dict[tuple,list[Event]] = {}
    for e in events:
        groups.setdefault((e.start,e.end,geometry_key(e.text),state_key(e,paint),placement_key(e)),[]).append(e)
    removed = set()
    for group in groups.values():
        ordered = sorted(group,key=lambda e:(int(e.layer) if e.layer.lstrip("-").isdigit() else 0,e.source_index),reverse=True)
        opaque_above = False
        for e in ordered:
            if opaque_above:
                removed.add(e.source_index)
            opaque_above |= all(e.state.get(f"{c}a",0)==0 for c in (1,3,4))
    return [e for e in events if e.source_index not in removed],len(removed)


def drawing_extent(e: Event) -> float:
    # Control-point bounds are a conservative estimate for Bezier curves.
    # This is used only for an explicitly requested vector count budget.
    vals = [v for v in geometry_key(e.text) if isinstance(v,float)]
    if len(vals)<4 or len(vals)%2:
        return float("inf")  # Unrecognized geometry must not be lowest priority.
    xs,ys = vals[::2],vals[1::2]
    scale = 2**max(0,e.state.get("p",1)-1)
    return (max(xs)-min(xs))*(max(ys)-min(ys))*abs(e.state.get("fscx",100)*e.state.get("fscy",100))/10000/scale**2


def cap_vector_cues(events: list[Event], limit: int) -> tuple[list[Event], int]:
    if limit<=0:
        return events,0
    groups: dict[tuple,list[Event]] = {}
    for e in events:
        groups.setdefault((e.start,e.end),[]).append(e)
    result=[]
    for group in groups.values():
        result.extend(sorted(group,key=drawing_extent,reverse=True)[:limit])
    return sorted(result,key=lambda e:e.source_index),len(events)-len(result)


def reduce_text_layers(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    def primary_alpha(e: Event) -> int:
        return e.state.get("1a",0)

    def primary_color(e: Event) -> str:
        return e.state.get("1c","FFFFFF")

    def visible_layer(e: Event) -> tuple[int, int, int]:
        layer = int(e.layer) if e.layer.isdigit() else 0
        return (-primary_alpha(e), layer, -e.source_index)

    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or inline_layout_key(e):
            groups.setdefault((e.source_index,), []).append(e)
            continue
        key = (e.start, e.end, e.style, e.name, get_pos(e.text),
               visible_map.get(e.source_index, ""), text_layout_key(e), placement_key(e))
        groups.setdefault(key, []).append(e)
    output = []
    for group in groups.values():
        opaque = [e for e in group if primary_alpha(e) == 0]
        if not opaque or any(0 < primary_alpha(e) < 255 for e in group):
            # Translucent paints combine; choosing one changes their result.
            output.extend(group)
            continue
        chosen = max(opaque, key=lambda e: (
            int(e.layer) if e.layer.lstrip("-").isdigit() else 0, e.source_index))
        output.append(chosen)
    return sorted(output, key=lambda e: e.source_index), len(events) - len(output)



def simplify_ass(path: Path, output: Path, max_blur: float,
                 short_duration: float, short_gap: float,
                 max_drawing_chars: int = 0,
                 max_vectors_per_cue: int = 0,
                 level: int = 1) -> dict[str, int]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = raw.splitlines()

    styles = parse_styles(lines)
    resolution_y = next((float(line.split(":",1)[1]) for line in lines
                         if line.strip().lower().startswith("playresy:")), 288.0)
    unit = resolution_y / 1080.0
    parsed_by_line = {}
    event_fields = EVENT_FIELDS
    section = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.lower()
        elif section == "[events]" and stripped.lower().startswith("format:"):
            event_fields = [x.strip().lower() for x in stripped.split(":",1)[1].split(",")]
        elif section == "[events]":
            e = parse_dialogue(line,idx,event_fields)
            if e is not None:
                e.unit = unit
                e.state = effective_state(e.text,styles.get(e.style,DEFAULT_STATE),styles)
                parsed_by_line[idx] = e
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
        new_text, visible, drawing_chars = simplify_visual_text(
            e.text, max_blur, e.duration, styles.get(e.style,DEFAULT_STATE), styles, level)
        e.state = effective_state(new_text,styles.get(e.style,DEFAULT_STATE),styles)
        visible_map[idx] = visible
        if drawing_chars:
            if max_drawing_chars <= 0 or drawing_chars <= max_drawing_chars:
                vector_events.append(replace(e, text=new_text, effect=""))
            else:
                dropped_drawings += 1
            continue
        if not visible:
            # Position-only events in per-character FX mark word spaces in some
            # generated lyrics. Keep their locations for text reconstruction.
            pos = get_pos(new_text)
            if (pos is not None and
                    not re.search(r"\\p\d", e.text, re.I)):
                key = (e.start, e.end, e.style, e.name, e.row)
                space_map.setdefault(key, set()).add(round(pos[0] / e.unit, 1) * e.unit)
                blank_events.append(replace(e, text=new_text))
            # A dialogue event with no remaining text is generally a vector drawing/effect.
            dropped_drawings += 1
            continue
        simplified_events.append(replace(e, text=new_text, effect=""))

    assign_layout(simplified_events + blank_events, visible_map)
    space_map.clear()
    for e in blank_events:
        pos = get_pos(e.text)
        space_map.setdefault((e.start,e.end,e.style,e.name,e.row),set()).add(pos[0])

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
        key = (e.start, e.end, e.style, e.name, e.row)
        space_map.setdefault(key, set()).add(round(pos[0] / e.unit, 1) * e.unit)

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
    for e in simplified_events:
        e.state = effective_state(e.text, styles.get(e.style, DEFAULT_STATE), styles)
    overlap_removed = full_copies_removed = 0
    if level == 1:
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
                "merged", "dropped", "overlap_removed", "full_copies_removed", "phase_merged",
                "text_copies_removed", "vector_copies_removed", "vector_glows_removed",
                "vector_frames_removed", "vector_output", "excess_vectors")}

    first_event_line = event_line_indices[0]
    last_event_line = event_line_indices[-1]
    before = lines[:first_event_line]
    after = lines[last_event_line + 1:]

    rendered = []
    for e in simplified_events:
        data = dict(zip(EVENT_FIELDS,e.fields()))
        data.update(actor=e.name, marked="Marked=0")
        rendered.append(f"{e.kind}: " + ",".join(data.get(key,"") for key in event_fields))

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
    ap.add_argument("--version", action="version", version=__version__)
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
    ap.add_argument("--max-drawing-chars", type=int, default=0,
                    help="optional vector path character budget; 0 retains all paths (default)")
    ap.add_argument("--max-vectors-per-cue", type=int, default=0,
                    help="optional vector count budget per cue; 0 retains all paths (default)")
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
