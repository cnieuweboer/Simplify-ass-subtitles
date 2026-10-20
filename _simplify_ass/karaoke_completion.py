"""Ordered karaoke completion proof and destination paint replacement."""
from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import math

from .ass_overrides import apply_override, evaluate_effective_state, effective_state
from .event_model import Event
from .event_operations import event_override_tokens, replace_event
from .effect_validation import parse_effect_transform
from .caption_geometry import (
    get_pos, inline_layout_key, text_height, placement_key, text_layout_key,
)
from .text_freezing import simplify_text
from .caption_rendering import render_tag
from .static_selection import unrotated_text_state, upright_text_state


@dataclass(frozen=True)
class KaraokeCompletionSourcePhase:
    """Validated source hold or one paint transition, before whole-fragment proof."""
    hold: tuple | None
    transition: tuple | None


@dataclass(frozen=True)
class KaraokeCompletionProfile:
    """A fragment's paint pair, activation, resolved replacement paint and completed hold.

    Paint identities can contain an admitted strip palette. Final formatting
    contains the paint fields this route replaces, never its proof metadata.
    """
    before: tuple
    after: tuple
    begin: float
    end: float
    final: dict
    completed: bool


def _karaoke_completion_identity(e: Event, word: str) -> tuple:
    """Match authored layout/placement/word with whole-turn rotation equivalence."""
    layout = tuple((k,math.remainder(v,360)
                   if k in {'frz','frx','fry'} and math.isfinite(v) else v)
                   for k,v in text_layout_key(e))
    return (e.style,e.name,placement_key(e),layout,
            get_pos(e.text),word)


def _karaoke_completion_cue_start(e: Event, source_events: dict[int,Event]) -> float:
    """Exclude an absorbed rotating entrance from the later upright colour sweep."""
    original = source_events.get(e.source_index)
    if (original is not None and original.duration > 0 and
            original.end_s < e.end_s and
            not unrotated_text_state(effective_state(original.text,original.defaults,original.styles))):
        # Exact-position phase reduction can absorb a rotating one-letter
        # entrance. Only the later upright phases belong to its sweep.
        return original.end_s
    return e.start_s


def _karaoke_completion_paint(state: dict) -> tuple:
    """Compare primary/outline colours and the effective horizontal/vertical border widths."""
    return (state.get('1c'),state.get('3c'),
            state.get('xbord',state.get('bord',0)),
            state.get('ybord',state.get('bord',0)))


def _index_retained_karaoke_completion_rows(events: list[Event], visible_map: dict[int,str], source_events: dict[int,Event]) -> dict:
    """Group opaque upright retained fragments by source-aware cue and authored row geometry."""
    rows = {}
    for e in events:
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or not word or pos is None or inline_layout_key(e) or
                not upright_text_state(e.state) or e.state.get('1a',0) != 0 or
                any(k in e.state for k in ('clip','iclip','org'))):
            continue
        key = (_karaoke_completion_cue_start(e,source_events),e.end,_karaoke_completion_identity(e,'')[:4],pos[1])
        rows.setdefault(key,[]).append(e)
    return rows


def _select_karaoke_completion_rows(rows: dict, visible_map: dict[int,str]) -> list[list[Event]]:
    """Require distinct ordered anchors and the original text-size-based spacing bound."""
    candidates = []
    for row in rows.values():
        row.sort(key=lambda e:get_pos(e.text)[0])
        if (len(row) < 2 or len({get_pos(e.text)[0] for e in row}) != len(row) or
                any(get_pos(b.text)[0]-get_pos(a.text)[0] >
                    2*max(text_height(a),text_height(b)) +
                    text_height(a)*len(visible_map[a.source_index])
                    for a,b in zip(row,row[1:]))):
            continue
        candidates.append(row)
    return candidates


def _index_karaoke_completion_sources(candidates: list[list[Event]], visible_map: dict[int,str], source_events: dict[int,Event]) -> dict:
    """Resolve only source phases matching a retained candidate word, position and layout."""
    # Only source phases of retained candidate glyphs can contribute to a
    # completion sweep. Most frame effects have no surviving matching anchor;
    # avoid reparsing their font and layout state just to discard them later.
    needed = {_karaoke_completion_identity(e,visible_map[e.source_index]) for row in candidates for e in row}
    wanted = {}
    for key in needed:
        wanted.setdefault((key[0],key[1],key[-2]),set()).add(key[-1])
    sources = {}
    for original in source_events.values():
        if original.kind != 'Dialogue':
            continue
        pos = get_pos(original.text)
        words = wanted.get((original.style,original.name,pos))
        if words is None:
            continue
        word = simplify_text(original.text,visible_only=True)[1]
        if word not in words:
            continue
        evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
        state = evaluated.formatting
        e = dataclass_replace(original,state=state,continuation=evaluated.continuation)
        key = _karaoke_completion_identity(e,word)
        if key in needed:
            sources.setdefault(key,[]).append(e)
    return sources


def _karaoke_completion_source_phases(e: Event, visible_map: dict[int,str], source_events: dict[int,Event], sources: dict) -> list[Event] | None:
    """Select and prove cue coverage with the same 11 ms endpoint/touching tolerance."""
    phases = sorted((p for p in sources.get(_karaoke_completion_identity(e,visible_map[e.source_index]),[])
                     if p.start_s >= _karaoke_completion_cue_start(e,source_events)-.011 and p.end_s <= e.end_s+.011),
                    key=lambda p:(p.start_s,p.end_s))
    if (not phases or abs(phases[0].start_s-_karaoke_completion_cue_start(e,source_events)) > .011 or
            abs(phases[-1].end_s-e.end_s) > .011 or
            any(abs(a.end_s-b.start_s) > .011 for a,b in zip(phases,phases[1:]))):
        return None
    return phases


