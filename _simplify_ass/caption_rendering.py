"""Source-paint resolution and reconstructed caption rendering.

Callers retain source-family, geometry, timing and compositing proofs.
"""
from __future__ import annotations
import math
import re
from dataclasses import dataclass
from typing import Iterable
from .ass_overrides import (
    DEFAULT_STATE, evaluate_effective_state, apply_override, effective_state,
    OVERRIDE_RE, tokenize_override,
)
from .event_model import DocumentMeasurementContext, Event

# Reconstructed source contours keep thinner/axis-specific widths, but cap each
# axis in ASS script units. Ordinary retained events are not subject to this cap.
# Coverage uses the emitted state; source grouping still uses original extents.
MAX_PROVED_CAPTION_BORDER = 2.


CAPTION_PAINT_TAGS = ('1c','2c','3c','4c','1a','2a','3a','4a',
                      'bord','xbord','ybord','shad','xshad','yshad','blur','be')

@dataclass(frozen=True)
class SourceCaptionPaint:
    """Proved representative subtitle-only paint, borrowed by caption rendering."""
    fill: str
    outline: str
    outline_alpha: int
    border: tuple[float,float] = (2.,2.)


def render_tag(name: str, value) -> str:
    if name in {"1c", "2c", "3c", "4c"}:
        return f"\\{name}&H{value}&"
    if name in {"1a", "2a", "3a", "4a"}:
        return f"\\{name}&H{round(value):02X}&"
    if isinstance(value, tuple):
        return "\\" + name + "(" + ",".join(f"{x:g}" for x in value) + ")"
    return "\\" + name + (f"{value:g}" if isinstance(value, (float, int)) else str(value))


def _source_caption_paint(state: dict, sources: Iterable[dict]) -> SourceCaptionPaint | None:
    """Resolve complete producer-owned contour evidence, never guess missing paint.

    Producers supply their whole compatible paint family after geometry/ownership
    proofs. One visible authored contour is authoritative even at low contrast.
    Borderless evidence requires visible foreground-only sources, with no shadow
    support. Hidden, clipped, conflicting or unsupported paint remains uncertain.
    """
    selected = {**DEFAULT_STATE,**state}
    fill = str(selected.get('1c','')).upper()
    if (selected.get('1a',0) >= 255 or any(k in selected for k in ('clip','iclip')) or
            not re.fullmatch(r'[0-9A-F]{6}',fill)):
        return None
    sources = [{**DEFAULT_STATE,**source} for source in sources]
    if not sources:
        return None
    contours = set()
    for source in sources:
        if (source.get('borderstyle',1) != 1 or source.get('p',0) or
                any(k in source for k in ('clip','iclip')) or
                any(source.get(k) != selected.get(k) for k in
                    ('fn','fs','b','i','frz','frx','fry','fax','fay'))):
            return None
        widths = tuple(source.get(k,source.get('bord',0)) for k in ('xbord','ybord'))
        alpha = source.get('3a',0)
        if (not all(isinstance(w,(int,float)) and math.isfinite(w) and w >= 0 for w in widths) or
                not isinstance(alpha,(int,float)) or not math.isfinite(alpha) or not 0<=alpha<=255):
            return None
        if max(widths)>0 and alpha<255:
            color = str(source.get('3c','')).upper()
            if not re.fullmatch(r'[0-9A-F]{6}',color):
                return None
            # The renderer already freezes fill opacity to opaque. A coupled
            # fill/outline fade must not make held and fading phases choose
            # different contours. Independent contour opacity remains authored.
            fill_alpha = source.get('1a',0)
            if 0 <= fill_alpha < 255 and fill_alpha == alpha:
                alpha = 0
            contours.add((color,round(alpha),widths))
    if len(contours)==1:
        color,alpha,widths = next(iter(contours))
        return SourceCaptionPaint(fill,color,alpha,tuple(min(MAX_PROVED_CAPTION_BORDER,w) for w in widths))
    if contours or any(source.get('1a',0) >= 255 or
                       str(source.get('1c','')).upper() != fill or
                       any(source.get(k,source.get('shad',0)) for k in ('xshad','yshad'))
                       for source in sources):
        return None
    return SourceCaptionPaint(fill,'000000',0,(0.,0.))


def render_simplified_caption(state: dict, text: str,
                       outline_states: Iterable[dict] | None = None, *,
                       measurement: DocumentMeasurementContext = DocumentMeasurementContext(),
                       source_paint: SourceCaptionPaint | None = None,
                       **layout) -> str:
    """Preserve proved source paint; contrast repair is for uncertain reconstruction.

    Unclipped visible primary paint supplies the fill; transparent or masked
    textures cannot. Producer-owned source contours preserve authored color, alpha and width.
    Uncertain contours use the neutral contrast fallback; selected state alone
    does not prove that discarded support was unnecessary.
    Explicit source paint bypasses the fallback without changing layout.
    Preserve explicit wrapping in the selected layout. Document wrapping stays
    in measurement context; absence of q does not create an authored override.
    """
    state = {**state,**layout}
    transferred_shadow = False
    canvas, pos = measurement.canvas,state.get("pos")
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
            transferred_shadow = True
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
    # Proved source paint supplies settled RGBA, including subdued contour
    # strength. Ordinary/ambiguous captions keep the neutral fallback.
    outline_alpha = 0
    border = (2.,2.)
    if source_paint is not None and not transferred_shadow:
        fill,outline = source_paint.fill,source_paint.outline
        outline_alpha = min(255,max(0,int(source_paint.outline_alpha)))
        border = source_paint.border
    state = {**DEFAULT_STATE, **state,
             "1c":fill, "3c":outline, "1a":0,
             "3a":outline_alpha,
             "bord":max(border), "shad":0, "blur":0, "be":0}
    state.pop('xbord',None);state.pop('ybord',None)
    if border[0] != border[1]:
        state.update(xbord=border[0],ybord=border[1])
    keys = ("an","pos","org","q","fn","fs","fscx","fscy","fsp","b","i",
            "u","s","frz","frx","fry","fax","fay",
            "1c","3c","1a","3a","bord","xbord","ybord","shad","blur","be")
    return "{"+"".join(render_tag(k,state[k]) for k in keys if k in state)+"}"+text


