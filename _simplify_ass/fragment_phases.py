"""Complete fragment-phase row proof, ownership and protected timing handoff."""
from __future__ import annotations

import statistics
import unicodedata
from dataclasses import dataclass
from typing import Mapping

from .caption_geometry import (
    get_pos, inline_layout_key, placement_key, text_height, text_layout_key,
)
from .caption_rendering import (
    _source_caption_paint, render_merged_caption, render_simplified_caption,
)
from .effect_validation import opaque_text_effect_state
from .event_model import Event
from .event_operations import replace_event, state_key
from .font_metrics import FontMetrics
from .font_reporting import FontProcessingReport
from .glyph_placement import fit_fragment_anchor
from .row_evidence import TextRow, TextPhaseRowsResult
from .row_fitting import recover_font_row
from .static_objects import static_object_key
from .static_selection import unrotated_text_state
from .subtitle_document import format_time


@dataclass(frozen=True)
class FragmentPhaseContext:
    """Private eligible fragments, touching phase indexes and font metric for one pass."""
    eligible: list[Event]
    words: dict[int,str]
    geometry: dict[int,tuple]
    positions: dict[int,tuple[float,float]]
    endings: dict[tuple,list[Event]]
    anchored_starts: dict[tuple,list[Event]]
    anchored_ends: dict[tuple,list[Event]]
    metric: FontMetrics
    font_report: FontProcessingReport | None = None


@dataclass(frozen=True)
class FragmentPhaseProfile:
    """A proved fragment-to-word chain and its authored activation boundaries."""
    caption_sample: Event
    members: list[Event]
    start_s: float
    activation_s: float
    terminal_start_s: float
    joined_fragments: bool


def _index_fragment_phase_rows(
    events: list[Event], visible_map: Mapping[int, str], metric: FontMetrics, *,
    font_report: FontProcessingReport | None=None,
) -> FragmentPhaseContext:
    """Index eligible stationary fragments and exact touching phase boundaries."""
    eligible, words, geometry, positions = [], {}, {}, {}
    for e in events:
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or not word or pos is None or e.duration <= 0 or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word) or
                inline_layout_key(e) or not opaque_text_effect_state(e.state) or
                not unrotated_text_state(e.state) or
                static_object_key(e,e.styles) is None):
            continue
        # Vertical exit compression does not change horizontal glyph anchors.
        # A matched earlier completed phase supplies its readable height.
        key = (e.style,placement_key(e),tuple((k,v) for k,v in text_layout_key(e)
                                             if k != 'fscy'),round(pos[1],4))
        eligible.append(e)
        words[e.source_index],geometry[e.source_index],positions[e.source_index] = word,key,pos
    endings, anchored_starts, anchored_ends = {}, {}, {}
    for e in eligible:
        key = geometry[e.source_index]
        endings.setdefault((key,round(e.end_s,2)),[]).append(e)
        anchor = (key,positions[e.source_index],words[e.source_index])
        anchored_starts.setdefault((*anchor,round(e.start_s,2)),[]).append(e)
        anchored_ends.setdefault((*anchor,round(e.end_s,2)),[]).append(e)
    for group in endings.values():
        group.sort(key=lambda e:positions[e.source_index][0])
    # Lookup is local to a centisecond phase boundary, rather than comparing
    # every event with every other event in a font/row family.
    return FragmentPhaseContext(eligible,words,geometry,positions,
                                endings,anchored_starts,anchored_ends,metric, font_report=font_report)


def _previous_fragment_phases(context: FragmentPhaseContext, e: Event) -> list[Event]:
    """Find same-word and same-anchor predecessors at an exact phase boundary."""
    key = (context.geometry[e.source_index],context.positions[e.source_index],context.words[e.source_index],round(e.start_s,2))
    return [p for p in context.anchored_ends.get(key,[])
            if abs(p.end_s-e.start_s) <= .001]


def _match_fragment_phase_join(context: FragmentPhaseContext, tail: Event,
                                current: Event) -> list[list[Event]]:
    """Prove fragment joins using literal order, compatible paint and exact-font anchors."""
    word = context.words[tail.source_index]
    peers = (context.endings.get((context.geometry[tail.source_index],round(current.start_s,2)),[])
             if len(word) > 1 else [])
    matches = []
    for offset,p in enumerate(peers):
        if not word.startswith(context.words[p.source_index]):
            continue
        pieces, text = [],''
        for index in range(offset,len(peers)):
            p = peers[index]
            if abs(p.end_s-current.start_s) > .001:
                break
            pieces.append(p)
            text += context.words[p.source_index]
            if not word.startswith(text):
                break
            if text == word:
                xs = [context.positions[p.source_index][0] for p in pieces]
                if len(pieces) > 1 and (any(b <= a for a,b in zip(xs,xs[1:])) or
                        len({state_key(p,{'pos'}) for p in pieces}) != 1):
                    break
                anchor = fit_fragment_anchor(context.metric, tail.state,xs,
                    [context.words[p.source_index] for p in pieces],word,tail.unit,exact_size=True)
                if anchor is not None and abs(anchor-context.positions[tail.source_index][0]) <= .25*tail.unit:
                    matches.append(pieces)
                break
    return matches


