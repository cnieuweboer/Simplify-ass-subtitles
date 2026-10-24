"""Supporting-drawing admission, coverage, paint reduction and contour evidence.

Inputs stay borrowed; contexts and counters belong to one call. Callers retain
caption association, budgets, layering, stage order and aggregate reporting.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from .ass_overrides import tokenize_override, apply_override, OVERRIDE_RE, NUMBER
from .event_model import Event, EventEvidence
from .effect_validation import parse_effect_transform, parse_effect_move
from .drawing_geometry import (
    coverage_geometry, drawing_polygon, normalize_drawing_alignment,
    flatten_rectangular_border, detach_drawing_edge_slivers,
    simplify_drawing_contour, merge_tiled_clips,
)
from .event_operations import replace_event, state_key
from .frame_sequences import freeze_vector_sequences
from .static_objects import geometry_key
from .caption_geometry import get_pos, inline_layout_key, placement_key, rectangle_clip
from .text_freezing import simplify_visual_text
from .caption_rendering import render_tag


@dataclass(frozen=True)
class SupportingDrawingContext:
    """Per-call border policy, counters, paint tags and retained original-contour evidence."""
    scaled_borders: bool
    counts: dict
    paint_tags: set
    original_contours: dict


@dataclass(frozen=True)
class SupportingDrawingCandidate:
    """Normalized candidate with frozen text, readable text and pre-simplification contour."""
    event: Event
    frozen_text: str
    visible: str
    original_points: list | None


@dataclass(frozen=True)
class SupportingDrawingCoverage:
    """Proven clip union and its distinct rectangles/coincident paint groups."""
    union: tuple | None
    clip_groups: dict
    rectangles: list


def reduce_vector_layers(events: list[Event]) -> tuple[list[Event], int]:
    # No arbitrary two-layer limit. Only remove exact opaque duplicates.
    seen, result = set(), []
    for e in sorted(events,key=lambda x:(-int(x.layer) if x.layer.lstrip("-").isdigit() else 0,x.source_index)):
        key = (e.start,e.end,geometry_key(e.text),state_key(e),placement_key(e))
        opaque = all(e.state.get(f"{c}a",0)==0 for c in (1,3,4))
        if opaque and key in seen:
            continue
        if opaque:
            seen.add(key)
        result.append(e)
    return sorted(result,key=lambda e:e.source_index),len(events)-len(result)


def drawing_paint(event):
    """Select visible paint; offset shadows/strokes need more geometry work."""
    st = event.state
    # A nearly coincident shadow can contain the actual background fill.
    if (st.get('4a', 0) < 254 and
            0 < max(abs(st.get(k, st.get('shad', 0))) for k in ('xshad', 'yshad'))
                <= .05 * event.unit and st.get('4a', 0) < st.get('1a', 0)):
        return st.get('4c', '000000'), st.get('4a', 0)
    if st.get('1a', 0) < 254:
        return st.get('1c', 'FFFFFF'), st.get('1a', 0)
    return None


def compose_drawing_paint(events):
    """Compose coextensive fills in their original same-layer source order."""
    opacity, premult = 0.0, [0.0, 0.0, 0.0]
    for event in sorted(events, key=lambda e: e.source_index):
        paint = drawing_paint(event)
        if paint is None:
            continue
        color, alpha = paint
        ink = (255-alpha)/255
        premult = [old*(1-ink)+((int(color, 16) >> shift) & 255)*ink
                   for old, shift in zip(premult, (16, 8, 0))]
        opacity = opacity*(1-ink)+ink
    if opacity <= 1/255:
        return None
    color = ''.join(f'{round(v/opacity):02X}' for v in premult)
    return color, round(255*(1-opacity))


def recover_held_drawing_scale(source, candidate, transforms, paint_tags):
    """Validate a short scale entrance, shrinking exit, or stable-pose pair."""
    if not transforms:
        return True, False
    if len(transforms) > 2:
        return False, False
    parsed, targets = [], []
    target = source.state.copy()
    target_continuation = source.continuation
    for value in transforms:
        item = parse_effect_transform(value, source.duration, paint_tags | {'fscx', 'fscy'})
        if item is None:
            return False, False
        for key, argument in item[2]:
            if key in ('fscx', 'fscy'):
                # libass accepts a trailing comma on these numeric targets.
                # Require a complete finite number rather than letting the
                # strict production parser silently skip a malformed target.
                if not re.fullmatch(r'\s*'+NUMBER+r'\s*,?\s*', argument):
                    return False, False
                argument = argument.strip().removesuffix(',').strip()
                if not math.isfinite(float(argument)):
                    return False, False
            target_continuation = apply_override(target,key,argument,source.styles,source.defaults,target_continuation)
        parsed.append(item)
        targets.append(target.copy())
    def matches(pose):
        return all(pose.get(k, 100) > 0 and
                   abs(pose.get(k, 100)-candidate.state.get(k, 100)) < .001
                   for k in ('fscx', 'fscy'))
    def shrinks(before, after):
        return (all(0 < after.get(k, 100) <= before.get(k, 100)
                    for k in ('fscx', 'fscy')) and
                any(after.get(k, 100) < before.get(k, 100) for k in ('fscx', 'fscy')))
    if len(parsed) == 1:
        begin, end, _ = parsed[0]
        entrance = begin == 0 and end <= 200*source.duration and matches(targets[0])
        exit_pose = (800*source.duration <= begin < 1000*source.duration and
                     end >= 1000*source.duration-50 and
                     matches(source.state) and shrinks(source.state, targets[0]))
        return entrance or exit_pose, exit_pose
    first, last = parsed
    exit_pose = (first[0] == 0 and first[1] <= 200*source.duration and
                 last[0]-first[1] >= 800*source.duration and
                 last[1] >= 1000*source.duration-50 and
                 matches(targets[0]) and shrinks(targets[0], targets[1]))
    return exit_pose, exit_pose


def _normalize_supporting_drawing_candidate(source: Event, context: SupportingDrawingContext) -> SupportingDrawingCandidate | None:
    """Freeze drawing paint, normalize alignment/stroke, detach edge slivers and simplify contours."""
    if (source.kind != 'Dialogue' or source.duration <= 0 or
            not re.search(r'\\p[1-9]\d*\b', source.text, re.I)):
        return None
    text, visible, chars = simplify_visual_text(
        source.text, 0, source.duration, source.defaults, source.styles, 2)
    if not chars:
        return None
    candidate = normalize_drawing_alignment(flatten_rectangular_border(
        replace_event(source, text=text, effect=''), scaled_borders=context.scaled_borders))
    candidate, detached = detach_drawing_edge_slivers(candidate)
    context.counts['drawing_edge_slivers_detached'] += detached
    original_points = None
    if drawing_polygon(candidate) is None:
        reduction = simplify_drawing_contour(candidate)
        if reduction is not None:
            raw, original_points = reduction
            candidate = replace_event(candidate, text=OVERRIDE_RE.match(candidate.text).group()+raw)
            context.counts['drawing_contours_simplified'] += 1
    return SupportingDrawingCandidate(candidate,text,visible,original_points)


def _profile_supporting_drawing_motion(source: Event, candidate: Event, text: str, paint_tags: set) -> tuple:
    """Retain the original held-scale proof and only a fully completed short entrance move."""
    transforms = [(k, v) for block in OVERRIDE_RE.findall(source.text)
                  for k, v in tokenize_override(block) if k == 't']
    geometry_transforms = [value for _, value in transforms if
                           any(k not in paint_tags for k, v in
                               tokenize_override(value[1:-1]))]
    held_scale, held_exit = recover_held_drawing_scale(
        source, candidate, geometry_transforms, paint_tags)
    animated_geometry = not held_scale
    moves = [v for block in OVERRIDE_RE.findall(source.text)
             for k, v in tokenize_override(block) if k == 'move']
    held_move = False
    if len(moves) == 1:
        motion = parse_effect_move(moves[0], source.duration)
        held_move = (motion is not None and len(motion) == 6 and
                     motion[5] <= 200*source.duration and
                     get_pos(text) is not None and
                     all(abs(a-b) < .001 for a, b in zip(get_pos(text), motion[2:4])))
    return animated_geometry,moves,held_exit,held_move


def _admit_supporting_drawing_candidate(source: Event, normalized: SupportingDrawingCandidate, context: SupportingDrawingContext) -> bool:
    """Reject mixed text, unsupported motion and static geometry before counting held exits/entrances."""
    candidate,visible = normalized.event,normalized.visible
    animated_geometry,moves,held_exit,held_move = _profile_supporting_drawing_motion(
        source,candidate,normalized.frozen_text,context.paint_tags)
    if (visible or inline_layout_key(source) or drawing_polygon(candidate) is None or
            (moves and not held_move) or animated_geometry or
            'iclip' in candidate.state or
            any(candidate.state.get(k, 0) for k in ('frx', 'fax', 'fay', 'pbo')) or
            candidate.state.get('fry', 0) % 360 not in (0, 180) or
            get_pos(candidate.text) is None):
        context.counts['unsupported_drawings_excluded'] += 1
        return False
    context.counts['drawing_scale_exits_frozen'] += held_exit
    context.counts['drawing_move_entrances_frozen'] += held_move
    return True


def _index_supporting_drawing_candidates(sources: Iterable[Event], context: SupportingDrawingContext) -> dict:
    """Group admitted candidates by original cue, drawing geometry, nonpaint state and contour evidence."""
    groups = {}
    for source in sources:
        normalized = _normalize_supporting_drawing_candidate(source,context)
        if normalized is None or not _admit_supporting_drawing_candidate(source,normalized,context):
            continue
        candidate,original_points = normalized.event,normalized.original_points
        raw_key = (source.start, source.end, source.layer, source.style, source.name,
                   source.margin_l, source.margin_r, source.margin_v,
                   geometry_key(candidate.text), state_key(candidate, context.paint_tags | {'clip'}),
                   tuple(original_points) if original_points is not None else None)
        if original_points is not None:
            context.original_contours[candidate.source_index] = tuple(original_points)
        groups.setdefault(raw_key, []).append(candidate)
    return groups


def _prove_supporting_drawing_strip_coverage(group: list[Event], context: SupportingDrawingContext) -> SupportingDrawingCoverage | None:
    """Intersect clips with actual rectangular fill and require a complete nondegenerate tiled union."""
    first = group[0]
    clipped = ['clip' in e.state for e in group]
    rects = [rectangle_clip(e) for e in group]
    # Clip coordinates outside a rectangle's actual fill do not create
    # gaps. Intersect first; gradient generators often round those unused
    # top/bottom limits differently in their final strip.
    path = drawing_polygon(first)
    if (path and len({x for x, y in path}) == 2 and
            len({y for x, y in path}) == 2 and coverage_geometry(first) is not None):
        points = coverage_geometry(first)[0]
        xs, ys = zip(*points)
        bounds = min(xs), min(ys), max(xs), max(ys)
        rects = [None if r is None else (max(r[0], bounds[0]), max(r[1], bounds[1]),
                                       min(r[2], bounds[2]), min(r[3], bounds[3]))
                 for r in rects]
    if any(clipped):
        if not all(clipped) or any(r is None or r[0] >= r[2] or r[1] >= r[3] for r in rects):
            context.counts['unsupported_drawings_excluded'] += len(group)
            return None
        clip_groups = {}
        for event, rect in zip(group, rects):
            clip_groups.setdefault(rect, []).append(event)
        rects = list(clip_groups)
        union = merge_tiled_clips(rects, first.unit)
        if union is None:
            context.counts['unsupported_drawings_excluded'] += len(group)
            return None
    else:
        union = None
        clip_groups = {}
    return SupportingDrawingCoverage(union,clip_groups,rects)


def _compose_supporting_drawing_group_paint(group: list[Event], coverage: SupportingDrawingCoverage) -> tuple[str,int] | None:
    """Compose coincident copies, then area-average distinct strips including transparent coverage."""
    union,clip_groups,rects = coverage.union,coverage.clip_groups,coverage.rectangles
    if union:
        paints = [compose_drawing_paint(clip_group) for clip_group in clip_groups.values()]
        weights = [(r[2]-r[0])*(r[3]-r[1]) for r in rects]
        active = [(paint, weight) for paint, weight in zip(paints, weights) if paint]
        # Average the composed paint of each distinct strip, including
        # transparent strips, rather than counting coincident copies as
        # overlapping partitions of the gradient.
        area = sum(weights)
        ink = sum(weight * (255-alpha) for (color, alpha), weight in active)
        alpha = round(255-ink/area)
        if alpha >= 254:
            return None
        channels = [round(sum(weight*(255-a)*((int(c, 16) >> shift) & 255)
                              for (c, a), weight in active)/ink)
                    for shift in (16, 8, 0)]
    else:
        paint = compose_drawing_paint(group)
        if paint is None:
            return None
        color, alpha = paint
        channels = [(int(color, 16) >> shift) & 255 for shift in (16, 8, 0)]
    color = ''.join(f'{v:02X}' for v in channels)
    return color,alpha


def _render_supporting_drawing_group(group: list[Event], union: tuple | None, color: str, alpha: int) -> Event:
    """Render composed fill at the normalized static pose with the original minimum source ID."""
    first = group[0]
    # Preserve the static pose and path after exact alignment normalization
    # and the simple same-colour rectangular-stroke expansion above.
    st = dict(first.state)
    st.update({'1c': color, '1a': alpha, '2a': alpha, '3a': 255, '4a': 255,
               'bord': 0, 'xbord': 0, 'ybord': 0, 'shad': 0,
               'xshad': 0, 'yshad': 0, 'blur': 0, 'be': 0})
    if union:
        st['clip'] = '('+','.join(f'{x:g}' for x in union)+')'
    else:
        st.pop('clip', None)
    keys = ('an', 'pos', 'org', 'p', 'fscx', 'fscy', 'frz', 'fry',
            'bord', 'shad', 'xbord', 'ybord', 'xshad', 'yshad',
            '1c', '1a', '2a', '3a', '4a', 'clip')
    tags = ''.join(render_tag(k, st[k]) for k in keys if k in st)
    event = replace_event(first, text='{'+tags+'}'+OVERRIDE_RE.sub('', first.text),
                          source_index=min(e.source_index for e in group))
    return event


def _reduce_supporting_drawing_groups(groups: dict, context: SupportingDrawingContext) -> list[Event]:
    """Reduce only coverage-proven visible groups and retain strip/duplicate count semantics."""
    output = []
    for group in groups.values():
        coverage = _prove_supporting_drawing_strip_coverage(group,context)
        if coverage is None:
            continue
        paint = _compose_supporting_drawing_group_paint(group,coverage)
        if paint is None:
            continue
        color,alpha = paint
        event = _render_supporting_drawing_group(group,coverage.union,color,alpha)
        output.append(event)
        context.counts['drawing_strips_collapsed' if coverage.union else 'drawing_duplicates_removed'] += len(group)-1
    return output


def _reduce_supporting_drawing_sequences(output: list[Event], context: SupportingDrawingContext) -> list[Event]:
    """Use existing layer/sequence reducers only within identical pose and original-contour families."""
    # Existing helper removes exact opaque layers. Restrict sequence merging
    # to identical poses: its general path can otherwise freeze moving signs.
    output, removed = reduce_vector_layers(output)
    context.counts['drawing_duplicates_removed'] += removed
    poses = {}
    for e in output:
        poses.setdefault((e.style, e.name, e.layer, geometry_key(e.text),
                          state_key(e, {'1a', '2a', '3a', '4a'}),
                          context.original_contours.get(e.source_index)), []).append(e)
    output = []
    for family in poses.values():
        family, removed = freeze_vector_sequences(family)
        output.extend(family)
        context.counts['drawing_fade_frames_removed'] += removed
    return output


def _finalize_supporting_drawings(output: list[Event], context: SupportingDrawingContext) -> tuple[list[Event],dict]:
    """Attach temporary original-contour evidence and return source-ordered candidates/counters."""
    context.counts['drawing_candidates'] = len(output)
    for e in output:
        if e.source_index in context.original_contours:
            # Retain source contours for subsequent caption-support coverage
            # checks. This evidence is separate from formatting and not serialized.
            e.evidence = EventEvidence(context.original_contours[e.source_index])
    return sorted(output, key=lambda e: e.source_index), context.counts


def reduce_supporting_drawings(sources, *, scaled_borders=True):
    """Reduce proved static primitives and clipped gradients, not moving UI."""
    counts = {'drawing_candidates': 0, 'drawing_strips_collapsed': 0,
              'drawing_duplicates_removed': 0, 'drawing_fade_frames_removed': 0,
              'unsupported_drawings_excluded': 0, 'drawing_contours_simplified': 0,
              'drawing_scale_exits_frozen': 0, 'drawing_move_entrances_frozen': 0,
              'drawing_edge_slivers_detached': 0}
    paint_tags = {'c', '1c', '2c', '3c', '4c', 'alpha', '1a', '2a', '3a', '4a',
                  'bord', 'xbord', 'ybord', 'shad', 'xshad', 'yshad', 'blur', 'be'}
    context = SupportingDrawingContext(scaled_borders,counts,paint_tags,{})
    groups = _index_supporting_drawing_candidates(sources,context)
    output = _reduce_supporting_drawing_groups(groups,context)
    output = _reduce_supporting_drawing_sequences(output,context)
    return _finalize_supporting_drawings(output,context)

