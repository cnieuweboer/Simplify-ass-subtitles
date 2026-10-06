#!/usr/bin/env python3
"""Simplify ASS/SSA subtitles at two levels for limited renderers.

Level 1 favors maximum reduction, retaining simple opaque caption backdrops;
level 2 retains static sign styling and
static vector shapes. Basic simplification requires only the standard library.
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

import argparse
import codecs
from bisect import bisect_left, bisect_right
import math
import logging
import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass, replace as dataclass_replace, field
from io import BytesIO
from itertools import islice
from pathlib import Path
from typing import Iterable

__version__ = "2026.10.06.61"
GENERATED_MARKER = "; Simplified by simplify_ass.py"


def mark_generated(lines: list[str]) -> list[str]:
    """Place one output marker inside Script Info, relocating legacy markers."""
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
    """Named, immutable settings shared by a subtitle simplification batch."""
    level: int = 1
    max_blur: float = 0.0
    short_duration: float = 0.16
    short_gap: float = 0.08
    max_drawing_chars: int = 0
    max_vectors_per_cue: int = 0
    encoding: str | None = None


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

    @property
    def anchors(self) -> list[tuple[str, float]]:
        return [(text, pos[0]) for _, text, pos in self.pieces]


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


def sample_transform_state(base: dict, transforms: list, at: float,
                           styles: dict, default: dict) -> dict:
    """Resolve ordered transforms at one instant without modifying the base."""
    state = base.copy()
    for begin, end, accel, changes in transforms:
        if at < begin:
            continue
        weight = 1.0 if end <= begin else min(1.0, max(0.0, (at-begin)/(end-begin))) ** accel
        target = state.copy()
        for name, value in changes:
            apply_tag(target, name, value, styles, default,event_tags=False)
        for key, finish in target.items():
            start = state.get(key, finish)
            if finish == start:
                continue
            if key.startswith("_"):
                state[key] = finish
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


def unrotated_text_state(state: dict) -> bool:
    """Treat whole turns on every axis as zero rotation."""
    return all(math.isfinite(state.get(k,0)) and
               abs(math.remainder(state.get(k,0),360)) <= .001
               for k in ('frz','frx','fry'))


def upright_text_state(state: dict) -> bool:
    """Recognize readable, unflipped text with no rotation on any axis."""
    return (state.get('1a',0) < 239 and
            all(state.get(k,100) > .01 for k in ('fscx','fscy')) and
            unrotated_text_state(state))


def select_static_state(base: dict, transforms: list, boundaries: set[float],
                        styles: dict, default: dict,
                        paint_events: Iterable[Event] | None = None,
                        opaque_spans: list[tuple[float,float]] | None = None,
                        settled_states: list[dict] | None = None, *,
                        prefer_upright: bool = False) -> dict:
    """Keep settled geometry and choose colours by their total visible time.

    Repeated colour holds add together across animation intervals. Event
    copies use compositing order, so simultaneous backing layers do not get
    duplicate votes. Colour ramps retain a representative interval sample.
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
    for start, end in zip(times,times[1:]):
        at = (start+end)/2
        state = sample_transform_state(base,transforms,at,styles,default)
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
    chosen = (max(candidates,key=lambda item:item[0])[1] if candidates else base).copy()
    if prefer_upright and not chosen.get('p',0) and not unrotated_text_state(chosen):
        holds = [item for item in candidates if item[0][0] and item[0][1] and
                 upright_text_state(item[1]) and not item[1].get('p',0)]
        if holds:
            chosen = max(holds,key=lambda item:item[0])[1].copy()
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
                 prefer_upright: bool = False) -> tuple[str, dict]:
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
                                prefer_upright=prefer_upright)
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
                         level: int = 2) -> tuple[str, str, int]:
    default = default or DEFAULT_STATE
    state = default.copy()
    output, visible = [], []
    drawing_chars = 0
    for part in re.split(r"(\{[^}]*\})", text):
        if part.startswith("{") and part.endswith("}"):
            block,state = freeze_block(part[1:-1],duration or 1, state,default,styles or {},max_blur,
                                      prefer_upright=level == 1)
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
    """Join adjacent rectangular clips with identical text and paint.

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
    """Flatten identical opaque text into its foreground and one outline.

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