def _prove_fragment_phase_chain(context: FragmentPhaseContext, tail: Event) -> FragmentPhaseProfile | None:
    """Require an unambiguous touching chain and restore its earlier readable height."""
    chain, current = [tail],tail
    while True:
        peers = _previous_fragment_phases(context,current)
        if not peers:
            break
        if len(peers) != 1:
            return None
        current = peers[0]
        chain.append(current)
    word = context.words[tail.source_index]
    matches = _match_fragment_phase_join(context,tail,current)
    if len(matches) != 1:
        # Single-letter phases have already been traversed by _previous_fragment_phases().
        # They participate only alongside proven multi-fragment joins.
        if matches or len(word) != 1 or len(chain) < 2:
            return None
        pieces = [chain.pop()]
        current = chain[-1]
    else:
        pieces = matches[0]
    members = pieces+chain
    if (min(p.end_s for p in members)-max(p.start_s for p in pieces) <= .011 or
            any(p.source_index == q.source_index for i,p in enumerate(members) for q in members[:i])):
        return None
    tail = replace_event(tail,text=render_simplified_caption(
        {**tail.state,'fscy':current.state.get('fscy',100)},word,measurement=tail.measurement,
        source_paint=_source_caption_paint(tail.state,[tail.state])))
    return FragmentPhaseProfile(tail,members,min(p.start_s for p in pieces),current.start_s,
            tail.start_s,len(pieces) > 1)


def _collect_fragment_phase_families(context: FragmentPhaseContext) -> dict:
    """Group terminal phases by layout and paint, retaining failed proofs as blockers."""
    families = {}
    for e in context.eligible:
        paint = tuple(e.state.get(k,e.defaults.get(k,0)) for k in
                      ('1c','3c','4c','1a','3a','4a','bord','xbord','ybord',
                       'shad','xshad','yshad','blur','be'))
        key = (context.geometry[e.source_index],e.layer,paint)
        anchor = (context.geometry[e.source_index],context.positions[e.source_index],context.words[e.source_index],round(e.end_s,2))
        successors = [p for p in context.anchored_starts.get(anchor,[])
                      if abs(e.end_s-p.start_s) <= .001]
        if not successors:
            families.setdefault(key,[]).append((e,_prove_fragment_phase_chain(context,e)))
    return families


def _group_fragment_phase_cues(context: FragmentPhaseContext, family: list,
                                direction: int) -> list:
    """Split ordered activations by horizontal direction and shared lifetime."""
    sequence, cues = [],[]
    for e,p in sorted(family,key=lambda pair:((pair[1].activation_s if pair[1] else pair[0].start_s),
                                            direction*context.positions[pair[0].source_index][0])):
        start = p.start_s if p else e.start_s
        if sequence and (direction*(context.positions[e.source_index][0]-context.positions[sequence[-1][0].source_index][0]) <= e.unit or
                         start >= min(q.end_s for q,_ in sequence)-.011):
            cues.append(sequence);sequence=[]
        sequence.append((e,p))
    cues.append(sequence)
    return cues


def _fit_fragment_phase_cue(context: FragmentPhaseContext, cue: list) -> tuple | None:
    """Fit only complete ordered rows and preserve their protected activation core."""
    if len(cue) < 4 or any(p is None for e,p in cue) or sum(p.joined_fragments for e,p in cue) < 2:
        return None
    if (any(b[1].activation_s <= a[1].activation_s+.011 or b[1].terminal_start_s < a[1].terminal_start_s-.011
            for a,b in zip(cue,cue[1:])) or
            any(b[0].end_s < a[0].end_s-.011 for a,b in zip(cue,cue[1:]))):
        return None
    held = sorted((p.caption_sample for e,p in cue),key=lambda e:context.positions[e.source_index][0])
    if len({state_key(e,{'pos'}) for e in held}) != 1:
        return None
    fragments = [context.words[e.source_index] for e in held]
    fit = recover_font_row(context.metric, held,fragments, font_report=context.font_report)
    if fit is None:
        return None
    text,x,sx,sy,an = fit
    body = render_merged_caption(held,fragments,text,animated=False,an=an,
        pos=(x,statistics.median(context.positions[e.source_index][1] for e in held)),fscx=sx,fscy=sy)
    if body is None:
        return None
    ids = frozenset(m.source_index for e,p in cue for m in p.members)
    if len(ids) != sum(len(p.members) for e,p in cue):
        return None
    start,end = min(p.start_s for e,p in cue),max(e.end_s for e,p in cue)
    core = (min(p.activation_s for e,p in cue),max(p.activation_s for e,p in cue))
    if not start < core[0] < core[1] < end:
        return None
    first = min(held,key=lambda e:e.source_index)
    caption = replace_event(first,text=body,start=format_time(start),start_s=start,
        end=format_time(end),end_s=end,source_index=min(ids))
    row = TextRow(caption,[(e,context.words[e.source_index],context.positions[e.source_index]) for e in held],
                  phase_core=core)
    return ids,row,text


