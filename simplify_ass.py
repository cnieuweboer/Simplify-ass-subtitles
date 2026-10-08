#!/usr/bin/env python3
"""Simplify ASS/SSA subtitles for limited renderers.

Requires Python 3.10 or newer.

Level 1 favors maximum reduction, retaining simple opaque caption backdrops;
Level 2 is deprecated; its static-sign/vector pipeline remains for reference
and compatibility. Basic simplification requires only the standard library.
Optional font-based word spacing uses Pillow and fonttools. If RAQM is absent
(for example on Windows), uharfbuzz supplies the same shaping measurements:
    python -m pip install Pillow fonttools uharfbuzz
    python simplify_ass.py input.ass --level 1 --font-mkv episode.mkv
Or supply extracted fonts with --fonts-dir FOLDER. Exact installed fonts and
fonts/ beside the script or input are also searched. No font substitution or
word dictionary is used. The MKV option requires MKVToolNix in PATH.

Ambiguous fragments keep their positions; drawing budgets are opt-in.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.exit("simplify_ass.py requires Python 3.10 or newer "
             f"(running {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}).")

import argparse
import collections
import codecs
from bisect import bisect_left, bisect_right
import math
import logging
import re
import statistics
import time
import unicodedata
from dataclasses import dataclass, replace as dataclass_replace, field
from io import BytesIO
from itertools import islice
from pathlib import Path
from typing import Iterable

__version__ = "2026.10.09.102"
GENERATED_MARKER = "; Simplified by simplify_ass.py"


def mark_generated(lines: list[str]) -> list[str]:
    """Place one output marker inside Script Info, relocating legacy markers."""
    lines = [line for line in lines if not line.strip().casefold().startswith(
        "; static vector support prototype ")]
    if not any(line.strip().casefold() == "[script info]" for line in lines):
        return lines
    marked = [line for line in lines if line.strip() != GENERATED_MARKER]
    header = next(i for i,line in enumerate(marked)
                  if line.strip().casefold() == "[script info]")
    marked.insert(header+1,GENERATED_MARKER)
    return marked


class _FontTimestampFilter(logging.Filter):
    """Hide harmless fontTools 'head' date warnings from embedded fonts."""

    def filter(self, record):
        return not (record.levelno == logging.WARNING and
                    record.msg in {
                        "'%s' timestamp seems very low; regarding as unix timestamp",
                        "'%s' timestamp out of range; ignoring top bytes",
                    })


logging.getLogger("fontTools.ttLib.tables._h_e_a_d").addFilter(_FontTimestampFilter())

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

@dataclass(frozen=True, kw_only=True)
class SimplifyConfig:
    """Named, immutable settings shared by a subtitle simplification batch.

    Level 2 is deprecated and retained for compatibility.
    """
    level: int = 1
    max_blur: float = 0.0
    short_duration: float = 0.16
    short_gap: float = 0.08
    max_drawing_chars: int = 0
    max_vectors_per_cue: int = 0
    encoding: str | None = None
    scroll_concurrency_limit: int = 32


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
    defaults: dict = field(default_factory=dict, compare=False, repr=False)
    styles: dict = field(default_factory=dict, compare=False, repr=False)
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


@dataclass
class TextRow:
    """Shared text, geometry and cue provenance for reconstruction and FX.

    Source rows retain their authored interval and alternate paint rows.
    Reconstructed/virtual rows carry the same anchors into effect removal;
    that stage never has to rediscover their fragment layout.
    """
    base: Event
    pieces: list[tuple[Event, str, tuple[float, float]]]
    paint_rows: list[list[Event]] = field(default_factory=list)
    source_anchors: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    foreground: list[Event] = field(default_factory=list)
    confirmed: bool = False
    virtual: bool = False
    # Optional protected cue core proved by source phase correspondence.
    # The overlap pass preserves every activation point inside this interval.
    phase_core: tuple[float, float] | None = None

    @property
    def anchors(self) -> list[tuple[str, float]]:
        return [(text, pos[0]) for _, text, pos in self.pieces]


def peak_concurrent_events(events: Iterable[Event]) -> int:
    """Count active Dialogue events, including drawings, on [start, end).

    Comments and empty/reversed intervals do not render. Aggregate equal
    boundaries so touching captions never count as overlapping, regardless
    of source order. Use serialized times so rounding a generated boundary
    cannot create a phantom overlap. Only distinct timestamps are sorted.
    """
    boundaries: dict[float,int] = {}
    for e in events:
        if e.kind != "Dialogue":
            continue
        start,end = parse_time(e.start),parse_time(e.end)
        if start < end:
            boundaries[start] = boundaries.get(start,0)+1
            boundaries[end] = boundaries.get(end,0)-1
    active = peak = 0
    for time in sorted(boundaries):
        active += boundaries[time]
        peak = max(peak,active)
    return peak


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
    kerning = False
    canvas = {}
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            section = line.casefold()
        elif section == "[script info]" and line.lower().startswith("kerning:"):
            kerning = line.split(":",1)[1].strip().casefold() in {"yes","1","-1","true"}
        elif section == "[script info]" and line.lower().startswith(("playresx:","playresy:")):
            key,value = line.split(":",1)
            try:
                dimension = float(value)
                if math.isfinite(dimension) and dimension > 0:
                    canvas[key.lower()] = dimension
            except ValueError:
                pass
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
    for state in result.values():
        state["kerning"] = kerning
        if "playresx" in canvas and "playresy" in canvas:
            state["_canvas"] = (canvas["playresx"],canvas["playresy"])
    return result


def apply_tag(state: dict, name: str, value: str, styles: dict, default: dict,
              event_tags: bool = True) -> None:
    name = {"c": "1c", "fr": "frz"}.get(name, name)
    original_default = default
    default = styles.get(state.get("_reset_style",""),default)
    if name == "r":
        # A style reset changes glyph paint/geometry, not line-wide placement,
        # clipping, alignment, wrapping or drawing mode (libass reset context).
        retained = {k:v for k,v in state.items() if k in
                    {"an","pos","org","clip","iclip","q","p","pbo",
                     "_alignment_set"}}
        state.clear()
        state.update(styles.get(value,original_default) if value else original_default)
        state.update(retained)
        state["_reset_style"] = value if value in styles else ""
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
        if len(nums) == 2 and (not event_tags or name not in state):
            state[name] = tuple(map(float, nums))
    elif name in {"a","an"}:
        if state.get("_alignment_set"):
            return
        # Renderer integer parsing consumes even an invalid first alignment.
        match = re.match(r"[-+]?\d+",value)
        number = int(match[0]) if match else 0
        if name == "a" and 1 <= number <= 11:
            number = 5 if number in (4,8) else number
            number = {1:1,2:2,3:3,5:7,6:8,7:9,9:4,10:5,11:6}[number]
        elif name == "a" or not 1 <= number <= 9:
            number = default.get("an",2)
        state["_alignment_set"] = True
        state["an"] = number
    elif name not in {"t", "clip", "iclip", "move", "fad", "fade"}:
        try:
            number = float(value) if value else default.get(name, 0.0)
        except ValueError:
            return
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


def replace_event(event: Event, **changes) -> Event:
    """Keep rendered overrides and their cached effective state synchronized."""
    if "text" in changes or "style" in changes:
        style = changes.get("style", event.style)
        default = event.styles.get(style, event.defaults or DEFAULT_STATE)
        changes["state"] = effective_state(changes.get("text", event.text),
                                           default, event.styles)
    return dataclass_replace(event, **changes)


def render_tag(name: str, value) -> str:
    if name in {"1c", "2c", "3c", "4c"}:
        return f"\\{name}&H{value}&"
    if name in {"1a", "2a", "3a", "4a"}:
        return f"\\{name}&H{round(value):02X}&"
    if isinstance(value, tuple):
        return "\\" + name + "(" + ",".join(f"{x:g}" for x in value) + ")"
    return "\\" + name + (f"{value:g}" if isinstance(value, (float, int)) else str(value))


def aggressive_caption(state: dict, text: str,
                       outline_states: Iterable[dict] | None = None, **layout) -> str:
    """Retain the selected foreground and an unambiguous contrasting outline.

    Unclipped visible primary paint supplies the fill; transparent or masked
    textures cannot. Opaque glyph contours supply the outline. Ambiguous or
    low-contrast contours use whichever of black/white contrasts with the fill.
    """
    state = {**state,**layout}
    canvas, pos = state.get("_canvas"),state.get("pos")
    if (canvas is not None and pos is not None and state.get("borderstyle",1) == 1 and
            "clip" not in state and "iclip" not in state and
            state.get("4a",DEFAULT_STATE.get("4a",0)) < 255 and
            not str(state.get("fn","")).startswith("@") and
            all(abs(state.get(k,0)) <= .001 for k in ("frz","frx","fry","fax","fay"))):
        # Generated text can be parked off-canvas while its offset shadow is
        # the actual visible caption. Transfer that paint and position before
        # removing shadows. An on-canvas foreground keeps its own position.
        height = abs(state.get("fs",20)*state.get("fscy",100)/100)
        width_bound = 4*abs(state.get("fs",20)*state.get("fscx",100)/100)*max(1,len(text))
        dx = state.get("xshad",state.get("shad",0))
        dy = state.get("yshad",state.get("shad",0))
        shadow = (pos[0]+dx,pos[1]+dy)
        foreground_outside = (pos[1] < -2*height or pos[1] > canvas[1]+2*height or
                              pos[0] < -width_bound or pos[0] > canvas[0]+width_bound)
        if (foreground_outside and 0 <= shadow[0] <= canvas[0] and
                0 <= shadow[1] <= canvas[1] and (dx or dy)):
            state.update(pos=shadow,**{"1c":state.get("4c","FFFFFF"),
                                     "1a":state.get("4a",0)})
    fill = str(state.get("1c","FFFFFF")).upper()
    if (state.get("1a",0) >= 255 or "clip" in state or "iclip" in state or
            not re.fullmatch(r"[0-9A-F]{6}",fill)):
        fill = "FFFFFF"
    def luminance(color):
        # ASS colors are BGR; convert sRGB channels to linear luminance.
        rgb = [int(color[i:i+2],16)/255 for i in (4,2,0)]
        linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    fill_luma = luminance(fill)
    colors = set()
    for source in ([state] if outline_states is None else outline_states):
        # Resolve defaults too: callers normally supply effective ASS state.
        source = {**DEFAULT_STATE, **source}
        if (source.get("borderstyle",1) != 1 or source.get("3a",0) != 0 or
                max(source.get("xbord",source.get("bord",0)),
                    source.get("ybord",source.get("bord",0))) <= 0 or
                "clip" in source or "iclip" in source or
                any(source.get(k,DEFAULT_STATE.get(k)) !=
                    state.get(k,DEFAULT_STATE.get(k))
                    for k in ("fn","fs","b","i","frz","frx","fry","fax","fay"))):
            continue
        color = str(source.get("3c","000000")).upper()
        if re.fullmatch(r"[0-9A-F]{6}",color):
            colors.add(color)
    # Choose the more legible neutral outline when source contours conflict.
    outline = "000000" if (fill_luma+.05)/.05 >= 1.05/(fill_luma+.05) else "FFFFFF"
    if len(colors) == 1:
        candidate = next(iter(colors))
        outline_luma = luminance(candidate)
        if (max(fill_luma,outline_luma)+.05)/(min(fill_luma,outline_luma)+.05) >= 3:
            outline = candidate
    state = {**DEFAULT_STATE, **state,
             "1c":fill, "3c":outline, "1a":0, "3a":0,
             "bord":2, "shad":0, "blur":0, "be":0}
    keys = ("an","pos","org","fn","fs","fscx","fscy","fsp","b","i",
            "u","s","frz","frx","fry","fax","fay",
            "1c","3c","1a","3a","bord","shad","blur","be")
    return "{"+"".join(render_tag(k,state[k]) for k in keys if k in state)+"}"+text


def safe_override(block: str, max_blur: float = 0.0) -> str:
    frozen = freeze_block(block, 1.0, DEFAULT_STATE, DEFAULT_STATE, {}, max_blur)[0]
    return "".join("\\"+name+value for name,value in tokenize_override(frozen)
                   if name not in {"p","pbo"})


def simplify_text(text: str, max_blur: float = 0.0, *,
                  visible_only: bool = False) -> tuple[str, str]:
    """Return (simplified ASS text, visible text), excluding vector sections.

    With visible_only, the first result is empty and overrides are not frozen
    or rendered. Drawing switches and visible whitespace keep the same rules.
    """
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
            if not visible_only:
                safe = safe_override(block, max_blur=max_blur)
                # Never retain \p itself (not in whitelist).
                if safe:
                    output.append("{" + safe + "}")
        else:
            if drawing_mode > 0:
                continue
            if not visible_only:
                output.append(part)
            visible.append(part)

    simplified = ""
    if not visible_only:
        simplified = "".join(output)
        # Drop empty override blocks and custom pseudo-blocks such as {=0}.
        simplified = re.sub(r"\{\s*\}", "", simplified)
        simplified = re.sub(r"\{[^\\{}][^{}]*\}", "", simplified)
    vis = "".join(visible)
    vis = vis.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
    vis = re.sub(r"\s+", " ", vis).strip()
    return simplified, vis


def transform_weight(begin: float, end: float, accel: float, at: float) -> float:
    """Use the same timing and acceleration for every transform evaluator."""
    return 1.0 if end <= begin else min(1.0,max(0.0,(at-begin)/(end-begin))) ** accel


def interpolate_transform_value(key: str, start, finish, weight: float,
                                color_channels: dict | None = None):
    """Blend one field, preserving metadata, rounding and discrete-tag rules.

    The ordered sampler supplies a block-local colour decoding cache. The
    arithmetic and validation behavior are shared with single-time sampling.
    """
    if finish == start:
        return start
    if key.startswith('_'):
        return finish
    if isinstance(start,(int,float)) and isinstance(finish,(int,float)):
        return start+(finish-start)*weight
    if isinstance(start,tuple) and isinstance(finish,tuple):
        return tuple(a+(b-a)*weight for a,b in zip(start,finish))
    if key in {'1c','2c','3c','4c'}:
        if weight == 1 and color_channels is not None:
            # The ordered caller validates both colour strings before using
            # a cache. A completed blend is the target in canonical casing.
            return finish.upper()
        channels = []
        for color in (start,finish):
            decoded = color_channels.get(color) if color_channels is not None else None
            if decoded is None:
                decoded = tuple(int(color[i:i+2],16) for i in (0,2,4))
                if color_channels is not None:
                    color_channels[color] = decoded
            channels.append(decoded)
        return ''.join(f'{round(a+(b-a)*weight):02X}'
                       for a,b in zip(*channels))
    return finish if weight >= 1 else start


def sample_transform_state(base: dict, transforms: list, at: float,
                           styles: dict, default: dict) -> dict:
    """Resolve ordered transforms at one instant without modifying the base."""
    state = base.copy()
    for begin, end, accel, changes in transforms:
        if at < begin or not changes:
            continue
        weight = transform_weight(begin,end,accel,at)
        if len(changes) == 1 and changes[0][0] in {'fr','frz','frx','fry'} and changes[0][1]:
            name,value = changes[0]
            key = 'frz' if name == 'fr' else name
            try: finish = float(value)
            except ValueError: continue
            start = state.get(key,finish)
            if finish != start:
                state[key] = interpolate_transform_value(key,start,finish,weight)
            continue
        target = state.copy()
        for name, value in changes:
            apply_tag(target, name, value, styles, default,event_tags=False)
        for key, finish in target.items():
            start = state.get(key, finish)
            if finish == start:
                continue
            state[key] = interpolate_transform_value(key,start,finish,weight)
    return state


def sample_transform_states(base: dict, transforms: list, times: Iterable[float],
                            styles: dict, default: dict) -> Iterable[dict]:
    """Sample an ordered timeline, retaining completed independent updates.

    Constant paint/geometry tags affect independent state fields. Parse their
    targets once and advance each field's completed prefix as time increases.
    Overlapping or unsorted updates still replay in source order after that
    prefix. Resets, clipping and other context-dependent tags use the original
    evaluator, as do nonfinite inputs and unordered sample times.
    """
    times = list(times)
    simple = {'c','1c','2c','3c','4c','alpha','1a','2a','3a','4a',
              'fn','fs','fscx','fscy','fsp','b','i','u','s','fr','frz','frx','fry',
              'fax','fay','bord','xbord','ybord','shad','xshad','yshad',
              'blur','be','pos','org','p','pbo','q','fe'}
    if (any(not math.isfinite(t) for t in times) or
            any(b < a for a,b in zip(times,times[1:])) or
            any(not all(math.isfinite(v) for v in (a,b,accel)) or accel <= 0 or
                any(name not in simple for name,_ in changes)
                for a,b,accel,changes in transforms)):
        for at in times:
            yield sample_transform_state(base,transforms,at,styles,default)
        return
    fields = {}
    targets = []
    for begin,end,accel,changes in transforms:
        target = {'_reset_style':base.get('_reset_style','')}
        for name,value in changes:
            apply_tag(target,name,value,styles,default,event_tags=False)
        for key,finish in target.items():
            if key == '_reset_style':
                continue
            targets.append((key,finish))
            # The original sampler leaves absent fields absent: their implicit
            # starting value equals the target, so no update is assigned.
            if key in base:
                fields.setdefault(key,[]).append((begin,end,accel,finish))
    colors = {'1c','2c','3c','4c'}
    values = [(key,base[key]) for key in fields]+targets
    if (any(isinstance(value,(int,float)) and not math.isfinite(value)
            for value in base.values()) or any(
           (isinstance(value,(int,float)) and not math.isfinite(value)) or
           (isinstance(value,tuple) and any(not math.isfinite(v) for v in value)) or
           (key in colors and not re.fullmatch(r'[0-9A-Fa-f]{6}',str(value)))
           for key,value in values)):
        for at in times:
            yield sample_transform_state(base,transforms,at,styles,default)
        return
    color_channels = {}
    prefixes = {key:0 for key in fields}
    completed = {key:base[key] for key in fields}
    ordered = {key:all(a[0] <= b[0] for a,b in zip(updates,updates[1:]))
               for key,updates in fields.items()}
    for at in times:
        state = base.copy()
        for key,updates in fields.items():
            index = prefixes[key]
            value = completed[key]
            while index < len(updates):
                begin,end,accel,finish = updates[index]
                if at < max(begin,end):
                    break
                value = interpolate_transform_value(key,value,finish,1.0,color_channels)
                index += 1
            prefixes[key],completed[key] = index,value
            for offset in range(index,len(updates)):
                begin,end,accel,finish = updates[offset]
                if at < begin:
                    if ordered[key]:
                        break
                    continue
                weight = transform_weight(begin,end,accel,at)
                value = interpolate_transform_value(key,value,finish,weight,color_channels)
            state[key] = value
        yield state


def unrotated_text_state(state: dict) -> bool:
    """Treat whole turns on every axis as zero rotation."""
    return all(math.isfinite(state.get(k,0)) and
               abs(math.remainder(state.get(k,0),360)) <= .001
               for k in ('frz','frx','fry'))


def upright_text_state(state: dict, *, include_shadow: bool = False,
                       include_outline: bool = False, minimum_opacity: int = 16) -> bool:
    """Recognize readable, unflipped text with no rotation on any axis.

    Pose selection may also use letters painted entirely by an offset shadow.
    Other callers still require visible primary text by default.
    """
    cutoff = 255-minimum_opacity
    visible = state.get('1a',0) < cutoff
    if include_outline and not visible and state.get('3a',0) < cutoff:
        visible = max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0
    if (include_shadow and not visible and state.get('1a',0) >= 254 and
            state.get('3a',0) >= 254 and state.get('4a',0) < cutoff and
            state.get('borderstyle',1) == 1 and
            'clip' not in state and 'iclip' not in state):
        offsets = [state.get(k,state.get('shad',0)) for k in ('xshad','yshad')]
        visible = all(math.isfinite(v) for v in offsets) and any(offsets)
    return (visible and
            all(state.get(k,100) > .01 for k in ('fscx','fscy')) and
            unrotated_text_state(state))


def animated_shadow_painted_source(e: Event, sources: dict[int,Event] | None,
                                   animated: set[int]) -> bool:
    """Recognize source text painted exclusively by an animated shadow."""
    original = (sources or {}).get(e.source_index)
    if original is None or original.kind != 'Dialogue' or e.source_index not in animated:
        return False
    state = effective_state(original.text,original.defaults,original.styles)
    if (state.get('1a',0) < 254 or state.get('3a',0) < 254 or
            state.get('borderstyle',1) != 1 or
            state.get('p',0) or any(k in state for k in ('clip','iclip','org')) or
            get_pos(original.text) is None or re.search(r'\\move\s*\(',original.text,re.I) or
            inline_layout_key(dataclass_replace(original,state=state)) or
            not any(abs(state.get(k,state.get('shad',0))) > 0 for k in ('xshad','yshad'))):
        return False
    return not any(tag in {'alpha','1a','3a','r'}
                   for name,value in event_override_tokens(original) if name == 't'
                   for tag,_ in tokenize_override(value.strip('()')))


def upright_transform_pose(base: dict, transforms: list, times: list[float],
                           styles: dict, default: dict, preferred_at: float) -> dict | None:
    """Find a visible upright pose on the actual numeric rotation path.

    Search endpoints and bracketed crossings of whole turns. Resolve the
    entire state at that instant, including simultaneous movement and sizing.
    Raw angles distinguish a half-turn around 180 from a crossing of zero.
    """
    axes = ('frz','frx','fry')
    rotations = [(a,b,accel,[(n,v) for n,v in changes if n in {*axes,'fr'}])
                 for a,b,accel,changes in transforms]
    cache = {}
    def angles(at):
        if at not in cache:
            state = sample_transform_state(base,rotations,at,styles,default)
            cache[at] = tuple(state.get(k,0) for k in axes)
        return cache[at]
    def pose(at):
        state = sample_transform_state(base,transforms,at,styles,default)
        return state if not state.get('p',0) and upright_text_state(
            state,include_shadow=True,include_outline=True,minimum_opacity=1) else None
    intervals = sorted(zip(times,times[1:]),key=lambda span:
                       max(span[0]-preferred_at,preferred_at-span[1],0))
    for left,right in intervals:
        for at in sorted((left,right),key=lambda t:(abs(t-preferred_at),-t)):
            if all(math.isfinite(v) and abs(math.remainder(v,360)) <= .001 for v in angles(at)):
                state = pose(at)
                if state is not None:
                    return state
        # A midpoint also brackets excursions from overlapping transforms
        # whose interval endpoints happen to have the same rotation.
        middle = (left+right)/2
        for a,b in ((left,middle),(middle,right)):
            start,finish = angles(a),angles(b)
            for axis,(lo,hi) in enumerate(zip(start,finish)):
                if not math.isfinite(lo) or not math.isfinite(hi) or abs(hi-lo) <= .001:
                    continue
                low,high = sorted((lo,hi))
                first,last = math.ceil(low/360),math.floor(high/360)
                if first > last:
                    continue
                winding = min(last,max(first,round(angles((a+b)/2)[axis]/360)))
                for target in dict.fromkeys((360*winding,360*first,360*last)):
                    begin,end = a,b
                    for _ in range(48):
                        at = (begin+end)/2
                        value = angles(at)[axis]
                        if abs(value-target) <= 1e-7:
                            break
                        if (value < target) == (lo < hi):
                            begin = at
                        else:
                            end = at
                    state = pose(at)
                    if state is not None:
                        return state
    return None


def select_static_state(base: dict, transforms: list, boundaries: set[float],
                        styles: dict, default: dict,
                        paint_events: Iterable[Event] | None = None,
                        opaque_spans: list[tuple[float,float]] | None = None,
                        settled_states: list[dict] | None = None, *,
                        prefer_upright: bool = False,
                        upright_crossings: bool = True) -> dict:
    """Keep settled geometry and choose colours by their total visible time.

    Repeated colour holds add together across animation intervals. Event
    copies use compositing order, so simultaneous backing layers do not get
    duplicate votes. Colour ramps retain a representative interval sample.
    Upright holds and crossings can override the representative text pose.
    """
    if not transforms and paint_events is None:
        if opaque_spans is not None and base.get('1a',0) == 0 and boundaries:
            opaque_spans.append((min(boundaries),max(boundaries)))
        if settled_states is not None and boundaries and max(boundaries) > min(boundaries):
            settled_states.append(base.copy())
        return base
    geometry = ("pos", "org", "fs", "fscx", "fscy", "fsp", "frz",
                "frx", "fry", "fax", "fay", "clip", "iclip")
    # Filter once per block instead of revisiting tag names at every interval.
    # Keep even empty change lists: equality checks retain their old semantics.
    geometry_transforms = [(a,b,[(name,value) for name,value in changes
                                if name in geometry or name in {"fr","r"}])
                           for a,b,_,changes in transforms]
    times = sorted(boundaries)
    candidates = []
    paint_samples = []
    samples = sample_transform_states(base,transforms,
        ((start+end)/2 for start,end in zip(times,times[1:])),styles,default)
    for (start,end),state in zip(zip(times,times[1:]),samples):
        at = (start+end)/2
        visible = (abs(state.get("fscx",100)) > .01 and abs(state.get("fscy",100)) > .01
                   and min(state.get("1a",0),state.get("3a",0),state.get("4a",0)) < 254)
        stable = not any(a < at < b for a,b,_,_ in transforms)
        # Color/blur animation must not make a settled glyph less desirable
        # than a rotated entrance or exit. Compare resolved geometry, so even
        # no-op transforms count as stationary. Paint is still sampled intact.
        settled = True
        for a,b,changes in geometry_transforms:
            if a < at < b:
                target = state.copy()
                for name,value in changes:
                    apply_tag(target,name,value,styles,default,event_tags=False)
                if any(target.get(k) != state.get(k) for k in geometry):
                    settled = False
                    break
        # Entrance/exit fades often use transparent primary text while an
        # unused shadow channel remains opaque. Prefer the visible fill too.
        strength = 255 - state.get("1a",0)
        if settled_states is not None and visible and settled:
            settled_states.append(state.copy())
        candidates.append(((visible, settled, stable, strength > 16, end-start, strength),state))
        paint_samples.append((start,end,state,(0,len(paint_samples))))
        if opaque_spans is not None and state.get('1a',0) == 0:
            if opaque_spans and abs(opaque_spans[-1][1]-start) < 1e-6:
                opaque_spans[-1] = (opaque_spans[-1][0],end)
            else:
                opaque_spans.append((start,end))
    best = max(range(len(candidates)),key=lambda i:candidates[i][0]) if candidates else None
    chosen = (candidates[best][1] if best is not None else base).copy()
    if prefer_upright and not chosen.get('p',0) and not unrotated_text_state(chosen):
        holds = [item for item in candidates if item[0][0] and item[0][1] and
                 upright_text_state(item[1],include_shadow=True) and not item[1].get('p',0)]
        if holds:
            chosen = max(holds,key=lambda item:item[0])[1].copy()
    if prefer_upright and upright_crossings and not chosen.get('p',0) and times:
        rotating = False
        for begin,end,_,changes in transforms:
            if begin >= times[-1] or end < times[0]:
                continue
            target = base.copy()
            for name,value in changes:
                if name in {'fr','frz','frx','fry'}:
                    apply_tag(target,name,value,styles,default,event_tags=False)
            if any(target.get(k,0) != base.get(k,0) for k in ('frz','frx','fry')):
                rotating = True
                break
        if rotating:
            if not upright_text_state(chosen,include_shadow=True,include_outline=True,minimum_opacity=1):
                at = sum(times[best:best+2])/2 if best is not None else times[0]
                upright = upright_transform_pose(base,transforms,times,styles,default,at)
                if upright is not None:
                    # Pose selection must not resurrect fading particles or
                    # change paint ties. Opacity and colour remain the
                    # representative paint, with dwell voting below.
                    paint = {k:chosen[k] for ch in (1,2,3,4) for k in (f'{ch}a',f'{ch}c')
                             if k in chosen}
                    chosen = upright
                    chosen.update(paint)
            if upright_text_state(chosen,include_shadow=True,include_outline=True,minimum_opacity=1):
                chosen.update(frz=0.0,frx=0.0,fry=0.0,_upright_rotation=True)
    if paint_events is None and not any(
            name in {'c','1c','3c','4c','r'}
            for _,_,_,changes in transforms for name,_ in changes):
        return chosen
    if paint_events is not None:
        paint_samples = [(e.start_s,e.end_s,e.state,
                          (int(e.layer) if e.layer.lstrip('-').isdigit() else 0,e.source_index))
                         for e in paint_events if e.end_s > e.start_s]
    # Count each channel only when it can paint visible pixels. Exact repeated
    # colours accumulate dwell time; a short highlight cannot replace a longer
    # base just because it was first, topmost, or present at the cue midpoint.
    if paint_events is None:
        spans = [(start,end,[(state,order)]) for start,end,state,order in paint_samples]
    else:
        times = sorted({t for start,end,_,_ in paint_samples for t in (start,end)})
        spans = [(start,end,[(state,order) for a,b,state,order in paint_samples
                            if a <= (start+end)/2 < b])
                 for start,end in zip(times,times[1:])]
    dwell = {channel:{} for channel in (1,3,4)}
    for start,end,active in spans:
        active = [(state,order) for state,order in active if
                  abs(state.get('fscx',100)) > .01 and abs(state.get('fscy',100)) > .01]
        for channel in dwell:
            eligible = [(state,order) for state,order in active
                        if state.get(f'{channel}a',0) < 254 and
                        re.fullmatch(r'[0-9A-Fa-f]{6}',str(state.get(f'{channel}c',''))) and
                        (channel == 1 or channel == 3 and
                         max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0 or
                         channel == 4 and
                         max(abs(state.get(k,state.get('shad',0))) for k in ('xshad','yshad')) > 0)]
            remaining = 1.0
            for state,_ in sorted(eligible,key=lambda item:item[1],reverse=True):
                color = state[f'{channel}c'].upper()
                opacity = min(1.0,max(0.0,(255-state.get(f'{channel}a',0))/255))
                dwell[channel][color] = (dwell[channel].get(color,0)+
                                         (end-start)*remaining*opacity)
                remaining *= 1-opacity
                if remaining <= 1e-9:
                    break
    for channel,colors in dwell.items():
        if colors:
            key = f'{channel}c'
            winner = max(colors,key=colors.get)
            if colors.get(chosen.get(key),-1) < colors[winner]-1e-6:
                chosen[key] = winner
    return chosen


def freeze_block(block: str, duration: float, initial: dict, default: dict,
                 styles: dict, max_blur: float,
                 opaque_spans: list[tuple[float,float]] | None = None,
                 settled_states: list[dict] | None = None, *,
                 prefer_upright: bool = False,
                 upright_crossings: bool = True) -> tuple[str, dict]:
    """Freeze a representative pose, preferring upright text when enabled."""
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
            changes = tokenize_override("\\" + tail)
            fixed = {"a","an","pos","org"}
            for child,argument in changes:
                if child in fixed:
                    apply_tag(base,child,argument,styles,default)
            transforms.append((begin,end,max(.01,accel),
                               [(child,argument) for child,argument in changes if child not in fixed]))
            boundaries.update((max(0, min(duration*1000, begin)), max(0, min(duration*1000, end))))
        elif name == "move":
            nums = list(map(float, re.findall(NUMBER, value)))
            if len(nums) in (4, 6) and "pos" not in base:
                base["pos"] = tuple(nums[:2])
                begin, end = nums[4:6] if len(nums) == 6 else (0, duration*1000)
                transforms.append((begin, end, 1, [("pos", f"({nums[2]},{nums[3]})")]))
                boundaries.update((max(0,min(duration*1000,begin)),max(0,min(duration*1000,end))))
        elif name not in {"fad", "fade"}:
            apply_tag(base, name, value, styles, default)
            if name == "r":
                reset = value
    state = select_static_state(base,transforms,boundaries,styles,default,
                                opaque_spans=opaque_spans,settled_states=settled_states,
                                prefer_upright=prefer_upright,upright_crossings=upright_crossings)
    for name in ("blur","be"):
        if name in state:
            state[name] = min(max_blur,max(0,state[name]))
    allowed = SAFE_SIMPLE_TAGS | {"pos","org","p","pbo","frx","fry","fax","fay",
                                   "1a","2a","3a","4a","blur","be","clip","iclip"}
    reference = styles.get(reset, default) if reset else (default if reset is not None else initial)
    text = ("\\r" + reset) if reset is not None else ""
    # Keep state dependencies in insertion order, particularly bord/xbord.
    # Uniform border/shadow tags clear earlier axis overrides even when the
    # uniform value already equals the style default.
    forced = {k for k in ("bord","shad") if reset is None and k in state and
              any(axis+k in initial and axis+k not in state for axis in "xy")}
    event_level = {"an","pos","org","clip","iclip","q","p","pbo"}
    # Emitting a uniform tag also clears axes that are intentionally restored
    # later in this block, even if their values equal the previous span's.
    forced.update(axis+k for k in ("bord","shad")
                  if k in state and (k in forced or k not in reference or state[k] != reference[k])
                  for axis in "xy" if axis+k in state)
    text += "".join(render_tag(k,v) for k,v in state.items()
                    if k in allowed and (k in forced or k not in reference or v != reference[k])
                    and not (reset is not None and k in event_level and initial.get(k) == v))
    return text,state


def simplify_visual_text(text: str, max_blur: float, duration: float | None = None,
                         default: dict | None = None, styles: dict | None = None,
                         level: int = 2, *, upright_crossings: bool = True) -> tuple[str, str, int]:
    default = default or DEFAULT_STATE
    state = default.copy()
    output, visible = [], []
    drawing_chars = 0
    parts = re.split(r"(\{[^}]*\})", text)
    if (level == 1 and upright_crossings and re.search(r'\\t\s*\(',text) and
            re.search(r'\\fr(?:[xyz])?(?=[+\-\d.])',text) and
            any(tag in {'fr','frz','frx','fry'} for block in OVERRIDE_RE.findall(text)
                for name,value in tokenize_override(block) if name == 't'
                for tag,_ in tokenize_override(value[1:-1]))):
        # Adjacent headers affect the same glyphs. Freeze their movement and
        # rotation together, instead of sampling each header at another time.
        combined = []
        for part in parts:
            if not part:
                continue
            if (part.startswith('{') and part.endswith('}') and combined and
                    combined[-1].startswith('{') and combined[-1].endswith('}')):
                combined[-1] = combined[-1][:-1]+part[1:]
            else:
                combined.append(part)
        parts = combined
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            block,state = freeze_block(part[1:-1],duration or 1, state,default,styles or {},max_blur,
                                      prefer_upright=level == 1,upright_crossings=upright_crossings)
            if level == 1:
                # Broken nested transforms can hide a final drawing switch
                # from the normal tag tokenizer. Keep the drawing payload out
                # of the dialogue text even in those generated effects.
                switches = re.findall(r"\\p(\d+)(?![\dA-Za-z])", part, re.I)
                if switches:
                    state["p"] = float(switches[-1])
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


def compact_static_overrides(events: list[Event], max_blur: float) -> list[Event]:
    """Serialize finished captions relative to their style and preceding spans.

    Reuse the normal override resolver after effect recognition has finished.
    Blur/edge blur default to zero even though ASS styles have no such fields.
    Keep drawing payloads, inline formatting, resets and comments intact.
    """
    output = []
    for e in events:
        if e.kind == "Dialogue":
            defaults = {**(e.defaults or DEFAULT_STATE), "blur":0.0, "be":0.0}
            text, _, _ = simplify_visual_text(
                e.text,max_blur,e.duration,defaults,e.styles,2)
            if re.search(r'\\org\(',text):
                # Keep origins through source-effect proofs: they distinguish
                # independently generated copies. At this late stage an origin
                # has no rendered effect when every span is unrotated.
                state = defaults.copy()
                upright = True
                for part in re.split(r'(\{[^}]*\})',text):
                    if part.startswith('{'):
                        for tag,value in tokenize_override(part[1:-1]):
                            apply_tag(state,tag,value,e.styles,defaults)
                    elif part and not unrotated_text_state(state):
                        upright = False
                        break
                if upright:
                    text = re.sub(r'\\org\([^)]*\)','',text)
            if text != e.text:
                e = replace_event(e,text=text)
        output.append(e)
    return output


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


def reduce_static_sign_copies(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """In level 1, fold slightly offset effect copies into their fill."""
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
        positions = {e.source_index: get_pos(e.text) for e in group}
        heights = {e.source_index: text_height(e) for e in group}
        # A covering copy must be within 6% of THIS event's height in x,
        # because the original bound uses the smaller of the two heights.
        # The sorted window is only a candidate index; all original removal
        # conditions still apply. Removed events remain available as evidence.
        finite = all(math.isfinite(positions[e.source_index][0]) and
                     math.isfinite(heights[e.source_index]) for e in group)
        by_x = sorted(group,key=lambda e: positions[e.source_index][0]) if finite else group
        xs = [positions[e.source_index][0] for e in by_x] if finite else None
        for e in group:
            x, y = positions[e.source_index]
            radius = math.nextafter(.06*heights[e.source_index],math.inf)
            # Expand the radius and endpoints by one floating-point step so
            # subtraction rounding (including cancellation) cannot exclude a
            # pair accepted by the original distance test.
            left = bisect_left(xs,math.nextafter(x-radius,-math.inf)) if xs is not None else 0
            right = bisect_right(xs,math.nextafter(x+radius,math.inf)) if xs is not None else len(by_x)
            for index in range(left,right):
                other = by_x[index]
                if other is e or ranks[other.source_index] >= ranks[e.source_index]:
                    continue
                ox, oy = positions[other.source_index]
                # Only remove a copy covered for its entire lifetime by an
                # almost coincident copy of the same complete text.
                if (other.start_s <= e.start_s + 0.001
                        and other.end_s >= e.end_s - 0.001
                        and abs(ox - x) <= .06*min(heights[e.source_index],heights[other.source_index])
                        and abs(oy - y) <= .06*min(heights[e.source_index],heights[other.source_index])
                        and compatible_text_layout(e,other)):
                    removed.add(e.source_index)
                    break
    return [e for e in events if e.source_index not in removed], len(removed)


def coalesce_lyric_phases(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Join glyph phases with sustained colours, keeping lyric rows separate."""
    groups: dict[tuple, list[Event]] = {}
    starts: dict[tuple, set[tuple]] = {}
    ends: dict[tuple, set[tuple]] = {}
    output = []
    for e in events:
        pos = get_pos(e.text)
        visible = visible_map.get(e.source_index, "")
        if (e.kind != "Dialogue" or not e.lyric or pos is None):
            output.append(e)
            continue
        row = (e.style, e.name, e.layer, e.row)
        glyph = (round(pos[0] / e.unit, 1) * e.unit, visible)
        starts.setdefault((*row, round(e.start_s, 2)), set()).add(glyph)
        ends.setdefault((*row, round(e.end_s, 2)), set()).add(glyph)
        if OVERRIDE_RE.search(e.text,re.match(r"(?:\{[^}]*\})*",e.text).end()):
            # A final state cannot describe differently painted inline spans.
            # Retain them, but still record their surrounding row boundaries.
            output.append(e)
            continue
        key = (e.style, e.name, e.layer, e.margin_l, e.margin_r, e.margin_v,
               round(pos[0] / e.unit, 1) * e.unit, round(pos[1] / e.unit, 1) * e.unit, visible, text_layout_key(e), placement_key(e))
        groups.setdefault(key, []).append(e)
    # Identical letters can occupy the same position in consecutive lyrics.
    # A change in the surrounding glyphs marks a real lyric boundary.
    boundaries = {key for key in starts.keys() & ends.keys()
                  if starts[key] != ends[key]}
    removed = 0
    for group in groups.values():
        group.sort(key=lambda e: (e.start_s, e.end_s, e.source_index))
        current = group[0]
        paint_events = [current]
        runs = []
        for e in group[1:]:
            pos = get_pos(e.text)
            boundary = (e.style, e.name, e.layer, e.row, round(e.start_s, 2))
            # A small fade overlap between consecutive rows is not another
            # phase of the same glyph. Compare the surrounding row at the old
            # end and new start, including overlaps rather than just touching.
            ending = ends.get((e.style,e.name,e.layer,e.row,round(current.end_s,2)),set())
            beginning = starts.get(boundary,set())
            changed_row = (e.start_s > current.start_s and e.end_s > current.end_s and
                           len(ending) > 1 and len(beginning) > 1 and ending != beginning and
                           current.end_s-e.start_s <= .2*min(current.duration,e.duration))
            if (e.start_s <= current.end_s + 0.011 and not changed_row and
                    not (abs(e.start_s - current.end_s) <= 0.011 and boundary in boundaries)):
                end = max(current.end_s, e.end_s)
                current = replace_event(current, end=format_time(end), end_s=end,
                                  source_index=min(current.source_index, e.source_index))
                paint_events.append(e)
                removed += 1
            else:
                runs.append((current,paint_events))
                current = e
                paint_events = [e]
        runs.append((current,paint_events))
        for caption,phases in runs:
            # Select once from original intervals, not from successively
            # extended representatives whose colours would get extra votes.
            if any(phase.state.get(k) != caption.state.get(k)
                   for phase in phases for k in ("1c","3c","4c")):
                state = select_static_state(caption.state,[],set(),caption.styles,
                                            caption.defaults,paint_events=phases)
                tags = ''.join(render_tag(k,state[k]) for k in ("1c","3c","4c")
                               if k in state and state[k] != caption.state.get(k))
                if tags:
                    text = caption.text
                    prefix_end = re.match(r"(?:\{[^}]*\})*",text).end()
                    if prefix_end:
                        text = text[:prefix_end-1]+tags+text[prefix_end-1:]
                    else:
                        text = '{'+tags+'}'+text
                    caption = replace_event(caption,text=text)
            output.append(caption)
    return sorted(output, key=lambda e: e.source_index), removed


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
            extended[line.source_index] = replace_event(line, start=format_time(earlier),
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
            state = select_static_state(best.state,[],set(),best.styles,best.defaults,
                                        paint_events=cluster)
            text = aggressive_caption(state, visible_map[best.source_index],
                                      outline_states=[e.state for e in cluster])
            replacements[first.source_index] = replace_event(
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
                          min_pieces: int = 3,
                          aggressive: bool = False) -> tuple[list[Event], int]:
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
        ordered=sorted(group,key=lambda e:(e.start_s,e.end_s,e.source_index)) if aggressive else []
        if (aggressive and
                sum(e.duration<=max_piece_duration and bool(inline_layout_key(e)) and
                    bool(re.search(r"\\(?:alpha|[1-4]a)&HFF&",e.text,re.I))
                    for e in group)>=2 and
                all(b.start_s>=a.end_s-1e-6 for a,b in zip(ordered,ordered[1:]))):
            # Paint-only span changes can hide letters during an exit. They do
            # not change the literal text or its layout. Normalize the complete
            # family so its static hold and exit frames still match. Font,
            # geometry and drawing changes within a line remain unsupported.
            paint={"alpha","1a","2a","3a","4a","c","1c","2c","3c","4c",
                   "bord","xbord","ybord","shad","xshad","yshad","blur","be"}
            safe=True
            for e in group:
                seen_text=False
                for part in re.split(r"(\{[^}]*\})",e.text):
                    if part.startswith("{"):
                        if seen_text and any(k not in paint for k,v in tokenize_override(part[1:-1])):
                            safe=False
                    elif part:
                        seen_text=True
            if safe:
                normalized=[]
                for e in group:
                    prefix=re.match(r"(?:\{[^}]*\})*",e.text).group()
                    state=effective_state(prefix,e.defaults or DEFAULT_STATE,e.styles)
                    normalized.append(replace_event(e,text=aggressive_caption(
                        state,OVERRIDE_RE.sub("",e.text))))
                group=normalized
        frozen,count=freeze_vector_sequences(group,max_piece_duration,max_gap,
                                             near_static=aggressive)
        output.extend(frozen)
        removed+=count
    return sorted(output,key=lambda e:e.source_index),removed


def freeze_vector_sequences(events: list[Event], short_duration: float = 0.16,
                            max_gap: float = 0.011,
                            near_static: bool = False) -> tuple[list[Event], int]:
    """Freeze frame-by-frame drawings, including their longer static hold.

    Match actual paths and static paint, not style names or colors specific
    to a show. Overlapping copies are ambiguous and remain separate.
    """
    frame_removed=0
    if near_static:
        # First retain the established treatment of actual moving frames.
        # Its frozen holds can then be joined when only tracking jitter differs.
        events,frame_removed=freeze_vector_sequences(events,short_duration,max_gap)
    changing = {"pos","fscx","fscy","frz","frx","fry","fax","fay",
                "1a","2a","3a","4a"}
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        key = (e.kind,e.layer,e.name,geometry_key(e.text),state_key(e,changing),placement_key(e))
        groups.setdefault(key,[]).append(e)

    output: list[Event] = []
    removed = frame_removed

    def emit(run: list[Event], settled: bool = False) -> None:
        nonlocal removed
        if (len(run) < 2 or not settled and
                (len(run) < 3 or
                 sum(e.duration <= short_duration + 1e-6 for e in run) < 2 or
                 len({e.text for e in run}) < 2)
                or any(b.start_s < a.end_s - 1e-6 for a, b in zip(run, run[1:]))):
            output.extend(run)
            return
        # Rank the visible primary paint, then the longest hold. Unused
        # secondary/shadow alpha must not outweigh an unfaded foreground.
        # Outline-only and shadow-only objects use their actual paint channel.
        channel = next((c for c in (1,3,4) if any(
            e.state.get(f"{c}a",0) < 254 and
            (c == 1 or c == 3 and max(abs(e.state.get(k,e.state.get("bord",0)))
                                    for k in ("xbord","ybord")) > 0 or
             c == 4 and max(abs(e.state.get(k,e.state.get("shad",0)))
                            for k in ("xshad","yshad")) > 0)
            for e in run)),1)
        chosen = min(run, key=lambda e: (e.state.get(f"{channel}a",0), -e.duration, e.source_index))
        output.append(replace_event(chosen, start=run[0].start, start_s=run[0].start_s,
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
            if near_static:
                # A tracked sign may jump between several stable placements.
                # Merge bounded jitter within each hold, without requiring the
                # entire time-connected component to have one static pose.
                run=[]
                reference=None
                pose={"pos","fscx","fscy","frz"}
                for candidate in component:
                    trial_reference=(candidate if reference is None or
                                     candidate.duration>reference.duration else reference)
                    position=get_pos(trial_reference.text)
                    sx=trial_reference.state.get("fscx",100)
                    sy=trial_reference.state.get("fscy",100)
                    settled=(bool(run) and abs(candidate.start_s-run[-1].end_s)<=1e-6 and
                             position is not None and sx>0 and sy>0 and
                             not trial_reference.state.get("p",0) and
                             not inline_layout_key(trial_reference))
                    if settled:
                        height=text_height(trial_reference)
                        width=abs(trial_reference.state.get("fs",20)*sx/100)*max(
                            1,len(OVERRIDE_RE.sub("",trial_reference.text)))
                        key=state_key(trial_reference,pose)
                        # Recheck earlier holds only when the chosen longest
                        # representative changes. This prevents cumulative
                        # drift from passing through many locally small steps.
                        check=run+[candidate] if trial_reference is not reference else [candidate]
                        for e in check:
                            pos=get_pos(e.text)
                            if (pos is None or state_key(e,pose)!=key or
                                    inline_layout_key(e)):
                                settled=False;break
                            origin=e.state.get("org",pos)
                            radius=math.dist(pos,origin)+math.hypot(width,height)
                            angle=math.radians(math.remainder(
                                e.state.get("frz",0)-trial_reference.state.get("frz",0),360))
                            error=(math.dist(pos,position)+
                                   abs(e.state.get("fscx",100)-sx)/sx*width+
                                   abs(e.state.get("fscy",100)-sy)/sy*height+
                                   2*radius*abs(math.sin(angle/2)))
                            if error>.02*height:
                                settled=False;break
                    if run and not settled:
                        emit(run,True)
                        run=[]
                    run.append(candidate)
                    reference=trial_reference if settled else candidate
                emit(run,True)
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
                        for k,v in e.state.items() if k not in omit and not k.startswith("_")))


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
    """Deprecated: legacy level 2 only; retained for reference.

    Remove a lower shape only when the same footprint is painted opaquely.

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


def coverage_geometry(e: Event, scaled_borders: bool = True):
    """Conservative bounds for a single top-left, unrotated drawing.

    Curves may be covered (their control points bound them); covering shapes
    must be straight-sided. Unsupported drawing syntax is never guessed.
    """
    state = e.state
    if not e.layer.lstrip("-").isdigit():
        return None
    if (state.get("an", 2) != 7 or state.get("p", 0) < 1
            or state.get("borderstyle", 1) != 1
            or any(state.get(k, 0) != 0 for k in
                   ("frz", "frx", "fry", "fax", "fay", "pbo", "blur", "be", "fsp"))):
        return None
    pos = get_pos(e.text)
    match = re.fullmatch(r"(?:\{[^}]*\})*([^{}]+)", e.text)
    if pos is None or match is None:
        return None
    raw = match.group(1).strip()
    tokens = re.findall(NUMBER + r"|[A-Za-z]", raw)
    if re.sub(NUMBER + r"|[A-Za-z]|\s+", "", raw):
        return None
    if not tokens or tokens[0].lower() != "m":
        return None
    points, curved, i = [], False, 0
    while i < len(tokens):
        command = tokens[i].lower()
        i += 1
        if command not in {"m", "l", "b"} or (command == "m" and points):
            return None  # Multiple contours, holes and splines stay untouched.
        coords = []
        while i < len(tokens) and re.fullmatch(NUMBER, tokens[i]):
            coords.append(float(tokens[i])); i += 1
        if ((command == "m" and len(coords) != 2)
                or (command == "l" and (len(coords) < 2 or len(coords) % 2))
                or (command == "b" and (len(coords) < 6 or len(coords) % 6))):
            return None
        points.extend(zip(coords[::2], coords[1::2]))
        curved |= command == "b"
    if len(points) < 3:
        return None
    scale = 2 ** (state["p"] - 1)
    sx, sy = state.get("fscx", 100) / (100 * scale), state.get("fscy", 100) / (100 * scale)
    if sx <= 0 or sy <= 0:
        return None
    points = [(pos[0] + x*sx, pos[1] + y*sy) for x,y in points]
    bx = abs(state.get("xbord", state.get("bord", 0)))
    by = abs(state.get("ybord", state.get("bord", 0)))
    dx = state.get("xshad", state.get("shad", 0))
    dy = state.get("yshad", state.get("shad", 0))
    if not scaled_borders and any((bx, by, dx, dy)):
        return None
    # Include the entire stroke and shadow even when their alpha is hidden.
    # Extra clearance keeps anti-aliased edges outside the coverage boundary.
    pad = max(2.0, 2*e.unit)
    xs, ys = zip(*points)
    bounds = (min(xs)-bx+min(0,dx)-pad, min(ys)-by+min(0,dy)-pad,
              max(xs)+bx+max(0,dx)+pad, max(ys)+by+max(0,dy)+pad)
    opaque = (state.get("1a", 0) == 0 and not curved
              and "clip" not in state and "iclip" not in state)
    return points, bounds, opaque


def polygon_covers_box(points, box) -> bool:
    """Require the whole box inside the fill, with no contour crossing it."""
    x0,y0,x1,y1 = box
    edges = list(zip(points, points[1:] + points[:1]))
    # Segment/rectangle intersection (including boundaries).
    for (ax,ay),(bx,by) in edges:
        lo, hi = 0.0, 1.0
        for origin, delta, low, high in ((ax,bx-ax,x0,x1),(ay,by-ay,y0,y1)):
            if delta == 0:
                if origin < low or origin > high:
                    lo,hi = 1.0,0.0
                    break
            else:
                t0,t1 = sorted(((low-origin)/delta,(high-origin)/delta))
                lo,hi = max(lo,t0),min(hi,t1)
        if lo <= hi:
            return False
    # With no boundary in the box, its interior has uniform fill. Require
    # both winding and odd/even rules to consider the test point filled.
    x,y = (x0+x1)/2,(y0+y1)/2
    crossings = winding = 0
    for (ax,ay),(bx,by) in edges:
        if (ay <= y < by) or (by <= y < ay):
            hit = ax + (y-ay)*(bx-ax)/(by-ay)
            if hit > x:
                crossings += 1
                winding += 1 if by > ay else -1
    return bool(crossings % 2 and winding)


def remove_fully_covered_vectors(events: list[Event], scaled_borders: bool = True):
    """Deprecated: legacy level 2 only; retained for reference."""
    geometry = {e.source_index: g for e in events
                if (g := coverage_geometry(e, scaled_borders)) is not None}
    covers = [e for e in events if e.source_index in geometry and geometry[e.source_index][2]]
    removed = set()
    for lower in events:
        info = geometry.get(lower.source_index)
        if info is None:
            continue
        order = (int(lower.layer), lower.source_index)
        box = info[1]
        for upper in covers:
            if ((int(upper.layer), upper.source_index) <= order
                    or upper.start_s > lower.start_s or upper.end_s < lower.end_s):
                continue
            polygon = geometry[upper.source_index][0]
            xs,ys = zip(*polygon)
            if not (min(xs) < box[0] and min(ys) < box[1]
                    and max(xs) > box[2] and max(ys) > box[3]):
                continue
            if polygon_covers_box(polygon, box):
                removed.add(lower.source_index)
                break
    return [e for e in events if e.source_index not in removed], len(removed)


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


def rectangle_clip(e: Event):
    value = e.state.get("clip", "")
    if "iclip" in e.state or not re.fullmatch(r"\(\s*" + NUMBER + r"(?:\s*,\s*" + NUMBER + r"){3}\s*\)", value):
        return None
    coords = tuple(map(float, re.findall(NUMBER, value)))
    return coords if coords[0] < coords[2] and coords[1] < coords[3] else None


def join_text_clip_tiles(events: list[Event]) -> tuple[list[Event], int]:
    """Deprecated: legacy level 2 only; retained for reference.

    Join adjacent rectangular clips with identical text and paint.

    Rectangles must exactly tile a larger rectangle. No gaps, overlaps,
    color approximation or transparency changes are allowed.
    """
    groups, output, layers = {}, [], {}
    for e in events:
        if e.kind == "Dialogue":
            layers.setdefault(e.layer, []).append(e)
        rect = rectangle_clip(e)
        if (e.kind != "Dialogue" or rect is None or inline_layout_key(e)
                or e.state.get("p", 0) or get_pos(e.text) is None):
            output.append(e)
            continue
        key = (e.start,e.end,e.layer,e.name,e.margin_l,e.margin_r,e.margin_v,
               OVERRIDE_RE.sub("",e.text),state_key(e,{"clip"}))
        groups.setdefault(key, []).append((e,rect))
    removed = 0
    for group in groups.values():
        ids = {e.source_index for e,r in group}
        low,high = min(ids),max(ids)
        first = group[0][0]
        if any(low < peer.source_index < high and peer.source_index not in ids
               and min(peer.end_s,first.end_s)>max(peer.start_s,first.start_s)
               for peer in layers[first.layer]):
            output.extend(e for e,r in group)
            continue
        changed = True
        while changed:
            changed = False
            for axis in (0,1):
                other = 1-axis
                group.sort(key=lambda pair:(pair[1][other],pair[1][other+2],pair[1][axis]))
                joined = []
                for event,rect in group:
                    if joined:
                        previous,pr = joined[-1]
                        if pr[other]==rect[other] and pr[other+2]==rect[other+2] and pr[axis+2]==rect[axis]:
                            union = list(pr); union[axis+2] = rect[axis+2]; union=tuple(union)
                            value = "("+",".join(f"{v:g}" for v in union)+")"
                            text = re.sub(r"\\clip\([^)]*\)",lambda _: "\\clip"+value,previous.text)
                            state = previous.state.copy(); state["clip"]=value
                            joined[-1]=(replace_event(previous,text=text,state=state,
                                source_index=min(previous.source_index,event.source_index)),union)
                            removed += 1; changed = True
                            continue
                    joined.append((event,rect))
                group = joined
        output.extend(e for e,r in group)
    return sorted(output,key=lambda e:e.source_index),removed


def reduce_text_layers(events: list[Event], visible_map: dict[int, str],
                       blockers: list[Event] | None = None) -> tuple[list[Event], int]:
    """Deprecated: legacy level 2 only; retained for reference.

    Flatten identical opaque text into its foreground and one outline.

    Layout, clipping and literal line breaks must match. Translucent paints,
    mixed spans and differing outline colors remain separate.
    """
    groups = {}
    for e in events:
        if (e.kind != "Dialogue" or inline_layout_key(e) or e.state.get("p",0)
                or get_pos(e.text) is None or not e.layer.lstrip("-").isdigit()):
            groups.setdefault((e.source_index,),[]).append(e)
            continue
        key=(e.start,e.end,e.name,get_pos(e.text),OVERRIDE_RE.sub("",e.text),
             text_layout_key(e),placement_key(e))
        groups.setdefault(key,[]).append(e)
    peers = events + (blockers or [])
    output=[]
    for group in groups.values():
        if len(group)<2:
            output.extend(group); continue
        # A single output cannot preserve independently positioned shadows
        # or the accumulation of translucent paints.
        if any(any(e.state.get(k,0) for k in ("shad","xshad","yshad","blur","be"))
               or e.state.get("1a",0) not in (0,255) for e in group):
            output.extend(group); continue
        fills=[e for e in group if e.state.get("1a",0)==0]
        if not fills:
            output.extend(group); continue
        foreground=max(fills,key=lambda e:(int(e.layer),e.source_index))
        ids={e.source_index for e in group}
        low=min((int(e.layer),e.source_index) for e in group)
        high=max((int(e.layer),e.source_index) for e in group)
        if any(peer.kind=="Dialogue" and peer.source_index not in ids
               and peer.layer.lstrip("-").isdigit()
               and low < (int(peer.layer),peer.source_index) < high
               and min(peer.end_s,foreground.end_s)>max(peer.start_s,foreground.start_s)
               for peer in peers):
            output.extend(group); continue
        contours=[]
        for e in group:
            bx=e.state.get("xbord",e.state.get("bord",0))
            by=e.state.get("ybord",e.state.get("bord",0))
            if max(bx,by)>0 and e.state.get("3a",0)<255:
                contours.append((e,bx,by))
        if (any(e.state.get("3a",0)!=0 for e,x,y in contours)
                or len({e.state.get("3c","000000") for e,x,y in contours})>1):
            output.extend(group); continue
        bx=max((x for e,x,y in contours),default=0)
        by=max((y for e,x,y in contours),default=0)
        # Crossed anisotropic outlines do not equal one larger outline.
        if contours and not any(x==bx and y==by for e,x,y in contours):
            output.extend(group); continue
        if contours:
            color=contours[0][0].state.get("3c","000000")
            tags=f"\\xbord{bx:g}\\ybord{by:g}\\3c&H{color}&\\3a&H00&"
            text=foreground.text
            if text.startswith("{"):
                end=text.index("}"); text=text[:end]+tags+text[end:]
            else:
                text="{"+tags+"}"+text
            state=foreground.state.copy()
            state.update(xbord=bx,ybord=by,**{"3c":color,"3a":0})
            foreground=replace_event(foreground,text=text,state=state)
        output.append(foreground)
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output)


def collapse_frame_text_echoes(events: list[Event],
                              max_piece_duration: float, *,
                              source_events: dict[int,Event] | None = None) -> tuple[list[Event], int]:
    """Collapse exit echoes proven by paint stacks or a settled caption.

    Require the same multilayer paint stack at every offset, a touching
    frame sequence, and evenly spaced offsets along the motion direction.
    Longer frames need recorded source movement; duration alone cannot prove
    or disprove such an exit. Unproven copies retain the short-frame limit.
    Already flattened copies require a longer isolated opaque hold with the
    same fill/layout. Static labels and unrelated paint remain separate.
    """
    families = {}
    for e in events:
        if (e.kind != "Dialogue" or e.effect or e.duration <= 0 or
                get_pos(e.text) is None or inline_layout_key(e) or
                e.state.get("p", 0) or "clip" in e.state or "iclip" in e.state):
            continue
        key = (e.style, e.name, e.margin_l, e.margin_r, e.margin_v,
               OVERRIDE_RE.sub("", e.text),
               tuple((k,v) for k,v in text_layout_key(e) if k not in {"fscx","fscy"}))
        families.setdefault(key, {}).setdefault((e.start_s,e.end_s), []).append(e)
    removed, replacements = set(), {}
    omit = {"pos", "fscx", "fscy", "1a", "2a", "3a", "4a"}

    def follows_motion(points, center, previous_center, height):
        span = math.dist(points[0], points[-1])
        if not (len(points) >= 3 and .001*height < span <= .5*height and
                math.dist(center,previous_center) > span):
            return False
        direction = tuple(points[-1][axis]-points[0][axis] for axis in (0,1))
        motion = tuple(center[axis]-previous_center[axis] for axis in (0,1))
        return (abs(direction[0]*motion[1]-direction[1]*motion[0]) <=
                .05*span*math.hypot(*motion) and
                all(math.dist(point, tuple(points[0][axis] + direction[axis]*i/(len(points)-1)
                                          for axis in (0,1))) <= .01*height
                    for i,point in enumerate(points)))

    def freeze_echo(members, anchor, text, layer=None):
        index = min(e.source_index for e in members)
        sample = members[0]
        replacements[index] = replace_event(sample, text=text, layer=anchor.layer if layer is None else layer,
                                            source_index=index, row=anchor.row, lyric=anchor.lyric)
        removed.update(e.source_index for e in members)

    for frames in families.values():
        moving_frames = {}
        def recorded_motion(time):
            if time not in moving_frames:
                valid = bool(source_events)
                points = sorted({get_pos(e.text) for e in frames[time]})
                direction = (tuple(points[-1][axis]-points[0][axis] for axis in (0,1))
                             if len(points) >= 3 else (0,0))
                span = math.hypot(*direction)
                valid &= span > 0
                reference = None
                for e in frames[time] if valid else ():
                    original = source_events.get(e.source_index)
                    if (original is None or original.duration <= 0 or
                            e.start_s < original.start_s-.001 or
                            e.end_s > original.end_s+.001 or inline_layout_key(original)):
                        valid = False; break
                    moves = [v for k,v in event_override_tokens(original) if k == 'move']
                    values = (parse_effect_move(moves[0],original.duration,endpoint_slack=50)
                              if len(moves) == 1 else None)
                    if values is None or math.dist(values[:2],values[2:4]) <= e.unit:
                        valid = False; break
                    motion = (values[2]-values[0],values[3]-values[1])
                    if (abs(direction[0]*motion[1]-direction[1]*motion[0]) >
                            .05*span*math.hypot(*motion) or reference is not None and
                            sum(a*b for a,b in zip(reference,motion)) <= 0):
                        valid = False; break
                    reference = motion
                moving_frames[time] = valid
            return moving_frames[time]

        def exit_frame(time):
            return time[1]-time[0] <= max_piece_duration+1e-6 or recorded_motion(time)

        # Most subtitles have no replicated exit frames. Avoid resolving
        # complete paint profiles for their ordinary frame animation.
        candidates = {time for time,members in frames.items()
                      if len(members) >= 3 and exit_frame(time) and
                      len({get_pos(e.text) for e in members}) >= 3 and
                      (len(members) >= 6 and all(0 < e.state.get("1a",0) < 255 for e in members) or
                       len(members) == len({get_pos(e.text) for e in members}) and
                       all(e.state.get("1a",0) < 255 for e in members))}
        if not candidates:
            continue
        starts = {start for start,_ in candidates}
        relevant = candidates | {time for time in frames if time[1] in starts}
        times = sorted(frames)
        isolated_frames = set()
        latest_end = -math.inf
        for i,(start,end) in enumerate(times):
            if latest_end <= start and (i+1 == len(times) or times[i+1][0] >= end):
                isolated_frames.add((start,end))
            latest_end = max(latest_end,end)
        # Brief entrances to persistent repeated labels are not exit echoes.
        # Propagate that ambiguity back through the touching frame sequence.
        blocked_starts, blocked = set(), set()
        for start,end in reversed(times):
            if (end in blocked_starts or not exit_frame((start,end)) and
                    len({get_pos(e.text) for e in frames[(start,end)]}) > 1):
                blocked.add((start,end))
                blocked_starts.add(start)
        previous = None
        held = None
        for start,end in sorted(relevant):
            members = frames[(start,end)]
            if (len({text_layout_key(e) for e in members}) != 1 or
                    any(e.state.get("borderstyle",1) != 1 for e in members)):
                previous = None
                held = None
                continue
            positions = {}
            for e in members:
                positions.setdefault(get_pos(e.text), []).append(e)
            height = min(text_height(e) for e in members)
            points = sorted(positions)
            center = tuple(statistics.mean(p[axis] for p in points) for axis in (0,1))
            # A previous simplification can erase both layer multiplicity
            # and transparency. Use the isolated hold and geometry instead.
            isolated = (start,end) in isolated_frames and (start,end) not in blocked
            if (len(members) == 1 and end-start > max_piece_duration+1e-6 and isolated and
                    members[0].state.get("1a",0) == 0):
                held = (end,center,members[0])
            elif held is not None:
                anchor = held[2]
                flattened = (isolated and len(members) == len(points) and
                    exit_frame((start,end)) and abs(start-held[0]) <= 1e-6 and
                    math.dist(center,held[1]) <= 5*height and
                    all(e.state.get("1c") == anchor.state.get("1c") and
                        e.state.get("1a",0) < 255 and
                        all(abs(e.state.get(k,0)-anchor.state.get(k,0)) <= .1*max(
                            abs(anchor.state.get(k,100)),1) for k in ("fscx","fscy")) and
                        all(e.state.get(axis+"shad",e.state.get("shad",0)) ==
                            anchor.state.get(axis+"shad",anchor.state.get("shad",0))
                            for axis in "xy") for e in members) and
                    follows_motion(points,center,held[1],height))
                if flattened:
                    freeze_echo(members,anchor,anchor.text)
                    held = (end,center,anchor)
                    previous = None
                    continue
                held = None
            profiles = []
            for stack in positions.values():
                layers = {e.layer for e in stack}
                if (len(layers) != len(stack) or len(layers) < 2 or
                        any(not layer.lstrip("-").isdigit() for layer in layers)):
                    profiles = []
                    break
                profiles.append(tuple(sorted((int(e.layer), state_key(e, {"pos"})) for e in stack)))
            if not profiles or len(set(profiles)) != 1:
                previous = None
                continue
            foreground = max(members, key=lambda e: (int(e.layer), -math.dist(get_pos(e.text),center)))
            stack = next(iter(positions.values()))
            # Contour widths can change between exit frames. Each offset
            # must still carry an identical complete stack within its frame.
            continuity = tuple(sorted((int(e.layer), state_key(e, omit | {"bord","xbord","ybord"}))
                                      for e in stack))
            if len(points) == 1:
                previous = ((end, continuity, center, foreground, stack)
                            if foreground.state.get("1a",0) == 0 else None)
                continue
            echoes = (previous is not None and abs(start-previous[0]) <= 1e-6 and
                      continuity == previous[1] and exit_frame((start,end)) and
                      (end-start <= max_piece_duration+1e-6 or isolated) and
                      all(0 < e.state.get("1a",0) < 255 for e in members) and
                      follows_motion(points,center,previous[2],height))
            if not echoes:
                previous = None
                continue
            # Freeze the exit at its preceding opaque pose and paint; using
            # a translucent echo would replace its real outline with fallback
            # paint and prevent the existing frame reducer joining the hold.
            anchor = previous[3]
            text = aggressive_caption(anchor.state, OVERRIDE_RE.sub("", anchor.text),
                                      outline_states=[e.state for e in previous[4]])
            freeze_echo(members,anchor,text,layer="0")
            previous = (end, continuity, center, anchor, previous[4])
    return ([replacements[e.source_index] if e.source_index in replacements else e
             for e in events if e.source_index not in removed or e.source_index in replacements],
            len(removed)-len(replacements))


def static_text_paint_geometry(e: Event, paint: set[str]):
    """Resolve literal spans, coalescing boundaries that change only paint."""
    obj = static_object_key(e,e.styles,allow_unpositioned=True)
    geometry = []
    if obj is not None:
        for signature,drawing,payload in obj[-1]:
            state = dict(signature)
            if drawing or state.get("borderstyle",1) != 1:
                return None
            layout = state_key(dataclass_replace(e,state=state),paint | {"clip","iclip"})
            if geometry and geometry[-1][0] == layout:
                geometry[-1] = (layout,geometry[-1][1]+payload)
            else:
                geometry.append((layout,payload))
    return (tuple(geometry),obj[-1]) if geometry else None


def static_text_paint_caption(e: Event, outlines: list[dict], paint: set[str]):
    """Use level 1 paint selection without rewriting authored text geometry."""
    header = aggressive_caption(e.state,"",outline_states=outlines)
    normalized = effective_state(header,e.defaults,e.styles)
    if normalized.get("pos") != e.state.get("pos"):
        return None
    tags = "".join("\\"+name+value for name,value in
                   tokenize_override(header[1:-1]) if name in paint)
    def retain_geometry(match):
        geometry = "".join("\\"+name+value for name,value in
                           tokenize_override(match[1])
                           if name not in paint | {"clip","iclip"})
        return "{"+geometry+tags+"}"
    text = OVERRIDE_RE.sub(retain_geometry,e.text)
    return text if text.startswith("{") else "{"+tags+"}"+text


def flatten_held_text_paint_copies(events: list[Event], visible_map: dict[int,str],
                                  paint: set[str], source_events: dict[int,Event],
                                  max_piece_duration: float) -> tuple[list[Event],int]:
    """Replace unpositioned paint copies beneath a full opaque hold.

    Match every literal span's geometry, retaining the foreground's layer,
    source order and interval. Only remove complete, isolated lower-layer
    components: an unrelated collision peer keeps the whole component.
    """
    families, layers = {}, {}
    for e in events:
        if e.kind != "Dialogue" or get_pos(e.text) is not None:
            continue
        layers.setdefault(e.layer,[]).append(e)
        if (not visible_map.get(e.source_index) or not e.layer.lstrip("-").isdigit()
                or e.effect or e.duration <= 0 or e.state.get("p",0)):
            continue
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
               visible_map[e.source_index])
        families.setdefault(key,[]).append(e)
    pending, copy_outlines = {}, {}
    for family in families.values():
        holds = [e for e in family if e.duration > max_piece_duration and
                 e.state.get("1a",0) == 0 and not inline_layout_key(e) and
                 not any(k in e.state for k in ("clip","iclip"))]
        if not holds:
            continue
        geometry = {}
        for hold in holds:
            profile = static_text_paint_geometry(hold,paint)
            if profile is not None:
                geometry[hold.source_index] = profile[0]
        for e in family:
            parents = [hold for hold in holds if int(hold.layer) > int(e.layer) and
                       hold.start_s <= e.start_s+1e-6 and hold.end_s >= e.end_s-1e-6 and
                       hold.source_index in geometry]
            if not parents:
                continue
            source = source_events.get(e.source_index,e)
            source_state = source.state or effective_state(source.text,source.defaults,source.styles)
            if source.effect or any(name in {"clip","iclip"} for block in
                                    OVERRIDE_RE.findall(source.text)
                                    for name,value in tokenize_override(block)):
                continue
            glow = any(abs(source_state.get(k,0)) > 0
                       for k in ("blur","be","shad","xshad","yshad"))
            # A short inline paint frame is also evidence after a prior run
            # removed its blur. Geometry still has to match the complete hold.
            frame = e.duration <= max_piece_duration and bool(inline_layout_key(e))
            coextensive = any(hold.start == e.start and hold.end == e.end for hold in parents)
            if not glow and not frame and not coextensive:
                continue
            profile = static_text_paint_geometry(e,paint)
            if profile is None or any("clip" in dict(s) or "iclip" in dict(s)
                                      for s,_,_ in profile[1]):
                continue
            parents = [hold for hold in parents if geometry[hold.source_index] == profile[0]]
            if len(parents) == 1 and (glow or frame or
                    parents[0].start == e.start and parents[0].end == e.end):
                pending[e.source_index] = (e,parents[0])
                # The outline selector only distinguishes one valid colour
                # from conflicting colours. Two samples preserve that evidence
                # without retaining every frame's complete inline state.
                samples = {}
                for signature,_,_ in profile[1]:
                    state = dict(signature)
                    colour = str(state.get("3c","000000")).upper()
                    if (state.get("3a",0) == 0 and
                            max(state.get("xbord",state.get("bord",0)),
                                state.get("ybord",state.get("bord",0))) > 0 and
                            re.fullmatch(r"[0-9A-F]{6}",colour)):
                        samples.setdefault(colour,state)
                        if len(samples) == 2:
                            break
                copy_outlines[e.source_index] = list(samples.values())
    removed, outlines = set(), {}
    for layer,peers in layers.items():
        copies = sorted((e for e in peers if e.source_index in pending),
                        key=lambda e:(e.start_s,e.end_s,e.source_index))
        foreign = [e for e in peers if e.source_index not in pending]
        components = []
        latest_end = -math.inf
        for e in copies:
            if not components or e.start_s > latest_end+1e-6:
                components.append([])
                latest_end = e.end_s
            components[-1].append(e)
            latest_end = max(latest_end,e.end_s)
        for component in components:
            start,end = component[0].start_s,max(e.end_s for e in component)
            if any(peer.start_s < end and peer.end_s > start for peer in foreign):
                continue
            for e in component:
                removed.add(e.source_index)
                parent = pending[e.source_index][1]
                outlines.setdefault(parent.source_index,[]).extend(copy_outlines[e.source_index])
    output = []
    for e in events:
        if e.source_index in removed:
            continue
        if e.source_index in outlines:
            text = static_text_paint_caption(e,[e.state]+outlines[e.source_index],paint)
            if text is not None:
                e = replace_event(e,text=text,effect="")
        output.append(e)
    return output,len(removed)


def flatten_aggressive_text_copies(events: list[Event],
                                   visible_map: dict[int,str],
                                   animated_sources: set[int] | None = None, *,
                                   max_piece_duration: float = .16,
                                   source_events: dict[int,Event] | None = None) -> tuple[list[Event], int]:
    """Replace stacked static copies of the same text with one.

    This is for level 1: color gradients, clipped stripes, shadows and
    alternate paint layers are intentionally replaced by a readable caption.
    No font, style name, color, language or strip-count assumption is used.
    """
    events, echo_removed = collapse_frame_text_echoes(
        events,max_piece_duration,source_events=source_events)
    events = [without_inert_spacing_tail(e)
              if e.source_index in (animated_sources or set()) and
                 e.state.get('1a',0) >= 254 and e.state.get('3a',0) >= 254
              else e for e in events]
    groups = {}
    kept = []
    collision_peers = {}
    paint = {"alpha", "1a", "2a", "3a", "4a", "c", "1c", "2c", "3c", "4c",
             "bord", "xbord", "ybord", "shad", "xshad", "yshad", "blur", "be"}
    if source_events is not None:
        events,paint_removed = flatten_held_text_paint_copies(
            events,visible_map,paint,source_events,max_piece_duration)
        echo_removed += paint_removed
    for e in events:
        if e.kind == "Dialogue" and get_pos(e.text) is None:
            collision_peers.setdefault(e.layer, []).append(e)
        visible = visible_map.get(e.source_index, "")
        pos = get_pos(e.text)
        if (e.kind != "Dialogue" or not visible or e.state.get("p", 0) > 0):
            kept.append(e)
            continue
        key = (e.start, e.end, e.style, e.name, e.margin_l, e.margin_r,
               e.margin_v, pos, visible)
        groups.setdefault(key, []).append(e)
    removed = echo_removed
    paint_groups = []
    for key, group in groups.items():
        # A differently scaled glow must not block an otherwise matching
        # shadow fill/contour stack. Partition only complete animated,
        # unclipped shadow families; keep every other geometry as its own
        # object for the existing later effect proofs.
        if (len(group) > 2 and all(e.source_index in (animated_sources or set()) and
                e.state.get('1a',0) >= 254 and e.state.get('3a',0) >= 254 and
                not inline_layout_key(e) and
                not any(k in e.state for k in ('clip','iclip')) for e in group)):
            layouts = {}
            for e in group:
                layouts.setdefault(text_layout_key(e),[]).append(e)
            paint_groups.extend((key,peers) for peers in layouts.values())
        else:
            paint_groups.append((key,group))
    for key, group in paint_groups:
        if len(group) < 2:
            kept.extend(group)
            continue
        if key[-2] is None or any(inline_layout_key(e) for e in group):
            # Equal final states do not prove equal inline spacing/fonts.
            # Compare every literal span, coalescing paint-only boundaries.
            layouts = {}
            spans = {}
            for e in group:
                profile = static_text_paint_geometry(e,paint)
                if profile is None:
                    kept.append(e)
                else:
                    geometry,spans[e.source_index] = profile
                    layouts.setdefault(geometry, []).append(e)
            for peers in layouts.values():
                ids = {e.source_index for e in peers}
                layers = {e.layer for e in peers}
                unpositioned = key[-2] is None
                # Same-layer unpositioned copies can occupy different rows.
                # Other captions can also displace either member of a stack.
                collision = unpositioned and (
                    len(layers) != len(peers) or
                    any(not layer.lstrip("-").isdigit() for layer in layers) or
                    any(other.source_index not in ids and
                        other.start_s < peers[0].end_s and other.end_s > peers[0].start_s
                        for layer in layers for other in collision_peers[layer]))
                opaque = [e for e in peers if all(
                    dict(signature).get("1a", 0) < 128 and
                    "clip" not in dict(signature) and "iclip" not in dict(signature)
                    for signature, _, _ in spans[e.source_index])]
                if len(peers) < 2 or collision or not opaque:
                    kept.extend(peers)
                    continue
                chosen = max(opaque, key=lambda e: (
                    int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
                    e.source_index))
                outlines = [dict(signature) for e in peers
                            for signature, _, _ in spans[e.source_index]]
                # Reuse level 1's paint choice while retaining all authored
                # geometry, including resets, wrapping and inline tracking.
                text = static_text_paint_caption(chosen,outlines,paint)
                if text is None:
                    kept.extend(peers)
                    continue
                caption = replace_event(chosen, text=text, effect="",
                                        source_index=min(ids))
                # Remove paint-only boundaries now so the existing frame
                # reducer can recognize the newly exposed complete caption.
                kept.extend(compact_static_overrides([caption], 0))
                removed += len(peers) - 1
            continue
        clipped = any("clip" in e.state or "iclip" in e.state for e in group)
        # Some effects paint the letters entirely with the shadow channel.
        # A stack of animated, coincident shadow copies is still one text
        # object; normalize it before dedup discards the channel evidence.
        shadow_paint = (not clipped and len({text_layout_key(e) for e in group}) == 1 and
                       all(e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254
                           for e in group) and
                       any(e.state.get("4a",0) < 254 and
                           any(abs(e.state.get(k,0)) > 0 for k in ("shad","xshad","yshad"))
                           for e in group))
        shadow_text = (shadow_paint and
                       all(e.source_index in (animated_sources or set()) and
                           e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254
                           for e in group))
        # Static shadow-painted stacks are the same text object too. Prove
        # the original spans are static and their offsets coincide before
        # transferring the top visible shadow's paint and actual position.
        # Ordinary filled text, moving shadows and separate labels stay out.
        static_shadow_text = (shadow_paint and not shadow_text and
            all(static_object_key(dataclass_replace(
                    (source_events or {}).get(e.source_index,e),effect=""),e.styles) is not None and
                unrotated_text_state(e.state) and
                e.state.get('borderstyle',1) == 1 and
                not any(k in e.state for k in ('org','clip','iclip')) and
                all(math.isfinite(e.state.get(k,0)) and e.state.get(k,0) > 0
                    for k in ('fs','fscx','fscy')) for e in group) and
            len({(e.state.get('xshad',e.state.get('shad',0)),
                  e.state.get('yshad',e.state.get('shad',0))) for e in group}) == 1 and
            all(math.isfinite(e.state.get(k,e.state.get('shad',0)))
                for e in group for k in ('xshad','yshad')))
        solid_stack = (not clipped and len({text_layout_key(e) for e in group}) == 1 and
                       any(e.state.get("1a",255) < 128 for e in group))
        if (len(group) < 2 or not (shadow_text or static_shadow_text or solid_stack or
                clipped and any(e.state.get("1a", 255) == 0 for e in group))):
            kept.extend(group)
            continue
        # A complete, unclipped text copy is the best source for the font and
        # size. The output paint is uniform and opaque by design in level 1.
        # Dominantly visible foreground paint may be slightly translucent.
        # Prefer its actual compositing order over an opaque backing fill.
        candidates = ([e for e in group if e.state.get('4a',0) < 254] if static_shadow_text or shadow_text else
                      [e for e in group if e.state.get("1a",255) < 128] if solid_stack else
                      [e for e in group if e.state.get("1a",255) == 0])
        chosen = max(candidates,key=lambda e:(
            "clip" not in e.state and "iclip" not in e.state,
            int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
            e.source_index))
        state = chosen.state
        outlines = [e.state for e in group]
        if shadow_text:
            # Animated shadow-painted letters still have real foreground
            # paint. Keep the established frozen glyph anchor while removing
            # shadow jitter; use the top visible contour below the fill rather
            # than conflicting lower glow colours. Effects become opaque.
            state = {**state,'1c':state.get('4c','FFFFFF'),'1a':0}
            fill_order = (int(chosen.layer), chosen.source_index)
            fill_border = max(chosen.state.get(k,chosen.state.get('bord',0))
                              for k in ('xbord','ybord'))
            # The selected fill may itself have a thin same-colour stroke.
            # That stroke is not its surrounding contour: use a wider visible
            # shadow-painted layer below the fill, in actual paint order.
            contours = [e for e in group if e.state.get('4a',0) < 254 and
                        (int(e.layer),e.source_index) < fill_order and
                        max(e.state.get(k,e.state.get('bord',0))
                            for k in ('xbord','ybord')) > max(0,fill_border)]
            contour = max(contours,key=lambda e:(
                int(e.layer) if e.layer.lstrip('-').isdigit() else 0,e.source_index)) if contours else None
            outlines = ([{**contour.state,'3c':contour.state.get('4c','000000'),'3a':0}]
                        if contour is not None else [])
        elif static_shadow_text:
            dx = state.get('xshad',state.get('shad',0))
            dy = state.get('yshad',state.get('shad',0))
            state = {**state,'pos':(key[-2][0]+dx,key[-2][1]+dy),
                     '1c':state.get('4c','FFFFFF'),'1a':state.get('4a',0)}
            outlines = [{**e.state,'3c':e.state.get('4c','000000'),
                         '3a':e.state.get('4a',0)} for e in group]
        text = aggressive_caption(state, OVERRIDE_RE.sub("", chosen.text),
                                  outline_states=outlines)
        kept.append(replace_event(chosen, text=text, layer=chosen.layer if shadow_text else "0", effect="",
                            source_index=min(e.source_index for e in group),
                            lyric=chosen.lyric or static_shadow_text))
        removed += len(group)-1
    return sorted(kept,key=lambda e:e.source_index), removed


def remove_fragmented_font_decorations(events: list[Event], visible_map: dict[int,str],
                                       metric: FontSpacing | None,
                                       source_events: dict[int,Event]) -> tuple[list[Event],int]:
    """Drop dense scattered stamps whose exact glyphs consist of tiny islands.

    Font names and letter payloads are not evidence. Require a coextensive
    caption in another exact font, a two-dimensional stamp cluster, and highly
    fragmented outlines for every removed glyph. Simple symbols, ordinary
    letters, rows, ambiguous caption families and unsupported fonts survive.
    """
    if metric is None or not metric.available:
        return events,0
    groups, captions = {}, {}
    for e in events:
        word = visible_map.get(e.source_index,"")
        source = source_events.get(e.source_index,e)
        if (e.kind != "Dialogue" or not word or e.duration <= 0 or e.effect or
                not e.layer.lstrip('-').isdigit() or
                source.effect or get_pos(e.text) is None or inline_layout_key(e) or
                any(k in e.state for k in ("clip","iclip")) or
                re.search(r"\\(?:t\s*\(|move\s*\(|fad(?:e)?\s*\(|[kK](?:f|o|t)?\d|[i]?clip\s*\()",source.text)):
            continue
        identity = (e.start,e.end,e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
        if len(word) >= 2 and e.state.get("1a",0) == 0:
            captions.setdefault(identity,[]).append(e)
        elif len(word) == 1 and not word.isspace():
            layout = (e.layer,) + tuple(e.state.get(k,DEFAULT_STATE.get(k))
                           for k in ("fn","fs","b","i","fscx","fscy","an","frz","frx","fry","fax","fay"))
            groups.setdefault((identity,layout),[]).append(e)
    removed = set()
    for (identity,layout),group in groups.items():
        if len(group) < 16:
            continue
        first = group[0]
        family = str(first.state.get("fn",""))
        parents = [p for p in captions.get(identity,())
                   if str(p.state.get("fn","")).casefold() != family.casefold()]
        if len(parents) != 1:
            continue
        parent = parents[0]
        all_positions = {get_pos(e.text) for e in group}
        if any(not math.isfinite(v) for pos in all_positions for v in pos):
            continue
        xs,ys = zip(*all_positions)
        height = text_height(first)
        if (len(all_positions) < 16 or height <= 0 or
                max(xs)-min(xs) < .5*height or max(ys)-min(ys) < .5*height):
            continue
        face = metric.matching_face(family,bool(first.state.get("b",0)),bool(first.state.get("i",0)))
        parent_face = metric.matching_face(str(parent.state.get("fn","")),
                                          bool(parent.state.get("b",0)),bool(parent.state.get("i",0)))
        if face is None or parent_face is None:
            continue
        # A second texture string must not stand in for a readable caption.
        parent_words = visible_map[parent.source_index]
        if any(ord(c) not in parent_face[2] or
               metric.fragmented_glyph(parent_face,c) is not False
               for c in set(parent_words) if not c.isspace()):
            continue
        glyphs = {visible_map[e.source_index] for e in group}
        fragments = {c for c in glyphs if ord(c) in face[2] and metric.fragmented_glyph(face,c) is True}
        stamps = [e for e in group if visible_map[e.source_index] in fragments]
        if len(fragments) < 4 or len(stamps) < 16 or len(stamps) < .9*len(group):
            continue
        positions = {get_pos(e.text) for e in stamps}
        xs,ys = zip(*positions)
        if (len(positions) < 16 or height <= 0 or
                max(xs)-min(xs) < .5*height or max(ys)-min(ys) < .5*height):
            continue
        # A slanted or rotated text row is still a row, not scattered artwork.
        mx,my = statistics.mean(xs),statistics.mean(ys)
        xx = sum((x-mx)**2 for x in xs)
        yy = sum((y-my)**2 for y in ys)
        xy = sum((x-mx)*(y-my) for x,y in positions)
        spread = (xx+yy-math.hypot(xx-yy,2*xy))/2
        if spread/len(positions) < (.1*height)**2:
            continue
        removed.update(e.source_index for e in stamps)
    return [e for e in events if e.source_index not in removed],len(removed)


def remove_masked_glyph_effects(events: list[Event],
                                visible_map: dict[int,str],
                                metric: FontSpacing | None = None,
                                animated_sources: set[int] | None = None) -> tuple[list[Event],int]:
    """Remove matching text copies or masks proven to trace an underlying glyph.

    Outline matching uses the exact font, contour topology and every control
    point. Shadow-only texture stacks can also be identified by their shared
    mask over a retained caption. Other unavailable-font or unsupported masks
    stay intact.
    This is a level 1 effect substitution, not an assertion of occlusion.
    """
    def closed_contours(commands, points):
        # ASS clips may explicitly return to a contour's first point, whereas
        # the font pen closes that same straight edge implicitly. Canonicalize
        # only identical endpoints; all other vertices and curves remain exact.
        result, vertices = [], []
        offset, start = 0, None
        for command in commands:
            count = {"m":1,"l":1,"b":3,"z":0}[command]
            coords = points[offset:offset+count]
            offset += count
            if command == "m":
                start = coords[0]
            if (command == "z" and result and result[-1] == "l" and
                    vertices[-1] == start):
                result.pop()
                vertices.pop()
            result.append(command)
            vertices.extend(coords)
        return result,vertices

    # Events are immutable within this pass; replacements are separate objects.
    # Resolve repeated geometry once rather than for every mask/base pair.
    positions = {e.source_index: get_pos(e.text) for e in events}
    heights = {e.source_index: text_height(e) for e in events}
    inline_layouts = {e.source_index: inline_layout_key(e) for e in events}
    layouts = {}
    placements = {}
    animated_sources = animated_sources or set()
    bases: dict[tuple,list[Event]] = {}
    for e in events:
        if (e.kind == "Dialogue" and positions[e.source_index] is not None and
                visible_map.get(e.source_index) and not inline_layouts[e.source_index] and
                "clip" not in e.state and "iclip" not in e.state and
                e.state.get("1a",0) < 255):
            x,y = positions[e.source_index]
            bases.setdefault((e.style,int(x//(20*e.unit)),int(y//(20*e.unit))),[]).append(e)
    removed, replacements, outlines, fonts = set(), {}, {}, {}
    texture_peers = {}
    shadow_masks, mask_peers, captions = {}, {}, {}
    shadow_sources, valid_shadow_masks = set(), set()
    for peer in events:
        # Inline letter spacing does not change a caption's anchor or paint.
        # Other inline overrides cannot supply this texture-stack evidence.
        inline = OVERRIDE_RE.findall(peer.text)[1:]
        if (peer.kind == "Dialogue" and positions[peer.source_index] is not None and
                visible_map.get(peer.source_index) and peer.state.get("1a",0) == 0 and
                "clip" not in peer.state and "iclip" not in peer.state and
                all(all(k == "fsp" for k,v in tokenize_override(block)) for block in inline)):
            captions.setdefault((peer.style,peer.name),[]).append(peer)
        if (peer.kind == "Dialogue" and positions[peer.source_index] is not None and
                not inline_layouts[peer.source_index] and "clip" in peer.state and
                "iclip" not in peer.state and peer.state.get("1a",0) >= 254 and
                peer.state.get("3a",0) >= 254 and peer.state.get("4a",255) < 128 and
                peer.state.get("borderstyle",1) == 1 and
                0 < max(abs(peer.state.get(k,peer.state.get("shad",0)))
                        for k in ("xshad","yshad")) <= peer.unit and
                max(abs(peer.state.get(k,peer.state.get("bord",0)))
                    for k in ("xbord","ybord")) <= peer.unit):
            family = (peer.style,peer.name,positions[peer.source_index],
                      visible_map.get(peer.source_index),state_key(peer,{"clip","blur","be"}))
            shadow_masks.setdefault(family,[]).append(peer)
            shadow_sources.add(peer.source_index)
            key = (peer.style,peer.name,peer.start,peer.end,positions[peer.source_index],
                   text_layout_key(peer),peer.state["clip"])
            mask_peers.setdefault(key,set()).add(visible_map.get(peer.source_index))
        if (peer.source_index in animated_sources and
                peer.kind == "Dialogue" and positions[peer.source_index] is not None and
                not inline_layouts[peer.source_index] and "clip" not in peer.state and
                "iclip" not in peer.state):
            key = (peer.style,peer.name,peer.start,peer.end,
                   visible_map.get(peer.source_index),peer.state.get("fn"),
                   positions[peer.source_index])
            texture_peers.setdefault(key,[]).append(peer)
    for e in events:
        pos = positions[e.source_index]
        if (e.kind != "Dialogue" or pos is None or inline_layouts[e.source_index] or
                "iclip" in e.state or "clip" not in e.state):
            continue
        # Parse only closed move/line/cubic contours, including scaled clips.
        mask = re.fullmatch(r"\(\s*(?:(\d+)\s*,\s*)?(m\s+.*?)\s*\)",
                            str(e.state["clip"]), re.I)
        if mask is None:
            continue
        commands, points = [], []
        parts = re.findall(r"([mlb])\s+([^mlb]+)",mask[2],re.I)
        valid = bool(parts) and not re.sub(r"[mlb\s]|"+NUMBER,"",mask[2],flags=re.I)
        scale_number = int(mask[1] or 1)
        if not 1 <= scale_number <= 16:
            continue
        clip_scale = 2 ** (scale_number-1)
        for command, coords in parts:
            command = command.lower()
            nums = list(map(float,re.findall(NUMBER,coords)))
            size = 6 if command == "b" else 2
            if not nums or len(nums)%size or (command == "m" and len(nums)!=2):
                valid = False; break
            if command == "m" and commands:
                commands.append("z")
            commands.extend([command]*(len(nums)//size))
            points.extend((x/clip_scale,y/clip_scale) for x,y in zip(nums[::2],nums[1::2]))
        commands.append("z")
        if not valid or not points:
            continue
        commands,points = closed_contours(commands,points)
        key = (e.style,e.name,e.start,e.end,pos,text_layout_key(e),e.state["clip"])
        if (e.source_index in shadow_sources and len(mask_peers.get(key,())) >= 2 and
                commands.count("m") >= 2):
            valid_shadow_masks.add(e.source_index)
            # Distinct filler strings painted through the same multi-contour
            # mask form a texture stack, rather than alternate caption text.
            # Require an opaque caption throughout this phase and an aligned
            # mask around its anchor; no font-name or payload blacklist.
            xs,ys = zip(*points)
            for base in captions.get((e.style,e.name),[]):
                bp = positions[base.source_index]
                radius = .25*min(heights[e.source_index],heights[base.source_index])
                if (base.start_s <= e.start_s+.001 and base.end_s >= e.end_s-.001 and
                        base.state.get("fn") != e.state.get("fn") and
                        visible_map[base.source_index] != visible_map[e.source_index] and
                        e.state.get("an",5) == base.state.get("an",5) == 5 and
                        all(abs(obj.state.get(k,0)) <= .001 for obj in (e,base)
                            for k in ("frz","frx","fry","fax","fay")) and
                        abs(pos[0]-bp[0]) <= radius and abs(pos[1]-bp[1]) <= radius and
                        min(xs) <= bp[0] <= max(xs) and min(ys) <= bp[1] <= max(ys) and
                        max(ys)-min(ys) <= 1.5*heights[base.source_index]):
                    removed.add(e.source_index)
                    break
        # Clips use screen coordinates independently of the texture's position.
        # Search at the mask itself; actors may label phases of the same glyph.
        xs,ys = zip(*points)
        radius, cell = heights[e.source_index], 20*e.unit
        offsets = [0]
        for op in commands:
            offsets.append(offsets[-1]+{"m":1,"l":1,"b":3,"z":0}[op])
        covered, matched, loose = set(), {}, set()
        # Spatial indexing changes only the search cost, not match tolerances.
        nearby = [base
                  for x in range(int((min(xs)-radius)//cell),int((max(xs)+radius)//cell)+1)
                  for y in range(int((min(ys)-radius)//cell),int((max(ys)+radius)//cell)+1)
                  for base in bases.get((e.style,x,y),[])]
        nearby.extend(base
                      for x in range(int((pos[0]-radius)//cell),int((pos[0]+radius)//cell)+1)
                      for y in range(int((pos[1]-radius)//cell),int((pos[1]+radius)//cell)+1)
                      for base in bases.get((e.style,x,y),[]))
        # Reject lifetime-ineligible candidates before sorting or layout checks.
        # Dict insertion order preserves the existing tie order by layer.
        candidates = {b.source_index:b for b in nearby
                      if not (b.start_s > e.start_s+.001 or b.end_s < e.end_s-.001)}
        for base in sorted(candidates.values(),
                           key=lambda b:int(b.layer) if b.layer.lstrip("-").isdigit() else 0,
                           reverse=True):
            bp = positions[base.source_index]
            tolerance = .12*min(heights[e.source_index],heights[base.source_index])
            if e.source_index not in placements:
                placements[e.source_index] = placement_key(e)
            if base.source_index not in placements:
                placements[base.source_index] = placement_key(base)
            if placements[e.source_index][0] != placements[base.source_index][0]:
                continue
            if (e.name == base.name and abs(pos[0]-bp[0]) <= tolerance and
                    abs(pos[1]-bp[1]) <= tolerance and
                    visible_map.get(e.source_index) == visible_map[base.source_index]):
                if e.source_index not in layouts:
                    layouts[e.source_index] = text_layout_key(e)
                if base.source_index not in layouts:
                    layouts[base.source_index] = text_layout_key(base)
                if layouts[e.source_index] == layouts[base.source_index]:
                    removed.add(e.source_index)
                    break
            glyph = visible_map[base.source_index]
            state = base.state
            if (not valid or metric is None or not metric.available or len(glyph)!=1 or
                    any(abs(state.get(k,0))>.001 for k in ("frz","frx","fry","fax","fay"))):
                continue
            face = metric.matching_face(str(state.get("fn","")),bool(state.get("b",0)),bool(state.get("i",0)))
            if face is None or ord(glyph) not in face[2]:
                continue
            key = (*face[:2],glyph)
            if key not in outlines:
                outlines[key] = None
                try:
                    from fontTools.ttLib import TTFont
                    from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
                    from fontTools.pens.qu2cuPen import Qu2CuPen
                    if face[:2] not in fonts:
                        font = TTFont(face[0],fontNumber=face[1])
                        fonts[face[:2]] = (font,font.getGlyphSet())
                    font,glyphs = fonts[face[:2]]
                    pen = DecomposingRecordingPen(glyphs)
                    glyphs[font.getBestCmap()[ord(glyph)]].draw(pen)
                    cubic = RecordingPen()
                    pen.replay(Qu2CuPen(cubic,max_err=.01,all_cubic=True))
                    ops, vertices = [], []
                    for op, coords in cubic.value:
                        ops.append({"moveTo":"m","lineTo":"l","curveTo":"b","closePath":"z"}[op])
                        vertices.extend((x,-y) for x,y in coords)
                    ops,vertices = closed_contours(ops,vertices)
                    os2,hhea = font['OS/2'],font['hhea']
                    outlines[key] = (ops,vertices,font['head'].unitsPerEm,
                        font['hmtx'].metrics[font.getBestCmap()[ord(glyph)]][0],
                        ((os2.usWinAscent,os2.usWinDescent),
                         (hhea.ascent,-hhea.descent),
                         (os2.sTypoAscender,-os2.sTypoDescender)))
                except Exception:
                    pass  # Corrupt/unsupported fonts cannot authorize deletion.
            outline = outlines[key]
            if outline is None or not outline[1] or int(state.get("an",5)) not in range(1,10):
                continue
            starts = [i for i in range(len(commands)-len(outline[0])+1)
                      if commands[i:i+len(outline[0])] == outline[0] and
                      not any(j in covered for j in range(i,i+len(outline[0])))]
            if not starts:
                continue
            # Fit just translation and one uniform font-size multiplier; never
            # warp unrelated contours into a match. ASS/em conventions vary.
            fs = state.get("fs",0)/outline[2]
            model = [(x*fs*state.get("fscx",100)/100,y*fs*state.get("fscy",100)/100)
                     for x,y in outline[1]]
            mx,my = (statistics.mean(v) for v in zip(*model))
            denom = sum((x-mx)**2+(y-my)**2 for x,y in model)
            if denom <= 0:
                continue
            for start in starts:
                stop = start+len(outline[0])
                segment = points[offsets[start]:offsets[stop]]
                if len(segment) != len(model):
                    continue
                px,py = (statistics.mean(v) for v in zip(*segment))
                factor = sum((x-mx)*(a-px)+(y-my)*(b-py)
                             for (x,y),(a,b) in zip(model,segment))/denom
                error = max(abs(v) for (x,y),(a,b) in zip(model,segment)
                            for v in (a-px-factor*(x-mx),b-py-factor*(y-my)))
                an = int(state.get("an",5))
                ax,ay = ((an-1)%3)/2, 1-((an-1)//3)/2
                dx = bp[0]-ax*outline[3]*fs*state.get("fscx",100)/100*factor
                dy = [bp[1]+(asc-ay*(asc+desc))*fs*state.get("fscy",100)/100*factor
                      for asc,desc in outline[4]]
                # Word masks can use shaped advances while the source glyphs
                # use individually rounded positions. Keep exact contour tests;
                # a wider anchor allowance needs a complete multi-glyph match.
                tolerance = max(1.5*base.unit,.04*heights[base.source_index])
                anchor_error = max(abs(px-factor*mx-dx),
                    min(abs(py-factor*my-y) for y in dy))
                if (not .5 <= factor <= 1.5 or error > max(.03,.001*heights[base.source_index]) or
                        anchor_error > max(tolerance,.12*heights[base.source_index])):
                    continue
                if anchor_error > tolerance:
                    loose.add(base.source_index)
                covered.update(range(start,stop))
                matched[base.source_index] = replace_event(base,
                    text=aggressive_caption(state,glyph))
        if len(covered) == len(commands) and (not loose or
                len({get_pos(base.text) for base in matched.values()}) >= 3):
            removed.add(e.source_index)
            # The mask can be the principal visible fill over a transparent
            # glyph. Keep the proven text readable when removing that fill.
            replacements.update(matched)
            # A texture may have both a glyph-shaped mask and an unmasked
            # animated copy. Only remove that companion when the proven mask
            # traces a different font, and timing, actor, glyph and anchor agree.
            # Do not extend this evidence to other phases or nearby objects.
            if (matched and e.source_index in animated_sources and
                    all(base.state.get("fn") != e.state.get("fn")
                        for base in matched.values())):
                key = (e.style,e.name,e.start,e.end,
                       visible_map.get(e.source_index),e.state.get("fn"),pos)
                for peer in texture_peers.get(key,[]):
                    if (all(peer.state.get(k,DEFAULT_STATE.get(k)) ==
                            e.state.get(k,DEFAULT_STATE.get(k))
                            for k in ("an","fsp","b","i","u","s","1a",
                                      "bord","shad","frx","fry","fax","fay"))):
                        removed.add(peer.source_index)
    # Follow only touching phases of the same proven texture carrier. This
    # removes its clipped wipe-out too, without affecting a later unrelated cue.
    for family in shadow_masks.values():
        runs = []
        for e in sorted((obj for obj in family if obj.source_index in valid_shadow_masks),
                        key=lambda obj:(obj.start_s,obj.end_s)):
            if not runs or e.start_s > max(obj.end_s for obj in runs[-1])+.001:
                runs.append([])
            runs[-1].append(e)
        for run in runs:
            if any(e.source_index in removed for e in run):
                removed.update(e.source_index for e in run)
    for font,_ in fonts.values():
        font.close()
    return [replacements.get(e.source_index,e) for e in events
            if e.source_index not in removed],len(removed)


def match_scale_trail(component: list[Event], visible: str,
                      animated_sources: set[int], positions: dict[int,tuple[float,float]],
                      heights: dict[int,float], layouts: dict[int,tuple]) -> list[Event] | None:
    """Return proven members of an unclipped, drifting scale-trail candidate.

    Validate shared layout, lifetime, scale and rendered-anchor trajectories
    using the caller's cached geometry. Return None for an unproven family;
    event grouping, caption selection and replacements remain with the caller.
    """
    if (len(component) < 3 or
            sum(e.source_index in animated_sources for e in component) < 3 or
            len({layouts[e.source_index] for e in component}) != 1 or
            len({e.name for e in component}) != 1):
        return None
    trail = False
    # Three distinct scales tracing the same affine position/scale
    # path establish an effect family. A nearby main fill may use
    # a slightly different authored scale; it must sit at the
    # largest trail sample, rather than at its displaced tail.
    samples=sorted(component,key=lambda e:e.state.get("fscx",100))
    lo,hi=samples[0],samples[-1]
    # Prefer the dense trail when an opaque main fill lies off its
    # scale trajectory. It is validated separately below.
    faded=[e for e in samples if e.state.get("1a",0)>0]
    if len(faded)>=3:
        samples=faded
        lo,hi=samples[0],samples[-1]
    sample_ids={e.source_index for e in samples}
    sample_start=max(e.start_s for e in samples)
    sample_end=min(e.end_s for e in samples)
    # A short lead-in/out phase outside the trail's shared visible
    # interval is not a trail member. Keep it independently rather
    # than letting it invalidate an otherwise proven family.
    members=[e for e in component if e.source_index in sample_ids or
             min(e.end_s,sample_end)>max(e.start_s,sample_start)]
    delta=hi.state.get("fscx",100)-lo.state.get("fscx",100)
    tolerance=max(.01*heights[hi.source_index],.05*hi.unit)
    if (sample_end>sample_start and delta>1e-6 and
            len({e.state.get("fscx",100) for e in samples})>=3 and
            all(e.source_index in animated_sources for e in samples)):
        lx,ly=positions[lo.source_index]; hx,hy=positions[hi.source_index]
        sy0,sy1=lo.state.get("fscy",100),hi.state.get("fscy",100)
        trail=all(
            abs(positions[e.source_index][0]-(lx+(hx-lx)*f))<=tolerance and
            abs(positions[e.source_index][1]-(ly+(hy-ly)*f))<=tolerance and
            abs(e.state.get("fscy",100)-(sy0+(sy1-sy0)*f))<=.05
            for e in samples
            for f in [(e.state.get("fscx",100)-lo.state.get("fscx",100))/delta])
        # Assess the rendered anchors, including displacement
        # around distant origins. Fit the whole family rather than
        # measuring every rotation against one endpoint sample.
        # Authored anchors/scales must still follow the path above.
        rendered=[]
        angle=hi.state.get("frz",0)
        for e in samples:
            px,py=positions[e.source_index]
            ox,oy=e.state.get("org",(px,py))
            turn=math.radians(math.remainder(e.state.get("frz",0),360))
            dx,dy=px-ox,py-oy
            rendered.append((e.state.get("fscx",100),
                             ox+dx*math.cos(turn)+dy*math.sin(turn),
                             oy-dx*math.sin(turn)+dy*math.cos(turn)))
        mean_scale=sum(v[0] for v in rendered)/len(rendered)
        mean_x=sum(v[1] for v in rendered)/len(rendered)
        mean_y=sum(v[2] for v in rendered)/len(rendered)
        variance=sum((v[0]-mean_scale)**2 for v in rendered)
        slope_x=sum((v[0]-mean_scale)*(v[1]-mean_x)
                    for v in rendered)/variance
        slope_y=sum((v[0]-mean_scale)*(v[2]-mean_y)
                    for v in rendered)/variance
        trail &= all(math.hypot(
            x-mean_x-slope_x*(scale-mean_scale),
            y-mean_y-slope_y*(scale-mean_scale))<=.06*heights[hi.source_index]
            for scale,x,y in rendered)
        # Rotation also changes glyph orientation around its
        # rendered anchor; large turns remain unsafe even when
        # anchors happen to trace a straight line.
        reference_anchor=rendered[-1][1:]
        for e in members:
            if e.source_index not in sample_ids:
                px,py=positions[e.source_index]
                ox,oy=e.state.get("org",(px,py))
                rotation=math.radians(math.remainder(e.state.get("frz",0),360))
                dx,dy=px-ox,py-oy
                anchor=(ox+dx*math.cos(rotation)+dy*math.sin(rotation),
                        oy-dx*math.sin(rotation)+dy*math.cos(rotation))
                trail &= math.dist(anchor,reference_anchor)<=.18*heights[e.source_index]
            radius=heights[e.source_index]*max(1,len(visible))
            turn=math.radians(math.remainder(e.state.get("frz",0)-angle,360))
            trail &= 2*radius*abs(math.sin(turn/2))<=.06*heights[hi.source_index]
        trail &= all(
            abs(positions[e.source_index][0]-hx)<=.18*heights[e.source_index] and
            abs(positions[e.source_index][1]-hy)<=.18*heights[e.source_index] and
            e.state.get("fscx",100)>=hi.state.get("fscx",100) and
            e.state.get("1a",0)<=hi.state.get("1a",0)
            for e in members if e.source_index not in sample_ids)
    return members if trail else None


def upright_text_holds(candidates: list[Event], source_events: dict[int,Event]) -> list[Event]:
    """Find candidate poses actually held by the original animated text.

    A midpoint sample that merely crosses zero is insufficient. Compare the
    complete settled geometry, so a hidden or flipped pose cannot win either.
    """
    holds = []
    geometry = ('pos','org','fn','fs','fscx','fscy','fsp','an','b','i','fax','fay',
                'clip','iclip','p','pbo','q')
    for e in candidates:
        original = source_events.get(e.source_index)
        if (not upright_text_state(e.state) or original is None or
                original.duration <= 0 or inline_layout_key(original)):
            continue
        settled = []
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        block = ''.join(OVERRIDE_RE.findall(prefix))
        freeze_block(block,original.duration,original.defaults,original.defaults,
                     original.styles,0,settled_states=settled)
        if any(upright_text_state(state,include_shadow=True) and
               all(state.get(k,DEFAULT_STATE.get(k)) == e.state.get(k,DEFAULT_STATE.get(k))
                   for k in geometry) for state in settled):
            holds.append(e)
    return holds


def event_override_tokens(e: Event) -> list[tuple[str,str]]:
    return [token for block in OVERRIDE_RE.findall(e.text)
            for token in tokenize_override(block)]


def without_inert_spacing_tail(e: Event) -> Event:
    """Ignore a tracking reset after the last literal glyph, with no ink.

    Generated punctuation can reset tracking after its sole character. The
    reset cannot move that character, but a final-state layout key mistakes
    it for the character's tracking. Keep all painted inline changes intact.
    """
    tail = re.search(r'(?:\{[^}]*\})+$',e.text)
    if tail is None or not simplify_text(e.text[:tail.start()],visible_only=True)[1]:
        return e
    tokens = [token for block in OVERRIDE_RE.findall(tail.group())
              for token in tokenize_override(block)]
    if not tokens or any(k != 'fsp' or not re.fullmatch(NUM,v) or
                         not math.isfinite(float(v)) for k,v in tokens):
        return e
    text = e.text[:tail.start()]
    tracking = effective_state(text,e.defaults,e.styles).get('fsp',0)
    return replace_event(e,text=text,state={**e.state,'fsp':tracking})


def literal_font_spans(e: Event) -> tuple[tuple[str,str],...] | None:
    """Identify literal spans with stationary font changes only.

    Resolve empty font resets so source and frozen overrides share a key.
    Paint, geometry, resets and transforms within text require other proofs.
    """
    state = e.defaults.copy()
    spans = []
    for part in re.split(r'(\{[^}]*\})',e.text):
        if part.startswith('{'):
            tokens = tokenize_override(part[1:-1])
            if spans and any(tag != 'fn' for tag,value in tokens):
                return None
            for tag,value in tokens:
                apply_tag(state,tag,value,e.styles,e.defaults)
        elif part:
            font = str(state.get('fn','Arial'))
            if spans and spans[-1][1] == font:
                spans[-1] = (spans[-1][0]+part,font)
            else:
                spans.append((part,font))
    return tuple(spans)


def parse_effect_transform(value: str, duration: float,
                           allowed: set[str], *, allow_instant: bool = False,
                           allow_after_end: bool = False) -> tuple[float,float,list[tuple[str,str]]] | None:
    """Validate one transform used as evidence for an effect family.

    Resolve all four ASS timing forms, requiring forward finite timing and
    positive acceleration. Instant alpha handoffs can opt into equal endpoints.
    These proofs allow at most 50 ms of endpoint
    rounding; the general static freezer retains its more permissive parsing.
    Geometry-only paint proofs may allow transforms ending after the cue.
    Each matcher supplies the tags that its own effect can safely change.
    """
    prefix,sep,tail = value[1:-1].partition('\\')
    try:
        args = [float(v.strip()) for v in prefix.rstrip(', ').split(',') if v.strip()]
    except ValueError:
        return None
    changes = tokenize_override('\\'+tail)
    begin,end = args[:2] if len(args) >= 2 else (0,1000*duration)
    if (not sep or len(args) > 3 or not all(math.isfinite(v) for v in args) or
            not 0 <= begin <= end or not allow_after_end and end > 1000*duration+50 or
            not allow_instant and begin == end or
            len(args) in (1,3) and args[-1] <= 0 or
            any(tag not in allowed for tag,value in changes)):
        return None
    return begin,end,changes


def opaque_text_effect_state(state: dict) -> bool:
    """Recognize unmasked opaque glyph effects with ordinary outlines."""
    return (not state.get('p',0) and state.get('1a',0) == 0 and
            state.get('borderstyle',1) == 1 and
            not any(k in state for k in ('clip','iclip','org')) and
            not any(abs(state.get(k,state.get('shad',0))) > .001
                    for k in ('xshad','yshad')))


def parse_effect_move(value: str, duration: float, *,
                      endpoint_slack: float = 0) -> list[float] | None:
    """Validate an effect's original move, retaining its source coordinates."""
    try:
        nums = [float(v) for v in value.strip('()').split(',')]
    except ValueError:
        return None
    if (len(nums) not in (4,6) or not all(math.isfinite(v) for v in nums) or
            len(nums) == 6 and not 0 <= nums[4] < nums[5] <= 1000*duration+endpoint_slack):
        return None
    return nums


def collapse_shrinking_glyph_rows(events: dict[int,Event],
                                  metric: FontSpacing | None,
                                  max_blur: float) -> tuple[dict[int,Event],int]:
    """Use a held caption for its complete moving, shrinking, fading row.

    Work before freezing/merging glyphs loses their source identity. Every
    layer must spell the whole caption and match its exact-font anchors at
    the held size. Paint copies may differ; the retained caption supplies
    formatting. Touching entrances and copies within the hold share that proof.
    Without a unique held owner, keep the existing simplification.
    """
    if metric is None or not metric.available:
        return events,0
    # Reject unrelated families before parsing transforms or freezing holds.
    # Every accepted shrinking fade must explicitly change both scale axes
    # and at least one visible alpha channel inside a moving source event.
    families = {(e.style,e.name) for e in events.values()
                if e.kind == 'Dialogue' and
                re.search(r'\\move\s*\(',e.text) and
                re.search(r'\\t\s*\(',e.text) and
                re.search(r'\\fscx(?=[^A-Za-z]|$)',e.text) and
                re.search(r'\\fscy(?=[^A-Za-z]|$)',e.text) and
                re.search(r'\\(?:alpha|[13]a)(?=[^A-Za-z]|$)',e.text)}
    families &= {(e.style,e.name) for e in events.values()
                 if (e.style,e.name) in families and e.kind == 'Dialogue' and
                 re.search(r'\\pos\s*\(',e.text) and
                 not re.search(r'\\move\s*\(',e.text) and
                 len(OVERRIDE_RE.sub('',e.text).strip()) >= 3}
    if not families:
        return events,0

    def geometry(e: Event) -> tuple:
        return (e.style,e.name,placement_key(e),
                tuple((k,v) for k,v in text_layout_key(e)
                      if k not in {'fscx','fscy'}))

    groups, captions = {}, {}
    for original in events.values():
        if (original.kind != 'Dialogue' or original.duration <= 0 or
                (original.style,original.name) not in families or
                not re.search(r'\\(?:move|pos)\s*\(',original.text) or
                inline_layout_key(original)):
            continue
        tokens = event_override_tokens(original)
        moves = [v for k,v in tokens if k == 'move']
        transforms = [v for k,v in tokens if k == 't']
        text = simplify_text(original.text,visible_only=True)[1]
        if not text:
            continue
        state = effective_state(original.text,original.defaults,original.styles)
        e = dataclass_replace(original,state=state)
        if (not unrotated_text_state(state) or state.get('p',0) or
                state.get('borderstyle',1) != 1 or
                any(k in state for k in ('clip','iclip','org')) or
                any(abs(state.get(k,0)) > .001 for k in ('fax','fay')) or
                any(k in {'fad','fade','k','K','kf','ko'} for k,v in tokens)):
            continue
        if not moves and len(text.strip()) >= 3 and get_pos(e.text) is not None:
            # A held caption may fade, but its font and geometry must stay held.
            if any(any(k not in {'alpha','1a','2a','3a','4a'}
                       for k,v in tokenize_override('\\'+value[1:-1].partition('\\')[2]))
                   for value in transforms):
                continue
            frozen,visible,drawings = simplify_visual_text(
                e.text,max_blur,e.duration,e.defaults,e.styles,1,
                upright_crossings=False)
            held = replace_event(e,text=frozen)
            if drawings or visible != text or held.state.get('1a',0) != 0:
                continue
            for boundary in (e.start_s,e.end_s):
                captions.setdefault(geometry(held),{}).setdefault(boundary,[]).append(held)
            continue
        if (len(text) != 1 or text.isspace() or unicodedata.combining(text) or
                len(moves) != 1 or len(transforms) != 1 or get_pos(e.text) is not None):
            continue
        move = parse_effect_move(moves[0],e.duration,endpoint_slack=50)
        transform = parse_effect_transform(transforms[0],e.duration,
                                           {'fscx','fscy','alpha','1a','2a','3a','4a','blur','be'})
        if (move is None or transform is None or
                transform[0] >= 1000*e.duration or
                len(move) == 6 and move[4] >= 1000*e.duration or
                abs(move[0]-move[2]) > e.unit):
            continue
        final = state.copy()
        for tag,value in transform[2]:
            apply_tag(final,tag,value,e.styles,e.defaults)
        if (not all(0 < final.get(k,100) < state.get(k,100) for k in ('fscx','fscy')) or
                final.get('1a',0) != 255 or final.get('3a',0) != 255 or
                state.get('1a',0) == 255 and
                (state.get('3a',0) == 255 or state.get('bord',0) <= 0)):
            continue
        key = (geometry(e),e.start_s,e.end_s,e.layer)
        groups.setdefault(key,[]).append((e,text,move))

    caption_index = {key:(sorted(times),times) for key,times in captions.items()}
    proposals = []
    for (key,start,end,layer),peers in groups.items():
        peers.sort(key=lambda item:item[2][0])
        if len(peers) < 3 or len({m[0] for e,c,m in peers}) != len(peers):
            continue
        owners = []
        for time,helds in nearby_boundary_groups(caption_index,key,end):
            # Extend touching entrances; an existing hold can also cover the
            # whole burst. Never bridge a real gap or erase a partial overlap.
            if abs(time-end) > 1e-6:
                continue
            for held in helds:
                literal = simplify_text(held.text,visible_only=True)[1]
                if ''.join(c for e,c,m in peers) != ''.join(literal.split()):
                    continue
                pos = get_pos(held.text)
                height = held.state.get('fs',20)*held.state.get('fscy',100)/100
                if (held.duration < end-start or
                        not (held.start_s == end or
                             held.start_s <= start and held.end_s >= end) or
                        any(abs(y-pos[1]) > .3*height for e,c,m in peers
                            for y in (m[1],m[3])) or
                        not metric.matches_authored_glyph_positions(
                            held.state,[m[0] for e,c,m in peers],literal,pos[0],held.unit)):
                    continue
                owners.append(held)
        if len(owners) == 1:
            proposals.append((start,end,layer,peers,owners[0]))

    # Ambiguous repetitions at one boundary cannot share ownership. Different
    # paint layers of the same complete row deliberately share a caption.
    claims = {}
    for start,end,layer,peers,held in proposals:
        key = (held.source_index,layer,end)
        claims[key] = claims.get(key,0)+1
    removed, replacements = set(), {}
    for start,end,layer,peers,held in proposals:
        if claims[(held.source_index,layer,end)] != 1:
            continue
        removed.update(e.source_index for e,c,m in peers)
        previous = replacements.get(held.source_index,held)
        if start < previous.start_s:
            replacements[held.source_index] = replace_event(
                held,start=format_time(start),start_s=start)
    if not removed:
        return events,0
    # Extending an entrance must not revive a preceding caption that was
    # already completely transparent. A single validated terminal alpha
    # transform proves a clean handoff; visible/ambiguous overlaps stay intact.
    for current in list(replacements.values()):
        original = events[current.source_index]
        if current.start_s >= original.start_s:
            continue
        preceding = [held for time,holds in nearby_boundary_groups(
                         caption_index,geometry(current),original.start_s)
                     for held in holds if held.source_index != current.source_index and
                     held.end_s == original.start_s and held.start_s < current.start_s and
                     held.layer == current.layer and get_pos(held.text) == get_pos(current.text)]
        if len(preceding) != 1:
            continue
        held = preceding[0]
        source = events[held.source_index]
        transforms = [v for k,v in event_override_tokens(source) if k == 't']
        if len(transforms) != 1:
            continue
        fade = parse_effect_transform(transforms[0],source.duration,
            {'alpha','1a','2a','3a','4a'},allow_instant=True)
        if fade is None or source.start_s+fade[1]/1000 > original.start_s+1e-6:
            continue
        final = effective_state(source.text,source.defaults,source.styles)
        for tag,value in fade[2]:
            apply_tag(final,tag,value,source.styles,source.defaults)
        if not all(final.get(k,0) == 255 for k in ('1a','3a','4a')):
            continue
        finish = source.start_s+fade[1]/1000
        previous = replacements.get(held.source_index,held)
        replacements[held.source_index] = replace_event(
            previous,end=format_time(finish),end_s=finish)
        # If the preceding source stays visible for part of the entrance,
        # delay the replacement caption to its fade boundary. Keep real gaps.
        if finish > current.start_s:
            replacements[current.source_index] = replace_event(
                current,start=format_time(finish),start_s=finish)
    return {idx:replacements.get(idx,e) for idx,e in events.items() if idx not in removed},len(removed)


def collapse_moving_glyph_sequences(events: list[Event], visible_map: dict[int,str],
                                    source_events: dict[int,Event],
                                    metric: FontSpacing | None) -> tuple[list[Event],int]:
    """Replace proven stationary/moving/stationary text with one held caption.

    A whole fragment must repeat at its exact authored destination. Isolated
    glyph runs instead need exact font advances and an authored word anchor.
    The run must end in the same completed text or a complete recorded fade.
    Consecutive moves with the same destination can share that proof.
    Only fades at those recorded phase boundaries belong to the run; partial,
    overlapping or ambiguous groups never authorize removal.
    """
    # This proof needs at least one moving fragment without transforms or
    # fades. Reject impossible families before resolving every source tag.
    families = set()
    for original in source_events.values():
        if (original.kind != 'Dialogue' or original.duration <= 0 or
                not re.search(r'\\move(?=[^A-Za-z]|$)',original.text,re.I) or
                not OVERRIDE_RE.sub('',original.text) or
                get_pos(original.text) is not None or
                inline_layout_key(original) and literal_font_spans(original) is None):
            continue
        tokens = event_override_tokens(original)
        if (sum(tag == 'move' for tag,value in tokens) == 1 and
                not any(tag in {'t','fad','fade'} for tag,value in tokens)):
            families.add((original.style,original.name))
    if not families:
        return events,0

    def geometry(e: Event) -> tuple:
        spans = literal_font_spans(e) if inline_layout_key(e) else ()
        if spans is not None and len(spans) <= 1:
            spans = ()
        return (e.style,e.name,placement_key(e)[:-1],text_layout_key(e),spans)

    def paint(state: dict) -> tuple:
        return (state.get('1c'),state.get('3c'),state.get('3a',0),
                state.get('xbord',state.get('bord',0)),
                state.get('ybord',state.get('bord',0)))

    static, moves, fades = {}, {}, {}
    for original in source_events.values():
        if ((original.style,original.name) not in families or
                original.kind != 'Dialogue' or original.duration <= 0 or
                inline_layout_key(original) and literal_font_spans(original) is None):
            continue
        word = simplify_text(original.text,visible_only=True)[1]
        if (not word or OVERRIDE_RE.sub('',original.text) != word or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word)):
            continue
        state = effective_state(original.text,original.defaults,original.styles)
        if not upright_text_state(state) or not opaque_text_effect_state(state):
            continue
        p = dataclass_replace(original,state=state)
        parts = event_override_tokens(p)
        movement = [value for tag,value in parts if tag == 'move']
        transforms = [value for tag,value in parts if tag == 't']
        pos = get_pos(p.text)
        key = geometry(p)
        if not movement and not transforms and pos is not None:
            static.setdefault((key,word),[]).append(p)
        elif len(movement) == 1 and not transforms and pos is None:
            if any(tag in {'fad','fade'} for tag,value in parts):
                continue
            # Generated phase times can exceed centisecond event boundaries
            # by a frame; the matching held phase proves the intended landing.
            values = parse_effect_move(movement[0],p.duration,endpoint_slack=50)
            if values is None:
                continue
            moves.setdefault((key,p.start,p.end,values[3],paint(state)),[]).append((p,values,word))
        elif not movement and len(transforms) == 1 and pos is not None:
            transform = parse_effect_transform(transforms[0],p.duration,
                                               {'alpha','1a','3a','blur','be'})
            if transform is None or any(tag in {'fad','fade'} for tag,value in parts):
                continue
            begin,end,changes = transform
            final = state.copy()
            for tag,value in changes:
                apply_tag(final,tag,value,p.styles,p.defaults)
            if (final.get('1a',0) >= 254 and
                    (final.get('3a',0) >= 254 or
                     max(state.get('xbord',state.get('bord',0)),
                         state.get('ybord',state.get('bord',0))) <= .001)):
                fades.setdefault((key,p.start,word,pos),[]).append(p)

    current = {}
    for e in events:
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (pos is not None and word and
                (not inline_layout_key(e) or literal_font_spans(e) is not None) and
                upright_text_state(e.state)):
            # A long fade can outweigh its opaque hold during earlier phase
            # selection. The source hold still proves this exact text/pose;
            # restore its opaque paint only after the complete run is proven.
            current.setdefault((geometry(e),word,pos),[]).append(e)

    def retained(p: Event) -> Event | None:
        matches = [e for e in current.get((geometry(p),simplify_text(p.text,visible_only=True)[1],
                                           get_pos(p.text)),[])
                   if e.start_s <= p.start_s+.001 and e.end_s >= p.end_s-.001]
        opaque = [e for e in matches if e.state.get('1a',0) == 0]
        if opaque:
            matches = opaque
        return matches[0] if len(matches) == 1 else None

    groups = []
    by_start = {}
    for (key,start,end,y,colors),peers in moves.items():
        peers.sort(key=lambda item:item[1][2])
        if (len({value[2] for p,value,word in peers}) != len(peers) or
                not any(math.dist(value[:2],value[2:4]) > p.unit for p,value,word in peers)):
            continue
        word = ''.join(char for p,value,char in peers)
        group = (key,start,end,y,colors,word,peers)
        groups.append(group)
        by_start.setdefault((key,start,word),[]).append(group)

    def fits(group: tuple, parent: Event) -> bool:
        key,start,end,y,colors,word,peers = group
        pos = get_pos(parent.text)
        if len(peers) == 1:
            # A whole fragment repeats the authored stationary text exactly;
            # its recorded destination proves placement without font fitting.
            return math.dist(tuple(peers[0][1][2:4]),pos) <= .001
        if metric is None or not metric.available or abs(pos[1]-y) > parent.unit:
            return False
        anchor = metric.fragment_anchor(parent.state,[value[2] for p,value,char in peers],
                                        [char for p,value,char in peers],word,parent.unit,
                                        allow_tracking=True,separate_glyphs=True)
        return anchor is not None and abs(anchor-pos[0]) <= 1.5*parent.unit

    def letter_fades(group: tuple) -> list[Event] | None:
        key,start,end,y,colors,word,peers = group
        matches = [[p for p in fades.get((key,end,char,tuple(value[2:4])),[])
                    if paint(p.state) == colors]
                   for p,value,char in peers]
        if any(len(items) != 1 for items in matches):
            return None
        result = [items[0] for items in matches]
        return result if len({p.end for p in result}) == 1 else None

    proposals = []
    for seed in sorted(groups,key=lambda group:(group[6][0][0].start_s,group[6][0][0].source_index)):
        key,start,end,y,colors,word,peers = seed
        parents = [p for p in static.get((key,word),[]) if p.end == start and
                   retained(p) is not None and fits(seed,p)]
        if len(parents) != 1:
            continue
        parent = parents[0]
        before = retained(parent)
        chain = [seed]
        after = None
        after_source = None
        departing = None
        while True:
            last = chain[-1]
            holds = [p for p in static.get((key,word),[]) if p.start == last[2] and
                     get_pos(p.text) == get_pos(parent.text) and paint(p.state) == colors and
                     retained(p) is not None]
            if len(holds) == 1:
                after_source = holds[0]
                after = retained(after_source); break
            if holds:
                break
            departing = letter_fades(last)
            if departing is not None:
                break
            following = [g for g in by_start.get((key,last[2],word),[]) if
                         g[4] == colors and fits(g,parent)]
            if len(following) != 1 or following[0] in chain:
                break
            chain.append(following[0])
        if after is None and departing is None:
            continue
        source_ids = {p.source_index for group in chain for p,value,char in group[6]}
        source_ids.add(before.source_index)
        # Authored fades at the start may survive separately when the
        # previous row overlaps. Only an exact, touching word phase belongs.
        prefixes = [p for p in static.get((key,word),[]) if p.end == before.start and
                    get_pos(p.text) == get_pos(parent.text) and paint(p.state) == paint(parent.state) and
                    retained(p) is not None and
                    any(tag == 'fad' for tag,value in event_override_tokens(p))]
        prefix_caption = retained(prefixes[0]) if len(prefixes) == 1 else None
        if prefix_caption is not None:
            source_ids.add(prefix_caption.source_index)
        if after is not None:
            source_ids.add(after.source_index)
        boundaries = {group[2] for group in chain}
        if after_source is not None:
            boundaries.add(after_source.end)
        # Word flashes and complete letter fades share the recorded word
        # boundaries. Their different paint is decorative, not a new caption.
        for boundary in boundaries:
            overlays = [p for p in fades.get((key,boundary,word,get_pos(parent.text)),[])
                        if max(p.state.get('xbord',p.state.get('bord',0)),
                               p.state.get('ybord',p.state.get('bord',0))) <= .001]
            if len(overlays) == 1:
                source_ids.add(overlays[0].source_index)
        final_group = chain[-1]
        exit_group = (key,final_group[1],after_source.end if after_source is not None else final_group[2],
                      y,colors,word,final_group[6])
        exiting = letter_fades(exit_group)
        if exiting is not None:
            source_ids.update(p.source_index for p in exiting)
        finish = after.end_s if after is not None else final_group[6][0][0].end_s
        if exiting is not None and after_source is not None:
            # Earlier phase reduction can absorb a one-letter fade into its
            # word. Restore the proven word boundary, preserving later cues.
            if after.end_s > max(p.end_s for p in exiting)+.001:
                continue
            finish = after_source.end_s
        chosen = after if after is not None else before
        state = final_group[6][0][0].state
        clear_axes = any(k in chosen.state and k not in state for k in ('xbord','ybord'))
        tags = ''.join(render_tag(k,state[k]) for k in ('1c','1a','3c','3a','bord','xbord','ybord')
                       if k in state and (state[k] != chosen.state.get(k) or
                                          k == 'bord' and clear_axes))
        prefix = re.match(r'(?:\{[^}]*\})*',chosen.text).end()
        text = (chosen.text[:prefix-1]+tags+chosen.text[prefix-1:] if prefix else
                ('{'+tags+'}' if tags else '')+chosen.text)
        if inline_layout_key(chosen):
            # Match the readable contour used by reconstructed neighbors while
            # retaining the authored font switches inside the whole fragment.
            spans = literal_font_spans(chosen)
            state = {**effective_state(text,chosen.defaults,chosen.styles),'fn':spans[0][1]}
            text = aggressive_caption(state,chosen.text[prefix:])
        beginning = prefix_caption if prefix_caption is not None else before
        caption = replace_event(chosen,start=beginning.start,start_s=beginning.start_s,
                                end=format_time(finish),end_s=finish,text=text,
                                source_index=before.source_index)
        proposals.append((source_ids,caption))

    ownership = {}
    for ids,caption in proposals:
        for index in ids:
            ownership[index] = ownership.get(index,0)+1
    accepted = [(ids,caption) for ids,caption in proposals
                if all(ownership[index] == 1 for index in ids)]
    if not accepted:
        return events,0
    consumed = set().union(*(ids for ids,caption in accepted))
    output = [e for e in events if e.source_index not in consumed]
    output.extend(caption for ids,caption in accepted)
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output)


def normalize_karaoke_completion_paint(events: list[Event],
                                        visible_map: dict[int,str],
                                        source_events: dict[int,Event]) -> list[Event]:
    """Use the shared destination of a proven one-way syllable colour sweep.

    Every fragment must have one transition between the same two paints,
    covering the retained cue without reversals or competing copies. Ordered
    activation and a visible completed hold distinguish a karaoke sweep from
    independent colour changes. Static gradients and cyclic highlights retain
    the ordinary per-fragment dwell selection.
    """
    def identity(e: Event, word: str) -> tuple:
        layout = tuple((k,math.remainder(v,360)
                       if k in {'frz','frx','fry'} and math.isfinite(v) else v)
                       for k,v in text_layout_key(e))
        return (e.style,e.name,placement_key(e),layout,
                get_pos(e.text),word)

    def cue_start(e: Event) -> float:
        original = source_events.get(e.source_index)
        if (original is not None and original.duration > 0 and
                original.end_s < e.end_s and
                not unrotated_text_state(effective_state(original.text,original.defaults,original.styles))):
            # Exact-position phase reduction can absorb a rotating one-letter
            # entrance. Only the later upright phases belong to its sweep.
            return original.end_s
        return e.start_s

    def paint(state: dict) -> tuple:
        return (state.get('1c'),state.get('3c'),
                state.get('xbord',state.get('bord',0)),
                state.get('ybord',state.get('bord',0)))

    rows = {}
    for e in events:
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or not word or pos is None or inline_layout_key(e) or
                not upright_text_state(e.state) or e.state.get('1a',0) != 0 or
                any(k in e.state for k in ('clip','iclip','org'))):
            continue
        key = (cue_start(e),e.end,identity(e,'')[:4],pos[1])
        rows.setdefault(key,[]).append(e)

    candidates = []
    for row in rows.values():
        row.sort(key=lambda e:get_pos(e.text)[0])
        if (len(row) < 2 or len({get_pos(e.text)[0] for e in row}) != len(row) or
                any(get_pos(b.text)[0]-get_pos(a.text)[0] >
                    2*max(text_height(a),text_height(b)) +
                    text_height(a)*len(visible_map[a.source_index])
                    for a,b in zip(row,row[1:]))):
            continue
        candidates.append(row)
    if not candidates:
        return events

    # Only source phases of retained candidate glyphs can contribute to a
    # completion sweep. Most frame effects have no surviving matching anchor;
    # avoid reparsing their font and layout state just to discard them later.
    needed = {identity(e,visible_map[e.source_index]) for row in candidates for e in row}
    wanted = {}
    for key in needed:
        wanted.setdefault((key[0],key[1],key[-2]),set()).add(key[-1])
    sources = {}
    for original in source_events.values():
        if original.kind != 'Dialogue':
            continue
        pos = get_pos(original.text)
        words = wanted.get((original.style,original.name,pos))
        if words is None:
            continue
        word = simplify_text(original.text,visible_only=True)[1]
        if word not in words:
            continue
        state = effective_state(original.text,original.defaults,original.styles)
        e = dataclass_replace(original,state=state)
        key = identity(e,word)
        if key in needed:
            sources.setdefault(key,[]).append(e)

    replacements = {}
    for row in candidates:
        profiles = []
        for e in row:
            phases = sorted((p for p in sources.get(identity(e,visible_map[e.source_index]),[])
                             if p.start_s >= cue_start(e)-.001 and p.end_s <= e.end_s+.001),
                            key=lambda p:(p.start_s,p.end_s))
            if (not phases or abs(phases[0].start_s-cue_start(e)) > .011 or
                    abs(phases[-1].end_s-e.end_s) > .011 or
                    any(abs(a.end_s-b.start_s) > .011 for a,b in zip(phases,phases[1:]))):
                break
            transitions, holds = [], []
            valid = True
            for p in phases:
                state = p.state
                if (inline_layout_key(p) or state.get('1a',0) != 0 or
                        state.get('3a',0) != 0 or not unrotated_text_state(state) or
                        state.get('p',0) or any(k in state for k in ('clip','iclip','org'))):
                    valid = False; break
                tokens = event_override_tokens(p)
                transforms = [(tag,value) for tag,value in tokens if tag == 't']
                if not transforms:
                    holds.append((paint(state),p.start_s,p.end_s)); continue
                if len(transforms) != 1:
                    valid = False; break
                transform = parse_effect_transform(transforms[0][1],p.duration,
                    {'c','1c','3c','bord','xbord','ybord','blur','be'})
                if transform is None:
                    valid = False; break
                begin,end,changes = transform
                final = state.copy()
                for tag,value in changes:
                    apply_tag(final,tag,value,p.styles,p.defaults)
                if final.get('1c') == state.get('1c'):
                    valid = False; break
                transitions.append((paint(state),paint(final),p.start_s+begin/1000,
                                    p.start_s+end/1000,final))
            if not valid or len(transitions) != 1:
                break
            before,after,begin,end,final = transitions[0]
            if any(not (value == before and finish <= begin+.011 or
                        value == after and start >= end-.051)
                   for value,start,finish in holds):
                break
            completed = any(value == after and finish-start >= .02
                            for value,start,finish in holds)
            profiles.append((before,after,begin,end,final,completed))
        if len(profiles) != len(row):
            continue
        begins = [p[2] for p in profiles]
        ends = [p[3] for p in profiles]
        ordered = lambda values: (all(a <= b for a,b in zip(values,values[1:])) or
                                  all(a >= b for a,b in zip(values,values[1:])))
        if (len({(p[0],p[1]) for p in profiles}) != 1 or len(set(begins)) < 2 or
                not ordered(begins) or not ordered(ends) or
                not any(p[5] for p in profiles)):
            continue
        final = profiles[0][4]
        tags = ''.join(render_tag(k,final[k]) for k in ('1c','3c','bord','xbord','ybord')
                       if k in final)
        for e in row:
            index = e.text.find('}') if e.text.startswith('{') else -1
            text = (e.text[:index]+tags+e.text[index:] if index >= 0 else
                    '{'+tags+'}'+e.text)
            replacements[e.source_index] = replace_event(e,text=text)
    return [replacements.get(e.source_index,e) for e in events]


def collapse_progressive_text_reveals(events: list[Event],
                                      visible_map: dict[int,str]) -> tuple[list[Event],int]:
    """Freeze a proved prefix reveal at its complete foreground caption.

    Literal-span state distinguishes a visible prefix from its hidden suffix;
    the event's final state may describe only that suffix. Require increasing
    prefixes, a final unclipped visible copy, and matching text geometry. Thin
    clipped glitch strips must cover their complete band at every boundary.
    Preserve actual gaps and reject resets, changing layout and partial tiles.
    """
    paint = {'alpha','1a','2a','3a','4a','c','1c','2c','3c','4c',
             'bord','xbord','ybord','shad','xshad','yshad','blur','be'}
    reveal_families = {(e.style,visible_map.get(e.source_index,'')) for e in events
                       if e.kind == 'Dialogue' and inline_layout_key(e) and
                       re.search(r'\\(?:alpha|[134]a)(?=[^A-Za-z]|$)',e.text,re.I)}
    if not reveal_families:
        return events,0
    families = {}
    for e in events:
        if (e.kind != 'Dialogue' or not visible_map.get(e.source_index) or
                (e.style,visible_map[e.source_index]) not in reveal_families or
                get_pos(e.text) is None or any(t in e.text for t in (r'\N',r'\n',r'\h'))):
            continue
        obj = static_object_key(e,e.styles)
        if obj is None:
            continue
        literal, prefix, hidden, layout, foreground, valid = '', '', False, None, None, True
        for signature,drawing,payload in obj[-1]:
            state = dict(signature)
            if 'clip' in state:
                if state['clip'] != geometry_key(e.state.get('clip','')):
                    valid = False; break
                state['clip'] = e.state['clip']
            sample = dataclass_replace(e,state=state)
            geometry = state_key(sample,paint | {'pos','clip','iclip'})
            if (drawing or not unrotated_text_state(state) or
                    any(k in state for k in ('iclip','org')) or
                    layout is not None and geometry != layout or
                    state.get('pos') != get_pos(e.text)):
                valid = False; break
            layout = geometry
            literal += payload
            invisible = all(state.get(k,0) == 255 for k in ('1a','3a','4a'))
            if invisible:
                hidden = True
            elif hidden or state.get('1a',0) >= 128:
                valid = False; break
            else:
                if foreground is not None and state_key(sample,{'clip'}) != state_key(
                        dataclass_replace(e,state=foreground),{'clip'}):
                    valid = False; break
                foreground = state
                prefix += payload
        if not valid or not prefix or literal != visible_map[e.source_index]:
            continue
        sample = dataclass_replace(e,state=foreground)
        rect = rectangle_clip(sample) if 'clip' in foreground else None
        if ('clip' in foreground and rect is None or
                any(not math.isfinite(v) for v in get_pos(e.text)) or
                any(not math.isfinite(foreground.get(k,0)) or foreground.get(k,0) <= 0
                    for k in ('fs','fscx','fscy'))):
            continue
        key = (e.style,e.layer,e.margin_l,e.margin_r,e.margin_v,literal,layout)
        families.setdefault(key,[]).append((e,prefix,foreground,rect))

    removed, replacements = set(), {}
    for key,family in families.items():
        # Separate distant signs and repeated captions. Candidate chains may
        # have small authored gaps, but replacements retain every such gap.
        chains = []
        for item in sorted(family,key=lambda p:(p[0].start_s,len(p[1]),p[0].source_index)):
            e,prefix,state,rect = item
            pos = get_pos(e.text)
            found = None
            for chain in reversed(chains):
                anchor = chain[0][0]
                height = min(text_height(anchor),text_height(e))
                start = chain[-1][0].start_s
                if (e.start_s <= max(p[0].end_s for p in chain)+.08+1e-6 and
                        abs(pos[0]-get_pos(anchor.text)[0]) <= .18*height and
                        abs(pos[1]-get_pos(anchor.text)[1]) <= .01*height and
                        (e.start_s == start or len(prefix) >= max(len(p[1]) for p in chain))):
                    found = chain; break
            if found is None:
                chains.append([item])
            else:
                found.append(item)
        for chain in chains:
            literal = key[-2]
            partials = {prefix for e,prefix,state,rect in chain if prefix != literal}
            holds = [(e,state) for e,prefix,state,rect in chain if
                     prefix == literal and rect is None and state.get('1a',0) < 128]
            if len(partials) < 2 or not holds:
                continue
            # A complete copy must finish the reveal, rather than be an
            # unrelated simultaneous label behind a retracting prefix.
            last_partial = max(e.start_s for e,prefix,state,rect in chain if prefix != literal)
            holds = [(e,state) for e,state in holds if e.start_s >= last_partial]
            if not holds:
                continue
            tiles = {}
            for e,prefix,state,rect in chain:
                if rect is not None:
                    tiles.setdefault((prefix,state_key(
                        dataclass_replace(e,state=state),{'pos','clip'})),[]).append((e,rect))
            complete = True
            for peers in tiles.values():
                rectangles = sorted(set(rect for e,rect in peers),key=lambda r:r[1])
                height = min(text_height(e) for e,rect in peers)
                # The union supplies the band's extent. A temporal hole in
                # any strip must not disappear merely because its neighbors
                # were coalesced across different start/end boundaries.
                if (len(rectangles) < 3 or
                        len({(r[0],r[2]) for r in rectangles}) != 1 or
                        any(r[3]-r[1] > .08*height for r in rectangles)):
                    complete = False; break
                top,bottom = rectangles[0][1],max(r[3] for r in rectangles)
                changes = {}
                for e,rect in peers:
                    changes.setdefault(e.start_s,[]).append((rect,1))
                    changes.setdefault(e.end_s,[]).append((rect,-1))
                active = {}
                for time,updates in sorted(changes.items()):
                    # Aggregate simultaneous ends/starts before checking the
                    # next half-open interval; a touching tile has no gap.
                    for rect,delta in updates:
                        active[rect] = active.get(rect,0)+delta
                        if not active[rect]:
                            del active[rect]
                    if not active:
                        continue
                    band = sorted(active,key=lambda r:r[1])
                    if (len(band) < 3 or bottom-top < .3*height or
                            abs(band[0][1]-top) > .001 or
                            abs(band[-1][3]-bottom) > .001 or
                            any(abs(a[3]-b[1]) > .001 for a,b in zip(band,band[1:]))):
                        complete = False; break
                if not complete:
                    break
            if not complete:
                continue
            chosen,state = max(holds,key=lambda p:(-p[1].get('1a',0),
                                                   p[0].duration,-p[0].source_index))
            body = aggressive_caption(state,literal,outline_states=[p[2] for p in chain])
            if state.get('1a',0):
                # The shared caption renderer normalizes opacity for effects.
                # This proof also accepts an already simplified translucent
                # foreground: keep its actual fill transparency.
                end_header = body.index('}')
                body = body[:end_header]+render_tag('1a',state['1a'])+body[end_header:]
            intervals = []
            for e,_,_,_ in sorted(chain,key=lambda p:(p[0].start_s,p[0].end_s)):
                if intervals and e.start_s <= intervals[-1][1]+1e-6:
                    intervals[-1][1] = max(intervals[-1][1],e.end_s)
                else:
                    intervals.append([e.start_s,e.end_s])
            for start,end in intervals:
                members = [e for e,_,_,_ in chain if e.start_s < end and e.end_s > start]
                index = min(e.source_index for e in members)
                replacements[index] = replace_event(chosen,start=format_time(start),start_s=start,
                    end=format_time(end),end_s=end,text=body,source_index=index,effect='')
                visible_map[index] = literal
                removed.update(e.source_index for e in members)
    output = [replacements.get(e.source_index,e) for e in events
              if e.source_index not in removed or e.source_index in replacements]
    return output,len(events)-len(output)


def flatten_aggressive_text_sequences(events: list[Event],
                                      visible_map: dict[int,str],
                                      styles: dict, animated_sources: set[int] | None = None,
                                      _scale_trails: bool = True, *,
                                      source_events: dict[int,Event] | None = None,
                                      font_spacing: FontSpacing | None = None) -> tuple[list[Event],int]:
    """Freeze connected full-text styling phases as one static caption.

    For unmasked text keep representative geometry and sustained colours;
    for clipped effects retain a plain readable caption. Gaps split runs.
    """
    animated_sources = animated_sources or set()
    original_removed=0
    if _scale_trails:
        # Finish the established exact-position/clipped sequence reduction
        # first. Unproven wider candidates then retain that result verbatim.
        events,original_removed=flatten_aggressive_text_sequences(
            events,visible_map,styles,animated_sources,False,source_events=source_events)
    buckets, output = {}, []
    for e in events:
        visible=visible_map.get(e.source_index,"")
        if e.kind!="Dialogue" or not visible or get_pos(e.text) is None or e.state.get("p",0):
            output.append(e)
            continue
        key=(e.style,visible)
        if source_events is not None and len(visible) == 1:
            original = source_events.get(e.source_index)
            # A frozen flying letter can land near a different stationary
            # letter. It is not a styling phase of that neighbour's caption.
            key += (bool(original and re.search(r"\\move\s*\(",original.text,re.I)),)
        if _scale_trails:
            key+=(e.name,tuple((k,v) for k,v in text_layout_key(e)
                              if k not in {"fscx","fscy","frz"}),placement_key(e))
        buckets.setdefault(key,[]).append(e)
    removed=original_removed
    for key,bucket in buckets.items():
        style,visible=key[:2]
        # Cache the geometry used while clustering. Scale trails change their
        # position and scale together, but not the font or paragraph layout.
        positions = {e.source_index: get_pos(e.text) for e in bucket}
        heights = {e.source_index: text_height(e) for e in bucket}
        layouts = {e.source_index: (tuple((k,v) for k,v in text_layout_key(e)
                                         if k not in {"fscx","fscy","frz"}), placement_key(e))
                   for e in bucket}
        components=[]
        anchors={}
        for e in sorted(bucket,key=lambda x:(x.start_s,x.end_s,x.source_index)):
            pos=get_pos(e.text)
            found=None
            for component in reversed(components):
                previous=component[-1]
                span_start = min(x.start_s for x in component)
                span_end = max(x.end_s for x in component)
                if e.start_s > span_end+1e-6:
                    continue
                # Brief fade overlaps between consecutive captions must not
                # link their repeated letters into one long styling sequence.
                # Nested highlight phases remain eligible; genuinely touching
                # phases still share the exact centisecond boundary.
                overlap = min(e.end_s,span_end)-max(e.start_s,span_start)
                if (e.start_s > span_start and e.end_s > span_end and
                        1e-6 < overlap < .8*min(e.duration,span_end-span_start)):
                    continue
                anchor=positions[previous.source_index]
                allowance=.18*min(heights[e.source_index],heights[previous.source_index])
                reference=anchors[id(component)]
                # Only broaden candidates for animated, strongly overlapping
                # copies with the same non-scale layout. The affine trajectory
                # test below must still prove that these form one scale trail.
                if (_scale_trails and not any(k in e.state or k in reference.state
                                                for k in ("clip","iclip")) and
                        (e.source_index in animated_sources or
                        pos==positions[reference.source_index]) and
                        layouts[e.source_index]==layouts[reference.source_index] and
                        e.name==reference.name and
                        min(e.end_s,reference.end_s)-max(e.start_s,reference.start_s)
                            >= .8*min(e.duration,reference.duration)):
                    anchor=positions[reference.source_index]
                    allowance=heights[reference.source_index]
                if (abs(pos[0]-anchor[0])<=allowance and
                    abs(pos[1]-anchor[1])<=allowance and
                    e.margin_l==previous.margin_l and
                    e.margin_r==previous.margin_r and
                    e.margin_v==previous.margin_v):
                    found=component;break
            if found is None:
                component=[e]
                components.append(component)
                anchors[id(component)]=e
            else:
                found.append(e)
                if heights[e.source_index]>heights[anchors[id(found)].source_index]:
                    anchors[id(found)]=e
        for component in components:
            if len(component)<2:
                output.extend(component);continue
            clipped=any("clip" in e.state or "iclip" in e.state for e in component)
            drifting=len({positions[e.source_index] for e in component})>1
            members = (match_scale_trail(component,visible,animated_sources,positions,heights,layouts)
                       if _scale_trails and not clipped and drifting else None)
            trail = members is not None
            if _scale_trails and not trail:
                output.extend(component)
                continue
            if trail:
                member_ids={e.source_index for e in members}
                output.extend(e for e in component if e.source_index not in member_ids)
                component=members
            if not clipped and (len({e.name for e in component}) != 1 or
                    drifting and not trail or
                    (len({state_key(e) for e in component}) < 2 and
                     not (all(e.source_index in (animated_sources or set()) for e in component) and
                          len({e.text for e in component}) == 1 and
                          len({e.layer for e in component}) == 1 and
                          all(a.end == b.start for a,b in zip(component,component[1:]))))):
                output.extend(component);continue
            visible_candidates=[e for e in component if e.state.get("1a",255)<255]
            if not visible_candidates:
                output.extend(component);continue
            start=min(e.start_s for e in component)
            end=max(e.end_s for e in component)
            if not clipped:
                midpoint=(start+end)/2
                if trail:
                    # Keep the most visible full-sized sample, not a tiny tail
                    # or an arbitrary frame nearer the temporal midpoint.
                    chosen=max(visible_candidates,key=lambda e:(
                        -e.state.get("1a",255), heights[e.source_index],
                        int(e.layer) if e.layer.lstrip("-").isdigit() else 0))
                else:
                    rank = lambda e: (e.start_s <= midpoint < e.end_s,
                                      -max(e.start_s-midpoint,midpoint-e.end_s,0),
                                      -e.state.get("1a",255),
                                      int(e.layer) if e.layer.lstrip("-").isdigit() else 0)
                    chosen=max(visible_candidates,key=rank)
                    if (source_events is not None and
                            any(e.source_index in animated_sources for e in component) and
                            not unrotated_text_state(chosen.state)):
                        # Prefer a real readable hold over a longer rotated
                        # entrance. Paint dwell and full cue timing stay shared.
                        holds = upright_text_holds(visible_candidates,source_events)
                        if holds:
                            chosen=max(holds,key=rank)
                state = select_static_state(chosen.state,[],set(),styles,chosen.defaults,
                                            paint_events=visible_candidates)
                # Preserve the chosen object's geometry and inline text. The
                # shared selector changes only colours when given event paint.
                color_tags = ''.join(render_tag(k,state[k]) for k in ('1c','3c','4c')
                                     if state.get(k) != chosen.state.get(k) and k in state)
                if trail:
                    text = aggressive_caption(state,OVERRIDE_RE.sub("",chosen.text),
                                              outline_states=[e.state for e in component])
                elif color_tags and chosen.text.startswith('{'):
                    index = chosen.text.index('}')
                    text = chosen.text[:index]+color_tags+chosen.text[index:]
                else:
                    text = ('{'+color_tags+'}' if color_tags else '')+chosen.text
                output.append(replace_event(chosen,start=format_time(start),end=format_time(end),
                                      start_s=start,end_s=end,text=text,
                                      source_index=min(e.source_index for e in component)))
                removed+=len(component)-1
                continue
            chosen=max(visible_candidates,key=lambda e:(
                e.state.get("1a",255)==0,
                "clip" not in e.state and "iclip" not in e.state,
                e.duration,int(e.layer) if e.layer.lstrip("-").isdigit() else 0))
            state = select_static_state(chosen.state,[],set(),styles,chosen.defaults,
                                        paint_events=visible_candidates)
            text = aggressive_caption(state, OVERRIDE_RE.sub("", chosen.text),
                                      outline_states=[e.state for e in component])
            output.append(replace_event(chosen,start=format_time(start),end=format_time(end),
                                  start_s=start,end_s=end,text=text,layer="0",effect="",
                                  source_index=min(e.source_index for e in component)))
            removed+=len(component)-1
    if _scale_trails and source_events is not None:
        output,phase_removed = collapse_moving_glyph_sequences(
            output,visible_map,source_events,font_spacing)
        removed += phase_removed
        output = normalize_karaoke_completion_paint(output,visible_map,source_events)
    if _scale_trails:
        # Unmasking/normalizing a caption can reveal an ordinary same-anchor
        # styling phase that was separate while it still had clips or scales.
        # Consolidate those results once with the existing phase rules and
        # original move/hold evidence; do not repeat the animation pipeline.
        output,phase_removed = flatten_aggressive_text_sequences(
            output,visible_map,styles,animated_sources,False,source_events=source_events)
        removed += phase_removed
    return sorted(output,key=lambda e:e.source_index),removed


def match_authored_lyric_rows(events: list[Event], visible_map: dict[int, str],
                              source_events: dict[int, Event]) -> tuple[set[int], list[TextRow]]:
    """Prove complete captions from matching entrance and exit letter rows.

    Return removable source indices and row evidence for the existing covered-
    fragment pass. Original move endpoints prove placement; caption text and
    timing remain unchanged, and ambiguous or incomplete matches stay intact.
    """
    removed: set[int] = set()
    row_evidence: list[TextRow] = []
    norm = lambda value: "".join(value.split()).casefold()
    moving: dict[tuple,list[tuple[Event,Event,list[float]]]] = {}
    captions: dict[tuple,list[tuple[Event,Event]]] = {}
    families = {(e.style,e.name) for e in events
                if visible_map.get(e.source_index,"") and
                (source := source_events.get(e.source_index)) is not None and
                re.search(r"\\move\s*\(",source.text,re.I)}
    for e in events:
        source = source_events.get(e.source_index)
        words = visible_map.get(e.source_index, "")
        if ((e.style,e.name) not in families or source is None or
                e.kind != "Dialogue" or not words or
                source.duration <= 0 or inline_layout_key(e)):
            continue
        is_move = bool(re.search(r"\\move\s*\(",source.text,re.I))
        if not is_move and len(words) < 8:
            continue
        if not is_move and re.search(r"\\(?:t|fad(?:e)?)\s*\(",source.text,re.I):
            continue
        state = source.state or effective_state(source.text,source.defaults,source.styles)
        source.state = state
        if (state.get("p",0) or state.get("1a",0) != 0 or
                any(k in state for k in ("clip","iclip","org")) or
                any(abs(state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        key = (e.style,e.name,placement_key(source)[0],
               tuple((k,v) for k,v in text_layout_key(source) if k != "an"))
        if is_move:
            tokens = [token for block in OVERRIDE_RE.findall(source.text)
                      for token in tokenize_override(block)]
            moves = [value for tag,value in tokens if tag == "move"]
            if (len(moves) != 1 or state.get("an") != 5 or
                    any(tag == "t" for tag,value in tokens)):
                continue
            try:
                values = [float(v) for v in moves[0].strip("()").split(",")]
            except ValueError:
                continue
            if len(values) not in (4,6) or not all(math.isfinite(v) for v in values):
                continue
            if len(values) == 6 and not 0 <= values[4] < values[5] <= 1000*source.duration+.001:
                continue
            moving.setdefault((key,source.start,source.end,source.layer),[]).append((e,source,values))
        elif get_pos(e.text) is None:
            captions.setdefault(key,[]).append((e,source))
    rows: dict[tuple,list[list[tuple[Event,Event,list[float]]]]] = {}
    for (key,start,end,layer),pieces in moving.items():
        if len(pieces) >= 8:
            rows.setdefault((key,"in",end),[]).append(pieces)
            rows.setdefault((key,"out",start),[]).append(pieces)
    for key,full_lines in captions.items():
        colliding = set()
        latest = None
        for full,source in sorted(full_lines,key=lambda pair:pair[0].start_s):
            if latest is not None and full.start_s < latest.end_s:
                colliding.update((full.source_index,latest.source_index))
            if latest is None or full.end_s > latest.end_s:
                latest = full
        for full,source in full_lines:
            # Style-based placement may move under ASS collision handling.
            # Overlapping unpositioned captions cannot prove this baseline.
            if full.source_index in colliding:
                continue
            height = text_height(source)
            alignment = int(source.state.get("an",2))
            if alignment not in range(1,10) or height <= 0:
                continue
            width,canvas_height = source.state.get("_canvas",(0,0))
            left,right,vertical = placement_key(source)[0]
            expected_y = (canvas_height-vertical-height/2 if alignment <= 3 else
                          canvas_height/2 if alignment <= 6 else vertical+height/2)
            matched = {"in":[],"out":[]}
            adjacent = [(phase,pieces) for phase,boundary in
                        (("in",source.start),("out",source.end))
                        for pieces in rows.get((key,phase,boundary),[])]
            for phase,pieces in adjacent:
                first = pieces[0][1]
                if first.layer != source.layer:
                    continue
                offset = 2 if phase == "in" else 0
                ordered = sorted(pieces,key=lambda piece:piece[2][offset])
                positions = [tuple(values[offset:offset+2]) for e,original,values in ordered]
                xs,ys = [p[0] for p in positions],[p[1] for p in positions]
                if (norm("".join(visible_map[e.source_index] for e,original,values in ordered)) !=
                        norm(visible_map[full.source_index]) or
                        any(b-a <= full.unit for a,b in zip(xs,xs[1:])) or
                        max(ys)-min(ys) > .06*height or
                        abs(statistics.median(ys)-expected_y) > .06*height):
                    continue
                horizontal = (alignment-1)%3
                if (horizontal == 0 and not left <= xs[0] <= left+height or
                        horizontal == 2 and not width-right-height <= xs[-1] <= width-right or
                        horizontal == 1 and abs((xs[0]+xs[-1])/2-width/2) > height/2):
                    continue
                matched[phase].append((ordered,positions))
            if len(matched["in"]) != 1 or len(matched["out"]) != 1:
                continue
            entrance,positions = matched["in"][0]
            exit_row,exit_positions = matched["out"][0]
            if (any(visible_map[a[0].source_index] != visible_map[b[0].source_index]
                    for a,b in zip(entrance,exit_row)) or len(entrance) != len(exit_row) or
                    any(math.dist(a,b) > full.unit for a,b in zip(positions,exit_positions))):
                continue
            # Feed the established covered-fragment pass a real row model.
            # It owns nested syllable removal and its font/actor/layer guards.
            # The model's centered placement does not alter the caption.
            pieces = [(replace_event(original,text=aggressive_caption(
                original.state,visible_map[e.source_index],an=5,pos=pos)),
                visible_map[e.source_index],pos)
                for (e,original,values),pos in zip(entrance,positions)]
            center = ((positions[0][0]+positions[-1][0])/2,statistics.median(p[1] for p in positions))
            base = replace_event(full,text=aggressive_caption(full.state,visible_map[full.source_index],
                                                              an=5,pos=center))
            row_evidence.append(TextRow(base,pieces))
            removed.update(e.source_index for row in (entrance,exit_row) for e,original,values in row)
    return removed,row_evidence


def match_nested_glyph_copies(events: list[Event], visible_map: dict[int,str],
                              metric: FontSpacing | None) -> set[int]:
    """Prove complete letter copies inside equally painted word fragments.

    Require near-coextensive nested timing and exact-font glyph spacing and
    anchors, rather than a shared word center alone. Every letter in a phase
    must have one owner; missing, extra or multiply owned letters keep that
    whole phase. Parent-only fragments are retained, including lone letters.
    """
    if metric is None or not metric.available:
        return set()
    groups = {}
    for e in events:
        word = visible_map.get(e.source_index,"")
        pos = get_pos(e.text)
        if (e.kind != "Dialogue" or not word or pos is None or e.effect or
                e.duration <= 0 or not e.layer.lstrip('-').isdigit() or
                e.state.get('1a',0) != 0 or e.state.get('p',0) or
                e.state.get('borderstyle',1) != 1 or inline_layout_key(e) or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay','fsp')) or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word) or
                OVERRIDE_RE.sub('',e.text) != word or
                any(not math.isfinite(v) for v in (*pos,e.start_s,e.end_s)) or
                static_object_key(e,e.styles) is None):
            continue
        key = (e.style,e.name,e.row,placement_key(e),state_key(e,{'pos'}))
        groups.setdefault(key,{}).setdefault((e.start,e.end,e.layer),[]).append(e)

    proposals = []
    for phases in groups.values():
        by_start = {}
        for (start,end,layer),group in phases.items():
            by_start.setdefault((start,layer),[]).extend(group)
        parents = [group for group in by_start.values()
                   if sum(len(visible_map[e.source_index]) > 1 for e in group) >= 4]
        children = sorted((group for group in phases.values()
                           if len(group) >= 8 and all(len(visible_map[e.source_index]) == 1
                                                    for e in group)),key=lambda g:g[0].start_s)
        starts = [group[0].start_s for group in children]
        for parent_group in parents:
            # Earlier phase merging can extend one held fragment beyond its
            # neighbors. It remains valid backing throughout the shorter cue;
            # keep that lifetime and use the common end only for phase lookup.
            parent = min(parent_group,key=lambda e:e.end_s)
            if len({get_pos(e.text) for e in parent_group}) != len(parent_group):
                continue
            for child_group in children[bisect_left(starts,parent.start_s-1e-6):
                                        bisect_right(starts,parent.start_s+.25+1e-6)]:
                child = child_group[0]
                if (child.end_s > parent.end_s+1e-6 or
                        parent.end_s-child.end_s > .25+1e-6 or
                        child.duration < .8*parent.duration or
                        child.start == parent.start and child.end == parent.end):
                    continue
                ordered = sorted(child_group,key=lambda e:get_pos(e.text)[0])
                xs = [get_pos(e.text)[0] for e in ordered]
                if any(b-a <= child.unit for a,b in zip(xs,xs[1:])):
                    continue
                letters = [visible_map[e.source_index] for e in ordered]
                owners = [0]*len(ordered)
                matched = 0
                for p in parent_group:
                    word = visible_map[p.source_index]
                    px,py = get_pos(p.text)
                    options = []
                    for index in range(len(ordered)-len(word)+1):
                        stop = index+len(word)
                        if (''.join(letters[index:stop]) != word or
                                any(abs(get_pos(e.text)[1]-py) > .25*p.unit
                                    for e in ordered[index:stop])):
                            continue
                        anchor = metric.fragment_anchor(p.state,xs[index:stop],letters[index:stop],
                                                        word,p.unit,separate_glyphs=True,exact_size=True)
                        if anchor is not None and abs(anchor-px) <= .25*p.unit:
                            options.append((index,stop))
                    if len(options) > 1:
                        matched = -1; break
                    if options:
                        index,stop = options[0]
                        for i in range(index,stop):
                            owners[i] += 1
                        matched += len(word) > 1
                if matched >= 4 and all(owner == 1 for owner in owners):
                    proposals.append({e.source_index for e in child_group})
    ownership = {}
    for members in proposals:
        for index in members:
            ownership[index] = ownership.get(index,0)+1
    return {index for members in proposals if all(ownership[i] == 1 for i in members)
            for index in members}


def match_staggered_full_line_copies(events: list[Event], visible_map: dict[int,str],
                                     metric: FontSpacing | None) -> set[int]:
    """Match complete, near-coextensive glyph rows to retained full captions.

    Exact font advances and the authored spaces prove the whole row, including
    style-based caption placement. Actor labels may differ, but each letter
    row keeps its own label/layer and needs exactly one owner. Keep the full
    caption's formatting and timing; staggered copy lead-ins/tails are effects.
    """
    if metric is None or not metric.available:
        return set()
    captions, groups, unpositioned = [], {}, {}

    def geometry(e: Event) -> tuple:
        return (e.style,placement_key(e)[0],
                tuple((k,str(v).casefold() if k == 'fn' else v)
                      for k,v in text_layout_key(e) if k != 'an'),
                (int(e.state.get('an',2))-1)%3)

    for e in events:
        word = visible_map.get(e.source_index,'')
        if e.kind != 'Dialogue' or not word or e.duration <= 0:
            continue
        pos = get_pos(e.text)
        if pos is None and not e.state.get('p',0):
            collision_layer = int(e.layer) if e.layer.lstrip('+-').isdigit() else 0
            unpositioned.setdefault((collision_layer,(int(e.state.get('an',2))-1)//3),[]).append(e)
        if (not e.layer.lstrip('-').isdigit() or e.state.get('1a',0) != 0 or
                e.state.get('p',0) or e.state.get('borderstyle',1) != 1 or
                inline_layout_key(e) or not unrotated_text_state(e.state) or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay'))):
            continue
        if len(word) == 1 and not word.isspace() and pos is not None:
            key = (geometry(e),e.name,e.layer,e.row)
            groups.setdefault(key,[]).append(e)
        elif len(''.join(word.split())) >= 3:
            captions.append(e)
    if not captions or not groups:
        return set()

    # Default ASS placement can shift under collision handling. Only isolated
    # unpositioned captions prove a baseline, even across different styles.
    colliding = set()
    for peers in unpositioned.values():
        previous = None
        for e in sorted(peers,key=lambda item:item.start_s):
            if previous is not None and e.start_s < previous.end_s:
                colliding.update((previous.source_index,e.source_index))
            if previous is None or e.end_s > previous.end_s:
                previous = e
    indexes = {}
    for (key,name,layer,row),peers in groups.items():
        ordered = sorted(peers,key=lambda e:e.start_s)
        indexes.setdefault(key,[]).append((int(layer),[e.start_s for e in ordered],ordered))

    proposals = []
    for full in captions:
        key = geometry(full)
        families = indexes.get(key,[])
        if not families or full.source_index in colliding:
            continue
        pos = get_pos(full.text)
        canvas = full.state.get('_canvas')
        alignment = int(full.state.get('an',2))
        if alignment not in range(1,10) or static_object_key(
                full,full.styles,allow_unpositioned=True) is None:
            continue
        left,right,vertical = placement_key(full)[0]
        height = text_height(full)
        if pos is None:
            if canvas is None:
                continue
            width,canvas_height = canvas
            horizontal = (alignment-1)%3
            pos = (left if horizontal == 0 else width-right if horizontal == 2 else
                   (left+width-right)/2,
                   canvas_height-vertical if alignment <= 3 else
                   canvas_height/2 if alignment <= 6 else vertical)
        center_y = pos[1]+((alignment-1)//3-1)*height/2
        text = visible_map[full.source_index]
        # Stagger may grow with a long cue. Bound both endpoints and shared
        # visibility relative to that cue instead of assuming a fixed delay.
        allowance = .2*full.duration
        for layer,starts,peers in families:
            if layer > int(full.layer):
                continue
            candidates = peers[bisect_left(starts,full.start_s-allowance-1e-6):
                               bisect_right(starts,full.start_s+allowance+1e-6)]
            candidates = [e for e in candidates
                if abs(e.end_s-full.end_s) <= allowance+1e-6 and
                   min(e.end_s,full.end_s)-max(e.start_s,full.start_s) >=
                        .8*max(e.duration,full.duration)-1e-6 and
                   e.state.get('1c') == full.state.get('1c') and
                   abs(get_pos(e.text)[1]+((int(e.state.get('an',5))-1)//3-1)*
                       text_height(e)/2-center_y) <= full.unit]
            candidates.sort(key=lambda e:get_pos(e.text)[0])
            if (len(candidates) != len(''.join(text.split())) or
                    ''.join(visible_map[e.source_index] for e in candidates) != ''.join(text.split()) or
                    len({get_pos(e.text)[0] for e in candidates}) != len(candidates) or
                    not metric.matches_authored_glyph_positions(
                        full.state,[get_pos(e.text)[0] for e in candidates],text,pos[0],full.unit)):
                continue
            # A caption that wraps is not the single row the letters prove.
            # Explicit no-wrap formatting can intentionally span the canvas.
            if full.state.get('q') != 2:
                if canvas is None:
                    continue
                face = metric.matching_face(str(full.state.get('fn','')),
                    bool(full.state.get('b',0)),bool(full.state.get('i',0)))
                try:
                    span = (metric.measure(face,text,bool(full.state.get('kerning',False)))*
                            metric.ass_em_scale(face)*full.state.get('fs',20)*
                            full.state.get('fscx',100)/100/1024+
                            full.state.get('fsp',0)*full.state.get('fscx',100)/100*(len(text)-1))
                except (OSError,ValueError,RuntimeError,TypeError):
                    continue
                if span > canvas[0]-left-right+full.unit:
                    continue
            if any(static_object_key(e,e.styles) is None for e in candidates):
                continue
            proposals.append({e.source_index for e in candidates})
    owners = {}
    for members in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    return {index for members in proposals if all(owners[i] == 1 for i in members)
            for index in members}


def remove_letters_over_full_lines(events: list[Event],
                                   visible_map: dict[int, str],
                                   source_events: dict[int, Event] | None = None,
                                   row_evidence: list[TextRow] | None = None, *,
                                   font_spacing: FontSpacing | None = None) -> tuple[list[Event], int]:
    """Use retained full lines or word fragments over proven letter copies.

    Match complete text and placement, using either equal timing or paired
    entrance/exit rows. Near-coextensive full-line and word-fragment copies
    additionally require exact-font glyph positions. Nearby letters alone never prove
    caption ownership. Complete shadow backings can supply authored text and
    its anchor, while matching opaque fragments supply foreground paint.
    """
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind == "Dialogue" and get_pos(e.text) is not None and visible_map.get(e.source_index):
            groups.setdefault((e.style,e.name,e.start,e.end,e.row,
                               e.margin_l,e.margin_r,e.margin_v),[]).append(e)
    removed = match_nested_glyph_copies(events,visible_map,font_spacing)
    removed.update(match_staggered_full_line_copies(events,visible_map,font_spacing))
    replacements: dict[int,Event] = {}
    norm = lambda value: "".join(value.split()).casefold()
    if source_events is not None and row_evidence is not None:
        authored_removed,authored_rows = match_authored_lyric_rows(events,visible_map,source_events)
        removed.update(authored_removed)
        row_evidence.extend(authored_rows)
    for group in groups.values():
        full_lines = [e for e in group if len(visible_map[e.source_index]) >= 8
                      and len(visible_map[e.source_index].split()) >= 2]
        for full in full_lines:
            if full.source_index in removed:
                continue
            shadow_only = (full.state.get('1a',0) >= 254 and
                           full.state.get('3a',0) >= 254 and
                           full.state.get('4a',0) < 254 and
                           full.state.get('borderstyle',1) == 1 and
                           not full.state.get('p',0) and
                           not inline_layout_key(full) and
                           not any(k in full.state for k in ('clip','iclip','org')) and
                           unrotated_text_state(full.state) and
                           any(abs(full.state.get(k,full.state.get('shad',0))) > 0
                               for k in ('xshad','yshad')))
            full_length = len(norm(visible_map[full.source_index]))
            fx = [e for e in group if e is not full and e.source_index not in removed
                  and 0 < len(norm(visible_map[e.source_index])) < full_length
                  # Longer word/syllable copies need matching font geometry
                  # and placement as well as the complete-row text proof below.
                  and (len(visible_map[e.source_index]) <= 4 or
                       (text_layout_key(e) == text_layout_key(full) and
                        placement_key(e) == placement_key(full) and
                        not e.state.get('p',0) and not inline_layout_key(e) and
                        not any(k in e.state for k in ('clip','iclip','org')) and
                        unrotated_text_state(e.state)))
                  and abs(get_pos(e.text)[1]-get_pos(full.text)[1]) <= .1*text_height(full)]
            if shadow_only:
                # A complete shadow backing supplies authored text and its
                # exact caption anchor. Four opaque, equally timed fragments
                # with identical font/layout can prove its foreground without
                # requiring duplicate effect layers for every syllable.
                fx = [e for e in fx if e.state.get('1a',0) == 0 and
                      text_layout_key(e) == text_layout_key(full) and
                      placement_key(e) == placement_key(full)]
            if len(fx) < (4 if shadow_only else 8):
                continue
            columns: list[list[Event]] = []
            for e in sorted(fx,key=lambda e:get_pos(e.text)[0]):
                if columns and abs(get_pos(e.text)[0]-get_pos(columns[-1][0].text)[0]) <= .06*text_height(full):
                    columns[-1].append(e)
                else:
                    columns.append([e])
            if len(columns) < 4 or any(len({visible_map[e.source_index] for e in col}) != 1
                                       for col in columns):
                continue
            assembled = "".join(visible_map[col[0].source_index] for col in columns)
            matches = (''.join(assembled.split()) == ''.join(visible_map[full.source_index].split())
                       if shadow_only else norm(assembled) == norm(visible_map[full.source_index]))
            if not matches:
                continue
            xs = [get_pos(col[0].text)[0] for col in columns]
            if not min(xs) <= get_pos(full.text)[0] <= max(xs):
                continue
            # The author's complete, spaced text is the canonical caption.
            # Level 1 gives it one opaque fill and contour instead of retaining
            # translucent backing paint plus dozens of animated letters.
            ordered = [max(col,key=lambda e:(int(e.layer) if e.layer.lstrip('-').isdigit() else 0,
                                             e.source_index)) for col in columns]
            prefix_end = re.match(r'(?:\{[^}]*\})*',full.text).end()
            tracking_tokens = [token for block in OVERRIDE_RE.findall(full.text[prefix_end:])
                               for token in tokenize_override(block)]
            tracking_only = (bool(tracking_tokens) and
                all(k == 'fsp' and re.fullmatch(NUM,v) and math.isfinite(float(v))
                    for k,v in tracking_tokens) and
                len({tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
                    ('1c','3c','b','i','u','s')) for e in ordered}) == 1)
            def paint_layout(e):
                return tuple((k,v) for k,v in text_layout_key(e)
                             if not tracking_only or k != 'fsp')
            # A nearly invisible full-line scaffold can carry the literal text
            # while its already-matched opaque letters carry the actual paint.
            # Reuse those colours only after the existing ownership proof, with
            # identical literal characters and font/layout/placement evidence.
            fragment_paint = shadow_only or (
                full.state.get('1a',0) >= 254 and full.state.get('3a',0) >= 254 and
                (not inline_layout_key(full) or tracking_only) and
                not any(k in full.state for k in ('clip','iclip','org')) and
                unrotated_text_state(full.state) and
                ''.join(assembled.split()) == ''.join(visible_map[full.source_index].split()) and
                all(e.state.get('1a',0) == 0 and
                    paint_layout(e) == paint_layout(full) and
                    (placement_key(e)[:3] == placement_key(full)[:3] if tracking_only else
                     placement_key(e) == placement_key(full)) and
                    not inline_layout_key(e) and
                    not any(k in e.state for k in ('clip','iclip','org')) for e in ordered))
            if fragment_paint:
                body = render_merged_caption(ordered,
                    [visible_map[e.source_index] for e in ordered],visible_map[full.source_index],
                    animated=True,an=int(full.state.get('an',5)),pos=get_pos(full.text),
                    fscx=full.state.get('fscx',100),fscy=full.state.get('fscy',100))
                if body is None:
                    continue
                if tracking_only:
                    # Authored spacing remains authoritative. Uniform proved
                    # foreground paint can replace the scaffold header while
                    # retaining its literal text and tracking spans exactly.
                    body = body[:body.index('}')+1]+full.text[prefix_end:]
                if 'q' in full.state:
                    body = '{'+render_tag('q',full.state['q'])+'}'+body
            else:
                body = aggressive_caption(full.state,visible_map[full.source_index])
            replacements[full.source_index] = replace_event(
                full, text=body,
                layer="0", effect="")
            if row_evidence is not None:
                row_evidence.append(TextRow(replacements[full.source_index],
                    [(e,visible_map[e.source_index],get_pos(e.text)) for e in ordered]))
            removed.update(e.source_index for e in fx)
    return [replacements.get(e.source_index,e) for e in events
            if e.source_index not in removed], len(removed)


def fit_cubic_points(expected: tuple, actual: tuple, *,
                     scale: float | None = None,
                     y_offset: float | None = None) -> tuple | None:
    """Fit matching contour commands with one uniform scale and translation."""
    if len(expected) != len(actual) or any(
            (isinstance(a,str) or isinstance(b,str)) and a != b for a,b in zip(expected,actual)):
        return None
    ep = [v for v in expected if not isinstance(v,str)]
    ap = [v for v in actual if not isinstance(v,str)]
    if len(ep) < 6 or not all(math.isfinite(v) for v in ep+ap):
        return None
    ex,ey,ax,ay = [p[axis::2] for p in (ep,ap) for axis in (0,1)]
    ex0,ey0,ax0,ay0 = map(statistics.mean,(ex,ey,ax,ay))
    denominator = sum((x-ex0)**2+(y-ey0)**2 for x,y in zip(ex,ey))
    if denominator <= 0:
        return None
    if scale is None:
        scale = sum((x-ex0)*(a-ax0)+(y-ey0)*(b-ay0)
                    for x,y,a,b in zip(ex,ey,ax,ay))/denominator
    tx,ty = ax0-scale*ex0,ay0-scale*ey0
    error = max(math.hypot(a-(scale*x+tx),b-(scale*y+(ty if y_offset is None else y_offset)))
                for x,y,a,b in zip(ex,ey,ax,ay))
    return scale,tx,ty,error


class FontSpacing:
    """Recover spaces from exact font advances and a consistent row geometry.

    No language model or word list is involved. Font files are matched by their
    internal family/full names and face flags; substitution is never allowed.
    """
    def __init__(self, directories=()):
        self.faces = {}
        self.cmaps = {}
        self.loaded = {}
        self.font_bytes = {}
        self.glyph_fragments = {}
        self.cubic_outlines = {}
        self.outline_profiles = {}
        self.ass_em_scales = {}
        self.missing = set()
        self.merged = 0
        self.available = False
        try:
            from PIL import ImageFont
            from fontTools.ttLib import TTFont, TTCollection
        except ImportError:
            return
        self.ImageFont = ImageFont
        self.harfbuzz = None
        self.shaping_fonts = {}
        try:
            import uharfbuzz
            self.harfbuzz = uharfbuzz
        except ImportError:
            pass  # RAQM installations do not require an additional backend.
        self.available = True
        import os
        roots = list(directories) + [Path(__file__).resolve().parent / "fonts"]
        if os.name == "nt":
            roots += [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
            if os.environ.get("LOCALAPPDATA"):
                roots += [Path(os.environ["LOCALAPPDATA"]) / "Microsoft/Windows/Fonts"]
        else:
            roots += [Path('/usr/share/fonts'), Path('/usr/local/share/fonts'),
                      Path.home()/'.local/share/fonts', Path('/Library/Fonts'),
                      Path('/System/Library/Fonts'), Path.home()/'Library/Fonts']
        # Resolve path aliases while preserving the first directory's priority.
        roots = list(dict.fromkeys(Path(root).resolve() for root in roots))
        seen = set()
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob('*')):
                if path.suffix.lower() not in {'.ttf','.otf','.ttc','.otc'} or path in seen:
                    continue
                seen.add(path)
                collection = None
                faces = []
                try:
                    if path.suffix.lower() in {'.ttc','.otc'}:
                        collection = TTCollection(str(path), lazy=True)
                        faces = collection.fonts
                    else:
                        faces = [TTFont(str(path), lazy=True)]
                    for index, face in enumerate(faces):
                        # Variable font defaults need axis selection; do not
                        # pretend the default is the requested static face.
                        if 'fvar' in face:
                            continue
                        names = {n.toUnicode().strip().casefold() for n in face['name'].names
                                 if n.nameID in {1,4,6,16}}
                        flags = face['head'].macStyle
                        bold, italic = bool(flags & 1), bool(flags & 2)
                        for name in names:
                            self.faces.setdefault((name,bold,italic),[]).append((str(path),index))
                except Exception:
                    # An unreadable font must not prevent subtitle processing.
                    pass
                finally:
                    if collection is not None:
                        collection.close()
                    else:
                        for face in faces:
                            face.close()

    def matching_face(self, family: str, bold: bool, italic: bool):
        """Prefer the requested weight, falling back within the exact name.

        Renderers can embolden a regular face when no bold face is embedded.
        A bold-only named face can also be used with ASS's bold flag unset.
        Its advances are only a candidate: the row must still pass the font
        measurement and position checks. Never change family or italic style.
        """
        for weight in (bold,not bold):
            for path,index in self.faces.get((family.casefold(),weight,italic),()):
                cmap = self.codepoints(path,index)
                if cmap is not None:
                    return path,index,cmap
        return None

    def codepoints(self, path: str, index: int):
        """Cache coverage only for matched faces; None marks an unreadable face."""
        key = (path,index)
        if key not in self.cmaps:
            from fontTools.ttLib import TTFont
            face = None
            try:
                # fontNumber selects TTC/OTC faces without opening their peers.
                face = TTFont(path,fontNumber=index,lazy=True)
                self.cmaps[key] = frozenset((face.getBestCmap() or {}).keys())
            except Exception:
                # Retain later candidates for the same exact name and weight.
                self.cmaps[key] = None
            finally:
                if face is not None:
                    face.close()
        return self.cmaps[key]

    def measure(self, face, text: str, kerning: bool = False, *,
                ligatures: bool = True) -> float:
        """Return exact-face shaped advances at 1024 px using RAQM or HarfBuzz.

        Direct HarfBuzz avoids RAQM's separate FriBiDi DLL on Windows. The
        caller still validates direction, glyph coverage and the complete row;
        this method never substitutes fonts or estimates spaces geometrically.
        """
        if not text:
            return 0.0
        path,index,_ = face
        key = (path,index)
        # Share lazily loaded collection bytes across faces and shaping backends.
        if path not in self.font_bytes:
            self.font_bytes[path] = Path(path).read_bytes()
        if key not in self.loaded:
            self.loaded[key] = self.ImageFont.truetype(BytesIO(self.font_bytes[path]),1024,index=index)
        font = self.loaded[key]
        if font.layout_engine == self.ImageFont.Layout.RAQM:
            features = ["kern" if kerning else "-kern"]
            if not ligatures:
                features.extend(("-liga","-clig"))
            return font.getlength(text,features=features)
        hb = self.harfbuzz
        if hb is None:
            raise ValueError("Font measurement needs RAQM or uharfbuzz")
        if key not in self.shaping_fonts:
            hb_face = hb.Face(self.font_bytes[path],index)
            if not hb_face.upem:
                raise ValueError("Invalid font face")
            hb_font = hb.Font(hb_face)
            hb.ot_font_set_funcs(hb_font)
            # 26.6 pixel units retain subpixel precision like FreeType/Pillow.
            hb_font.scale = (1024*64,1024*64)
            self.shaping_fonts[key] = hb_font
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        if buffer.direction != "ltr":
            raise ValueError("This row reconstruction requires horizontal LTR text")
        features = {"kern":bool(kerning)}
        if not ligatures:
            features.update(liga=False,clig=False)
        hb.shape(self.shaping_fonts[key],buffer,features)
        if any(info.codepoint == 0 for info in buffer.glyph_infos):
            raise ValueError("Shaping produced a missing glyph")
        if any(position.y_advance for position in buffer.glyph_positions):
            raise ValueError("Vertical glyph advances are unsupported")
        return sum(position.x_advance for position in buffer.glyph_positions)/64

    def fragmented_glyph(self, face, glyph: str) -> bool | None:
        """Inspect only requested exact-face outlines; unreadable stays unknown.

        A stamp has at least 64 closed contours, with at least 90 percent
        smaller than one percent of its overall control-point bounding box.
        This alone never authorizes deleting text: the decoration pass also
        requires dense scattered placement and an independent held caption.
        """
        path,index,cmap = face
        key = (path,index,glyph)
        if key not in self.glyph_fragments:
            self.glyph_fragments[key] = None
            font = None
            try:
                from fontTools.ttLib import TTFont
                from fontTools.pens.recordingPen import DecomposingRecordingPen
                if path not in self.font_bytes:
                    self.font_bytes[path] = Path(path).read_bytes()
                font = TTFont(BytesIO(self.font_bytes[path]),fontNumber=index,lazy=True)
                glyphs = font.getGlyphSet()
                pen = DecomposingRecordingPen(glyphs)
                glyphs[font.getBestCmap()[ord(glyph)]].draw(pen)
                contours,points = [],[]
                for op,coords in pen.value:
                    if op == "closePath":
                        if points:
                            contours.append(points)
                        points = []
                    elif op == "endPath":
                        raise ValueError("Open glyph contour")
                    else:
                        points.extend(p for p in coords if p is not None)
                def box_area(points):
                    xs,ys = zip(*points)
                    return (max(xs)-min(xs))*(max(ys)-min(ys))
                if not contours or any(not math.isfinite(v)
                        for contour in contours for point in contour for v in point):
                    raise ValueError("Empty or invalid glyph outline")
                self.glyph_fragments[key] = False
                if len(contours) >= 64:
                    area = box_area([p for contour in contours for p in contour])
                    self.glyph_fragments[key] = area > 0 and sum(
                        box_area(contour) <= .01*area for contour in contours) >= .9*len(contours)
            except Exception:
                self.glyph_fragments[key] = None
            finally:
                if font is not None:
                    font.close()
        return self.glyph_fragments[key]

    def cubic_outline(self, face, text: str) -> tuple | None:
        """Cache exact-face contour topology and points for requested text.

        Font coordinates remain unscaled; callers must prove size, placement
        and cue ownership separately. Quadratic curves are converted exactly
        to cubics, and composite glyphs use the same decomposed pen path.
        Contextual shaping and missing glyphs cannot authorize recovery.
        """
        path,index,cmap = face
        key = (path,index,text)
        if key not in self.cubic_outlines:
            self.cubic_outlines[key] = None
            font = None
            try:
                from fontTools.ttLib import TTFont
                from fontTools.pens.basePen import BasePen
                if any(ord(c) not in cmap or unicodedata.combining(c) or
                       unicodedata.bidirectional(c) in {'R','AL','AN'} for c in text):
                    return None
                if path not in self.font_bytes:
                    self.font_bytes[path] = Path(path).read_bytes()
                font = TTFont(BytesIO(self.font_bytes[path]),fontNumber=index,lazy=True)
                glyphs, mapping = font.getGlyphSet(),font.getBestCmap()
                class CubicPen(BasePen):
                    def __init__(self):
                        super().__init__(glyphs)
                        self.offset, self.tokens = 0.0, []
                    def add(self, op, *points):
                        self.tokens.append(op)
                        for x,y in points:
                            self.tokens.extend((x+self.offset,-y))
                    def _moveTo(self,p): self.add('m',p)
                    def _lineTo(self,p): self.add('l',p)
                    def _curveToOne(self,a,b,c): self.add('b',a,b,c)
                    def _qCurveToOne(self,b,c):
                        a = self._getCurrentPoint()
                        self._curveToOne(tuple((x+2*y)/3 for x,y in zip(a,b)),
                                         tuple((x+2*y)/3 for x,y in zip(c,b)),c)
                    def _closePath(self): pass
                    def _endPath(self): raise ValueError('Open font contour')
                pen = CubicPen()
                for char in text:
                    glyph = glyphs[mapping[ord(char)]]
                    glyph.draw(pen)
                    pen.offset += glyph.width
                if (not pen.tokens or not pen.offset or
                        abs(self.measure(face,text,False)*font['head'].unitsPerEm/1024-
                            pen.offset) > font['head'].unitsPerEm/1024):
                    return None
                self.cubic_outlines[key] = (tuple(pen.tokens),font['head'].unitsPerEm)
            except Exception:
                pass  # Unreadable/unsupported outlines are not evidence.
            finally:
                if font is not None:
                    font.close()
        return self.cubic_outlines[key]

    def decode_cubic_outline(self, face, path: tuple, fs: float, unit: float,
                             alphabet: set[str]) -> str | None:
        """Read only an unambiguous exact-font contour/advance sequence.

        Search printable ASCII plus literal characters present in the input,
        rather than loading every installed font's glyphs. Every glyph must
        share the first glyph's scale/baseline, and every gap must fit measured
        advances/spaces. Ambiguity or a bounded search overflow rejects the run.
        This is font geometry matching, with no language/word heuristics.
        """
        nominal = self.ass_em_scale(face)
        if nominal is None or not math.isfinite(fs) or fs <= 0:
            return None
        characters = tuple(sorted(char for char in set(map(chr,range(33,127)))|alphabet
                                  if not char.isspace() and ord(char) in face[2]))
        key = (*face[:2],characters)
        if key not in self.outline_profiles:
            profiles = []
            for char in characters:
                if self.fragmented_glyph(face,char) is True:
                    continue  # Grain/stamp fonts remain decorative effects.
                outline = self.cubic_outline(face,char)
                if outline is not None:
                    profiles.append((char,outline[0],outline[1],
                                     self.measure(face,char)*outline[1]/1024))
            self.outline_profiles[key] = profiles
        profiles = self.outline_profiles[key]
        if not profiles:
            return None
        em = profiles[0][2]
        nominal *= fs/em
        space = self.measure(face,' ')*em/1024
        if space <= 0:
            return None
        tolerance = max(unit,.04*fs)
        options = [(0,'',None,None,None,None)]
        completed = set()
        examined = 0
        while options:
            offset,text,scale,y,last_x,last_advance = options.pop()
            examined += 1
            if examined > 4096 or len(options) > 32:
                return None
            if offset == len(path):
                completed.add(text)
                if len(completed) > 1:
                    return None
                continue
            for char,model,em,advance in profiles:
                fitted = fit_cubic_points(model,path[offset:offset+len(model)],scale=scale,y_offset=y)
                if fitted is None:
                    continue
                factor,x,baseline,error = fitted
                if abs(factor-nominal) > .2*nominal or error > tolerance:
                    continue
                spaces = 0
                if last_x is not None:
                    gap = x-last_x-last_advance*factor
                    spaces = round(gap/(space*factor))
                    if spaces < 0 or spaces > 3 or abs(gap-spaces*space*factor) > tolerance:
                        continue
                options.append((offset+len(model),text+' '*spaces+char,factor,
                                baseline if y is None else y,x,advance))
        return next(iter(completed)) if len(completed) == 1 else None

    def recover(self, ordered, fragments, *, max_size_error: float | None = None):
        if not self.available or len(ordered) < 4:
            return None
        import unicodedata
        if any(not t or t != t.strip() or any(c.isspace() or
               unicodedata.bidirectional(c) in {'R','AL','AN'} or
               unicodedata.combining(c) for c in t) for t in fragments):
            return None
        first = ordered[0].state
        identity = ('fn','fs','b','i','fsp','an')
        if any(any(e.state.get(k) != first.get(k) for k in identity) or
               any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay'))
               for e in ordered):
            return None
        family = str(first.get('fn','')).strip()
        key = (family.casefold(), bool(first.get('b',0)), bool(first.get('i',0)))
        face = self.matching_face(family, key[1], key[2])
        if face is None:
            self.missing.add(family)
            return None
        path, index, cmap = face
        if any(ord(c) not in cmap for c in ''.join(fragments)+' '):
            return None
        try:
            kerning = bool(first.get("kerning",False))
            sx = statistics.median(e.state.get('fscx',100) for e in ordered)
            sy = statistics.median(e.state.get('fscy',100) for e in ordered)
            if sx <= 0 or sy <= 0:
                return None
            scale = first.get('fs',20)*sx/100/1024
            spacing = first.get('fsp',0)*sx/100
            # Nonzero authored tracking has differing renderer conventions.
            if abs(spacing) > .001:
                return None
            widths = [self.measure(face,t,kerning)*scale for t in fragments]
            space = self.measure(face,' ',kerning)*scale
        except (OSError, ValueError, RuntimeError):
            return None
        if space <= 0:
            return None
        alignment = int(first.get('an',5))
        if alignment not in range(1,10):
            return None
        anchor = ((alignment-1)%3)/2
        xs = [get_pos(e.text)[0] for e in ordered]
        deltas = [b-a for a,b in zip(xs,xs[1:])]
        base = [(1-anchor)*a+anchor*b for a,b in zip(widths,widths[1:])]
        # ASS font size conventions differ from Pillow's em size. Calibrate
        # one common multiplier for the row, checking every boundary against
        # an integral number of measured spaces. Ambiguous fits stay positioned.
        fits, unbroken_fits = {}, {}
        for distance, advance in zip(deltas,base):
            for bit in (0,1):
                factor = distance/(advance+bit*space)
                if not .5 <= factor <= 1.5:
                    continue
                for _ in range(3):
                    bits = tuple(max(0,math.floor((distance-factor*advance)/(factor*space)+.5))
                                 for distance,advance in zip(deltas,base))
                    predicted = [advance+bit*space for advance,bit in zip(base,bits)]
                    factor = sum(a*b for a,b in zip(predicted,deltas))/sum(a*a for a in predicted)
                if (not .5 <= factor <= 1.5 or
                        sum(bits) > sum(map(len,fragments))
                        or (any(bits) and 0 in bits and bits.count(0)<2 and len(bits)<4)):
                    continue
                errors = [abs(actual-factor*expected)/(factor*space)
                          for actual,expected in zip(deltas,predicted)]
                # Up to one script pixel of coordinate rounding is tolerated.
                if max(errors) > .22 + min(.12,1/(factor*space)):
                    continue
                score = sum(e*e for e in errors)/len(errors)
                destination = fits if any(bits) and 0 in bits else unbroken_fits
                if bits not in destination or score < destination[bits][0]:
                    destination[bits] = (score,factor)
        # Preserve established mixed-space recovery. When it has no fit,
        # try an unbroken run, retaining entirely spaced alternatives as
        # ambiguity evidence (especially for equal-width fonts).
        candidates = fits or unbroken_fits
        if not candidates:
            return None
        ranked = sorted(candidates.items(),key=lambda pair:pair[1][0])
        if len(ranked)>1 and ranked[1][1][0]-ranked[0][1][0] < .02:
            return None
        bits, (_,factor) = ranked[0]
        if max_size_error is not None:
            nominal = self.ass_em_scale(face)
            if nominal is None or abs(factor-nominal) > max_size_error*nominal:
                return None
        # Entirely spaced rows cannot calibrate a no-space reference. Keep
        # them as ambiguity evidence, but only emit mixed or unbroken fits.
        if 0 not in bits:
            return None
        text = fragments[0]+''.join(' '*bit+t for bit,t in zip(bits,fragments[1:]))
        # A merged font may kern across the old fragment seams. Reject a large
        # difference between the assembled advance and the measured row span.
        span = factor*(sum(widths)+sum(bits)*space)
        try:
            if abs(self.measure(face,text,kerning)*scale*factor-span) > max(1,.2*factor*space):
                return None
        except (OSError,ValueError,RuntimeError):
            return None
        center = (xs[0]-anchor*widths[0]*factor +
                  xs[-1]+(1-anchor)*widths[-1]*factor)/2
        return text, center, sx, sy, ((alignment-1)//3)*3+2

    def recover_tracked(self, ordered, fragments):
        """Recover a tracked single-glyph row without rescaling its glyphs.

        Reuse spacing recovery for the literal text, then fit only one tracking
        value against exact ASS font metrics. Every original anchor must fit
        within a bounded tolerance relative to glyph advance. Shaping across
        former glyph seams must preserve the separate advances.
        """
        # Brief bursts can belong to entrance/exit effects, rather than a held
        # line. Leave them to the existing effect-removal passes.
        if (not ordered or any(e.duration <= .25 for e in ordered) or
                any(len(t) != 1 for t in fragments)):
            return None
        state = ordered[0].state
        spacing = state.get('fsp',0)
        if not math.isfinite(spacing) or abs(spacing) <= .001:
            return None
        fit = self.recover([dataclass_replace(e,state={**e.state,'fsp':0})
                            for e in ordered],fragments)
        if fit is None:
            return None
        text,_,sx,sy,alignment = fit
        if any(any(e.state.get(k) != state.get(k)
                   for k in ('fn','fs','b','i','fsp','an','fscx','fscy'))
               for e in ordered):
            return None
        face = self.matching_face(str(state.get('fn','')),bool(state.get('b',0)),
                                  bool(state.get('i',0)))
        factor = self.ass_em_scale(face) if face is not None else None
        if factor is None:
            return None
        scale = state.get('fs',20)*sx/100/1024*factor
        kerning = bool(state.get('kerning',False))
        try:
            widths = [self.measure(face,c,kerning,ligatures=False)*scale for c in text]
            full = self.measure(face,text,kerning,ligatures=False)*scale
        except (OSError,ValueError,RuntimeError):
            return None
        if abs(full-sum(widths)) > 1:
            return None
        anchor = ((int(state.get('an',5))-1)%3)/2
        indices = [i for i,c in enumerate(text) if not c.isspace()]
        xs = [get_pos(e.text)[0] for e in ordered]
        prefix = [0.0]
        for width in widths:
            prefix.append(prefix[-1]+width)
        residuals = [x-prefix[i]-anchor*widths[i] for x,i in zip(xs,indices)]
        mean_i,mean_r = statistics.mean(indices),statistics.mean(residuals)
        denominator = sum((i-mean_i)**2 for i in indices)
        tracking = sum((i-mean_i)*(r-mean_r) for i,r in zip(indices,residuals))/denominator
        origin = mean_r-tracking*(mean_i+anchor)
        # Allow modest irregular spacing, measured in script pixels at the
        # rendered glyph size. Exclude word spaces from the typical advance.
        tolerance = min(5,max(1,.1*statistics.median(widths[i] for i in indices)))
        # Check every anchor against the completed row, so boundary errors
        # cannot accumulate. Keep the existing bound on fitted tracking.
        if (abs(tracking) > .1*state.get('fs',20)*sx/100 or
                abs(tracking) <= .001 or any(w+tracking <= 0 for w in widths) or
                max(abs(x-(origin+prefix[i]+anchor*widths[i]+
                           tracking*(i+anchor))) for x,i in zip(xs,indices)) > tolerance):
            return None
        center = origin+(full+len(text)*tracking)/2
        return text,center,sx,sy,alignment,tracking*100/sx

    def ass_em_scale(self, face) -> float | None:
        """Cache exact-face Windows line metrics used for ASS font sizing."""
        path,index,_ = face
        key = (path,index)
        if key not in self.ass_em_scales:
            self.ass_em_scales[key] = None
            font = None
            try:
                from fontTools.ttLib import TTFont
                if path not in self.font_bytes:
                    self.font_bytes[path] = Path(path).read_bytes()
                font = TTFont(BytesIO(self.font_bytes[path]),fontNumber=index,lazy=True)
                height = font['OS/2'].usWinAscent+font['OS/2'].usWinDescent
                em = font['head'].unitsPerEm
                if height > 0 and em > 0:
                    self.ass_em_scales[key] = em/height
            except Exception:
                pass  # Unsupported metrics cannot prove identical placement.
            finally:
                if font is not None:
                    font.close()
        return self.ass_em_scales[key]

    def fragment_anchor(self, state: dict, xs: list[float], fragments: list[str],
                        text: str, unit: float, *, allow_tracking: bool = False,
                        separate_glyphs: bool = False,
                        exact_size: bool = False,
                        max_size_error: float | None = None) -> float | None:
        """Fit an authored fragment anchor to exact-font glyph positions.

        Calibrate the font's common size convention from the recorded run;
        leading and trailing spaces shift its anchor without inventing gaps.
        Tracking is opt-in for matching known glyph text, not spacing recovery.
        Separately rendered glyphs use their own advances; contextual shaping
        of the assembled word must not change the measured letter-run span.
        Exact-size proofs additionally use the font's ASS line metrics and
        verify every recorded glyph position, without fitting another scale.
        """
        if (not self.available or not fragments or len(xs) != len(fragments) or
                any(not word or any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word)
                    for word in fragments) or ''.join(fragments) != text.strip() or
                abs(state.get('fsp',0)) > .001 and not allow_tracking):
            return None
        face = self.matching_face(str(state.get('fn','')),bool(state.get('b',0)),bool(state.get('i',0)))
        if face is None or any(ord(c) not in face[2] for c in text):
            return None
        kerning = bool(state.get('kerning',False))
        scale = state.get('fs',20)*state.get('fscx',100)/100/1024
        try:
            widths = [self.measure(face,word,kerning)*scale for word in fragments]
            if separate_glyphs:
                if text != text.strip() or any(len(word) != 1 for word in fragments):
                    return None
                width = sum(widths)
            else:
                width = self.measure(face,text.strip(),kerning)*scale
            leading = self.measure(face,text[:len(text)-len(text.lstrip())],kerning)*scale
            trailing = self.measure(face,text[len(text.rstrip()):],kerning)*scale
        except (OSError,ValueError,RuntimeError):
            return None
        if any(w <= 0 for w in widths) or abs(width-sum(widths)) > unit:
            return None
        alignment = int(state.get('an',5))
        if alignment not in range(1,10):
            return None
        anchor = ((alignment-1)%3)/2
        advances = [(1-anchor)*a+anchor*b for a,b in zip(widths,widths[1:])]
        tracking = state.get('fsp',0)*state.get('fscx',100)/100
        gaps = [tracking*((1-anchor)*len(a)+anchor*len(b))
                for a,b in zip(fragments,fragments[1:])]
        if not advances:
            return xs[0] if text == text.strip() else None
        factor = sum((b-a-gap)*w for a,b,w,gap in zip(xs,xs[1:],advances,gaps))/sum(w*w for w in advances)
        if (not .5 <= factor <= 1.5 or
                any(abs(b-a-factor*w-gap) > 1.5*unit
                    for a,b,w,gap in zip(xs,xs[1:],advances,gaps))):
            return None
        if max_size_error is not None:
            nominal = self.ass_em_scale(face)
            if nominal is None or abs(factor-nominal) > max_size_error*nominal:
                return None
        if exact_size:
            factor = self.ass_em_scale(face)
            if factor is None:
                return None
            offset = 0.0
            for x,advance,gap in zip(xs[1:],advances,gaps):
                offset += factor*advance+gap
                if abs(x-xs[0]-offset) > .25*unit:
                    return None
        return (xs[0]-anchor*factor*widths[0]+
                factor*(anchor*width+(anchor-1)*leading+anchor*trailing)+
                tracking*(anchor*(len(text.strip())-len(fragments[0]))+
                          (anchor-1)*(len(text)-len(text.lstrip()))+
                          anchor*(len(text)-len(text.rstrip()))))

    def authored_glyph_positions(self, state: dict,
                                         text: str, anchor_x: float,
                                         unit: float) -> list[tuple[str,float]] | None:
        """Measure a known caption's separate glyph anchors, including spaces.

        Use its held size and ASS font metrics rather than fitting a new size.
        Reject contextual shaping that changes the individual glyph advances.
        """
        if (not self.available or
                any(unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in text) or
                any(c in text for c in ('\\','\n','\r','\t'))):
            return None
        face = self.matching_face(str(state.get('fn','')),bool(state.get('b',0)),bool(state.get('i',0)))
        if face is None or any(ord(c) not in face[2] for c in text):
            return None
        factor = self.ass_em_scale(face)
        alignment = int(state.get('an',5))
        if factor is None or alignment not in range(1,10):
            return None
        scale = state.get('fs',20)*state.get('fscx',100)/100/1024*factor
        tracking = state.get('fsp',0)*state.get('fscx',100)/100
        try:
            kerning = bool(state.get('kerning',False))
            widths = [self.measure(face,c,kerning)*scale for c in text]
            width = self.measure(face,text,kerning)*scale
        except (OSError,ValueError,RuntimeError):
            return None
        if scale <= 0 or abs(width-sum(widths)) > unit:
            return None
        anchor = ((alignment-1)%3)/2
        origin = anchor_x-anchor*(width+tracking*(len(text)-1))
        expected = []
        for c,w in zip(text,widths):
            if not c.isspace():
                expected.append((c,origin+anchor*w))
            origin += w+tracking
        return expected

    def matches_authored_glyph_positions(self, state: dict, xs: list[float],
                                         text: str, anchor_x: float,
                                         unit: float) -> bool:
        expected = self.authored_glyph_positions(state,text,anchor_x,unit)
        return (expected is not None and len(xs) == len(expected) and
                all(abs(x-model) <= 1.5*unit for x,(_,model) in zip(xs,expected)))

    def fit_fullwidth_run(self, ordered: list[Event], glyphs: list[str]):
        """Fit one unbroken row against its exact font's glyph advances."""
        if not self.available or len(ordered) < 2 or sum(map(len,glyphs)) < 3:
            return None
        state = ordered[0].state
        family = str(state.get("fn", "")).strip()
        key = (family.casefold(), bool(state.get("b",0)), bool(state.get("i",0)))
        face = self.matching_face(family, key[1], key[2])
        if face is None:
            self.missing.add(family)
            return None
        path, index, cmap = face
        if any(ord(g) not in cmap for fragment in glyphs for g in fragment):
            return None
        if any(any(e.state.get(k) != state.get(k)
                   for k in ("fn","fs","fscx","fscy","an","b","i","fsp"))
               for e in ordered):
            return None
        fs, sx = state.get("fs",0), state.get("fscx",100)
        if fs <= 0 or sx <= 0:
            return None
        try:
            kerning = bool(state.get("kerning",False))
            text = "".join(glyphs)
            scale = fs*sx/100/1024
            widths = [self.measure(face,g,kerning)*scale for g in glyphs]
            offsets = [0]
            for fragment in glyphs:
                offsets.append(offsets[-1]+len(fragment))
            advances = [self.measure(face,text[:i],kerning)*scale for i in offsets]
        except (OSError,ValueError,RuntimeError):
            return None
        # Adjacent glyph positions are their own alignment anchors, not
        # necessarily their centres. Preserve the original glyph width.
        alignment = int(state.get("an",5))
        if alignment not in range(1,10):
            return None
        anchor = ((alignment-1)%3)/2
        model = [advance+anchor*width for advance,width in zip(advances,widths)]
        xs = [get_pos(e.text)[0] for e in ordered]
        model_delta = [b-a for a,b in zip(model,model[1:])]
        actual_delta = [b-a for a,b in zip(xs,xs[1:])]
        denominator = sum(v*v for v in model_delta)
        if denominator == 0:
            return None
        factor = sum(a*b for a,b in zip(model_delta,actual_delta))/denominator
        if not .85 <= factor <= 1.15:
            return None
        origin = statistics.mean(x-factor*advance for x,advance in zip(xs,model))
        if max(abs(x-(origin+factor*advance))
               for x,advance in zip(xs,model)) > max(1.25,.06*statistics.median(actual_delta)):
            return None
        return (origin+anchor*factor*advances[-1], sx*factor)


def render_merged_caption(ordered: list[Event], fragments: list[str], text: str,
                          *, animated: bool, an: int, pos: tuple[float,float],
                          fscx: float, fscy: float, fsp: float | None = None) -> str | None:
    """Render a validated row using its recovered text and placement.

    Preserve each animated fragment's paint and decorations, or the shared
    static formatting. Return None if span formatting cannot map to the text.
    Spacing recovery, row eligibility and event updates belong to the caller.
    """
    alignment = an
    x,y = pos
    sx,sy = fscx,fscy
    norm = lambda value: "".join(value.split())
    chosen = ordered[0]
    if animated:
        # Normalize geometry/effects, retaining each fragment's formatting.
        # Visibility changes also mark stable gradient glyphs as animated;
        # merging them must not spread the first glyph's fill over the row.
        body = aggressive_caption(chosen.state,text,
                                  outline_states=[e.state for e in ordered],
                                  an=alignment,pos=(x,y),fscx=sx,fscy=sy)
        paints = [effective_state(aggressive_caption(e.state,fragment),e.defaults,e.styles)
                  for e,fragment in zip(ordered,fragments)]
        span_tags = ('b','i','u','s','1c','3c')
        formatting = [tuple(paint[k] for k in span_tags) for paint in paints]
        if len(set(formatting)) > 1:
            # Spacing may come from comments, blank anchors or exact font
            # measurements. Map by literal nonspace characters in all three
            # routes; never alter the recovered text or infer word breaks.
            if norm(text) != norm(''.join(fragments)):
                return None
            header = body[:body.index('}')+1]
            live = effective_state(header,chosen.defaults,chosen.styles)
            segments = []
            cursor = 0
            for fragment,paint in zip(fragments,paints):
                begin = cursor
                remaining = len(norm(fragment))
                while remaining and cursor < len(text):
                    remaining -= not text[cursor].isspace()
                    cursor += 1
                tags = ''.join(render_tag(k,paint[k]) for k in span_tags
                               if live.get(k) != paint[k])
                segments.append(('{' + tags + '}' if tags else '')+text[begin:cursor])
                live.update({k:paint[k] for k in span_tags})
            body = header+''.join(segments)+text[cursor:]
    else:
        # Candidate grouping guarantees identical static state. Reusing
        # its tags also preserves underline, outline axes and other tags.
        tags = "".join(OVERRIDE_RE.findall(chosen.text))
        tags = "".join("\\"+name+value for name,value in tokenize_override(tags)
                       if name not in {"pos","an","a","fscx","fscy"})
        body = "{"+tags+f"\\an{alignment}\\pos({x:g},{y:g})\\fscx{sx:g}\\fscy{sy:g}"+"}"+text
    if fsp is not None:
        # This is one proven positioned row, including when it is wider than
        # the canvas. Disable automatic wrapping and replace prior tracking.
        end = body.index('}')
        tags = ''.join('\\'+tag+value for tag,value in tokenize_override(body[1:end])
                       if tag not in {'fsp','q'})
        body = '{'+tags+render_tag('fsp',fsp)+r'\q2'+body[end:]
    return body


def collapse_translated_phase_rows(events: list[Event], visible: dict[int,str],
                                   metric: FontSpacing | None
                                   ) -> tuple[list[Event],int,list[TextRow]]:
    """Flatten complete authored rows with measured entrance/translation phases.

    Touching before/after fragments prove a shared horizontal translation.
    The exact font and authored spaces must account for every glyph in the
    initial row and its held backing. Short bounce/fade phases may then vary
    in paint and grouping; moving syllables need a touching held successor.
    Without translation, at least four changing entrance fragments are needed.
    Missing text, competing persistent neighbors or shared ownership reject
    the cue. Neither actor names nor fixed effect timings/coordinates matter.
    """
    if metric is None or not getattr(metric,'available',False):
        return events,0,[]
    cues = [e for e in events if e.kind == 'Comment' and e.duration > 0]
    if not cues:
        return events,0,[]
    cue_styles = {e.style for e in cues}
    allids = {e.source_index:e for e in events}
    def basic(e):
        return (e.style,placement_key(e),tuple((k,v) for k,v in text_layout_key(e)
                if k not in {'fscx','fscy','fax','fay'}))
    def motion_profiles():
        keys, poses, words, begins, ends, eligible = {}, {}, {}, {}, {}, []
        for e in events:
            word, pos = visible.get(e.source_index,''), get_pos(e.text)
            if (e.kind != 'Dialogue' or e.style not in cue_styles or not word or pos is None or e.duration <= 0 or
                    any(c.isspace() for c in word) or inline_layout_key(e) or
                    not opaque_text_effect_state(e.state) or not unrotated_text_state(e.state) or
                    static_object_key(e,e.styles) is None):
                continue
            key = basic(e)
            keys[e.source_index], poses[e.source_index], words[e.source_index] = key,pos,word
            eligible.append(e)
            if not any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay')):
                begins.setdefault((key,round(e.start_s,2)),[]).append(e)
                ends.setdefault((key,round(e.end_s,2)),[]).append(e)
        def matches(peers,target):
            peers = sorted(peers,key=lambda e:poses[e.source_index][0])
            spans = index_fragment_spans(words[e.source_index] for e in peers)
            output = []
            for a,b in matching_fragment_spans(spans,words[target.source_index]):
                row = peers[a:b+1]
                if (len({state_key(p,{'pos'}) for p in row}) != 1 or
                        any(abs(poses[p.source_index][1]-poses[target.source_index][1]) > .001 for p in row)):
                    continue
                anchor = metric.fragment_anchor(row[0].state,[poses[p.source_index][0] for p in row],
                    [words[p.source_index] for p in row],words[target.source_index],target.unit,
                    separate_glyphs=all(len(words[p.source_index]) == 1 for p in row),max_size_error=.1)
                if anchor is not None:
                    output.append((row,anchor))
            return output
        proposals = []
        for e in eligible:
            key, pos = keys[e.source_index],poses[e.source_index]
            left = matches(ends.get((key,round(e.start_s,2)),[]),e)
            right = matches(begins.get((key,round(e.end_s,2)),[]),e)
            options = []
            for before,bx in left:
                for after,ax in right:
                    delta = ax-bx
                    if (state_key(before[0],{'pos'}) != state_key(after[0],{'pos'}) or
                            abs(delta) <= e.unit or not min(ax,bx)-e.unit <= pos[0] <= max(ax,bx)+e.unit):
                        continue
                    if (len(before) == len(after) and any(
                            abs(poses[b.source_index][0]-poses[a.source_index][0]-delta) > 1.5*e.unit
                            for a,b in zip(before,after))):
                        continue
                    options.append((before,after,delta))
            if len(options) == 1:
                before,after,delta = options[0]
                ids = {e.source_index}|{p.source_index for p in before+after}
                proposals.append((ids,after,e,before,delta))
        claims = {}
        for ids,after,e,before,delta in proposals:
            for index in ids:
                claims[index] = claims.get(index,0)+1
        return [p for p in proposals if all(claims[index] == 1 for index in p[0])]
    profiles = motion_profiles()
    pool = {}
    for e in events:
        w = visible.get(e.source_index, '')
        p = get_pos(e.text)
        if (e.kind == 'Dialogue' and e.style in cue_styles and w and p and (e.duration > 0)
            and (not inline_layout_key(e)) and (static_object_key(e, e.styles) is not None)
            and unrotated_text_state(e.state) and (not any((k in e.state for k in ['clip', 'iclip', 'org'])))):
            pool.setdefault(e.style, []).append(e)
    proposals = []
    for cue in cues:
        text = simplify_text(cue.text, visible_only=True)[1]
        if len(''.join(text.split())) < 4 or cue.duration <= 0:
            continue
        # Scale lead-in/tail allowances with the cue, not a fixed time limit.
        window = 0.25 * cue.duration
        seeds = [p for p in profiles if p[2].style == cue.style and cue.start_s - 0.011 <= p[2].start_s
            and (p[2].end_s <= cue.end_s + 0.011)]
        if seeds:
            k = basic(seeds[0][3][0])
            delta = statistics.median((p[4] for p in seeds))
            if any((basic(p[3][0]) != k or abs(p[4] - delta) > p[2].unit + 0.1 * text_height(p[2]) for p in seeds)):
                continue
            sample = seeds[0][3][0]
            y = get_pos(sample.text)[1]
        else:
            options = [e for e in pool.get(cue.style, []) if opaque_text_effect_state(e.state)
                and e.start_s <= cue.start_s + window and (e.end_s >= cue.end_s - window)
                and (e.duration >= 0.5 * cue.duration) and (not any((abs(e.state.get(k, 0)) > 0.001 for k in ['fax',
                'fay'])))]
            if not options:
                continue
            sample = max(options, key=lambda e: e.duration)
            k = basic(sample)
            delta = 0
            y = get_pos(sample.text)[1]
        positions = metric.authored_glyph_positions(sample.state, text, 0, sample.unit)
        if not positions:
            continue
        candidates = [e for e in pool.get(cue.style, []) if basic(e) == k
            and cue.start_s - window - 0.001 <= e.start_s <= cue.start_s + window + 0.001
            and (e.end_s <= cue.end_s + window + 0.001)
            and (abs(get_pos(e.text)[1] - y) <= 0.25 * text_height(sample)) and (not any((abs(e.state.get(k,
            0)) > 0.001 for k in ['fax', 'fay']))) and (e.state.get('fscx') == sample.state.get('fscx'))
            and (e.state.get('fscy') == sample.state.get('fscy')) and (e.state.get('1c') == sample.state.get('1c'))]
        # Full font geometry must account for every authored nonspace glyph.
        first = [e for e in candidates if visible[e.source_index] == positions[0][0]]
        models = {}
        glyph_spans = index_fragment_spans(c for c,x in positions)
        for e in first:
            center = get_pos(e.text)[0] - positions[0][1]
            matches = [[p for p in candidates if visible[p.source_index] == char
                and abs(get_pos(p.text)[0] - (center + offset)) <= 1.5 * sample.unit] for char, offset in positions]
            for ids, new, phase, before, d in seeds:
                for b in before:
                    word = visible[b.source_index]
                    if len(word) <= 1:
                        continue
                    for a, z in matching_fragment_spans(glyph_spans, word):
                        gp = metric.authored_glyph_positions(sample.state, word, 0, sample.unit)
                        if (gp
                            and abs(get_pos(b.text)[0] - (center + positions[a][1] - gp[0][1])) <= sample.unit + 0.1 * text_height(sample)):
                            for i in range(a, z + 1):
                                matches[i].append(b)
            if any((not m for m in matches)):
                continue
            if (seeds and any((not all((any((p.source_index == b.source_index for m in matches for p in m))
                for b in before)) for ids, new, p, before, d in seeds))):
                continue
            models[round(center, 1)] = (center, matches)
        if len(models) != 1:
            continue
        center, matches = next(iter(models.values()))
        xs = [center + x for c, x in positions]
        initial_start = (min([b.start_s for ids, new, phase, before, d in seeds for b in before] + [p.start_s
            for group in matches for p in group if (p.end_s > cue.start_s + 0.011 or abs(p.end_s-cue.start_s) < .001)
            and abs(get_pos(p.text)[1] - y) <= sample.unit and (state_key(p, {'pos'}) == state_key(sample, {'pos'}))],
            default=cue.start_s))
        spans = glyph_spans

        options_cache = {}
        def span_options(e, dx=0, travel=False):
            key = (e.source_index,dx,travel)
            if key in options_cache:
                return options_cache[key]
            word = visible[e.source_index]
            poss = []
            for a, b in matching_fragment_spans(spans, ''.join(word.split())):
                anchor = (metric.fragment_anchor(sample.state, xs[a:b + 1], [c for c, x in positions[a:b + 1]], word,
                    sample.unit) if not any((c.isspace() for c in word)) else None)
                if anchor is None:
                    if any((c.isspace() for c in word)):
                        g = metric.authored_glyph_positions(sample.state, word, 0, sample.unit)
                        if g and len(g) == b - a + 1:
                            anchor = xs[a] - g[0][1]
                        if (anchor is not None and (not metric.matches_authored_glyph_positions(sample.state,
                            xs[a:b + 1], word, anchor, sample.unit))):
                            anchor = None
                if anchor is not None:
                    px, py = get_pos(e.text)
                    if (min(anchor, anchor + dx) - sample.unit <= px <= max(anchor, anchor + dx) + sample.unit
                        if travel else abs(px - anchor - dx) <= sample.unit + 0.1 * text_height(sample)):
                        poss.append((a, b))
            options_cache[key] = poss
            return poss
        before_ids = {p.source_index for ids,after,phase,before,d in seeds for p in before}
        after_ids = {p.source_index for ids,after,phase,before,d in seeds for p in after}
        effect_ends = {}
        for p in pool.get(cue.style,[]):
            changing = (any(abs(p.state.get(q,0)) > .001 for q in ('fax','fay')) or
                        any(p.state.get(q) != sample.state.get(q) for q in ('fscx','fscy')))
            if (basic(p) == k and changing and opaque_text_effect_state(p.state) and
                    cue.start_s-.011 <= p.start_s < cue.end_s and
                    abs(get_pos(p.text)[1]-y) <= sample.unit):
                effect_ends.setdefault(round(p.end_s,2),[]).append(p)
        stable = []
        entrances = []
        pulses = []
        for e in pool.get(cue.style, []):
            if (basic(e) != k or e.start_s < cue.start_s - window - 0.001 or e.end_s > cue.end_s + window + 0.001
                or (e.start_s >= cue.end_s + window) or (e.end_s <= cue.start_s - window)):
                continue
            w = visible[e.source_index]
            px, py = get_pos(e.text)
            flat = (not any((abs(e.state.get(q, 0)) > 0.001 for q in ['fax', 'fay']))
                and all((e.state.get(q) == sample.state.get(q) for q in ['fscx', 'fscy'])))
            if flat and state_key(e, {'pos'}) == state_key(sample, {'pos'}) and (abs(py - y) <= sample.unit):
                oldopts = span_options(e)
                newopts = span_options(e, delta)
                if e.source_index in after_ids:
                    opts = set(newopts)
                elif e.source_index in before_ids:
                    opts = set(oldopts)
                elif e.end_s < cue.end_s - window:
                    if seeds and e.start_s < initial_start - 0.011:
                        continue
                    opts = set(oldopts)
                elif e.start_s >= cue.start_s + window:
                    opts = set(newopts)
                else:
                    opts = set(oldopts + newopts)
                if len(opts) == 1 and e.start_s >= cue.end_s and e.source_index not in after_ids:
                    # A late held tail needs its own touching effect phase.
                    # The next cue's entrance cannot be backing for this row.
                    opts = {span for span in opts if any(
                        abs(p.end_s-e.start_s) <= .001 and any(
                            max(span[0],ab[0]) <= min(span[1],ab[1])
                            for ab in span_options(p,delta,True))
                        for p in effect_ends.get(round(e.start_s,2),[]))}
                if len(opts) == 1:
                    stable.append((e, next(iter(opts))))
                    continue
            if (flat and e.duration <= window + 0.001 and (e.start_s <= cue.start_s + window)
                and (e.end_s <= cue.start_s + window) and (abs(py - y) <= 0.25 * text_height(sample))
                and (e.state.get('1c') == sample.state.get('1c'))):
                opts = span_options(e)
                if not opts:
                    # A prior simplification may have mistaken a narrow
                    # letter for a space in an entrance prefix. Match every
                    # rendered glyph to the complete row instead of trusting
                    # that partial transcript. Missing held glyphs still
                    # reject the whole cue below.
                    recorded = metric.authored_glyph_positions(
                        e.state,visible[e.source_index],px,e.unit)
                    owners = [[i for i,(c,x) in enumerate(zip(
                        [c for c,x in positions],xs)) if c == char and
                        abs(x-gx) <= sample.unit+.2*text_height(sample)]
                        for char,gx in (recorded or [])]
                    if (len(owners) >= 4 and all(len(indices) == 1 for indices in owners) and
                            all(a[0] < b[0] for a,b in zip(owners,owners[1:]))):
                        opts = [(owners[0][0],owners[-1][0])]
                if len(opts) == 1:
                    entrances.append((e, opts[0]))
                    continue
            if (delta and not flat and opaque_text_effect_state(e.state) and abs(py - y) <= sample.unit
                and (cue.start_s - 0.011 <= e.start_s) and e.start_s < cue.end_s
                and (e.end_s <= cue.end_s + window + 0.001)):
                pulses.append((e,span_options(e,delta,True)))
        # An earlier merge may already hold a whole phrase over a later
        # syllable pulse. Its measured translated span proves that pulse too;
        # do not require the held event to begin again at every word boundary.
        covered_pulses = []
        for e,options in pulses:
            covered = [span for span in options if all(
                any(a <= i <= b and p.start_s <= e.end_s+.001 and p.end_s > e.end_s+.011 and
                    (a,b) in span_options(p,delta) for p,(a,b) in stable)
                for i in range(span[0],span[1]+1))]
            # Repeated words can have overlapping travel segments. Their
            # exact occurrence is immaterial when the complete held caption
            # already contains every candidate; ownership is still cue-wide.
            if covered:
                covered_pulses.append((e,covered[0]))
        pulses = covered_pulses
        if any((not any((a <= i <= b for e, (a, b) in stable)) for i in range(len(positions)))):
            continue
        # Static matching fragments alone do not prove an animation.
        changed = {ab for e, ab in entrances if abs(get_pos(e.text)[1] - y) > e.unit or e.state.get('1a', 0) > 0}
        if not seeds and len(changed) < 4:
            continue
        if seeds and len(seeds) < 2 and (len(pulses) < 3 or
                sum(len(visible[e.source_index]) > 1 for e,span in pulses) < 2):
            continue
        # Every glyph needs completed held backing, not only an early fragment.
        if any(not any(a <= i <= b and p.end_s >= cue.end_s-window and
                       (a,b) in span_options(p,delta) for p,(a,b) in stable)
               for i in range(len(positions))):
            continue
        members = [e for e, span in stable + entrances + pulses]
        ids = {e.source_index for e in members}
        if seeds:
            ids.update((i for pi, new, e, before, d in seeds for i in pi))
            members = [allids[i] for i in ids]
        blockers = [e for e in pool.get(cue.style, []) if basic(e) == k and e.source_index not in ids
            and (cue.start_s - 0.011 <= e.start_s < cue.end_s) and (min(e.end_s, cue.end_s) - max(e.start_s,
            cue.start_s) >= 0.5 * min(e.duration, cue.duration)) and (e.duration >= window)
            and (abs(get_pos(e.text)[1] - y) <= 0.25 * text_height(sample))
            and (xs[0] - text_height(sample) <= get_pos(e.text)[0] <= xs[-1] + text_height(sample))]
        if blockers:
            continue
        body = render_merged_caption([sample],[text],text,animated=False,
            an=int(sample.state.get('an',5)),pos=(center+delta,y),
            fscx=sample.state.get('fscx',100),fscy=sample.state.get('fscy',100),
            fsp=sample.state.get('fsp',0))
        if body is None:
            continue
        start = min((e.start_s for e in members))
        end = max((e.end_s for e in members))
        base = min(members, key=lambda e: e.source_index)
        caption = (replace_event(base, layer=sample.layer, text=body, start=format_time(start), start_s=start,
            end=format_time(end), end_s=end))
        core = (cue.start_s,cue.end_s) if start < cue.start_s < cue.end_s < end else None
        # Supply the verified glyph anchors even when an earlier pass already
        # combined the held backing into one event. Its center alone is not
        # the row's horizontal extent for the shared overlap pass.
        pieces = [(replace_event(sample,text=aggressive_caption(
            {**sample.state,'pos':(x+delta,y)},char)),char,(x+delta,y))
            for (char,offset),x in zip(positions,xs)]
        row = TextRow(caption,pieces,phase_core=core)
        proposals.append((ids, row, text))
    # Resolve ownership across complete cues, never greedily by event order.
    claims = collections.Counter((i for ids, e, t in proposals for i in ids))
    accepted = [p for p in proposals if all((claims[i] == 1 for i in p[0]))]
    ids = set().union(*(p[0] for p in accepted)) if accepted else set()
    out = [e for e in events if e.source_index not in ids]+[row.base for ids,row,t in accepted]
    for ids,row,t in accepted:
        visible[row.base.source_index] = t
        metric.merged += 1
    return sorted(out,key=lambda e:e.source_index),len(events)-len(out),[row for ids,row,t in accepted]




def collapse_fragment_phase_rows(events: list[Event], visible_map: dict[int,str],
                                  metric: FontSpacing | None
                                  ) -> tuple[list[Event],int,list[TextRow]]:
    """Assemble rows whose touching phases change fragment granularity.

    Exact-font anchors connect smaller fragments to the same completed word
    or syllable. Any number of same-anchor phases may follow. Ordered word
    activation and a shared terminal paint prove a complete readable row;
    event names, animation tags and particular colours are not evidence.
    Missing, competing or multiply claimed phases reject the whole cue.
    """
    if metric is None or not getattr(metric,'available',False):
        return events,0,[]
    eligible, words, geometry, positions = [], {}, {}, {}
    for e in events:
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or not word or pos is None or e.duration <= 0 or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word) or
                inline_layout_key(e) or not opaque_text_effect_state(e.state) or
                not unrotated_text_state(e.state) or
                static_object_key(e,e.styles) is None):
            continue
        # Vertical exit compression does not change horizontal glyph anchors.
        # A matched earlier completed phase supplies its readable height.
        key = (e.style,placement_key(e),tuple((k,v) for k,v in text_layout_key(e)
                                             if k != 'fscy'),round(pos[1],4))
        eligible.append(e)
        words[e.source_index],geometry[e.source_index],positions[e.source_index] = word,key,pos
    endings, anchored_starts, anchored_ends = {}, {}, {}
    for e in eligible:
        key = geometry[e.source_index]
        endings.setdefault((key,round(e.end_s,2)),[]).append(e)
        anchor = (key,positions[e.source_index],words[e.source_index])
        anchored_starts.setdefault((*anchor,round(e.start_s,2)),[]).append(e)
        anchored_ends.setdefault((*anchor,round(e.end_s,2)),[]).append(e)
    for group in endings.values():
        group.sort(key=lambda e:positions[e.source_index][0])
    # Lookup is local to a centisecond phase boundary, rather than comparing
    # every event with every other event in a font/row family.
    def before(e):
        key = (geometry[e.source_index],positions[e.source_index],words[e.source_index],round(e.start_s,2))
        return [p for p in anchored_ends.get(key,[])
                if abs(p.end_s-e.start_s) <= .001]

    def profile(tail):
        chain, current = [tail],tail
        while True:
            peers = before(current)
            if not peers:
                break
            if len(peers) != 1:
                return None
            current = peers[0]
            chain.append(current)
        word = words[tail.source_index]
        peers = (endings.get((geometry[tail.source_index],round(current.start_s,2)),[])
                 if len(word) > 1 else [])
        matches = []
        for offset,p in enumerate(peers):
            if not word.startswith(words[p.source_index]):
                continue
            pieces, text = [],''
            for index in range(offset,len(peers)):
                p = peers[index]
                if abs(p.end_s-current.start_s) > .001:
                    break
                pieces.append(p)
                text += words[p.source_index]
                if not word.startswith(text):
                    break
                if text == word:
                    xs = [positions[p.source_index][0] for p in pieces]
                    if len(pieces) > 1 and (any(b <= a for a,b in zip(xs,xs[1:])) or
                            len({state_key(p,{'pos'}) for p in pieces}) != 1):
                        break
                    anchor = metric.fragment_anchor(tail.state,xs,
                        [words[p.source_index] for p in pieces],word,tail.unit,exact_size=True)
                    if anchor is not None and abs(anchor-positions[tail.source_index][0]) <= .25*tail.unit:
                        matches.append(pieces)
                    break
        if len(matches) != 1:
            # Single-letter phases have already been traversed by before().
            # They participate only alongside proven multi-fragment joins.
            if matches or len(word) != 1 or len(chain) < 2:
                return None
            pieces = [chain.pop()]
            current = chain[-1]
        else:
            pieces = matches[0]
        members = pieces+chain
        if (min(p.end_s for p in members)-max(p.start_s for p in pieces) <= .011 or
                any(p.source_index == q.source_index for i,p in enumerate(members) for q in members[:i])):
            return None
        tail = replace_event(tail,text=aggressive_caption(
            {**tail.state,'fscy':current.state.get('fscy',100)},word))
        return (tail,members,min(p.start_s for p in pieces),current.start_s,
                tail.start_s,len(pieces) > 1)

    families = {}
    for e in eligible:
        paint = tuple(e.state.get(k,e.defaults.get(k,0)) for k in
                      ('1c','3c','4c','1a','3a','4a','bord','xbord','ybord',
                       'shad','xshad','yshad','blur','be'))
        key = (geometry[e.source_index],e.layer,paint)
        anchor = (geometry[e.source_index],positions[e.source_index],words[e.source_index],round(e.end_s,2))
        successors = [p for p in anchored_starts.get(anchor,[])
                      if abs(e.end_s-p.start_s) <= .001]
        if not successors:
            families.setdefault(key,[]).append((e,profile(e)))
    proposals = []
    for family in families.values():
        if sum(p is not None and p[-1] for e,p in family) < 2:
            continue
        for direction in (1,-1):
            sequence, cues = [],[]
            for e,p in sorted(family,key=lambda pair:((pair[1][3] if pair[1] else pair[0].start_s),
                                                    direction*positions[pair[0].source_index][0])):
                start = p[2] if p else e.start_s
                if sequence and (direction*(positions[e.source_index][0]-positions[sequence[-1][0].source_index][0]) <= e.unit or
                                 start >= min(q.end_s for q,_ in sequence)-.011):
                    cues.append(sequence);sequence=[]
                sequence.append((e,p))
            cues.append(sequence)
            for cue in cues:
                if len(cue) < 4 or any(p is None for e,p in cue) or sum(p[-1] for e,p in cue) < 2:
                    continue
                if (any(b[1][3] <= a[1][3]+.011 or b[1][4] < a[1][4]-.011
                        for a,b in zip(cue,cue[1:])) or
                        any(b[0].end_s < a[0].end_s-.011 for a,b in zip(cue,cue[1:]))):
                    continue
                held = sorted((p[0] for e,p in cue),key=lambda e:positions[e.source_index][0])
                if len({state_key(e,{'pos'}) for e in held}) != 1:
                    continue
                fragments = [words[e.source_index] for e in held]
                fit = metric.recover(held,fragments)
                if fit is None:
                    continue
                text,x,sx,sy,an = fit
                body = render_merged_caption(held,fragments,text,animated=False,an=an,
                    pos=(x,statistics.median(positions[e.source_index][1] for e in held)),fscx=sx,fscy=sy)
                if body is None:
                    continue
                ids = frozenset(m.source_index for e,p in cue for m in p[1])
                if len(ids) != sum(len(p[1]) for e,p in cue):
                    continue
                start,end = min(p[2] for e,p in cue),max(e.end_s for e,p in cue)
                core = (min(p[3] for e,p in cue),max(p[3] for e,p in cue))
                if not start < core[0] < core[1] < end:
                    continue
                first = min(held,key=lambda e:e.source_index)
                caption = replace_event(first,text=body,start=format_time(start),start_s=start,
                    end=format_time(end),end_s=end,source_index=min(ids))
                row = TextRow(caption,[(e,words[e.source_index],positions[e.source_index]) for e in held],
                              phase_core=core)
                proposals.append((ids,row,text))
    # An unmatched nearby fragment may be a missing part of this cue. Do not
    # turn a failed boundary or font match into a partial reconstructed line.
    # Other complete proposals are known neighbouring cues, not missing text.
    proposed_ids = set().union(*(ids for ids,row,text in proposals)) if proposals else set()
    blockers = {}
    for e in eligible:
        if e.source_index not in proposed_ids:
            key = (e.style,placement_key(e),round(positions[e.source_index][1],4))
            blockers.setdefault(key,[]).append(e)
    complete = []
    for ids,row,text in proposals:
        e = row.pieces[0][0]
        key = (e.style,placement_key(e),round(row.pieces[0][2][1],4))
        xs = [pos[0] for piece,word,pos in row.pieces]
        start,end = row.phase_core
        reach = 2*min(text_height(piece) for piece,word,pos in row.pieces)
        if not any(min(xs)-reach <= positions[p.source_index][0] <= max(xs)+reach and
                   min(end,p.end_s)-max(start,p.start_s) >= .5*min(end-start,p.duration)
                   for p in blockers.get(key,[])):
            complete.append((ids,row,text))
    # A phase belongs to exactly one complete caption; no greedy ownership.
    unique = {ids:(row,text) for ids,row,text in complete}
    claims = {}
    for ids in unique:
        for index in ids:
            claims[index] = claims.get(index,0)+1
    accepted = [(ids,row,text) for ids,(row,text) in unique.items()
                if all(claims[index] == 1 for index in ids)]
    consumed = set().union(*(ids for ids,row,text in accepted)) if accepted else set()
    rows = [row for ids,row,text in accepted]
    for ids,row,text in accepted:
        visible_map[row.base.source_index] = text
        metric.merged += 1
    output = [e for e in events if e.source_index not in consumed]+[row.base for row in rows]
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output),rows


def reconstruct_text_rows(events: list[Event], visible_map: dict[int,str],
                          space_map: dict[tuple,set[float]],
                          font_spacing: FontSpacing | None,
                          animated_sources: set[int],
                          source_rows: list[TextRow] | None = None,
                          source_only: bool = False, *,
                          static_only: bool = False,
                          source_events: dict[int,Event] | None = None) -> tuple[list[Event],int,int,list[TextRow]]:
    """Reconstruct static and animated rows with shared evidence and rendering.

    Static rows share effective styling and equal timing. A timing fallback
    also accepts equal-paint fragments sharing 80% of their complete interval,
    with exact-font spacing evidence. Longer sweeps require animation evidence
    for every fragment, monotonic starts and ends, and overlapping visibility.
    A chain without a common interval also requires exact-font spacing recovery.
    Spaces come from authored
    text, explicit blank positions, or measured advances in the exact font.
    Persistent matching row neighbors cannot occupy gaps between fragments.
    If spacing is unproven, preserve the original fragment positions and timing.
    The final static-only pass assembles equal-time, equal-paint fragments;
    it neither extends lifetimes nor chooses between different paint copies.
    """
    source_rows = [row for row in (source_rows or []) if row.confirmed and not static_only]
    if source_only:
        # The normal reconstruction stage owns paint for both positioned
        # fragments and assembled lines. Source cues retain their exact timing.
        normalized = {}
        for row in source_rows:
            paint = max(row.foreground,key=lambda e:(
                int(e.layer) if e.layer.lstrip('-').isdigit() else 0,e.duration))
            state = paint.state or effective_state(paint.text,paint.defaults,paint.styles)
            row.pieces = [(replace_event(e,text=aggressive_caption(
                {**e.state,"1c":state.get("1c","FFFFFF")},text,
                outline_states=[p.state for p in row.foreground if p.state])),text,pos)
                for e,text,pos in row.pieces]
            row.base = row.pieces[0][0]
            normalized.update((e.source_index,e) for e,_,_ in row.pieces)
        return [normalized.get(e.source_index,e) for e in events],0,0,source_rows

    quantum = .011  # ASS times have centisecond precision.
    removed: set[int] = set()
    replacements: dict[int,Event] = {}
    row_evidence: dict[int,TextRow] = {}
    chain_families: set[tuple] = set()
    coextensive_rows: set[int] = set()
    duplicate_count = merged_count = 0

    # Collapse paint copies only at the same position, with matching text,
    # geometry and complete timing. This precedes row reconstruction so that
    # duplicate glyphs cannot become duplicate letters in the assembled text.
    copies: dict[tuple,list[Event]] = {}
    for e in events:
        if (not static_only and e.kind == "Dialogue" and get_pos(e.text) is not None and
                (e.lyric or e.source_index in animated_sources) and
                visible_map.get(e.source_index) and not inline_layout_key(e)):
            key = (e.start,e.end,e.style,e.name,e.row,get_pos(e.text),
                   visible_map[e.source_index],text_layout_key(e),placement_key(e))
            copies.setdefault(key,[]).append(e)
    for group in copies.values():
        if len(group) < 2:
            continue
        chosen = min(group,key=lambda e:(e.state.get("1a",0),
                     -int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
                     -e.source_index))
        removed.update(e.source_index for e in group if e is not chosen)
        duplicate_count += len(group)-1

    eligible = []
    for e in events:
        text = visible_map.get(e.source_index, "")
        if (e.source_index in removed or e.kind != "Dialogue" or not text or
                get_pos(e.text) is None or e.duration <= 0 or e.state.get("p",0) or
                OVERRIDE_RE.search(e.text,re.match(r"(?:\{[^}]*\})*",e.text).end()) or
                "clip" in e.state or "iclip" in e.state or
                any(tag in e.text for tag in (r"\N",r"\n")) or
                any(abs(e.state.get(tag,0)) > .001
                    for tag in ("frz","frx","fry","fax","fay"))):
            continue
        eligible.append(e)

    def base_key(e):
        return (e.style,e.name,e.row,e.margin_l,e.margin_r,e.margin_v,
                tuple((k,v) for k,v in text_layout_key(e)
                      if k not in {"fscx","fscy","u","s"}))

    # Keep original glyph anchors as evidence even after an earlier merge.
    # Position and start-time indexes bound checks to nearby row neighbors.
    neighbors = {}
    for e in eligible:
        px,py = get_pos(e.text)
        neighbors.setdefault(base_key(e),[]).append((e,px,py,text_height(e)))
    for key,group in neighbors.items():
        spatial = sorted(group,key=lambda item:item[1])
        temporal = sorted(group,key=lambda item:item[0].start_s)
        neighbors[key] = (([px for e,px,py,height in spatial],spatial),
                          ([e.start_s for e,px,py,height in temporal],temporal))

    comments: dict[str,list[tuple[Event,str]]] = {}
    for e in events:
        if e.kind == "Comment":
            comments.setdefault(e.style,[]).append((e,simplify_text(e.text,visible_only=True)[1]))

    def occupied_gap(ordered: list[Event], start: float, end: float, *,
                     complete_row: bool = False) -> bool:
        # Font advances cannot distinguish real spaces from omitted letters.
        # Persistent matching row neighbors must belong to the candidate row.
        xs = [get_pos(e.text)[0] for e in ordered]
        y = statistics.median(get_pos(e.text)[1] for e in ordered)
        tolerance = min(e.unit for e in ordered)
        height = min(text_height(e) for e in ordered)
        members = {e.source_index for e in ordered}
        (positions,spatial),(starts,temporal) = neighbors[base_key(ordered[0])]
        reach = 2*height if complete_row else 0
        left,right = ((bisect_left(positions,xs[0]-reach),bisect_right(positions,xs[-1]+reach))
                      if complete_row else
                      (bisect_right(positions,xs[0]+tolerance),bisect_left(positions,xs[-1]-tolerance)))
        # Mutual 50% overlap implies a nearby start. These broad bounds keep
        # past/future cues out before the exact lifetime and geometry checks.
        early,late = bisect_left(starts,start-(end-start)),bisect_left(starts,end)
        peers,begin,stop = ((spatial,left,right) if right-left <= late-early else
                            (temporal,early,late))
        for index in range(begin,stop):
            peer,px,py,peer_height = peers[index]
            if (peer.source_index in members or abs(py-y) > .15*min(height,peer_height) or
                    min(peer.end_s,end)-max(peer.start_s,start) < .5*max(peer.duration,end-start)):
                continue
            gap = bisect_left(xs,px)
            if 0 < gap < len(xs) and xs[gap-1]+tolerance < px < xs[gap]-tolerance:
                return True
            # Timing similarity can select only the middle of a longer row.
            # Near-coextensive candidates need the nearby edge glyphs too;
            # otherwise their partial model could falsely identify a new cue.
            if complete_row and (xs[0]-2*min(height,peer_height) <= px <= xs[0]+tolerance or
                                 xs[-1]-tolerance <= px <= xs[-1]+2*min(height,peer_height)):
                return True
        return False

    # A stationary letter can be shared by successive captions at the same
    # anchor. Equal-time grouping alone sees a hole in both rows. Reconstruct
    # complete rows with an unambiguous exact-font fit, and consume a shared
    # letter only when the proven captions cover its entire original lifetime.
    # Authored text, when available, must agree with the recovered word gaps.
    # No cue is extended and unclaimed portions of a held label cannot vanish.
    if font_spacing is not None and not static_only:
        families = {}
        for e in eligible:
            if (e.lyric and e.source_index not in animated_sources and e.state.get('1a',0) == 0 and
                    len(visible_map[e.source_index]) == 1 and
                    static_object_key(e,e.styles) is not None):
                key = (base_key(e),e.layer,state_key(e,{'pos'}))
                families.setdefault(key,[]).append(e)
        for family in families.values():
            family.sort(key=lambda e:e.start_s)
            starts = [e.start_s for e in family]
            latest = []
            for e in family:
                latest.append(max(latest[-1] if latest else -math.inf,e.end_s))
            cues = {}
            for e in family:
                cues.setdefault((e.start_s,e.end_s),[]).append(e)
            proposals = []
            for (start,end),seed in cues.items():
                if len(seed) < 2:
                    continue
                seed_ids = {e.source_index for e in seed}
                shared = [e for e in family[bisect_left(latest,end):bisect_right(starts,start)]
                          if e.source_index not in seed_ids and e.end_s >= end]
                if not shared:
                    continue
                ordered = sorted(seed+shared,key=lambda e:get_pos(e.text)[0])
                xs = [get_pos(e.text)[0] for e in ordered]
                ys = [get_pos(e.text)[1] for e in ordered]
                if (any(b-a <= min(e.unit for e in ordered) for a,b in zip(xs,xs[1:])) or
                        max(ys)-min(ys) > .15*min(text_height(e) for e in ordered)):
                    continue
                fragments = [visible_map[e.source_index] for e in ordered]
                literal = ''.join(fragments)
                authored = {text for comment,text in comments.get(seed[0].style,[]) if
                            ''.join(text.split()) == literal and
                            min(comment.end_s,end)-max(comment.start_s,start) >=
                            .8*max(comment.duration,end-start)}
                if len(authored) > 1:
                    continue
                if not authored and (occupied_gap(ordered,start,end) or any(
                        comment.name == seed[0].name and text and
                        min(comment.end_s,end)-max(comment.start_s,start) >=
                        .8*max(comment.duration,end-start)
                        for comment,text in comments.get(seed[0].style,[]))):
                    continue
                fit = font_spacing.recover(ordered,fragments)
                if fit is None:
                    continue
                text = next(iter(authored)) if authored else fit[0]
                if fit[0].split() != text.split():
                    continue
                _,x,sx,sy,alignment = fit
                body = render_merged_caption(ordered,fragments,text,animated=False,
                    an=alignment,pos=(x,statistics.median(ys)),fscx=sx,fscy=sy)
                if body is not None:
                    proposals.append((seed,shared,ordered,body,text,bool(authored)))
            # Reject the connected proposal set if any shared member has an
            # uncovered interval, including a failed or missing adjacent cue.
            shared_ids = {e.source_index:e for _,shared,_,_,_,_ in proposals for e in shared}
            # Without authored row evidence, the fitted cues must also be
            # disjoint: an overlap would draw the held letter more than once.
            measured_ids = {e.source_index for _,shared,_,_,_,authored in proposals
                            if not authored for e in shared}
            if set(shared_ids) & {e.source_index for seed,_,_,_,_,_ in proposals for e in seed}:
                continue
            valid = bool(proposals)
            for index,e in shared_ids.items():
                intervals = sorted((seed[0].start_s,seed[0].end_s)
                                   for seed,shared,ordered,body,text,authored in proposals
                                   if any(p.source_index == index for p in ordered))
                covered = e.start_s
                for start,end in intervals:
                    if (start > covered+.001 or
                            index in measured_ids and start < covered-.001):
                        valid = False; break
                    covered = max(covered,end)
                if covered < e.end_s-.001:
                    valid = False
            if not valid:
                continue
            for seed,shared,ordered,body,text,authored in proposals:
                first = min(seed,key=lambda e:e.source_index)
                pieces = [(e,visible_map[e.source_index],get_pos(e.text)) for e in ordered]
                replacements[first.source_index] = replace_event(first,text=body,effect='')
                visible_map[first.source_index] = text
                row_evidence[first.source_index] = TextRow(replacements[first.source_index],
                    pieces)
                before = len(removed)
                removed.update(e.source_index for e in ordered if e is not first)
                merged_count += len(removed)-before
                font_spacing.merged += 1

    def join(run: list[Event], animated: bool, *, coextensive: bool = False) -> bool:
        nonlocal merged_count
        if len(run) < 2 or any(e.source_index in removed or
                              e.source_index in replacements for e in run):
            return False
        ordered = sorted(run,key=lambda e:get_pos(e.text)[0])
        xs = [get_pos(e.text)[0] for e in ordered]
        ys = [get_pos(e.text)[1] for e in ordered]
        tolerance = min(e.unit for e in run)
        height = min(text_height(e) for e in run)
        if (any(b-a <= tolerance for a,b in zip(xs,xs[1:])) or
                max(ys)-min(ys) > .15*height):
            return False
        start,end = min(e.start_s for e in run),max(e.end_s for e in run)
        shared_interval = min(e.end_s for e in run)-max(e.start_s for e in run) > quantum
        if coextensive and (len(run) < 4 or
                min(e.end_s for e in run)-max(e.start_s for e in run) < .8*(end-start)-1e-6 or
                any(e.layer != run[0].layer or e.state.get('1a',0) != 0 or
                    base_key(e) != base_key(run[0]) or
                    state_key(e,{'pos'}) != state_key(run[0],{'pos'}) for e in run)):
            return False
        if animated:
            # Span decoration can vary; font metrics and paragraph geometry
            # must agree even when a proven source row bypasses grouping.
            reference = base_key(run[0])
            if (any(base_key(e) != reference for e in run) or
                    not all(e.source_index in animated_sources for e in run) or
                    any(min(a.end_s,b.end_s)-max(a.start_s,b.start_s) <= quantum
                        for a,b in zip(ordered,ordered[1:])) or
                    not any(all(direction*(b.start_s-a.start_s) >= -quantum and
                                    direction*(b.end_s-a.end_s) >= -quantum
                                    for a,b in zip(ordered,ordered[1:]))
                            for direction in (1,-1))):
                return False
        y = statistics.median(ys)
        if occupied_gap(ordered,start,end,complete_row=coextensive):
            return False
        fragments = [visible_map[e.source_index] for e in ordered]
        norm = lambda value: "".join(value.split())
        authored = {words for comment,words in comments.get(run[0].style,[])
                    if min(comment.end_s,end)-max(comment.start_s,start) >=
                       .8*max(comment.duration,end-start) and
                       norm(words) == norm("".join(fragments))}
        text = next(iter(authored)) if len(authored) == 1 else None
        x = (xs[0]+xs[-1])/2
        # Keep the authored vertical band when centering a combined row.
        alignment = ((int(ordered[0].state.get('an',5))-1)//3)*3+2
        sx = statistics.median(e.state.get("fscx",100) for e in run)
        sy = statistics.median(e.state.get("fscy",100) for e in run)
        if text is None:
            blanks = space_map.get((format_time(start),format_time(end),
                                    run[0].style,run[0].name,run[0].row),set())
            if blanks:
                text = fragments[0]+"".join(
                    (" " if any(a < space < b for space in blanks) else "")+part
                    for a,b,part in zip(xs,xs[1:],fragments[1:]))
        measured = False
        tracking = None
        expected_text = text
        if (text is None or coextensive) and font_spacing is not None:
            # Karaoke pulses can leave different sampled scales per glyph.
            # Animated rows share their median scale; static rows are exact.
            metric_row = [dataclass_replace(e,state={**e.state,"fscx":sx,"fscy":sy})
                          for e in ordered] if animated else ordered
            if abs(metric_row[0].state.get('fsp',0)) > .001:
                fit = font_spacing.recover_tracked(metric_row,fragments)
                if fit is not None:
                    text,x,sx,sy,alignment,tracking = fit
            else:
                fit = font_spacing.recover(metric_row,fragments)
                if fit is not None:
                    text,x,sx,sy,alignment = fit
            if fit is not None:
                measured = True
            elif all(unicodedata.category(c) == "Lo" and
                     unicodedata.east_asian_width(c) in ("W","F")
                     for part in fragments for c in part):
                fit = font_spacing.fit_fullwidth_run(metric_row,fragments)
                if fit is not None:
                    x,sx = fit
                    text = "".join(fragments)
                    alignment = int(ordered[0].state.get("an",5))
                    measured = True
        if coextensive and (not measured or expected_text is not None and
                            expected_text.split() != text.split()):
            return False
        if text is None or animated and not shared_interval and not measured:
            return False
        chosen = ordered[0]
        body = render_merged_caption(ordered,fragments,text,animated=animated,
                                     an=alignment,pos=(x,y),fscx=sx,fscy=sy,fsp=tracking)
        if body is None:
            return False
        first = min(e.source_index for e in run)
        # Preserve the visible shadow-painted foreground above independent
        # decorative glyphs. Other animation reducers retain their established
        # layer normalization; their phase/echo matching relies on that order.
        layer = (chosen.layer if not animated or all(animated_shadow_painted_source(
            e,source_events,animated_sources) for e in run) else '0')
        replacements[first] = replace_event(chosen,source_index=first,
            start=format_time(start),end=format_time(end),start_s=start,end_s=end,
            text=body,effect="",layer=layer)
        visible_map[first] = text
        row_evidence[first] = TextRow(replacements[first],
            [(e,text,(x,y)) for e,text,x,y in zip(ordered,fragments,xs,ys)])
        if animated and not shared_interval:
            chain_families.add(base_key(ordered[0]))
        if coextensive:
            coextensive_rows.add(first)
        removed.update(e.source_index for e in run if e.source_index != first)
        merged_count += len(run)-1
        if measured:
            font_spacing.merged += 1
        return True

    # Reuse proven source rows, without redetecting their original fragments.
    current = {e.source_index:e for e in eligible}
    protected = set()
    for row in source_rows:
        run = [current[e.source_index] for e,_,_ in row.pieces if e.source_index in current]
        if (len(run) == len(row.pieces) and all(
                e.start == row.base.start and e.end == row.base.end for e in run)):
            protected.update(e.source_index for e in run)
            if not join(run,all(e.source_index in animated_sources for e in run)):
                idx = -1-sum(r.virtual for r in row_evidence.values())
                xs = [pos[0] for _,_,pos in row.pieces]
                ys = [pos[1] for _,_,pos in row.pieces]
                base = replace_event(run[0],source_index=idx,
                    text=set_pos(run[0].text,((xs[0]+xs[-1])/2,statistics.median(ys))))
                row_evidence[idx] = TextRow(base,
                    [(e,text,pos) for e,(_,text,pos) in zip(run,row.pieces)],virtual=True)

    # Animated candidates are tried as complete sweeps before equal-time
    # subsets, so a syllable is not prematurely assembled into a separate word.
    sweeps: dict[tuple,list[Event]] = {}
    for e in eligible:
        if (not static_only and e.source_index in animated_sources and
                e.source_index not in protected):
            sweeps.setdefault(base_key(e),[]).append(e)
    candidates = []
    for bucket in sweeps.values():
        for direction in (1,-1):
            ordered = sorted(bucket,key=lambda e:(e.start_s,direction*get_pos(e.text)[0]))
            # Keep shared-interval candidates as fallbacks when a longer chain
            # has no unambiguous font fit. Both use the same trajectory rules.
            for shared in ((True,False) if font_spacing is not None else (True,)):
                run = []
                for e in ordered:
                    if run and (direction*(get_pos(e.text)[0]-get_pos(run[-1].text)[0]) <= e.unit or
                                e.end_s < run[-1].end_s-quantum or
                                e.start_s >= (min(p.end_s for p in run) if shared else run[-1].end_s)-quantum or
                                abs(get_pos(e.text)[1]-get_pos(run[0].text)[1]) >
                                .15*min(text_height(e),text_height(run[0]))):
                        candidates.append(run)
                        run = []
                    run.append(e)
                candidates.append(run)
    for run in sorted(candidates,key=lambda run:-len(run)):
        join(run,True)

    # A centre-outward or irregular entrance need not be a directional sweep.
    # Index near-coextensive equal-paint peers directly; never grow a cue by
    # chaining pairwise overlaps. The 25% seed window is a search bound: the
    # completed row must still share 80% of its entire union interval in join.
    # Conflicting candidate memberships stay separate, and occupied_gap checks
    # all original neighbors so a missing letter cannot become inferred space.
    if font_spacing is not None and getattr(font_spacing,'available',False) and not static_only:
        holds = {}
        for e in eligible:
            if (e.source_index not in protected and e.source_index not in removed and
                    e.source_index not in replacements and e.state.get('1a',0) == 0):
                holds.setdefault((base_key(e),e.layer,state_key(e,{'pos'})),[]).append(e)
        proposals = {}
        for bucket in holds.values():
            bucket.sort(key=lambda e:e.start_s)
            starts = [e.start_s for e in bucket]
            seeds = {(e.start_s,e.end_s,get_pos(e.text)[1]):e for e in bucket}
            for seed in seeds.values():
                window = .25*seed.duration
                row = [e for e in bucket[bisect_left(starts,seed.start_s-window):
                                        bisect_right(starts,seed.start_s+window)]
                       if abs(e.end_s-seed.end_s) <= window and
                          abs(get_pos(e.text)[1]-get_pos(seed.text)[1]) <=
                          .15*min(text_height(e),text_height(seed))]
                if len(row) < 4 or len({(e.start,e.end) for e in row}) == 1:
                    continue
                start,end = min(e.start_s for e in row),max(e.end_s for e in row)
                if min(e.end_s for e in row)-max(e.start_s for e in row) >= .8*(end-start)-1e-6:
                    proposals.setdefault(frozenset(e.source_index for e in row),row)
        owners = {}
        for members in proposals:
            for index in members:
                owners[index] = owners.get(index,0)+1
        for members,row in proposals.items():
            if all(owners[index] == 1 for index in members):
                join(row,False,coextensive=True)

    simultaneous: dict[tuple,list[Event]] = {}
    for e in eligible:
        if (e.source_index not in removed and e.source_index not in replacements and
                e.source_index not in protected):
            key = (base_key(e),e.start,e.end,e.layer,state_key(e,{"pos"}))
            simultaneous.setdefault(key,[]).append(e)
    for run in simultaneous.values():
        join(run,False)
    # Rolling rows may retain late syllables while the next row enters from
    # the left. Once each row is a complete caption, those tails would draw
    # whole sentences over each other. End proven chains at the next row,
    # only after every fragment has appeared and the caption spans overlap.
    sequences = {}
    for index,row in row_evidence.items():
        key = base_key(row.pieces[0][0])
        if not row.virtual and (key in chain_families or index in coextensive_rows):
            xs = [pos[0] for piece,word,pos in row.pieces]
            sequences.setdefault(key,[]).append((index,row,min(xs),max(xs),
                max(piece.start_s for piece,word,pos in row.pieces)))
    for sequence in sequences.values():
        sequence.sort(key=lambda item:item[1].base.start_s)
        for offset,(index,row,left,right,last_start) in enumerate(sequence):
            for other in range(offset+1,len(sequence)):
                _,peer,peer_left,peer_right,_ = sequence[other]
                if peer.base.start_s >= row.base.end_s:
                    break
                overlap = min(right,peer_right)-max(left,peer_left)
                if (peer.base.start_s > last_start+quantum and
                        overlap > .5*min(right-left,peer_right-peer_left)):
                    # A near-coextensive row may have a staggered exit tail.
                    # Trim only inside its same 20% boundary budget, after
                    # every original fragment has appeared. Other rows retain
                    # the established rolling-sweep timing rule.
                    if (index in coextensive_rows and
                            row.base.end_s-peer.base.start_s > .2*row.base.duration+quantum):
                        continue
                    end = peer.base.start_s
                    row.base = replace_event(row.base,end=format_time(end),end_s=end)
                    replacements[index] = row.base
                    break
    output = [replacements.get(e.source_index,e) for e in events if e.source_index not in removed]
    if static_only:
        return output,merged_count,duplicate_count,list(row_evidence.values())
    # Record unassembled rows here too. These models supply shadow-copy
    # evidence without requiring fonts or emitting inferred word spacing.
    fragments: dict[tuple,list[Event]] = {}
    for e in output:
        if (e.kind == "Dialogue" and e.source_index not in row_evidence and
                e.source_index not in protected and
                (e.lyric or e.source_index in animated_sources) and
                visible_map.get(e.source_index) and get_pos(e.text) is not None and
                not e.state.get("p",0) and not inline_layout_key(e) and
                "clip" not in e.state and "iclip" not in e.state and
                e.state.get("1a",0) == 0):
            key = (e.style,e.name,e.row,e.start,e.end,text_layout_key(e))
            fragments.setdefault(key,[]).append(e)
    virtual_count = sum(row.virtual for row in row_evidence.values())
    for group in fragments.values():
        runs = []
        for e in sorted(group,key=lambda e:get_pos(e.text)[0]):
            if not runs or (get_pos(e.text)[0]-get_pos(runs[-1][-1].text)[0] >
                            2*min(text_height(e),text_height(runs[-1][-1]))):
                runs.append([])
            runs[-1].append(e)
        for ordered in runs:
            if len(ordered) < 2:
                continue
            xs = [get_pos(e.text)[0] for e in ordered]
            ys = [get_pos(e.text)[1] for e in ordered]
            height = min(text_height(e) for e in ordered)
            if (any(b-a <= ordered[0].unit for a,b in zip(xs,xs[1:])) or
                    max(ys)-min(ys) > .15*height):
                continue
            idx = -virtual_count-1
            base = replace_event(ordered[0],source_index=idx,
                text=set_pos(ordered[0].text,((xs[0]+xs[-1])/2,statistics.median(ys))))
            row_evidence[idx] = TextRow(base,[(e,visible_map[e.source_index],(x,y))
                                            for e,x,y in zip(ordered,xs,ys)],virtual=True)
            virtual_count += 1
    return output,merged_count,duplicate_count,list(row_evidence.values())


def match_translucent_glyph_particles(events: list[Event], row_evidence: list[TextRow],
                                      words: dict[int,str],
                                      animated_sources: set[int]) -> set[int]:
    """Prove dense, complete particle phases behind an opaque source row.

    Match original movement endpoints to authored glyph anchors, without font
    substitution or sampled geometry. Each repeated phase must cover every
    glyph exactly once; incomplete or multiply owned families remain intact.
    This matcher returns membership only and never changes foreground rows.
    """
    if not events or not row_evidence:
        return set()
    buckets = {}
    identity = lambda e: (e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
    geometry = {key for key,_ in text_layout_key(row_evidence[0].base)}
    varying = {"fscx","fscy","frz","frx","fry"}
    paint = {"alpha","1a","2a","3a","4a","c","1c","2c","3c","4c","blur","be"}
    for e in events:
        word = words.get(e.source_index,"")
        if (e.kind != "Dialogue" or e.source_index not in animated_sources or
                len(word) != 1 or word.isspace() or e.duration <= 0 or
                not e.layer.lstrip('-').isdigit() or inline_layout_key(e)):
            continue
        tags = [item for block in OVERRIDE_RE.findall(e.text)
                for item in tokenize_override(block)]
        moves = [value for tag,value in tags if tag == "move"]
        if (len(moves) != 1 or any(tag not in geometry|paint|{"move","fad","t"}
                                   for tag,value in tags)):
            continue
        try:
            move = tuple(float(v.strip()) for v in moves[0][1:-1].split(','))
        except ValueError:
            continue
        if (len(move) not in (4,6) or not all(math.isfinite(v) for v in move) or
                len(move) == 6 and not 0 <= move[4] <= move[5] <= 1000*e.duration):
            continue
        state = effective_state(e.text,e.defaults,e.styles)
        final = state.copy()
        states = [state]
        safe = True
        for tag,value in tags:
            if tag != "t":
                continue
            for name,argument in tokenize_override(value[1:-1]):
                if name not in varying|paint:
                    safe = False
                    break
                apply_tag(final,name,argument,e.styles,e.defaults)
                states.append(final.copy())
        if (not safe or state.get("blur",0) <= 0 or
                any(min(s.get(k,0) for k in ("1a","3a","4a")) < 128 for s in states)):
            continue
        buckets.setdefault(identity(e),[]).append((e,word,move,state,states))
    for key,group in buckets.items():
        group.sort(key=lambda item:item[0].start_s)
        buckets[key] = ([item[0].start_s for item in group],group)

    families = []
    for row in row_evidence:
        if row.virtual or len(row.pieces) < 4:
            continue
        first = row.base
        foreground = [piece for piece,word,pos in row.pieces]
        if (first.duration <= 0 or any(len(word) != 1 or word.isspace() or
                piece.start != first.start or piece.end != first.end or
                piece.state.get("1a",0) != 0 or
                not piece.layer.lstrip('-').isdigit() or
                piece.source_index in animated_sources for piece,word,pos in row.pieces)):
            continue
        index = buckets.get(identity(first))
        if index is None:
            continue
        starts,group = index
        height = min(text_height(piece) for piece in foreground)
        radius = .25*height
        foreground_layer = min(int(piece.layer) for piece in foreground)
        phases = {}
        for e,word,move,state,states in group[
                bisect_left(starts,first.start_s-.25*first.duration):
                bisect_right(starts,first.end_s+.25*first.duration)]:
            if (e.duration > .25*first.duration or
                    e.end_s > first.end_s+.25*first.duration or
                    int(e.layer) >= foreground_layer):
                continue
            matches = []
            for glyph,(piece,text,pos) in enumerate(row.pieces):
                if (word != text or math.dist(move[:2],pos) > radius or
                        math.dist(move[2:4],pos) > radius or
                        any((str(state.get(k,"")).casefold() != str(piece.state.get(k,"")).casefold()
                             if k == "fn" else state.get(k) != piece.state.get(k))
                            for k in geometry) or
                        any(not .5*piece.state.get(k,100) <= s.get(k,100) <=
                                2*piece.state.get(k,100)
                            for s in states for k in ("fscx","fscy"))):
                    continue
                matches.append(glyph)
            if len(matches) == 1:
                phases.setdefault((e.layer,e.start,e.end),[]).append((matches[0],e))
        if (len(phases) < 3 or any(len(phase) != len(row.pieces) or
                len({glyph for glyph,e in phase}) != len(row.pieces) for phase in phases.values())):
            continue
        peers = [e for phase in phases.values() for glyph,e in phase]
        if max(e.end_s for e in peers)-min(e.start_s for e in peers) < .5*first.duration:
            continue
        families.append({e.source_index for e in peers})
    owners = {}
    for family in families:
        for index in family:
            owners[index] = owners.get(index,0)+1
    return set().union(*(family for family in families if all(owners[index] == 1 for index in family)))


def collapse_backed_glyph_pulses(events: list[Event], words: dict[int,str],
                                  positions: dict[int,tuple[float,float] | None]) -> tuple[list[Event],int]:
    """Freeze complete glyph rows proven by a continuous stationary backing.

    A translucent copy supplies exact anchors and cue bounds. Every glyph
    needs an opaque held foreground pose and uninterrupted foreground coverage.
    Colour and size pulses must return to that shared pose; frame jitter must
    converge to it. Pulse magnitude is unrestricted, but sizes must remain
    finite, positive and unflipped. Partial rows, gradients, ambiguous copies
    and moving labels stay.
    Text spacing remains the responsibility of the existing row reconstruction.
    """
    allowed = {'c','1c','3c','4c','alpha','1a','3a','4a','blur','be','fscx','fscy'}
    indexed, backing = {}, {}
    details = {}
    for e in events:
        word,pos = words.get(e.source_index,''),positions.get(e.source_index)
        if (e.kind != 'Dialogue' or len(word) != 1 or word.isspace() or
                unicodedata.combining(word) or pos is None or e.duration <= 0 or
                not e.layer.lstrip('-').isdigit() or inline_layout_key(e)):
            continue
        state = e.state or effective_state(e.text,e.defaults,e.styles)
        if (not all(math.isfinite(v) for v in pos) or
                any(not math.isfinite(state.get(k,0)) or state.get(k,0) <= 0
                    for k in ('fs','fscx','fscy')) or
                state.get('p',0) or state.get('borderstyle',1) != 1 or
                any(k in state for k in ('clip','iclip','org')) or
                any(abs(state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay')) or
                any(abs(state.get(k,state.get('shad',0))) > .001 for k in ('xshad','yshad'))):
            continue
        tokens = event_override_tokens(e)
        if any(tag in {'move','fade','k','kf','ko'} for tag,value in tokens):
            continue
        transforms = []
        safe = True
        final = state.copy()
        for tag,value in tokens:
            if tag == 't':
                transform = parse_effect_transform(value,e.duration,allowed)
                if transform is None:
                    safe = False; break
                begin,end,changes = transform
                for name,argument in changes:
                    apply_tag(final,name,argument,e.styles,e.defaults)
                transforms.append((begin,end,final.copy()))
        if not safe:
            continue
        fades = [value for tag,value in tokens if tag == 'fad']
        try:
            fade = tuple(float(v) for v in fades[0].strip('()').split(',')) if fades else (0,0)
        except ValueError:
            continue
        if (len(fades) > 1 or len(fade) != 2 or
                not all(math.isfinite(v) and v >= 0 for v in fade)):
            continue
        sample = dataclass_replace(e,state=state)
        layout = tuple((k,v) for k,v in text_layout_key(sample) if k not in {'fscx','fscy'})
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,layout)
        details[e.source_index] = (state,transforms,fade)
        indexed.setdefault(key,[]).append(e)
        if (0 < state.get('1a',0) < 255 and
                all(final.get('1c') == state.get('1c') and 0 < final.get('1a',0) < 255
                    for _,_,final in transforms)):
            backing.setdefault((key,e.layer,pos,word,state.get('1c')),[]).append(e)

    rows = {}
    for (key,layer,pos,word,colour),phases in backing.items():
        phases.sort(key=lambda e:(e.start_s,e.end_s,e.source_index))
        runs = []
        for e in phases:
            if not runs or abs(runs[-1][-1].end_s-e.start_s) > .011:
                runs.append([])
            runs[-1].append(e)
        for run in runs:
            if run[-1].end_s-run[0].start_s > .25:
                rows.setdefault((key,layer,run[0].start_s,run[-1].end_s,pos[1]),[]).append(
                    (pos,word,run))

    def pose(state: dict) -> tuple:
        return tuple(state.get(k,DEFAULT_STATE.get(k)) for k in
                     ('1c','3c','bord','xbord','ybord','fscx','fscy'))

    def converges(frames: list[Event], base: dict, *, clipped: bool = False) -> bool:
        distances = []
        for frame in frames:
            state = details[frame.source_index][0]
            if any(state.get(k,DEFAULT_STATE.get(k)) != base.get(k,DEFAULT_STATE.get(k))
                   for k in ('3c','bord','xbord','ybord')):
                return False
            distances.append((sum(abs(int(state['1c'][i:i+2],16)-
                                      int(base['1c'][i:i+2],16)) for i in (0,2,4)),
                              abs(state.get('fscx',100)-base.get('fscx',100)),
                              abs(state.get('fscy',100)-base.get('fscy',100))))
        if any(any(b > a+.02 for a,b in zip(left,right))
               for left,right in zip(distances,distances[1:])):
            return False
        # A pulse cut short by the recorded cue boundary still needs a
        # substantial return toward a pose held elsewhere in this glyph's cue.
        return (not clipped or len(frames) >= 2 and any(distances[0]) and
                all(b <= .5*a+.02 for a,b in zip(distances[0],distances[-1])))

    proposals = []
    for (key,layer,start,end,y),row in rows.items():
        row.sort(key=lambda item:item[0][0])
        if len(row) < 4 or len({pos[0] for pos,word,run in row}) != len(row):
            continue
        glyphs,common = [], None
        for pos,word,run in row:
            height = text_height(dataclass_replace(run[0],state=details[run[0].source_index][0]))
            peers = [e for e in indexed[key] if words[e.source_index] == word and
                     int(e.layer) > int(layer) and e.start_s >= start-.001 and
                     e.end_s <= end+.001 and math.dist(positions[e.source_index],pos) <= .12*height]
            holds = {}
            for e in peers:
                state,transforms,fade = details[e.source_index]
                if (not transforms and fade == (0,0) and state.get('1a',0) == 0 and
                        e.duration >= .02 and math.dist(positions[e.source_index],pos) <= e.unit):
                    holds.setdefault(pose(state),[]).append(e)
            common = set(holds) if common is None else common & set(holds)
            glyphs.append((pos,word,run,peers,holds,height))
        if not common:
            continue
        if any(sum(words[e.source_index] == word and
                   math.dist(positions[e.source_index],pos) <= .12*height
                   for pos,word,run,peers,holds,height in glyphs) != 1
               for *_,peers,holds,height in glyphs for e in peers):
            continue
        height = min(glyph[-1] for glyph in glyphs)
        if any(e.start_s < end and e.end_s > start and
               min(e.end_s,end)-max(e.start_s,start) > .02 and
               row[0][0][0]-height <= positions[e.source_index][0] <= row[-1][0][0]+height and
               abs(positions[e.source_index][1]-y) <= .12*height and
               int(e.layer) >= int(layer) and
               not any(words[e.source_index] == word and
                       math.dist(positions[e.source_index],pos) <= .12*height
                       for pos,word,run in row)
               for e in indexed[key]):
            continue
        ranked = sorted(common,key=lambda p:-sum(sum(e.duration for e in holds[p])
                                                 for *_,holds,height in glyphs))
        target = ranked[0]
        # Two similarly sustained common paints do not identify a base pose.
        scores = [sum(sum(e.duration for e in holds[p]) for *_,holds,height in glyphs)
                  for p in ranked[:2]]
        if len(scores) > 1 and scores[0] < 2*scores[1]:
            continue
        changed,activation,kept,members = 0,[],[],set()
        valid = True
        for pos,word,run,peers,holds,height in glyphs:
            chosen = max(holds[target],key=lambda e:e.duration)
            base = details[chosen.source_index][0]
            # The common opaque hold and return trajectory prove the base
            # size. Large excursions are still pulses; flipped or degenerate
            # sizes cannot establish the same readable pose.
            if any(not math.isfinite(sample.get(k,100)) or sample.get(k,100) <= 0
                   for e in run+peers
                   for sample in [details[e.source_index][0]]+
                                 [final for _,_,final in details[e.source_index][1]]
                   for k in ('fscx','fscy')):
                valid = False; break
            boundaries = sorted({start,end}|{t for e in peers for t in (e.start_s,e.end_s)})
            foreground = []
            for a,b in zip(boundaries,boundaries[1:]):
                covering = [e for e in peers if e.start_s <= a+.001 and e.end_s >= b-.001]
                if not covering:
                    valid = False; break
                top = max(int(e.layer) for e in covering)
                top_events = [e for e in covering if int(e.layer) == top]
                if len(top_events) != 1:
                    valid = False; break
                e = top_events[0]
                if not foreground or foreground[-1] is not e:
                    foreground.append(e)
            if not valid:
                break
            pending = []
            pulse_times = []
            for e in foreground:
                state,transforms,fade = details[e.source_index]
                if state.get('1a',0) != 0:
                    valid = False; break
                if pose(state) == target:
                    if pending:
                        # A frame pulse must approach the held paint and size
                        # monotonically, then return to an exact authored hold.
                        if not converges(pending,base):
                            valid = False; break
                        pending = []
                    if not transforms:
                        continue
                if transforms:
                    if (e.end_s == end and fade[0] == 0 and fade[1] > 0 and
                            state.get('1c') == base.get('1c') and
                            all(final.get('1c') == base.get('1c') for _,_,final in transforms)):
                        continue
                    final = transforms[-1][2]
                    if pose(final) != target or final.get('1a',0) != 0:
                        valid = False; break
                    # Separate colour and size transforms may share a pulse,
                    # but none may introduce another destination or a cycle.
                    for tag,value in event_override_tokens(e):
                        if tag != 't':
                            continue
                        changes = parse_effect_transform(value,e.duration,allowed)[2]
                        for name,argument in changes:
                            sample = base.copy()
                            apply_tag(sample,name,argument,e.styles,e.defaults)
                            if pose(sample) != target or sample.get('1a',0) != 0:
                                valid = False; break
                    if not valid:
                        break
                    if pose(state) != target:
                        pulse_times.append(e.start_s)
                else:
                    if e.duration > .1 or fade != (0,0):
                        valid = False; break
                    pending.append(e)
                    if pose(state) != target:
                        pulse_times.append(e.start_s)
            if pending and pending[-1].end_s == end and converges(pending,base,clipped=True):
                pending = []
            if not valid or pending:
                valid = False; break
            if pulse_times:
                changed += 1;activation.append(min(pulse_times))
            members.update(e.source_index for e in run+peers)
            kept.append(replace_event(chosen,start=format_time(start),end=format_time(end),
                        start_s=start,end_s=end,text=aggressive_caption(base,word,
                        pos=pos,an=int(base.get('an',5))),layer='0'))
        if valid:
            # A simultaneous final colour flash/fade is an exit, not another
            # lyric. Extend only when the complete backing and foreground
            # both fade at every recorded anchor to one shared boundary.
            tails = []
            for pos,word,run,peers,holds,height in glyphs:
                fading = [e for e in indexed[key] if words[e.source_index] == word and
                          e.start_s == end and int(e.layer) >= int(layer) and
                          math.dist(positions[e.source_index],pos) <= e.unit and
                          details[e.source_index][2][0] == 0 and
                          details[e.source_index][2][1] > 0 and
                          details[e.source_index][1] and
                          details[e.source_index][1][-1][2].get('1a',0) >= 254]
                if (not fading or not any(e.layer == layer for e in fading) or
                        not any(int(e.layer) > int(layer) for e in fading)):
                    tails = []; break
                tails.extend(fading)
            if tails and len({e.end for e in tails}) == 1:
                members.update(e.source_index for e in tails)
                finish = tails[0].end_s
                kept = [replace_event(e,end=tails[0].end,end_s=finish) for e in kept]
        if (valid and changed >= 3 and
                (all(a <= b for a,b in zip(activation,activation[1:])) or
                 all(a >= b for a,b in zip(activation,activation[1:])))):
            proposals.append((members,kept))
    owners = {}
    for members,kept in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    removed,replacements = set(),{}
    for members,kept in proposals:
        if any(owners[index] != 1 for index in members):
            continue
        removed.update(members)
        replacements.update((e.source_index,e) for e in kept)
    if not removed:
        return events,0
    output = [replacements.get(e.source_index,e) for e in events
              if e.source_index not in removed or e.source_index in replacements]
    return output,len(events)-len(output)


def collapse_sliced_text_sequences(events: list[Event]) -> tuple[list[Event],int]:
    """Replace a tiled entrance/held-text/exit with its recorded opaque text.

    Adjacent full-width strips must cover the held text's vertical box and
    converge to, or depart from, its exact anchor at touching phase boundaries.
    Both complete strip phases prove the effect. Matching translucent size
    pulses are decoration; unrelated copies and incomplete tiles stay intact.
    """
    candidates = [e for e in events if e.kind == 'Dialogue' and
                re.search(r'\\move\s*\(',e.text,re.I) and
                re.search(r'\\clip\s*\(',e.text,re.I) and
                re.search(r'\\(?:alpha|1a|3a)(?=[^A-Za-z]|$)',e.text,re.I) and
                re.search(r'\\t\s*\(',e.text,re.I)]
    if not candidates:
        return events,0
    # A source family may contain tens of thousands of unrelated effects.
    # Both strip phases must touch a literal held copy; reject impossible
    # families using raw text/times before resolving their override states.
    families = {(e.style,e.name) for e in candidates}
    beginnings = {(e.style,e.name,e.start,OVERRIDE_RE.sub('',e.text)) for e in candidates}
    endings = {(e.style,e.name,e.end,OVERRIDE_RE.sub('',e.text)) for e in candidates}
    eligible = set()
    for e in events:
        if (e.kind != 'Dialogue' or (e.style,e.name) not in families or
                get_pos(e.text) is None or
                re.search(r'\\(?:move|t|clip|iclip|fad|fade)(?=[^A-Za-z]|$)',e.text,re.I)):
            continue
        literal = OVERRIDE_RE.sub('',e.text)
        if ((e.style,e.name,e.start,literal) in endings and
                (e.style,e.name,e.end,literal) in beginnings):
            eligible.add((e.style,e.name))
    families = eligible
    if not families:
        return events,0
    holds, tiles, pulses = {}, {}, {}

    def layout(e: Event, state: dict, *, scaled: bool = False) -> tuple:
        sample = dataclass_replace(e,state=state)
        return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
                tuple((k,v) for k,v in text_layout_key(sample)
                      if not scaled or k not in {'fscx','fscy'}),literal_font_spans(e))

    def paint(state: dict) -> tuple:
        return tuple(state.get(k,DEFAULT_STATE.get(k)) for k in
                     ('1c','3c','1a','3a','bord','xbord','ybord'))

    for e in events:
        if ((e.style,e.name) not in families or e.kind != 'Dialogue' or
                e.duration <= 0 or not e.layer.lstrip('-').isdigit() or
                not OVERRIDE_RE.sub('',e.text).strip() or
                any(tag in e.text for tag in (r'\N',r'\n',r'\h')) or
                literal_font_spans(e) is None):
            continue
        state = effective_state(e.text,e.defaults,e.styles)
        if (state.get('p',0) or state.get('borderstyle',1) != 1 or
                any(k in state for k in ('iclip','org')) or
                any(abs(state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay')) or
                any(abs(state.get(k,state.get('shad',0))) > .001 for k in ('xshad','yshad')) or
                any(not math.isfinite(state.get(k,0)) or state.get(k,0) <= 0
                    for k in ('fs','fscx','fscy'))):
            continue
        p = dataclass_replace(e,state=state)
        tokens = event_override_tokens(p)
        moves = [v for tag,v in tokens if tag == 'move']
        transforms = [v for tag,v in tokens if tag == 't']
        if any(tag in {'fad','fade','k','kf','ko'} for tag,value in tokens):
            continue
        pos = get_pos(e.text)
        key = layout(p,state)
        if (not moves and not transforms and pos is not None and
                opaque_text_effect_state(state) and state.get('3a',0) == 0):
            holds.setdefault((key,e.start,e.end,pos),[]).append(p)
            continue
        if len(transforms) != 1:
            continue
        final = state.copy()
        allowed = {'alpha','1a','3a','blur','be'} | ({'fscx','fscy'} if not moves else set())
        transform = parse_effect_transform(transforms[0],e.duration,allowed)
        if transform is None:
            continue
        for tag,value in transform[2]:
            apply_tag(final,tag,value,e.styles,e.defaults)
        if not moves and pos is not None and 'clip' not in state:
            if (0 < state.get('1a',0) < 254 and final.get('1a',0) >= 254 and
                    max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord')) <= .001):
                pulses.setdefault((layout(p,state,scaled=True),e.start,e.end,pos),[]).append((p,final))
            continue
        rect = rectangle_clip(p)
        if len(moves) != 1 or pos is not None or rect is None:
            continue
        move = parse_effect_move(moves[0],e.duration,endpoint_slack=50)
        if move is None or math.dist(move[:2],move[2:4]) <= e.unit:
            continue
        if (state.get('1a',0) >= 254 and state.get('3a',0) >= 254 and
                final.get('1a',0) == 0 and final.get('3a',0) == 0):
            phase,boundary,anchor,pose = 'in',e.end,tuple(move[2:4]),final
        elif (state.get('1a',0) == 0 and state.get('3a',0) == 0 and
                final.get('1a',0) >= 254 and final.get('3a',0) >= 254):
            phase,boundary,anchor,pose = 'out',e.start,tuple(move[:2]),state
        else:
            continue
        tiles.setdefault((key,phase,boundary,anchor,e.start,e.end,e.layer,paint(pose)),[]).append((p,rect))

    proven = {}
    for (key,phase,boundary,anchor,start,end,layer,colors),peers in tiles.items():
        first = peers[0][0]
        canvas = first.state.get('_canvas')
        peers.sort(key=lambda item:item[1][1])
        if (len(peers) < 3 or canvas is None or
                any(rect[0] != 0 or rect[2] != canvas[0] for e,rect in peers) or
                any(a[1][3] != b[1][1] for a,b in zip(peers,peers[1:]))):
            continue
        height = text_height(first)
        alignment = int(first.state.get('an',2))
        top = anchor[1] - ((2-(alignment-1)//3)/2)*height
        border = max(first.state.get(k,first.state.get('bord',0)) for k in ('xbord','ybord'))
        if peers[0][1][1] > top-border or peers[-1][1][3] < top+height+border:
            continue
        proven.setdefault((key,phase,boundary,anchor,colors),[]).append([e for e,rect in peers])

    proposals = []
    for (key,start,end,pos),copies in holds.items():
        if len({paint(e.state) for e in copies}) != 1:
            continue
        base = copies[0]
        colors = paint(base.state)
        incoming = proven.get((key,'in',start,pos,colors),[])
        outgoing = proven.get((key,'out',end,pos,colors),[])
        if len(incoming) != 1 or len(outgoing) != 1:
            continue
        members = {e.source_index for e in copies+incoming[0]+outgoing[0]}
        for p,final in pulses.get((layout(base,base.state,scaled=True),start,end,pos),[]):
            # The source is a fading copy at this exact anchor and interval.
            # Its positive starting size may be larger or smaller; the exact
            # return to the proven hold identifies it, not its amplitude.
            if (int(p.layer) >= max(int(e.layer) for e in copies) and
                    all(final.get(k,100) == base.state.get(k,100) for k in ('fscx','fscy'))):
                members.add(p.source_index)
        prefix = re.match(r'(?:\{[^}]*\})*',base.text).end()
        caption = replace_event(base,text=aggressive_caption(
                    {**base.state,'fn':literal_font_spans(base)[0][1]},base.text[prefix:]),
                    start=incoming[0][0].start,start_s=incoming[0][0].start_s,
                    source_index=min(members))
        proposals.append((members,caption))
    owners = {}
    for members,caption in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    accepted = [(members,caption) for members,caption in proposals
                if all(owners[index] == 1 for index in members)]
    if not accepted:
        return events,0
    # A matching authored lyric proves the complete cue, including fragments
    # with inline fonts that the ordinary row assembler keeps positioned.
    # Its times must coincide with the first and last held phases, and every
    # literal character must be present in anchor order. Trim decorative
    # entrances/exits to those lyric bounds rather than exposing overlapping
    # full captions during neighboring strip fades.
    held_by_id = {e.source_index:e for copies in holds.values() for e in copies}
    cues = {}
    for members,caption in accepted:
        base = next(held_by_id[i] for i in members if i in held_by_id)
        cue_key = (caption.style,caption.name,caption.start,
                   get_pos(caption.text)[1],text_layout_key(base),paint(base.state))
        cues.setdefault(cue_key,[]).append((members,caption,base))
    adjusted = {}
    comments = [e for e in events if e.kind == 'Comment' and e.duration > 0]
    for peers in cues.values():
        peers.sort(key=lambda item:get_pos(item[1].text)[0])
        if len({get_pos(c.text)[0] for ids,c,base in peers}) != len(peers):
            continue
        beginning = min(base.start_s for ids,c,base in peers)
        finish = max(base.end_s for ids,c,base in peers)
        literal = ''.join(OVERRIDE_RE.sub('',c.text) for ids,c,base in peers)
        norm = lambda value: ''.join(value.split())
        if any(e.style == peers[0][1].style and e.name == peers[0][1].name and
               abs(e.start_s-beginning) <= .05 and abs(e.end_s-finish) <= .05 and
               norm(simplify_text(e.text,visible_only=True)[1]) == norm(literal)
               for e in comments):
            adjusted.update((c.source_index,replace_event(c,start=format_time(beginning),
                start_s=beginning,end=format_time(finish),end_s=finish))
                for ids,c,base in peers)
    accepted = [(ids,adjusted.get(c.source_index,c)) for ids,c in accepted]
    consumed = set().union(*(members for members,caption in accepted))
    output = [e for e in events if e.source_index not in consumed]
    output.extend(caption for members,caption in accepted)
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output)


def index_fragment_spans(fragments: Iterable[str], *, casefold: bool = False) -> tuple:
    """Index literal text at recorded fragment boundaries without a length cap."""
    words, starts, ends = [], {}, {}
    offset = 0
    for index,fragment in enumerate(fragments):
        word = ''.join(fragment.split())
        if casefold:
            word = word.casefold()
        words.append(word)
        starts.setdefault(offset,[]).append(index)
        offset += len(word)
        ends.setdefault(offset,[]).append(index)
    return ''.join(words),starts,ends


def matching_fragment_spans(index: tuple, target: str):
    """Yield complete contiguous fragments spelling an already normalized target."""
    if not target:
        return
    text,starts,ends = index
    offset = text.find(target)
    while offset >= 0:
        for first in starts.get(offset,()):
            for last in ends.get(offset+len(target),()):
                if first <= last:
                    yield first,last
        offset = text.find(target,offset+1)


def match_repeated_glyph_flashes(events: list[Event], words: dict[int,str],
                                  positions: dict[int,tuple[float,float] | None],
                                  metric: FontSpacing | None) -> set[int]:
    """Prove complete repeated colour flashes over a held text row.

    Use the retained fragment geometry and exact font, including the existing
    font-size calibration for separately authored glyphs. A whole family must
    repeat every glyph, vary its paint, and stay within the foreground cue.
    Fixed same-layer flashes also qualify after their fades have been stripped.
    Return membership only; the held text, paint and timing remain untouched.
    """
    if metric is None or not metric.available:
        return set()
    paint = {'c','1c','2c','3c','4c','bord','xbord','ybord','blur','be'}
    parents, flashes = {}, {}
    for e in events:
        text,pos = words.get(e.source_index,''),positions.get(e.source_index)
        if (e.kind != 'Dialogue' or not text or pos is None or e.duration <= 0 or
                e.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'} or
                not e.layer.lstrip('-').isdigit() or
                any(not math.isfinite(v) for v in (*pos,e.start_s,e.end_s))):
            continue
        state = e.state or effective_state(e.text,e.defaults,e.styles)
        sample = dataclass_replace(e,state=state)
        inline = inline_layout_key(sample)
        profile = static_text_paint_geometry(sample,paint) if inline else None
        if (state.get('p',0) or state.get('borderstyle',1) != 1 or
                inline and (profile is None or len(profile[0]) != 1) or
                not unrotated_text_state(state) or
                any(k in state for k in ('clip','iclip','org')) or
                any(abs(state.get(k,0)) > .001 for k in ('fax','fay'))):
            continue
        tokens = event_override_tokens(e)
        if any(tag in {'move','fade','k','kf','ko','kt'} for tag,value in tokens):
            continue
        transforms = [value for tag,value in tokens if tag == 't']
        if any(parse_effect_transform(value,e.duration,paint,allow_after_end=True) is None
               for value in transforms):
            continue
        layout = tuple((k,str(v).casefold() if k == 'fn' else v)
                       for k,v in text_layout_key(sample) if k != 'q')
        key = (e.style,e.name,placement_key(sample)[0],layout)
        border = max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord'))
        if (len(text) == 1 and not text.isspace() and border == 0 and
                not transforms and not unicodedata.combining(text) and
                unicodedata.bidirectional(text) not in {'R','AL','AN'}):
            flashes.setdefault(key,{}).setdefault(e.layer,[]).append(sample)
        elif border > 0 and state.get('1a',0) == 0:
            parents.setdefault((key,e.layer,e.start,e.end,pos[1]),[]).append(sample)
    indexes = {}
    for key,layers in flashes.items():
        indexes[key] = []
        for peers in layers.values():
            peers.sort(key=lambda e:e.start_s)
            indexes[key].append(([e.start_s for e in peers],peers))
    proposals = []
    for (key,layer,start,end,y),row in parents.items():
        if key not in indexes or sum(len(''.join(words[e.source_index].split())) for e in row) < 3:
            continue
        row.sort(key=lambda e:positions[e.source_index][0])
        if len({positions[e.source_index][0] for e in row}) != len(row):
            continue
        first = row[0]
        for starts,peers in indexes[key]:
            candidates = [e for e in peers[bisect_left(starts,first.start_s-1e-6):
                                           bisect_right(starts,first.end_s)]
                          if e.end_s <= first.end_s+1e-6 and e.duration <= .25*first.duration and
                             abs(positions[e.source_index][1]-y) <= first.unit]
            slots = {}
            for e in candidates:
                slots.setdefault((positions[e.source_index][0],words[e.source_index]),[]).append(e)
            if not slots or any(len(group) < 3 or
                    len({e.state.get('1c') for e in group}) < 3 or
                    max(e.end_s for e in group)-min(e.start_s for e in group) < .5*first.duration
                    for group in slots.values()):
                continue
            ordered = sorted(slots)
            ownership = [0]*len(ordered)
            complete = True
            for parent in row:
                text = words[parent.source_index]
                target = ''.join(text.split())
                px,py = positions[parent.source_index]
                options = []
                for i in range(len(ordered)-len(target)+1):
                    span = ordered[i:i+len(target)]
                    if ''.join(c for x,c in span) != target:
                        continue
                    xs = [x for x,c in span]
                    if any(b-a <= first.unit for a,b in zip(xs,xs[1:])):
                        continue
                    if not any(c.isspace() for c in text):
                        anchor = metric.fragment_anchor(parent.state,xs,list(target),text,
                                                        parent.unit,allow_tracking=True,separate_glyphs=True,
                                                        max_size_error=.1)
                        fits = anchor is not None and abs(anchor-px) <= 1.5*parent.unit
                    else:
                        glyphs = [slots[slot][0] for slot in span]
                        fit = metric.recover(glyphs,list(target),max_size_error=.1)
                        fits = (fit is not None and ' '.join(fit[0].split()) == ' '.join(text.split()) and
                                (int(parent.state.get('an',5))-1)%3 == 1 and
                                abs(fit[1]-px) <= max(1.5*parent.unit,.1*text_height(parent)))
                    if fits:
                        options.append(i)
                if len(options) != 1:
                    complete = False; break
                for i in range(options[0],options[0]+len(target)):
                    ownership[i] += 1
            if complete and all(n == 1 for n in ownership):
                proposals.append({e.source_index for group in slots.values() for e in group})
    owners = {}
    for members in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    return {index for members in proposals if all(owners[i] == 1 for i in members)
            for index in members}


def remove_source_fragment_effects(events: list[Event], row_evidence: list[TextRow],
                                   words: dict[int,str],
                                   positions: dict[int,tuple[float,float] | None],
                                   animated_sources: set[int] | None = None, *,
                                   font_spacing: FontSpacing | None = None) -> tuple[list[Event],int]:
    """Remove effects proven by original source rows and visibility phases.

    Use source text and anchors before freezing or coalescing glyph lifetimes.
    Confirm stable rows and record their foreground paint in the supplied row
    models for reconstruction. Ambiguous or incomplete evidence stays intact.
    """
    animated_sources = animated_sources or set()
    parsed = {e.source_index:e for e in events}
    indexed: dict[tuple,list[Event]] = {}
    for e in parsed.values():
        if positions.get(e.source_index) is not None and words.get(e.source_index):
            indexed.setdefault((e.style,e.name,e.margin_l,e.margin_r,e.margin_v),[]).append(e)
    removed = match_translucent_glyph_particles(events,row_evidence,words,animated_sources)
    removed.update(match_repeated_glyph_flashes(events,words,positions,font_spacing))
    for row in row_evidence:
        # Short rows may prove complete particle phases, but retain the older
        # minimum for the broader layered-effect and foreground-paint rules.
        if (sum(len(''.join(word.split())) for _,word,_ in row.pieces) < 8 or
                len({paint_row[0].layer for paint_row in row.paint_rows}) < 2):
            continue
        first = row.base
        phases = {}
        for paint_row in row.paint_rows:
            profile = paint_row[0].state.get('_opaque_spans',((first.start_s,first.end_s),))
            phases.setdefault(profile,[]).append(paint_row)
        alternating = any(profile != ((first.start_s,first.end_s),) for profile in phases)
        if alternating:
            # Different segmentations can replace each other during a cue.
            # Require complete, nonoverlapping visibility and layered text
            # in every phase; a partial row cannot prove full-cue coverage.
            if (len(phases) < 2 or any(len({paint_row[0].layer for paint_row in peers}) < 2
                                      for peers in phases.values())):
                continue
            spans = sorted(span for profile in phases for span in profile)
            cursor = first.start_s
            complete = True
            for start,end in spans:
                if abs(start-cursor) > .001:
                    complete = False
                    break
                cursor = end
            if not complete or abs(cursor-first.end_s) > .001:
                continue
            selected = first.state['_opaque_spans']
            removed.update(e.source_index for profile,peers in phases.items()
                           if profile != selected for paint_row in peers for e in paint_row)
        chosen = [e for e, _, _ in row.pieces]
        height = text_height(first)
        anchors = row.source_anchors
        # A highlight may spell several separately positioned glyphs.
        # Retain their original anchors before paint-based reconstruction
        # divides a gradient into differently coloured caption fragments.
        span_index = index_fragment_spans(word for _,word,_ in row.pieces)
        gaps = [0]
        for left,right in zip(row.pieces,row.pieces[1:]):
            gaps.append(gaps[-1]+(right[2][0]-left[2][0] > 2*height))
        syllables = {}
        top_layer = max(int(paint_row[0].layer) if paint_row[0].layer.lstrip('-').isdigit()
                        else 0 for paint_row in row.paint_rows)
        layout_tags = ({tag for tag,_ in text_layout_key(first)} - {'fscx','fscy'} |
                       {'a','r','fr','pos','move','clip','iclip','p'})
        candidates = []
        evidence = set()
        for e in indexed.get((first.style,first.name,first.margin_l,first.margin_r,first.margin_v),[]):
            delayed = first.end_s <= e.start_s <= first.end_s+.25*first.duration
            if not (first.start_s-.001 <= e.start_s and
                    (e.start_s < first.end_s or delayed and e.source_index in animated_sources)):
                continue
            pos = positions[e.source_index]
            nearby = [anchor for anchor in anchors.get(words[e.source_index],[]) if
                      abs(pos[0]-anchor[0]) <= height and abs(pos[1]-anchor[1]) <= .25*height]
            state = e.state or effective_state(e.text,e.defaults,e.styles)
            e.state = state
            # This proof removes only a nested animated copy above an
            # existing layered row. It does not confirm a dense fade family
            # or normalize the underlying row's gradient paint.
            if (e.source_index in animated_sources and e.duration < first.duration-.011 and
                    e.end_s <= first.end_s and e.start_s >= first.start_s and
                    (int(e.layer) if e.layer.lstrip('-').isdigit() else 0) > top_layer and
                    state.get('1a',0) < 128 and not state.get('p',0) and
                    'clip' not in state and 'iclip' not in state and
                    not inline_layout_key(e) and text_layout_key(e) == text_layout_key(first) and
                    not re.search(r'\\(?:move|org)\s*\(',e.text,re.I)):
                transforms = [value for block in OVERRIDE_RE.findall(e.text)
                              for tag,value in tokenize_override(block) if tag == 't']
                moving = any(tag in layout_tags for value in transforms
                             for tag,_ in tokenize_override(value))
                target = ''.join(words[e.source_index].split())
                query = (target,pos)
                if query not in syllables:
                    matches = []
                    # Search only the actual effect text, not all quadratic
                    # combinations of a long row. Consider every occurrence,
                    # but two nearby matches already establish ambiguity.
                    for start,end in matching_fragment_spans(span_index,target):
                        if gaps[start] != gaps[end]:
                            continue
                        a,b = row.pieces[start][2],row.pieces[end][2]
                        anchor = ((a[0]+b[0])/2,(a[1]+b[1])/2)
                        if (abs(pos[0]-anchor[0]) <= .12*height and
                                abs(pos[1]-anchor[1]) <= .06*height):
                            matches.append(anchor)
                            if len(matches) == 2:
                                break
                    syllables[query] = matches
                matches = syllables[query]
                if not moving and len(matches) == 1:
                    removed.add(e.source_index)
            # Some fade copies rise and shrink about a distant origin. The
            # unchanged x anchor, explicit transparency and smaller scale tie
            # them to the same glyph even after they leave the baseline.
            if not nearby and e.source_index in animated_sources:
                origin = re.search(r"\\org\(\s*("+NUM+r")\s*,\s*("+NUM+r")",e.text,re.I)
                if origin:
                    state = effective_state(e.text,e.defaults,e.styles)
                    if (state.get("1a",0) > 0 and state.get("fscx",100) <= first.state.get("fscx",100)
                            and abs(float(origin[2])-pos[1]) > 20*height):
                        nearby = [p for p in anchors.get(words[e.source_index],[]) if
                                  abs(pos[0]-p[0]) <= .06*height and
                                  abs(float(origin[1])-p[0]) <= .06*height and
                                  abs(pos[1]-p[1]) <= 2*height]
            if not nearby:
                continue
            if (state.get("p",0) or "clip" in state or "iclip" in state or
                    str(state.get("fn","")).casefold() != str(first.state.get("fn","")).casefold() or
                    abs(state.get("fs",75)-first.state.get("fs",75)) > .05*first.state.get("fs",75) or
                    any(state.get(k,DEFAULT_STATE.get(k)) != first.state.get(k,DEFAULT_STATE.get(k))
                        for k in ("b","i","an"))):
                continue
            if delayed:
                # Delayed particles must actually fade. A new opaque lyric at
                # the same position is never an old row's decorative tail.
                if state.get("1a",0) <= 0 or not re.search(r"\\(?:move|fad|t)\(",e.text,re.I):
                    continue
                # A matching anchor in a later stable row takes precedence;
                # repeated syllables alone cannot identify their owner.
                if any(other[0].start_s > first.start_s and
                       other[0].start_s <= e.start_s < other[0].end_s and
                       other[0].style == first.style and other[0].name == first.name and
                       any(words[g.source_index] == words[e.source_index] and
                           math.dist(positions[g.source_index],pos) <= .06*height for g in other)
                       for peer in row_evidence for other in peer.paint_rows):
                    continue
            if e.source_index in animated_sources:
                anchor = min(nearby,key=lambda p:math.dist(p,pos))
                evidence.add((words[e.source_index],anchor[0]))
                candidates.append(e)
            elif (e.end_s <= first.end_s+.001 and any(math.dist(pos,p) <= .06*height for p in nearby)):
                candidates.append(e)
        # Ordinary layered signs and isolated highlights are insufficient.
        if (alternating or len(evidence) < max(3, math.ceil(len(chosen)/2)) or
                sum(e.source_index in animated_sources for e in candidates) < 3*len(evidence)):
            continue
        # Static foreground highlight paint provides the fill, while the base
        # row supplies geometry and timing. Use one paint across the whole row.
        paints = [e for e in candidates if e.source_index not in animated_sources]
        if not paints:
            paints = [e for paint_row in row.paint_rows for e in paint_row]
        row.foreground = paints
        row.confirmed = True
        kept = {e.source_index for e in chosen}
        removed.update(e.source_index for e in candidates if e.source_index not in kept)
    output,pulses = collapse_backed_glyph_pulses(
        [e for e in events if e.source_index not in removed],words,positions)
    output,slices = collapse_sliced_text_sequences(output)
    return output, len(removed)+pulses+slices


def nearby_boundary_groups(index: dict, key: tuple, boundary: float) -> list[tuple[float,list]]:
    """Look up whole phase groups within 50 ms of a caption boundary.

    Groups retain their authored times. Query a fixed boundary rather than
    chaining nearby times, which could join separate repetitions.
    """
    times, groups = index.get(key, ([], {}))
    slack = .05+1e-6
    left = bisect_left(times, boundary-slack)
    right = bisect_right(times, boundary+slack)
    return [(time,groups[time]) for time in times[left:right]]


def match_boundary_glyph_effects(events: list[Event], visible_map: dict[int,str],
                                 source_events: dict[int,Event],
                                 metric: FontSpacing | None) -> set[int]:
    """Prove whole rotating entrances and flying exits of retained words.

    The source phase must meet the static caption within 50 ms, spell every
    fragment in order, and fit each authored word anchor with the exact font,
    including tracking. Partial groups, duplicate letters and unrelated labels cannot
    authorize removal. The retained words supply text; no spaces are inferred.
    """
    if metric is None or not metric.available:
        return set()

    def geometry(e: Event, y: float) -> tuple:
        return (e.style,e.name,placement_key(e),y,
                tuple((k,v) for k,v in text_layout_key(e)
                      if k not in {'frz','frx','fry'}))

    groups = {}
    captions = {}
    caption_candidates = []
    boundary_sources, protected = set(), set()
    for e in events:
        original = source_events.get(e.source_index)
        if original is None or e.kind != 'Dialogue' or inline_layout_key(original):
            continue
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (e.duration > 0 and word and pos is not None and upright_text_state(e.state) and
                e.state.get('1a',0) == 0 and not any(c.isspace() for c in word) and
                not any(k in e.state for k in ('clip','iclip','org')) and
                get_pos(original.text) == pos):
            key = geometry(e,pos[1])
            caption_candidates.append((e,key))
        glyph = simplify_text(original.text,visible_only=True)[1]
        if (len(glyph) != 1 or glyph.isspace() or unicodedata.combining(glyph) or
                original.duration <= 0):
            continue
        tokens = event_override_tokens(original)
        state = effective_state(original.text,original.defaults,original.styles)
        if (not opaque_text_effect_state(state) or
                any(abs(state.get(k,0)) > .001 for k in ('fax','fay'))):
            continue
        fades = [value for tag,value in tokens if tag == 'fad']
        if len(fades) != 1 or any(tag == 'fade' for tag,value in tokens):
            continue
        try:
            fade = [float(v) for v in fades[0].strip('()').split(',')]
        except ValueError:
            continue
        if len(fade) != 2 or not all(math.isfinite(v) and v >= 0 for v in fade):
            continue
        moves = [value for tag,value in tokens if tag == 'move']
        transforms = [value for tag,value in tokens if tag == 't']
        phase = None
        if not moves and len(transforms) == 1 and get_pos(original.text) is not None:
            transform = parse_effect_transform(transforms[0],original.duration,
                                               {'fr','frz','frx','fry','blur','be'})
            if transform is None:
                continue
            begin,end,changes = transform
            final = state.copy()
            for tag,value in changes:
                apply_tag(final,tag,value,original.styles,original.defaults)
            if (unrotated_text_state(state) or not unrotated_text_state(final) or
                    not 0 < fade[0] <= 1000*original.duration or fade[1] != 0):
                continue
            phase,boundary,pos = 'entrance',original.end_s,get_pos(original.text)
        elif len(moves) == 1 and not transforms and unrotated_text_state(state):
            move = parse_effect_move(moves[0],original.duration,endpoint_slack=50)
            if (move is None or math.dist(move[:2],move[2:4]) < e.unit or
                    get_pos(original.text) is not None or
                    fade[0] != 0 or not 0 < fade[1] <= 1000*original.duration+50):
                continue
            phase,boundary,pos = 'exit',original.start_s,tuple(move[:2])
        if phase is not None:
            source = dataclass_replace(original,state=state)
            key = (phase,geometry(source,pos[1]))
            boundary_sources.add(e.source_index)
            if e.duration > original.duration+.001:
                # A one-letter syllable may already include its entrance in
                # the retained cue. It proves its slot but must never be
                # removed along with its decorative peers. Compare source
                # coverage instead of guessing from the event's duration.
                if (phase != 'entrance' or word != glyph or get_pos(e.text) != pos or
                        not upright_text_state(e.state) or e.state.get('1a',0) != 0):
                    continue
                protected.add(e.source_index)
                captions.setdefault(key,{}).setdefault(boundary,[]).append(e)
            groups.setdefault((key,boundary),[]).append((e,pos,glyph))

    # A long frozen entrance is still an entrance, not another held word.
    # Only a source-independent caption or an absorbed held phase can prove
    # the destination. This distinction also permits genuinely brief holds.
    for e,key in caption_candidates:
        if e.source_index not in boundary_sources or e.source_index in protected:
            for phase,boundary in (('entrance',e.start_s),('exit',e.end_s)):
                captions.setdefault((phase,key),{}).setdefault(boundary,[]).append(e)

    caption_index = {key:(sorted(phases),phases) for key,phases in captions.items()}
    proposals = []
    for (key,boundary),peers in groups.items():
        peers.sort(key=lambda item:item[1][0])
        nearby = nearby_boundary_groups(caption_index,key,boundary)
        # An absorbed one-letter entrance can appear at both its emitted and
        # original stable boundary. Use its closest anchor once; independent
        # nearby repetitions retain distinct source IDs and fail the proof.
        candidates = {}
        for time,words in nearby:
            for e in words:
                previous = candidates.get(e.source_index)
                if previous is None or abs(time-boundary) < abs(previous[0]-boundary):
                    candidates[e.source_index] = (time,e)
        times = [time for time,e in candidates.values()]
        if not times or max(times)-min(times) > .05+1e-6:
            continue
        words = sorted((e for time,e in candidates.values()),key=lambda e:get_pos(e.text)[0])
        if (sum(len(visible_map[e.source_index]) for e in words) != len(peers) or
                len(peers) < 3 or len({pos[0] for e,pos,char in peers}) != len(peers) or
                ''.join(visible_map[e.source_index] for e in words) != ''.join(c for e,p,c in peers)):
            continue
        offset = 0
        for word in words:
            text = visible_map[word.source_index]
            letters = peers[offset:offset+len(text)]
            offset += len(text)
            anchor = metric.fragment_anchor(word.state,[p[0] for e,p,c in letters],
                                           [c for e,p,c in letters],text,word.unit,
                                           allow_tracking=True)
            if anchor is None or abs(anchor-get_pos(word.text)[0]) > 1.5*word.unit:
                break
        else:
            proposals.append((key[0],peers,words))
    # Each effect needs one owner; each held word can prove one entrance and
    # one exit independently, but cannot absorb competing copies of either.
    effect_owners, caption_owners = {}, {}
    for phase,peers,words in proposals:
        for e,p,c in peers:
            effect_owners[e.source_index] = effect_owners.get(e.source_index,0)+1
        for e in words:
            owner = (phase,e.source_index)
            caption_owners[owner] = caption_owners.get(owner,0)+1
    return {e.source_index for phase,peers,words in proposals
            if all(effect_owners[e.source_index] == 1 for e,p,c in peers) and
               all(caption_owners[(phase,e.source_index)] == 1 for e in words)
            for e,p,c in peers if e.source_index not in protected and
            all(e.source_index != word.source_index for word in words)}


def match_departing_glyph_effects(events: list[Event], row_evidence: list[TextRow],
                                  source_events: dict[int,Event],
                                  metric: FontSpacing | None) -> set[int]:
    """Prove complete outline exits from retained fragments' original anchors.

    A whole letter group must spell its source fragment, begin within 50 ms
    of that fragment's end, and fit the exact font at its authored position.
    Moving, fading contours are decorative exits; partial or ambiguous groups stay.
    This proof uses source trajectories rather than frozen effect positions.
    """
    if metric is None or not metric.available or not any(not row.virtual for row in row_evidence):
        return set()
    groups = {}
    for e in events:
        original = source_events.get(e.source_index)
        if (original is None or e.kind != "Dialogue" or
                not re.search(r"\\move\s*\(",original.text,re.I)):
            continue
        word = simplify_text(original.text,visible_only=True)[1]
        if len(word) != 1 or word.isspace() or unicodedata.combining(word):
            continue
        tokens = [token for block in OVERRIDE_RE.findall(original.text)
                  for token in tokenize_override(block)]
        moves = [value for tag,value in tokens if tag == "move"]
        if len(moves) != 1 or inline_layout_key(original):
            continue
        move = parse_effect_move(moves[0],original.duration,endpoint_slack=.001)
        if move is None or move[:2] == move[2:4]:
            continue
        state = effective_state(original.text,original.defaults,original.styles)
        final = state.copy()
        opaque_fill = False
        for tag,value in tokens:
            if tag == "t":
                for name,argument in tokenize_override(value[1:-1]):
                    apply_tag(final,name,argument,original.styles,original.defaults)
                    opaque_fill |= final.get("1a",0) < 254
        if (opaque_fill or state.get("1a",0) < 254 or state.get("3a",0) >= 128 or
                final.get("1a",0) < 254 or final.get("3a",0) < 254 or
                any(s.get("p",0) or s.get("borderstyle",1) != 1 or
                    any(k in s for k in ("clip","iclip","org")) or
                    any(abs(s.get(k,s.get("shad",0))) > 0 for k in ("xshad","yshad"))
                    for s in (state,final)) or
                any(abs(state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        layout = tuple((k,str(v).casefold() if k == "fn" else v)
                       for k,v in text_layout_key(dataclass_replace(original,state=state)))
        key = (original.style,original.name,
               placement_key(dataclass_replace(original,state=state))[0],layout)
        groups.setdefault(key,{}).setdefault(original.start_s,[]).append((e,move,word))
    boundary_index = {key:(sorted(phases),phases) for key,phases in groups.items()}
    proofs = []
    for row in row_evidence:
        if row.virtual:
            continue
        for piece,word,pos in row.pieces:
            original = source_events.get(piece.source_index)
            if (original is None or get_pos(original.text) is None or
                    math.dist(get_pos(original.text),pos) > piece.unit or
                    not word or any(c.isspace() or unicodedata.combining(c) or
                        unicodedata.bidirectional(c) in {"R","AL","AN"} for c in word) or
                    piece.state.get("1a",255) != 0 or inline_layout_key(original)):
                continue
            layout = tuple((k,str(v).casefold() if k == "fn" else v)
                           for k,v in text_layout_key(piece))
            key = (piece.style,piece.name,placement_key(piece)[0],layout)
            for boundary,candidates in nearby_boundary_groups(boundary_index,key,original.end_s):
                peers = sorted(candidates,key=lambda item:item[1][0])
                if (len(peers) != len(word) or "".join(item[2] for item in peers) != word or
                        not original.layer.lstrip("-").isdigit() or
                        any(not source_events[e.source_index].layer.lstrip("-").isdigit() or
                            int(source_events[e.source_index].layer) <= int(original.layer)
                            for e,move,char in peers) or
                        any(abs(move[1]-pos[1]) > piece.unit for e,move,char in peers)):
                    continue
                expected = metric.fragment_anchor(piece.state,
                    [move[0] for e,move,char in peers],[char for e,move,char in peers],word,piece.unit)
                if expected is None or abs(expected-pos[0]) > 1.5*piece.unit:
                    continue
                proofs.append((piece.source_index,{e.source_index for e,move,char in peers}))
    effect_owners, caption_owners = {}, {}
    for source_index,members in proofs:
        caption_owners[source_index] = caption_owners.get(source_index,0)+1
        for index in members:
            effect_owners[index] = effect_owners.get(index,0)+1
    return {index for source_index,members in proofs
            if caption_owners[source_index] == 1 and
               all(effect_owners[index] == 1 for index in members)
            for index in members}


def match_staggered_row_effects(events: list[Event], row_evidence: list[TextRow],
                                source_events: dict[int,Event],
                                animated_sources: set[int],
                                metric: FontSpacing | None) -> set[int]:
    """Prove complete animated copies at a recorded row's source phase ends.

    Normalize vertical alignment at the stable pose. Every source fragment
    must belong to exactly one copy, with phase offsets within 50 ms,
    monotonic timing and matching font geometry. Partial and ambiguous
    families stay.
    """
    if metric is None or not metric.available or not any(not row.virtual for row in row_evidence):
        return set()
    buckets = {}
    identity = lambda e: (e.style,e.name,placement_key(e)[0],
        tuple((k,str(v).casefold() if k == "fn" else v)
              for k,v in text_layout_key(e) if k not in {"an","org"}),
        (int(e.state.get("an",5))-1)%3)
    for e in events:
        original = source_events.get(e.source_index)
        if (original is None or e.kind != "Dialogue" or
                e.source_index not in animated_sources or get_pos(original.text) is None or
                inline_layout_key(original) or not re.search(r"\\t\s*\(",original.text,re.I)):
            continue
        # Literal edge spaces affect alignment. The visible-word collector
        # intentionally strips them, so retain the unrendered source payload.
        words = OVERRIDE_RE.sub("",original.text).replace(r"\h"," ")
        if not words.strip() or original.duration <= 0 or any(tag in words for tag in (r"\N",r"\n")):
            continue
        state = effective_state(original.text,original.defaults,original.styles)
        final = state.copy()
        moving = False
        for block in OVERRIDE_RE.findall(original.text):
            for tag,value in tokenize_override(block):
                if tag == "t":
                    for name,argument in tokenize_override(value[1:-1]):
                        moving |= name in {"pos","move","org","clip","iclip","p","r",
                                           "fn","fs","fsp","an","pbo","encoding","q"}
                        apply_tag(final,name,argument,original.styles,original.defaults)
        if (moving or any(s.get("p",0) or s.get("1a",0) >= 128 or
                         any(k in s for k in ("clip","iclip")) or
                         any(abs(s.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))
                         for s in (state,final))):
            continue
        stable = dataclass_replace(original,state=final)
        if identity(dataclass_replace(original,state=state)) != identity(stable):
            continue
        pos = get_pos(original.text)
        # For equal horizontal alignment, only the vertical box anchor moves.
        y = pos[1]+((int(final.get("an",5))-1)//3-1)*text_height(stable)/2
        buckets.setdefault(identity(stable),[]).append((original,words,(pos[0],y)))
    families = []
    for row in row_evidence:
        if row.virtual or len(row.pieces) < 4:
            continue
        first = row.pieces[0][0]
        key = identity(first)
        peers = buckets.get(key,[])
        if not peers:
            continue
        originals = [source_events.get(piece.source_index) for piece,word,pos in row.pieces]
        if any(e is None or e.duration <= 0 for e in originals):
            continue
        height = min(text_height(piece) for piece,word,pos in row.pieces)
        ys = [pos[1]+((int(piece.state.get("an",5))-1)//3-1)*text_height(piece)/2
              for piece,word,pos in row.pieces]
        duration = max(e.end_s for e in originals)-min(e.start_s for e in originals)
        longest = max(len("".join(words.split())) for e,words,pos in peers)
        spans = {}
        for index in range(len(row.pieces)):
            text = ""
            for last in range(index,len(row.pieces)):
                text += "".join(row.pieces[last][1].split())
                if len(text) > longest:
                    break
                spans.setdefault(text,[]).append((index,last))
        matched = []
        covered = [0]*len(row.pieces)
        for original,words,pos in peers:
            if abs(pos[1]-statistics.median(ys)) > .06*height:
                continue
            options = []
            for index,last in spans.get("".join(words.split()),[]):
                pieces = row.pieces[index:last+1]
                x = metric.fragment_anchor(first.state,[point[0] for piece,word,point in pieces],
                                           [word for piece,word,point in pieces],words,first.unit)
                sources = originals[index:last+1]
                ends = [e.end_s for e in sources]
                delta = original.start_s-max(ends)
                if (x is None or max(ends)-min(ends) > .011 or abs(delta) > .05*duration or
                        abs(pos[0]-x) > .12*height or
                        not original.layer.lstrip("-").isdigit() or
                        any(not e.layer.lstrip("-").isdigit() or
                            (int(original.layer),original.source_index) <= (int(e.layer),e.source_index)
                            for e in sources)):
                    continue
                options.append((index,last,delta))
            if len(options) == 1:
                index,last,delta = options[0]
                matched.append((index,original,delta))
                for glyph in range(index,last+1):
                    covered[glyph] += 1
        if len(matched) < 4 or any(count != 1 for count in covered):
            continue
        matched.sort(key=lambda item:item[0])
        offsets = [delta for index,e,delta in matched]
        # Authored handoffs can vary by a few centiseconds across syllables.
        # Keep the tolerance bounded; the epsilon only absorbs float rounding.
        if (max(offsets)-min(offsets) > .05+1e-6 or
                any(a.start_s > b.start_s+.011 or a.end_s > b.end_s+.011
                    for (_,a,_),(_,b,_) in zip(matched,matched[1:]))):
            continue
        families.append({e.source_index for index,e,delta in matched})
    counts = {}
    for family in families:
        for index in family:
            counts[index] = counts.get(index,0)+1
    return set().union(*(family for family in families if all(counts[index] == 1 for index in family)))


def remove_covered_fragment_effects(events: list[Event], visible_map: dict[int,str],
                                    row_evidence: list[TextRow],
                                    animated_sources: set[int] | None = None,
                                    source_events: dict[int,Event] | None = None,
                                    font_spacing: FontSpacing | None = None) -> tuple[list[Event],int]:
    """Remove copies proven to repeat reconstructed, authored or virtual rows.

    Consume shared fragment anchors without guessing spacing or rediscovering
    rows. Visible overlays require nested animation evidence. Static glyphs
    can repeat an animated row's recorded glyphs with identical placement and
    source styling, provided the emitted paint is unchanged or matches its
    level-1 normalized form; virtual rows authorize only matching shadow copies. Original
    trajectories and exact font measurements prove entrance and exit groups.
    """
    animated_sources = animated_sources or set()
    anchors = {row.base.source_index: row.anchors for row in row_evidence}
    models = {row.base.source_index: row for row in row_evidence}
    # Search literal spans at recorded fragment boundaries. The row's text
    # bounds the search, rather than a fixed character or fragment count.
    # Cache both forms because shadow copies allow case-insensitive matching.
    span_indexes = {}

    def matching_spans(base: Event, visible: str, shadow_only: bool):
        key = (base.source_index,shadow_only)
        if key not in span_indexes:
            span_indexes[key] = index_fragment_spans(
                (text for text,x in anchors[base.source_index]),casefold=shadow_only)
        target = ''.join(visible.split())
        if shadow_only:
            target = target.casefold()
        yield from matching_fragment_spans(span_indexes[key],target)
    shadow_sources = {}

    def animated_shadow_source(e: Event) -> bool:
        # Copy reduction can transfer animated shadow paint into the primary
        # channel. Retain the original evidence when checking its highlight
        # fragments; actor labels need not identify the same effect phase.
        if e.source_index not in shadow_sources:
            shadow_sources[e.source_index] = animated_shadow_painted_source(e,source_events,animated_sources)
        return shadow_sources[e.source_index]
    layouts = {row.base.source_index: tuple(
        (key,str(value).casefold() if key == "fn" else value)
        for key,value in text_layout_key(row.pieces[0][0])
        if key not in {"fscx","fscy"}) for row in row_evidence}
    rows: dict[str,list[Event]] = {}
    virtual: set[int] = set()
    for row in row_evidence:
        rows.setdefault(row.base.style,[]).append(row.base)
        if row.virtual:
            virtual.add(row.base.source_index)

    # A row extended across animation phases may also cover surviving held
    # glyphs. Match its recorded pieces and emitted per-character paint, not
    # substrings or nearby positions. Requiring unchanged scales avoids
    # treating an approximate font fit as proof of identical glyph geometry.
    static_glyphs = {}
    for row in row_evidence:
        if (row.virtual or len(row.pieces) < 2 or
                any(piece.source_index not in animated_sources or len(text) != 1 or
                    text.isspace() or unicodedata.combining(text) or
                    unicodedata.bidirectional(text) in {'R','AL','AN'} or
                    piece.layer != row.base.layer
                    for piece,text,pos in row.pieces)):
            continue
        state = row.base.defaults.copy()
        painted = []
        for part in re.split(r"(\{[^}]*\})",row.base.text):
            if part.startswith('{'):
                for tag,value in tokenize_override(part[1:-1]):
                    apply_tag(state,tag,value,row.base.styles,row.base.defaults)
            else:
                painted.extend((char,state.copy()) for char in part if not char.isspace())
        if ''.join(char for char,state in painted) != ''.join(text for piece,text,pos in row.pieces):
            continue
        glyphs = []
        for (piece,text,pos),(char,paint) in zip(row.pieces,painted):
            if (piece.state.get('1a',0) != 0 or
                    paint.get('1a',0) != 0 or paint.get('3a',0) != 0 or
                    (int(paint.get('an',2))-1)//3 != (int(piece.state.get('an',2))-1)//3 or
                    abs(get_pos(row.base.text)[1]-pos[1]) > .001):
                continue
            emitted = dataclass_replace(piece,state=paint)
            # Assembly intentionally replaces outlines, shadows and blur.
            # Validate that known conversion rather than equating the output
            # paint with the unsimplified held phase. Foreground formatting
            # and geometry, including per-glyph colours and scales, must agree.
            paint_key = state_key(emitted,{'pos','an'})
            if paint_key != state_key(piece,{'pos','an'}):
                normalized = replace_event(piece,text=aggressive_caption(piece.state,text))
                if paint_key != state_key(normalized,{'pos','an'}):
                    continue
            glyphs.append((piece,text,pos))
        static_glyphs[row.base.source_index] = glyphs

    def held_glyph_copy(e: Event, visible: str, pos: tuple, base: Event) -> bool:
        if (not static_glyphs.get(base.source_index) or
                e.source_index in animated_sources or len(visible) != 1 or
                e.style != base.style or e.name != base.name or
                e.start_s < base.start_s or e.end_s > base.end_s):
            return False
        matches = [piece for piece,text,anchor in
                   static_glyphs.get(base.source_index,[]) if text == visible and
                   math.dist(pos,anchor) <= .001]
        if len(matches) != 1:
            return False
        piece = matches[0]
        return (e.layer == piece.layer and placement_key(e) == placement_key(piece) and
                state_key(e,{'pos'}) == state_key(piece,{'pos'}) and
                static_object_key(e,e.styles) is not None)

    # Index each style's original row order by start time. Prefix maximum
    # ends keep earlier long-running captions in the candidate window.
    row_indexes = {}
    for style,group in rows.items():
        if any(not math.isfinite(t) for base in group for t in (base.start_s,base.end_s)):
            row_indexes[style] = None
            continue
        ordered = sorted(enumerate(group),key=lambda item:item[1].start_s)
        starts = [base.start_s for order,base in ordered]
        latest = []
        for order,base in ordered:
            latest.append(max(latest[-1] if latest else -math.inf,base.end_s))
        row_indexes[style] = (starts,latest,ordered)

    def timed_rows(style: str, e: Event) -> list[Event]:
        index = row_indexes.get(style)
        if index is None or not all(math.isfinite(t) for t in (e.start_s,e.end_s)):
            return list(rows.get(style,[]))
        starts,latest,ordered = index
        # Expand the bounds by one floating-point step. The unchanged exact
        # comparisons below decide equality at the existing 0.15 s tolerance.
        left = bisect_left(latest,math.nextafter(e.end_s-.15,-math.inf))
        right = bisect_right(starts,math.nextafter(e.start_s+.15,math.inf))
        candidates = [(order,base) for order,base in ordered[left:right]
                      if not (e.start_s < base.start_s-.15 or e.end_s > base.end_s+.15)]
        return [base for order,base in sorted(candidates,key=lambda item:item[0])]

    removed = (match_departing_glyph_effects(events,row_evidence,source_events,font_spacing)
               if source_events is not None else set())
    if source_events is not None:
        removed.update(match_boundary_glyph_effects(events,visible_map,source_events,font_spacing))
        removed.update(match_staggered_row_effects(events,row_evidence,source_events,animated_sources,font_spacing))
    # A shadow-painted highlight may already have become a partial caption.
    # Prove ownership using its recorded source fragments, before inferred
    # tracking or its new paragraph anchor obscures the original glyph row.
    shadow_rows = {index for index,row in models.items() if not row.virtual and
                   row.pieces and all(animated_shadow_source(piece) for piece,_,_ in row.pieces)}
    shadow_layers = {index:max(int(piece.layer) if piece.layer.lstrip('-').isdigit() else 0
                             for piece,_,_ in models[index].pieces) for index in shadow_rows}
    # Authored cue intervals protect the completed lyric while the shared
    # overlap pass trims only the surrounding reconstructed entrance/tail.
    # Require a complete, equally timed source glyph row and one exact cue.
    cue_comments = {}
    if shadow_rows:
        for e in events:
            if e.kind == 'Comment':
                words = simplify_text(e.text,visible_only=True)[1]
                cue_comments.setdefault((e.style,words),[]).append(e)
    for index in shadow_rows:
        row = models[index]
        base = row.base
        if row.phase_core is not None or not all(
                round((source_events or {})[piece.source_index].start_s,2) == round(base.start_s,2) and
                round((source_events or {})[piece.source_index].end_s,2) == round(base.end_s,2)
                for piece,_,_ in row.pieces):
            continue
        cues = {(cue.start_s,cue.end_s) for cue in
                cue_comments.get((base.style,visible_map.get(index,'')),[]) if
                base.start_s < cue.start_s < cue.end_s < base.end_s}
        if len(cues) == 1:
            row.phase_core = next(iter(cues))
        elif not cue_comments.get((base.style,visible_map.get(index,''))):
            # Remuxed tracks often omit the authored Comment lines. A complete
            # coextensive shadow row can still prove its entrance/tail from one
            # shared fade. Animation/paint ownership was checked above; these
            # fades supply timing only, never permission to remove other rows.
            fades = set()
            for piece,_,_ in row.pieces:
                original = (source_events or {})[piece.source_index]
                values = [value for tag,value in event_override_tokens(original) if tag == 'fad']
                try:
                    pair = tuple(float(v)/1000 for v in values[0].strip('()').split(','))
                except (IndexError,ValueError):
                    break
                if (len(values) != 1 or len(pair) != 2 or
                        not all(math.isfinite(v) and v > 0 for v in pair) or
                        sum(pair) >= original.duration):
                    break
                fades.add(pair)
            else:
                if len(fades) == 1:
                    entrance,tail = next(iter(fades))
                    row.phase_core = (round(base.start_s+entrance,2),round(base.end_s-tail,2))
    shadow_poses = {}

    def shadow_fragment_copy(piece: Event, text: str, pos: tuple, base: Event) -> bool:
        if (not animated_shadow_source(piece) or base.source_index not in shadow_rows or
                piece.state.get('p',0) or inline_layout_key(piece) or
                any(k in piece.state for k in ('clip','iclip','org')) or
                piece.duration >= base.duration-.011 or
                piece.start_s < base.start_s-.15 or piece.end_s > base.end_s+.15 or
                piece.state.get('1a',0) != 0 or base.state.get('1a',0) != 0 or
                piece.state.get('1c') != base.state.get('1c') or
                not piece.layer.lstrip('-').isdigit() or
                int(piece.layer) <= shadow_layers[base.source_index] or
                placement_key(piece)[0] != placement_key(base)[0] or
                abs(pos[1]-get_pos(base.text)[1]) > .06*min(text_height(piece),text_height(base))):
            return False
        if piece.source_index not in shadow_poses:
            # The final rotation cleanup would select this same authored
            # upright pose. Use that helper here too, so a late pulse is not
            # mistaken for an independent angled letter merely because the
            # initial frozen sample preceded its readable pose.
            shadow_poses[piece.source_index] = prefer_surviving_upright_poses(
                [piece],source_events or {})[0]
        pose = shadow_poses[piece.source_index]
        layout = tuple((key,str(value).casefold() if key == 'fn' else value)
                       for key,value in text_layout_key(pose) if key not in {'fscx','fscy'})
        if layout != layouts[base.source_index]:
            return False
        glyphs = anchors[base.source_index]
        matches = [(first,last) for first,last in matching_spans(base,text,False) if
                   abs(pos[0]-(glyphs[first][1]+glyphs[last][1])/2) <=
                   .12*min(text_height(piece),text_height(base))]
        return len(matches) == 1

    for e in events:
        pos = get_pos(e.text)
        text = visible_map.get(e.source_index,'')
        if e.kind != 'Dialogue' or not text or pos is None or e.source_index in removed:
            continue
        model = models.get(e.source_index)
        pieces = model.pieces if model is not None and not model.virtual else [(e,text,pos)]
        if not pieces or not all(animated_shadow_source(piece) for piece,_,_ in pieces):
            continue
        owners = [base for base in timed_rows(e.style,e) if base.source_index != e.source_index and
                  all(shadow_fragment_copy(piece,word,point,base) for piece,word,point in pieces)]
        if len(owners) == 1:
            removed.add(e.source_index)
    for e in events:
        pos = get_pos(e.text)
        visible = visible_map.get(e.source_index,"")
        if (e.kind != "Dialogue" or e.source_index in removed or e.source_index in anchors or pos is None or
                not visible or e.state.get("p",0) or
                inline_layout_key(e) or "clip" in e.state or "iclip" in e.state):
            continue
        layout = tuple((key,str(value).casefold() if key == "fn" else value)
                       for key,value in text_layout_key(e)
                       if key not in {"fscx","fscy"})
        shadow_only = (e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254 and
                       e.state.get("4a",0) < 254 and
                       any(abs(e.state.get(k,e.state.get("shad",0))) > 0
                           for k in ("xshad","yshad")))
        candidates = timed_rows(e.style,e)
        if e.source_index in (animated_sources or set()):
            # Highlight copies may use a different style. Require matching
            # font geometry, exact fragment position/text and nested lifetime.
            for style in rows:
                if style == e.style:
                    continue
                for base in timed_rows(style,e):
                    if (e.name == base.name and e.duration <= .5*base.duration
                            and e.start_s >= base.start_s and e.end_s <= base.end_s
                            and all(e.state.get(tag) == base.state.get(tag)
                                    for tag in ("fn","fs","an","b","i","frz"))
                            and abs(pos[1]-get_pos(base.text)[1]) <= e.unit
                            and any(text == visible and abs(pos[0]-x) <= e.unit
                                    for text,x in anchors[base.source_index])):
                        candidates.append(base)
        for base in candidates:
            if held_glyph_copy(e,visible,pos,base):
                removed.add(e.source_index)
                break
            # A substring and nearby anchor do not identify an effect copy.
            # Compare the source fragment layout: assembly may change the
            # row's alignment and scales, but not its font or caption identity.
            if (e.name != base.name or layout != layouts[base.source_index] or
                    placement_key(e)[0] != placement_key(base)[0]):
                continue
            # Unassembled rows prove only shadow copies. Their font/layout
            # identity is checked above along with assembled rows.
            if base.source_index in virtual and not shadow_only:
                continue
            if not shadow_only:
                # Visible syllables need the same nested animated foreground
                # evidence as early source-row removal. Static labels remain
                # independent even when their text and position happen to fit.
                source_layer = max(int(piece.layer) if piece.layer.lstrip("-").isdigit() else 0
                                   for piece,_,_ in models[base.source_index].pieces)
                if (e.source_index not in animated_sources or
                        e.duration >= base.duration-.011 or
                        e.start_s < base.start_s or e.end_s > base.end_s or
                        abs(pos[1]-get_pos(base.text)[1]) > .06*min(text_height(e),text_height(base)) or
                        not e.layer.lstrip("-").isdigit() or int(e.layer) <= source_layer):
                    continue
            if (e.duration > .8*base.duration and e.layer == base.layer or
                    e.start_s < base.start_s-.15 or e.end_s > base.end_s+.15 or
                    abs(pos[1]-get_pos(base.text)[1]) > .15*text_height(base)):
                continue
            glyphs = anchors[base.source_index]
            matches = []
            for index,last in matching_spans(base,visible,shadow_only):
                if (abs(pos[0]-(glyphs[index][1]+glyphs[last][1])/2)
                        <= ((.6 if len(visible)>2 else .24)*text_height(base)
                            if shadow_only else .12*min(text_height(e),text_height(base)))):
                    matches.append((index,last))
            if len(matches) == 1:
                removed.add(e.source_index)
            if e.source_index in removed:
                break
    return [e for e in events if e.source_index not in removed],len(removed)


def static_object_key(e: Event, styles: dict, *,
                      allow_unpositioned: bool = False) -> tuple | None:
    """Describe every static text/drawing span, including inherited styling."""
    if e.kind != "Dialogue" or e.effect or e.duration <= 0:
        return None
    # Unpositioned subtitles participate in renderer collision placement.
    # Extending one could change that placement even with identical text.
    if not allow_unpositioned and get_pos(e.text) is None:
        return None
    default = styles.get(e.style, DEFAULT_STATE)
    state = default.copy()
    runs = []
    for part in re.split(r"(\{[^}]*\})", e.text):
        if part.startswith("{") and part.endswith("}"):
            for name, value in tokenize_override(part[1:-1]):
                if name in {"t", "move", "fad", "fade", "k", "kf", "ko", "kt"}:
                    return None
                apply_tag(state, name, value, styles, default)
        elif part:
            normalized = state.copy()
            for clip in ("clip", "iclip"):
                if clip in normalized:
                    normalized[clip] = geometry_key(normalized[clip])
            signature = tuple(sorted(normalized.items()))
            drawing = state.get("p", 0) > 0
            payload = geometry_key(part) if drawing else part
            if runs and runs[-1][0] == signature and runs[-1][1] == drawing:
                runs[-1] = (signature, drawing, runs[-1][2] + payload)
            else:
                runs.append((signature, drawing, payload))
    return (e.layer, e.style, e.name, e.margin_l, e.margin_r, e.margin_v,
            tuple(runs)) if runs else None


def merge_static_timed_copies(events: list[Event], styles: dict) -> tuple[list[Event], int]:
    """Join touching identical positioned objects; never bridge a visible gap.

    Preserve overlapping copies and same-layer compositing order. There is
    no glyph-count, font-name, duration, color or show-specific threshold.
    """
    groups, layers = {}, {}
    untouched = []
    for e in events:
        if e.kind == "Dialogue":
            layers.setdefault(e.layer, []).append(e)
        key = static_object_key(e, styles)
        if key is None:
            untouched.append(e)
        else:
            groups.setdefault(key, []).append(e)
    output, removed = list(untouched), 0
    for group in groups.values():
        ordered = sorted(group, key=lambda e: (e.start_s, e.end_s, e.source_index))
        # Mark all overlapping copies: their compositing multiplicity matters.
        overlapping = set()
        active = []
        for e in ordered:
            active = [other for other in active if other.end_s > e.start_s]
            if active:
                overlapping.add(e.source_index)
                overlapping.update(other.source_index for other in active)
            active.append(e)
        current = ordered[0]
        members = {current.source_index}
        for e in ordered[1:]:
            touching = current.end == e.start
            can_join = touching and e.source_index not in overlapping and not (members & overlapping)
            if can_join:
                low, high = min(*members, e.source_index), max(*members, e.source_index)
                # A peer between source records could switch from being above
                # to below the object after records are combined.
                can_join = not any(low < peer.source_index < high
                    and peer.source_index not in members
                    and min(peer.end_s, e.end_s) > max(peer.start_s, current.start_s)
                    for peer in layers[e.layer])
            if can_join:
                members.add(e.source_index)
                current = replace_event(current, end=e.end, end_s=e.end_s,
                                  source_index=min(members))
                removed += 1
            else:
                output.append(current)
                current, members = e, {e.source_index}
        output.append(current)
    return sorted(output, key=lambda e: e.source_index), removed


def read_subtitle(path: Path, encoding: str | None = None) -> str:
    """Decode Unicode strictly; legacy encodings require an explicit choice."""
    data = path.read_bytes()
    if encoding is None:
        if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            encoding = "utf-32"
        elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            encoding = "utf-16"
        else:
            encoding = "utf-8-sig"
    try:
        text = data.decode(encoding).lstrip("\ufeff")
    except UnicodeError as exc:
        raise ValueError(f"{path}: cannot decode as {encoding}; specify the correct "
                         "--encoding (for example cp1252 or utf-16-le).") from exc
    if "\x00" in text:
        raise ValueError(f"{path}: decoded text contains NUL characters; check "
                         "--encoding (BOM-less UTF-16 needs utf-16-le or utf-16-be).")
    return text


def collect_source_text_rows(parsed: dict[int, Event], animated: set[int]) -> tuple[list[TextRow], dict, dict]:
    """Record duplicated layout-stable rows before transformations lose timing.

    This collector records text and geometry only. Effect membership belongs
    to remove_source_fragment_effects; paint and text output belong to
    reconstruct_text_rows. Color-only transforms do not change row geometry.
    Visibility intervals distinguish whole-cue rows from alternating layouts.
    """
    groups: dict[tuple, list[Event]] = {}
    words = {}
    positions = {}
    for e in parsed.values():
        if e.kind != "Dialogue" or e.duration <= 0:
            continue
        words[e.source_index] = simplify_text(e.text,visible_only=True)[1]
        pos = get_pos(e.text)
        if pos is None:
            move = re.search(r"\\move\(\s*("+NUM+r")\s*,\s*("+NUM+r")", e.text, re.I)
            if move:
                pos = (float(move[1]), float(move[2]))
        positions[e.source_index] = pos
        transforms = [value for block in OVERRIDE_RE.findall(e.text)
                      for tag,value in tokenize_override(block) if tag == "t"]
        moving_layout = any(re.search(r"\\(?:fs(?:c[xy]|p)?|fr[xyz]?|fa[xy]|pos|move|org|clip|iclip|fn|an)(?=[^A-Za-z]|$)",
                                     value,re.I) for value in transforms)
        if (pos is None or not words[e.source_index] or moving_layout or
                re.search(r"\\(?:move|clip|iclip|p[1-9]\d*|org|fad|fade)\b", e.text, re.I)):
            continue
        e.state = effective_state(e.text, e.defaults, e.styles)
        if (inline_layout_key(e) or any(abs(e.state.get(k,100)) <= .01 for k in ('fscx','fscy')) or
                any(abs(e.state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        profile = ((e.start_s,e.end_s),)
        if transforms and any(tag in {'alpha','1a','r'} for transform in transforms
                              for tag,_ in tokenize_override(transform[1:-1])):
            opaque_spans = []
            _, state = freeze_block(''.join(OVERRIDE_RE.findall(e.text)),e.duration,
                                    e.defaults,e.defaults,e.styles,0,opaque_spans)
            if not opaque_spans:
                continue
            profile = tuple((e.start_s+a/1000,e.start_s+b/1000) for a,b in opaque_spans)
            e = dataclass_replace(e,state=state)
        if e.state.get('1a',0) != 0:
            continue
        e = dataclass_replace(e,state={**e.state,'_opaque_spans':profile})
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
               e.start,e.end,pos[1],
               tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
                     ("fn","fs","fscx","fscy","fsp","b","i","an")))
        groups.setdefault((*key,profile,e.layer),[]).append(e)

    families: dict[tuple,list[list[Event]]] = {}
    norm = lambda value: "".join(value.split())
    for key, group in groups.items():
        ordered = sorted(group,key=lambda e: positions[e.source_index][0])
        if (len(ordered) < 4 or
                len({positions[e.source_index][0] for e in ordered}) != len(ordered)):
            continue
        text = norm("".join(words[e.source_index] for e in ordered))
        families.setdefault((*key[:-2],text),[]).append(ordered)

    evidence = []
    for rows in families.values():
        chosen = max(rows,key=lambda row:(sum(b-a for a,b in row[0].state['_opaque_spans']),
                                         len(row),int(row[0].layer) if row[0].layer.lstrip('-').isdigit() else 0))
        first = chosen[0]
        height = text_height(first)
        if any(abs(positions[row[0].source_index][0]-positions[first.source_index][0]) > .5*height or
               abs(positions[row[-1].source_index][0]-positions[chosen[-1].source_index][0]) > .5*height
               for row in rows):
            continue
        anchors: dict[str,list[tuple[float,float]]] = {}
        for paint_row in rows:
            for e in paint_row:
                anchors.setdefault(words[e.source_index],[]).append(positions[e.source_index])
        evidence.append(TextRow(
            first, [(e, words[e.source_index], positions[e.source_index]) for e in chosen],
            paint_rows=rows, source_anchors=anchors))
    return evidence, words, positions


def shadow_lyric_fade_core(e: Event) -> tuple[dict,float,float] | None:
    """Prove one shadow glyph's opaque hold between entrance and fade tail.

    Only a short, one-way shadow-opacity entrance and stationary literal
    geometry qualify. Shadow offsets and colour may animate; other geometry,
    alpha pulses, clips, inline state and unsupported fade forms cannot prove
    a handoff. This supplies timing evidence, never a replacement caption.
    """
    e = without_inert_spacing_tail(e)
    state = effective_state(e.text,e.defaults,e.styles)
    if (e.duration <= 0 or get_pos(e.text) is None or inline_layout_key(e) or
            state.get('1a',0) < 254 or state.get('3a',0) < 254 or
            state.get('borderstyle',1) != 1 or state.get('p',0) or
            not unrotated_text_state(state) or
            not any(abs(state.get(k,state.get('shad',0))) > 0
                    for k in ('xshad','yshad')) or
            any(k in state for k in ('clip','iclip','org'))):
        return None
    tokens = event_override_tokens(e)
    fades = [v for k,v in tokens if k == 'fad']
    if len(fades) != 1 or any(k in {'move','fade','r','alpha','k','kf','ko','kt'} for k,v in tokens):
        return None
    try:
        fade_in,fade_out = [float(v)/1000 for v in fades[0].strip('()').split(',')]
    except ValueError:
        return None
    if (not fades[0].startswith('(') or not fades[0].endswith(')') or
            not all(math.isfinite(v) and v >= 0 for v in (fade_in,fade_out)) or
            fade_out <= 0):
        return None
    entrance = fade_in
    reveals = []
    allowed = {'4a','4c','shad','xshad','yshad'}
    for tag,value in tokens:
        if tag != 't':
            continue
        transform = parse_effect_transform(value,e.duration,allowed,
            allow_instant=True,allow_after_end=True)
        if transform is None:
            return None
        begin,end,changes = transform
        if any(k == '4a' for k,v in changes):
            target = state.copy()
            for k,v in changes:
                apply_tag(target,k,v,e.styles,e.defaults)
            if (target.get('4a') != 0 or end > 500*e.duration or
                    len([1 for k,v in changes if k == '4a']) != 1):
                return None
            reveals.append(end/1000)
    if state.get('4a',0) != 0:
        if state.get('4a',0) < 254 or len(reveals) != 1:
            return None
    elif reveals:
        return None
    entrance = max([entrance]+reveals)
    start,end = e.start_s+entrance,e.end_s-fade_out
    if not e.start_s <= start < end < e.end_s:
        return None
    return {**state,'1a':0,'3a':0,'shad':0,'xshad':0,'yshad':0},start,end


def trim_faded_cue_overlaps(events: list[Event], rows: list[TextRow],
                            source_events: dict[int,Event]) -> tuple[list[Event],int]:
    """Give consecutive static rows a clean handoff within their source fades.

    Reconstructed rows supply their original fragment anchors. Every retained
    fragment, including separate font spans, must match complete source fade
    entrances and tails at the cue's boundaries. Matched fragment phases can
    instead supply their complete ordered word-activation interval. Only rows
    whose protected cores are disjoint qualify. Ambiguous or incomplete groups,
    simultaneous cores and independent positions keep their original timing.
    """
    def lane(e: Event, pos: tuple[float,float], state: dict) -> tuple:
        return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
                round(pos[1],4),(int(state.get('an',2))-1)//3)

    def scrolling(e: Event) -> bool:
        return e.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'}

    def slot(e: Event, pos: tuple[float,float]) -> tuple | None:
        e = without_inert_spacing_tail(e)
        spans = literal_font_spans(e)
        if not spans or any(re.search(r'\\[Nn]|[\r\n]',text) for text,font in spans):
            return None
        # Outer whitespace does not identify a glyph; internal spaces do.
        spans = list(spans)
        spans[0] = (spans[0][0].lstrip(),spans[0][1])
        spans[-1] = (spans[-1][0].rstrip(),spans[-1][1])
        spans = tuple((text,font.casefold()) for text,font in spans if text)
        if not spans:
            return None
        return (tuple(round(v,4) for v in pos),spans,
                tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
                      ('fs','fscx','fscy','fsp','an','b','i','u','s','q','pbo','encoding')))

    provenance: dict[int,list[TextRow]] = {}
    for row in rows:
        if not row.virtual:
            provenance.setdefault(row.base.source_index,[]).append(row)
    groups: dict[tuple,dict[tuple,list[Event]]] = {}
    for e in events:
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or scrolling(e) or pos is None or
                not opaque_text_effect_state(e.state) or not unrotated_text_state(e.state)):
            continue
        timing = (round(e.start_s,2),round(e.end_s,2))
        groups.setdefault(lane(e,pos,e.state),{}).setdefault(timing,[]).append(e)

    # Examine source overrides only for boundaries involved in a collision.
    # This avoids another expensive state-parsing pass over large animations.
    pairs = []
    wanted = set()
    for key,timed in groups.items():
        ordered = sorted(timed)
        previous_end = float('-inf')
        for i,(start,end) in enumerate(ordered[:-1]):
            next_start,next_end = ordered[i+1]
            if (start < next_start < end < next_end and
                    previous_end <= next_start and
                    (i+2 == len(ordered) or ordered[i+2][0] >= end)):
                pairs.append((key,(start,end),(next_start,next_end)))
                wanted.update(((key,0,start),(key,1,end),
                               (key,0,next_start),(key,1,next_end)))
            previous_end = max(previous_end,end)
    if not pairs:
        return events,0

    phase_slots: dict[tuple,dict[tuple,set[float]]] = {}
    shadow_phases = set()
    families = {key[:5] for key,phase,time in wanted}
    boundaries = {(key[:5],phase,time) for key,phase,time in wanted}
    forbidden = {'t','move','clip','iclip','org','fade','k','kf','ko','kt'}
    for e in source_events.values():
        family = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
        start,end = round(e.start_s,2),round(e.end_s,2)
        if (e.kind != 'Dialogue' or scrolling(e) or family not in families or
                r'\fad(' not in e.text.lower() or
                (family,0,start) not in boundaries and (family,1,end) not in boundaries):
            continue
        shadow_core = shadow_lyric_fade_core(e)
        if shadow_core is not None:
            state,core_start,core_end = shadow_core
            pos = get_pos(e.text)
            key = lane(e,pos,state)
            identity = slot(dataclass_replace(e,state=state),pos)
            if identity is not None:
                for phase,time,core in ((0,start,core_start),(1,end,core_end)):
                    phase_key = (key,phase,time)
                    if phase_key in wanted:
                        phase_slots.setdefault(phase_key,{}).setdefault(identity,set()).add(round(core,2))
                        shadow_phases.add(phase_key)
            continue
        tokens = event_override_tokens(e)
        fades = [value for tag,value in tokens if tag == 'fad']
        if (len(fades) != 1 or not fades[0].startswith('(') or not fades[0].endswith(')') or
                any(tag in forbidden for tag,value in tokens)):
            continue
        try:
            fade_in,fade_out = [float(v) / 1000 for v in fades[0].strip('()').split(',')]
        except ValueError:
            continue
        # A final syllable may begin partway through the cue-wide fade tail.
        # Its nominal fade can exceed this phase's duration; the complete row
        # must still agree on a positive non-fading cue interval below.
        if not all(math.isfinite(v) and v >= 0 for v in (fade_in,fade_out)):
            continue
        pos = get_pos(e.text)
        state = effective_state(e.text,e.defaults,e.styles)
        if (pos is None or not opaque_text_effect_state(state) or
                not unrotated_text_state(state)):
            continue
        key = lane(e,pos,state)
        identity = slot(dataclass_replace(e,state=state),pos)
        if identity is None:
            continue
        for phase,time,fade,core in ((0,start,fade_in,start+fade_in),
                                     (1,end,fade_out,end-fade_out)):
            phase_key = (key,phase,time)
            if fade > 0 and phase_key in wanted:
                phase_slots.setdefault(phase_key,{}).setdefault(identity,set()).add(round(core,2))

    proven = {}
    candidates = {(key,timing) for key,left,right in pairs for timing in (left,right)}
    for key,timing in candidates:
        members = groups[key][timing]
        if len(members) == 1:
            e = members[0]
            evidence = provenance.get(e.source_index,[])
            if (len(evidence) == 1 and evidence[0].phase_core is not None and
                    evidence[0].base.text == e.text):
                row = evidence[0]
                start,end = row.phase_core
                xs = [pos[0] for piece,text,pos in row.pieces]
                proven[key,timing] = ((start,end,min(xs),max(xs))
                    if timing[0] < start < end < timing[1] else None)
                continue
        identities = []
        for e in members:
            evidence = provenance.get(e.source_index,[])
            if len(evidence) > 1 or evidence and evidence[0].base.text != e.text:
                identities.append(None)
            elif evidence:
                identities.extend(slot(piece,pos) for piece,text,pos in evidence[0].pieces)
            else:
                identities.append(slot(e,get_pos(e.text)))
        unique = set(identities)
        entrance = phase_slots.get((key,0,timing[0]),{})
        tail = phase_slots.get((key,1,timing[1]),{})
        if (None in unique or len(unique) != len(identities) or
                unique != entrance.keys() or unique != tail.keys()):
            proven[key,timing] = None
            continue
        starts = set().union(*entrance.values())
        ends = set().union(*tail.values())
        shadow_pair = ((key,0,timing[0]) in shadow_phases and
                       (key,1,timing[1]) in shadow_phases)
        if shadow_pair:
            # Staggered reveal endpoints can differ between letters. Every
            # glyph still needs one unambiguous entrance and tail; protect the
            # interval during which the complete row is fully visible.
            if any(len(v) != 1 for v in (*entrance.values(),*tail.values())):
                proven[key,timing] = None
                continue
        elif len(starts) != 1 or len(ends) != 1:
            proven[key,timing] = None
            continue
        core_start,core_end = (max(starts),min(ends)) if shadow_pair else (next(iter(starts)),next(iter(ends)))
        xs = [identity[0][0] for identity in identities]
        proven[key,timing] = ((core_start,core_end,min(xs),max(xs))
                              if timing[0] < core_start < core_end < timing[1] else None)

    replacements = {}
    trimmed = 0
    for key,left,right in pairs:
        a,b = proven.get((key,left)),proven.get((key,right))
        if a is None or b is None or a[1] > b[0]:
            continue
        if min(a[3],b[3]) < max(a[2],b[2]):
            continue
        # A handoff inside both the collision and the gap between stable cores
        # preserves every stable frame and all exposure outside the collision.
        low,high = max(right[0],a[1]),min(left[1],b[0])
        if low > high:
            continue
        boundary = round((low+high)/2,2)
        for timing,time_field in ((left,'end'),(right,'start')):
            for e in groups[key][timing]:
                changes = replacements.setdefault(e.source_index,{})
                changes.update({time_field:format_time(boundary),time_field+'_s':boundary})
        trimmed += 1
    return [replace_event(e,**replacements[e.source_index])
            if e.source_index in replacements else e for e in events],trimmed


def normalize_animated_rotations(events: dict[int,Event]) -> dict[int,Event]:
    """Expose opaque oscillating text as upright source rows of fixed geometry.

    Preserve paint animation and provenance; only rotations and their unused
    origin are removed. Moving/resizing text is frozen normally later, where
    its complete pose can be selected at the same instant.
    """
    result = dict(events)
    for index,e in events.items():
        if (e.kind != 'Dialogue' or e.duration <= 0 or
                not re.search(r'\\t\s*\(',e.text) or
                not re.search(r'\\fr(?:[xyz])?(?=[+\-\d.])',e.text)):
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',e.text).group()
        if not prefix or OVERRIDE_RE.search(e.text,len(prefix)):
            continue
        tokens = [token for block in OVERRIDE_RE.findall(prefix)
                  for token in tokenize_override(block)]
        if any(tag in {'move','r','p'} for tag,_ in tokens):
            continue
        changing = {'fs','fscx','fscy','fsp','fn','b','i','u','s','a','an','r','p',
                    'fax','fay','pos','move','org','clip','iclip','t'}
        if any(tag in changing for name,value in tokens if name == 't'
               for tag,_ in tokenize_override(value[1:-1])):
            continue
        # One-way entrances/exits remain recognizable by the source effect
        # matchers. Only a repeated oscillation supplies an early static row.
        turns = []
        for name,value in tokens:
            if name == 't':
                for tag,argument in tokenize_override(value[1:-1]):
                    if tag in {'fr','frz'}:
                        try: turns.append(math.remainder(float(argument),360))
                        except ValueError: pass
        if len(turns) < 2 or not any(a*b < 0 for a,b in zip(turns,turns[1:])):
            continue
        _,state = freeze_block(''.join(OVERRIDE_RE.findall(prefix)),e.duration,
                              e.defaults,e.defaults,e.styles,0,prefer_upright=True)
        if not state.get('_upright_rotation') or not unrotated_text_state(state):
            continue
        if not (state.get('1a',0) == 0 or state.get('1a',0) >= 254 and
                state.get('3a',0) == 0 and
                max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0):
            continue
        block = re.sub(r'\\fr(?:[xyz])?'+NUMBER,'',prefix)
        block = re.sub(r'\\org\([^)]*\)','',block)
        result[index] = replace_event(e,text=r'{\frz0\frx0\fry0}'+block+e.text[len(prefix):])
    return result


def prefer_surviving_upright_poses(events: list[Event], sources: dict[int,Event]) -> list[Event]:
    """Apply the general rotation policy after source effect cleanup.

    Earlier proofs use their established frozen geometry. Revisit only intact
    retained text, preserving its selected paint, timing and assembled rows.
    """
    geometry = {'fn','fs','fscx','fscy','fsp','b','i','u','s','an','a','pos','org',
                'fr','frz','frx','fry','fax','fay','pbo'}
    def inline_geometry(e):
        if not inline_layout_key(e):
            return False
        painted = False
        for part in re.split(r'(\{[^}]*\})',e.text):
            if part.startswith('{'):
                if painted and any(tag in geometry|{'r','t','p','clip','iclip'}
                                   for tag,_ in tokenize_override(part[1:-1])):
                    return True
            elif part:
                painted = True
        return False
    output = []
    for e in events:
        original = sources.get(e.source_index)
        if (e.kind != 'Dialogue' or original is None or e.style != original.style or
                all(abs(e.state.get(k,0)) <= .001 for k in ('frz','frx','fry')) or
                inline_geometry(e) or inline_geometry(original) or
                not re.search(r'\\t\s*\(',original.text) or
                not re.search(r'\\fr(?:[xyz])?(?=[+\-\d.])',original.text) or
                OVERRIDE_RE.sub('',e.text) != OVERRIDE_RE.sub('',original.text)):
            output.append(e)
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        _,state = freeze_block(''.join(OVERRIDE_RE.findall(prefix)),original.duration,
                              original.defaults,original.defaults,original.styles,0,
                              prefer_upright=True)
        if not state.get('_upright_rotation') or not unrotated_text_state(state):
            output.append(e)
            continue
        prefix_end = re.match(r'(?:\{[^}]*\})*',e.text).end()
        paint = ''.join('\\'+tag+value for block in OVERRIDE_RE.findall(e.text[:prefix_end])
                        for tag,value in tokenize_override(block) if tag not in geometry)
        pose = ''.join(render_tag(k,v) for k,v in state.items() if k in geometry-{'a','fr'})
        output.append(replace_event(e,text='{'+paint+pose+'}'+e.text[prefix_end:]))
    return output


def infer_vector_text_cues(runs: dict, parsed: dict[int,Event], metric: FontSpacing,
                           authored_styles: set[str]) -> list[tuple[Event,str]]:
    """Recover missing cue evidence only from decoded complete animation rows.

    Ordered instantaneous opacity switches prove syllable activation intervals.
    A synchronized full line may share that interval when its font, layer,
    placement margins, frame boundaries and entrance/exit fades agree. Neither
    guessed words nor a renderer-dependent frame rounding offset supplies timing.
    """
    alphabet = set()
    for e in parsed.values():
        if e.kind == 'Dialogue' and not re.search(r'\\p[1-9]',e.text,re.I):
            alphabet.update(simplify_text(e.text,visible_only=True)[1])
    families = {}
    for style,group in runs.items():
        if style in authored_styles:
            continue
        for key,items in group:
            if len(items) < 3:
                continue
            lane = key[:6]+(key[6][1],key[7],round(items[0][0].start_s,2),round(items[-1][0].end_s,2))
            families.setdefault(lane,[]).append((key,items))
    decoded = []
    for family in families.values():
        family.sort(key=lambda run:run[0][6][0])
        activations = []
        for key,items in family:
            first = items[0][0]
            switches = []
            for tag,value in event_override_tokens(first):
                if tag != 't':
                    continue
                transform = parse_effect_transform(value,first.duration,{'1a','3a'},
                    allow_instant=True,allow_after_end=True)
                if transform is None or transform[0] != transform[1]:
                    continue
                target = first.defaults.copy()
                for name,arg in transform[2]:
                    apply_tag(target,name,arg,first.styles,first.defaults)
                if any(name == '1a' for name,arg in transform[2]):
                    switches.append((first.start_s+transform[0]/1000,target.get('1a',0)))
            if (len(switches) != 2 or switches[0][1] != 255 or switches[1][1] != 0 or
                    switches[0][0] >= switches[1][0]):
                break
            activation = (switches[0][0],switches[1][0])
            # Generated frames may retain transforms scheduled beyond their
            # own end. Those annotations alone are not timing evidence: the
            # subsequent frames must actually hide/show this backing glyph.
            starts = [e.start_s for e,p,s in items]
            def opacity_at(at):
                offset = bisect_right(starts,at)-1
                if offset < 0 or at >= items[offset][0].end_s:
                    return None
                event,_,base = items[offset]
                transforms = []
                for tag,value in event_override_tokens(event):
                    if tag == 't':
                        t = parse_effect_transform(value,event.duration,{'1a','3a','alpha'},
                            allow_instant=True,allow_after_end=True)
                        if t is not None:
                            transforms.append((t[0],t[1],1,t[2]))
                return sample_transform_state(base,transforms,1000*(at-event.start_s),
                                              event.styles,event.defaults).get('1a',0)
            inside = [activation[0]+fraction*(activation[1]-activation[0]) for fraction in (.25,.75)]
            outside = [(a+b)/2 for a,b in ((items[0][0].end_s,activation[0]),
                        (activation[1],items[-1][0].start_s)) if a < b]
            if (not outside or any((opacity_at(at) or 0) < 254 for at in inside) or
                    not any((value := opacity_at(at)) is not None and value < 16 for at in outside)):
                break
            activations.append(tuple(round(v,2) for v in activation))
        core = None
        if (len(activations) == len(family) and all(a[0] <= b[0] and a[1] <= b[1]
                for a,b in zip(activations,activations[1:]))):
            core = (activations[0][0],activations[-1][1])
        first,last = family[0][1][0][0],family[0][1][-1][0]
        state = family[0][1][0][2]
        sync = (first.layer,first.name,first.margin_l,first.margin_r,first.margin_v,
                tuple(state.get(k) for k in ('fn','fs','fscx','fscy','b','i')),
                round(first.start_s,2),round(last.end_s,2))
        # Require whole-frame alpha entrances and exits for cross-row timing.
        def edge_fade(e,alpha):
            return any(tag == 't' and not re.match(r'\(\s*'+NUMBER,value) and
                (t := parse_effect_transform(value,e.duration,{'1a','3a'})) is not None and
                any(k == '1a' and v.upper().removeprefix('&H').rstrip('&') == alpha
                    for k,v in t[2]) for tag,value in event_override_tokens(e))
        synchronized = all(edge_fade(items[0][0],'00') and edge_fade(items[-1][0],'FF')
                           for key,items in family)
        if core is None and not synchronized:
            continue
        row,words = [],[]
        for key,items in family:
            sample,state = items[0][0],items[0][2]
            face = metric.matching_face(str(state.get('fn','')),bool(state.get('b',0)),False)
            if face is None:
                break
            path = tuple(v if isinstance(v,str) else statistics.median(item[1][i] for item in items)
                         for i,v in enumerate(items[0][1]))
            try:
                text = metric.decode_cubic_outline(face,path,state.get('fs',20),sample.unit,alphabet)
            except (OSError,ValueError,RuntimeError):
                text = None
            if text is None:
                break
            row.append(replace_event(sample,text=aggressive_caption(state,text,p=0,fsp=0)))
            words.append(text)
        else:
            if sum(c.isalnum() for text in words for c in text) < 3:
                continue
            text = words[0]
            if len(row) > 1:
                fit = metric.recover(row,words,max_size_error=.2)
                if fit is not None:
                    text = fit[0]
                elif all(not any(c.isspace() for c in word) for word in words):
                    text = ''.join(words)
                    if metric.fragment_anchor(row[0].state,[get_pos(e.text)[0] for e in row],
                            words,text,row[0].unit,max_size_error=.2) is None:
                        continue
                else:
                    continue
            decoded.append((family,row,words,text,core,sync,synchronized))
    shared = {}
    for family,row,words,text,core,sync,synchronized in decoded:
        if core is not None and synchronized:
            shared.setdefault(sync,set()).add(core)
    cues = []
    for family,row,words,text,core,sync,synchronized in decoded:
        if core is None and synchronized and len(shared.get(sync,())) == 1:
            core = next(iter(shared[sync]))
        sample = family[0][1][0][0]
        if core is None or not sample.start_s < core[0] < core[1] < family[0][1][-1][0].end_s:
            continue
        # Internal cue evidence only; no inferred Comment is written to output.
        body = text if len(words) == 1 else ''.join(r'{\k0}'+word for word in words)
        # Keep measured spaces for the caption, while fragments identify paths.
        cues.append((replace_event(sample,kind='Comment',text=body,start=format_time(core[0]),
            start_s=core[0],end=format_time(core[1]),end_s=core[1]),text))
    return cues


def recover_vector_text_cues(parsed: dict[int,Event], metric: FontSpacing | None,
                             max_blur: float = 0.0) -> tuple[dict[int,Event],int]:
    """Recover authored captions proven by complete exact-font drawing rows.

    A comment is only a text candidate. Each whole line or karaoke fragment
    must match the font's contour commands and control points at a plausible
    common size, across a time-connected drawing run covering its cue. Existing
    font spacing checks prove fragment order and authored spaces. Clipped,
    moving, rotated, incomplete, competing and already text-backed cues reject.
    No effect names, source-line annotations or subtitle-specific values matter.
    """
    if metric is None or not metric.available:
        return parsed,0
    cues = {}
    for e in parsed.values():
        if e.kind != 'Comment' or e.duration <= 0:
            continue
        text = simplify_text(e.text,visible_only=True)[1]
        if (not text.strip() or re.search(r'\\[Nn]|[\r\n]',text) or
                any(tag not in {'k','kf','ko','kt'} for tag,value in event_override_tokens(e))):
            continue
        cues.setdefault((e.style,e.start_s,e.end_s,text),e)
    authored_styles = {cue.style for cue in cues.values()}
    styles = authored_styles|{e.style for e in parsed.values() if e.kind == 'Dialogue' and
                             re.search(r'\\p1(?![\dA-Za-z])',e.text,re.I)}
    if not styles:
        return parsed,0
    groups, backing = {}, {}
    geometry = {'fn','fs','fsp','fscx','fscy','an','b','i','u','s','pbo','encoding'}
    transform_paint = {'alpha','1a','2a','3a','4a','c','1c','2c','3c','4c',
                       'bord','xbord','ybord','blur','be'}
    for e in parsed.values():
        if e.kind != 'Dialogue' or e.style not in styles or e.duration <= 0:
            continue
        if not re.search(r'\\p1(?![\dA-Za-z])',e.text,re.I):
            if simplify_text(e.text,visible_only=True)[1].strip():
                backing.setdefault(e.style,[]).append(e)
            continue
        tokens = event_override_tokens(e)
        if (inline_layout_key(e) or any(tag in {'move','clip','iclip','org','r'} or
                tag == 't' and any(k not in transform_paint for k,v in
                    tokenize_override(value.strip('()'))) for tag,value in tokens)):
            continue
        state = effective_state(e.text,e.defaults,e.styles)
        pos = get_pos(e.text)
        if (pos is None or state.get('p',0) != 1 or int(state.get('an',5)) != 5 or
                state.get('pbo',0) or state.get('borderstyle',1) != 1 or
                not unrotated_text_state(state) or any(abs(state.get(k,0)) > .001
                    for k in ('fax','fay','u','s','i')) or
                any(state.get(k,100) != 100 for k in ('fscx','fscy')) or
                not all(math.isfinite(v) for v in (*pos,state.get('fs',20)))):
            continue
        path = geometry_key(e.text)
        skeleton = tuple(v if isinstance(v,str) else None for v in path)
        if not path or any(v not in {'m','l','b'} for v in path if isinstance(v,str)):
            continue
        key = (e.style,e.layer,e.name,e.margin_l,e.margin_r,e.margin_v,pos,
               tuple(state.get(k,DEFAULT_STATE.get(k)) for k in sorted(geometry)),skeleton)
        groups.setdefault(key,[]).append((e,path,state))
    runs = {}
    for key,items in groups.items():
        items.sort(key=lambda item:(item[0].start_s,item[0].end_s))
        components = []
        latest = float('-inf')
        for item in items:
            if not components or item[0].start_s > latest+.011:
                components.append([])
            components[-1].append(item)
            latest = max(latest,item[0].end_s)
        for component in components:
            if any(b[0].start_s < a[0].end_s-.001 for a,b in zip(component,component[1:])):
                continue
            runs.setdefault(key[0],[]).append((key,component))
    for cue,text in infer_vector_text_cues(runs,parsed,metric,authored_styles):
        cues.setdefault((cue.style,cue.start_s,cue.end_s,text),cue)
    fit_cache = {}
    def outline_fit(run, text):
        key,items = run
        cache_key = (items[0][0].source_index,text)
        if cache_key in fit_cache:
            return fit_cache[cache_key]
        fit_cache[cache_key] = None
        state = items[0][2]
        face = metric.matching_face(str(state.get('fn','')),bool(state.get('b',0)),False)
        if face is None:
            metric.missing.add(str(state.get('fn','')))
            return None
        outline = metric.cubic_outline(face,text)
        if outline is None or tuple(v if isinstance(v,str) else None for v in outline[0]) != key[-1]:
            return None
        sample = [items[i] for i in sorted({round(j*(len(items)-1)/4) for j in range(5)})]
        measured = tuple(v if isinstance(v,str) else statistics.median(item[1][i] for item in sample)
                         for i,v in enumerate(outline[0]))
        fitted = fit_cubic_points(outline[0],measured)
        if fitted is None:
            return None
        scale,_,_,error = fitted
        nominal = metric.ass_em_scale(face)
        if nominal is None:
            return None
        nominal *= state.get('fs',20)/outline[1]
        # Font drawing exporters and renderers use different line metrics.
        # Permit the same modest sizing variance, never arbitrary path fits.
        tolerance = max(items[0][0].unit,.05*state.get('fs',20))
        if nominal <= 0 or abs(scale-nominal) > .2*nominal or error > tolerance:
            return None
        visible = []
        for e,path,state in sample:
            body,_,_ = simplify_visual_text(e.text,max_blur,e.duration,e.defaults,e.styles,2)
            frozen = replace_event(e,text=body)
            if frozen.state.get('1a',0) < 16:
                visible.append(frozen)
        if not visible:
            return None
        chosen = max(visible,key=lambda e:e.duration)
        result = replace_event(chosen,text=aggressive_caption(chosen.state,text,p=0))
        fit_cache[cache_key] = result
        return result
    proposals = []
    for (_,start,end,text),cue in cues.items():
        if any(min(e.end_s,end)-max(e.start_s,start) >= .5*cue.duration
               for e in backing.get(cue.style,())):
            continue
        candidates = {}
        for run in runs.get(cue.style,()):
            key,items = run
            allowance = max(.25*cue.duration,2*statistics.median(e.duration for e,p,s in items))
            if (items[0][0].start_s > start+.011 or items[-1][0].end_s < end-.011 or
                    items[0][0].start_s < start-allowance or items[-1][0].end_s > end+allowance):
                continue
            lane = key[:6]+(key[6][1],key[7])
            candidates.setdefault(lane,[]).append(run)
        fragments = [part.strip() for part in re.split(
            r'\{[^}]*\\[kK](?:f|o|t)?\d+[^}]*\}',cue.text) if part.strip()]
        options = []
        for family in candidates.values():
            family.sort(key=lambda run:run[0][6][0])
            words = [text] if len(family) == 1 else fragments
            if (len(words) != len(family) or ''.join(''.join(w.split()) for w in words) !=
                    ''.join(text.split())):
                continue
            row = [outline_fit(run,word) for run,word in zip(family,words)]
            if any(e is None for e in row):
                continue
            x,y = get_pos(row[0].text)
            if len(row) > 1:
                measured = [dataclass_replace(e,state={**e.state,'fsp':0}) for e in row]
                recovered = metric.recover(measured,words,max_size_error=.2)
                if recovered is not None and recovered[0] == text:
                    x = recovered[1]
                elif not any(c.isspace() for c in text):
                    x = metric.fragment_anchor(measured[0].state,
                        [get_pos(e.text)[0] for e in row],words,text,row[0].unit,max_size_error=.2)
                    if x is None:
                        continue
                else:
                    continue
            body = render_merged_caption(row,words,text,animated=True,an=5,pos=(x,y),fscx=100,fscy=100)
            if body is None:
                continue
            members = {e.source_index for run in family for e,p,s in run[1]}
            first = min(members)
            caption = replace_event(row[0],source_index=first,text=body,start=cue.start,
                start_s=start,end=cue.end,end_s=end,effect='')
            options.append((members,caption))
        if len(options) == 1:
            proposals.append(options[0])
    claims = collections.Counter(index for members,caption in proposals for index in members)
    accepted = [(members,caption) for members,caption in proposals
                if all(claims[index] == 1 for index in members)]
    if not accepted:
        return parsed,0
    consumed = set().union(*(members for members,caption in accepted))
    result = {index:e for index,e in parsed.items() if index not in consumed}
    result.update((caption.source_index,caption) for members,caption in accepted)
    return result,len(accepted)


def simplify_ass(path: Path, output: Path, config: SimplifyConfig, *,
                 font_spacing: FontSpacing | None = None) -> dict[str, int]:
    if path.resolve() == output.resolve():
        raise ValueError("Subtitle output must differ from its input.")
    raw = read_subtitle(path, config.encoding)
    # ASS records use CR/LF; Unicode paragraph/line separators are text.
    lines = re.split(r"\r\n|\r|\n", raw)
    if lines and lines[-1] == "" and raw.endswith(("\n", "\r")):
        lines.pop()

    styles = parse_styles(lines)
    scaled_borders = any(line.strip().lower() == "scaledborderandshadow: yes" for line in lines)
    resolution_value = next((line.split(":",1)[1].strip() for line in lines
                             if line.strip().lower().startswith("playresy:")), "288")
    try:
        resolution_y = float(resolution_value)
        if not math.isfinite(resolution_y) or resolution_y <= 0:
            raise ValueError
    except ValueError:
        resolution_y = 288.0
        print(f"Warning: {path.name}: invalid PlayResY; using 288 for geometry.")
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
                e.defaults = styles.get(e.style, DEFAULT_STATE)
                e.styles = styles
                # Dialogue state is resolved by replace_event only after its
                # text is simplified. Unchanged comments retain their state.
                if e.kind != "Dialogue":
                    e.state = effective_state(e.text,e.defaults,styles)
                parsed_by_line[idx] = e
    max_concurrent_in = peak_concurrent_events(parsed_by_line.values())
    animated_sources = {idx for idx,e in parsed_by_line.items()
                        if re.search(r"\\(?:t\s*\(|[kK](?:f|o)?\d|fad(?:e)?\s*\(|move\s*\()", e.text)}
    source_rows = []
    source_effects = 0
    vector_text_recovered = 0
    working_by_line = parsed_by_line
    if config.level == 1:
        working_by_line, vector_text_recovered = recover_vector_text_cues(
            working_by_line,font_spacing,config.max_blur)
        # Identify original cue geometry once. Existing stages consume that
        # evidence before transformations can extend a lyric through its tail.
        working_by_line = normalize_animated_rotations(working_by_line)
        working_by_line, shrinking_effects = collapse_shrinking_glyph_rows(
            working_by_line,font_spacing,config.max_blur)
        source_data = collect_source_text_rows(working_by_line,animated_sources)
        source_events, source_effects = remove_source_fragment_effects(
            list(working_by_line.values()),source_data[0],source_data[1],source_data[2],animated_sources,
            font_spacing=font_spacing)
        source_events, _, _, source_rows = reconstruct_text_rows(
            source_events,source_data[1],{},None,animated_sources,
            source_rows=source_data[0],source_only=True)
        source_effects += shrinking_effects
        working_by_line = {e.source_index:e for e in source_events}
    simplified_events: list[Event] = []
    vector_events: list[Event] = []
    backdrops: list[tuple[Event,list]] = []
    visible_map: dict[int, str] = {}
    space_map: dict[tuple, set[float]] = {}
    dropped_drawings = 0
    original_dialogues = 0
    blank_events: list[Event] = []

    for idx, line in enumerate(lines):
        e = parsed_by_line.get(idx)
        if e is None:
            continue
        if e.kind != "Dialogue":
            simplified_events.append(e)
            continue
        original_dialogues += 1
        if idx not in working_by_line:
            continue
        e = working_by_line[idx]
        if e.duration<=0:
            # ASS events with an empty/reversed interval cannot be displayed.
            dropped_drawings += 1
            continue
        if config.level == 1 and re.search(r"\\p[1-9]\d*(?![\dA-Za-z])",e.text,re.I):
            # A cheap opaque rectangle may hide text baked into the video.
            # Keep it as a candidate until we know a retained caption actually
            # sits above it. Decorative/curved/translucent drawings still go.
            drawing,words,chars = simplify_visual_text(
                e.text,config.max_blur,e.duration,e.defaults,styles,2)
            candidate = replace_event(e,text=drawing,effect="")
            geometry = coverage_geometry(candidate,scaled_borders)
            if chars and not words and geometry is not None and geometry[2]:
                points = geometry[0]
                xs,ys = {x for x,y in points},{y for x,y in points}
                corners = {(x,y) for x in xs for y in ys}
                if (len(xs)==len(ys)==2 and len(points) in (4,5) and
                        set(points)==corners and
                        all(a==c or b==d for (a,b),(c,d) in
                            zip(points,points[1:]+points[:1]))):
                    backdrops.append((candidate,points))
            if chars and not words and not simplify_text(e.text,visible_only=True)[1]:
                # Both the frozen drawing and the original drawing switches
                # prove there is no text. Its backdrop candidate is already
                # recorded; level 1 would only freeze it again before dropping.
                visible_map[idx] = ''
                dropped_drawings += 1
                continue
        new_text, visible, drawing_chars = simplify_visual_text(
            e.text, config.max_blur, e.duration, styles.get(e.style,DEFAULT_STATE), styles, config.level,
            upright_crossings=False)
        visible_map[idx] = visible
        if drawing_chars:
            if config.max_drawing_chars <= 0 or drawing_chars <= config.max_drawing_chars:
                vector_events.append(replace_event(e, text=new_text, effect=""))
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
                blank_events.append(replace_event(e, text=new_text))
            # A dialogue event with no remaining text is generally a vector drawing/effect.
            dropped_drawings += 1
            continue
        simplified_events.append(replace_event(e, text=new_text, effect=""))

    assign_layout(simplified_events + blank_events, visible_map)
    space_map.clear()
    for e in blank_events:
        pos = get_pos(e.text)
        space_map.setdefault((e.start,e.end,e.style,e.name,e.row),set()).add(pos[0])

    aggressive_copies = masked_decorations = 0
    progressive_reveals = 0
    if config.level == 1:
        simplified_events,progressive_reveals = collapse_progressive_text_reveals(
            simplified_events,visible_map)
        simplified_events, font_decorations = remove_fragmented_font_decorations(
            simplified_events,visible_map,font_spacing,parsed_by_line)
        dropped_drawings += font_decorations
        simplified_events, masked_decorations = remove_masked_glyph_effects(
            simplified_events, visible_map, font_spacing, animated_sources)
        simplified_events, aggressive_copies = flatten_aggressive_text_copies(
            simplified_events, visible_map, animated_sources,
            max_piece_duration=config.short_duration,source_events=parsed_by_line)

    sign_copies_removed = 0
    if config.level == 1:
        simplified_events, sign_copies_removed = reduce_static_sign_copies(
            simplified_events, visible_map)

    # Reconstruct each glyph's complete lifetime before trying to assemble rows.
    simplified_events, phase_merged = coalesce_lyric_phases(
        simplified_events, visible_map)
    joined_blanks, _ = coalesce_lyric_phases(blank_events, visible_map)
    for e in joined_blanks:
        pos = get_pos(e.text)
        key = (e.start, e.end, e.style, e.name, e.row)
        space_map.setdefault(key, set()).add(round(pos[0] / e.unit, 1) * e.unit)

    tiles_joined = 0
    # Deprecated level 2 path; retain for reference and compatibility.
    if config.level == 2:
        simplified_events, tiles_joined = join_text_clip_tiles(simplified_events)

    # For visual signs, choose their visible fill before same-layer dedup can
    # discard a brighter effect copy merely because it appeared later.
    text_copies_removed = 0
    # Deprecated level 2 path; retain for reference and compatibility.
    if config.level == 2:
        simplified_events, text_copies_removed = reduce_text_layers(
            simplified_events, visible_map, vector_events)

    # Work in chronological/source order. Effect-layer dedup is safe regardless of adjacency.
    simplified_events, deduped = deduplicate_layers(simplified_events, visible_map)
    lyric_merged = 0
    overlap_removed = full_copies_removed = 0
    if config.level == 1:
        simplified_events, overlap_removed = collapse_matching_lyric_layers(
            simplified_events, visible_map)
        simplified_events, full_copies_removed = collapse_full_lyric_copies(
            simplified_events, visible_map)
    simplified_events, merged = merge_frame_animation(
        simplified_events, visible_map,
        max_piece_duration=config.short_duration,
        max_gap=config.short_gap,
        aggressive=config.level == 1,
    )
    aggressive_sequences = 0
    # Counter names remain compatible with older batch reports.
    staggered_rows = fullwidth_merged = 0
    progressive_rows = progressive_reveals
    overlaid_letters = covered_fragments = cue_overlaps_trimmed = 0
    if config.level == 1:
        simplified_events, aggressive_sequences = flatten_aggressive_text_sequences(
            simplified_events, visible_map, styles, animated_sources,
            source_events=parsed_by_line,font_spacing=font_spacing)
        authored_rows: list[TextRow] = []
        simplified_events, overlaid_letters = remove_letters_over_full_lines(
            simplified_events, visible_map,parsed_by_line,authored_rows,font_spacing=font_spacing)
        simplified_events, lyric_merged, row_duplicates, row_evidence = reconstruct_text_rows(
            simplified_events, visible_map, space_map, font_spacing, animated_sources,
            source_rows=source_rows,source_events=parsed_by_line)
        deduped += row_duplicates
        simplified_events, covered_fragments = remove_covered_fragment_effects(
            simplified_events, visible_map, row_evidence+authored_rows, animated_sources,parsed_by_line,font_spacing)
        covered_fragments += source_effects
        simplified_events, cue_overlaps_trimmed = trim_faded_cue_overlaps(
            simplified_events,row_evidence+authored_rows,parsed_by_line)
    covered_vectors = 0
    vector_copies_removed = vector_glows_removed = vector_frames_removed = excess_vectors = 0
    # Deprecated level 2 path; retain for reference and compatibility.
    if config.level == 2:
        simplified_events, remaining_copies = reduce_text_layers(simplified_events, visible_map, vector_events)
        text_copies_removed += remaining_copies
        vector_events, vector_copies_removed = reduce_vector_layers(vector_events)
        vector_events, vector_frames_removed = freeze_vector_sequences(vector_events, config.short_duration)
        vector_events, vector_glows_removed = remove_covered_vector_glows(vector_events)
        vector_events, covered_vectors = remove_fully_covered_vectors(vector_events, scaled_borders)
        vector_events, excess_vectors = cap_vector_cues(vector_events, config.max_vectors_per_cue)
        simplified_events = sorted(simplified_events + vector_events, key=lambda e: e.source_index)

    backdrops_retained = 0
    if config.level == 1:
        captions = [(e,get_pos(e.text)) for e in simplified_events
                    if e.kind=="Dialogue" and visible_map.get(e.source_index) and
                    not e.state.get("p",0) and get_pos(e.text) is not None and
                    e.layer.lstrip("-").isdigit()]
        raised_layers = {}
        for backdrop,points in backdrops:
            order = (int(backdrop.layer),backdrop.source_index)
            pad = .5*backdrop.unit
            covered_captions = []
            for caption,pos in captions:
                source = parsed_by_line.get(caption.source_index,caption)
                if (not source.layer.lstrip("-").isdigit() or
                        (int(source.layer),source.source_index)<=order or
                        backdrop.start_s > caption.start_s+.001 or
                        backdrop.end_s < caption.end_s-.001):
                    continue
                if polygon_covers_box(points,(pos[0]-pad,pos[1]-pad,pos[0]+pad,pos[1]+pad)):
                    covered_captions.append(caption)
            if covered_captions:
                vector_events.append(backdrop)
                backdrops_retained += 1
                dropped_drawings -= 1
                # Reconstructed lyrics may have been moved to layer zero.
                # Restore their order above any backdrop that now survives.
                for caption in covered_captions:
                    raised_layers[caption.source_index] = max(
                        raised_layers.get(caption.source_index,int(caption.layer)),int(backdrop.layer)+1)
        simplified_events = [replace_event(e,layer=str(raised_layers[e.source_index]))
                             if e.source_index in raised_layers else e for e in simplified_events]
        simplified_events = sorted(simplified_events+vector_events,key=lambda e:e.source_index)
        simplified_events = prefer_surviving_upright_poses(simplified_events,parsed_by_line)
        # Late generators emit full state headers. Compact them only after
        # source-dependent effect/timing proofs, then remove exact duplicates
        # whose formerly redundant tag spelling hid their identity.
        simplified_events = compact_static_overrides(simplified_events,config.max_blur)
        simplified_events, final_duplicates = deduplicate_layers(simplified_events,visible_map)
        deduped += final_duplicates
        # Finished geometry can connect differently divided animation phases.
        # Run after rotation/origin cleanup, without disturbing earlier source
        # effect proofs. The shared overlap pass owns the proven cue handoffs.
        simplified_events, translated_merged, translated_rows = collapse_translated_phase_rows(
            simplified_events,visible_map,font_spacing)
        simplified_events, phase_rows_merged, phase_rows = collapse_fragment_phase_rows(
            simplified_events,visible_map,font_spacing)
        phase_rows = translated_rows+phase_rows
        aggressive_sequences += translated_merged+phase_rows_merged
        if phase_rows:
            simplified_events, phase_overlaps = trim_faded_cue_overlaps(
                simplified_events,phase_rows,{})
            cue_overlaps_trimmed += phase_overlaps
            simplified_events = compact_static_overrides(simplified_events,config.max_blur)
        # Effect removal and timing cleanup can uncover complete static rows.
        # Reuse the same source comments, spacing and neighbor checks without
        # extending lifetimes or selecting new animation/foreground paint.
        simplified_events, final_rows_merged, _, _ = reconstruct_text_rows(
            simplified_events,visible_map,space_map,font_spacing,animated_sources,
            static_only=True)
        lyric_merged += final_rows_merged
        if final_rows_merged:
            simplified_events = compact_static_overrides(simplified_events,config.max_blur)

    static_merged = 0
    # Join final touching static objects after all layout and timing changes.
    if config.level in (1,2):
        simplified_events, static_merged = merge_static_timed_copies(simplified_events, styles)

    # Rebuild [Events] while preserving all non-dialogue/event metadata lines.
    # We replace Dialogue/Comment lines at their original region with the processed sequence.
    event_line_indices = sorted(parsed_by_line)
    if not event_line_indices:
        output.write_text("\n".join(mark_generated(lines)) +
                          ("\n" if raw.endswith(("\n", "\r")) else ""), encoding="utf-8-sig")
        return {key: 0 for key in ("original", "output", "max_concurrent_in", "max_concurrent_out",
                "deduped", "lyric_merged",
                "merged", "dropped", "overlap_removed", "cue_overlaps_trimmed", "vector_text_recovered", "full_copies_removed", "phase_merged",
                "text_copies_removed", "vector_copies_removed", "vector_glows_removed",
                "vector_frames_removed", "vector_output", "excess_vectors", "static_merged", "covered_vectors", "tiles_joined", "aggressive_copies", "aggressive_sequences", "staggered_rows", "overlaid_letters", "covered_fragments", "fullwidth_merged", "progressive_rows", "masked_decorations", "backdrops_retained")}

    first_event_line = event_line_indices[0]
    last_event_line = event_line_indices[-1]
    before = lines[:first_event_line]
    after = lines[last_event_line + 1:]

    rendered = []
    for e in simplified_events:
        data = dict(zip(EVENT_FIELDS,e.fields()))
        data.update(actor=e.name, marked="Marked=0")
        rendered.append(f"{e.kind}: " + ",".join(data.get(key,"") for key in event_fields))

    final_lines = mark_generated(before + rendered + after)
    output.write_text("\n".join(final_lines) + ("\n" if raw.endswith(("\n", "\r")) else ""),
                      encoding="utf-8-sig")

    vector_source_indices = {v.source_index for v in vector_events}
    output_dialogues = sum(1 for e in simplified_events if e.kind == "Dialogue")
    return {
        "original": original_dialogues,
        "max_concurrent_in": max_concurrent_in,
        "max_concurrent_out": peak_concurrent_events(simplified_events),
        "backdrops_retained": backdrops_retained,
        "vector_text_recovered": vector_text_recovered,
        "static_merged": static_merged,
        "covered_vectors": covered_vectors,
        "tiles_joined": tiles_joined,
        "aggressive_copies": aggressive_copies,
        "masked_decorations": masked_decorations,
        "aggressive_sequences": aggressive_sequences,
        "staggered_rows": staggered_rows,
        "fullwidth_merged": fullwidth_merged,
        "progressive_rows": progressive_rows,
        "overlaid_letters": overlaid_letters,
        "covered_fragments": covered_fragments,
        "phase_merged": phase_merged,
        "output": output_dialogues,
        "deduped": deduped + sign_copies_removed,
        "lyric_merged": lyric_merged,
        "overlap_removed": overlap_removed,
        "cue_overlaps_trimmed": cue_overlaps_trimmed,
        "full_copies_removed": full_copies_removed,
        "merged": merged,
        "text_copies_removed": text_copies_removed,
        "vector_copies_removed": vector_copies_removed,
        "vector_glows_removed": vector_glows_removed,
        "vector_frames_removed": vector_frames_removed,
        "vector_output": sum(e.source_index in vector_source_indices
                             for e in simplified_events),
        "excess_vectors": excess_vectors,
        "dropped": dropped_drawings,
    }


def iter_inputs(targets: Iterable[str], recursive: bool, suffix: str = ".simple") -> list[Path]:
    found: list[Path] = []
    for target in targets:
        p = Path(target)
        if p.is_file():
            # An explicit file is intentional, including a suffix-like name.
            if p.suffix.lower() in {".ass", ".ssa"}:
                found.append(p)
        elif p.is_dir():
            pattern = "**/*" if recursive else "*"
            for f in p.glob(pattern):
                if not f.is_file() or f.suffix.lower() not in {".ass", ".ssa"}:
                    continue
                # Preserve the established default-output exclusion for older
                # files without a marker. Custom suffixes can be source names.
                if suffix.lower() == ".simple" and f.stem.lower().endswith(".simple"):
                    continue
                try:
                    with f.open("rb") as stream:
                        generated = any(line.removeprefix(codecs.BOM_UTF8).strip() ==
                                        GENERATED_MARKER.encode("utf-8") for line in islice(stream,40))
                    if generated:
                        continue
                except OSError:
                    pass  # Let the per-file batch handler report unreadable inputs.
                found.append(f)
        else:
            print(f"Warning: not found: {p}")
    return sorted(set(found))


def extract_mkv_fonts(mkv: Path, destination: Path) -> None:
    """Read attached fonts into a private temporary directory; never edit MKV."""
    import json
    import shutil
    import subprocess
    merge, extract = shutil.which('mkvmerge'), shutil.which('mkvextract')
    if not merge or not extract:
        raise ValueError('--font-mkv requires mkvmerge and mkvextract in PATH')
    if not mkv.is_file():
        raise ValueError(f'Font source MKV not found: {mkv}')
    result = subprocess.run([merge,'-J',str(mkv.resolve())], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=120)
    if result.returncode not in (0,1):
        raise ValueError('Could not inspect MKV fonts: '+result.stderr.strip())
    try:
        attachments = json.loads(result.stdout).get('attachments',[])
    except json.JSONDecodeError as exc:
        raise ValueError(f'Could not parse mkvmerge JSON output: {exc}') from exc
    targets = []
    for attachment in attachments:
        suffix = Path(attachment.get('file_name','')).suffix.lower()
        mime = attachment.get('content_type','').lower()
        if suffix not in {'.ttf','.otf','.ttc','.otc'}:
            if mime not in {'application/x-truetype-font','application/vnd.ms-opentype',
                            'application/x-font-ttf','application/x-font-opentype',
                            'font/ttf','font/otf','font/collection','application/font-sfnt'}:
                continue
            suffix = '.ttc' if mime == 'font/collection' else '.ttf'
        identifier = int(attachment['id'])
        # Attachment filenames are untrusted. Use only a numeric ID locally.
        path = destination / f'font_{identifier}{suffix}'
        targets.append((identifier,path))
    if targets:
        result = subprocess.run([extract,str(mkv.resolve()),'attachments'] +
                                [f'{identifier}:{path}' for identifier,path in targets],
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=120)
        if result.returncode not in (0,1) or any(not path.is_file() for _,path in targets):
            raise ValueError('Could not extract attached fonts: '+result.stderr.strip())
    print(f'Loaded {len(targets)} attached font files from {mkv.name}')


def text_drop_warnings(stats):
    """Stable per-track warning records; ordinary effect merging is not a loss."""
    count = stats.get('prototype_scrolling_events_removed', 0)
    if not count:
        return []
    limit = stats['prototype_scrolling_concurrency_limit']
    return [{'code': 'scrolling_text_dropped', 'severity': 'warning',
             'events': count, 'concurrency_limit': limit,
             'blocks': stats['prototype_scrolling_blocks_removed'],
             'peak_concurrent': stats['prototype_scrolling_peak_after_reduction'],
             'message': f'Dropped {count} events due to exceeding concurrent event limit '
                        f'{limit} for scrolling text blocks.'}]


def print_text_drop_warning(warning, context, stream=None):
    """Readable redirected logs, and a bold red banner on supported consoles."""
    import os
    stream = sys.stderr if stream is None else stream
    color = bool(getattr(stream, 'isatty', lambda: False)())
    if color and os.name == 'nt':
        # Enable virtual-terminal colours on Windows consoles, restoring the
        # previous mode afterward. A redirected stream gets plain text.
        import ctypes
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        mode = ctypes.c_ulong()
        try:
            handle = msvcrt.get_osfhandle(stream.fileno())
            color = bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and
                         kernel.SetConsoleMode(handle, mode.value | 4))
        except (AttributeError, OSError, ValueError):
            color = False
    prefix, suffix = ('\033[1;31m', '\033[0m') if color else ('', '')
    try:
        print(f'{prefix}{"="*78}\nWARNING: {warning["message"]}\n{context}\n{"="*78}{suffix}',
              file=stream)
    finally:
        if color and os.name == 'nt':
            kernel.SetConsoleMode(handle, mode.value)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Simplify ASS/SSA subtitles for limited renderers. Level 1 reduces effects and retains supporting backdrops; level 2 is deprecated and retained for compatibility."
    )
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("inputs", nargs="+", help="ASS/SSA file(s) or folder(s)")
    ap.add_argument("-r", "--recursive", action="store_true", help="scan folders recursively")
    ap.add_argument("--level", type=int, choices=(1, 2), default=1,
                    help="1: maximum reduction (default); 2: deprecated legacy static-visual pipeline")
    ap.add_argument("--suffix", default=".simple", help="output suffix before extension (default: .simple); scans skip marked outputs")
    ap.add_argument("--encoding", help="input encoding override for legacy or BOM-less files; "
                    "default: UTF-8 or BOM-marked UTF-16/UTF-32, decoded strictly")
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
    ap.add_argument("--scroll-concurrency-limit", type=int, default=32,
                    help="level 1 scrolling-text fallback: drop a proved block only when its "
                    "remaining peak exceeds this count after ordinary reduction "
                    "(default 32; 0 disables text dropping)")
    ap.add_argument("--fonts-dir", action="append", default=[], metavar="FOLDER",
                    help="extra font folder (repeatable); exact fonts enable measured word spacing")
    ap.add_argument("--font-mkv", type=Path, metavar="FILE",
                    help="read font attachments from this MKV using MKVToolNix; source stays untouched")
    ap.add_argument("--no-font-spacing", action="store_true",
                    help="disable measured spacing; preserve uncertain fragment positions")
    ap.add_argument("--stats-json", type=Path, metavar="FILE",
                    help="also write per-input event counts as JSON for batch reports")
    args = ap.parse_args()

    if args.scroll_concurrency_limit < 0:
        ap.error("--scroll-concurrency-limit must be nonnegative")

    if not args.suffix.strip() or any(c in args.suffix for c in '/\\:*?"<>|'):
        ap.error("--suffix must be nonempty and contain no filename separators or reserved characters")
    if args.encoding:
        try:
            codecs.lookup(args.encoding)
        except LookupError:
            ap.error(f"Unknown input encoding: {args.encoding}")
    if args.level == 2:
        print("WARNING: Level 2 is deprecated; use level 1 for current simplification.",
              file=sys.stderr)
    inputs = iter_inputs(args.inputs, args.recursive, args.suffix)
    if not inputs:
        ap.error("No .ass/.ssa files found")

    config = SimplifyConfig(level=args.level, max_blur=args.max_blur,
        short_duration=args.short_duration, short_gap=args.short_gap,
        max_drawing_chars=args.max_drawing_chars,
        max_vectors_per_cue=args.max_vectors_per_cue, encoding=args.encoding,
        scroll_concurrency_limit=args.scroll_concurrency_limit)
    font_temp = None
    try:
        metric = None
        if args.level == 1 and not args.no_font_spacing:
            folders = args.fonts_dir + [p.parent / "fonts" for p in inputs]
            if args.font_mkv:
                import tempfile
                font_temp = tempfile.TemporaryDirectory(prefix="ass-fonts-")
                extract_mkv_fonts(args.font_mkv, Path(font_temp.name))
                folders.insert(0, font_temp.name)
            metric = FontSpacing(folders)
            if not metric.available:
                print("Font spacing unavailable. Enable with: python -m pip install Pillow fonttools")
            else:
                from PIL import features
                if not features.check_feature("raqm") and metric.harfbuzz is None:
                    print("RAQM unavailable: install the portable measurement backend with: "
                          "python -m pip install uharfbuzz (unmerged rows keep original timing)")
        total_in = total_out = 0
        records = []
        failed = 0
        input_paths = {src.resolve() for src in inputs}
        for src in inputs:
            dst = src.with_name(src.stem + args.suffix + src.suffix)
            track_started = time.perf_counter()
            try:
                if dst.resolve() in input_paths:
                    raise ValueError(f"Output is another input file: {dst}; choose a different --suffix.")
                stats = simplify_ass(src, dst, config, font_spacing=metric)
            except (ValueError,OSError) as exc:
                failed += 1
                records.append({"input":str(src.resolve()),"output":str(dst.resolve()),
                                "error":str(exc),
                                "processing_seconds": time.perf_counter() - track_started})
                print(f"Error: {src.name}: {exc}",file=sys.stderr)
                continue
            total_in += stats["original"]
            total_out += stats["output"]
            warnings = text_drop_warnings(stats)
            records.append({"input": str(src.resolve()),
                            "output": str(dst.resolve()), "stats": stats,
                            "warnings": warnings,
                            "processing_seconds": time.perf_counter() - track_started})
            for warning in warnings:
                print_text_drop_warning(warning, src.name)
            print(f"{src.name} -> {dst.name} (level {args.level})")
            print(f"  Processing time: {records[-1]['processing_seconds']:.3f} seconds")
            print(f"  Peak simultaneous events: {stats['max_concurrent_in']} -> "
                  f"{stats['max_concurrent_out']}")
            print(
                f"  dialogue events: {stats['original']} -> {stats['output']} "
                f"(duplicate layers removed: {stats['deduped']}, "
                f"lyric fragments merged: {stats['lyric_merged']}, "
                f"glyph phases merged: {stats['phase_merged']}, "
                f"overlapping effects removed: {stats['overlap_removed']}, "
                f"cue overlaps trimmed: {stats['cue_overlaps_trimmed']}, "
                f"full lyric copies removed: {stats['full_copies_removed']}, "
                f"frame pieces merged: {stats['merged']}, "
                f"identical timed copies merged: {stats['static_merged']}, "
                f"duplicate sign text: {stats['text_copies_removed']}, "
                f"masked texture copies removed: {stats['masked_decorations']}, "
                f"identical text strips joined: {stats['tiles_joined']}, "
                f"stacked text copies flattened: {stats['aggressive_copies']}, "
                f"text effect sequences frozen: {stats['aggressive_sequences']}, "
                f"covered fragment effects removed: {stats['covered_fragments']}, "
                f"vector copies: {stats['vector_copies_removed']}, "
                f"covered contours: {stats['vector_glows_removed']}, "
                f"fully covered drawings: {stats['covered_vectors']}, "
                f"drawing animation frames: {stats['vector_frames_removed']}, "
                f"vectors retained: {stats['vector_output']}, "
                f"caption backdrops retained: {stats['backdrops_retained']}, "
                f"vector captions recovered: {stats['vector_text_recovered']}, "
                f"excess vector details removed: {stats['excess_vectors']}, "
                f"drawings/effects dropped before reconstruction: {stats['dropped']})"
            )
    
        if metric is not None and metric.available:
            print(f"Rows joined using font measurements: {metric.merged}")
            if metric.missing:
                print("Exact fonts unavailable (kept positions): " + ", ".join(sorted(metric.missing)))
        if len(inputs) > 1:
            print(f"Total dialogue events: {total_in} -> {total_out}")
        if failed:
            print(f"Failed files: {failed}/{len(inputs)}",file=sys.stderr)
        if args.stats_json:
            import json
            args.stats_json.parent.mkdir(parents=True, exist_ok=True)
            args.stats_json.write_text(json.dumps({"level": args.level,
                                                   "tracks": records},
                                                  ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        return 1 if failed else 0
    except (ValueError,OSError) as exc:
        ap.error(str(exc))
    finally:
        if font_temp is not None:
            font_temp.cleanup()



# Experimental post-pass. The v100 pipeline above remains the text engine.
# Geometry and font-based decisions are local to this pass; no persistent
# foreground/background classification is added to Event or FontSpacing.

def prototype_text_box(event, metric, *, adjacency=False):
    """Conservative positioned line box, using the exact ASS font metrics.

    Missing fonts, inline layout and projective text are deliberately unknown.
    A box is used to prove containment, never inferred from an anchor alone.
    """
    st = event.state
    pos = get_pos(event.text)
    if (metric is None or not metric.available or pos is None or
            inline_layout_key(event) or st.get('p', 0) or
            st.get('pbo', 0) or
            (not adjacency and any(st.get(k, 0) for k in ('frx', 'fry'))) or
            (adjacency and any(abs(math.remainder(st.get(k, 0), 360)) > 5
                               for k in ('frx', 'fry'))) or
            'clip' in st or 'iclip' in st):
        return None
    # Some captions are painted by their opaque shadow, with an effectively
    # invisible primary and no outline. Measure that visible ink at its screen
    # offset; counting the offset again as padding would invent extra bounds.
    if (st.get('1a', 0) >= 254 and st.get('4a', 0) < 254 and
            st.get('borderstyle', 1) == 1 and
            max(abs(st.get(k, st.get('bord', 0))) for k in ('xbord', 'ybord')) == 0 and
            all(abs(st.get(k, 0)) <= .001 for k in ('frz', 'frx', 'fry', 'fax', 'fay'))):
        dx, dy = (st.get(k, st.get('shad', 0)) for k in ('xshad', 'yshad'))
        if dx or dy:
            pos = (pos[0]+dx, pos[1]+dy)
            st = {**st, 'shad': 0, 'xshad': 0, 'yshad': 0}
    visible = OVERRIDE_RE.sub('', event.text).replace(r'\h', ' ')
    # A soft break only creates a new line under wrap mode 2. Under other
    # modes it is a space; treating it as a line would underestimate width.
    if st.get('q', st.get('_prototype_wrap_mode', 0)) != 2:
        visible = visible.replace(r'\n', ' ')
    lines = re.split(r'\\[Nn]', visible)
    face = metric.matching_face(str(st.get('fn', '')), bool(st.get('b', 0)),
                                bool(st.get('i', 0)))
    if face is None or any(ord(c) not in face[2] for line in lines for c in line):
        return None
    factor = metric.ass_em_scale(face)
    fs, sx, sy = (st.get('fs', 20), st.get('fscx', 100), st.get('fscy', 100))
    if factor is None or min(fs, sx, sy) <= 0:
        return None
    try:
        widths = [metric.measure(face, line, bool(st.get('kerning', False))) *
                  fs * sx / 102400 * factor +
                  len(line) * st.get('fsp', 0) * sx / 100 for line in lines]
    except (OSError, ValueError, RuntimeError):
        return None
    width, height = max(widths), fs * sy / 100 * len(lines)
    if width <= 0 or height <= 0:
        return None
    an = int(st.get('an', 2))
    if an not in range(1, 10):
        return None
    x0 = pos[0] - ((an-1) % 3) / 2 * width
    y0 = pos[1] - (1-(an-1)//3/2) * height
    x1, y1 = x0+width, y0+height
    font = metric.loaded.get(face[:2])
    if (font is not None and font.layout_engine == metric.ImageFont.Layout.RAQM and
            not st.get('fsp', 0)):
        # ASS alignment uses the line box, but backgrounds only need to
        # surround the actual ink. Do not mistake the font's blank ascender
        # and descender space for visible glyph geometry.
        from fontTools.ttLib import TTFont
        cache = getattr(metric, '_prototype_line_metrics', None)
        if cache is None:
            cache = metric._prototype_line_metrics = {}
        if face[:2] not in cache:
            with TTFont(BytesIO(metric.font_bytes[face[0]]), fontNumber=face[1]) as tf:
                os2 = tf['OS/2']
                cache[face[:2]] = os2.usWinAscent/(os2.usWinAscent+os2.usWinDescent)
        ascent = cache[face[:2]]*fs*sy/100
        features = ['kern' if st.get('kerning', False) else '-kern']
        ink_boxes = []
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            left, top, right, bottom = font.getbbox(line, anchor='ls', features=features)
            origin_x = pos[0]-((an-1) % 3)/2*widths[i]
            baseline_y = y0+i*fs*sy/100+ascent
            fx, fy = fs*sx/102400*factor, fs*sy/102400*factor
            ink_boxes.append((origin_x+left*fx, baseline_y+top*fy,
                              origin_x+right*fx, baseline_y+bottom*fy))
        if ink_boxes:
            x0, y0 = min(b[0] for b in ink_boxes), min(b[1] for b in ink_boxes)
            x1, y1 = max(b[2] for b in ink_boxes), max(b[3] for b in ink_boxes)
    pad = max(2*event.unit, abs(st.get('xbord', st.get('bord', 0))),
              abs(st.get('ybord', st.get('bord', 0))),
              abs(st.get('xshad', st.get('shad', 0))),
              abs(st.get('yshad', st.get('shad', 0))))
    # Overhangs and synthetic bold/italic need clearance beyond the advance.
    pad += .08 * fs * max(sx, sy) / 100
    if adjacency:
        # This is a proximity estimate, never a full coverage proof. A small
        # projective pose gets extra clearance; steep perspectives stay unknown.
        pad += math.hypot(width, height)*sum(abs(math.sin(math.radians(st.get(k, 0))))
                                           for k in ('frx', 'fry'))
    points = [(x0-pad, y0-pad), (x1+pad, y0-pad),
              (x1+pad, y1+pad), (x0-pad, y1+pad)]
    origin = st.get('org', pos)
    angle = math.radians(-st.get('frz', 0))
    transformed = []
    for x, y in points:
        x, y = x-origin[0], y-origin[1]
        x, y = x + st.get('fax', 0)*y, y + st.get('fay', 0)*x
        transformed.append((origin[0]+x*math.cos(angle)-y*math.sin(angle),
                            origin[1]+x*math.sin(angle)+y*math.cos(angle)))
    xs, ys = zip(*transformed)
    box = (min(xs), min(ys), max(xs), max(ys))
    return box if all(math.isfinite(v) for v in box) else None


def prototype_simple_path(event, *, max_vertices=8):
    """One finite straight-sided contour with at most eight distinct vertices."""
    raw = OVERRIDE_RE.sub('', event.text).strip()
    tokens = geometry_key(event.text)
    if (re.sub(NUMBER+r'|[A-Za-z]|\s+', '', raw) or not tokens or
            tokens[0] != 'm' or sum(x == 'm' for x in tokens) != 1 or
            any(isinstance(x, str) and x not in {'m', 'l'} for x in tokens)):
        return None
    points = []
    i = 0
    while i < len(tokens):
        command = tokens[i]; i += 1
        coords = []
        while i < len(tokens) and isinstance(tokens[i], float):
            coords.append(tokens[i]); i += 1
        if ((command == 'm' and len(coords) != 2) or
                (command == 'l' and (len(coords) < 2 or len(coords) % 2)) or
                any(not math.isfinite(v) for v in coords)):
            return None
        points.extend(zip(coords[::2], coords[1::2]))
    if points and points[-1] == points[0]:
        points.pop()
    if (len(set(points)) < 3 or (max_vertices is not None and
            (len(set(points)) > max_vertices or len(points) > max_vertices+1))):
        return None
    area = abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                   zip(points, points[1:]+points[:1]))) / 2
    return points if area > 0 else None


def prototype_flat_rectangle_border(event, *, scaled_borders=True):
    """Fold a same-colour rectangular stroke into its simple solid fill."""
    st = event.state
    points = prototype_simple_path(event)
    if (not scaled_borders or points is None or len(points) != 4 or st.get('borderstyle', 1) != 1 or
            st.get('1c', 'FFFFFF') != st.get('3c', '000000') or
            st.get('1a', 0) != st.get('3a', 0) or st.get('1a', 0) >= 254 or
            any(st.get(k, 0) for k in ('frz', 'frx', 'fry', 'fax', 'fay', 'pbo'))):
        return event
    xs, ys = sorted({x for x, y in points}), sorted({y for x, y in points})
    if (len(xs) != 2 or len(ys) != 2 or
            set(points) != {(x, y) for x in xs for y in ys} or
            any(ax != bx and ay != by for (ax, ay), (bx, by) in
                zip(points, points[1:]+points[:1]))):
        return event
    sx = st.get('fscx', 100)/(100*2**(st.get('p', 1)-1))
    sy = st.get('fscy', 100)/(100*2**(st.get('p', 1)-1))
    bx, by = abs(st.get('xbord', st.get('bord', 0))), abs(st.get('ybord', st.get('bord', 0)))
    if min(sx, sy) <= 0 or not (bx or by):
        return event
    # Preserve the drawing anchor before expanding its stroked footprint.
    event = prototype_normalize_alignment(event)
    x0, x1 = xs[0]-bx/sx, xs[1]+bx/sx
    y0, y1 = ys[0]-by/sy, ys[1]+by/sy
    block = OVERRIDE_RE.match(event.text)
    raw = f'm {x0:g} {y0:g} l {x1:g} {y0:g} {x1:g} {y1:g} {x0:g} {y1:g}'
    tags = block.group()[:-1]+r'\bord0\xbord0\ybord0'+'}'
    return replace_event(event, text=tags+raw)


def prototype_normalize_alignment(event):
    """Express an unrotated drawing's alignment as an equivalent an7 pose."""
    st = event.state
    alignment = st.get('an', 7)
    if alignment == 7 or alignment not in range(1, 10):
        return event
    if any(st.get(k, 0) for k in ('frz', 'frx', 'fry', 'fax', 'fay', 'pbo')):
        return event
    points = prototype_simple_path(event, max_vertices=None)
    pos = get_pos(event.text)
    if points is None or pos is None or st.get('p', 0) < 1:
        return event
    scale = 2 ** (st['p']-1)
    sx, sy = st.get('fscx', 100)/(100*scale), st.get('fscy', 100)/(100*scale)
    if sx <= 0 or sy <= 0:
        return event
    xs, ys = zip(*points)
    x = pos[0] - ((alignment-1) % 3)/2 * (max(xs)-min(xs))*sx
    y = pos[1] - (2-(alignment-1)//3)/2 * (max(ys)-min(ys))*sy
    block = OVERRIDE_RE.match(event.text)
    if block is None:
        return event
    tags = re.sub(r'\\an\d+|\\pos\([^)]*\)', '', block.group()[:-1], flags=re.I)
    return replace_event(event, text=tags+f'\\an7\\pos({x:g},{y:g})}}'+event.text[block.end():])


def prototype_rectangle_bias(points):
    """Prefer the original bounds when a contour closely follows a rectangle."""
    xs, ys = zip(*points)
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    side, box_area = min(x1-x0, y1-y0), (x1-x0)*(y1-y0)
    if side <= 0:
        return None
    area = abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                   zip(points, points[1:]+points[:1])))/2
    if not .85*box_area <= area <= box_area*(1+1e-9):
        return None
    tolerance = .15*side+1e-9
    for a, b in zip(points, points[1:]+points[:1]):
        # Also test the segment midpoint: matching the four extremes alone
        # would turn diagonal sides or a deep inward notch into a rectangle.
        for x, y in (a, ((a[0]+b[0])/2, (a[1]+b[1])/2)):
            if min(x-x0, x1-x, y-y0, y1-y) > tolerance:
                return None
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]



def prototype_detach_edge_slivers(event):
    """Separate tiny exterior triangles from one nearly rectangular panel.

    Do not discard holes, intersecting contours or independent artwork. The
    triangle must touch the main boundary but have no filled interior in it.
    Test every boundary-partitioned segment, including collinear/tangent hits,
    rather than relying on vertices or the overall drawing bounds.
    """
    raw = OVERRIDE_RE.sub('', event.text).strip()
    block = OVERRIDE_RE.match(event.text)
    parts = [part.strip() for part in re.split(r'(?=\bm\s)', raw, flags=re.I)
             if part.strip()]
    if block is None or not 2 <= len(parts) <= 5:
        return event, 0
    fragments = [replace_event(event, text=block.group()+part) for part in parts]
    polygons = [prototype_simple_path(e, max_vertices=None) for e in fragments]
    if any(p is None or len(p) > 4096 for p in polygons):
        return event, 0
    def area(p):
        return abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                       zip(p, p[1:]+p[:1])))/2
    index = max(range(len(polygons)), key=lambda i: area(polygons[i]))
    main = polygons[index]
    if prototype_rectangle_bias(main) is None or coverage_geometry(fragments[index]) is None:
        return event, 0
    xs, ys = zip(*main)
    side = min(max(xs)-min(xs), max(ys)-min(ys))
    eps = 1e-8*max(1, side)
    def cross(a, b):
        return a[0]*b[1]-a[1]*b[0]
    def sub(a, b):
        return a[0]-b[0], a[1]-b[1]
    def on_edge(p, a, b):
        return (abs(cross(sub(p, a), sub(b, a))) <= eps*max(1, math.dist(a, b)) and
                min(a[0], b[0])-eps <= p[0] <= max(a[0], b[0])+eps and
                min(a[1], b[1])-eps <= p[1] <= max(a[1], b[1])+eps)
    edges = list(zip(main, main[1:]+main[:1]))
    def inside(p, polygon):
        if any(on_edge(p, a, b) for a, b in zip(polygon, polygon[1:]+polygon[:1])):
            return False  # Boundary contact is permitted, filled overlap is not.
        crossings = winding = 0
        for a, b in zip(polygon, polygon[1:]+polygon[:1]):
            if a[1] <= p[1] < b[1] or b[1] <= p[1] < a[1]:
                hit = a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
                if hit > p[0]:
                    crossings += 1
                    winding += 1 if b[1] > a[1] else -1
        return bool(crossings % 2 or winding)
    for i, triangle in enumerate(polygons):
        if i == index:
            continue
        tx, ty = zip(*triangle)
        if (len(triangle) != 3 or area(triangle) > .001*area(main) or
                max(max(tx)-min(tx), max(ty)-min(ty)) > .05*side or
                not any(on_edge(p, a, b) for p in triangle for a, b in edges) or
                any(inside(p, main) for p in triangle) or
                any(inside(p, triangle) for p in main)):
            return event, 0
        for a, b in zip(triangle, triangle[1:]+triangle[:1]):
            delta = sub(b, a)
            length2 = delta[0]**2+delta[1]**2
            if length2 <= eps**2:
                return event, 0
            cuts = {0.0, 1.0}
            for c, d in edges:
                other = sub(d, c)
                determinant = cross(delta, other)
                if abs(determinant) > eps*max(1, math.dist(a, b), math.dist(c, d)):
                    t = cross(sub(c, a), other)/determinant
                    u = cross(sub(c, a), delta)/determinant
                    if 0 <= t <= 1 and 0 <= u <= 1:
                        cuts.add(t)
                else:
                    for p in (c, d):
                        if on_edge(p, a, b):
                            cuts.add(max(0, min(1, (sub(p, a)[0]*delta[0]+sub(p, a)[1]*delta[1])/length2)))
            ordered = sorted(cuts)
            if any(inside((a[0]+(lo+hi)/2*delta[0], a[1]+(lo+hi)/2*delta[1]), main)
                   for lo, hi in zip(ordered, ordered[1:])):
                return event, 0
    return fragments[index], len(parts)-1


def prototype_reduce_contour(event):
    """Simplify a jagged single outer contour with bounded geometric error.

    Nearly rectangular contours prefer a rectangle with their original bounds.
    Other shapes retain the bounded contour reduction. Both the original fill
    and the reduced fill must later cover the measured text.
    """
    points = prototype_simple_path(event, max_vertices=None)
    info = coverage_geometry(event)
    if points is None or info is None or len(points) > 4096:
        return None
    rectangle = prototype_rectangle_bias(points)
    if rectangle is not None:
        raw = 'm '+f'{rectangle[0][0]:g} {rectangle[0][1]:g} l '+ ' '.join(
            f'{x:g} {y:g}' for x, y in rectangle[1:])
        return raw, info[0]
    def area(poly):
        return abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                       zip(poly, poly[1:]+poly[:1])))/2
    def segment_distance(point, a, b):
        vx, vy = b[0]-a[0], b[1]-a[1]
        d = vx*vx+vy*vy
        t = max(0, min(1, ((point[0]-a[0])*vx+(point[1]-a[1])*vy)/d)) if d else 0
        return math.hypot(point[0]-a[0]-t*vx, point[1]-a[1]-t*vy)
    def reduce_open(poly, tolerance):
        retain, todo = {0, len(poly)-1}, [(0, len(poly)-1)]
        while todo:
            first, last = todo.pop()
            if last <= first+1:
                continue
            distance, i = max((segment_distance(poly[j], poly[first], poly[last]), j)
                              for j in range(first+1, last))
            if distance > tolerance:
                retain.add(i); todo.extend([(first, i), (i, last)])
        return [poly[i] for i in sorted(retain)]
    xs, ys = zip(*points)
    side = min(max(xs)-min(xs), max(ys)-min(ys))
    if side <= 0:
        return None
    split = max(range(1, len(points)), key=lambda i: math.dist(points[0], points[i]))
    original_area = area(points)
    for step in range(1, 11):
        ratio = step/100
        left = reduce_open(points[:split+1], ratio*side)
        right = reduce_open(points[split:]+points[:1], ratio*side)
        reduced = left[:-1]+right[:-1]
        if (3 <= len(reduced) <= 8 and
                abs(area(reduced)-original_area) <= .05*original_area):
            raw = 'm '+f'{reduced[0][0]:g} {reduced[0][1]:g} l '+ ' '.join(
                f'{x:g} {y:g}' for x, y in reduced[1:])
            return raw, info[0]
    return None


def prototype_tiled_clip(rectangles, unit):
    """Accept a gapless, non-overlapping strip partition of one rectangle.

    Preserve the union clip. Removing it would expose unseen parts of paths.
    General tiled artwork and overlapping clips are not approximated here.
    """
    if not rectangles:
        return None
    eps = 1e-5 * unit
    for axis in (0, 1):
        other = 1-axis
        reference = rectangles[0]
        if any(abs(r[other]-reference[other]) > eps or
               abs(r[other+2]-reference[other+2]) > eps for r in rectangles):
            continue
        ordered = sorted(rectangles, key=lambda r: r[axis])
        # Tiny overlaps from decimal rounding are harmless for the union;
        # actual holes and substantial overlapping layers stay unsupported.
        if any(b[axis]-a[axis+2] > eps or a[axis+2]-b[axis] >
               min(.25*unit, .05*min(a[axis+2]-a[axis], b[axis+2]-b[axis]))+eps
               for a, b in zip(ordered, ordered[1:])):
            continue
        box = list(reference)
        box[axis], box[axis+2] = ordered[0][axis], ordered[-1][axis+2]
        return tuple(box)
    return None


def prototype_paint(event):
    """Select visible paint; offset shadows/strokes need more geometry work."""
    st = event.state
    # A nearly coincident shadow can contain the actual background fill.
    if (st.get('4a', 0) < 254 and
            0 < max(abs(st.get(k, st.get('shad', 0))) for k in ('xshad', 'yshad'))
                <= .05 * event.unit and st.get('4a', 0) < st.get('1a', 0)):
        return st.get('4c', '000000'), st.get('4a', 0)
    if st.get('1a', 0) < 254:
        return st.get('1c', 'FFFFFF'), st.get('1a', 0)
    return None


def prototype_composed_paint(events):
    """Compose coextensive fills in their original same-layer source order."""
    opacity, premult = 0.0, [0.0, 0.0, 0.0]
    for event in sorted(events, key=lambda e: e.source_index):
        paint = prototype_paint(event)
        if paint is None:
            continue
        color, alpha = paint
        ink = (255-alpha)/255
        premult = [old*(1-ink)+((int(color, 16) >> shift) & 255)*ink
                   for old, shift in zip(premult, (16, 8, 0))]
        opacity = opacity*(1-ink)+ink
    if opacity <= 1/255:
        return None
    color = ''.join(f'{round(v/opacity):02X}' for v in premult)
    return color, round(255*(1-opacity))


def prototype_held_scale(source, candidate, transforms, paint_tags):
    """Validate a short scale entrance, shrinking exit, or stable-pose pair."""
    if not transforms:
        return True, False
    if len(transforms) > 2:
        return False, False
    parsed, targets = [], []
    target = source.state.copy()
    for value in transforms:
        item = parse_effect_transform(value, source.duration, paint_tags | {'fscx', 'fscy'})
        if item is None:
            return False, False
        for key, argument in item[2]:
            if key in ('fscx', 'fscy'):
                # libass accepts a trailing comma on these numeric targets.
                # Require a complete finite number rather than letting the
                # strict production parser silently skip a malformed target.
                if not re.fullmatch(r'\s*'+NUMBER+r'\s*,?\s*', argument):
                    return False, False
                argument = argument.strip().removesuffix(',').strip()
                if not math.isfinite(float(argument)):
                    return False, False
            apply_tag(target, key, argument, source.styles, source.defaults)
        parsed.append(item)
        targets.append(target.copy())
    def matches(pose):
        return all(pose.get(k, 100) > 0 and
                   abs(pose.get(k, 100)-candidate.state.get(k, 100)) < .001
                   for k in ('fscx', 'fscy'))
    def shrinks(before, after):
        return (all(0 < after.get(k, 100) <= before.get(k, 100)
                    for k in ('fscx', 'fscy')) and
                any(after.get(k, 100) < before.get(k, 100) for k in ('fscx', 'fscy')))
    if len(parsed) == 1:
        begin, end, _ = parsed[0]
        entrance = begin == 0 and end <= 200*source.duration and matches(targets[0])
        exit_pose = (800*source.duration <= begin < 1000*source.duration and
                     end >= 1000*source.duration-50 and
                     matches(source.state) and shrinks(source.state, targets[0]))
        return entrance or exit_pose, exit_pose
    first, last = parsed
    exit_pose = (first[0] == 0 and first[1] <= 200*source.duration and
                 last[0]-first[1] >= 800*source.duration and
                 last[1] >= 1000*source.duration-50 and
                 matches(targets[0]) and shrinks(targets[0], targets[1]))
    return exit_pose, exit_pose


def prototype_static_vectors(sources, *, scaled_borders=True):
    """Reduce proved static primitives and clipped gradients, not moving UI."""
    groups, original_contours = {}, {}
    counts = {'prototype_vector_candidates': 0, 'prototype_strips_collapsed': 0,
              'prototype_vector_duplicates': 0, 'prototype_fade_frames': 0,
              'prototype_unsupported_drawings': 0, 'prototype_polygons_simplified': 0,
              'prototype_held_scaling_exits': 0, 'prototype_held_move_entrances': 0,
              'prototype_edge_slivers_detached': 0}
    paint_tags = {'c', '1c', '2c', '3c', '4c', 'alpha', '1a', '2a', '3a', '4a',
                  'bord', 'xbord', 'ybord', 'shad', 'xshad', 'yshad', 'blur', 'be'}
    for source in sources:
        if (source.kind != 'Dialogue' or source.duration <= 0 or
                not re.search(r'\\p[1-9]\d*\b', source.text, re.I)):
            continue
        text, visible, chars = simplify_visual_text(
            source.text, 0, source.duration, source.defaults, source.styles, 2)
        if not chars:
            continue
        candidate = prototype_normalize_alignment(prototype_flat_rectangle_border(
            replace_event(source, text=text, effect=''), scaled_borders=scaled_borders))
        candidate, detached = prototype_detach_edge_slivers(candidate)
        counts['prototype_edge_slivers_detached'] += detached
        original_points = None
        if prototype_simple_path(candidate) is None:
            reduction = prototype_reduce_contour(candidate)
            if reduction is not None:
                raw, original_points = reduction
                candidate = replace_event(candidate, text=OVERRIDE_RE.match(candidate.text).group()+raw)
                counts['prototype_polygons_simplified'] += 1
        # A mixed text/drawing line and an animated pose cannot be represented
        # by a single independently retained static primitive.
        transforms = [(k, v) for block in OVERRIDE_RE.findall(source.text)
                      for k, v in tokenize_override(block) if k == 't']
        geometry_transforms = [value for _, value in transforms if
                               any(k not in paint_tags for k, v in
                                   tokenize_override(value[1:-1]))]
        held_scale, held_exit = prototype_held_scale(
            source, candidate, geometry_transforms, paint_tags)
        animated_geometry = not held_scale
        moves = [v for block in OVERRIDE_RE.findall(source.text)
                 for k, v in tokenize_override(block) if k == 'move']
        held_move = False
        if len(moves) == 1:
            motion = parse_effect_move(moves[0], source.duration)
            held_move = (motion is not None and len(motion) == 6 and
                         motion[5] <= 200*source.duration and
                         get_pos(text) is not None and
                         all(abs(a-b) < .001 for a, b in zip(get_pos(text), motion[2:4])))
        if (visible or inline_layout_key(source) or prototype_simple_path(candidate) is None or
                (moves and not held_move) or animated_geometry or
                'iclip' in candidate.state or
                any(candidate.state.get(k, 0) for k in ('frx', 'fax', 'fay', 'pbo')) or
                candidate.state.get('fry', 0) % 360 not in (0, 180) or
                get_pos(candidate.text) is None):
            counts['prototype_unsupported_drawings'] += 1
            continue
        counts['prototype_held_scaling_exits'] += held_exit
        counts['prototype_held_move_entrances'] += held_move
        raw_key = (source.start, source.end, source.layer, source.style, source.name,
                   source.margin_l, source.margin_r, source.margin_v,
                   geometry_key(candidate.text), state_key(candidate, paint_tags | {'clip'}),
                   tuple(original_points) if original_points is not None else None)
        if original_points is not None:
            original_contours[candidate.source_index] = tuple(original_points)
        groups.setdefault(raw_key, []).append(candidate)
    output = []
    for group in groups.values():
        first = group[0]
        clipped = ['clip' in e.state for e in group]
        rects = [rectangle_clip(e) for e in group]
        # Clip coordinates outside a rectangle's actual fill do not create
        # gaps. Intersect first; gradient generators often round those unused
        # top/bottom limits differently in their final strip.
        path = prototype_simple_path(first)
        if (path and len({x for x, y in path}) == 2 and
                len({y for x, y in path}) == 2 and coverage_geometry(first) is not None):
            points = coverage_geometry(first)[0]
            xs, ys = zip(*points)
            bounds = min(xs), min(ys), max(xs), max(ys)
            rects = [None if r is None else (max(r[0], bounds[0]), max(r[1], bounds[1]),
                                           min(r[2], bounds[2]), min(r[3], bounds[3]))
                     for r in rects]
        if any(clipped):
            if not all(clipped) or any(r is None or r[0] >= r[2] or r[1] >= r[3] for r in rects):
                counts['prototype_unsupported_drawings'] += len(group)
                continue
            clip_groups = {}
            for event, rect in zip(group, rects):
                clip_groups.setdefault(rect, []).append(event)
            rects = list(clip_groups)
            union = prototype_tiled_clip(rects, first.unit)
            if union is None:
                counts['prototype_unsupported_drawings'] += len(group)
                continue
        else:
            union = None
        if union:
            paints = [prototype_composed_paint(clip_group) for clip_group in clip_groups.values()]
            weights = [(r[2]-r[0])*(r[3]-r[1]) for r in rects]
            active = [(paint, weight) for paint, weight in zip(paints, weights) if paint]
            # Average the composed paint of each distinct strip, including
            # transparent strips, rather than counting coincident copies as
            # overlapping partitions of the gradient.
            area = sum(weights)
            ink = sum(weight * (255-alpha) for (color, alpha), weight in active)
            alpha = round(255-ink/area)
            if alpha >= 254:
                continue
            channels = [round(sum(weight*(255-a)*((int(c, 16) >> shift) & 255)
                                  for (c, a), weight in active)/ink)
                        for shift in (16, 8, 0)]
        else:
            paint = prototype_composed_paint(group)
            if paint is None:
                continue
            color, alpha = paint
            channels = [(int(color, 16) >> shift) & 255 for shift in (16, 8, 0)]
        color = ''.join(f'{v:02X}' for v in channels)
        # Preserve the static pose and path after exact alignment normalization
        # and the simple same-colour rectangular-stroke expansion above.
        st = dict(first.state)
        st.update({'1c': color, '1a': alpha, '2a': alpha, '3a': 255, '4a': 255,
                   'bord': 0, 'xbord': 0, 'ybord': 0, 'shad': 0,
                   'xshad': 0, 'yshad': 0, 'blur': 0, 'be': 0})
        if union:
            st['clip'] = '('+','.join(f'{x:g}' for x in union)+')'
        else:
            st.pop('clip', None)
        keys = ('an', 'pos', 'org', 'p', 'fscx', 'fscy', 'frz', 'fry',
                'bord', 'shad', 'xbord', 'ybord', 'xshad', 'yshad',
                '1c', '1a', '2a', '3a', '4a', 'clip')
        tags = ''.join(render_tag(k, st[k]) for k in keys if k in st)
        event = replace_event(first, text='{'+tags+'}'+OVERRIDE_RE.sub('', first.text),
                              source_index=min(e.source_index for e in group))
        output.append(event)
        counts['prototype_strips_collapsed' if union else 'prototype_vector_duplicates'] += len(group)-1
    # Existing helper removes exact opaque layers. Restrict sequence merging
    # to identical poses: its general path can otherwise freeze moving signs.
    output, removed = reduce_vector_layers(output)
    counts['prototype_vector_duplicates'] += removed
    poses = {}
    for e in output:
        poses.setdefault((e.style, e.name, e.layer, geometry_key(e.text),
                          state_key(e, {'1a', '2a', '3a', '4a'}),
                          original_contours.get(e.source_index)), []).append(e)
    output = []
    for family in poses.values():
        family, removed = freeze_vector_sequences(family)
        output.extend(family)
        counts['prototype_fade_frames'] += removed
    counts['prototype_vector_candidates'] = len(output)
    for e in output:
        if e.source_index in original_contours:
            # Temporary evidence for this pass, never serialized or shared
            # with the production text engine.
            e.state['_prototype_original_points'] = original_contours[e.source_index]
    return sorted(output, key=lambda e: e.source_index), counts


def prototype_composite_backdrops(sources, captions, metric):
    """Approximate static shadow-painted erasure patches around literal text.

    This is a bounded reconstruction, not a claim that disjoint source masks
    covered every glyph. Require several matching opaque, similarly coloured
    patches intersecting a measured caption, and keep their combined bounds.
    Separate contours are measured separately so a distant separator cannot
    enlarge a title panel merely because both share one drawing event.
    """
    groups = {}
    for source in sources:
        st = source.state
        if (source.kind != 'Dialogue' or not st.get('p', 0) or
                st.get('an') != 7 or st.get('1a', 0) < 254 or
                st.get('3a', 0) < 254 or st.get('4a', 0) != 0 or
                st.get('borderstyle', 1) != 1 or get_pos(source.text) is None or
                not source.layer.lstrip('-').isdigit() or
                any(k in st for k in ('clip', 'iclip')) or
                any(st.get(k, 0) for k in ('frz', 'frx', 'fry', 'fax', 'fay', 'pbo')) or
                re.search(r'\\(?:t|move|fad|fade)\s*\(', source.text, re.I) or
                not 0 < max(abs(st.get(k, st.get('shad', 0)))
                            for k in ('xshad', 'yshad')) <= .05*source.unit or
                not 0 <= st.get('blur', 0) <= 8*source.unit):
            continue
        text, visible, chars = simplify_visual_text(source.text, 0, source.duration,
                                                   source.defaults, source.styles, 2)
        if visible or not chars or inline_layout_key(source):
            continue
        raw = OVERRIDE_RE.sub('', text).strip()
        # Reject unknown commands before splitting move/line/cubic contours.
        if re.sub(NUMBER+r'|[mlb\s]', '', raw, flags=re.I):
            continue
        key = (source.start, source.end, source.style, source.name, source.layer,
               get_pos(source.text), st.get('p'), st.get('fscx'), st.get('fscy'))
        for contour in re.split(r'(?=m\s)', raw, flags=re.I):
            if not re.search(r'\bb\s', contour, re.I):
                continue
            fragment = replace_event(source, text=OVERRIDE_RE.match(text).group()+contour)
            info = coverage_geometry(fragment)
            if info is None:
                continue
            pad = 2*st.get('blur', 0)
            x0, y0, x1, y1 = info[1]
            bounds = (x0-pad, y0-pad, x1+pad, y1+pad)
            color = str(st.get('4c', ''))
            if re.fullmatch(r'[0-9A-Fa-f]{6}', color):
                groups.setdefault(key, []).append((source, bounds, color))
    rebuilt, used = [], set()
    for caption in captions:
        if (caption.kind != 'Dialogue' or caption.state.get('p', 0) or caption.lyric or
                not caption.layer.lstrip('-').isdigit() or
                len(OVERRIDE_RE.sub('', caption.text).strip()) < 2 or
                re.search(r'\\[Nn]', OVERRIDE_RE.sub('', caption.text))):
            continue
        box = prototype_text_box(caption, metric)
        if box is None:
            continue
        for key, fragments in groups.items():
            first = fragments[0][0]
            if (key in used or first.style != caption.style or first.name != caption.name or
                    int(first.layer) >= int(caption.layer) or
                    min(first.end_s, caption.end_s) <= max(first.start_s, caption.start_s)):
                continue
            nearby = []
            for e, b, c in fragments:
                # Blur clearance can approach a neighbouring separator, but
                # that alone does not make its contour a title patch.
                pad = 2*e.state.get('blur', 0)
                if (min(b[2]-pad, box[2]) > max(b[0]+pad, box[0]) and
                        min(b[3]-pad, box[3]) > max(b[1]+pad, box[1])):
                    nearby.append((e, b, c))
            if len({e.source_index for e, b, c in nearby}) < 3:
                continue
            bounds = (min(b[0] for e, b, c in nearby), min(b[1] for e, b, c in nearby),
                      max(b[2] for e, b, c in nearby), max(b[3] for e, b, c in nearby))
            x0, y0, x1, y1 = bounds
            if (not (x0 < box[0] < box[2] < x1 and y0 < box[1] < box[3] < y1) or
                    x1-x0 > 2*(box[2]-box[0]) or y1-y0 > 2*(box[3]-box[1])):
                continue
            colors = [tuple(int(c[i:i+2], 16) for i in (0, 2, 4)) for e, b, c in nearby]
            if any(max(c[i] for c in colors)-min(c[i] for c in colors) > 32 for i in range(3)):
                continue
            weights = [(b[2]-b[0])*(b[3]-b[1]) for e, b, c in nearby]
            color = ''.join(f'{round(sum(w*c[i] for w, c in zip(weights, colors))/sum(weights)):02X}'
                            for i in range(3))
            tags = (r'\an7\pos(0,0)\p1\fscx100\fscy100\bord0\shad0'
                    r'\xbord0\ybord0\xshad0\yshad0'+render_tag('1c', color)+
                    r'\1a&H00&\2a&H00&\3a&HFF&\4a&HFF&')
            raw = f'm {x0:g} {y0:g} l {x1:g} {y0:g} {x1:g} {y1:g} {x0:g} {y1:g}'
            event = replace_event(first, text='{'+tags+'}'+raw, effect='')
            event.state['_prototype_composite_patch_bounds'] = bounds
            rebuilt.append(event)
            used.add(key)
    return rebuilt


def prototype_resolution(lines, axis):
    default = 384 if axis == 'x' else 288
    for line in lines:
        if line.strip().lower().startswith('playres'+axis+':'):
            try:
                value = float(line.split(':', 1)[1])
                return value if math.isfinite(value) and value > 0 else default
            except ValueError:
                return default
    return default


def prototype_load(path, encoding=None):
    """Use the shared parser, including event fields and exact style state."""
    raw = read_subtitle(path, encoding)
    lines = re.split(r'\r\n|\r|\n', raw)
    styles = parse_styles(lines)
    section, wrap_mode = '', 0
    for line in lines:
        clean = line.strip()
        if clean.startswith('['):
            section = clean.casefold()
        elif section == '[script info]' and clean.casefold().startswith('wrapstyle:'):
            try:
                value = int(clean.split(':', 1)[1].strip())
                if value in range(4):
                    wrap_mode = value
            except ValueError:
                pass
    # Keep the script default as local measurement metadata, not an ASS tag
    # default: adding q to the style state would change override serialization
    # when a source caption is restored by the ordinary freezer.
    for state in styles.values():
        state['_prototype_wrap_mode'] = wrap_mode
    default = {**DEFAULT_STATE, '_prototype_wrap_mode': wrap_mode}
    unit = prototype_resolution(lines, 'y')/1080
    section, fields, events, indices = '', EVENT_FIELDS, [], []
    for i, line in enumerate(lines):
        clean = line.strip()
        if clean.startswith('['):
            section = clean.lower()
        elif section == '[events]' and clean.lower().startswith('format:'):
            fields = [x.strip().lower() for x in clean.split(':', 1)[1].split(',')]
        elif section == '[events]':
            e = parse_dialogue(line, i, fields)
            if e:
                e.defaults = styles.get(e.style, default)
                e.styles = styles
                e.unit = unit
                e.state = effective_state(e.text, e.defaults, styles)
                events.append(e); indices.append(i)
    return lines, events, fields, indices


def prototype_texture(event, metric):
    """Prove a multiline stamp texture by its exact glyph contour structure."""
    if metric is None or not metric.available or event.state.get('p', 0):
        return False
    text = OVERRIDE_RE.sub('', event.text)
    lines = re.split(r'\\[Nn]', text)
    chars = [c for line in lines for c in line if not c.isspace()]
    if len(lines) < 3 or len(chars) < 24:
        return False
    face = metric.matching_face(str(event.state.get('fn', '')),
                                bool(event.state.get('b', 0)), bool(event.state.get('i', 0)))
    if face is None or any(ord(c) not in face[2] for c in chars):
        return False
    # A font name or nonsensical-looking string alone authorizes nothing.
    return all(metric.fragmented_glyph(face, c) is True for c in set(chars))


def prototype_fullscreen(event):
    """Prove that a static fill covers the viewport, including its clip."""
    info = coverage_geometry(event)
    canvas = event.state.get('_canvas')
    if info is None or canvas is None:
        return False
    width, height = canvas
    if width <= 0 or height <= 0:
        return False
    eps = 1e-4*event.unit
    viewport = (eps, eps, width-eps, height-eps)
    clip = rectangle_clip(event)
    if 'clip' in event.state and (clip is None or not all((
            clip[0] <= viewport[0], clip[1] <= viewport[1],
            clip[2] >= viewport[2], clip[3] >= viewport[3]))):
        return False
    return polygon_covers_box(info[0], viewport)


def prototype_clip_outline(event):
    """Return one static, straight-sided scene-coordinate clip contour.

    A shared authored contour can identify a panel without approximating the
    perspective of its text. Keep the clip on that text; do not expand its ink.
    """
    if (event.state.get('p', 0) or 'iclip' in event.state or
            inline_layout_key(event) or
            re.search(r'\\(?:t|move|fad|fade)\s*\(', event.text, re.I)):
        return None
    mask = re.fullmatch(r'\(\s*(?:(\d+)\s*,\s*)?(m\s+.*?)\s*\)',
                        str(event.state.get('clip', '')), re.I)
    if mask is None or not 1 <= int(mask[1] or 1) <= 16:
        return None
    points = prototype_simple_path(replace_event(event, text='{\\p1}'+mask[2]))
    scale = 2**(int(mask[1] or 1)-1)
    return tuple((x/scale, y/scale) for x, y in points) if points else None


def prototype_repair_shadow_offsets(sources, captions):
    """Recover a held shadow offset hidden by an extra numeric-tag comma.

    libass accepts a numeric prefix before the comma; v100's strict float
    parsing skips it. Repair only these shadow tags, on the same faint-primary
    caption with an opaque shadow and no outline. Other text paint is retained.
    """
    def key(e):
        return (e.start, e.end, e.style, e.name, placement_key(e)[0],
                get_pos(e.text), text_layout_key(e), OVERRIDE_RE.sub('', e.text).strip())
    corrected = {}
    for source in sources:
        if (source.kind != 'Dialogue' or source.state.get('p', 0) or
                inline_layout_key(source) or source.state.get('1a', 0) < 254 or
                source.state.get('4a', 0) != 0 or
                source.state.get('borderstyle', 1) != 1 or
                max(abs(source.state.get(k, source.state.get('bord', 0)))
                    for k in ('xbord', 'ybord')) != 0):
            continue
        clean = re.sub(r'(\\(?:xshad|yshad|shad)'+NUMBER+r'),(?=\\)', r'\1', source.text)
        if clean == source.text:
            continue
        text, _, _ = simplify_visual_text(clean, 0, source.duration,
                                         source.defaults, source.styles, 1)
        repaired = replace_event(source, text=text)
        corrected.setdefault(key(repaired), []).append(repaired)
    output, count = [], 0
    for e in captions:
        choices = corrected.get(key(e), [])
        offsets = {(c.state.get('xshad', c.state.get('shad', 0)),
                    c.state.get('yshad', c.state.get('shad', 0))) for c in choices}
        if (e.kind == 'Dialogue' and not e.lyric and len(offsets) == 1 and
                e.state.get('1a', 0) >= 254 and e.state.get('4a', 0) == 0 and
                not inline_layout_key(e)):
            dx, dy = next(iter(offsets))
            if (dx, dy) != (e.state.get('xshad', e.state.get('shad', 0)),
                            e.state.get('yshad', e.state.get('shad', 0))):
                text = OVERRIDE_RE.sub(lambda m: '{'+re.sub(
                    r'\\(?:xshad|yshad|shad)[^\\}]*', '', m.group()[1:-1])+'}', e.text)
                text = '{'+render_tag('xshad', dx)+render_tag('yshad', dy)+'}'+text
                e = replace_event(e, text=text)
                count += 1
        output.append(e)
    return output, count


def prototype_restore_masked_foregrounds(sources, captions):
    """Restore a solid clipped caption when v100 kept only its faint clone.

    Require identical literal text, static layout, anchor, lifetime, actor and
    fill colour. An ambiguous set of solid masks authorizes no replacement.
    This correction is local to level 1; the embedded v100 engine is unchanged.
    """
    def key(e):
        return (e.start, e.end, e.style, e.name, placement_key(e)[0],
                get_pos(e.text), text_layout_key(e),
                OVERRIDE_RE.sub('', e.text).strip(), e.state.get('1c'))
    solids = {}
    for source in sources:
        if (source.kind != 'Dialogue' or source.state.get('1a', 0) != 0 or
                prototype_clip_outline(source) is None):
            continue
        text, _, _ = simplify_visual_text(source.text, 0, source.duration,
                                         source.defaults, source.styles, 1)
        solid = replace_event(source, text=text, effect='')
        solids.setdefault(key(solid), []).append(solid)
    restored, count = [], 0
    for caption in captions:
        choices = solids.get(key(caption), [])
        signatures = {(e.text, e.layer) for e in choices}
        if (caption.kind == 'Dialogue' and not caption.lyric and
                not caption.state.get('p', 0) and
                not inline_layout_key(caption) and
                'clip' not in caption.state and 'iclip' not in caption.state and
                0 < caption.state.get('1a', 0) < 255 and len(signatures) == 1):
            solid = choices[0]
            # Preserve the output index for insertion, but recover the source
            # layer as well as its paint, mask and exact static text pose.
            caption = replace_event(caption, text=solid.text, layer=solid.layer)
            count += 1
        restored.append(caption)
    return restored, count


def prototype_shared_outline(panel, caption, points=None):
    """Match a text mask to its panel while rejecting a displaced reuse."""
    mask = prototype_clip_outline(caption)
    raw_points = prototype_simple_path(panel)
    if mask is None or raw_points is None or 'clip' in panel.state:
        return False
    scale = 2**(panel.state.get('p', 1)-1)
    outline = tuple((x/scale, y/scale) for x, y in raw_points)
    anchor = get_pos(caption.text)
    if points is None:
        info = coverage_geometry(panel)
        points = info[0] if info is not None else None
    return (mask == outline and points is not None and anchor is not None and
            polygon_covers_box(list(mask), (*anchor, *anchor)) and
            polygon_covers_box(points, (*anchor, *anchor)))


def prototype_select_supports(candidates, captions, metric):
    """Keep fullscreen fills and the uppermost local support in each interval.

    Adjacency is only considered for small, straight, non-rectangular shapes
    in a sparse sign group. It does not imply video coverage or text recovery.
    """
    eligible = [e for e in captions
             if e.kind == 'Dialogue' and not e.state.get('p', 0) and
             bool(OVERRIDE_RE.sub('', e.text).strip()) and not e.lyric]
    boxes = {e.source_index: prototype_text_box(e, metric) for e in eligible}
    nearby = [(e, prototype_text_box(e, metric, adjacency=True)) for e in captions
              if e.kind == 'Dialogue' and not e.state.get('p', 0) and
              len(OVERRIDE_RE.sub('', e.text).strip()) >= 2 and not e.lyric]
    nearby = [(e, box) for e, box in nearby if box is not None]
    geometry = {}
    for e in candidates:
        info = coverage_geometry(e)
        if info is not None:
            points, bounds, _ = info
            xs, ys = zip(*points)
            box = (min(xs), min(ys), max(xs), max(ys))
            geometry[e.source_index] = points, box
        elif rectangle_clip(e) is not None:
            # Scene-coordinate clip bounds also bound rotated/aligned paths.
            # They are sufficient for adjacency, but cannot prove fill coverage.
            geometry[e.source_index] = None, rectangle_clip(e)
    fullscreen_ids = {e.source_index for e in candidates if prototype_fullscreen(e)}
    selected, associated, enclosing_ids = set(fullscreen_ids), {}, set()
    # Fullscreen fills do not compete with local panels or require font
    # measurement. Preserve source layers so both can sit beneath their text.
    for e in candidates:
        if e.source_index in fullscreen_ids:
            associated[e.source_index] = [caption for caption in captions
                if caption.kind == 'Dialogue' and caption.style == e.style and
                caption.name == e.name and not caption.state.get('p', 0) and
                min(caption.end_s, e.end_s) > max(caption.start_s, e.start_s)]
    for caption in eligible:
        box = boxes[caption.source_index]
        mask = prototype_clip_outline(caption)
        if box is None and mask is None:
            continue
        enclosing = []
        for e in candidates:
            if (e.source_index in fullscreen_ids or
                    e.source_index not in geometry or e.style != caption.style or
                    e.name != caption.name or not e.layer.lstrip('-').isdigit() or
                    not caption.layer.lstrip('-').isdigit() or
                    int(e.layer) > int(caption.layer)):
                continue
            overlap = min(e.end_s, caption.end_s)-max(e.start_s, caption.start_s)
            if overlap <= 0:
                continue
            # Backdrops need only support the text while both are visible.
            # Preserve source timing; no minimum percentage or maximum gap.
            points, bounds = geometry[e.source_index]
            clip = rectangle_clip(e)
            contained = (box is not None and points is not None and polygon_covers_box(points, box) and
                    polygon_covers_box(list(e.state.get('_prototype_original_points', points)), box) and
                    (clip is None or all((clip[0] < box[0], clip[1] < box[1],
                                         clip[2] > box[2], clip[3] > box[3]))))
            # Authored reuse of the same simple path is explicit panel/mask
            # evidence even for rotated, sheared or projective lettering.
            # Both must contain the text anchor in rendered scene space: a
            # reused shape parked elsewhere is not a supporting panel.
            shared_outline = mask is not None and prototype_shared_outline(e, caption, points)
            if contained or shared_outline:
                enclosing.append(e)
        if enclosing:
            # Choose the uppermost local support separately for each occupied
            # interval. A later panel cannot erase an earlier panel that is
            # the text's only support before or after their shared interval.
            times = sorted({caption.start_s, caption.end_s} |
                           {t for e in enclosing for t in
                            (max(e.start_s, caption.start_s),
                             min(e.end_s, caption.end_s))})
            winners = {}
            for start, end in zip(times, times[1:]):
                top = max((e for e in enclosing if e.start_s < end and e.end_s > start),
                          key=lambda e: (int(e.layer), e.source_index), default=None)
                if top is not None:
                    winners[top.source_index] = top
            for top in winners.values():
                selected.add(top.source_index)
                enclosing_ids.add(top.source_index)
                associated.setdefault(top.source_index, []).append(caption)
    # Adjacent arrows and small polygon patches are useful even when they are
    # not backgrounds enclosing text. Reject dense drawings and lyric regions.
    sparse = collections.Counter((e.start, e.end, e.style, e.name) for e in candidates
                                 if e.source_index not in fullscreen_ids)
    for e in candidates:
        if e.source_index in selected or e.source_index not in geometry:
            continue
        points, bounds = geometry[e.source_index]
        primitive = prototype_simple_path(e)
        if (e.duration < .12 or sparse[(e.start, e.end, e.style, e.name)] > 8 or
                '_prototype_original_points' in e.state or
                primitive is None or len({x for x, y in primitive}) == 2 and
                len({y for x, y in primitive}) == 2):
            continue
        for caption, box in nearby:
            overlap = min(caption.end_s, e.end_s)-max(caption.start_s, e.start_s)
            if (caption.style != e.style or caption.name != e.name or
                    overlap < .8*min(caption.duration, e.duration)):
                continue
            height = text_height(caption)
            dx = max(box[0]-bounds[2], bounds[0]-box[2], 0)
            dy = max(box[1]-bounds[3], bounds[1]-box[3], 0)
            if (math.hypot(dx, dy) <= 1.5*height and
                    bounds[2]-bounds[0] <= 5*height and
                    bounds[3]-bounds[1] <= 5*height):
                selected.add(e.source_index)
                associated.setdefault(e.source_index, []).append(caption)
                break
    kept = []
    for e in candidates:
        if e.source_index not in selected:
            continue
        if (e.source_index in enclosing_ids and
                '_prototype_original_points' in e.state):
            # Reconstructed paper panels hide the picture behind a caption.
            # Their original translucent paint may have depended on discarded
            # scene artwork underneath. Keep the simplified contour, colour
            # and pose, but make these enclosing panels opaque. Gradient bands
            # and adjacent decorative shapes retain their original opacity.
            original_points = e.state['_prototype_original_points']
            e = replace_event(e, text=re.sub(r'\\([12])a&H[0-9a-f]+&',
                                            r'\\\1a&H00&', e.text, flags=re.I))
            e.state['_prototype_original_points'] = original_points
        kept.append(e)
    return kept, associated


_simplify_text_and_vectors = simplify_ass


def prototype_fallback_vectors(events, captions, kept, metric, *, scaled_borders=True):
    """Preserve baseline supports for unknown text, without equivalent copies."""
    caption_groups = {}
    for caption in captions:
        if (caption.kind == 'Dialogue' and not caption.state.get('p', 0) and
                OVERRIDE_RE.sub('', caption.text).strip()):
            caption_groups.setdefault((caption.style, caption.name), []).append(
                (caption, prototype_text_box(caption, metric)))
    def fill_key(event):
        # Compare rendered fill footprints, not header spelling or unused
        # shadow/outline alpha. Never equate extra visible stroke/shadow paint.
        event = prototype_normalize_alignment(prototype_flat_rectangle_border(
            event, scaled_borders=scaled_borders))
        st = event.state
        if (prototype_simple_path(event) is None or st.get('1a', 0) >= 254 or
                st.get('3a', 0) < 254 and any(st.get(k, st.get('bord', 0))
                                            for k in ('xbord', 'ybord')) or
                st.get('4a', 0) < 254 and any(st.get(k, st.get('shad', 0))
                                            for k in ('xshad', 'yshad')) or
                'iclip' in st or 'clip' in st and rectangle_clip(event) is None):
            return None
        info = coverage_geometry(event)
        if info is None:
            return None
        points = tuple((round(x, 6), round(y, 6)) for x, y in info[0])
        if points[-1] == points[0]:
            points = points[:-1]
        polygon = min(order[i:]+order[:i] for order in (points, points[::-1])
                      for i in range(len(points)))
        return (event.start, event.end, event.layer, event.style, event.name,
                st.get('1c'), st.get('1a', 0), polygon, rectangle_clip(event))
    equivalents = {key for event in kept if (key := fill_key(event)) is not None}
    fullscreen_paints = {(v.start, v.end, v.layer, v.style, v.name,
                          v.state.get('1c'), v.state.get('1a', 0))
                         for v in kept if prototype_fullscreen(v)}
    fallback = []
    for event in events:
        if event.kind != 'Dialogue' or not event.state.get('p', 0):
            continue
        overlapping = [(caption, box) for caption, box in
                       caption_groups.get((event.style, event.name), [])
                       if min(caption.end_s, event.end_s) > max(caption.start_s, event.start_s)]
        # A known caption elsewhere cannot disprove the support needed by an
        # unknown caption in the same group. Retain v100's existing fallback
        # whenever any overlapping caption remains unmeasurable.
        if overlapping and all(box is not None for caption, box in overlapping):
            continue
        key = fill_key(event)
        if key is not None and key in equivalents:
            continue
        if (prototype_fullscreen(event) and
                (event.start, event.end, event.layer, event.style, event.name,
                 event.state.get('1c'), event.state.get('1a', 0)) in fullscreen_paints):
            continue
        fallback.append(event)
    return fallback


def prototype_scroll_tracks(events, resx, resy):
    """Track baked text frames; never join overlapping spatial instances.

    Paint-only inline spans and coincident effect copies may describe the same
    line. Font/layout spans, live animation, drawings and non-frame cues cannot.
    Ambiguous nearest-neighbour assignments start new tracks instead of guessing.
    """
    paint = {'alpha', 'c', 'bord', 'xbord', 'ybord', 'shad', 'xshad', 'yshad',
             'blur', 'be'} | {f'{c}{kind}' for c in range(1, 5) for kind in 'ca'}
    pose = {'pos', 'org', 'fscx', 'fscy', 'frz', 'frx', 'fry', 'fax', 'fay'}
    groups = {}
    for e in events:
        if (e.kind != 'Dialogue' or not 0 < e.duration <= .16+1e-6 or
                e.state.get('p', 0) or e.effect.strip() or
                re.search(r'\\(?:move|t|fad|fade|[kK])(?=[(\d])', e.text)):
            continue
        pos = get_pos(e.text)
        literal = OVERRIDE_RE.sub('', e.text)
        if pos is None or not literal.strip() or any(x in literal for x in (r'\N', r'\n')):
            continue
        seen_text = False
        safe = True
        for part in re.split(r'(\{[^}]*\})', e.text):
            if part.startswith('{'):
                if seen_text and any(k not in paint for k, v in tokenize_override(part[1:-1])):
                    safe = False
            elif part:
                seen_text = True
        values = (*pos, *e.state.get('org', pos), *(e.state.get(k, 0) for k in
                  ('fscx', 'fscy', 'frz', 'frx', 'fry', 'fax', 'fay')))
        if not safe or not all(math.isfinite(v) for v in values):
            continue
        key = (e.style, e.name, e.layer, literal, e.margin_l, e.margin_r, e.margin_v,
               state_key(e, paint | pose),
               tuple(k for k in ('xbord', 'ybord', 'xshad', 'yshad') if k in e.state))
        # Equal interval/pose copies are one spatial line, not extra votes.
        frame_key = (e.start_s, e.end_s, tuple(e.state.get(k) for k in sorted(pose)), pos)
        groups.setdefault(key, {}).setdefault(frame_key, []).append(e)
    tracks = []
    max_step = .08*min(resx, resy)
    for frames in groups.values():
        buckets = {}
        for copies in frames.values():
            e = copies[0]
            buckets.setdefault(e.start_s, []).append(copies)
        family = []
        for start, nodes in sorted(buckets.items()):
            active = [t for t in family if abs(t[-1][0].end_s-start) <= .011+1e-6]
            distances = {(i, j): math.dist(get_pos(t[-1][0].text), get_pos(n[0].text))
                         for i, t in enumerate(active) for j, n in enumerate(nodes)}
            def nearest(options):
                ranked = sorted(options)
                if not ranked or ranked[0][0] > max_step:
                    return None
                if len(ranked) > 1 and ranked[1][0]-ranked[0][0] <= max(2*nodes[0][0].unit, .2*ranked[0][0]):
                    return None
                return ranked[0][1]
            forward = {i: nearest([(distances[i, j], j) for j in range(len(nodes))])
                       for i in range(len(active))}
            reverse = {j: nearest([(distances[i, j], i) for i in range(len(active))])
                       for j in range(len(nodes))}
            for j, node in enumerate(nodes):
                i = reverse[j]
                if i is not None and forward[i] == j:
                    active[i].append(node)
                else:
                    family.append([node])
        tracks.extend(family)
    return tracks


def prototype_scroll_edge(track, axis, sign, resx, resy, metric):
    """Strong edge evidence from measured text, with a wide uncertainty margin.

    This is a bounded near-front-facing estimate, not a projective glyph box.
    Steep perspective, distant origins, unknown fonts and clips cannot prove an
    edge crossing. Anchors outside the viewport alone are never sufficient.
    """
    extent = (resx, resy)[axis]
    def box(node):
        e = node[0]
        st = e.state
        pos = get_pos(e.text)
        origin = st.get('org', pos)
        angles = [abs(math.remainder(st.get(k, 0), 360)) for k in ('frx', 'fry')]
        if (max(angles) > 5 or math.dist(pos, origin) > .25*min(resx, resy) or
                'clip' in st or 'iclip' in st):
            return None
        prefix = re.match(r'(?:\{[^}]*\})*', e.text).group()
        flat = dataclass_replace(e, text=prefix+OVERRIDE_RE.sub('', e.text),
                                 state={**st, 'frx': 0, 'fry': 0})
        bounds = prototype_text_box(flat, metric)
        if bounds is None:
            return None
        radius = math.dist(pos, origin)+math.hypot(bounds[2]-bounds[0], bounds[3]-bounds[1])
        margin = .10*extent + radius*sum(abs(math.sin(math.radians(a))) for a in angles)
        return bounds[axis]-margin, bounds[axis+2]+margin
    first, last = box(track[0]), box(track[-1])
    if first is None or last is None:
        return False
    # One endpoint's whole expanded box must be inside the scrolling axis;
    # the other must be wholly beyond the corresponding edge.
    if sign > 0:
        return (0 < first[0] and first[1] < extent and last[0] > extent or
                first[1] < 0 and 0 < last[0] and last[1] < extent)
    return (0 < first[0] and first[1] < extent and last[1] < 0 or
            first[0] > extent and 0 < last[0] and last[1] < extent)


def prototype_drop_scrolling_blocks(events, resx, resy, metric, *, concurrency_limit=32):
    """Last-resort removal of proved scrolling blocks after ordinary reduction.

    At least three spatially distinct tracks must share >=1s of coherent
    movement. Each travels >=50% of the relevant screen dimension. At least
    one line has strong measured edge evidence. Removal also requires the
    block's own remaining concurrency to exceed the explicit policy limit.
    Total event count and unrelated captions cannot trigger this fallback.
    """
    if concurrency_limit < 0:
        raise ValueError('Scrolling concurrency limit must be nonnegative.')
    profiles = []
    for track in prototype_scroll_tracks(events, resx, resy):
        if len(track) < 8 or track[-1][0].end_s-track[0][0].start_s < 1:
            continue
        points = [get_pos(node[0].text) for node in track]
        delta = tuple(points[-1][k]-points[0][k] for k in range(2))
        axis = max(range(2), key=lambda k: abs(delta[k])/(resx, resy)[k])
        extent = (resx, resy)[axis]
        if abs(delta[axis]) < .5*extent:
            continue
        sign = 1 if delta[axis] > 0 else -1
        # A brief zoom/entrance may precede the sustained scroll. Ignore at
        # most the first 20% (and never more than one second) for its motion
        # proof, but keep the whole continuous track as the removal unit.
        cutoff = track[0][0].start_s+min(1, .2*(track[-1][0].end_s-track[0][0].start_s))
        initial = [i for i, node in enumerate(track) if node[0].start_s <= cutoff]
        first = min(initial, key=lambda i: sign*points[i][axis])
        proof = track[first:]
        points = points[first:]
        delta = tuple(points[-1][k]-points[0][k] for k in range(2))
        if proof[-1][0].end_s-proof[0][0].start_s < 1 or abs(delta[axis]) < .5*extent:
            continue
        steps = [(b[0]-a[0], b[1]-a[1]) for a, b in zip(points, points[1:])]
        distance = math.hypot(*delta)
        total = sum(math.hypot(*d) for d in steps)
        if (distance < .92*total or
                sum(max(0, -sign*d[axis]) for d in steps) > .05*abs(delta[axis]) or
                abs(delta[1-axis]) > .25*abs(delta[axis])):
            continue
        # Large rotations/scale swings are not a translational scrolling line.
        states = [node[0].state for node in track]
        if any(abs(math.remainder(st.get(k, 0), 360)) > 5
               for st in states for k in ('frx', 'fry')):
            continue
        offsets = [tuple(st.get('org', pos)[k]-pos[k] for k in range(2))
                   for st, pos in zip(states, [get_pos(node[0].text) for node in track])]
        if any(st.get(k, 0) for st in states for k in ('frz', 'frx', 'fry')) and (
                max(math.hypot(*d) for d in offsets) > .25*min(resx, resy) or
                any(max(d[k] for d in offsets)-min(d[k] for d in offsets) > .05*extent
                    for k in range(2))):
            # A changing rotation origin can cancel the movement of pos.
            # Such anchors cannot establish a translating text track.
            continue
        if any(min(st.get(k, 100) for st in states) <= 0 or
               max(st.get(k, 100) for st in states) > 1.3*min(st.get(k, 100) for st in states)
               for k in ('fscx', 'fscy')):
            continue
        if any(max(abs(math.remainder(st.get(k, 0)-states[0].get(k, 0), 360)) for st in states) > 2
               for k in ('frz', 'frx', 'fry')):
            continue
        profiles.append({'track': track, 'axis': axis, 'sign': sign,
                         'start': proof[0][0].start_s, 'end': proof[-1][0].end_s,
                         'delta': delta, 'points': points,
                         'times': [node[0].start_s for node in proof]})
    def position(p, at):
        i = max(0, min(len(p['times'])-2, bisect_right(p['times'], at)-1))
        a, b = p['times'][i:i+2]
        fraction = max(0, min(1, (at-a)/(b-a)))
        return tuple(p['points'][i][k]*(1-fraction)+p['points'][i+1][k]*fraction for k in range(2))
    def coherent(a, b, lo, hi):
        if (a['axis'], a['sign']) != (b['axis'], b['sign']):
            return False
        extent = (resx, resy)[a['axis']]
        samples = [lo+(hi-lo)*i/4 for i in range(5)]
        ap, bp = [position(a, t) for t in samples], [position(b, t) for t in samples]
        da, db = [p[-1][a['axis']]-p[0][a['axis']] for p in (ap, bp)]
        if min(a['sign']*da, a['sign']*db) < .05*extent:
            return False
        tolerance = max(.02*extent, .25*max(abs(da), abs(db)))
        if abs(da-db) > tolerance:
            return False
        # Compare progress throughout the shared interval, not just endpoints.
        return all(math.dist((x[0]-ap[0][0], x[1]-ap[0][1]),
                             (y[0]-bp[0][0], y[1]-bp[0][1])) <= tolerance
                   for x, y in zip(ap, bp))
    def distinct(a, b, at):
        pa, pb = position(a, at), position(b, at)
        ea, eb = a['track'][0][0], b['track'][0][0]
        # Effect shadows/paint copies of one word cannot vote as extra lines.
        return math.dist(pa, pb) > max(4*ea.unit, .75*max(text_height(ea), text_height(eb)))
    removed, report, confirmed = set(), [], set()
    for i, seed in enumerate(profiles):
        if i in confirmed:
            continue
        # Require every pair to agree on one common interval; no transitive
        # chaining of unrelated neighbouring animations into a large block.
        group = [i]
        lo, hi = seed['start'], seed['end']
        for j, candidate in enumerate(profiles):
            if j == i:
                continue
            start, end = max(lo, candidate['start']), min(hi, candidate['end'])
            if end-start < 1:
                continue
            if all(coherent(profiles[k], candidate, start, end) and
                   distinct(profiles[k], candidate, (start+end)/2) for k in group):
                group.append(j); lo, hi = start, end
        if len(group) < 3 or not any(prototype_scroll_edge(profiles[k]['track'], seed['axis'],
                                                           seed['sign'], resx, resy, metric)
                                     for k in group):
            continue
        # Paint variants of a participating line are members but never extra
        # votes toward the three-line minimum. Match their literal identity
        # and near-coincident trajectory over this same proved interval.
        voters = list(group)
        for j, candidate in enumerate(profiles):
            if j in group or candidate['start'] > lo or candidate['end'] < hi:
                continue
            ce = candidate['track'][0][0]
            for k in voters:
                p = profiles[k]; pe = p['track'][0][0]
                if ((ce.style, ce.name, ce.layer, OVERRIDE_RE.sub('', ce.text),
                     ce.state.get('fn'), ce.state.get('fs'), ce.state.get('an')) !=
                    (pe.style, pe.name, pe.layer, OVERRIDE_RE.sub('', pe.text),
                     pe.state.get('fn'), pe.state.get('fs'), pe.state.get('an'))):
                    continue
                if coherent(p, candidate, lo, hi) and all(
                        math.dist(position(p, at), position(candidate, at)) <=
                        .25*max(text_height(pe), text_height(ce))
                        for at in (lo, (lo+hi)/2, hi)):
                    group.append(j); break
        members, block_events = [], []
        for k in group:
            confirmed.add(k)
            p = profiles[k]
            ids = {e.source_index for node in p['track'] for e in node}
            block_events.extend(e for node in p['track'] for e in node)
            members.append({'text': OVERRIDE_RE.sub('', p['track'][0][0].text),
                            'start': p['start'], 'end': p['end'], 'events': len(ids),
                            'travel': round(abs(p['delta'][p['axis']]), 2)})
        block_ids = {e.source_index for e in block_events}
        peak = peak_concurrent_events({e.source_index: e for e in block_events}.values())
        drop = concurrency_limit > 0 and peak > concurrency_limit
        if drop:
            removed.update(block_ids)
        report.append({'start': lo, 'end': hi, 'axis': 'xy'[seed['axis']],
                       'direction': seed['sign'], 'tracks': members,
                       'peak_concurrent': peak, 'concurrency_limit': concurrency_limit,
                       'action': 'removed' if drop else 'retained'})
    return [e for e in events if e.source_index not in removed], report



def simplify_ass(path: Path, output: Path, config: SimplifyConfig, *,
                 font_spacing: FontSpacing | None = None) -> dict[str, int]:
    """Simplify text, apply the scrolling concurrency fallback, rebuild supports."""
    if config.level != 1:
        return _simplify_text_and_vectors(path, output, config, font_spacing=font_spacing)
    if path.resolve() == output.resolve():
        raise ValueError('Subtitle output must differ from its input.')
    if config.scroll_concurrency_limit < 0:
        raise ValueError('Scrolling concurrency limit must be nonnegative.')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='ass-simplify-') as temp:
        source_lines, sources, _, _ = prototype_load(path, config.encoding)
        baseline = Path(temp)/'baseline.ass'
        stats = _simplify_text_and_vectors(path, baseline, config, font_spacing=font_spacing)
        lines, events, fields, indices = prototype_load(baseline)
        events, repaired_shadows = prototype_repair_shadow_offsets(sources, events)
        events, restored_foregrounds = prototype_restore_masked_foregrounds(sources, events)
        # Judge the residual moving block, after all ordinary text reduction.
        # A dense source or a large number of successive frames is not enough.
        before_scroll = len(events)
        events, scroll_report = prototype_drop_scrolling_blocks(
            events, prototype_resolution(lines, 'x'), prototype_resolution(lines, 'y'),
            font_spacing, concurrency_limit=config.scroll_concurrency_limit)
        scrolling_removed = before_scroll-len(events)
        scaled_borders = any(line.strip().lower() == 'scaledborderandshadow: yes'
                             for line in source_lines)
        candidates, counts = prototype_static_vectors(sources, scaled_borders=scaled_borders)
        counts['prototype_scrolling_events_removed'] = scrolling_removed
        counts['prototype_scrolling_blocks_detected'] = len(scroll_report)
        counts['prototype_scrolling_blocks_removed'] = sum(b['action'] == 'removed' for b in scroll_report)
        counts['prototype_scrolling_blocks_retained'] = sum(b['action'] == 'retained' for b in scroll_report)
        counts['prototype_scrolling_peak_after_reduction'] = max(
            (b['peak_concurrent'] for b in scroll_report), default=0)
        counts['prototype_scrolling_concurrency_limit'] = config.scroll_concurrency_limit
        counts['prototype_masked_foregrounds_restored'] = restored_foregrounds
        counts['prototype_shadow_offsets_repaired'] = repaired_shadows
        # Texture removal is only for proved stamps in a replacement sign:
        # there must also be retained literal text and a supporting shape.
        textures = {e.source_index for e in events if e.kind == 'Dialogue' and
                    prototype_texture(e, font_spacing)}
        captions = [e for e in events if e.source_index not in textures]
        composites = prototype_composite_backdrops(sources, captions, font_spacing)
        candidates += composites
        counts['prototype_composite_backdrops'] = len(composites)
        if config.max_drawing_chars > 0:
            candidates = [e for e in candidates if
                          len(OVERRIDE_RE.sub('', e.text)) <= config.max_drawing_chars]
        kept, associated = prototype_select_supports(candidates, captions, font_spacing)
        fallback_vectors = prototype_fallback_vectors(
            events, captions, kept, font_spacing, scaled_borders=scaled_borders)
        budgeted, capped = cap_vector_cues(kept+fallback_vectors, config.max_vectors_per_cue)
        budget_ids = {id(e) for e in budgeted}
        kept = [e for e in kept if id(e) in budget_ids]
        fallback_vectors = [e for e in fallback_vectors if id(e) in budget_ids]
        counts['prototype_vectors_capped'] = capped
        removed_textures = set()
        resx = prototype_resolution(lines, 'x')
        resy = prototype_resolution(lines, 'y')
        for e in events:
            if e.source_index not in textures:
                continue
            box = prototype_text_box(e, font_spacing)
            if box is not None:
                # Only ink inside the rendered viewport can affect the video.
                # Inset a boundary-touching test box for the strict polygon
                # containment helper; no ink outside the viewport is exposed.
                eps = 1e-4*e.unit
                box = (max(eps, box[0]), max(eps, box[1]),
                       min(resx-eps, box[2]), min(resy-eps, box[3]))
            if box is not None and box[0] < box[2] and box[1] < box[3] and any(
                    v.style == e.style and v.name == e.name and
                    v.start_s <= e.start_s+.001 and v.end_s >= e.end_s-.001 and
                    coverage_geometry(v) is not None and
                    polygon_covers_box(coverage_geometry(v)[0], box) and
                    polygon_covers_box(list(v.state.get('_prototype_original_points',
                                                         coverage_geometry(v)[0])), box) and
                    ((clip := rectangle_clip(v)) is None or
                     clip[0] < box[0] and clip[1] < box[1] and
                     clip[2] > box[2] and clip[3] > box[3]) for v in kept):
                removed_textures.add(e.source_index)
        counts['prototype_unmeasured_backdrops'] = len(fallback_vectors)
        fallback_ids = {e.source_index for e in fallback_vectors}
        # Enclosing supports were proved to be below their captions. Nearby
        # arrows may intentionally have a higher layer; preserve their original
        # layering rather than raising the associated literal text.
        result = [e for e in events
                  if (not (e.kind == 'Dialogue' and e.state.get('p', 0)) or
                      e.source_index in fallback_ids) and
                  e.source_index not in removed_textures]
        # Insert supports before their associated retained captions. Do not
        # sort unrelated same-layer captions by start time or source indices
        # from the other file: those indices belong to different documents.
        insertion, standalone = {}, []
        for v in kept:
            if not associated[v.source_index]:
                standalone.append(v)
                continue
            index = min(e.source_index for e in associated[v.source_index])
            insertion.setdefault(index, []).append(v)
        combined = sorted(standalone, key=lambda v: (int(v.layer), v.source_index))
        for e in result:
            combined.extend(sorted(insertion.pop(e.source_index, []),
                                   key=lambda v: (int(v.layer), v.source_index)))
            combined.append(e)
        # The text engine already ran its touching-copy pass. Preserve that
        # order after the targeted solid-mask correction and support insertion.
        combined = [dataclass_replace(e, source_index=i) for i, e in enumerate(combined)]
        rendered = []
        for e in combined:
            data = dict(zip(EVENT_FIELDS, e.fields()))
            data.update(actor=e.name, marked='Marked=0')
            rendered.append(f'{e.kind}: '+','.join(data.get(k, '') for k in fields))
        if indices:
            lines = lines[:indices[0]]+rendered+lines[indices[-1]+1:]
        elif rendered:
            section = next(i for i, line in enumerate(lines)
                           if line.strip().lower() == '[events]')
            end = next((i for i in range(section+1, len(lines))
                        if lines[i].strip().startswith('[')), len(lines))
            lines = lines[:end]+rendered+lines[end:]
        lines = mark_generated(lines)
        output.write_text('\n'.join(lines).rstrip('\n')+'\n', encoding='utf-8-sig')
        stats.update(counts)
        stats['excess_vectors'] += capped
        stats['prototype_supports_retained'] = len(kept)
        stats['prototype_textures_removed'] = len(removed_textures)
        stats['prototype_fullscreen_backgrounds'] = sum(prototype_fullscreen(v) for v in kept)
        stats['output'] = sum(e.kind == 'Dialogue' for e in combined)
        stats['max_concurrent_out'] = peak_concurrent_events(combined)
        stats['vector_output'] = sum(e.kind == 'Dialogue' and bool(e.state.get('p', 0))
                                     for e in combined)
        enclosed = 0
        for v in kept:
            if prototype_fullscreen(v):
                continue
            info = coverage_geometry(v)
            clip = rectangle_clip(v)
            if info is not None and any(prototype_shared_outline(v, e, info[0]) or
                    (box := prototype_text_box(e, font_spacing)) is not None and
                    polygon_covers_box(info[0], box) and (clip is None or
                    clip[0] < box[0] and clip[1] < box[1] and
                    clip[2] > box[2] and clip[3] > box[3]) for e in associated[v.source_index]):
                enclosed += 1
        stats['backdrops_retained'] = enclosed+len(fallback_vectors)+stats['prototype_fullscreen_backgrounds']
        stats['prototype_adjacent_shapes'] = len(kept)-enclosed-stats['prototype_fullscreen_backgrounds']
        print(f"  Vector supports: {len(kept)} supporting shapes; "
              f"{counts['prototype_strips_collapsed']} strips collapsed; "
              f"{len(removed_textures)} font textures removed")
        if scroll_report:
            print(f"  Scrolling fallback: {counts['prototype_scrolling_blocks_removed']} blocks removed; "
                  f"{counts['prototype_scrolling_blocks_retained']} retained; "
                  f"remaining block peak {counts['prototype_scrolling_peak_after_reduction']} "
                  f"(limit {config.scroll_concurrency_limit}; 0 disables removal)")
        return stats


if __name__ == '__main__':
    raise SystemExit(main())
