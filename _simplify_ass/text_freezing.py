"""Static override/text freezing; callers retain event and reporting ownership."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from .ass_overrides import (
    DEFAULT_STATE, NUMBER, OVERRIDE_RE, OverrideContinuation, OverrideEvaluation,
    apply_override, effective_state, resolve_event_style, tokenize_override,
)
from .static_selection import StaticPoseEvidence, StaticStateSelection, select_static_state
from .caption_rendering import render_tag
from .caption_geometry import NUM
from .event_model import Event
from .event_operations import replace_event

# Static tag whitelist for simplify_text(); visual freezing handles more tags.
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


@dataclass(frozen=True)
class FrozenBlock:
    """Serialized static overrides and the formatting/evidence selection behind them."""
    text: str
    selection: StaticStateSelection


def safe_override(block: str, max_blur: float = 0.0) -> str:
    frozen = freeze_block(block, 1.0, DEFAULT_STATE, DEFAULT_STATE, {}, max_blur).text
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


def _freeze_inputs(block: str, duration: float, initial: dict, default: dict,
                   styles: dict, *, continuation: OverrideContinuation = OverrideContinuation()
                   ) -> tuple[OverrideEvaluation,list,set,str | None]:
    """Parse one source header for freezing and exact boundary evidence."""
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
                    continuation = apply_override(base,child,argument,styles,default,continuation)
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
            continuation = apply_override(base,name,value,styles,default,continuation)
            if name == "r":
                reset = value
    return OverrideEvaluation(base,continuation),transforms,boundaries,reset


def freeze_block(block: str, duration: float, initial: dict, default: dict,
                 styles: dict, max_blur: float,
                 prior_opaque_spans: Iterable[tuple[float,float]] | None = None,
                 prior_settled_states: Iterable[dict] | None = None, *,
                 prefer_upright: bool = False,
                 upright_crossings: bool = True,
                 prior_pose: StaticPoseEvidence | None = None,
                 continuation: OverrideContinuation = OverrideContinuation()) -> FrozenBlock:
    """Return overrides and their selection without modifying supplied evidence seeds."""
    evaluated,transforms,boundaries,reset = _freeze_inputs(block,duration,initial,default,styles,
                                                        continuation=continuation)
    base = evaluated.formatting
    selection = select_static_state(base,transforms,boundaries,styles,default,
                                prior_opaque_spans=prior_opaque_spans,
                                prior_settled_states=prior_settled_states,
                                prefer_upright=prefer_upright,upright_crossings=upright_crossings,
                                prior_pose=prior_pose if reset is None else None,
                                continuation=evaluated.continuation)
    state = selection.state
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
    return FrozenBlock(text,selection)


def simplify_visual_text(text: str, max_blur: float, duration: float | None = None,
                         default: dict | None = None, styles: dict | None = None,
                         level: int = 2, *, upright_crossings: bool = True) -> tuple[str, str, int]:
    default = default or resolve_event_style(styles or {}, 'Default')
    state = default.copy()
    continuation = OverrideContinuation()
    pose = StaticPoseEvidence()
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
            frozen = freeze_block(part[1:-1],duration or 1, state,default,styles or {},max_blur,
                                      prefer_upright=level == 1,upright_crossings=upright_crossings,
                                      prior_pose=pose,continuation=continuation)
            block,state = frozen.text,frozen.selection.state
            pose = frozen.selection.pose
            continuation = frozen.selection.continuation
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