def _propose_fragment_phase_rows(context: FragmentPhaseContext, families: dict) -> list:
    """Build all row proposals before missing-fragment and ownership checks."""
    proposals = []
    for family in families.values():
        if sum(p is not None and p.joined_fragments for e,p in family) < 2:
            continue
        for direction in (1,-1):
            for cue in _group_fragment_phase_cues(context,family,direction):
                proposal = _fit_fragment_phase_cue(context,cue)
                if proposal is not None:
                    proposals.append(proposal)
    return proposals


def _filter_incomplete_fragment_rows(context: FragmentPhaseContext, proposals: list) -> list:
    """Reject rows with unmatched nearby fragments before resolving source ownership."""
    # An unmatched nearby fragment may be a missing part of this cue. Do not
    # turn a failed boundary or font match into a partial reconstructed line.
    # Other complete proposals are known neighbouring cues, not missing text.
    proposed_ids = set().union(*(ids for ids,row,text in proposals)) if proposals else set()
    blockers = {}
    for e in context.eligible:
        if e.source_index not in proposed_ids:
            key = (e.style,placement_key(e),round(context.positions[e.source_index][1],4))
            blockers.setdefault(key,[]).append(e)
    complete = []
    for ids,row,text in proposals:
        e = row.pieces[0][0]
        key = (e.style,placement_key(e),round(row.pieces[0][2][1],4))
        xs = [pos[0] for piece,word,pos in row.pieces]
        start,end = row.phase_core
        reach = 2*min(text_height(piece) for piece,word,pos in row.pieces)
        if not any(min(xs)-reach <= context.positions[p.source_index][0] <= max(xs)+reach and
                   min(end,p.end_s)-max(start,p.start_s) >= .5*min(end-start,p.duration)
                   for p in blockers.get(key,[])):
            complete.append((ids,row,text))
    return complete


def _resolve_fragment_phase_ownership(complete: list) -> list:
    """Deduplicate equivalent claims and reject every competing source owner."""
    # A phase belongs to exactly one complete caption; no greedy ownership.
    unique = {ids:(row,text) for ids,row,text in complete}
    claims = {}
    for ids in unique:
        for index in ids:
            claims[index] = claims.get(index,0)+1
    accepted = [(ids,row,text) for ids,(row,text) in unique.items()
                if all(claims[index] == 1 for index in ids)]
    return accepted


def _apply_fragment_phase_rows(context: FragmentPhaseContext, events: list[Event],
                               accepted: list) -> TextPhaseRowsResult:
    """Return accepted rows and visibility; commit the explicit font counter."""
    consumed = set().union(*(ids for ids,row,text in accepted)) if accepted else set()
    rows = [row for ids,row,text in accepted]
    visibility_updates = {}
    for ids,row,text in accepted:
        visibility_updates[row.base.source_index] = text
        if context.font_report is not None:
            context.font_report.rows_joined += 1
    output = [e for e in events if e.source_index not in consumed]+[row.base for row in rows]
    return TextPhaseRowsResult(sorted(output,key=lambda e:e.source_index),
        len(events)-len(output),rows,visibility_updates)


def collapse_fragment_phase_rows(
    events: list[Event], visible_map: Mapping[int, str], metric: FontMetrics | None, *,
    font_report: FontProcessingReport | None=None,
) -> TextPhaseRowsResult:
    """Assemble rows whose touching phases change fragment granularity.

    Exact-font anchors connect smaller fragments to the same completed word
    or syllable. Any number of same-anchor phases may follow. Ordered word
    activation and a shared terminal paint prove a complete readable row;
    event names, animation tags and particular colours are not evidence.
    Missing, competing or multiply claimed phases reject the whole cue.
    Borrow visibility and return accepted text updates with protected row
    evidence. The pipeline applies the updates before timing/reconstruction.
    """
    if metric is None or not getattr(metric,'available',False):
        return TextPhaseRowsResult(events,0,[],{})
    context = _index_fragment_phase_rows(events,visible_map,metric, font_report=font_report)
    families = _collect_fragment_phase_families(context)
    proposals = _propose_fragment_phase_rows(context,families)
    complete = _filter_incomplete_fragment_rows(context,proposals)
    accepted = _resolve_fragment_phase_ownership(complete)
    return _apply_fragment_phase_rows(context,events,accepted)
