"""Complete shrinking glyph-row proof, ownership and fade handoffs."""
from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import re
import unicodedata

from .ass_overrides import tokenize_override, apply_override, evaluate_effective_state, OVERRIDE_RE
from .font_metrics import FontMetrics
from .glyph_placement import matches_authored_glyph_positions
from .event_model import Event
from .effect_validation import parse_effect_transform, parse_effect_move
from .event_operations import event_override_tokens, replace_event
from .caption_geometry import get_pos, inline_layout_key, placement_key, text_layout_key
from .text_freezing import simplify_text, simplify_visual_text
from .subtitle_document import format_time
from .static_selection import unrotated_text_state
from .boundary_groups import nearby_boundary_groups


@dataclass(frozen=True)
class ShrinkingRowSource:
    """Resolved source text with its original move and transform evidence."""
    event: Event
    text: str
    moves: list[str]
    transforms: list[str]


@dataclass(frozen=True)
class ShrinkingRowIndex:
    """Private complete-row groups and held-caption boundary index for one pass."""
    groups: dict
    caption_index: dict


@dataclass(frozen=True)
class ShrinkingRowProposal:
    """A complete shrinking source row and its unique held-caption owner."""
    start_s: float
    end_s: float
    layer: str
    peers: list
    held: Event


def _eligible_shrinking_row_families(events: dict[int,Event]) -> set:
    """Prefilter families with explicit moving scale fades and a positioned hold."""
    # Reject unrelated families before parsing transforms or freezing holds.
    # Every accepted shrinking fade must explicitly change both scale axes
    # and at least one visible alpha channel inside a moving source event.
    families = {(e.style,e.name) for e in events.values()
                if e.kind == 'Dialogue' and
                re.search(r'\\move\s*\(',e.text) and
                re.search(r'\\t\s*\(',e.text) and
                re.search(r'\\fscx(?=[^A-Za-z]|$)',e.text) and
                re.search(r'\\fscy(?=[^A-Za-z]|$)',e.text) and
                re.search(r'\\(?:alpha|[13]a)(?=[^A-Za-z]|$)',e.text)}
    families &= {(e.style,e.name) for e in events.values()
                 if (e.style,e.name) in families and e.kind == 'Dialogue' and
                 re.search(r'\\pos\s*\(',e.text) and
                 not re.search(r'\\move\s*\(',e.text) and
                 len(OVERRIDE_RE.sub('',e.text).strip()) >= 3}
    return families


def _shrinking_row_geometry(e: Event) -> tuple:
    """Use the existing placement/layout key, allowing the two shrinking scale axes."""
    return (e.style,e.name,placement_key(e),
            tuple((k,v) for k,v in text_layout_key(e)
                  if k not in {'fscx','fscy'}))


def _profile_shrinking_row_source(original: Event, families: set) -> ShrinkingRowSource | None:
    """Resolve one eligible source and reject unsupported geometry or timing effects."""
    if (original.kind != 'Dialogue' or original.duration <= 0 or
            (original.style,original.name) not in families or
            not re.search(r'\\(?:move|pos)\s*\(',original.text) or
            inline_layout_key(original)):
        return None
    tokens = event_override_tokens(original)
    moves = [v for k,v in tokens if k == 'move']
    transforms = [v for k,v in tokens if k == 't']
    text = simplify_text(original.text,visible_only=True)[1]
    if not text:
        return None
    evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
    state = evaluated.formatting
    e = dataclass_replace(original,state=state,continuation=evaluated.continuation)
    if (not unrotated_text_state(state) or state.get('p',0) or
            state.get('borderstyle',1) != 1 or
            any(k in state for k in ('clip','iclip','org')) or
            any(abs(state.get(k,0)) > .001 for k in ('fax','fay')) or
            any(k in {'fad','fade','k','K','kf','ko'} for k,v in tokens)):
        return None
    return ShrinkingRowSource(e,text,moves,transforms)


