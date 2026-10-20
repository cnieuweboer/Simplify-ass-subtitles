"""Settled caption paint sampling after caller-owned compositing proofs.

Producers retain source-family, geometry, timing and ownership decisions.
Font caches stay with the borrowed metrics owner; raster buffers are call-local.
"""
from __future__ import annotations

from io import BytesIO
import math
import unicodedata

from .ass_overrides import apply_override, OVERRIDE_RE
from .event_model import Event
from .font_metrics import FontMetrics
from .effect_validation import parse_effect_transform
from .event_operations import event_override_tokens
from .caption_rendering import SourceCaptionPaint


def _settled_caption_paint_samples(foreground: Event, copies: list[Event], metric: FontMetrics) -> tuple | None:
    """Estimate settled subtitle-only RGBA in the ink core and a two-unit contour.

    The small exact-face mask is an appearance estimate, not an ownership proof.
    No video/background color is baked into it. Blur uses a Gaussian footprint;
    this intentionally approximates libass rather than introducing a renderer
    dependency. Unsupported shaping/layout falls back to the ordinary stack.
    """
    from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageChops
    text = OVERRIDE_RE.sub('',foreground.text)
    state = foreground.state
    if (any(unicodedata.combining(c) or unicodedata.bidirectional(c) in {'R','AL','AN'} for c in text) or
            state.get('fsp',0) or state.get('kerning',False) or state.get('u',0) or state.get('s',0)):
        return None
    face = metric.matching_face(str(state.get('fn','')),state.get('b',0),bool(state.get('i',0)))
    scale = metric.ass_em_scale(face) if face is not None else None
    if scale is None:
        return None
    settled = []
    for e in copies:
        final = e.state.copy()
        continuation = e.continuation
        for tag,value in event_override_tokens(e):
            if tag != 't':
                continue
            transform = parse_effect_transform(value,e.duration,
                {'c','1c','alpha','1a','2a','3a','4a','blur','be','fscx','fscy'},allow_instant=True)
            if transform is None:
                return None
            for name,argument in transform[2]:
                continuation = apply_override(final,name,argument,e.styles,e.defaults,continuation)
        if (any(final.get(k,100) != state.get(k,100) for k in ('fscx','fscy')) or
                final.get('be',0) or final.get('bord',0) or
                any(final.get(k,0) for k in ('xbord','ybord','shad','xshad','yshad'))):
            return None
        settled.append((e,final))
    # Supersampling keeps thin strokes and the small contour band measurable.
    factor = 2
    try:
        data,index = metric.face_data(face)
        size = round(state.get('fs',20)*scale*factor)
        if not 1 <= size <= 512:
            return None
        font = ImageFont.truetype(BytesIO(data),size,index=index,layout_engine=ImageFont.Layout.BASIC)
        box = font.getbbox(text)
        blur = max(max(0,p.get('blur',0)) for e,p in settled)
        if not math.isfinite(blur) or blur > 64:
            return None
        padding = math.ceil(1.5*blur*factor)+6
        width,height = box[2]-box[0]+2*padding,box[3]-box[1]+2*padding
        if not 0 < width*height <= 2_000_000:
            return None
        ink = Image.new('L',(width,height))
        ImageDraw.Draw(ink).text((padding-box[0],padding-box[1]),text,font=font,fill=255)
        resized = (max(1,round(width*state.get('fscx',100)/100)),
                   max(1,round(height*state.get('fscy',100)/100)))
        if resized[0]*resized[1] > 2_000_000:
            return None
        ink = ink.resize(resized)
        core = ink.filter(ImageFilter.MinFilter(3))
        ring = ImageChops.subtract(ink.filter(ImageFilter.MaxFilter(2*2*factor+1)),ink)
        regions = [list(core.getdata()),list(ring.getdata())]
        accum = [[0.,0.,0.,0.,0.] for _ in regions]
        planes = [(list(ink.filter(ImageFilter.GaussianBlur(p.get('blur',0)*factor/2)).getdata()),
                   (255-p.get('1a',0))/255,[int(p['1c'][i:i+2],16)/255 for i in (4,2,0)])
                  for e,p in sorted(settled,key=lambda pair:(int(pair[0].layer),pair[0].source_index),reverse=True)]
        for i in range(len(regions[0])):
            weights = [1. if regions[0][i] >= 250 else 0.,regions[1][i]/255]
            if not any(weights):
                continue
            remaining,rgb = 1.,[0.,0.,0.]
            for mask,opacity,color in planes:
                alpha = mask[i]/255*opacity
                for ch in range(3):
                    rgb[ch] += remaining*alpha*color[ch]
                remaining *= 1-alpha
            for weight,total in zip(weights,accum):
                total[0] += weight
                total[1] += weight*(1-remaining)
                for ch in range(3):
                    total[ch+2] += weight*rgb[ch]
        return tuple(tuple(row) for row in accum) if all(row[1] > 0 for row in accum) else None
    except (OSError,ValueError,RuntimeError):
        return None


def _pool_source_caption_paint(samples: list[tuple]) -> SourceCaptionPaint:
    """Pool complete-row mask contributions so glyph thickness cannot split paint."""
    totals = [[sum(p[region][ch] for p in samples) for ch in range(5)] for region in range(2)]
    def color(total):
        return ''.join(f'{min(255,max(0,round(total[i]/total[1]*255))):02X}' for i in (4,3,2))
    alpha = min(254,max(0,round(255*(1-totals[1][1]/totals[1][0]))))
    return SourceCaptionPaint(color(totals[0]),color(totals[1]),alpha)
