"""Original surrounding-lyric signatures shared by glyph and sequence reducers.

Callers choose capture timing and evidence lifetime. Consumers borrow the index;
construction owns fresh signature maps and does not edit source events.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

from .caption_geometry import get_pos
from .event_model import Event


@dataclass(frozen=True)
class LyricBoundaryIndex:
    """Original surrounding-row signatures, borrowed through fragment reduction.

    This pass-local evidence survives glyph joins without claiming a new source
    lifetime. It expires after sequence merging and does not cross serialization.
    """
    starts: dict[tuple, set[tuple]]
    ends: dict[tuple, set[tuple]]
    touching: frozenset[tuple]
    caption_handoffs: frozenset[tuple]



def _index_lyric_boundaries(events: list[Event], visible_map: dict[int,str], *,
                            phase_groups: dict[int,int] | None = None) -> LyricBoundaryIndex:
    """Capture changes in the complete surrounding lyric before reducing pieces."""
    starts: dict[tuple, set[tuple]] = {}
    ends: dict[tuple, set[tuple]] = {}
    caption_starts: dict[tuple,set[tuple]] = {}
    caption_ends: dict[tuple,set[tuple]] = {}
    intervals: dict[tuple,list[tuple[float,float]]] = {}
    lyric_lanes = {(e.style,e.name,e.row) for e in events
                  if e.kind == 'Dialogue' and get_pos(e.text) is not None and
                  (e.lyric if phase_groups is None else e.source_index in phase_groups)}
    for e in events:
        pos = get_pos(e.text)
        row = (e.style, e.name, e.layer, e.row)
        lane = (e.style,e.name,e.row)
        # Eligibility limits edits, not neighboring context. An ordinary
        # single-plane next cue can still end an established lyric family.
        if e.kind != 'Dialogue' or pos is None or lane not in lyric_lanes:
            continue
        intervals.setdefault(lane,[]).append((e.start_s,e.end_s))
        glyph = (round(pos[0] / e.unit, 1) * e.unit, visible_map.get(e.source_index,''))
        caption_starts.setdefault((*lane, round(e.start_s, 2)), set()).add(glyph)
        caption_ends.setdefault((*lane, round(e.end_s, 2)), set()).add(glyph)
        admitted = e.lyric if phase_groups is None else e.source_index in phase_groups
        if admitted:
            starts.setdefault((*row, round(e.start_s, 2)), set()).add(glyph)
            ends.setdefault((*row, round(e.end_s, 2)), set()).add(glyph)
    touching = frozenset(key for key in starts.keys() & ends.keys()
                         if starts[key] != ends[key])
    handoffs = set()
    def literal(signature):
        return ''.join(''.join(word.split()) for x,word in sorted(signature))
    caption_changes = {key for key in caption_starts.keys() & caption_ends.keys()
                       if literal(caption_starts[key]) != literal(caption_ends[key])}
    for row,spans in intervals.items():
        # A complete row changes together. An ongoing letter means that a
        # touching subset may just be another staggered phase of the same cue.
        # Prefix maxima answer this without rescanning the row per boundary.
        ordered = sorted(spans)
        times = [a for a,b in ordered]
        maximum_ends = []
        for a,b in ordered:
            maximum_ends.append(max(b,maximum_ends[-1] if maximum_ends else b))
        for key in caption_changes:
            if key[:-1] != row or len(caption_starts[key])<2 or len(caption_ends[key])<2:
                continue
            at = key[-1]
            previous = bisect_left(times,at-1e-6)-1
            if previous>=0 and maximum_ends[previous]<=at+1e-6:
                handoffs.add(key)
    return LyricBoundaryIndex(starts,ends,touching,frozenset(handoffs))



def _crosses_lyric_boundary(index: LyricBoundaryIndex, current: Event, e: Event, *,
                             complete_only: bool = False) -> bool:
    """Keep repeated letters separate at touching or briefly overlapping lyrics."""
    row = (e.style,e.name,e.layer,e.row)
    boundary = (*row,round(e.start_s,2))
    if complete_only:
        # Later mergers reduce styling/frame sequences, including legitimate
        # staggered glyph changes. Only a complete caption handoff owns a veto.
        return ((current.style,current.name,current.row)==(e.style,e.name,e.row) and
                abs(e.start_s-current.end_s)<=.011 and
                (e.style,e.name,e.row,round(e.start_s,2)) in index.caption_handoffs)
    ending = index.ends.get((*row,round(current.end_s,2)),set())
    beginning = index.starts.get(boundary,set())
    changed_row = (e.start_s > current.start_s and e.end_s > current.end_s and
                   len(ending)>1 and len(beginning)>1 and ending != beginning and
                   current.end_s-e.start_s <= .2*min(current.duration,e.duration))
    return changed_row or (abs(e.start_s-current.end_s)<=.011 and boundary in index.touching)
