"""Complete tiled entrance/held-caption/exit proof and reconstruction.

Inputs remain borrowed; source profiles, coverage and proposal buffers are local.
Source-fragment orchestration, shared geometry and paint policy keep their owners.
"""
from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import math
import re

from .ass_overrides import apply_override, evaluate_effective_state, OVERRIDE_RE, DEFAULT_STATE
from .event_model import Event
from .event_operations import event_override_tokens, literal_font_spans, replace_event
from .effect_validation import opaque_text_effect_state, parse_effect_move, parse_effect_transform
from .caption_geometry import get_pos, rectangle_clip, text_height, text_layout_key
from .caption_rendering import _source_caption_paint, render_simplified_caption
from .subtitle_document import format_time
from .text_freezing import simplify_text


@dataclass(frozen=True)
class SlicedTextIndex:
    """Temporary indexes of held captions, clipped strips and fading size pulses."""
    holds: dict
    tiles: dict
    pulses: dict


@dataclass(frozen=True)
class SlicedTextEvent:
    """One resolved source event and its original movement, transform and layout evidence."""
    event: Event
    moves: list[str]
    transforms: list[str]
    pos: tuple | None
    key: tuple


def _eligible_sliced_text_families(events: list[Event]) -> set[tuple[str,str]]:
    """Reject impossible strip families using raw text and exact held-phase boundaries."""
    candidates = [e for e in events if e.kind == 'Dialogue' and
                re.search(r'\\move\s*\(',e.text,re.I) and
                re.search(r'\\clip\s*\(',e.text,re.I) and
                re.search(r'\\(?:alpha|1a|3a)(?=[^A-Za-z]|$)',e.text,re.I) and
                re.search(r'\\t\s*\(',e.text,re.I)]
    if not candidates:
        return set()
    # A source family may contain tens of thousands of unrelated effects.
    # Both strip phases must touch a literal held copy; reject impossible
    # families using raw text/times before resolving their override states.
    families = {(e.style,e.name) for e in candidates}
    beginnings = {(e.style,e.name,e.start,OVERRIDE_RE.sub('',e.text)) for e in candidates}
    endings = {(e.style,e.name,e.end,OVERRIDE_RE.sub('',e.text)) for e in candidates}
    eligible = set()
    for e in events:
        if (e.kind != 'Dialogue' or (e.style,e.name) not in families or
                get_pos(e.text) is None or
                re.search(r'\\(?:move|t|clip|iclip|fad|fade)(?=[^A-Za-z]|$)',e.text,re.I)):
            continue
        literal = OVERRIDE_RE.sub('',e.text)
        if ((e.style,e.name,e.start,literal) in endings and
                (e.style,e.name,e.end,literal) in beginnings):
            eligible.add((e.style,e.name))
    families = eligible
    if not families:
        return set()
    return families


def _sliced_text_layout(e: Event, state: dict, *, scaled: bool = False) -> tuple:
    """Use the existing layout and literal-font key, optionally omitting scale."""
    sample = dataclass_replace(e,state=state)
    return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
            tuple((k,v) for k,v in text_layout_key(sample)
                  if not scaled or k not in {'fscx','fscy'}),literal_font_spans(e))


def _sliced_text_paint(state: dict) -> tuple:
    """Match the original fill, outline, alpha and contour-width channels."""
    return tuple(state.get(k,DEFAULT_STATE.get(k)) for k in
                 ('1c','3c','1a','3a','bord','xbord','ybord'))


