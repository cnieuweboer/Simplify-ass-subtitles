"""Frame-sequence freezing with independent source-pose and visible-paint selection.

Callers retain admission, inline-paint proofs, stage order and report aggregation.
"""
from __future__ import annotations

import math
import re
from dataclasses import replace as dataclass_replace

from .ass_overrides import OVERRIDE_RE
from .lyric_boundaries import LyricBoundaryIndex, _crosses_lyric_boundary
from .event_model import Event
from .event_operations import replace_event, state_key
from .frame_pose import _frame_paint_alphas, _representative_frame_pose
from .static_objects import geometry_key, static_object_key
from .caption_geometry import get_pos, inline_layout_key, text_height, placement_key
from .caption_rendering import render_tag


def _frame_sequence_paint_owner(events: list[Event]) -> Event:
    """Keep the frame freezer's visible-paint rule independent of source pose."""
    paint = {id(e):_frame_paint_alphas(e) for e in events}
    channel = next((c for c in range(3) if any(a[c]<254 for a in paint.values())),0)
    return min(events,key=lambda e:(paint[id(e)][channel],-e.duration,e.source_index))


def _near_static_frame_fits(reference: Event, candidate: Event, *, allow_inline: bool = False) -> bool:
    """Bound jitter against one source anchor; never follow cumulative drift."""
    pose = {'pos','fscx','fscy','frz'}
    position,pos = get_pos(reference.text),get_pos(candidate.text)
    sx,sy = reference.state.get('fscx',100),reference.state.get('fscy',100)
    if (position is None or pos is None or sx<=0 or sy<=0 or
            reference.state.get('p',0) or (not allow_inline and (inline_layout_key(reference) or
            inline_layout_key(candidate))) or state_key(reference,pose)!=state_key(candidate,pose)):
        return False
    height = text_height(reference)
    width = abs(reference.state.get('fs',20)*sx/100)*max(1,len(OVERRIDE_RE.sub('',reference.text)))
    radius = math.dist(pos,candidate.state.get('org',pos))+math.hypot(width,height)
    angle = math.radians(math.remainder(candidate.state.get('frz',0)-reference.state.get('frz',0),360))
    error = (math.dist(pos,position)+abs(candidate.state.get('fscx',100)-sx)/sx*width+
             abs(candidate.state.get('fscy',100)-sy)/sy*height+2*radius*abs(math.sin(angle/2)))
    return error<=.02*height


