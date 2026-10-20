"""Bounded complete-line jitter proof and owned caption construction."""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

from .event_model import Event
from .event_operations import replace_event, state_key
from .frame_pose import _preserve_frame_pose_support, _representative_frame_pose
from .static_objects import static_object_key
from .caption_geometry import get_pos, inline_layout_key, text_height, text_layout_key
from .caption_rendering import _source_caption_paint, render_simplified_caption
from .subtitle_document import format_time
from .static_selection import unrotated_text_state, select_static_state


@dataclass(frozen=True)
class JitterTextFamily:
    """One complete, uniformly painted frame sequence and its readable hold."""
    members: tuple[Event,...]
    holds: tuple[Event,...]
    start_s: float
    end_s: float
    anchor: tuple[float,float]


def _index_complete_line_jitter(events: list[Event], visible_map: dict[int,str],
                                 styles: dict, max_piece_duration: float,
                                 source_events: dict[int,Event] | None) -> dict:
    """Index static literal frames by exact text/layout, independently of paint."""
    buckets = {}
    for e in events:
        literal = visible_map.get(e.source_index,'')
        if (e.kind != 'Dialogue' or len(literal.strip()) < 2 or
                e.duration <= 0 or e.duration > max_piece_duration+1e-6 or
                get_pos(e.text) is None or inline_layout_key(e) or
                not e.layer.lstrip('-').isdigit()):
            continue
        if source_events is not None:
            original = source_events.get(e.source_index)
            original_object = (static_object_key(original,styles) if original is not None else None)
            if (original is None or inline_layout_key(original) or original_object is None or
                    len(original_object[-1]) != 1 or original_object[-1][0][1] or
                    original_object[-1][0][2] != literal or
                    original.start_s != e.start_s or original.end_s != e.end_s or
                    any(k in original.state for k in ('clip','iclip','org')) or
                    not unrotated_text_state(original.state)):
                continue
        obj = static_object_key(e,styles)
        if obj is None or len(obj[-1]) != 1:
            continue
        signature,drawing,payload = obj[-1][0]
        state = dict(signature.formatting)
        if (drawing or payload != literal or not unrotated_text_state(state) or
                any(k in state for k in ('clip','iclip','org')) or
                state.get('borderstyle',1) != 1 or
                str(state.get('fn','')).startswith('@') or
                any(not math.isfinite(state.get(k,0)) or state.get(k,0) <= 0
                    for k in ('fs','fscx','fscy')) or
                not math.isfinite(text_height(e)) or text_height(e) <= 0 or
                any(not math.isfinite(v) for v in get_pos(e.text))):
            continue
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
               e.measurement,literal,text_layout_key(e))
        buckets.setdefault(key,{}).setdefault(e.layer,[]).append(e)
    return buckets


def _prove_complete_line_jitter(members: list[Event],
                                 max_piece_duration: float) -> JitterTextFamily | None:
    """Require repeated bounded reversals and a sustained readable paint core.

    A whole-family box, rather than pairwise distance, prevents small steps
    from swallowing travelling text. Fade-only echoes have no sustained core.
    """
    if len(members) < 8:
        return None
    ordered = sorted(members,key=lambda e:(e.start_s,e.end_s,e.source_index))
    if any(a.end_s != b.start_s for a,b in zip(ordered,ordered[1:])):
        return None  # One sample per frame; overlapping copies need separate proof.
    positions = [get_pos(e.text) for e in ordered]
    height = min(text_height(e) for e in ordered)
    if any(max(p[i] for p in positions)-min(p[i] for p in positions) > .05*height+1e-6
           for i in (0,1)):
        return None
    reversals = 0
    for axis in (0,1):
        signs = [1 if b[axis] > a[axis] else -1
                 for a,b in zip(positions,positions[1:])
                 if abs(b[axis]-a[axis]) > .001*height]
        reversals = max(reversals,sum(a != b for a,b in zip(signs,signs[1:])))
    if reversals < 2:
        return None
    # Consecutive equal effective paint, including alpha, supplies the core.
    # Geometry remains exact through the bucket key; only position is jitter.
    paint = lambda e: state_key(e,{'pos'})
    runs = []
    for e in ordered:
        if e.state.get('1a',255) >= 128:
            continue
        if runs and runs[-1][-1].end_s == e.start_s and paint(runs[-1][-1]) == paint(e):
            runs[-1].append(e)
        else:
            runs.append([e])
    holds = [e for run in runs if run[-1].end_s-run[0].start_s >= 2*max_piece_duration-1e-6
             for e in run]
    if not holds:
        return None
    anchor = tuple(statistics.median(get_pos(e.text)[i] for e in holds) for i in (0,1))
    return JitterTextFamily(tuple(ordered),tuple(holds),ordered[0].start_s,ordered[-1].end_s,anchor)


def _complete_line_jitter_families(layers: dict,
                                   max_piece_duration: float) -> list[JitterTextFamily]:
    """Preserve every gap and reject a whole temporal component on proof failure."""
    families = []
    for events in layers.values():
        components = []
        for e in sorted(events,key=lambda e:(e.start_s,e.end_s,e.source_index)):
            if not components or e.start_s > components[-1][-1].end_s+1e-6:
                components.append([])
            components[-1].append(e)
        for component in components:
            proof = _prove_complete_line_jitter(component,max_piece_duration)
            if proof is not None:
                families.append(proof)
    return families


