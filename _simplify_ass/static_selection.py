"""Representative static geometry, paint and selection-local source evidence.

Inputs are borrowed; sampling buffers and votes belong to each selection call.
Event replacement, serialization and pipeline diagnostics stay with their callers.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from .event_model import Event
from .ass_overrides import OverrideEvaluation, OverrideContinuation, apply_override
from .transform_sampling import sample_transform_state, sample_transform_states


@dataclass(frozen=True)
class StaticStateContext:
    """Selection inputs and pass-owned evidence accumulators copied from optional seeds."""
    base: dict
    transforms: list
    times: list[float]
    styles: dict
    default: dict
    opaque_spans: list[tuple[float,float]] | None
    settled_states: list[dict] | None
    prefer_upright: bool
    upright_crossings: bool
    prior_pose: StaticPoseEvidence
    continuation: OverrideContinuation


@dataclass(frozen=True)
class StaticStateEvidence:
    """Existing geometry filters and independent stationary position/sizing votes."""
    geometry: tuple
    geometry_transforms: list
    hold_groups: tuple
    hold_votes: list[dict]
    hold_transforms: list


@dataclass(frozen=True)
class StaticStateSamples:
    """Ranked interval states, paint samples and the total readable hold-voting time."""
    candidates: list
    paint_samples: list
    visible_time: float


@dataclass(frozen=True)
class StaticPoseEvidence:
    """Selection-local upright policy and protected source geometry.

    A continued authored span may explicitly inherit this proof. Literal style
    resets clear it; a new upright selection recomputes its sustained geometry.
    Arbitrary event replacements and render/reparse normalization carry only
    formatting, so consumers re-prove pose from source instead of inheriting
    a decision for another layout or interval.
    """
    upright_rotation: bool = False
    sustained_geometry: tuple[tuple[str,float | str | tuple[float,float]], ...] | None = None

    def __post_init__(self):
        if self.sustained_geometry is not None:
            object.__setattr__(self, 'sustained_geometry',tuple(
                (key,tuple(value) if isinstance(value,(list,tuple)) else value)
                for key,value in self.sustained_geometry))


@dataclass(frozen=True)
class StaticStateSelection:
    """Selected formatting and separately collected transform evidence.

    Evidence intervals use milliseconds relative to the sampled block.
    None means collection was disabled; an empty tuple means nothing was
    recorded. Seeded state snapshots are borrowed unchanged, while newly
    sampled snapshots are independent dictionary copies. The state retains
    the selector's existing identity and formatting ownership rules.
    """
    state: dict
    opaque_spans: tuple[tuple[float,float], ...] | None
    settled_states: tuple[dict, ...] | None
    pose: StaticPoseEvidence = field(default_factory=StaticPoseEvidence)
    continuation: OverrideContinuation = field(default_factory=OverrideContinuation)


def unrotated_text_state(state: dict) -> bool:
    """Treat whole turns on every axis as zero rotation."""
    return all(math.isfinite(state.get(k,0)) and
               abs(math.remainder(state.get(k,0),360)) <= .001
               for k in ('frz','frx','fry'))


def upright_text_state(state: dict, *, include_shadow: bool = False,
                       include_outline: bool = False, minimum_opacity: int = 16) -> bool:
    """Recognize readable, unflipped text with no rotation on any axis.

    Pose selection may also use letters painted entirely by an offset shadow.
    Other callers still require visible primary text by default.
    """
    cutoff = 255-minimum_opacity
    visible = state.get('1a',0) < cutoff
    if include_outline and not visible and state.get('3a',0) < cutoff:
        visible = max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0
    if (include_shadow and not visible and state.get('1a',0) >= 254 and
            state.get('3a',0) >= 254 and state.get('4a',0) < cutoff and
            state.get('borderstyle',1) == 1 and
            'clip' not in state and 'iclip' not in state):
        offsets = [state.get(k,state.get('shad',0)) for k in ('xshad','yshad')]
        visible = all(math.isfinite(v) for v in offsets) and any(offsets)
    return (visible and
            all(state.get(k,100) > .01 for k in ('fscx','fscy')) and
            unrotated_text_state(state))


def upright_transform_pose(base: dict, transforms: list, times: list[float],
                           styles: dict, default: dict, preferred_at: float, *,
                           continuation: OverrideContinuation = OverrideContinuation()
                           ) -> OverrideEvaluation | None:
    """Find a visible upright pose on the actual numeric rotation path.

    Search endpoints and bracketed crossings of whole turns. Resolve the
    entire state at that instant, including simultaneous movement and sizing.
    Raw angles distinguish a half-turn around 180 from a crossing of zero.
    """
    axes = ('frz','frx','fry')
    rotations = [(a,b,accel,[(n,v) for n,v in changes if n in {*axes,'fr'}])
                 for a,b,accel,changes in transforms]
    cache = {}
    def angles(at):
        if at not in cache:
            state = sample_transform_state(base,rotations,at,styles,default,
                                           continuation=continuation).formatting
            cache[at] = tuple(state.get(k,0) for k in axes)
        return cache[at]
    def pose(at):
        result = sample_transform_state(base,transforms,at,styles,default,continuation=continuation)
        state = result.formatting
        return result if not state.get('p',0) and upright_text_state(
            state,include_shadow=True,include_outline=True,minimum_opacity=1) else None
    intervals = sorted(zip(times,times[1:]),key=lambda span:
                       max(span[0]-preferred_at,preferred_at-span[1],0))
    for left,right in intervals:
        for at in sorted((left,right),key=lambda t:(abs(t-preferred_at),-t)):
            if all(math.isfinite(v) and abs(math.remainder(v,360)) <= .001 for v in angles(at)):
                state = pose(at)
                if state is not None:
                    return state
        # A midpoint also brackets excursions from overlapping transforms
        # whose interval endpoints happen to have the same rotation.
        middle = (left+right)/2
        for a,b in ((left,middle),(middle,right)):
            start,finish = angles(a),angles(b)
            for axis,(lo,hi) in enumerate(zip(start,finish)):
                if not math.isfinite(lo) or not math.isfinite(hi) or abs(hi-lo) <= .001:
                    continue
                low,high = sorted((lo,hi))
                first,last = math.ceil(low/360),math.floor(high/360)
                if first > last:
                    continue
                winding = min(last,max(first,round(angles((a+b)/2)[axis]/360)))
                for target in dict.fromkeys((360*winding,360*first,360*last)):
                    begin,end = a,b
                    for _ in range(48):
                        at = (begin+end)/2
                        value = angles(at)[axis]
                        if abs(value-target) <= 1e-7:
                            break
                        if (value < target) == (lo < hi):
                            begin = at
                        else:
                            end = at
                    state = pose(at)
                    if state is not None:
                        return state
    return None


def _prepare_static_state_evidence(transforms: list, boundaries: set[float]
                                    ) -> tuple[list[float],StaticStateEvidence]:
    """Prepare interval boundaries and the existing geometry/hold tag filters once."""
    geometry = ("pos", "org", "fs", "fscx", "fscy", "fsp", "frz",
                "frx", "fry", "fax", "fay", "clip", "iclip")
    # Filter once per block instead of revisiting tag names at every interval.
    # Keep even empty change lists: equality checks retain their old semantics.
    geometry_transforms = [(a,b,[(name,value) for name,value in changes
                                if name in geometry or name in {"fr","r"}])
                           for a,b,_,changes in transforms]
    times = sorted(boundaries)
    hold_groups = (('pos',),('fn','fs','fscx','fscy','fsp','an','b','i','u','s'))
    hold_votes = [{} for _ in hold_groups]
    hold_transforms = [[(a,b,[(name,value) for name,value in changes
                            if name in {*group,'r'} or name == 'a' and 'an' in group])
                        for a,b,_,changes in transforms
                        if any(name in {*group,'r'} or name == 'a' and 'an' in group
                               for name,_ in changes)] for group in hold_groups]
    return times,StaticStateEvidence(geometry,geometry_transforms,hold_groups,hold_votes,hold_transforms)


def _static_state_geometry_is_settled(context: StaticStateContext, evidence: StaticStateEvidence,
                                      state: dict, continuation: OverrideContinuation, at: float) -> bool:
    """Treat resolved no-op geometry as settled even during colour or blur animation."""
    for a,b,changes in evidence.geometry_transforms:
        if a < at < b:
            target = state.copy()
            target_continuation = continuation
            for name,value in changes:
                target_continuation = apply_override(target,name,value,context.styles,context.default,
                                                     target_continuation,event_tags=False)
            if any(target.get(k) != state.get(k) for k in evidence.geometry):
                return False
    return True


def _vote_static_state_holds(context: StaticStateContext, evidence: StaticStateEvidence,
                             state: dict, continuation: OverrideContinuation,
                             at: float, start: float, end: float) -> None:
    """Accumulate stationary position and sizing holds independently across paint boundaries."""
    for group,votes,updates in zip(evidence.hold_groups,evidence.hold_votes,evidence.hold_transforms):
        if any(k not in state for k in group):
            continue
        stationary = True
        for a,b,changes in updates:
            if not a < at < b:
                continue
            target = state.copy()
            target_continuation = continuation
            for name,value in changes:
                target_continuation = apply_override(target,name,value,context.styles,context.default,
                                                     target_continuation,event_tags=False)
            if any(target.get(k) != state.get(k) for k in group):
                stationary = False
                break
        if stationary:
            key = tuple(state[k] for k in group)
            votes[key] = votes.get(key,0)+end-start


def _record_static_opaque_span(spans: list[tuple[float,float]], start: float, end: float) -> None:
    """Merge touching opaque intervals with the original strict timing tolerance."""
    if spans and abs(spans[-1][1]-start) < 1e-6:
        spans[-1] = (spans[-1][0],end)
    else:
        spans.append((start,end))


def _sample_static_state_intervals(context: StaticStateContext, evidence: StaticStateEvidence) -> StaticStateSamples:
    """Sample complete transform states, rank geometry and collect paint/evidence intervals."""
    candidates = []
    paint_samples = []
    visible_time = 0.0
    samples = sample_transform_states(context.base,context.transforms,
        ((start+end)/2 for start,end in zip(context.times,context.times[1:])),context.styles,context.default,
        continuation=context.continuation)
    for (start,end),sample in zip(zip(context.times,context.times[1:]),samples):
        state,continuation = sample.formatting,sample.continuation
        at = (start+end)/2
        visible = (abs(state.get("fscx",100)) > .01 and abs(state.get("fscy",100)) > .01
                   and min(state.get("1a",0),state.get("3a",0),state.get("4a",0)) < 254)
        stable = not any(a < at < b for a,b,_,_ in context.transforms)
        # Color/blur animation must not make a settled glyph less desirable
        # than a rotated entrance or exit. Compare resolved geometry, so even
        # no-op transforms count as stationary. Paint is still sampled intact.
        settled = _static_state_geometry_is_settled(context,evidence,state,continuation,at)
        # Entrance/exit fades often use transparent primary text while an
        # unused shadow channel remains opaque. Prefer the visible fill too.
        strength = 255 - state.get("1a",0)
        readable = (not state.get('p',0) and state.get('fs',20) > 0 and
                    not any(k in state for k in ('clip','iclip')) and
                    upright_text_state({**state,'frz':0,'frx':0,'fry':0},
                        include_shadow=True,include_outline=True))
        if context.prefer_upright and readable:
            visible_time += end-start
            _vote_static_state_holds(context,evidence,state,continuation,at,start,end)
        if context.settled_states is not None and visible and settled:
            context.settled_states.append(state.copy())
        candidates.append(((visible, settled, stable, strength > 16, end-start, strength),sample))
        paint_samples.append((start,end,state,(0,len(paint_samples))))
        if context.opaque_spans is not None and state.get('1a',0) == 0:
            _record_static_opaque_span(context.opaque_spans,start,end)
    return StaticStateSamples(candidates,paint_samples,visible_time)


def _choose_static_state_geometry(context: StaticStateContext, samples: StaticStateSamples) -> tuple[OverrideEvaluation,int | None]:
    """Choose the ranked interval, preferring an existing settled upright hold when requested."""
    candidates = samples.candidates
    best = max(range(len(candidates)),key=lambda i:candidates[i][0]) if candidates else None
    chosen = candidates[best][1] if best is not None else OverrideEvaluation(context.base,context.continuation)
    if context.prefer_upright and not chosen.formatting.get('p',0) and not unrotated_text_state(chosen.formatting):
        holds = [item for item in candidates if item[0][0] and item[0][1] and
                 upright_text_state(item[1].formatting,include_shadow=True) and not item[1].formatting.get('p',0)]
        if holds:
            chosen = max(holds,key=lambda item:item[0])[1]
    return OverrideEvaluation(chosen.formatting.copy(),chosen.continuation),best


def _static_state_has_rotation(context: StaticStateContext) -> bool:
    """Check overlapping original rotation transforms without changing pose or paint."""
    for begin,end,_,changes in context.transforms:
        if begin >= context.times[-1] or end < context.times[0]:
            continue
        target = context.base.copy()
        continuation = context.continuation
        for name,value in changes:
            if name in {'fr','frz','frx','fry'}:
                continuation = apply_override(target,name,value,context.styles,context.default,
                                               continuation,event_tags=False)
        if any(target.get(k,0) != context.base.get(k,0) for k in ('frz','frx','fry')):
            return True
    return False


def _apply_static_upright_fallback(context: StaticStateContext, chosen: OverrideEvaluation,
                                  best: int | None) -> tuple[OverrideEvaluation,bool]:
    """Use a complete upright pose only when needed, retaining the representative paint."""
    upright_rotation = context.prior_pose.upright_rotation
    state = chosen.formatting
    if (context.prefer_upright and context.upright_crossings and not state.get('p',0) and context.times and
            _static_state_has_rotation(context)):
        if not upright_text_state(state,include_shadow=True,include_outline=True,minimum_opacity=1):
            at = sum(context.times[best:best+2])/2 if best is not None else context.times[0]
            upright = upright_transform_pose(context.base,context.transforms,context.times,context.styles,context.default,at,
                                             continuation=context.continuation)
            if upright is not None:
                # Pose selection must not resurrect fading particles or
                # change paint ties. Opacity and colour remain the
                # representative paint, with dwell voting below.
                paint = {k:state[k] for ch in (1,2,3,4) for k in (f'{ch}a',f'{ch}c')
                         if k in state}
                chosen = upright
                state = chosen.formatting
                state.update(paint)
        if upright_text_state(state,include_shadow=True,include_outline=True,minimum_opacity=1):
            state.update(frz=0.0,frx=0.0,fry=0.0)
            upright_rotation = True
    return chosen,upright_rotation


def _protect_sustained_static_geometry(chosen: dict, evidence: StaticStateEvidence, visible_time: float) -> tuple | None:
    """Restore one majority position/size hold of at least 250 ms after an upright fallback."""
    protected = {}
    for group,votes in zip(evidence.hold_groups,evidence.hold_votes):
        # Require a real hold covering a majority of the readable time.
        # Colour boundaries divide a hold but must not weaken its proof.
        sustained = [key for key,dwell in votes.items()
                     if dwell >= 250-1e-6 and dwell > .5*visible_time+1e-6]
        if len(sustained) == 1:
            protected.update(zip(group,sustained[0]))
    chosen.update(protected)
    return tuple(protected.items()) if protected else None


def _static_state_colour_spans(paint_samples: list, paint_events: Iterable[Event] | None) -> list:
    """Create transform intervals or composited event intervals for visible colour voting."""
    if paint_events is not None:
        paint_samples = [(e.start_s,e.end_s,e.state,
                          (int(e.layer) if e.layer.lstrip('-').isdigit() else 0,e.source_index))
                         for e in paint_events if e.end_s > e.start_s]
    # Count each channel only when it can paint visible pixels. Exact repeated
    # colours accumulate dwell time; a short highlight cannot replace a longer
    # base just because it was first, topmost, or present at the cue midpoint.
    if paint_events is None:
        spans = [(start,end,[(state,order)]) for start,end,state,order in paint_samples]
    else:
        times = sorted({t for start,end,_,_ in paint_samples for t in (start,end)})
        spans = [(start,end,[(state,order) for a,b,state,order in paint_samples
                            if a <= (start+end)/2 < b])
                 for start,end in zip(times,times[1:])]
    return spans


def _vote_static_state_colours(spans: list) -> dict:
    """Accumulate visible colour dwell per channel using front-to-back alpha compositing."""
    dwell = {channel:{} for channel in (1,3,4)}
    for start,end,active in spans:
        active = [(state,order) for state,order in active if
                  abs(state.get('fscx',100)) > .01 and abs(state.get('fscy',100)) > .01]
        for channel in dwell:
            eligible = [(state,order) for state,order in active
                        if state.get(f'{channel}a',0) < 254 and
                        re.fullmatch(r'[0-9A-Fa-f]{6}',str(state.get(f'{channel}c',''))) and
                        (channel == 1 or channel == 3 and
                         max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0 or
                         channel == 4 and
                         max(abs(state.get(k,state.get('shad',0))) for k in ('xshad','yshad')) > 0)]
            remaining = 1.0
            for state,_ in sorted(eligible,key=lambda item:item[1],reverse=True):
                color = state[f'{channel}c'].upper()
                opacity = min(1.0,max(0.0,(255-state.get(f'{channel}a',0))/255))
                dwell[channel][color] = (dwell[channel].get(color,0)+
                                         (end-start)*remaining*opacity)
                remaining *= 1-opacity
                if remaining <= 1e-9:
                    break
    return dwell


def _apply_static_state_colour_vote(chosen: dict, dwell: dict) -> dict:
    """Apply only a stronger dwell winner, retaining representative paint for ties."""
    for channel,colors in dwell.items():
        if colors:
            key = f'{channel}c'
            winner = max(colors,key=colors.get)
            if colors.get(chosen.get(key),-1) < colors[winner]-1e-6:
                chosen[key] = winner
    return chosen


def select_static_state(base: dict, transforms: list, boundaries: set[float],
                        styles: dict, default: dict,
                        paint_events: Iterable[Event] | None = None,
                        prior_opaque_spans: Iterable[tuple[float,float]] | None = None,
                        prior_settled_states: Iterable[dict] | None = None, *,
                        prefer_upright: bool = False,
                        upright_crossings: bool = True,
                        prior_pose: StaticPoseEvidence | None = None,
                        continuation: OverrideContinuation = OverrideContinuation()) -> StaticStateSelection:
    """Keep settled geometry and choose colours by their total visible time.

    Repeated colour holds add together across animation intervals. Event
    copies use compositing order, so simultaneous backing layers do not get
    duplicate votes. Colour ramps retain a representative interval sample.
    Sustained position and sizing evidence outranks upright instants. Without
    that evidence, an upright crossing remains a complete-pose fallback.
    Optional evidence seeds are read-only inputs. Return the accumulated
    evidence separately; an unchanged selection still returns the base
    formatting dictionary itself in the result's state field.
    Parser continuation and pose proof are distinct explicit inputs/results.
    Pose proof is inherited only through prior_pose. Sustained geometry is
    recomputed whenever the upright policy protects an animated selection.
    """
    opaque_spans = list(prior_opaque_spans) if prior_opaque_spans is not None else None
    settled_states = list(prior_settled_states) if prior_settled_states is not None else None
    prior_pose = prior_pose or StaticPoseEvidence()
    if not transforms and paint_events is None:
        if opaque_spans is not None and base.get('1a',0) == 0 and boundaries:
            opaque_spans.append((min(boundaries),max(boundaries)))
        if settled_states is not None and boundaries and max(boundaries) > min(boundaries):
            settled_states.append(base.copy())
        return StaticStateSelection(base,
            tuple(opaque_spans) if opaque_spans is not None else None,
            tuple(settled_states) if settled_states is not None else None,prior_pose,continuation)
    times,evidence = _prepare_static_state_evidence(transforms,boundaries)
    context = StaticStateContext(base,transforms,times,styles,default,
                                 opaque_spans,settled_states,prefer_upright,upright_crossings,prior_pose,continuation)
    samples = _sample_static_state_intervals(context,evidence)
    selected,best = _choose_static_state_geometry(context,samples)
    selected,upright_rotation = _apply_static_upright_fallback(context,selected,best)
    chosen = selected.formatting
    protected = prior_pose.sustained_geometry
    if prefer_upright and upright_rotation:
        protected = _protect_sustained_static_geometry(chosen,evidence,samples.visible_time)
    if paint_events is not None or any(
            name in {'c','1c','3c','4c','r'}
            for _,_,_,changes in transforms for name,_ in changes):
        spans = _static_state_colour_spans(samples.paint_samples,paint_events)
        dwell = _vote_static_state_colours(spans)
        chosen = _apply_static_state_colour_vote(chosen,dwell)
    return StaticStateSelection(chosen,
        tuple(opaque_spans) if opaque_spans is not None else None,
        tuple(settled_states) if settled_states is not None else None,
        StaticPoseEvidence(upright_rotation,protected),selected.continuation)
