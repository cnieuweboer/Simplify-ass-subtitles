"""Shared measured clearance for caption reconstruction; callers own admission."""
from __future__ import annotations

from dataclasses import replace as dataclass_replace
import math
import re

from .ass_overrides import OVERRIDE_RE, apply_override, tokenize_override
from .caption_geometry import caption_bounds, get_pos, set_pos, text_layout_key
from .caption_rendering import CAPTION_PAINT_TAGS, render_tag
from .effect_validation import parse_effect_transform
from .event_model import Event
from .event_operations import event_evaluation, event_override_tokens, replace_event
from .font_metrics import FontMetrics


def _caption_implicit_anchor(event: Event) -> tuple[Event | None,float | None]:
    """Resolve a static ASS margin anchor for measured clearance only.

    Return the available width so callers reject unknown automatic wrapping.
    This never changes serialized placement or renderer collision policy.
    """
    if get_pos(event.text) is not None:return event,None
    if event.measurement.canvas is None or re.search(r'\\(?:move|t)\s*\(',event.text):return None,None
    width,height=event.measurement.canvas
    st=event.state;alignment=int(st.get('an',2))
    if alignment not in range(1,10):return None,None
    left,right,vertical=(float(value) or st.get(tag,0) for value,tag in
        ((event.margin_l,'marginl'),(event.margin_r,'marginr'),(event.margin_v,'marginv')))
    x=(left,(width+left-right)/2,width-right)[(alignment-1)%3]
    y=(height-vertical,height/2,vertical)[(alignment-1)//3]
    return replace_event(event,text=set_pos(event.text,(x,y))),width-left-right


def _glyph_replacement_row_is_clear(caption: Event, core: tuple[float,float],
                                    members: set[int], highest: int,
                                    parsed: dict[int,Event], metric: FontMetrics,
                                    poses: list[Event]) -> bool:
    """Prove intervening paint cannot obscure newly assembled readable content.

    The established fade-core handoff owns neighboring cue tails. This check
    covers independent content during the common readable core, including
    other styles and ordinary implicit-position captions.
    """
    # Layout and source advances have already been proved for every glyph.
    # Measure the common geometry with the union of its contour footprints;
    # intentional paint spans must not make that geometry unknown again.
    state = caption.state.copy()
    for k in ('bord','xbord','ybord','blur','be'):
        state[k] = max(e.state.get(k,e.state.get('bord',0) if k.endswith('bord') else 0) for e in poses)
    probe = dataclass_replace(caption,state=state,
        text='{'+render_tag('pos',get_pos(caption.text))+'}'+OVERRIDE_RE.sub('',caption.text))
    box = caption_bounds(probe,metric)
    if box is None:
        return False
    for other in parsed.values():
        if (other.kind != 'Dialogue' or other.source_index in members or
                other.start_s >= core[1] or other.end_s <= core[0]):
            continue
        if other.layer.lstrip('-').isdigit() and not int(caption.layer) <= int(other.layer) <= highest:
            continue
        evaluated = event_evaluation(other)
        peer = dataclass_replace(other,state=evaluated.formatting,continuation=evaluated.continuation)
        geometry = {k for k,_ in text_layout_key(peer)}|{'pos','move','clip','iclip','r','fr','a','fe',
            'bord','xbord','ybord','shad','xshad','yshad','blur','be','p'}
        bounded = {'fscx','fscy','bord','xbord','ybord','shad','xshad','yshad','blur','be'}
        samples = [peer.state];live = peer.state.copy();continuation = peer.continuation
        for tag,value in event_override_tokens(peer):
            if tag != 't':
                continue
            changes = tokenize_override(value[1:-1])
            if any(k in geometry-bounded for k,_ in changes):
                return False
            if not changes:
                continue
            transform = parse_effect_transform(value,peer.duration,bounded|set(CAPTION_PAINT_TAGS)|{'alpha','c'},allow_instant=True)
            if transform is None:
                return False
            for name,argument in changes:
                continuation = apply_override(live,name,argument,peer.styles,peer.defaults,continuation)
            samples.append(live.copy())
        # Fixed-anchor, fixed-font scale/stroke changes have a conservative
        # envelope from component maxima, even with overlapping transforms.
        # This keeps distant animated peers eligible without trusting just
        # their initial box or mistaking a growing peer for disjoint content.
        envelope = peer.state.copy()
        for k in bounded:
            values = [st.get(k,st.get(k[1:],0) if k in {'xbord','ybord','xshad','yshad'} else
                             100 if k in {'fscx','fscy'} else 0) for st in samples]
            if any(not math.isfinite(v) or k in {'fscx','fscy'} and v<=0 for v in values):
                return False
            envelope[k] = max(abs(v) for v in values)
        envelope['1a'] = 0  # Bound possible primary ink, including fade-ins.
        peer = dataclass_replace(peer,state=envelope)
        implicit = get_pos(peer.text) is None
        available = None
        if implicit:
            peer,available = _caption_implicit_anchor(peer)
            if peer is None:return False
        peer_box = caption_bounds(peer,metric)
        if implicit and peer_box is not None and available is not None and peer_box[2]-peer_box[0] > available:
            peer_box = None  # Automatic wrapping could change its footprint.
        if (peer_box is None or not (peer_box[2] < box[0] or box[2] < peer_box[0] or
                                     peer_box[3] < box[1] or box[3] < peer_box[1])):
            return False
    return True


def _caption_order_is_unchanged(family: list[Event], other: Event, order,
                            replacement_rank: tuple[int,int] | None) -> bool:
    """Compare foreground coverage against original planes, over the peer's life.

    A lower redundant plane is harmless when existing upper planes already cover
    the whole interval above independent ink. Do not mistake that backing plane
    for evidence that the replacement crosses visible content.
    """
    rank = order[other.source_index]
    ranks = [order[e.source_index] for e in family]
    if replacement_rank is None or rank is None or any(r is None for r in ranks):
        return False
    start = max(other.start_s,min(e.start_s for e in family))
    end = min(other.end_s,max(e.end_s for e in family))
    above = [(max(start,e.start_s),min(end,e.end_s))
             for e,r in zip(family,ranks) if r > rank and
             e.end_s > start and e.start_s < end]
    if replacement_rank < rank:
        return not above
    covered = start
    for left,right in sorted(above):
        if left > covered:
            return False
        covered = max(covered,right)
    return covered >= end
