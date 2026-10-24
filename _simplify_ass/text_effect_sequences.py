"""Complete text-effect sequence admission, selection and reconstruction.

Inputs and supplied font/report owners remain borrowed. Geometry indexes,
components and output buffers are call-local; the engine retains stage order,
result adoption and aggregate reporting.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .ass_overrides import DEFAULT_STATE, OVERRIDE_RE
from .caption_geometry import (
    get_pos, inline_layout_key, placement_key, text_height, text_layout_key,
)
from .caption_rendering import _source_caption_paint, render_simplified_caption, render_tag
from .event_model import Event
from .event_operations import _frame_pose_key, replace_event, state_key
from .font_metrics import FontMetrics
from .font_reporting import FontProcessingReport
from .frame_pose import _preserve_frame_pose_support, _representative_frame_pose
from .karaoke_completion import normalize_karaoke_completion_paint
from .lyric_boundaries import (
    LyricBoundaryIndex, _crosses_lyric_boundary, _index_lyric_boundaries,
)
from .moving_glyphs import collapse_moving_glyph_sequences
from .static_selection import select_static_state, unrotated_text_state, upright_text_state
from .subtitle_document import format_time
from .text_freezing import freeze_block


@dataclass(frozen=True)
class TextEffectSequenceContext:
    """Original pass inputs and the exact-position versus scale-trail mode."""
    visible_map: dict[int,str]
    styles: dict
    animated_sources: set[int]
    scale_trails: bool
    source_events: dict[int,Event] | None
    font_metrics: FontMetrics | None
    font_report: FontProcessingReport | None = None
    lyric_boundaries: LyricBoundaryIndex | None = None



@dataclass(frozen=True)
class TextEffectSequenceGeometry:
    """Cached positions, heights and non-scale layouts for one copy bucket."""
    positions: dict[int,tuple]
    heights: dict[int,float]
    layouts: dict[int,tuple]



@dataclass(frozen=True)
class TextEffectSequenceProfile:
    """Admitted members, visible paint samples and the complete caption interval."""
    members: list[Event]
    visible_candidates: list[Event]
    clipped: bool
    trail: bool
    start_s: float
    end_s: float



def match_scale_trail(component: list[Event], visible: str,
                      animated_sources: set[int], positions: dict[int,tuple[float,float]],
                      heights: dict[int,float], layouts: dict[int,tuple]) -> list[Event] | None:
    """Return proven members of an unclipped, drifting scale-trail candidate.

    Validate shared layout, lifetime, scale and rendered-anchor trajectories
    using the caller's cached geometry. Return None for an unproven family;
    event grouping, caption selection and replacements remain with the caller.
    """
    if (len(component) < 3 or
            sum(e.source_index in animated_sources for e in component) < 3 or
            len({layouts[e.source_index] for e in component}) != 1 or
            len({e.name for e in component}) != 1):
        return None
    trail = False
    # Three distinct scales tracing the same affine position/scale
    # path establish an effect family. A nearby main fill may use
    # a slightly different authored scale; it must sit at the
    # largest trail sample, rather than at its displaced tail.
    samples=sorted(component,key=lambda e:e.state.get("fscx",100))
    lo,hi=samples[0],samples[-1]
    # Prefer the dense trail when an opaque main fill lies off its
    # scale trajectory. It is validated separately below.
    faded=[e for e in samples if e.state.get("1a",0)>0]
    if len(faded)>=3:
        samples=faded
        lo,hi=samples[0],samples[-1]
    sample_ids={e.source_index for e in samples}
    sample_start=max(e.start_s for e in samples)
    sample_end=min(e.end_s for e in samples)
    # A short lead-in/out phase outside the trail's shared visible
    # interval is not a trail member. Keep it independently rather
    # than letting it invalidate an otherwise proven family.
    members=[e for e in component if e.source_index in sample_ids or
             min(e.end_s,sample_end)>max(e.start_s,sample_start)]
    delta=hi.state.get("fscx",100)-lo.state.get("fscx",100)
    tolerance=max(.01*heights[hi.source_index],.05*hi.unit)
    if (sample_end>sample_start and delta>1e-6 and
            len({e.state.get("fscx",100) for e in samples})>=3 and
            all(e.source_index in animated_sources for e in samples)):
        lx,ly=positions[lo.source_index]; hx,hy=positions[hi.source_index]
        sy0,sy1=lo.state.get("fscy",100),hi.state.get("fscy",100)
        trail=all(
            abs(positions[e.source_index][0]-(lx+(hx-lx)*f))<=tolerance and
            abs(positions[e.source_index][1]-(ly+(hy-ly)*f))<=tolerance and
            abs(e.state.get("fscy",100)-(sy0+(sy1-sy0)*f))<=.05
            for e in samples
            for f in [(e.state.get("fscx",100)-lo.state.get("fscx",100))/delta])
        # Assess the rendered anchors, including displacement
        # around distant origins. Fit the whole family rather than
        # measuring every rotation against one endpoint sample.
        # Authored anchors/scales must still follow the path above.
        rendered=[]
        angle=hi.state.get("frz",0)
        for e in samples:
            px,py=positions[e.source_index]
            ox,oy=e.state.get("org",(px,py))
            turn=math.radians(math.remainder(e.state.get("frz",0),360))
            dx,dy=px-ox,py-oy
            rendered.append((e.state.get("fscx",100),
                             ox+dx*math.cos(turn)+dy*math.sin(turn),
                             oy-dx*math.sin(turn)+dy*math.cos(turn)))
        mean_scale=sum(v[0] for v in rendered)/len(rendered)
        mean_x=sum(v[1] for v in rendered)/len(rendered)
        mean_y=sum(v[2] for v in rendered)/len(rendered)
        variance=sum((v[0]-mean_scale)**2 for v in rendered)
        slope_x=sum((v[0]-mean_scale)*(v[1]-mean_x)
                    for v in rendered)/variance
        slope_y=sum((v[0]-mean_scale)*(v[2]-mean_y)
                    for v in rendered)/variance
        trail &= all(math.hypot(
            x-mean_x-slope_x*(scale-mean_scale),
            y-mean_y-slope_y*(scale-mean_scale))<=.06*heights[hi.source_index]
            for scale,x,y in rendered)
        # Rotation also changes glyph orientation around its
        # rendered anchor; large turns remain unsafe even when
        # anchors happen to trace a straight line.
        reference_anchor=rendered[-1][1:]
        for e in members:
            if e.source_index not in sample_ids:
                px,py=positions[e.source_index]
                ox,oy=e.state.get("org",(px,py))
                rotation=math.radians(math.remainder(e.state.get("frz",0),360))
                dx,dy=px-ox,py-oy
                anchor=(ox+dx*math.cos(rotation)+dy*math.sin(rotation),
                        oy-dx*math.sin(rotation)+dy*math.cos(rotation))
                trail &= math.dist(anchor,reference_anchor)<=.18*heights[e.source_index]
            radius=heights[e.source_index]*max(1,len(visible))
            turn=math.radians(math.remainder(e.state.get("frz",0)-angle,360))
            trail &= 2*radius*abs(math.sin(turn/2))<=.06*heights[hi.source_index]
        trail &= all(
            abs(positions[e.source_index][0]-hx)<=.18*heights[e.source_index] and
            abs(positions[e.source_index][1]-hy)<=.18*heights[e.source_index] and
            e.state.get("fscx",100)>=hi.state.get("fscx",100) and
            e.state.get("1a",0)<=hi.state.get("1a",0)
            for e in members if e.source_index not in sample_ids)
    return members if trail else None



def upright_text_holds(candidates: list[Event], source_events: dict[int,Event]) -> list[Event]:
    """Find candidate poses actually held by the original animated text.

    A midpoint sample that merely crosses zero is insufficient. Compare the
    complete settled geometry, so a hidden or flipped pose cannot win either.
    """
    holds = []
    geometry = ('pos','org','fn','fs','fscx','fscy','fsp','an','b','i','fax','fay',
                'clip','iclip','p','pbo','q')
    for e in candidates:
        original = source_events.get(e.source_index)
        if (not upright_text_state(e.state) or original is None or
                original.duration <= 0 or inline_layout_key(original)):
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        block = ''.join(OVERRIDE_RE.findall(prefix))
        frozen = freeze_block(block,original.duration,original.defaults,original.defaults,
                              original.styles,0,prior_settled_states=())
        if any(upright_text_state(state,include_shadow=True) and
               all(state.get(k,DEFAULT_STATE.get(k)) == e.state.get(k,DEFAULT_STATE.get(k))
                   for k in geometry) for state in frozen.selection.settled_states):
            holds.append(e)
    return holds



def _prepare_text_effect_sequence_pass(events: list[Event], context: TextEffectSequenceContext
                                       ) -> tuple[list[Event],int]:
    """Complete exact-position reduction before attempting wider scale trails."""
    if not context.scale_trails:
        return events,0
    # Keep the established recursion contract: the exact-position pass does
    # not receive font metrics or repeat the wider animation pipeline.
    return flatten_text_effect_sequences(
        events,context.visible_map,context.styles,context.animated_sources,False,
        source_events=context.source_events, font_report=context.font_report,
        lyric_boundaries=context.lyric_boundaries)



def _group_text_effect_sequences(events: list[Event], context: TextEffectSequenceContext
                                 ) -> tuple[dict[tuple,list[Event]],list[Event]]:
    """Group eligible visible captions while separating original flying letters."""
    buckets, output = {}, []
    for e in events:
        visible=context.visible_map.get(e.source_index,"")
        if e.kind!="Dialogue" or not visible or get_pos(e.text) is None or e.state.get("p",0):
            output.append(e)
            continue
        key=(e.style,visible)
        if context.source_events is not None and len(visible) == 1:
            original = context.source_events.get(e.source_index)
            # A frozen flying letter can land near a different stationary
            # letter. It is not a styling phase of that neighbour's caption.
            key += (bool(original and re.search(r"\\move\s*\(",original.text,re.I)),)
        if context.scale_trails:
            key+=(e.name,tuple((k,v) for k,v in text_layout_key(e)
                              if k not in {"fscx","fscy","frz"}),placement_key(e))
        buckets.setdefault(key,[]).append(e)
    return buckets,output



def _index_text_effect_sequence_geometry(bucket: list[Event]) -> TextEffectSequenceGeometry:
    """Cache unchanged position, height and non-scale layout for one sequence bucket."""
    # Cache the geometry used while clustering. Scale trails change their
    # position and scale together, but not the font or paragraph layout.
    positions = {e.source_index: get_pos(e.text) for e in bucket}
    heights = {e.source_index: text_height(e) for e in bucket}
    layouts = {e.source_index: (tuple((k,v) for k,v in text_layout_key(e)
                                     if k not in {"fscx","fscy","frz"}), placement_key(e))
               for e in bucket}
    return TextEffectSequenceGeometry(positions,heights,layouts)



def _text_effect_sequence_neighbor(context: TextEffectSequenceContext,
                                   geometry: TextEffectSequenceGeometry, e: Event, pos: tuple,
                                   component: list[Event], reference: Event) -> bool:
    """Check connected timing, fade handoffs, scale allowance and authored margins."""
    previous=component[-1]
    if (context.lyric_boundaries is not None and
            any(_crosses_lyric_boundary(context.lyric_boundaries,member,e,complete_only=True) for member in component)):
        return False
    span_start = min(x.start_s for x in component)
    span_end = max(x.end_s for x in component)
    if e.start_s > span_end+1e-6:
        return False
    # Brief fade overlaps between consecutive captions must not
    # link their repeated letters into one long styling sequence.
    # Nested highlight phases remain eligible; genuinely touching
    # phases still share the exact centisecond boundary.
    overlap = min(e.end_s,span_end)-max(e.start_s,span_start)
    if (e.start_s > span_start and e.end_s > span_end and
            1e-6 < overlap < .8*min(e.duration,span_end-span_start)):
        return False
    anchor=geometry.positions[previous.source_index]
    allowance=.18*min(geometry.heights[e.source_index],geometry.heights[previous.source_index])
    # Only broaden candidates for animated, strongly overlapping
    # copies with the same non-scale layout. The affine trajectory
    # test below must still prove that these form one scale trail.
    if (context.scale_trails and not any(k in e.state or k in reference.state
                                    for k in ("clip","iclip")) and
            (e.source_index in context.animated_sources or
            pos==geometry.positions[reference.source_index]) and
            geometry.layouts[e.source_index]==geometry.layouts[reference.source_index] and
            e.name==reference.name and
            min(e.end_s,reference.end_s)-max(e.start_s,reference.start_s)
                >= .8*min(e.duration,reference.duration)):
        anchor=geometry.positions[reference.source_index]
        allowance=geometry.heights[reference.source_index]
    if (abs(pos[0]-anchor[0])<=allowance and
        abs(pos[1]-anchor[1])<=allowance and
        e.margin_l==previous.margin_l and
        e.margin_r==previous.margin_r and
        e.margin_v==previous.margin_v):
        return True
    return False



def _cluster_text_effect_sequences(context: TextEffectSequenceContext,
                                   geometry: TextEffectSequenceGeometry, bucket: list[Event]
                                   ) -> list[list[Event]]:
    """Build source-ordered components and retain the highest-sample reference."""
    components=[]
    anchors={}
    for e in sorted(bucket,key=lambda x:(x.start_s,x.end_s,x.source_index)):
        pos=get_pos(e.text)
        found=None
        for component in reversed(components):
            if _text_effect_sequence_neighbor(context,geometry,e,pos,component,anchors[id(component)]):
                found=component;break
        if found is None:
            component=[e]
            components.append(component)
            anchors[id(component)]=e
        else:
            found.append(e)
            if geometry.heights[e.source_index]>geometry.heights[anchors[id(found)].source_index]:
                anchors[id(found)]=e
    return components



def _prove_text_effect_sequence(context: TextEffectSequenceContext,
                                geometry: TextEffectSequenceGeometry, visible: str,
                                component: list[Event]
                                ) -> tuple[TextEffectSequenceProfile | None,list[Event]]:
    """Apply scale-trail proof and existing phase admission, preserving every excluded member."""
    retained=[]
    if len(component)<2:
        return None,retained+component
    clipped=any("clip" in e.state or "iclip" in e.state for e in component)
    drifting=len({geometry.positions[e.source_index] for e in component})>1
    members = (match_scale_trail(component,visible,context.animated_sources,geometry.positions,geometry.heights,geometry.layouts)
               if context.scale_trails and not clipped and drifting else None)
    trail = members is not None
    if context.scale_trails and not trail:
        return None,retained+component
    if trail:
        member_ids={e.source_index for e in members}
        retained.extend(e for e in component if e.source_index not in member_ids)
        component=members
    if not clipped and (len({e.name for e in component}) != 1 or
            drifting and not trail or
            (len({state_key(e) for e in component}) < 2 and
             not (all(e.source_index in (context.animated_sources or set()) for e in component) and
                  len({e.text for e in component}) == 1 and
                  len({e.layer for e in component}) == 1 and
                  all(a.end == b.start for a,b in zip(component,component[1:]))))):
        return None,retained+component
    visible_candidates=[e for e in component if e.state.get("1a",255)<255]
    if not visible_candidates:
        return None,retained+component
    start=min(e.start_s for e in component)
    end=max(e.end_s for e in component)
    return TextEffectSequenceProfile(component,visible_candidates,clipped,trail,start,end),retained



def _select_text_effect_sequence_geometry(context: TextEffectSequenceContext,
                                      geometry: TextEffectSequenceGeometry,
                                      profile: TextEffectSequenceProfile) -> Event:
    """Choose full-sized trail geometry, a temporal sample, or a proven upright hold."""
    if profile.clipped:
        chosen=max(profile.visible_candidates,key=lambda e:(
            e.state.get("1a",255)==0,
            "clip" not in e.state and "iclip" not in e.state,
            e.duration,int(e.layer) if e.layer.lstrip("-").isdigit() else 0))
        return chosen
    midpoint=(profile.start_s+profile.end_s)/2
    if profile.trail:
        # Keep the most visible full-sized sample, not a tiny tail
        # or an arbitrary frame nearer the temporal midpoint.
        chosen=max(profile.visible_candidates,key=lambda e:(
            -e.state.get("1a",255), geometry.heights[e.source_index],
            int(e.layer) if e.layer.lstrip("-").isdigit() else 0))
    else:
        rank = lambda e: (e.start_s <= midpoint < e.end_s,
                          -max(e.start_s-midpoint,midpoint-e.end_s,0),
                          -e.state.get("1a",255),
                          int(e.layer) if e.layer.lstrip("-").isdigit() else 0)
        def choose(candidates):
            ordered = sorted(candidates,key=lambda e:(e.start_s,e.end_s))
            if any(b.start_s<a.end_s-1e-6 for a,b in zip(ordered,ordered[1:])):
                # Simultaneous paint/effect alternatives are not a sampled
                # motion timeline. Their existing compositing representative
                # remains the owner; frame dwell cannot establish that role.
                return max(candidates,key=rank)
            pose,_ = _representative_frame_pose(candidates)
            key = _frame_pose_key(pose)
            # The ordinary sequence's existing literal/paint representative
            # remains independent of geometry, among records at that pose.
            return max((e for e in candidates if _frame_pose_key(e)==key),key=rank)
        chosen = choose(profile.visible_candidates)
        if (context.source_events is not None and
                any(e.source_index in context.animated_sources for e in profile.members) and
                not unrotated_text_state(chosen.state)):
            # Prefer a real readable hold over a longer rotated
            # entrance. Paint dwell and full cue timing stay shared.
            holds = upright_text_holds(profile.visible_candidates,context.source_events)
            if holds:
                chosen = choose(holds)
    return chosen



def _select_text_effect_sequence_paint(context: TextEffectSequenceContext,
                                   profile: TextEffectSequenceProfile, chosen: Event
                                   ) -> tuple[dict,str]:
    """Select sustained event paint without changing representative geometry."""
    selection = select_static_state(chosen.state,[],set(),context.styles,chosen.defaults,
        paint_events=profile.visible_candidates,continuation=chosen.continuation)
    state = selection.state
    # Preserve the chosen object's geometry and inline text. The
    # shared selector changes only colours when given event paint.
    color_tags = '' if profile.clipped else ''.join(render_tag(k,state[k]) for k in ('1c','3c','4c')
                         if state.get(k) != chosen.state.get(k) and k in state)
    return state,color_tags



def _construct_text_effect_sequence_caption(context: TextEffectSequenceContext,
                                          geometry: TextEffectSequenceGeometry,
                                          profile: TextEffectSequenceProfile) -> Event:
    """Construct the caption while preserving each route's text, timing and layer rules."""
    chosen = _select_text_effect_sequence_geometry(context,geometry,profile)
    state,color_tags = _select_text_effect_sequence_paint(context,profile,chosen)
    if profile.clipped or profile.trail:
        text = render_simplified_caption(state,OVERRIDE_RE.sub("",chosen.text),
                                        outline_states=[e.state for e in profile.members],measurement=chosen.measurement,
                                        source_paint=_source_caption_paint(state,[e.state for e in profile.members]))
    elif color_tags and chosen.text.startswith('{'):
        index = chosen.text.index('}')
        text = chosen.text[:index]+color_tags+chosen.text[index:]
    else:
        text = ('{'+color_tags+'}' if color_tags else '')+chosen.text
    timing = dict(start=format_time(profile.start_s),end=format_time(profile.end_s),
                  start_s=profile.start_s,end_s=profile.end_s,
                  source_index=min(e.source_index for e in profile.members))
    if profile.clipped:
        timing.update(layer="0",effect="")
    caption = replace_event(chosen,text=text,**timing)
    return _preserve_frame_pose_support(chosen,caption,profile.visible_candidates)