def _profile_karaoke_completion_source_phase(p: Event) -> KaraokeCompletionSourcePhase | None:
    """Admit an opaque unrotated hold or one supported transform changing the primary colour."""
    state = p.state
    if (inline_layout_key(p) or state.get('1a',0) != 0 or
            state.get('3a',0) != 0 or not unrotated_text_state(state) or
            state.get('p',0) or any(k in state for k in ('clip','iclip','org'))):
        return None
    tokens = event_override_tokens(p)
    transforms = [(tag,value) for tag,value in tokens if tag == 't']
    if not transforms:
        return KaraokeCompletionSourcePhase((_karaoke_completion_paint(state),p.start_s,p.end_s),None)
    if len(transforms) != 1:
        return None
    transform = parse_effect_transform(transforms[0][1],p.duration,
        {'c','1c','3c','bord','xbord','ybord','blur','be'})
    if transform is None:
        return None
    begin,end,changes = transform
    final = state.copy()
    final_continuation = p.continuation
    for tag,value in changes:
        final_continuation = apply_override(final,tag,value,p.styles,p.defaults,final_continuation)
    if final.get('1c') == state.get('1c'):
        return None
    return KaraokeCompletionSourcePhase(None,(_karaoke_completion_paint(state),_karaoke_completion_paint(final),
                                            p.start_s+begin/1000,p.start_s+end/1000,final))


def _prove_karaoke_completion_transition(phases: list[Event]) -> KaraokeCompletionProfile | None:
    """Require one transition, compatible surrounding paint holds and record completed visibility."""
    transitions,holds = [],[]
    for p in phases:
        phase = _profile_karaoke_completion_source_phase(p)
        if phase is None:
            return None
        if phase.hold is not None:
            holds.append(phase.hold)
        else:
            transitions.append(phase.transition)
    if len(transitions) != 1:
        return None
    before,after,begin,end,final = transitions[0]
    if any(not (value == before and finish <= begin+.011 or
                value == after and start >= end-.051)
           for value,start,finish in holds):
        return None
    completed = any(value == after and finish-start >= .02
                    for value,start,finish in holds)
    return KaraokeCompletionProfile(before,after,begin,end,final,completed)


def _match_karaoke_completion_profiles(row: list[Event], visible_map: dict[int,str], source_events: dict[int,Event], sources: dict) -> list[KaraokeCompletionProfile] | None:
    """Require complete source timing and one valid colour-transition profile for every fragment."""
    profiles = []
    for e in row:
        phases = _karaoke_completion_source_phases(e,visible_map,source_events,sources)
        if phases is None:
            return None
        profile = _prove_karaoke_completion_transition(phases)
        if profile is None:
            return None
        profiles.append(profile)
    return profiles


def _prove_ordered_karaoke_completion_sweep(profiles: list[KaraokeCompletionProfile]) -> bool:
    """Require one shared paint pair, distinct activation, monotonic starts/ends and a completed hold."""
    begins = [p.begin for p in profiles]
    ends = [p.end for p in profiles]
    ordered = lambda values: (all(a <= b for a,b in zip(values,values[1:])) or
                              all(a >= b for a,b in zip(values,values[1:])))
    if (len({(p.before,p.after) for p in profiles}) != 1 or len(set(begins)) < 2 or
            not ordered(begins) or not ordered(ends) or
            not any(p.completed for p in profiles)):
        return False
    return True


def _replace_karaoke_completion_paint(row: list[Event], profiles: list[KaraokeCompletionProfile], replacements: dict[int,Event]) -> None:
    """Append the proven destination paint to retained text without changing geometry or lifetimes."""
    final = profiles[0].final
    tags = ''.join(render_tag(k,final[k]) for k in ('1c','3c','bord','xbord','ybord')
                   if k in final)
    for e in row:
        index = e.text.find('}') if e.text.startswith('{') else -1
        text = (e.text[:index]+tags+e.text[index:] if index >= 0 else
                '{'+tags+'}'+e.text)
        replacements[e.source_index] = replace_event(e,text=text)


def normalize_karaoke_completion_paint(events: list[Event],
                                        visible_map: dict[int,str],
                                        source_events: dict[int,Event], *,
                                        outline_profiles: dict[int,KaraokeCompletionProfile] | None = None) -> list[Event]:
    """Use the shared destination of a proven one-way syllable colour sweep.

    Every fragment must have one transition between the same two paints,
    covering the retained cue without reversals or competing copies. Ordered
    activation and a visible completed hold distinguish a karaoke sweep from
    independent colour changes. Static gradients and cyclic highlights retain
    the ordinary per-fragment dwell selection. Optional strip profiles are
    borrowed pass-local evidence collected before copies were discarded; this
    route requires a complete row and shares the existing sweep/replacement proof.
    """
    rows = _index_retained_karaoke_completion_rows(events,visible_map,source_events)
    candidates = _select_karaoke_completion_rows(rows,visible_map)
    if not candidates:
        return events
    sources = (_index_karaoke_completion_sources(candidates,visible_map,source_events)
               if outline_profiles is None else None)
    replacements = {}
    for row in candidates:
        if outline_profiles is None:
            profiles = _match_karaoke_completion_profiles(row,visible_map,source_events,sources)
        elif all(e.source_index in outline_profiles for e in row):
            profiles = [outline_profiles[e.source_index] for e in row]
        else:
            continue
        if profiles is None or not _prove_ordered_karaoke_completion_sweep(profiles):
            continue
        _replace_karaoke_completion_paint(row,profiles,replacements)
    return [replacements.get(e.source_index,e) for e in events]
