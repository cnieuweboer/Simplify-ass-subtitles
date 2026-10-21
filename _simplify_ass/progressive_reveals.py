"""Complete progressive text-reveal proof, paint selection and reconstruction."""
from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import math
import re

from .ass_overrides import OverrideContinuation
from .event_model import Event
from .event_operations import replace_event, state_key
from .static_objects import geometry_key, static_object_key
from .caption_geometry import get_pos, inline_layout_key, text_height, rectangle_clip
from .caption_rendering import _source_caption_paint, render_simplified_caption, render_tag
from .subtitle_document import format_time
from .static_selection import unrotated_text_state
from .text_visibility import TextVisibilityResult


@dataclass(frozen=True)
class ProgressiveRevealPrefix:
    """Literal-span proof with its visible prefix, common layout and foreground paint."""
    literal: str
    prefix: str
    layout: tuple
    foreground: dict


@dataclass(frozen=True)
class ProgressiveRevealBand:
    """The existing text height and complete vertical extent of a thin strip group."""
    height: float
    top: float
    bottom: float


@dataclass(frozen=True)
class ProgressiveRevealCaption:
    """Selected held foreground source and its rendered complete caption body."""
    event: Event
    body: str


def _eligible_progressive_reveal_families(events: list[Event], visible_map: dict[int,str]) -> set:
    """Prefilter visible-text/style families containing an inline alpha reveal."""
    reveal_families = {(e.style,visible_map.get(e.source_index,'')) for e in events
                       if e.kind == 'Dialogue' and inline_layout_key(e) and
                       re.search(r'\\(?:alpha|[134]a)(?=[^A-Za-z]|$)',e.text,re.I)}
    return reveal_families


def _parse_progressive_reveal_prefix(e: Event, obj: tuple, paint: set, visible_map: dict[int,str]) -> ProgressiveRevealPrefix | None:
    """Prove consistent literal-span geometry and a visible prefix followed by hidden text."""
    literal, prefix, hidden, layout, foreground, valid = '', '', False, None, None, True
    for signature,drawing,payload in obj[-1]:
        state = dict(signature.formatting)
        if 'clip' in state:
            if state['clip'] != geometry_key(e.state.get('clip','')):
                valid = False; break
            state['clip'] = e.state['clip']
        sample = dataclass_replace(e,state=state,continuation=signature.continuation)
        geometry = state_key(sample,paint | {'pos','clip','iclip'})
        if (drawing or not unrotated_text_state(state) or
                any(k in state for k in ('iclip','org')) or
                layout is not None and geometry != layout or
                state.get('pos') != get_pos(e.text)):
            valid = False; break
        layout = geometry
        literal += payload
        invisible = all(state.get(k,0) == 255 for k in ('1a','3a','4a'))
        if invisible:
            hidden = True
        elif hidden or state.get('1a',0) >= 128:
            valid = False; break
        else:
            if foreground is not None and state_key(sample,{'clip'}) != state_key(
                    dataclass_replace(e,state=foreground,continuation=OverrideContinuation()),{'clip'}):
                valid = False; break
            foreground = state
            prefix += payload
    if not valid or not prefix or literal != visible_map[e.source_index]:
        return None
    return ProgressiveRevealPrefix(literal,prefix,layout,foreground)


def _profile_progressive_reveal_event(e: Event, visible_map: dict[int,str], reveal_families: set, paint: set) -> tuple | None:
    """Admit positioned single-line sources and validate their foreground clip and sizing."""
    if (e.kind != 'Dialogue' or not visible_map.get(e.source_index) or
            (e.style,visible_map[e.source_index]) not in reveal_families or
            get_pos(e.text) is None or any(t in e.text for t in (r'\N',r'\n',r'\h'))):
        return None
    obj = static_object_key(e,e.styles)
    if obj is None:
        return None
    parsed = _parse_progressive_reveal_prefix(e,obj,paint,visible_map)
    if parsed is None:
        return None
    literal,prefix,layout,foreground = (parsed.literal,parsed.prefix,parsed.layout,parsed.foreground)
    sample = dataclass_replace(e,state=foreground,continuation=OverrideContinuation())
    rect = rectangle_clip(sample) if 'clip' in foreground else None
    if ('clip' in foreground and rect is None or
            any(not math.isfinite(v) for v in get_pos(e.text)) or
            any(not math.isfinite(foreground.get(k,0)) or foreground.get(k,0) <= 0
                for k in ('fs','fscx','fscy'))):
        return None
    key = (e.style,e.layer,e.margin_l,e.margin_r,e.margin_v,literal,layout)
    return key,(e,prefix,foreground,rect)