def flatten_aggressive_text_copies(events: list[Event],
                                   visible_map: dict[int,str],
                                   animated_sources: set[int] | None = None) -> tuple[list[Event], int]:
    """Replace stacked static copies of the same positioned text with one.

    This is for level 1: color gradients, clipped stripes, shadows and
    alternate paint layers are intentionally replaced by a readable caption.
    No font, style name, color, language or strip-count assumption is used.
    """
    groups = {}
    kept = []
    for e in events:
        visible = visible_map.get(e.source_index, "")
        pos = get_pos(e.text)
        if (e.kind != "Dialogue" or not visible or pos is None or
                e.state.get("p", 0) > 0 or inline_layout_key(e)):
            kept.append(e)
            continue
        key = (e.start, e.end, e.style, e.name, e.margin_l, e.margin_r,
               e.margin_v, pos, visible)
        groups.setdefault(key, []).append(e)
    removed = 0
    for key, group in groups.items():
        clipped = any("clip" in e.state or "iclip" in e.state for e in group)
        # Some effects paint the letters entirely with the shadow channel.
        # A stack of animated, coincident shadow copies is still one text
        # object; normalize it before dedup discards the channel evidence.
        shadow_text = (not clipped and len({text_layout_key(e) for e in group}) == 1 and
                       all(e.source_index in (animated_sources or set()) and
                           e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254
                           for e in group) and
                       any(e.state.get("4a",0) < 254 and
                           any(abs(e.state.get(k,0)) > 0 for k in ("shad","xshad","yshad"))
                           for e in group))
        solid_stack = (not clipped and len({text_layout_key(e) for e in group}) == 1 and
                       any(e.state.get("1a",255) < 128 for e in group))
        if (len(group) < 2 or not (shadow_text or solid_stack or
                clipped and any(e.state.get("1a", 255) == 0 for e in group))):
            kept.extend(group)
            continue
        # A complete, unclipped text copy is the best source for the font and
        # size. The output paint is uniform and opaque by design in level 1.
        # Dominantly visible foreground paint may be slightly translucent.
        # Prefer its actual compositing order over an opaque backing fill.
        candidates = (group if shadow_text else
                      [e for e in group if e.state.get("1a",255) < 128] if solid_stack else
                      [e for e in group if e.state.get("1a",255) == 0])
        chosen = max(candidates,key=lambda e:(
            "clip" not in e.state and "iclip" not in e.state,
            int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
            e.source_index))
        text = aggressive_caption(chosen.state, OVERRIDE_RE.sub("", chosen.text),
                                  outline_states=[e.state for e in group])
        kept.append(replace_event(chosen, text=text, layer="0", effect="",
                            source_index=min(e.source_index for e in group)))
        removed += len(group)-1
    return sorted(kept,key=lambda e:e.source_index), removed


def remove_masked_glyph_effects(events: list[Event],
                                visible_map: dict[int,str],
                                metric: FontSpacing | None = None,
                                animated_sources: set[int] | None = None) -> tuple[list[Event],int]:
    """Remove matching text copies or masks proven to trace an underlying glyph.

    Outline matching uses the exact font, contour topology and every control
    point. Shadow-only texture stacks can also be identified by their shared
    mask over a retained caption. Other unavailable-font or unsupported masks
    stay intact.
    This is an aggressive-mode substitution, not an assertion of occlusion.
    """
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
        if any(upright_text_state(state) and
               all(state.get(k,DEFAULT_STATE.get(k)) == e.state.get(k,DEFAULT_STATE.get(k))
                   for k in geometry) for state in settled):
            holds.append(e)
    return holds


