"""Event-based exact-font row recovery, using borrowed events and measurements.

Fits and temporary event views are call-local. Callers retain source-family
proofs, rendering, timing, accepted-join counters and event edit application.
Measurement caches belong to the supplied FontMetrics; reports belong to callers,
including missing-face findings from refused fits or failed conversions.
"""
from __future__ import annotations

from dataclasses import replace as dataclass_replace
import math
import statistics

from .caption_geometry import get_pos
from .event_model import Event
from .font_metrics import FontMetrics
from .font_reporting import FontProcessingReport


def recover_font_row(
    metrics: FontMetrics, ordered, fragments, *, max_size_error: float | None=None,
    allow_internal_spaces: bool=False, font_report: FontProcessingReport | None=None,
    fit_scale: bool=False,
):
    if not metrics.available or len(ordered) < 4:
        return None
    import unicodedata
    if any(not t or t != t.strip() or any((c.isspace() and not
           (allow_internal_spaces and c == ' ')) or
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
    key = (family.casefold(), first.get('b',0), bool(first.get('i',0)))
    face = metrics.matching_face(family, key[1], key[2])
    if face is None:
        if font_report is not None:
            font_report.missing_families.add(family)
        return None
    cmap = face.cmap
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
        widths = [metrics.measure(face,t,kerning)*scale for t in fragments]
        space = metrics.measure(face,' ',kerning)*scale
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
        nominal = metrics.ass_em_scale(face)
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
        if abs(metrics.measure(face,text,kerning)*scale*factor-span) > max(1,.2*factor*space):
            return None
    except (OSError,ValueError,RuntimeError):
        return None
    center = (xs[0]-anchor*widths[0]*factor +
              xs[-1]+(1-anchor)*widths[-1]*factor)/2
    if fit_scale:
        nominal = metrics.ass_em_scale(face)
        if nominal is None:
            return None
        sx *= factor/nominal
    return text, center, sx, sy, ((alignment-1)//3)*3+2



def recover_tracked_font_row(
    metrics: FontMetrics, ordered, fragments, *, font_report: FontProcessingReport | None=None,
):
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
    fit = recover_font_row(metrics,[dataclass_replace(e,state={**e.state,'fsp':0})
                        for e in ordered],fragments,font_report=font_report)
    if fit is None:
        return None
    text,_,sx,sy,alignment = fit
    if any(any(e.state.get(k) != state.get(k)
               for k in ('fn','fs','b','i','fsp','an','fscx','fscy'))
           for e in ordered):
        return None
    face = metrics.matching_face(str(state.get('fn','')),state.get('b',0),
                              bool(state.get('i',0)))
    factor = metrics.ass_em_scale(face) if face is not None else None
    if factor is None:
        return None
    scale = state.get('fs',20)*sx/100/1024*factor
    kerning = bool(state.get('kerning',False))
    try:
        widths = [metrics.measure(face,c,kerning,ligatures=False)*scale for c in text]
        full = metrics.measure(face,text,kerning,ligatures=False)*scale
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



def fit_fullwidth_run(
    metrics: FontMetrics, ordered: list[Event], glyphs: list[str], *,
    font_report: FontProcessingReport | None=None,
):
    """Fit one unbroken row against its exact font's glyph advances."""
    if not metrics.available or len(ordered) < 2 or sum(map(len,glyphs)) < 3:
        return None
    state = ordered[0].state
    family = str(state.get("fn", "")).strip()
    key = (family.casefold(), state.get("b",0), bool(state.get("i",0)))
    face = metrics.matching_face(family, key[1], key[2])
    if face is None:
        if font_report is not None:
            font_report.missing_families.add(family)
        return None
    cmap = face.cmap
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
        widths = [metrics.measure(face,g,kerning)*scale for g in glyphs]
        offsets = [0]
        for fragment in glyphs:
            offsets.append(offsets[-1]+len(fragment))
        advances = [metrics.measure(face,text[:i],kerning)*scale for i in offsets]
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

