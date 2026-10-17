"""Exact-font fragment fitting and authored glyph placement.

These functions borrow formatting and coordinates. Measurement resources and
caches belong to FontMetrics; event recovery and diagnostics stay in the engine.
"""
from __future__ import annotations

import unicodedata

from .font_metrics import FontMetrics


def fit_fragment_anchor(
    metrics: FontMetrics, state: dict, xs: list[float], fragments: list[str], text: str,
    unit: float, *, allow_tracking: bool=False, separate_glyphs: bool=False,
    exact_size: bool=False, max_size_error: float | None=None,
) -> float | None:
    """Fit an authored fragment anchor to exact-font glyph positions.

    Calibrate the font's common size convention from the recorded run;
    leading and trailing spaces shift its anchor without inventing gaps.
    Tracking is opt-in for matching known glyph text, not spacing recovery.
    Separately rendered glyphs use their own advances; contextual shaping
    of the assembled word must not change the measured letter-run span.
    Exact-size proofs additionally use the font's ASS line metrics and
    verify every recorded glyph position, without fitting another scale.
    """
    if (not metrics.available or not fragments or len(xs) != len(fragments) or
            any(not word or any(c.isspace() or unicodedata.combining(c) or
                unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word)
                for word in fragments) or ''.join(fragments) != text.strip() or
            abs(state.get('fsp',0)) > .001 and not allow_tracking):
        return None
    face = metrics.matching_face(str(state.get('fn','')),state.get('b',0),bool(state.get('i',0)))
    if face is None or any(ord(c) not in face.cmap for c in text):
        return None
    kerning = bool(state.get('kerning',False))
    scale = state.get('fs',20)*state.get('fscx',100)/100/1024
    try:
        widths = [metrics.measure(face,word,kerning)*scale for word in fragments]
        if separate_glyphs:
            if text != text.strip() or any(len(word) != 1 for word in fragments):
                return None
            width = sum(widths)
        else:
            width = metrics.measure(face,text.strip(),kerning)*scale
        leading = metrics.measure(face,text[:len(text)-len(text.lstrip())],kerning)*scale
        trailing = metrics.measure(face,text[len(text.rstrip()):],kerning)*scale
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
        nominal = metrics.ass_em_scale(face)
        if nominal is None or abs(factor-nominal) > max_size_error*nominal:
            return None
    if exact_size:
        factor = metrics.ass_em_scale(face)
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


def authored_glyph_positions(
    metrics: FontMetrics, state: dict, text: str, anchor_x: float, unit: float,
) -> list[tuple[str, float]] | None:
    """Measure a known caption's separate glyph anchors, including spaces.

    Use its held size and ASS font metrics rather than fitting a new size.
    Reject contextual shaping that changes the individual glyph advances.
    """
    if (not metrics.available or
            any(unicodedata.combining(c) or
                unicodedata.bidirectional(c) in {'R','AL','AN'} for c in text) or
            any(c in text for c in ('\\','\n','\r','\t'))):
        return None
    face = metrics.matching_face(str(state.get('fn','')),state.get('b',0),bool(state.get('i',0)))
    if face is None or any(ord(c) not in face.cmap for c in text):
        return None
    factor = metrics.ass_em_scale(face)
    alignment = int(state.get('an',5))
    if factor is None or alignment not in range(1,10):
        return None
    scale = state.get('fs',20)*state.get('fscx',100)/100/1024*factor
    tracking = state.get('fsp',0)*state.get('fscx',100)/100
    try:
        kerning = bool(state.get('kerning',False))
        widths = [metrics.measure(face,c,kerning)*scale for c in text]
        width = metrics.measure(face,text,kerning)*scale
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


def matches_authored_glyph_positions(
    metrics: FontMetrics, state: dict, xs: list[float], text: str, anchor_x: float, unit: float,
) -> bool:
    expected = authored_glyph_positions(metrics,state,text,anchor_x,unit)
    return (expected is not None and len(xs) == len(expected) and
            all(abs(x-model) <= 1.5*unit for x,(_,model) in zip(xs,expected)))
