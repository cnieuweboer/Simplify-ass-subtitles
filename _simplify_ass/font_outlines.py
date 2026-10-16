"""Exact-font contour matching, borrowing measurements from the font owner.

This module owns alphabet profiles and geometric fits. Caption reconstruction,
source-event evidence, timing, paint selection and reporting stay in the engine.
"""
from __future__ import annotations

import math
import statistics

from .font_metrics import FontMetrics


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




class FontOutlineMatcher:
    """Bounded exact-font contour decoding with reusable alphabet profiles.

    Borrow the shared font owner. Profile keys contain only exact face identity
    and the admitted alphabet, never event IDs, cue timing or source geometry.
    The CLI shares a matcher across its batch. Python callers may share one
    explicitly; otherwise conversion creates a local matcher.
    """
    def __init__(self, metrics: FontMetrics):
        self.metrics = metrics
        self._profiles = {}

    def decode_cubic_outline(self, face, path: tuple, fs: float, unit: float,
                             alphabet: set[str]) -> str | None:
        """Read only an unambiguous exact-font contour/advance sequence.

        Search printable ASCII plus literal characters present in the input,
        rather than loading every installed font's glyphs. Every glyph must
        share the first glyph's scale/baseline, and every gap must fit measured
        advances/spaces. Ambiguity or a bounded search overflow rejects the run.
        This is font geometry matching, with no language/word heuristics.
        """
        nominal = self.metrics.ass_em_scale(face)
        if nominal is None or not math.isfinite(fs) or fs <= 0:
            return None
        characters = tuple(sorted(char for char in set(map(chr,range(33,127)))|alphabet
                                  if not char.isspace() and ord(char) in face.cmap))
        key = (face.key,characters)
        if key not in self._profiles:
            profiles = []
            for char in characters:
                if self.metrics.fragmented_glyph(face,char) is True:
                    continue  # Grain/stamp fonts remain decorative effects.
                outline = self.metrics.cubic_outline(face,char)
                if outline is not None:
                    profiles.append((char,outline[0],outline[1],
                                     self.metrics.measure(face,char)*outline[1]/1024))
            self._profiles[key] = profiles
        profiles = self._profiles[key]
        if not profiles:
            return None
        em = profiles[0][2]
        nominal *= fs/em
        space = self.metrics.measure(face,' ')*em/1024
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