def _profile_sliced_text_event(e: Event, families: set[tuple[str,str]]) -> SlicedTextEvent | None:
    """Resolve eligible literal text, static geometry and original movement/transform tokens."""
    if ((e.style,e.name) not in families or e.kind != 'Dialogue' or
            e.duration <= 0 or not e.layer.lstrip('-').isdigit() or
            not OVERRIDE_RE.sub('',e.text).strip() or
            any(tag in e.text for tag in (r'\N',r'\n',r'\h')) or
            literal_font_spans(e) is None):
        return None
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    if (state.get('p',0) or state.get('borderstyle',1) != 1 or
            any(k in state for k in ('iclip','org')) or
            any(abs(state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay')) or
            any(abs(state.get(k,state.get('shad',0))) > .001 for k in ('xshad','yshad')) or
            any(not math.isfinite(state.get(k,0)) or state.get(k,0) <= 0
                for k in ('fs','fscx','fscy'))):
        return None
    p = dataclass_replace(e,state=state,continuation=evaluated.continuation)
    tokens = event_override_tokens(p)
    moves = [v for tag,v in tokens if tag == 'move']
    transforms = [v for tag,v in tokens if tag == 't']
    if any(tag in {'fad','fade','k','kf','ko'} for tag,value in tokens):
        return None
    pos = get_pos(e.text)
    key = _sliced_text_layout(p,state)
    return SlicedTextEvent(p,moves,transforms,pos,key)


def _sliced_text_final_state(profile: SlicedTextEvent) -> dict | None:
    """Resolve exactly one admitted transform and apply its final paint/scale state."""
    e = profile.event
    state,moves,transforms = e.state,profile.moves,profile.transforms
    if len(transforms) != 1:
        return None
    final = state.copy()
    final_continuation = e.continuation
    allowed = {'alpha','1a','3a','blur','be'} | ({'fscx','fscy'} if not moves else set())
    transform = parse_effect_transform(transforms[0],e.duration,allowed)
    if transform is None:
        return None
    for tag,value in transform[2]:
        final_continuation = apply_override(final,tag,value,e.styles,e.defaults,final_continuation)
    return final


def _index_sliced_text_pulse(index: SlicedTextIndex, profile: SlicedTextEvent, final: dict) -> None:
    """Index borderless translucent copies that fade to invisible at a fixed anchor."""
    p = profile.event
    e,state,pos = p,p.state,profile.pos
    if (0 < state.get('1a',0) < 254 and final.get('1a',0) >= 254 and
            max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord')) <= .001):
        index.pulses.setdefault((_sliced_text_layout(p,state,scaled=True),e.start,e.end,pos),[]).append((p,final))


def _index_sliced_text_tile(index: SlicedTextIndex, profile: SlicedTextEvent, final: dict) -> None:
    """Index clipped moving strips only at an opaque entrance or exit endpoint."""
    p = profile.event
    e,state,moves,pos,key = p,p.state,profile.moves,profile.pos,profile.key
    rect = rectangle_clip(p)
    if len(moves) != 1 or pos is not None or rect is None:
        return
    move = parse_effect_move(moves[0],e.duration,endpoint_slack=50)
    if move is None or math.dist(move[:2],move[2:4]) <= e.unit:
        return
    if (state.get('1a',0) >= 254 and state.get('3a',0) >= 254 and
            final.get('1a',0) == 0 and final.get('3a',0) == 0):
        phase,boundary,anchor,pose = 'in',e.end,tuple(move[2:4]),final
    elif (state.get('1a',0) == 0 and state.get('3a',0) == 0 and
            final.get('1a',0) >= 254 and final.get('3a',0) >= 254):
        phase,boundary,anchor,pose = 'out',e.start,tuple(move[:2]),state
    else:
        return
    index.tiles.setdefault((key,phase,boundary,anchor,e.start,e.end,e.layer,_sliced_text_paint(pose)),[]).append((p,rect))


def _index_sliced_text_event(index: SlicedTextIndex, profile: SlicedTextEvent) -> None:
    """Classify one resolved event as a hold, pulse or strip in the original order."""
    p = profile.event
    e,state,moves,transforms,pos,key = p,p.state,profile.moves,profile.transforms,profile.pos,profile.key
    if (not moves and not transforms and pos is not None and
            opaque_text_effect_state(state) and state.get('3a',0) == 0):
        index.holds.setdefault((key,e.start,e.end,pos),[]).append(p)
        return
    final = _sliced_text_final_state(profile)
    if final is None:
        return
    if not moves and pos is not None and 'clip' not in state:
        _index_sliced_text_pulse(index,profile,final)
        return
    _index_sliced_text_tile(index,profile,final)


def _prove_sliced_text_strip_phases(tiles: dict) -> dict:
    """Require adjacent full-width strips covering the anchor text box and border."""
    proven = {}
    for (key,phase,boundary,anchor,start,end,layer,colors),peers in tiles.items():
        first = peers[0][0]
        canvas = first.measurement.canvas
        peers.sort(key=lambda item:item[1][1])
        if (len(peers) < 3 or canvas is None or
                any(rect[0] != 0 or rect[2] != canvas[0] for e,rect in peers) or
                any(a[1][3] != b[1][1] for a,b in zip(peers,peers[1:]))):
            continue
        height = text_height(first)
        alignment = int(first.state.get('an',2))
        top = anchor[1] - ((2-(alignment-1)//3)/2)*height
        border = max(first.state.get(k,first.state.get('bord',0)) for k in ('xbord','ybord'))
        if peers[0][1][1] > top-border or peers[-1][1][3] < top+height+border:
            continue
        proven.setdefault((key,phase,boundary,anchor,colors),[]).append([e for e,rect in peers])
    return proven


def _propose_sliced_text_caption(index: SlicedTextIndex, copies: list[Event], base: Event,
                                 incoming: list[list[Event]], outgoing: list[list[Event]],
                                 start: str, end: str, pos: tuple) -> tuple[set[int],Event]:
    """Collect proven phases and matching pulses, then render the recorded hold and entrance start."""
    members = {e.source_index for e in copies+incoming[0]+outgoing[0]}
    for p,final in index.pulses.get((_sliced_text_layout(base,base.state,scaled=True),start,end,pos),[]):
        # The source is a fading copy at this exact anchor and interval.
        # Its positive starting size may be larger or smaller; the exact
        # return to the proven hold identifies it, not its amplitude.
        if (int(p.layer) >= max(int(e.layer) for e in copies) and
                all(final.get(k,100) == base.state.get(k,100) for k in ('fscx','fscy'))):
            members.add(p.source_index)
    prefix = re.match(r'(?:\{[^}]*\})*',base.text).end()
    caption = replace_event(base,text=render_simplified_caption(
                {**base.state,'fn':literal_font_spans(base)[0][1]},base.text[prefix:],measurement=base.measurement,
                source_paint=_source_caption_paint(base.state,[e.state for e in copies])),
                start=incoming[0][0].start,start_s=incoming[0][0].start_s,
                source_index=min(members))
    return members,caption


def _propose_sliced_text_replacements(index: SlicedTextIndex, proven: dict) -> list[tuple[set[int],Event]]:
    """Match each unanimous hold to exactly one complete incoming and outgoing phase."""
    proposals = []
    for (key,start,end,pos),copies in index.holds.items():
        if len({_sliced_text_paint(e.state) for e in copies}) != 1:
            continue
        base = copies[0]
        colors = _sliced_text_paint(base.state)
        incoming = proven.get((key,'in',start,pos,colors),[])
        outgoing = proven.get((key,'out',end,pos,colors),[])
        if len(incoming) != 1 or len(outgoing) != 1:
            continue
        proposals.append(_propose_sliced_text_caption(index,copies,base,incoming,outgoing,start,end,pos))
    return proposals


def _accept_sliced_text_ownership(proposals: list[tuple[set[int],Event]]) -> list[tuple[set[int],Event]]:
    """Accept proposals only when every consumed source event has a single owner."""
    owners = {}
    for members,caption in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    accepted = [(members,caption) for members,caption in proposals
                if all(owners[index] == 1 for index in members)]
    return accepted


def _group_sliced_text_cues(accepted: list[tuple[set[int],Event]], holds: dict) -> dict:
    """Group accepted captions with their original held geometry and paint."""
    held_by_id = {e.source_index:e for copies in holds.values() for e in copies}
    cues = {}
    for members,caption in accepted:
        base = next(held_by_id[i] for i in members if i in held_by_id)
        cue_key = (caption.style,caption.name,caption.start,
                   get_pos(caption.text)[1],text_layout_key(base),_sliced_text_paint(base.state))
        cues.setdefault(cue_key,[]).append((members,caption,base))
    return cues


def _adjust_sliced_text_cue_timing(peers: list, comments: list[Event], adjusted: dict[int,Event]) -> None:
    """Use complete anchor-ordered authored lyrics to adjust a cue to its held timing."""
    peers.sort(key=lambda item:get_pos(item[1].text)[0])
    if len({get_pos(c.text)[0] for ids,c,base in peers}) != len(peers):
        return
    beginning = min(base.start_s for ids,c,base in peers)
    finish = max(base.end_s for ids,c,base in peers)
    literal = ''.join(OVERRIDE_RE.sub('',c.text) for ids,c,base in peers)
    norm = lambda value: ''.join(value.split())
    if any(e.style == peers[0][1].style and e.name == peers[0][1].name and
           abs(e.start_s-beginning) <= .05 and abs(e.end_s-finish) <= .05 and
           norm(simplify_text(e.text,visible_only=True)[1]) == norm(literal)
           for e in comments):
        adjusted.update((c.source_index,replace_event(c,start=format_time(beginning),
            start_s=beginning,end=format_time(finish),end_s=finish))
            for ids,c,base in peers)


def _adjust_authored_sliced_text_timing(events: list[Event], index: SlicedTextIndex,
                                        accepted: list[tuple[set[int],Event]]) -> list[tuple[set[int],Event]]:
    """Adjust only fully proven cues with coincident authored timing and complete literal text."""
    # A matching authored lyric proves the complete cue, including fragments
    # with inline fonts that the ordinary row assembler keeps positioned.
    # Its times must coincide with the first and last held phases, and every
    # literal character must be present in anchor order. Trim decorative
    # entrances/exits to those lyric bounds rather than exposing overlapping
    # full captions during neighboring strip fades.
    cues = _group_sliced_text_cues(accepted,index.holds)
    adjusted = {}
    comments = [e for e in events if e.kind == 'Comment' and e.duration > 0]
    for peers in cues.values():
        _adjust_sliced_text_cue_timing(peers,comments,adjusted)
    return [(ids,adjusted.get(c.source_index,c)) for ids,c in accepted]


def collapse_sliced_text_sequences(events: list[Event]) -> tuple[list[Event],int]:
    """Replace a tiled entrance/held-text/exit with its recorded opaque text.

    Adjacent full-width strips must cover the held text's vertical box and
    converge to, or depart from, its exact anchor at touching phase boundaries.
    Both complete strip phases prove the effect. Matching translucent size
    pulses are decoration; unrelated copies and incomplete tiles stay intact.
    """
    families = _eligible_sliced_text_families(events)
    if not families:
        return events,0
    index = SlicedTextIndex({},{},{})
    for e in events:
        profile = _profile_sliced_text_event(e,families)
        if profile is not None:
            _index_sliced_text_event(index,profile)
    proven = _prove_sliced_text_strip_phases(index.tiles)
    proposals = _propose_sliced_text_replacements(index,proven)
    accepted = _accept_sliced_text_ownership(proposals)
    if not accepted:
        return events,0
    accepted = _adjust_authored_sliced_text_timing(events,index,accepted)
    consumed = set().union(*(members for members,caption in accepted))
    output = [e for e in events if e.source_index not in consumed]
    output.extend(caption for members,caption in accepted)
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output)
