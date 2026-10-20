"""Frame-exit echo proofs and ordered replacement using borrowed source evidence."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from .ass_overrides import OVERRIDE_RE
from .caption_geometry import get_pos, inline_layout_key, text_height, text_layout_key
from .caption_rendering import _source_caption_paint, render_simplified_caption
from .effect_validation import parse_effect_move
from .event_model import Event
from .event_operations import event_override_tokens, replace_event, state_key


@dataclass(frozen=True)
class FrameEchoContext:
    """Original duration/source inputs and private replacement ownership for one pass."""
    max_piece_duration: float
    source_events: dict[int,Event] | None
    omit: set[str]
    removed: set[int]
    replacements: dict[int,Event]

@dataclass(frozen=True)
class FrameEchoFamily:
    """Exact frame members and the existing per-family recorded-motion cache."""
    frames: dict[tuple[float,float],list[Event]]
    moving_frames: dict[tuple[float,float],bool]

@dataclass(frozen=True)
class FrameEchoFrame:
    """Validated layout, cached offset geometry and isolation for one frame."""
    start_s: float
    end_s: float
    members: list[Event]
    positions: dict[tuple,list[Event]]
    height: float
    points: list[tuple]
    center: tuple
    isolated: bool

@dataclass(frozen=True)
class FrameEchoHold:
    """The existing opaque settled-caption anchor and touching boundary."""
    end_s: float
    center: tuple
    anchor: Event

@dataclass(frozen=True)
class FrameEchoPaintProfile:
    """Paint-stack continuity and the retained foreground/outline anchor."""
    end_s: float
    continuity: tuple
    center: tuple
    foreground: Event
    stack: list[Event]

def _index_frame_echo_families(events: list[Event]) -> dict:
    """Index eligible captions by layout and exact frame interval."""
    families = {}
    for e in events:
        if (e.kind != "Dialogue" or e.effect or e.duration <= 0 or
                get_pos(e.text) is None or inline_layout_key(e) or
                e.state.get("p", 0) or "clip" in e.state or "iclip" in e.state):
            continue
        key = (e.style, e.name, e.margin_l, e.margin_r, e.margin_v,
               OVERRIDE_RE.sub("", e.text),
               tuple((k,v) for k,v in text_layout_key(e) if k not in {"fscx","fscy"}))
        families.setdefault(key, {}).setdefault((e.start_s,e.end_s), []).append(e)
    return families

def _frame_echo_follows_motion(points: list[tuple], center: tuple, previous_center: tuple,
                               height: float) -> bool:
    """Require evenly spaced offsets parallel to motion from the preceding anchor."""
    span = math.dist(points[0], points[-1])
    if not (len(points) >= 3 and .001*height < span <= .5*height and
            math.dist(center,previous_center) > span):
        return False
    direction = tuple(points[-1][axis]-points[0][axis] for axis in (0,1))
    motion = tuple(center[axis]-previous_center[axis] for axis in (0,1))
    return (abs(direction[0]*motion[1]-direction[1]*motion[0]) <=
            .05*span*math.hypot(*motion) and
            all(math.dist(point, tuple(points[0][axis] + direction[axis]*i/(len(points)-1)
                                      for axis in (0,1))) <= .01*height
                for i,point in enumerate(points)))

def _replace_frame_echo(context: FrameEchoContext, members: list[Event],
                        anchor: Event, text: str, layer: str | None = None) -> None:
    """Replace at the lowest source index using the original frame sample and anchor flags."""
    index = min(e.source_index for e in members)
    sample = members[0]
    context.replacements[index] = replace_event(sample, text=text, layer=anchor.layer if layer is None else layer,
                                        source_index=index, row=anchor.row, lyric=anchor.lyric)
    context.removed.update(e.source_index for e in members)

def _recorded_frame_echo_motion(context: FrameEchoContext, family: FrameEchoFamily,
                                time: tuple[float,float]) -> bool:
    """Cache original movement proof, lifetime bounds and consistent direction per frame."""
    if time not in family.moving_frames:
        valid = bool(context.source_events)
        points = sorted({get_pos(e.text) for e in family.frames[time]})
        direction = (tuple(points[-1][axis]-points[0][axis] for axis in (0,1))
                     if len(points) >= 3 else (0,0))
        span = math.hypot(*direction)
        valid &= span > 0
        reference = None
        for e in family.frames[time] if valid else ():
            original = context.source_events.get(e.source_index)
            if (original is None or original.duration <= 0 or
                    e.start_s < original.start_s-.001 or
                    e.end_s > original.end_s+.001 or inline_layout_key(original)):
                valid = False; break
            moves = [v for k,v in event_override_tokens(original) if k == 'move']
            values = (parse_effect_move(moves[0],original.duration,endpoint_slack=50)
                      if len(moves) == 1 else None)
            if values is None or math.dist(values[:2],values[2:4]) <= e.unit:
                valid = False; break
            motion = (values[2]-values[0],values[3]-values[1])
            if (abs(direction[0]*motion[1]-direction[1]*motion[0]) >
                    .05*span*math.hypot(*motion) or reference is not None and
                    sum(a*b for a,b in zip(reference,motion)) <= 0):
                valid = False; break
            reference = motion
        family.moving_frames[time] = valid
    return family.moving_frames[time]

def _frame_echo_is_exit(context: FrameEchoContext, family: FrameEchoFamily,
                         time: tuple[float,float]) -> bool:
    """Allow a short frame or the existing recorded-motion proof."""
    return time[1]-time[0] <= context.max_piece_duration+1e-6 or _recorded_frame_echo_motion(context,family,time)

def _frame_echo_candidates(context: FrameEchoContext, family: FrameEchoFamily
                            ) -> set[tuple[float,float]]:
    """Avoid full paint profiles until replicated exit candidates exist."""
    # Most subtitles have no replicated exit frames. Avoid resolving
    # complete paint profiles for their ordinary frame animation.
    candidates = {time for time,members in family.frames.items()
                  if len(members) >= 3 and _frame_echo_is_exit(context,family,time) and
                  len({get_pos(e.text) for e in members}) >= 3 and
                  (len(members) >= 6 and all(0 < e.state.get("1a",0) < 255 for e in members) or
                   len(members) == len({get_pos(e.text) for e in members}) and
                   all(e.state.get("1a",0) < 255 for e in members))}
    return candidates

def _isolated_frame_echo_times(times: list[tuple[float,float]]) -> set[tuple[float,float]]:
    """Identify frames without preceding or following temporal overlap."""
    isolated_frames = set()
    latest_end = -math.inf
    for i,(start,end) in enumerate(times):
        if latest_end <= start and (i+1 == len(times) or times[i+1][0] >= end):
            isolated_frames.add((start,end))
        latest_end = max(latest_end,end)
    return isolated_frames

def _blocked_frame_echo_times(context: FrameEchoContext, family: FrameEchoFamily,
                               times: list[tuple[float,float]]) -> set[tuple[float,float]]:
    """Propagate persistent repeated-label ambiguity backwards through touching frames."""
    # Brief entrances to persistent repeated labels are not exit echoes.
    # Propagate that ambiguity back through the touching frame sequence.
    blocked_starts, blocked = set(), set()
    for start,end in reversed(times):
        if (end in blocked_starts or not _frame_echo_is_exit(context,family,(start,end)) and
                len({get_pos(e.text) for e in family.frames[(start,end)]}) > 1):
            blocked.add((start,end))
            blocked_starts.add(start)
    return blocked

def _prepare_frame_echo_family(context: FrameEchoContext, frames: dict
                                ) -> tuple[FrameEchoFamily,list,set,set]:
    """Prepare only candidate families, reusing one ordered timeline for isolation and blocking."""
    family = FrameEchoFamily(frames,{})
    candidates = _frame_echo_candidates(context,family)
    if not candidates:
        return family,[],set(),set()
    starts = {start for start,_ in candidates}
    relevant = candidates | {time for time in frames if time[1] in starts}
    times = sorted(frames)
    isolated = _isolated_frame_echo_times(times)
    blocked = _blocked_frame_echo_times(context,family,times)
    return family,sorted(relevant),isolated,blocked

def _profile_frame_echo(time: tuple[float,float], members: list[Event],
                        isolated: set, blocked: set) -> FrameEchoFrame | None:
    """Resolve valid frame layout, offset stacks, height, center and isolation."""
    start,end = time
    if (len({text_layout_key(e) for e in members}) != 1 or
            any(e.state.get("borderstyle",1) != 1 for e in members)):
        return None
    positions = {}
    for e in members:
        positions.setdefault(get_pos(e.text), []).append(e)
    height = min(text_height(e) for e in members)
    points = sorted(positions)
    center = tuple(statistics.mean(p[axis] for p in points) for axis in (0,1))
    return FrameEchoFrame(start,end,members,positions,height,points,center,
                          time in isolated and time not in blocked)

def _match_flattened_frame_echo(context: FrameEchoContext, family: FrameEchoFamily,
                                frame: FrameEchoFrame, held: FrameEchoHold, anchor: Event) -> bool:
    """Require an isolated touching hold, matching fill/scale/shadow and proved motion."""
    return (frame.isolated and len(frame.members) == len(frame.points) and
        _frame_echo_is_exit(context,family,(frame.start_s,frame.end_s)) and abs(frame.start_s-held.end_s) <= 1e-6 and
        math.dist(frame.center,held.center) <= 5*frame.height and
        all(e.state.get("1c") == anchor.state.get("1c") and
            e.state.get("1a",0) < 255 and
            all(abs(e.state.get(k,0)-anchor.state.get(k,0)) <= .1*max(
                abs(anchor.state.get(k,100)),1) for k in ("fscx","fscy")) and
            all(e.state.get(axis+"shad",e.state.get("shad",0)) ==
                anchor.state.get(axis+"shad",anchor.state.get("shad",0))
                for axis in "xy") for e in frame.members) and
        _frame_echo_follows_motion(frame.points,frame.center,held.center,frame.height))

def _advance_flattened_frame_echo(context: FrameEchoContext, family: FrameEchoFamily,
                                  frame: FrameEchoFrame, held: FrameEchoHold | None
                                  ) -> tuple[FrameEchoHold | None,bool]:
    """Advance or reject the settled-caption proof without changing paint-stack state."""
    if (len(frame.members) == 1 and frame.end_s-frame.start_s > context.max_piece_duration+1e-6 and
            frame.isolated and frame.members[0].state.get("1a",0) == 0):
        return FrameEchoHold(frame.end_s,frame.center,frame.members[0]),False
    if held is not None:
        anchor = held.anchor
        if _match_flattened_frame_echo(context,family,frame,held,anchor):
            _replace_frame_echo(context,frame.members,anchor,anchor.text)
            return FrameEchoHold(frame.end_s,frame.center,anchor),True
    return None,False

def _frame_echo_paint_profile(context: FrameEchoContext, frame: FrameEchoFrame
                               ) -> FrameEchoPaintProfile | None:
    """Prove identical multilayer paint at every offset and cache continuity without stroke width."""
    profiles = []
    for stack in frame.positions.values():
        layers = {e.layer for e in stack}
        if (len(layers) != len(stack) or len(layers) < 2 or
                any(not layer.lstrip("-").isdigit() for layer in layers)):
            profiles = []
            break
        profiles.append(tuple(sorted((int(e.layer), state_key(e, {"pos"})) for e in stack)))
    if not profiles or len(set(profiles)) != 1:
        return None
    foreground = max(frame.members, key=lambda e: (int(e.layer), -math.dist(get_pos(e.text),frame.center)))
    stack = next(iter(frame.positions.values()))
    # Contour widths can change between exit frames. Each offset
    # must still carry an identical complete stack within its frame.
    continuity = tuple(sorted((int(e.layer), state_key(e, context.omit | {"bord","xbord","ybord"}))
                              for e in stack))
    return FrameEchoPaintProfile(frame.end_s,continuity,frame.center,foreground,stack)

def _match_stacked_frame_echo(context: FrameEchoContext, family: FrameEchoFamily,
                              frame: FrameEchoFrame, paint: FrameEchoPaintProfile,
                              previous: FrameEchoPaintProfile | None) -> bool:
    """Require touching continuity, eligible duration/isolation, translucent copies and motion."""
    return (previous is not None and abs(frame.start_s-previous.end_s) <= 1e-6 and
              paint.continuity == previous.continuity and _frame_echo_is_exit(context,family,(frame.start_s,frame.end_s)) and
              (frame.end_s-frame.start_s <= context.max_piece_duration+1e-6 or frame.isolated) and
              all(0 < e.state.get("1a",0) < 255 for e in frame.members) and
              _frame_echo_follows_motion(frame.points,frame.center,previous.center,frame.height))

def _collapse_frame_echo_family(context: FrameEchoContext, frames: dict) -> None:
    """Process the two proof paths in their original frame order and accumulate replacements."""
    family,times,isolated,blocked = _prepare_frame_echo_family(context,frames)
    previous = None
    held = None
    for time in times:
        frame = _profile_frame_echo(time,frames[time],isolated,blocked)
        if frame is None:
            previous = None
            held = None
            continue
        # Previously flattened copies use the independent settled-caption proof.
        held,flattened = _advance_flattened_frame_echo(context,family,frame,held)
        if flattened:
            previous = None
            continue
        paint = _frame_echo_paint_profile(context,frame)
        if paint is None:
            previous = None
            continue
        if len(frame.points) == 1:
            previous = paint if paint.foreground.state.get("1a",0) == 0 else None
            continue
        if not _match_stacked_frame_echo(context,family,frame,paint,previous):
            previous = None
            continue
        # Keep the preceding opaque pose and paint, never a translucent echo.
        anchor = previous.foreground
        text = render_simplified_caption(anchor.state,OVERRIDE_RE.sub("",anchor.text),
                                         outline_states=[e.state for e in previous.stack],measurement=anchor.measurement,
                                         source_paint=_source_caption_paint(anchor.state,[e.state for e in previous.stack]))
        _replace_frame_echo(context,frame.members,anchor,text,layer="0")
        previous = FrameEchoPaintProfile(frame.end_s,paint.continuity,frame.center,anchor,previous.stack)

def collapse_frame_text_echoes(events: list[Event],
                              max_piece_duration: float, *,
                              source_events: dict[int,Event] | None = None) -> tuple[list[Event], int]:
    """Collapse exit echoes proven by paint stacks or a settled caption.

    Require the same multilayer paint stack at every offset, a touching
    frame sequence, and evenly spaced offsets along the motion direction.
    Longer frames need recorded source movement; duration alone cannot prove
    or disprove such an exit. Unproven copies retain the short-frame limit.
    Already flattened copies require a longer isolated opaque hold with the
    same fill/layout. Static labels and unrelated paint remain separate.
    """
    context = FrameEchoContext(
        max_piece_duration,source_events,{"pos","fscx","fscy","1a","2a","3a","4a"},set(),{})
    for frames in _index_frame_echo_families(events).values():
        _collapse_frame_echo_family(context,frames)
    # Apply accepted replacements in the original event-list order.
    output = [context.replacements[e.source_index] if e.source_index in context.replacements else e
              for e in events if e.source_index not in context.removed or e.source_index in context.replacements]
    return output,len(context.removed)-len(context.replacements)