def event_override_tokens(e: Event) -> list[tuple[str,str]]:
    return [token for block in OVERRIDE_RE.findall(e.text)
            for token in tokenize_override(block)]


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
                           allowed: set[str]) -> tuple[float,float,list[tuple[str,str]]] | None:
    """Validate one transform used as evidence for an effect family.

    Resolve all four ASS timing forms, requiring forward finite timing and
    positive acceleration. These proofs allow at most 50 ms of endpoint
    rounding; the general static freezer retains its more permissive parsing.
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
            not 0 <= begin < end <= 1000*duration+50 or
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
        elif not movement and len(transforms) == 1 and pos is not None and p.duration <= .15:
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
                e.state.get('1a',0) == 0 and upright_text_state(e.state)):
            current.setdefault((geometry(e),word,pos),[]).append(e)

    def retained(p: Event) -> Event | None:
        matches = [e for e in current.get((geometry(p),simplify_text(p.text,visible_only=True)[1],
                                           get_pos(p.text)),[])
                   if e.start_s <= p.start_s+.001 and e.end_s >= p.end_s-.001]
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
        # Brief authored fades at the start may survive separately when the
        # previous row overlaps. Only an exact, touching word phase belongs.
        prefixes = [p for p in static.get((key,word),[]) if p.end == before.start and
                    get_pos(p.text) == get_pos(parent.text) and paint(p.state) == paint(parent.state) and
                    0 < p.duration <= .15 and retained(p) is not None and
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
        tags = ''.join(render_tag(k,state[k]) for k in ('1c','3c','3a','bord','xbord','ybord')
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
        if (original is not None and 0 < original.duration <= .25 and
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
                if 0 < len(visible_map.get(e.source_index,"")) <= 4 and
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
            if (len(words) > 4 or len(moves) != 1 or state.get("an") != 5 or
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
                if first.layer != source.layer or first.duration > .25*source.duration:
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


def remove_letters_over_full_lines(events: list[Event],
                                   visible_map: dict[int, str],
                                   source_events: dict[int, Event] | None = None,
                                   row_evidence: list[TextRow] | None = None) -> tuple[list[Event], int]:
    """Use an authored full line when its overlaid letter effects spell it.

    Match complete text and placement, using either equal timing or paired
    entrance/exit rows. Nearby letters alone never prove caption ownership.
    """
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind == "Dialogue" and get_pos(e.text) is not None and visible_map.get(e.source_index):
            groups.setdefault((e.style,e.name,e.start,e.end,e.row,
                               e.margin_l,e.margin_r,e.margin_v),[]).append(e)
    removed: set[int] = set()
    replacements: dict[int,Event] = {}
    norm = lambda value: "".join(value.split()).casefold()
    if source_events is not None and row_evidence is not None:
        removed,authored_rows = match_authored_lyric_rows(events,visible_map,source_events)
        row_evidence.extend(authored_rows)
    for group in groups.values():
        full_lines = [e for e in group if len(visible_map[e.source_index]) >= 8
                      and len(visible_map[e.source_index].split()) >= 2]
        for full in full_lines:
            if full.source_index in removed:
                continue
            fx = [e for e in group if e is not full and e.source_index not in removed
                  and len(visible_map[e.source_index]) <= 4
                  and abs(get_pos(e.text)[1]-get_pos(full.text)[1]) <= .1*text_height(full)]
            if len(fx) < 8:
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
            if norm(assembled) != norm(visible_map[full.source_index]):
                continue
            xs = [get_pos(col[0].text)[0] for col in columns]
            if not min(xs) <= get_pos(full.text)[0] <= max(xs):
                continue
            # The author's complete, spaced text is the canonical caption.
            # Level 1 gives it one opaque fill and contour instead of retaining
            # translucent backing paint plus dozens of animated letters.
            replacements[full.source_index] = replace_event(
                full, text=aggressive_caption(full.state,visible_map[full.source_index]),
                layer="0", effect="")
            removed.update(e.source_index for e in fx)
    return [replacements.get(e.source_index,e) for e in events
            if e.source_index not in removed], len(removed)


class FontSpacing:
    """Recover spaces from exact font advances and a consistent row geometry.

    No language model or word list is involved. Font files are matched by their
    internal family/full names and face flags; substitution is never allowed.
    """
    def __init__(self, directories=()):
        self.faces = {}
        self.loaded = {}
        self.font_bytes = {}
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
                        cmap = set((face.getBestCmap() or {}).keys())
                        for name in names:
                            self.faces.setdefault((name,bold,italic),(str(path),index,cmap))
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
        face = self.faces.get((family.casefold(),bold,italic))
        if face is None:
            face = self.faces.get((family.casefold(),not bold,italic))
        return face

    def measure(self, face, text: str, kerning: bool = False) -> float:
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
            return font.getlength(text,features=["kern" if kerning else "-kern"])
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
        hb.shape(self.shaping_fonts[key],buffer,{"kern":bool(kerning)})
        if any(info.codepoint == 0 for info in buffer.glyph_infos):
            raise ValueError("Shaping produced a missing glyph")
        if any(position.y_advance for position in buffer.glyph_positions):
            raise ValueError("Vertical glyph advances are unsupported")
        return sum(position.x_advance for position in buffer.glyph_positions)/64

    def recover(self, ordered, fragments):
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

    def fragment_anchor(self, state: dict, xs: list[float], fragments: list[str],
                        text: str, unit: float, *, allow_tracking: bool = False,
                        separate_glyphs: bool = False) -> float | None:
        """Fit an authored fragment anchor to exact-font glyph positions.

        Calibrate the font's common size convention from the recorded run;
        leading and trailing spaces shift its anchor without inventing gaps.
        Tracking is opt-in for matching known glyph text, not spacing recovery.
        Separately rendered glyphs use their own advances; contextual shaping
        of the assembled word must not change the measured letter-run span.
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
        return (xs[0]-anchor*factor*widths[0]+
                factor*(anchor*width+(anchor-1)*leading+anchor*trailing)+
                tracking*(anchor*(len(text.strip())-len(fragments[0]))+
                          (anchor-1)*(len(text)-len(text.lstrip()))+
                          anchor*(len(text)-len(text.rstrip()))))

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
                          fscx: float, fscy: float) -> str | None:
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
    return body


