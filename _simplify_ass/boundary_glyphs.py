"""Complete source-boundary glyph proofs; callers apply removal IDs and report."""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, replace as dataclass_replace

from .ass_overrides import (OverrideContinuation, apply_override, evaluate_effective_state)
from .font_metrics import (FontMetrics)
from .glyph_placement import (fit_fragment_anchor)
from .event_model import (Event)
from .effect_validation import (parse_effect_transform, parse_effect_move)
from .event_operations import (event_override_tokens)
from .caption_geometry import (get_pos, inline_layout_key, placement_key, text_layout_key)
from .text_freezing import (simplify_text)
from .static_selection import (unrotated_text_state, upright_text_state)
from .effect_validation import (opaque_text_effect_state)
from .boundary_groups import (nearby_boundary_groups)
from .effect_validation import _parse_simple_source_fade


@dataclass(frozen=True)
class BoundaryGlyphPhase:
    """Classified authored entrance/exit with its boundary, anchor, state and glyph."""
    phase: str
    boundary: float
    pos: tuple
    state: dict
    glyph: str
    continuation: OverrideContinuation



@dataclass(frozen=True)
class BoundaryGlyphIndex:
    """Per-call effect groups, caption candidates and source/protection membership."""
    groups: dict
    captions: dict
    caption_candidates: list
    boundary_sources: set[int]
    protected: set[int]



def _boundary_glyph_geometry(e: Event, y: float) -> tuple:
    return (e.style,e.name,placement_key(e),y,
            tuple((k,v) for k,v in text_layout_key(e)
                  if k not in {'frz','frx','fry'}))



def _boundary_glyph_caption_key(e: Event, original: Event, word: str, pos: tuple | None):
    """Admit an opaque upright word anchored at its original source position."""
    if (e.duration > 0 and word and pos is not None and upright_text_state(e.state) and
            e.state.get('1a',0) == 0 and not any(c.isspace() for c in word) and
            not any(k in e.state for k in ('clip','iclip','org')) and
            get_pos(original.text) == pos):
        return _boundary_glyph_geometry(e,pos[1])
    return None



def _classify_boundary_glyph_phase(original: Event, state: dict, tokens: list, fade: list, unit: float, *,
                                    continuation: OverrideContinuation):
    """Classify a fading rotation into an upright entrance or a moving flying exit."""
    moves = [value for tag,value in tokens if tag == 'move']
    transforms = [value for tag,value in tokens if tag == 't']
    phase = None
    if not moves and len(transforms) == 1 and get_pos(original.text) is not None:
        transform = parse_effect_transform(transforms[0],original.duration,
                                           {'fr','frz','frx','fry','blur','be'})
        if transform is None:
            return None
        begin,end,changes = transform
        final = state.copy()
        final_continuation = continuation
        for tag,value in changes:
            final_continuation = apply_override(final,tag,value,original.styles,original.defaults,final_continuation)
        # Source fade parameters may finish one frame beyond the record,
        # matching exit validation. The event boundary itself stays exact.
        if (unrotated_text_state(state) or not unrotated_text_state(final) or
                not 0 < fade[0] <= 1000*original.duration+50 or fade[1] != 0):
            return None
        phase,boundary,pos = 'entrance',original.end_s,get_pos(original.text)
    elif len(moves) == 1 and not transforms and unrotated_text_state(state):
        move = parse_effect_move(moves[0],original.duration,endpoint_slack=50)
        if (move is None or math.dist(move[:2],move[2:4]) < unit or
                get_pos(original.text) is not None or
                fade[0] != 0 or not 0 < fade[1] <= 1000*original.duration+50):
            return None
        phase,boundary,pos = 'exit',original.start_s,tuple(move[:2])
    return (phase,boundary,pos) if phase is not None else None



def _profile_boundary_glyph_source(original: Event, unit: float):
    """Require one authored glyph and supported opaque geometry before phase classification."""
    glyph = simplify_text(original.text,visible_only=True)[1]
    if (len(glyph) != 1 or glyph.isspace() or unicodedata.combining(glyph) or
            original.duration <= 0):
        return None
    tokens = event_override_tokens(original)
    evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
    state = evaluated.formatting
    if (not opaque_text_effect_state(state) or
            any(abs(state.get(k,0)) > .001 for k in ('fax','fay'))):
        return None
    fade = _parse_simple_source_fade(tokens)
    if fade is None:
        return None
    classified = _classify_boundary_glyph_phase(original,state,tokens,fade,unit,continuation=evaluated.continuation)
    if classified is None:
        return None
    phase,boundary,pos = classified
    return BoundaryGlyphPhase(phase,boundary,pos,state,glyph,evaluated.continuation)



def _boundary_glyph_protection(e: Event, original: Event, word: str, phase: str, pos: tuple, glyph: str):
    """Protect an absorbed held entrance; reject extended sources without that proof."""
    if e.duration > original.duration+.001:
        # A one-letter syllable may already include its entrance in
        # the retained cue. It proves its slot but must never be
        # removed along with its decorative peers. Compare source
        # coverage instead of guessing from the event's duration.
        if (phase != 'entrance' or word != glyph or get_pos(e.text) != pos or
                not upright_text_state(e.state) or e.state.get('1a',0) != 0):
            return None
        return True
    return False