def render_caption_spans(header: str, fragments: list[str], text: str,
                         paints: list[dict], span_tags: tuple[str,...],
                         chosen: Event, *, exact: bool = False) -> str | None:
    """Attach selected span formatting to literal recovered characters.

    Callers choose the paint policy; this helper only maps fragments and emits
    state changes. Spaces belong to the recovered text, never to a word guess.
    Replay emitted tags so base border/shadow changes reset their axes exactly
    as the renderer does before comparing the next tag or fragment.
    Exact correspondence retains literal whitespace at its authored offsets;
    recovered glyph rows keep their existing whitespace-insensitive mapping.
    """
    norm = lambda value: ''.join(value.split())
    if len(fragments) != len(paints) or (text != ''.join(fragments) if exact else
                                       norm(text) != norm(''.join(fragments))):
        return None
    def value(state,tag):
        return state.get(tag,state.get(tag[1:],0) if tag in
                         {'xbord','ybord','xshad','yshad'} else DEFAULT_STATE.get(tag,0))
    evaluation = evaluate_effective_state(header,chosen.defaults,chosen.styles)
    live,continuation = evaluation.formatting,evaluation.continuation
    cursor,segments = 0,[]
    for fragment,paint in zip(fragments,paints):
        begin,remaining = cursor,len(norm(fragment))
        if exact:
            cursor+=len(fragment)
        else:
            while remaining and cursor < len(text):
                remaining -= not text[cursor].isspace()
                cursor += 1
        tags = ''
        for tag in span_tags:
            target = value(paint,tag)
            if value(live,tag) != target:
                rendered = render_tag(tag,target)
                tags += rendered
                continuation = apply_override(live,tag,rendered[len(tag)+1:],
                                              chosen.styles,chosen.defaults,continuation)
        segments.append(('{' + tags + '}' if tags else '')+text[begin:cursor])
    return header+''.join(segments)+text[cursor:]


def render_merged_caption(ordered: list[Event], fragments: list[str], text: str,
                          *, animated: bool, an: int, pos: tuple[float,float],
                          fscx: float, fscy: float, fsp: float | None = None,
                          preserve_paint: bool = False) -> str | None:
    """Render a validated row using its recovered text and placement.

    Animated rows use simplified fragment paint and decorations. Static rows
    use shared formatting, or exact per-fragment paint with preserve_paint.
    Return None if span formatting cannot map to the text.
    Spacing recovery, row eligibility and event updates belong to the caller.
    """
    alignment = an
    x,y = pos
    sx,sy = fscx,fscy
    chosen = ordered[0]
    paints = None
    span_tags = ()
    if animated:
        # Normalize geometry/effects, retaining each fragment's formatting.
        # Visibility changes also mark stable gradient glyphs as animated;
        # merging them must not spread the first glyph's fill over the row.
        body = render_simplified_caption(chosen.state,text,
                                  outline_states=[e.state for e in ordered],
                                  source_paint=_source_caption_paint(chosen.state,[e.state for e in ordered]),
                                  an=alignment,pos=(x,y),fscx=sx,fscy=sy,measurement=chosen.measurement)
        header = body[:body.index('}')+1]
        paints = [effective_state(render_simplified_caption(e.state,fragment,measurement=e.measurement,
                                          source_paint=_source_caption_paint(e.state,[e.state])),e.defaults,e.styles)
                  for e,fragment in zip(ordered,fragments)]
        span_tags = ('b','i','u','s','1c','3c','3a','bord','xbord','ybord')
        formatting = [tuple(paint.get(k,paint.get('bord',0) if k in {'xbord','ybord'} else DEFAULT_STATE.get(k))
                            for k in span_tags) for paint in paints]
        if len(set(formatting)) == 1:
            paints = None
    else:
        # Static callers prove a shared layout. Reuse the first fragment's
        # overrides for the header, and retain paint spans when requested.
        tags = "".join(OVERRIDE_RE.findall(chosen.text))
        tags = "".join("\\"+name+value for name,value in tokenize_override(tags)
                       if name not in {"pos","an","a","fscx","fscy"})
        header = "{"+tags+f"\\an{alignment}\\pos({x:g},{y:g})\\fscx{sx:g}\\fscy{sy:g}"+"}"
        if preserve_paint:
            paints = [e.state for e in ordered]
            span_tags = CAPTION_PAINT_TAGS
    if fsp is not None:
        # This is one proven positioned row, including when it is wider than
        # the canvas. Disable automatic wrapping and replace prior tracking.
        tags = ''.join('\\'+tag+value for tag,value in tokenize_override(header[1:-1])
                       if tag not in {'fsp','q'})
        header = '{'+tags+render_tag('fsp',fsp)+r'\q2}'
    if paints is not None:
        return render_caption_spans(header,fragments,text,paints,span_tags,chosen)
    return header+text