def _complete_line_jitter_core_overlap(a: JitterTextFamily, b: JitterTextFamily) -> float:
    """Measure actual readable coverage without bridging an internal fade gap."""
    i = j = 0
    overlap = 0.0
    while i < len(a.holds) and j < len(b.holds):
        x,y = a.holds[i],b.holds[j]
        overlap += max(0,min(x.end_s,y.end_s)-max(x.start_s,y.start_s))
        if x.end_s <= y.end_s:
            i += 1
        else:
            j += 1
    return overlap


def _group_complete_line_jitter_stacks(families: list[JitterTextFamily],
                                       max_piece_duration: float) -> list[list[JitterTextFamily]]:
    """Own staggered layers over a continuous complete-caption witness.

    A foreground can briefly disappear while its full-caption backing remains.
    Such gaps do not split the caption; a gap in every layer always does.
    Reject overlapping copies within a layer and unrelated partial overlays.
    """
    components = []
    for family in sorted(families,key=lambda f:(f.start_s,f.end_s)):
        matching = [group for group in components if any(
            family.start_s < peer.end_s and peer.start_s < family.end_s and
            max(abs(family.anchor[i]-peer.anchor[i]) for i in (0,1)) <=
                .05*min(text_height(family.members[0]),text_height(peer.members[0]))+1e-6
            for peer in group)]
        if len(matching) == 1:
            matching[0].append(family)
        else:
            components.append([family])
    groups = []
    for component in components:
        start,end = min(f.start_s for f in component),max(f.end_s for f in component)
        witness = next((f for f in component if f.start_s == start and f.end_s == end),None)
        layers = {}
        for f in component:
            layers.setdefault(f.members[0].layer,[]).append(f)
        valid = witness is not None
        for peers in layers.values():
            peers.sort(key=lambda f:f.start_s)
            core = sum(e.duration for f in peers for e in f.holds)
            valid &= (all(a.end_s <= b.start_s for a,b in zip(peers,peers[1:])) and
                      peers[0].start_s-start <= max_piece_duration+1e-6 and
                      end-peers[-1].end_s <= max_piece_duration+1e-6 and
                      core >= .8*(end-start)-.011)
        if witness is not None:
            height = min(text_height(f.members[0]) for f in component)
            valid &= all(max(abs(f.anchor[i]-witness.anchor[i]) for i in (0,1)) <= .05*height+1e-6 and
                _complete_line_jitter_core_overlap(f,witness) >=
                .8*min(sum(e.duration for e in f.holds),
                       sum(e.duration for e in witness.holds))-.011
                for f in component)
        groups.extend([component] if valid else [[f] for f in component])
    return groups


def _render_complete_line_jitter(group: list[JitterTextFamily], literal: str,
                                  styles: dict) -> Event:
    """Use the actual foreground layer's sustained paint and representative pose."""
    foreground = max(group,key=lambda f:(int(f.members[0].layer),f.members[0].source_index))
    holds = [e for f in group if f.members[0].layer == foreground.members[0].layer for e in f.holds]
    chosen,intervals = _representative_frame_pose(holds)
    state = select_static_state(chosen.state,[],set(),styles,chosen.defaults,
        paint_events=holds,continuation=chosen.continuation).state
    members = [e for f in group for e in f.members]
    text = render_simplified_caption(state,literal,outline_states=[e.state for e in members],
                                     measurement=chosen.measurement,
                                     source_paint=_source_caption_paint(state,[e.state for e in members]))
    start,end = min(f.start_s for f in group),max(f.end_s for f in group)
    caption = replace_event(chosen,text=text,start=format_time(start),end=format_time(end),
        start_s=start,end_s=end,source_index=min(e.source_index for e in members),effect='')
    return _preserve_frame_pose_support(chosen,caption,holds)


@dataclass(frozen=True)
class CompleteLineJitterResult:
    """Accepted captions explicitly own subsequent word-echo proofs."""
    events: list[Event]
    frames: int
    stacks: int
    captions: tuple[Event,...]


def flatten_complete_line_jitter(events: list[Event], visible_map: dict[int,str],
                                  styles: dict, *, max_piece_duration: float = .16,
                                  source_events: dict[int,Event] | None = None
                                  ) -> CompleteLineJitterResult:
    """Freeze complete explicit-frame jitter, then consolidate its proved paint layers.

    Uniform static frames only: inline gradients and other incomplete evidence
    fall through to the existing pipeline. No animation tag or exact font is
    required to prove that the same literal caption remains at the same anchor.
    Ownership is local and atomic; unrelated translucent text is untouched.
    """
    buckets = _index_complete_line_jitter(events,visible_map,styles,max_piece_duration,source_events)
    replacements,removed = {},set()
    frame_count = stack_count = 0
    for key,layers in buckets.items():
        families = _complete_line_jitter_families(layers,max_piece_duration)
        for group in _group_complete_line_jitter_stacks(families,max_piece_duration):
            caption = _render_complete_line_jitter(group,key[-2],styles)
            replacements[caption.source_index] = caption
            removed.update(e.source_index for f in group for e in f.members)
            frame_count += sum(len(f.members)-1 for f in group)
            stack_count += len(group)-1
    return CompleteLineJitterResult([replacements.get(e.source_index,e) for e in events
             if e.source_index not in removed or e.source_index in replacements],
            frame_count,stack_count,tuple(replacements.values()))