def _index_progressive_reveal_families(events: list[Event], visible_map: dict[int,str], reveal_families: set) -> dict:
    """Group validated prefix/foreground fragments by the existing caption geometry key."""
    paint = {'alpha','1a','2a','3a','4a','c','1c','2c','3c','4c',
             'bord','xbord','ybord','shad','xshad','yshad','blur','be'}
    families = {}
    for e in events:
        profile = _profile_progressive_reveal_event(e,visible_map,reveal_families,paint)
        if profile is not None:
            key,item = profile
            families.setdefault(key,[]).append(item)
    return families


def _build_progressive_reveal_chains(family: list) -> list:
    """Separate distant/repeated captions and build locally increasing prefix chains."""
    # Separate distant signs and repeated captions. Candidate chains may
    # have small authored gaps, but replacements retain every such gap.
    chains = []
    for item in sorted(family,key=lambda p:(p[0].start_s,len(p[1]),p[0].source_index)):
        e,prefix,state,rect = item
        pos = get_pos(e.text)
        found = None
        for chain in reversed(chains):
            anchor = chain[0][0]
            height = min(text_height(anchor),text_height(e))
            start = chain[-1][0].start_s
            if (e.start_s <= max(p[0].end_s for p in chain)+.08+1e-6 and
                    abs(pos[0]-get_pos(anchor.text)[0]) <= .18*height and
                    abs(pos[1]-get_pos(anchor.text)[1]) <= .01*height and
                    (e.start_s == start or len(prefix) >= max(len(p[1]) for p in chain))):
                found = chain; break
        if found is None:
            chains.append([item])
        else:
            found.append(item)
    return chains


def _progressive_reveal_finishing_holds(chain: list, literal: str) -> list:
    """Require two incomplete prefixes and an unclipped complete copy finishing the reveal."""
    incomplete_prefixes = {prefix for e,prefix,state,rect in chain if prefix != literal}
    holds = [(e,state) for e,prefix,state,rect in chain if
             prefix == literal and rect is None and state.get('1a',0) < 128]
    if len(incomplete_prefixes) < 2 or not holds:
        return []
    # A complete copy must finish the reveal, rather than be an
    # unrelated simultaneous label behind a retracting prefix.
    last_prefix_start = max(e.start_s for e,prefix,state,rect in chain if prefix != literal)
    holds = [(e,state) for e,state in holds if e.start_s >= last_prefix_start]
    if not holds:
        return []
    return holds


def _progressive_reveal_strip_band(peers: list) -> ProgressiveRevealBand | None:
    """Prove a common horizontal extent and thin strips before checking temporal coverage."""
    rectangles = sorted(set(rect for e,rect in peers),key=lambda r:r[1])
    height = min(text_height(e) for e,rect in peers)
    # The union supplies the band's extent. A temporal hole in
    # any strip must not disappear merely because its neighbors
    # were coalesced across different start/end boundaries.
    if (len(rectangles) < 3 or
            len({(r[0],r[2]) for r in rectangles}) != 1 or
            any(r[3]-r[1] > .08*height for r in rectangles)):
        return None
    top,bottom = rectangles[0][1],max(r[3] for r in rectangles)
    return ProgressiveRevealBand(height,top,bottom)


def _progressive_reveal_strips_cover_band(peers: list) -> bool:
    """Aggregate simultaneous tile changes and prove each nonempty interval covers the whole band."""
    extent = _progressive_reveal_strip_band(peers)
    if extent is None:
        return False
    height,top,bottom = extent.height,extent.top,extent.bottom
    changes = {}
    for e,rect in peers:
        changes.setdefault(e.start_s,[]).append((rect,1))
        changes.setdefault(e.end_s,[]).append((rect,-1))
    active = {}
    for time,updates in sorted(changes.items()):
        # Aggregate simultaneous ends/starts before checking the
        # next half-open interval; a touching tile has no gap.
        for rect,delta in updates:
            active[rect] = active.get(rect,0)+delta
            if not active[rect]:
                del active[rect]
        if not active:
            continue
        band = sorted(active,key=lambda r:r[1])
        if (len(band) < 3 or bottom-top < .3*height or
                abs(band[0][1]-top) > .001 or
                abs(band[-1][3]-bottom) > .001 or
                any(abs(a[3]-b[1]) > .001 for a,b in zip(band,band[1:]))):
            return False
    return True