def _flatten_text_effect_sequence_bucket(context: TextEffectSequenceContext, key: tuple,
                                        bucket: list[Event]) -> tuple[list[Event],int]:
    """Cluster, prove and construct independent captions within one grouping key."""
    style,visible=key[:2]
    geometry = _index_text_effect_sequence_geometry(bucket)
    output=[]
    removed=0
    for component in _cluster_text_effect_sequences(context,geometry,bucket):
        profile,retained = _prove_text_effect_sequence(context,geometry,visible,component)
        output.extend(retained)
        if profile is None:
            continue
        output.append(_construct_text_effect_sequence_caption(context,geometry,profile))
        removed += len(profile.members)-1
    return output,removed



def _finish_text_effect_sequences(context: TextEffectSequenceContext, output: list[Event],
                                  removed: int) -> tuple[list[Event],int]:
    """Run the existing movement/paint handoff and final exact-position consolidation."""
    if context.scale_trails and context.source_events is not None:
        output,phase_removed = collapse_moving_glyph_sequences(
            output,context.visible_map,context.source_events,context.font_metrics)
        removed += phase_removed
        output = normalize_karaoke_completion_paint(output,context.visible_map,context.source_events)
    if context.scale_trails:
        # Unmasking/normalizing can expose an ordinary same-anchor phase.
        # Repeat only the existing exact-position phase rules, retaining
        # original move/hold evidence and avoiding another animation pass.
        output,phase_removed = flatten_text_effect_sequences(
            output,context.visible_map,context.styles,context.animated_sources,False,
            source_events=context.source_events, font_report=context.font_report,
            lyric_boundaries=context.lyric_boundaries)
        removed += phase_removed
    return sorted(output,key=lambda e:e.source_index),removed



def flatten_text_effect_sequences(
    events: list[Event], visible_map: dict[int, str], styles: dict,
    animated_sources: set[int] | None=None, _scale_trails: bool=True, *,
    source_events: dict[int, Event] | None=None, font_metrics: FontMetrics | None=None,
    font_report: FontProcessingReport | None=None,
    lyric_boundaries: LyricBoundaryIndex | None=None,
) -> tuple[list[Event], int]:
    """Freeze connected full-text styling phases as one static caption.

    For unmasked text keep representative geometry and sustained colours;
    for clipped effects retain a plain readable caption. Gaps split runs.
    """
    context = TextEffectSequenceContext(
        visible_map,styles,animated_sources or set(),_scale_trails,source_events,font_metrics,
        font_report=font_report,
        lyric_boundaries=lyric_boundaries or _index_lyric_boundaries(events,visible_map))
    events,removed = _prepare_text_effect_sequence_pass(events,context)
    buckets,output = _group_text_effect_sequences(events,context)
    for key,bucket in buckets.items():
        captions,count = _flatten_text_effect_sequence_bucket(context,key,bucket)
        output.extend(captions)
        removed += count
    return _finish_text_effect_sequences(context,output,removed)