def reconstruct_text_rows(events: list[Event], visible_map: dict[int,str],
                          space_map: dict[tuple,set[float]],
                          font_spacing: FontSpacing | None,
                          animated_sources: set[int],
                          source_rows: list[TextRow] | None = None,
                          source_only: bool = False) -> tuple[list[Event],int,int,list[TextRow]]:
    """Reconstruct static and animated rows with shared evidence and rendering.

    Static fragments must share their complete timing and effective styling.
    Extending timings requires animation evidence for every fragment, monotonic
    starts and ends, and overlapping visibility. A chain without a common
    interval also requires exact-font spacing recovery. Spaces come from authored
    text, explicit blank positions, or measured advances in the exact font.
    Persistent matching row neighbors cannot occupy gaps between fragments.
    If spacing is unproven, preserve the original fragment positions and timing.
    """
    source_rows = [row for row in (source_rows or []) if row.confirmed]
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
    duplicate_count = merged_count = 0

    # Collapse paint copies only at the same position, with matching text,
    # geometry and complete timing. This precedes row reconstruction so that
    # duplicate glyphs cannot become duplicate letters in the assembled text.
    copies: dict[tuple,list[Event]] = {}
    for e in events:
        if (e.kind == "Dialogue" and get_pos(e.text) is not None and
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

    def join(run: list[Event], animated: bool) -> bool:
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
        # Font advances cannot distinguish real spaces from omitted letters.
        # A persistent matching glyph between candidate anchors disproves a
        # complete row. Mutual overlap leaves brief entrance/exit effects alone.
        members = {e.source_index for e in run}
        y = statistics.median(ys)
        (positions,spatial),(starts,temporal) = neighbors[base_key(ordered[0])]
        left,right = bisect_right(positions,xs[0]+tolerance),bisect_left(positions,xs[-1]-tolerance)
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
        if text is None and font_spacing is not None:
            # Karaoke pulses can leave different sampled scales per glyph.
            # Animated rows share their median scale; static rows are exact.
            metric_row = [dataclass_replace(e,state={**e.state,"fscx":sx,"fscy":sy})
                          for e in ordered] if animated else ordered
            fit = font_spacing.recover(metric_row,fragments)
            if fit is not None:
                text,x,sx,sy,alignment = fit
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
        if text is None or animated and not shared_interval and not measured:
            return False
        chosen = ordered[0]
        body = render_merged_caption(ordered,fragments,text,animated=animated,
                                     an=alignment,pos=(x,y),fscx=sx,fscy=sy)
        if body is None:
            return False
        first = min(e.source_index for e in run)
        replacements[first] = replace_event(chosen,source_index=first,
            start=format_time(start),end=format_time(end),start_s=start,end_s=end,
            text=body,effect="",layer="0" if animated else chosen.layer)
        visible_map[first] = text
        row_evidence[first] = TextRow(replacements[first],
            [(e,text,(x,y)) for e,text,x,y in zip(ordered,fragments,xs,ys)])
        if animated and not shared_interval:
            chain_families.add(base_key(ordered[0]))
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
        if e.source_index in animated_sources and e.source_index not in protected:
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
        if not row.virtual and key in chain_families:
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
                    end = peer.base.start_s
                    row.base = replace_event(row.base,end=format_time(end),end_s=end)
                    replacements[index] = row.base
                    break
    output = [replacements.get(e.source_index,e) for e in events if e.source_index not in removed]
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
    Colour pulses must return to that shared paint; frame jitter must converge
    to it. Partial rows, gradients, ambiguous copies and moving labels stay.
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
            if any(not .8*base.get(k,100) <= sample.get(k,100) <= 1.2*base.get(k,100)
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
            if (int(p.layer) >= max(int(e.layer) for e in copies) and
                    all(base.state.get(k,100) <= p.state.get(k,100) <= 1.5*base.state.get(k,100) and
                        final.get(k,100) == base.state.get(k,100) for k in ('fscx','fscy'))):
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


def remove_source_fragment_effects(events: list[Event], row_evidence: list[TextRow],
                                   words: dict[int,str],
                                   positions: dict[int,tuple[float,float] | None],
                                   animated_sources: set[int] | None = None) -> tuple[list[Event],int]:
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
        syllables = {}
        for index, (_, _, start_pos) in enumerate(row.pieces):
            text = ""
            for last in range(index, len(row.pieces)):
                text += "".join(row.pieces[last][1].split())
                if len(text) > 8:
                    break
                end_pos = row.pieces[last][2]
                if last > index and (end_pos[0]-row.pieces[last-1][2][0] > 2*height):
                    break
                syllables.setdefault(text, []).append(
                    ((start_pos[0]+end_pos[0])/2, (start_pos[1]+end_pos[1])/2))
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
                matches = [anchor for anchor in syllables.get(''.join(words[e.source_index].split()),[]) if
                           abs(pos[0]-anchor[0]) <= .12*height and
                           abs(pos[1]-anchor[1]) <= .06*height]
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


def match_boundary_glyph_effects(events: list[Event], visible_map: dict[int,str],
                                 source_events: dict[int,Event],
                                 metric: FontSpacing | None) -> set[int]:
    """Prove whole rotating entrances and flying exits of retained words.

    The source phase must touch the static caption, spell every fragment in
    order, and fit each authored word anchor with the exact font, including
    tracking. Partial groups, duplicate letters and unrelated labels cannot
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
    for e in events:
        original = source_events.get(e.source_index)
        if original is None or e.kind != 'Dialogue' or inline_layout_key(original):
            continue
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (e.duration > .25 and word and pos is not None and upright_text_state(e.state) and
                e.state.get('1a',0) == 0 and not any(c.isspace() for c in word) and
                not any(k in e.state for k in ('clip','iclip','org')) and
                get_pos(original.text) == pos):
            key = geometry(e,pos[1])
            for phase,boundary in (('entrance',e.start),('exit',e.end)):
                captions.setdefault((phase,boundary,key),[]).append(e)
        glyph = simplify_text(original.text,visible_only=True)[1]
        if (len(glyph) != 1 or glyph.isspace() or unicodedata.combining(glyph) or
                not 0 < original.duration <= .25):
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
            phase,boundary,pos = 'entrance',original.end,get_pos(original.text)
        elif len(moves) == 1 and not transforms and unrotated_text_state(state):
            move = parse_effect_move(moves[0],original.duration,endpoint_slack=50)
            if (move is None or math.dist(move[:2],move[2:4]) < e.unit or
                    get_pos(original.text) is not None or
                    fade[0] != 0 or not 0 < fade[1] <= 1000*original.duration+50):
                continue
            phase,boundary,pos = 'exit',original.start,tuple(move[:2])
        if phase is not None:
            source = dataclass_replace(original,state=state)
            key = (phase,boundary,geometry(source,pos[1]))
            if e.duration > .25:
                # A one-letter syllable may already include its entrance in
                # the retained cue. It proves its slot but must never be
                # removed along with the remaining short decorative letters.
                if (phase != 'entrance' or word != glyph or get_pos(e.text) != pos or
                        not upright_text_state(e.state) or e.state.get('1a',0) != 0):
                    continue
                captions.setdefault(key,[]).append(e)
            groups.setdefault(key,[]).append((e,pos,glyph))

    removed = set()
    for key,peers in groups.items():
        words = sorted(captions.get(key,[]),key=lambda e:get_pos(e.text)[0])
        peers.sort(key=lambda item:item[1][0])
        if (not words or sum(len(visible_map[e.source_index]) for e in words) != len(peers) or
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
            removed.update(e.source_index for e,p,c in peers if e.duration <= .25)
    return removed


def match_departing_glyph_effects(events: list[Event], row_evidence: list[TextRow],
                                  source_events: dict[int,Event],
                                  metric: FontSpacing | None) -> set[int]:
    """Prove complete outline exits from retained fragments' original anchors.

    A whole letter group must spell its source fragment, begin when that
    fragment ends, and fit the exact font at its authored position. Moving,
    fading contours are decorative exits; partial or ambiguous groups stay.
    This proof uses source trajectories rather than frozen effect positions.
    """
    if metric is None or not metric.available or not any(not row.virtual for row in row_evidence):
        return set()
    groups: dict[tuple,list[tuple[Event,list[float],str]]] = {}
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
        groups.setdefault((original.style,original.name,original.start,
                           placement_key(dataclass_replace(original,state=state))[0],layout),[]).append(
                               (e,move,word))
    proofs: dict[tuple,list[set[int]]] = {}
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
            key = (piece.style,piece.name,original.end,placement_key(piece)[0],layout)
            peers = sorted(groups.get(key,[]),key=lambda item:item[1][0])
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
            proofs.setdefault(key,[]).append({e.source_index for e,move,char in peers})
    return set().union(*(matches[0] for matches in proofs.values() if len(matches) == 1))


def match_staggered_row_effects(events: list[Event], row_evidence: list[TextRow],
                                source_events: dict[int,Event],
                                animated_sources: set[int],
                                metric: FontSpacing | None) -> set[int]:
    """Prove complete animated copies at a recorded row's source phase ends.

    Normalize vertical alignment at the stable pose. Every source fragment
    must belong to exactly one copy, with a shared phase offset, monotonic
    timing and matching font geometry. Partial and ambiguous families stay.
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
        if (max(offsets)-min(offsets) > .011 or
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
    paint; virtual rows authorize only matching shadow copies. Original
    trajectories and exact font measurements prove entrance and exit groups.
    """
    animated_sources = animated_sources or set()
    anchors = {row.base.source_index: row.anchors for row in row_evidence}
    models = {row.base.source_index: row for row in row_evidence}
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
            if (paint.get('1a',0) != 0 or paint.get('3a',0) != 0 or
                    (int(paint.get('an',2))-1)//3 != (int(piece.state.get('an',2))-1)//3 or
                    abs(get_pos(row.base.text)[1]-pos[1]) > .001):
                continue
            emitted = dataclass_replace(piece,state=paint)
            glyphs.append((piece,text,pos,state_key(emitted,{'pos','an'})))
        static_glyphs[row.base.source_index] = glyphs

    def held_glyph_copy(e: Event, visible: str, pos: tuple, base: Event) -> bool:
        if (not static_glyphs.get(base.source_index) or
                e.source_index in animated_sources or len(visible) != 1 or
                e.style != base.style or e.name != base.name or
                e.start_s < base.start_s or e.end_s > base.end_s):
            return False
        matches = [(piece,paint) for piece,text,anchor,paint in
                   static_glyphs.get(base.source_index,[]) if text == visible and
                   math.dist(pos,anchor) <= .001]
        if len(matches) != 1:
            return False
        piece,paint = matches[0]
        return (e.layer == piece.layer and placement_key(e) == placement_key(piece) and
                state_key(e,{'pos'}) == state_key(piece,{'pos'}) and
                state_key(e,{'pos','an'}) == paint and
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
    for e in events:
        pos = get_pos(e.text)
        visible = visible_map.get(e.source_index,"")
        if (e.kind != "Dialogue" or e.source_index in anchors or pos is None or
                not visible or len(visible)>8 or e.state.get("p",0) or
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
            for index in range(len(glyphs)):
                text = ""
                for last in range(index,min(len(glyphs),index+8)):
                    text += glyphs[last][0]
                    if len(text)>len(visible)+2:
                        break
                    if (("".join(text.split()).casefold() == "".join(visible.split()).casefold()
                         if shadow_only else "".join(text.split()) == "".join(visible.split()))
                            and abs(pos[0]-(glyphs[index][1]+glyphs[last][1])/2)
                            <= ((.6 if len(visible)>2 else .24)*text_height(base)
                                if shadow_only else .12*min(text_height(e),text_height(base)))):
                        matches.append((index,last))
            if len(matches) == 1:
                removed.add(e.source_index)
            if e.source_index in removed:
                break
    return [e for e in events if e.source_index not in removed],len(removed)


def static_object_key(e: Event, styles: dict) -> tuple | None:
    """Describe every static text/drawing span, including inherited styling."""
    if e.kind != "Dialogue" or e.effect or e.duration <= 0:
        return None
    # Unpositioned subtitles participate in renderer collision placement.
    # Extending one could change that placement even with identical text.
    if get_pos(e.text) is None:
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


def trim_faded_cue_overlaps(events: list[Event], rows: list[TextRow],
                            source_events: dict[int,Event]) -> tuple[list[Event],int]:
    """Give consecutive static rows a clean handoff within their source fades.

    Reconstructed rows supply their original fragment anchors. Every retained
    fragment, including separate font spans, must match complete source fade
    entrances and tails at the cue's boundaries. Only colliding rows whose
    non-fading cores are disjoint qualify. Ambiguous or incomplete cue groups,
    simultaneous cores and independent positions keep their original timing.
    """
    def lane(e: Event, pos: tuple[float,float], state: dict) -> tuple:
        return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
                round(pos[1],4),(int(state.get('an',2))-1)//3)

    def scrolling(e: Event) -> bool:
        return e.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'}

    def slot(e: Event, pos: tuple[float,float]) -> tuple | None:
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
        if len(starts) != 1 or len(ends) != 1:
            proven[key,timing] = None
            continue
        core_start,core_end = next(iter(starts)),next(iter(ends))
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
        for timing,field in ((left,'end'),(right,'start')):
            for e in groups[key][timing]:
                changes = replacements.setdefault(e.source_index,{})
                changes.update({field:format_time(boundary),field+'_s':boundary})
        trimmed += 1
    return [replace_event(e,**replacements[e.source_index])
            if e.source_index in replacements else e for e in events],trimmed


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
    animated_sources = {idx for idx,e in parsed_by_line.items()
                        if re.search(r"\\(?:t\s*\(|[kK](?:f|o)?\d|fad(?:e)?\s*\(|move\s*\()", e.text)}
    source_rows = []
    source_effects = 0
    working_by_line = parsed_by_line
    if config.level == 1:
        # Identify original cue geometry once. Existing stages consume that
        # evidence before transformations can extend a lyric through its tail.
        source_data = collect_source_text_rows(parsed_by_line,animated_sources)
        source_events, source_effects = remove_source_fragment_effects(
            list(parsed_by_line.values()),source_data[0],source_data[1],source_data[2],animated_sources)
        source_events, _, _, source_rows = reconstruct_text_rows(
            source_events,source_data[1],{},None,animated_sources,
            source_rows=source_data[0],source_only=True)
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
        new_text, visible, drawing_chars = simplify_visual_text(
            e.text, config.max_blur, e.duration, styles.get(e.style,DEFAULT_STATE), styles, config.level)
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
    if config.level == 1:
        simplified_events, masked_decorations = remove_masked_glyph_effects(
            simplified_events, visible_map, font_spacing, animated_sources)
        simplified_events, aggressive_copies = flatten_aggressive_text_copies(
            simplified_events, visible_map, animated_sources)

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
    if config.level == 2:
        simplified_events, tiles_joined = join_text_clip_tiles(simplified_events)

    # For visual signs, choose their visible fill before same-layer dedup can
    # discard a brighter effect copy merely because it appeared later.
    text_copies_removed = 0
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
    staggered_rows = fullwidth_merged = progressive_rows = 0
    overlaid_letters = covered_fragments = cue_overlaps_trimmed = 0
    if config.level == 1:
        simplified_events, aggressive_sequences = flatten_aggressive_text_sequences(
            simplified_events, visible_map, styles, animated_sources,
            source_events=parsed_by_line,font_spacing=font_spacing)
        authored_rows: list[TextRow] = []
        simplified_events, overlaid_letters = remove_letters_over_full_lines(
            simplified_events, visible_map,parsed_by_line,authored_rows)
        simplified_events, lyric_merged, row_duplicates, row_evidence = reconstruct_text_rows(
            simplified_events, visible_map, space_map, font_spacing, animated_sources,
            source_rows=source_rows)
        deduped += row_duplicates
        simplified_events, covered_fragments = remove_covered_fragment_effects(
            simplified_events, visible_map, row_evidence+authored_rows, animated_sources,parsed_by_line,font_spacing)
        covered_fragments += source_effects
        simplified_events, cue_overlaps_trimmed = trim_faded_cue_overlaps(
            simplified_events,row_evidence+authored_rows,parsed_by_line)
    covered_vectors = 0
    vector_copies_removed = vector_glows_removed = vector_frames_removed = excess_vectors = 0
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

    static_merged = 0
    if config.level == 2:
        simplified_events, static_merged = merge_static_timed_copies(simplified_events, styles)

    # Rebuild [Events] while preserving all non-dialogue/event metadata lines.
    # We replace Dialogue/Comment lines at their original region with the processed sequence.
    event_line_indices = sorted(parsed_by_line)
    if not event_line_indices:
        output.write_text("\n".join(mark_generated(lines)) +
                          ("\n" if raw.endswith(("\n", "\r")) else ""), encoding="utf-8-sig")
        return {key: 0 for key in ("original", "output", "deduped", "lyric_merged",
                "merged", "dropped", "overlap_removed", "cue_overlaps_trimmed", "full_copies_removed", "phase_merged",
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
        "backdrops_retained": backdrops_retained,
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Simplify ASS/SSA subtitles at level 1 (aggressive) or 2 (retain static visuals)."
    )
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("inputs", nargs="+", help="ASS/SSA file(s) or folder(s)")
    ap.add_argument("-r", "--recursive", action="store_true", help="scan folders recursively")
    ap.add_argument("--level", type=int, choices=(1, 2), default=1,
                    help="1: maximum reduction (default); 2: preserve static visual elements")
    ap.add_argument("--suffix", default=".simple", help="output suffix before extension (default: .simple; compatible with the MKV wrapper); scans skip marked outputs (and legacy *.simple files with the default suffix)")
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
    ap.add_argument("--fonts-dir", action="append", default=[], metavar="FOLDER",
                    help="extra font folder (repeatable); exact fonts enable measured word spacing")
    ap.add_argument("--font-mkv", type=Path, metavar="FILE",
                    help="read font attachments from this MKV using MKVToolNix; source stays untouched")
    ap.add_argument("--no-font-spacing", action="store_true",
                    help="disable measured spacing; preserve uncertain fragment positions")
    ap.add_argument("--stats-json", type=Path, metavar="FILE",
                    help="also write per-input event counts as JSON for batch reports")
    args = ap.parse_args()

    if not args.suffix.strip() or any(c in args.suffix for c in '/\\:*?"<>|'):
        ap.error("--suffix must be nonempty and contain no filename separators or reserved characters")
    if args.encoding:
        try:
            codecs.lookup(args.encoding)
        except LookupError:
            ap.error(f"Unknown input encoding: {args.encoding}")
    inputs = iter_inputs(args.inputs, args.recursive, args.suffix)
    if not inputs:
        ap.error("No .ass/.ssa files found")

    config = SimplifyConfig(level=args.level, max_blur=args.max_blur,
        short_duration=args.short_duration, short_gap=args.short_gap,
        max_drawing_chars=args.max_drawing_chars,
        max_vectors_per_cue=args.max_vectors_per_cue, encoding=args.encoding)
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
            try:
                if dst.resolve() in input_paths:
                    raise ValueError(f"Output is another input file: {dst}; choose a different --suffix.")
                stats = simplify_ass(src, dst, config, font_spacing=metric)
            except (ValueError,OSError) as exc:
                failed += 1
                records.append({"input":str(src.resolve()),"output":str(dst.resolve()),
                                "error":str(exc)})
                print(f"Error: {src.name}: {exc}",file=sys.stderr)
                continue
            total_in += stats["original"]
            total_out += stats["output"]
            records.append({"input": str(src.resolve()),
                            "output": str(dst.resolve()), "stats": stats})
            print(f"{src.name} -> {dst.name} (level {args.level})")
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
                f"aggressive text copies flattened: {stats['aggressive_copies']}, "
                f"text effect sequences frozen: {stats['aggressive_sequences']}, "
                f"covered fragment effects removed: {stats['covered_fragments']}, "
                f"vector copies: {stats['vector_copies_removed']}, "
                f"covered contours: {stats['vector_glows_removed']}, "
                f"fully covered drawings: {stats['covered_vectors']}, "
                f"drawing animation frames: {stats['vector_frames_removed']}, "
                f"vectors retained: {stats['vector_output']}, "
                f"caption backdrops retained: {stats['backdrops_retained']}, "
                f"excess vector details removed: {stats['excess_vectors']}, "
                f"drawings/effects dropped: {stats['dropped']})"
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


if __name__ == "__main__":
    raise SystemExit(main())