def _progressive_reveal_strip_coverage(chain: list) -> bool:
    """Group strips by prefix/paint and reject any group without complete coverage."""
    tiles = {}
    for e,prefix,state,rect in chain:
        if rect is not None:
            tiles.setdefault((prefix,state_key(
                dataclass_replace(e,state=state,continuation=OverrideContinuation()),{'pos','clip'})),[]).append((e,rect))
    for peers in tiles.values():
        if not _progressive_reveal_strips_cover_band(peers):
            return False
    return True


def _select_progressive_reveal_caption(holds: list, chain: list, literal: str) -> ProgressiveRevealCaption:
    """Select foreground paint by opacity/duration/source order and retain its fill transparency."""
    chosen,state = max(holds,key=lambda p:(-p[1].get('1a',0),
                                           p[0].duration,-p[0].source_index))
    source_paint = _source_caption_paint(state,[p[1] for p in holds])
    body = render_simplified_caption(state,literal,outline_states=[p[2] for p in chain],measurement=chosen.measurement,
                                     source_paint=source_paint)
    if state.get('1a',0):
        # The shared caption renderer normalizes opacity for effects.
        # This proof also accepts an already simplified translucent
        # foreground: keep its actual fill transparency.
        end_header = body.index('}')
        tags = render_tag('1a',state['1a'])
        if source_paint is not None and max(source_paint.border)>0 and state.get('3a',0)==state['1a']:
            # This route preserves fill transparency rather than freezing it.
            # Restore the coupled source contour opacity as well.
            tags += render_tag('3a',state['3a'])
        body = body[:end_header]+tags+body[end_header:]
    return ProgressiveRevealCaption(chosen,body)


def _progressive_reveal_intervals(chain: list) -> list[list[float]]:
    """Coalesce only overlapping/touching lifetimes so real authored gaps survive."""
    intervals = []
    for e,_,_,_ in sorted(chain,key=lambda p:(p[0].start_s,p[0].end_s)):
        if intervals and e.start_s <= intervals[-1][1]+1e-6:
            intervals[-1][1] = max(intervals[-1][1],e.end_s)
        else:
            intervals.append([e.start_s,e.end_s])
    return intervals


def _record_progressive_reveal_replacements(chain: list, literal: str, caption: ProgressiveRevealCaption, visibility_updates: dict[int,str], removed: set[int], replacements: dict[int,Event]) -> None:
    """Record captions and local visibility deltas for each covered interval."""
    chosen,body = caption.event,caption.body
    intervals = _progressive_reveal_intervals(chain)
    for start,end in intervals:
        members = [e for e,_,_,_ in chain if e.start_s < end and e.end_s > start]
        index = min(e.source_index for e in members)
        replacements[index] = replace_event(chosen,start=format_time(start),start_s=start,
            end=format_time(end),end_s=end,text=body,source_index=index,effect='')
        visibility_updates[index] = literal
        removed.update(e.source_index for e in members)


def collapse_progressive_text_reveals(events: list[Event],
                                      visible_map: dict[int,str]) -> TextVisibilityResult:
    """Freeze a proved prefix reveal at its complete foreground caption.

    Literal-span state distinguishes a visible prefix from its hidden suffix;
    the event's final state may describe only that suffix. Require increasing
    prefixes, a final unclipped visible copy, and matching text geometry. Thin
    clipped glitch strips must cover their complete band at every boundary.
    Preserve actual gaps and reject resets, changing layout and partial tiles.
    Borrow visibility during matching and return updates for accepted captions,
    including reveals whose preserved gaps leave the event count unchanged.
    """
    reveal_families = _eligible_progressive_reveal_families(events,visible_map)
    if not reveal_families:
        return TextVisibilityResult(events,0,{})
    families = _index_progressive_reveal_families(events,visible_map,reveal_families)
    removed,replacements = set(), {}
    visibility_updates: dict[int,str] = {}
    for key,family in families.items():
        literal = key[-2]
        for chain in _build_progressive_reveal_chains(family):
            holds = _progressive_reveal_finishing_holds(chain,literal)
            if not holds or not _progressive_reveal_strip_coverage(chain):
                continue
            caption = _select_progressive_reveal_caption(holds,chain,literal)
            _record_progressive_reveal_replacements(
                chain,literal,caption,visibility_updates,removed,replacements)
    output = [replacements.get(e.source_index,e) for e in events
              if e.source_index not in removed or e.source_index in replacements]
    return TextVisibilityResult(output,len(events)-len(output),visibility_updates)