def _index_shrinking_row_hold(captions: dict, source: ShrinkingRowSource, max_blur: float) -> None:
    """Freeze an opaque geometry-stable hold and index both authored boundaries."""
    e,text,transforms = source.event,source.text,source.transforms
    # A held caption may fade, but its font and geometry must stay held.
    if any(any(k not in {'alpha','1a','2a','3a','4a'}
               for k,v in tokenize_override('\\'+value[1:-1].partition('\\')[2]))
           for value in transforms):
        return
    frozen,visible,drawings = simplify_visual_text(
        e.text,max_blur,e.duration,e.defaults,e.styles,1,
        upright_crossings=False)
    held = replace_event(e,text=frozen)
    if drawings or visible != text or held.state.get('1a',0) != 0:
        return
    for boundary in (e.start_s,e.end_s):
        captions.setdefault(_shrinking_row_geometry(held),{}).setdefault(boundary,[]).append(held)


def _prove_shrinking_row_glyph(source: ShrinkingRowSource) -> tuple | None:
    """Require one near-vertical move and one shrinking transform ending in transparent paint."""
    e,text,moves,transforms = source.event,source.text,source.moves,source.transforms
    state = e.state
    if (len(text) != 1 or text.isspace() or unicodedata.combining(text) or
            len(moves) != 1 or len(transforms) != 1 or get_pos(e.text) is not None):
        return None
    move = parse_effect_move(moves[0],e.duration,endpoint_slack=50)
    transform = parse_effect_transform(transforms[0],e.duration,
                                       {'fscx','fscy','alpha','1a','2a','3a','4a','blur','be'})
    if (move is None or transform is None or
            transform[0] >= 1000*e.duration or
            len(move) == 6 and move[4] >= 1000*e.duration or
            abs(move[0]-move[2]) > e.unit):
        return None
    final = state.copy()
    final_continuation = e.continuation
    for tag,value in transform[2]:
        final_continuation = apply_override(final,tag,value,e.styles,e.defaults,final_continuation)
    if (not all(0 < final.get(k,100) < state.get(k,100) for k in ('fscx','fscy')) or
            final.get('1a',0) != 255 or final.get('3a',0) != 255 or
            state.get('1a',0) == 255 and
            (state.get('3a',0) == 255 or state.get('bord',0) <= 0)):
        return None
    return e,text,move


def _index_shrinking_row_sources(events: dict[int,Event], families: set, max_blur: float) -> ShrinkingRowIndex:
    """Keep held-caption boundaries separate from complete source row groups."""
    groups, captions = {}, {}
    for original in events.values():
        source = _profile_shrinking_row_source(original,families)
        if source is None:
            continue
        e,text,moves = source.event,source.text,source.moves
        if not moves and len(text.strip()) >= 3 and get_pos(e.text) is not None:
            _index_shrinking_row_hold(captions,source,max_blur)
            continue
        glyph = _prove_shrinking_row_glyph(source)
        if glyph is not None:
            key = (_shrinking_row_geometry(e),e.start_s,e.end_s,e.layer)
            groups.setdefault(key,[]).append(glyph)
    caption_index = {key:(sorted(times),times) for key,times in captions.items()}
    return ShrinkingRowIndex(groups,caption_index)


def _shrinking_row_owners(
    caption_index: dict, metric: FontMetrics, key: tuple, start: float, end: float, peers: list,
) -> list[Event]:
    """Find boundary owners with complete literals, held geometry and exact-font anchors."""
    owners = []
    for time,helds in nearby_boundary_groups(caption_index,key,end):
        # Extend touching entrances; an existing hold can also cover the
        # whole burst. Never bridge a real gap or erase a partial overlap.
        if abs(time-end) > 1e-6:
            continue
        for held in helds:
            literal = simplify_text(held.text,visible_only=True)[1]
            if ''.join(c for e,c,m in peers) != ''.join(literal.split()):
                continue
            pos = get_pos(held.text)
            height = held.state.get('fs',20)*held.state.get('fscy',100)/100
            if (held.duration < end-start or
                    not (held.start_s == end or
                         held.start_s <= start and held.end_s >= end) or
                    any(abs(y-pos[1]) > .3*height for e,c,m in peers
                        for y in (m[1],m[3])) or
                    not matches_authored_glyph_positions(metric,
                        held.state,[m[0] for e,c,m in peers],literal,pos[0],held.unit)):
                continue
            owners.append(held)
    return owners


