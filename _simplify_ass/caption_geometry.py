"""Explicit caption anchors and conservative bounds using caller-owned metrics."""
from __future__ import annotations

import math
import re

from .ass_overrides import DEFAULT_STATE, OVERRIDE_RE, NUMBER
from .event_model import Event
from .font_metrics import FontMetrics

NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


POS_RE = re.compile(r"\\pos\(\s*("+NUM+r")\s*,\s*("+NUM+r")\s*\)", re.I)


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


def caption_bounds(event, metric: FontMetrics | None, *, adjacency=False):
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
    if st.get('q', event.measurement.script_wrap_mode) != 2:
        visible = visible.replace(r'\n', ' ')
    lines = re.split(r'\\[Nn]', visible)
    face = metric.matching_face(str(st.get('fn', '')), st.get('b', 0),
                                bool(st.get('i', 0)))
    if face is None or any(ord(c) not in face.cmap for line in lines for c in line):
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
    ink = (metric.line_ink_metrics(face,lines,kerning=bool(st.get('kerning',False)))
           if not st.get('fsp',0) else None)
    if ink is not None:
        # ASS alignment uses the line box; supports surround actual visible ink.
        ascent = ink.ascent_ratio*fs*sy/100
        ink_boxes = []
        for i, box in enumerate(ink.boxes):
            if box is None:
                continue
            left, top, right, bottom = box
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


def text_height(e: Event) -> float:
    return max(e.unit, abs(e.state.get("fs",20) * e.state.get("fscy",100) / 100))


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


def rectangle_clip(e: Event):
    value = e.state.get("clip", "")
    if "iclip" in e.state or not re.fullmatch(r"\(\s*" + NUMBER + r"(?:\s*,\s*" + NUMBER + r"){3}\s*\)", value):
        return None
    coords = tuple(map(float, re.findall(NUMBER, value)))
    return coords if coords[0] < coords[2] and coords[1] < coords[3] else None