def _index_boundary_glyph_events(events: list[Event], visible_map: dict[int,str], source_events: dict[int,Event]):
    """Collect retained caption candidates, classified effects and protected source IDs."""
    groups, captions = {}, {}
    caption_candidates = []
    boundary_sources, protected = set(), set()
    for e in events:
        original = source_events.get(e.source_index)
        if original is None or e.kind != 'Dialogue' or inline_layout_key(original):
            continue
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        key = _boundary_glyph_caption_key(e,original,word,pos)
        if key is not None:
            caption_candidates.append((e,key))
        profile = _profile_boundary_glyph_source(original,e.unit)
        if profile is None:
            continue
        phase,boundary,pos = profile.phase,profile.boundary,profile.pos
        source = dataclass_replace(original,state=profile.state,continuation=profile.continuation)
        key = (phase,_boundary_glyph_geometry(source,pos[1]))
        boundary_sources.add(e.source_index)
        protect = _boundary_glyph_protection(e,original,word,phase,pos,profile.glyph)
        if protect is None:
            continue
        if protect:
            protected.add(e.source_index)
            captions.setdefault(key,{}).setdefault(boundary,[]).append(e)
        groups.setdefault((key,boundary),[]).append((e,pos,profile.glyph))
    return BoundaryGlyphIndex(groups,captions,caption_candidates,boundary_sources,protected)



def _index_boundary_glyph_captions(index: BoundaryGlyphIndex):
    """Index independent held captions and protected absorbed phases at both boundaries."""
    # A long frozen entrance is still an entrance, not another held word.
    # Only a source-independent caption or an absorbed held phase can prove
    # the destination. This distinction also permits genuinely brief holds.
    for e,key in index.caption_candidates:
        if e.source_index not in index.boundary_sources or e.source_index in index.protected:
            for phase,boundary in (('entrance',e.start_s),('exit',e.end_s)):
                index.captions.setdefault((phase,key),{}).setdefault(boundary,[]).append(e)

    return {key:(sorted(phases),phases) for key,phases in index.captions.items()}



def _match_boundary_glyph_words(key: tuple, boundary: float, peers: list, caption_index: dict, visible_map: dict[int,str]):
    """Match the complete ordered glyph sequence to nearby words using each closest source anchor once."""
    nearby = nearby_boundary_groups(caption_index,key,boundary)
    # An absorbed one-letter entrance can appear at both its emitted and
    # original stable boundary. Use its closest anchor once; independent
    # nearby repetitions retain distinct source IDs and fail the proof.
    candidates = {}
    for time,words in nearby:
        for e in words:
            previous = candidates.get(e.source_index)
            if previous is None or abs(time-boundary) < abs(previous[0]-boundary):
                candidates[e.source_index] = (time,e)
    times = [time for time,e in candidates.values()]
    if not times or max(times)-min(times) > .05+1e-6:
        return None
    words = sorted((e for time,e in candidates.values()),key=lambda e:get_pos(e.text)[0])
    if (sum(len(visible_map[e.source_index]) for e in words) != len(peers) or
            len(peers) < 3 or len({pos[0] for e,pos,char in peers}) != len(peers) or
            ''.join(visible_map[e.source_index] for e in words) != ''.join(c for e,p,c in peers)):
        return None
    return words



def _fit_boundary_glyph_words(
    peers: list, words: list[Event], visible_map: dict[int, str], metric: FontMetrics,
):
    """Fit every authored word anchor with the exact font and original tracking allowance."""
    offset = 0
    for word in words:
        text = visible_map[word.source_index]
        letters = peers[offset:offset+len(text)]
        offset += len(text)
        anchor = fit_fragment_anchor(metric, word.state,[p[0] for e,p,c in letters],
                                       [c for e,p,c in letters],text,word.unit,
                                       allow_tracking=True)
        if anchor is None or abs(anchor-get_pos(word.text)[0]) > 1.5*word.unit:
            return False
    return True



def _collect_boundary_glyph_proposals(
    index: BoundaryGlyphIndex, caption_index: dict, visible_map: dict[int, str],
    metric: FontMetrics,
):
    """Build complete boundary proposals only after literal and font-anchor proofs."""
    proposals = []
    for (key,boundary),peers in index.groups.items():
        peers.sort(key=lambda item:item[1][0])
        words = _match_boundary_glyph_words(key,boundary,peers,caption_index,visible_map)
        if words is None or not _fit_boundary_glyph_words(peers,words,visible_map,metric):
            continue
        proposals.append((key[0],peers,words))
    return proposals



def _resolve_boundary_glyph_ownership(proposals: list, protected: set[int]):
    """Require unique effect ownership and one caption owner per phase, retaining protected glyphs."""
    effect_owners, caption_owners = {}, {}
    for phase,peers,words in proposals:
        for e,p,c in peers:
            effect_owners[e.source_index] = effect_owners.get(e.source_index,0)+1
        for e in words:
            owner = (phase,e.source_index)
            caption_owners[owner] = caption_owners.get(owner,0)+1
    return {e.source_index for phase,peers,words in proposals
            if all(effect_owners[e.source_index] == 1 for e,p,c in peers) and
               all(caption_owners[(phase,e.source_index)] == 1 for e in words)
            for e,p,c in peers if e.source_index not in protected and
            all(e.source_index != word.source_index for word in words)}



def match_boundary_glyph_effects(
    events: list[Event], visible_map: dict[int, str], source_events: dict[int, Event],
    metric: FontMetrics | None,
) -> set[int]:
    """Prove whole rotating entrances and flying exits of retained words.

    The source phase must meet the static caption within 50 ms, spell every
    fragment in order, and fit each authored word anchor with the exact font,
    including tracking. Partial groups, duplicate letters and unrelated labels cannot
    authorize removal. The retained words supply text; no spaces are inferred.
    """
    if metric is None or not metric.available:
        return set()
    index = _index_boundary_glyph_events(events,visible_map,source_events)
    caption_index = _index_boundary_glyph_captions(index)
    proposals = _collect_boundary_glyph_proposals(index,caption_index,visible_map,metric)
    return _resolve_boundary_glyph_ownership(proposals,index.protected)