def freeze_vector_sequences(events: list[Event], short_duration: float = 0.16,
                            max_gap: float = 0.011,
                            near_static: bool = False, *,
                            inline_paint_sources: frozenset[int] = frozenset(),
                            lyric_boundaries: LyricBoundaryIndex | None = None) -> tuple[list[Event], int]:
    """Freeze frame-by-frame drawings, including their longer static hold.

    Match actual paths and static paint, not style names or colors specific
    to a show. Overlapping copies are ambiguous and remain separate.
    inline_paint_sources is a pass-local producer proof: those source identities
    have uniform resolved geometry and settled per-literal paint. Descendants
    retain a contributing identity; ordinary inline guards stay unchanged.
    """
    frame_removed=0
    if near_static:
        # First retain the established treatment of actual moving frames.
        # Its frozen holds can then be joined when only tracking jitter differs.
        events,frame_removed=freeze_vector_sequences(events,short_duration,max_gap,
                                                     inline_paint_sources=inline_paint_sources,
                                                     lyric_boundaries=lyric_boundaries)
    changing = {"pos","fscx","fscy","frz","frx","fry","fax","fay",
                "1a","2a","3a","4a"}
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        placement=placement_key(e)
        if e.source_index in inline_paint_sources and inline_layout_key(e):
            # The producer proved uniform geometry separately from span paint.
            # Match every settled paint range; raw inline tag spelling must not
            # block the existing motion proof. No general inline guard is relaxed.
            obj=static_object_key(e,e.styles,allow_unpositioned=True)
            pose={'pos','fscx','fscy','frz','frx','fry','fax','fay'}
            ranges=tuple((tuple((k,v) for k,v in sig.formatting if k not in pose),drawing,literal)
                         for sig,drawing,literal in obj[-1])
            placement=placement[:-1]+(('proved-span-paint',ranges),)
        key = (e.kind,e.layer,e.name,geometry_key(e.text),state_key(e,changing),placement)
        groups.setdefault(key,[]).append(e)

    output: list[Event] = []
    removed = frame_removed

    def emit(run: list[Event], settled: bool = False) -> None:
        nonlocal removed
        if (len(run) < 2 or not settled and
                (len(run) < 3 or
                 sum(e.duration <= short_duration + 1e-6 for e in run) < 2 or
                 len({e.text for e in run}) < 2)
                or any(b.start_s < a.end_s - 1e-6 for a, b in zip(run, run[1:]))):
            output.extend(run)
            return
        chosen,intervals = _representative_frame_pose(run)
        if settled and not all(_near_static_frame_fits(chosen,e,
                allow_inline=chosen.source_index in inline_paint_sources and e.source_index in inline_paint_sources) for e in run):
            # The fixed admission anchor prevents drift. The actual selected
            # pose must independently meet the same final displacement bound.
            output.extend(run)
            return
        paint_owner = _frame_sequence_paint_owner(run)
        if not inline_layout_key(chosen):
            # These frames already share static paint except alpha. Retain the
            # established unfaded paint without giving its pose extra dwell.
            alpha_tags = ''.join(render_tag(k,paint_owner.state.get(k,0))
                for k in ('1a','2a','3a','4a')
                if chosen.state.get(k,0)!=paint_owner.state.get(k,0))
            if alpha_tags:
                prefix = re.match(r'(?:\{[^}]*\})*',chosen.text).end()
                chosen = replace_event(chosen,text=chosen.text[:prefix]+'{'+alpha_tags+'}'+chosen.text[prefix:])
        output.append(replace_event(chosen, start=run[0].start, start_s=run[0].start_s,
                              end=run[-1].end, end_s=run[-1].end_s,
                              source_index=min(e.source_index for e in run),
                              evidence=dataclass_replace(chosen.evidence,frame_pose_intervals=intervals)))
        removed += len(run) - 1

    for group in groups.values():
        ordered = sorted(group, key=lambda e: (e.start_s, e.end_s, e.source_index))
        # Build time-connected components first so simultaneous identical
        # shapes cannot accidentally be connected to one another's frames.
        components: list[list[Event]] = []
        latest_end = -1.0
        for e in ordered:
            if (not components or e.start_s > latest_end + max_gap + 1e-6 or
                    lyric_boundaries is not None and
                    _crosses_lyric_boundary(lyric_boundaries,components[-1][-1],e,complete_only=True)):
                components.append([])
                latest_end = e.end_s
            components[-1].append(e)
            latest_end = max(latest_end, e.end_s)
        for component in components:
            if any(b.start_s < a.end_s - 1e-6 for a, b in zip(component, component[1:])):
                output.extend(component)
                continue
            if near_static:
                # A tracked sign may jump between several stable placements.
                # Merge bounded jitter within each hold, without requiring the
                # entire time-connected component to have one static pose.
                run=[]
                reference=None
                for candidate in component:
                    settled=(bool(run) and abs(candidate.start_s-run[-1].end_s)<=1e-6 and
                             _near_static_frame_fits(reference,candidate,
                                allow_inline=reference.source_index in inline_paint_sources and candidate.source_index in inline_paint_sources))
                    if run and not settled:
                        emit(run,True)
                        run=[]
                    if not run:
                        reference=candidate
                    run.append(candidate)
                emit(run,True)
                continue
            run: list[Event] = []
            has_hold = False
            for e in component:
                is_hold = e.duration > short_duration + 1e-6
                if is_hold and has_hold:
                    emit(run)
                    run, has_hold = [], False
                run.append(e)
                has_hold |= is_hold
            emit(run)
    return sorted(output, key=lambda e: e.source_index), removed