def _adjust_shrinking_row_fade_handoffs(events: dict[int,Event], caption_index: dict, replacements: dict[int,Event]) -> None:
    """Trim proven transparent predecessors and delay entrances only to their fade boundary."""
    # Extending an entrance must not revive a preceding caption that was
    # already completely transparent. A single validated terminal alpha
    # transform proves a clean handoff; visible/ambiguous overlaps stay intact.
    for current in list(replacements.values()):
        original = events[current.source_index]
        if current.start_s >= original.start_s:
            continue
        preceding = [held for time,holds in nearby_boundary_groups(
                     caption_index,_shrinking_row_geometry(current),original.start_s)
                 for held in holds if held.source_index != current.source_index and
                 held.end_s == original.start_s and held.start_s < current.start_s and
                 held.layer == current.layer and get_pos(held.text) == get_pos(current.text)]
        if len(preceding) != 1:
            continue
        held = preceding[0]
        source = events[held.source_index]
        transforms = [v for k,v in event_override_tokens(source) if k == 't']
        if len(transforms) != 1:
            continue
        fade = parse_effect_transform(transforms[0],source.duration,
            {'alpha','1a','2a','3a','4a'},allow_instant=True)
        if fade is None or source.start_s+fade[1]/1000 > original.start_s+1e-6:
            continue
        evaluated = evaluate_effective_state(source.text,source.defaults,source.styles)
        final = evaluated.formatting
        final_continuation = evaluated.continuation
        for tag,value in fade[2]:
            final_continuation = apply_override(final,tag,value,source.styles,source.defaults,final_continuation)
        if not all(final.get(k,0) == 255 for k in ('1a','3a','4a')):
            continue
        finish = source.start_s+fade[1]/1000
        previous = replacements.get(held.source_index,held)
        replacements[held.source_index] = replace_event(
            previous,end=format_time(finish),end_s=finish)
        # If the preceding source stays visible for part of the entrance,
        # delay the replacement caption to its fade boundary. Keep real gaps.
        if finish > current.start_s:
            replacements[current.source_index] = replace_event(
                current,start=format_time(finish),start_s=finish)


def collapse_shrinking_glyph_rows(
    events: dict[int, Event], metric: FontMetrics | None, max_blur: float,
) -> tuple[dict[int, Event], int]:
    """Use a held caption for its complete moving, shrinking, fading row.

    Work before freezing/merging glyphs loses their source identity. Every
    layer must spell the whole caption and match its exact-font anchors at
    the held size. Paint copies may differ; the retained caption supplies
    formatting. Touching entrances and copies within the hold share that proof.
    Without a unique held owner, keep the existing simplification.
    """
    if metric is None or not metric.available:
        return events,0
    families = _eligible_shrinking_row_families(events)
    if not families:
        return events,0
    index = _index_shrinking_row_sources(events,families,max_blur)
    proposals = []
    for (key,start,end,layer),peers in index.groups.items():
        peers.sort(key=lambda item:item[2][0])
        if len(peers) < 3 or len({m[0] for e,c,m in peers}) != len(peers):
            continue
        owners = _shrinking_row_owners(index.caption_index,metric,key,start,end,peers)
        if len(owners) == 1:
            proposals.append(ShrinkingRowProposal(start,end,layer,peers,owners[0]))

    # Ambiguous repetitions at one boundary cannot share ownership. Different
    # paint layers of the same complete row deliberately share a caption.
    claims = {}
    for proposal in proposals:
        key = (proposal.held.source_index,proposal.layer,proposal.end_s)
        claims[key] = claims.get(key,0)+1
    removed, replacements = set(), {}
    for proposal in proposals:
        held = proposal.held
        if claims[(held.source_index,proposal.layer,proposal.end_s)] != 1:
            continue
        removed.update(e.source_index for e,c,m in proposal.peers)
        previous = replacements.get(held.source_index,held)
        if proposal.start_s < previous.start_s:
            replacements[held.source_index] = replace_event(
                held,start=format_time(proposal.start_s),start_s=proposal.start_s)
    if not removed:
        return events,0
    _adjust_shrinking_row_fade_handoffs(events,index.caption_index,replacements)
    return {idx:replacements.get(idx,e) for idx,e in events.items() if idx not in removed},len(removed)
