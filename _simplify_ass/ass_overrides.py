"""ASS style and ordered override interpretation, independent of engine policy.

Callers own formatting buffers and borrow style/default catalogs. Continuation
and evaluation records retain their existing frozen bindings; formatting stays
an ordinary dictionary. Event caches, sampling and output policy belong to callers.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


OVERRIDE_RE = re.compile(r"\{([^}]*)\}")


@dataclass(frozen=True)
class OverrideContinuation:
    """Parser history that governs later overrides, separate from formatting.

    None means the tag has not occurred; an empty reset name records an
    explicit empty/unknown reset. Even an invalid first alignment consumes
    the latch, which survives style resets. Immutable snapshots can be shared
    across literal spans and copied independently into evaluation branches.
    """
    reset_style: str | None = None
    # Legacy seeds may carry a numeric latch; its truth value still determines
    # first-alignment handling. Canonical overrides only set it to True.
    alignment_set: bool | float | None = None


@dataclass(frozen=True)
class OverrideEvaluation:
    """Resolved formatting paired with its immutable parser successor.

    The frozen binding does not freeze its dictionary. Complete parsers and
    samplers own fresh buffers; event_evaluation may borrow an event cache.
    Consumers copy borrowed formatting before applying overrides.
    """
    formatting: dict
    continuation: OverrideContinuation


# Recognized syntax is independent of the simplifier's permitted output tags.
# Match longer names before their prefixes; same-length alternatives are distinct.
TAG_NAMES = sorted({
    "an", "a", "b", "i", "u", "s", "fn", "fs", "fsp", "fscx", "fscy",
    "frz", "fr", "bord", "xbord", "ybord", "shad", "xshad", "yshad",
    "c", "1c", "2c", "3c", "4c", "q", "r",
    "alpha", "1a", "2a", "3a", "4a", "blur", "be", "p", "pbo",
    "frx", "fry", "fax", "fay", "pos", "move", "org", "clip", "iclip",
    "t", "fad", "fade", "k", "kf", "ko", "kt",
}, key=len, reverse=True)


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


def resolve_event_style(styles: dict, name: str, fallback: dict | None = None) -> dict:
    """Resolve an event style exactly, then use the file's Default style.

    Event lookup accepts the legacy star prefix and canonical Default name.
    Named override resets use their own strict lookup in apply_override.
    """
    name = name.lstrip('*')
    if not name or name.lower() == 'default':
        name = 'Default'
    return styles.get(name, styles.get('Default',
                      fallback if fallback is not None else DEFAULT_STATE))


def parse_styles(lines: list[str]) -> dict[str, dict]:
    # libass supplies this style even if the file defines no Default style.
    # Keep DEFAULT_STATE's standalone helper defaults separate from it.
    implicit = {**DEFAULT_STATE, 'fs':18.0, 'b':200.0, 'bord':2.0, 'shad':3.0,
                '2c':'FFFF00', '4a':128, 'borderstyle':1.0, 'encoding':0.0,
                'marginl':20.0, 'marginr':20.0, 'marginv':20.0}
    result, fields, section = {'Default':implicit}, [], ""
    kerning = False
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            section = line.casefold()
        elif section == "[script info]" and line.lower().startswith("kerning:"):
            kerning = line.split(":",1)[1].strip().casefold() in {"yes","1","-1","true"}
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
                result[values.get("name", "Default").lstrip('*')] = state
    for state in result.values():
        state["kerning"] = kerning
    return result


def apply_font_size(state: dict, value: str, default: dict, weight: float = 1.0) -> None:
    """Resolve ASS font size; signed values adjust the current size by tenths.

    Apply transform weight before the nonpositive-size fallback, and before
    the next size tag, matching libass's ordered override evaluation.
    """
    value = value.strip()
    fallback = default.get('fs', DEFAULT_STATE['fs'])
    try:
        number = float(value) if value else 0.0
    except ValueError:
        return
    if value:
        current = state.get('fs', fallback)
        if value.startswith(('+', '-')):
            number = current * (1 + weight * number / 10)
        elif weight != 1:
            number = current * (1 - weight) + number * weight
    state['fs'] = fallback if number <= 0 else number


def apply_override(state: dict, name: str, value: str, styles: dict, default: dict,
                   continuation: OverrideContinuation, *,
                   event_tags: bool = True) -> OverrideContinuation:
    """Apply one ordered override and return its explicit parser successor.

    The caller owns the formatting dictionary. Default/style dictionaries
    are borrowed; continuation is immutable. This is the sole implementation
    of override semantics.
    """
    name = {"c": "1c", "fr": "frz"}.get(name, name)
    original_default = default
    default = styles.get(continuation.reset_style or "",default)
    if name == "r":
        # A style reset changes glyph paint/geometry, not line-wide placement,
        # clipping, alignment, wrapping or drawing mode (libass reset context).
        retained = {k:v for k,v in state.items() if k in
                    {"an","pos","org","clip","iclip","q","p","pbo"}}
        state.clear()
        state.update(styles.get(value,original_default) if value else original_default)
        state.update(retained)
        continuation = OverrideContinuation(
            value if value in styles else "",continuation.alignment_set)
    elif name == "fn":
        state[name] = value or default.get(name, "Arial")
    elif name == "fs":
        apply_font_size(state, value, default)
    elif name in {"1c", "2c", "3c", "4c", "alpha", "1a", "2a", "3a", "4a"}:
        # Some generated tags append one stray ')' after a complete hex value.
        # libass still reads that value; do not accept other trailing garbage.
        if re.fullmatch(r"&[Hh]?[0-9A-Fa-f]+&\s*\)", value):
            value = value[:-1].rstrip()
        try:
            raw = value.upper()
            raw = raw[2:] if raw.startswith('&H') else raw[1:] if raw.startswith('&') else raw
            v = int(raw.rstrip('&'), 16)
        except ValueError:
            return continuation
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
        if continuation.alignment_set:
            return continuation
        # Renderer integer parsing consumes even an invalid first alignment.
        match = re.match(r"[-+]?\d+",value)
        number = int(match[0]) if match else 0
        if name == "a" and 1 <= number <= 11:
            number = 5 if number in (4,8) else number
            number = {1:1,2:2,3:3,5:7,6:8,7:9,9:4,10:5,11:6}[number]
        elif name == "a" or not 1 <= number <= 9:
            number = default.get("an",2)
        continuation = OverrideContinuation(continuation.reset_style,True)
        state["an"] = number
    elif name not in {"t", "clip", "iclip", "move", "fad", "fade"}:
        try:
            number = float(value) if value else default.get(name, 0.0)
        except ValueError:
            return continuation
        state[name] = number
        if name in {"bord", "shad"}:
            for axis in "xy":
                state.pop(axis + name, None)
    return continuation


def evaluate_effective_state(text: str, default: dict | None = None,
                             styles: dict | None = None, *,
                             tokens: Iterable[tuple[str,str]] | None = None) -> OverrideEvaluation:
    """Evaluate a complete override stream without mixing history into formatting.

    Adjacent blocks and literal text do not restart reset-style tracking or
    the first-alignment latch. Readers that emit/evaluate more overrides must
    keep the returned continuation alongside the owned formatting buffer.
    Defaults and styles are borrowed; each evaluation owns a fresh buffer.
    A caller may supply the complete ordered tokens of this same text to reuse
    parsing. The stream is borrowed and formatting/history are still resolved
    here through the canonical override evaluator.
    """
    default = default or resolve_event_style(styles or {}, 'Default')
    state = default.copy()
    continuation = OverrideContinuation()
    token_blocks = ((tokenize_override(block) for block in OVERRIDE_RE.findall(text))
                    if tokens is None else (tokens,))
    for block in token_blocks:
        for name, value in block:
            continuation = apply_override(state,name,value,styles or {},default,continuation)
    return OverrideEvaluation(state,continuation)


def effective_state(text: str, default: dict | None = None, styles: dict | None = None) -> dict:
    """Return resolved formatting when no further parser continuation is needed."""
    return evaluate_effective_state(text,default,styles).formatting
