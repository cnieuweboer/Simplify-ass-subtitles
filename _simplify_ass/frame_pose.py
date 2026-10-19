"""Source-frame exposure, representative poses and compatible support handoff.

Callers retain candidate admission, evidence capture and output paint selection.
"""
from __future__ import annotations

import collections
from dataclasses import replace as dataclass_replace
from typing import Iterable

from .event_model import Event
from .event_operations import _frame_pose_key

def _frame_paint_alphas(e: Event) -> tuple:
    """Describe actual primary, outline and shadow paint; unused channels are hidden."""
    return tuple(e.state.get(f'{c}a',0) if c == 1 or
        max(abs(e.state.get(k,e.state.get('bord' if c == 3 else 'shad',0)))
            for k in (('xbord','ybord') if c == 3 else ('xshad','yshad'))) > 0
        else 255 for c in (1,3,4))


def _frame_pose_intervals(e: Event) -> tuple:
    """Borrow source pose dwell, clipped to the surviving event's actual lifetime."""
    intervals = e.evidence.frame_pose_intervals
    if intervals is None:
        intervals = ((e.start_s,e.end_s,_frame_paint_alphas(e)),)
    return tuple((round(max(start,e.start_s),6),round(min(end,e.end_s),6),alpha)
                 for start,end,alpha in intervals
                 if min(end,e.end_s)>max(start,e.start_s))


def _visible_pose_support(intervals: Iterable[tuple], channel: int) -> list[tuple]:
    """Source exposure at maximum actual opacity; copies cannot multiply votes."""
    boundaries = {}
    for start,end,alpha in intervals:
        strength = max(0,min(255,255-alpha[channel]))
        if end <= start or not strength:
            continue
        boundaries.setdefault(start,collections.Counter())[strength] += 1
        boundaries.setdefault(end,collections.Counter())[strength] -= 1
    result,active,previous = [],collections.Counter(),None
    for at,delta in sorted(boundaries.items()):
        if previous is not None and at>previous and active:
            strength = max(active)
            if result and result[-1][1]==previous and result[-1][2]==strength:
                result[-1] = (result[-1][0],at,strength)
            else:
                result.append((previous,at,strength))
        active.update(delta);active = +active
        previous = at
    return result


def _preserve_frame_pose_support(source: Event, successor: Event,
                                 peers: Iterable[Event] | None = None) -> Event:
    """Explicitly hand off only dwell belonging to the retained literal/geometry."""
    key = _frame_pose_key(source)
    if key != _frame_pose_key(successor):
        return successor
    intervals = tuple(sorted(set(entry for e in (peers if peers is not None else [source])
        if _frame_pose_key(e)==key for entry in _frame_pose_intervals(e))))
    return dataclass_replace(successor,evidence=dataclass_replace(
        successor.evidence,frame_pose_intervals=intervals))


def _representative_frame_pose(events: list[Event]) -> tuple[Event,tuple]:
    """Choose greatest visible source exposure, then a central existing pose.

    Paint grouping, copied records, source-ID order and frame splitting cannot
    manufacture dwell. Microsecond-rounded intervals avoid floating duration
    ties deciding placement. The result is an existing pose, not averaged geometry.
    """
    families = {}
    for e in events:
        key = _frame_pose_key(e)
        peers,intervals = families.setdefault(key,([],[]))
        peers.append(e);intervals.extend(_frame_pose_intervals(e))
    all_intervals = [entry for peers,intervals in families.values() for entry in intervals]
    channel = next((c for c in range(3) if any(alpha[c]<254 for a,b,alpha in all_intervals)),0)
    current_paint = {id(e):_frame_paint_alphas(e) for e in events}
    paint_channel = next((c for c in range(3) if any(a[c]<254 for a in current_paint.values())),0)
    support = _visible_pose_support(all_intervals,channel)
    midpoint = (min(e.start_s for e in events)+max(e.end_s for e in events))/2
    half = sum((b-a)*strength for a,b,strength in support)/2
    for a,b,strength in support:
        if half <= (b-a)*strength:
            midpoint = a+half/strength;break
        half -= (b-a)*strength
    ranked = []
    for key,(peers,intervals) in families.items():
        spans = _visible_pose_support(intervals,channel)
        dwell = sum((b-a)*strength for a,b,strength in spans)
        center = sum((a+b)/2*(b-a)*strength for a,b,strength in spans)/dwell if dwell else midpoint
        first = spans[0][0] if spans else min(e.start_s for e in peers)
        # Geometry votes use source support. Among records at that exact pose,
        # retain the established visible-paint/longest-hold choice separately.
        owner = min(peers,key=lambda e:(current_paint[id(e)][paint_channel],
                                        -e.duration,e.source_index))
        contains = any(a<=midpoint<b for a,b,strength in spans)
        ranked.append(((-round(dwell,6),not contains,round(abs(center-midpoint),6),first,repr(key)),owner,tuple(intervals)))
    _,chosen,intervals = min(ranked,key=lambda item:item[0])
    return chosen,tuple(sorted(set(intervals)))
