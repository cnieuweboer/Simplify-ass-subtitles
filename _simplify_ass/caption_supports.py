"""Caption-support association, ownership, fallback and final layer settling.

Inputs stay borrowed and bounds/association buffers stay local. Callers retain
reduction, budgets, output assembly, invocation order and reporting.
"""
from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass, replace as dataclass_replace

from .ass_overrides import OVERRIDE_RE
from .font_metrics import FontMetrics
from .event_model import Event
from .drawing_geometry import (
    coverage_geometry, polygon_covers_box, drawing_polygon,
    normalize_drawing_alignment, flatten_rectangular_border, caption_clip_outline,
)
from .paint_normalization import normalize_shadow_lettering
from .event_operations import replace_event
from .static_objects import static_object_key
from .caption_geometry import caption_bounds, get_pos, text_height, rectangle_clip


@dataclass(frozen=True)
class CaptionPanelOwnership:
    """A measured enclosing relationship; borrowed panel and caption records."""
    panel: Event
    caption: Event


@dataclass
class CaptionSupportResult:
    """Selected supports, their caption associations and output ordering."""
    events: list[Event]
    kept: list[Event]
    fallback: list[Event]
    associated: dict
    removed_textures: set[int]
    counts: dict[str,int]
    # None accepts older direct constructors; production always supplies proof.
    ownership: list[CaptionPanelOwnership] | None = None


def is_fullscreen_background(event):
    """Prove that a static fill covers the viewport, including its clip."""
    info = coverage_geometry(event)
    canvas = event.measurement.canvas
    if info is None or canvas is None:
        return False
    width, height = canvas
    if width <= 0 or height <= 0:
        return False
    eps = 1e-4*event.unit
    viewport = (eps, eps, width-eps, height-eps)
    clip = rectangle_clip(event)
    if 'clip' in event.state and (clip is None or not all((
            clip[0] <= viewport[0], clip[1] <= viewport[1],
            clip[2] >= viewport[2], clip[3] >= viewport[3]))):
        return False
    return polygon_covers_box(info[0], viewport)


def drawing_matches_caption_outline(panel, caption, points=None):
    """Match a text mask to its panel while rejecting a displaced reuse."""
    mask = caption_clip_outline(caption)
    raw_points = drawing_polygon(panel)
    if mask is None or raw_points is None or 'clip' in panel.state:
        return False
    scale = 2**(panel.state.get('p', 1)-1)
    outline = tuple((x/scale, y/scale) for x, y in raw_points)
    anchor = get_pos(caption.text)
    if points is None:
        info = coverage_geometry(panel)
        points = info[0] if info is not None else None
    return (mask == outline and points is not None and anchor is not None and
            polygon_covers_box(list(mask), (*anchor, *anchor)) and
            polygon_covers_box(points, (*anchor, *anchor)))


def caption_panel_contains(panel: Event, points: list | None, caption: Event, box: tuple | None) -> bool:
    """Prove measured ink inside current and original fill, respecting panel clips.

    This is spatial/family evidence, not a timing, ordering or opacity proof.
    Those obligations differ between support admission and final promotion.
    """
    original = panel.evidence.original_contour_points
    clip = rectangle_clip(panel)
    return (box is not None and points is not None and
            panel.style == caption.style and panel.name == caption.name and
            polygon_covers_box(points, box) and
            polygon_covers_box(list(original if original is not None else points), box) and
            (clip is None or clip[0] < box[0] and clip[1] < box[1] and
             clip[2] > box[2] and clip[3] > box[3]))


def _caption_panel_ownership(kept: list[Event], associated: dict,
                             metric: FontMetrics | None) -> list[CaptionPanelOwnership]:
    """Carry enclosing ownership; adjacency/fullscreen associations are not owners."""
    ownership = []
    boxes = {}
    for panel in kept:
        geometry = coverage_geometry(panel)
        if (geometry is None or not geometry[2] or is_fullscreen_background(panel) or
                static_object_key(panel, panel.styles) is None):
            continue
        for caption in associated.get(panel.source_index, ()):
            if (not any(c.isalnum() for c in OVERRIDE_RE.sub('', caption.text)) or
                    not caption.layer.lstrip('-').isdigit() or int(panel.layer) > int(caption.layer)):
                continue
            if id(caption) not in boxes:
                boxes[id(caption)] = caption_bounds(caption, metric)
            if caption_panel_contains(panel, geometry[0], caption, boxes[id(caption)]):
                ownership.append(CaptionPanelOwnership(panel, caption))
    return ownership


def _select_enclosing_caption_panels(caption, box, candidates, geometry, fullscreen_ids):
    """Prove local coverage or shared masks and choose supports for every occupied interval."""
    mask = caption_clip_outline(caption)
    if box is None and mask is None:
        return []
    enclosing = []
    for e in candidates:
        if (e.source_index in fullscreen_ids or
                e.source_index not in geometry or e.style != caption.style or
                e.name != caption.name or not e.layer.lstrip('-').isdigit() or
                not caption.layer.lstrip('-').isdigit() or
                int(e.layer) > int(caption.layer)):
            continue
        overlap = min(e.end_s, caption.end_s)-max(e.start_s, caption.start_s)
        if overlap <= 0:
            continue
        # Backdrops need only support the text while both are visible.
        # Preserve source timing; no minimum percentage or maximum gap.
        points, bounds = geometry[e.source_index]
        contained = caption_panel_contains(e, points, caption, box)
        # Authored reuse of the same simple path is explicit panel/mask
        # evidence even for rotated, sheared or projective lettering.
        # Both must contain the text anchor in rendered scene space: a
        # reused shape parked elsewhere is not a supporting panel.
        shared_outline = mask is not None and drawing_matches_caption_outline(e, caption, points)
        if contained or shared_outline:
            enclosing.append((e, contained))
    if enclosing:
        # Choose the uppermost local support separately for each occupied
        # interval. A later panel cannot erase an earlier panel that is
        # the text's only support before or after their shared interval.
        times = sorted({caption.start_s, caption.end_s} |
                       {t for e, _ in enclosing for t in
                        (max(e.start_s, caption.start_s),
                         min(e.end_s, caption.end_s))})
        winners = {}
        for start, end in zip(times, times[1:]):
            top = max(((e, measured) for e, measured in enclosing
                       if e.start_s < end and e.end_s > start),
                      key=lambda item: (int(item[0].layer), item[0].source_index), default=None)
            if top is not None:
                winners[top[0].source_index] = top
        return list(winners.values())
    return []


def _match_adjacent_caption_shapes(candidates, nearby, geometry, fullscreen_ids, selected):
    """Associate unselected sparse decorative shapes without changing established panel choices."""
    # Adjacent arrows and small polygon patches are useful even when they are
    # not backgrounds enclosing text. Reject dense drawings and lyric regions.
    sparse = collections.Counter((e.start, e.end, e.style, e.name) for e in candidates
                                 if e.source_index not in fullscreen_ids)
    adjacent = {}
    for e in candidates:
        if (e.source_index in selected or e.source_index in adjacent or
                e.source_index not in geometry):
            continue
        points, bounds = geometry[e.source_index]
        primitive = drawing_polygon(e)
        if (e.duration < .12 or sparse[(e.start, e.end, e.style, e.name)] > 8 or
                e.evidence.original_contour_points is not None or
                primitive is None or len({x for x, y in primitive}) == 2 and
                len({y for x, y in primitive}) == 2):
            continue
        for caption, box in nearby:
            overlap = min(caption.end_s, e.end_s)-max(caption.start_s, e.start_s)
            if (caption.style != e.style or caption.name != e.name or
                    overlap < .8*min(caption.duration, e.duration)):
                continue
            height = text_height(caption)
            dx = max(box[0]-bounds[2], bounds[0]-box[2], 0)
            dy = max(box[1]-bounds[3], bounds[1]-box[3], 0)
            if (math.hypot(dx, dy) <= 1.5*height and
                    bounds[2]-bounds[0] <= 5*height and
                    bounds[3]-bounds[1] <= 5*height):
                adjacent[e.source_index] = [caption]
                break
    return adjacent


def select_caption_supports(candidates, captions, metric):
    """Preserve the established two-result support-selection API."""
    kept, associated, _ = _select_caption_supports(candidates, captions, metric)
    return kept, associated


def _select_caption_supports(candidates, captions, metric) -> tuple[list[Event], dict, list[CaptionPanelOwnership]]:
    """Keep fullscreen fills and the uppermost local support in each interval.

    Adjacency is only considered for small, straight, non-rectangular shapes
    in a sparse sign group. It does not imply video coverage or text recovery.
    """
    eligible = [e for e in captions
             if e.kind == 'Dialogue' and not e.state.get('p', 0) and
             bool(OVERRIDE_RE.sub('', e.text).strip()) and not e.lyric]
    boxes = {e.source_index: caption_bounds(e, metric) for e in eligible}
    nearby = [(e, caption_bounds(e, metric, adjacency=True)) for e in captions
              if e.kind == 'Dialogue' and not e.state.get('p', 0) and
              len(OVERRIDE_RE.sub('', e.text).strip()) >= 2 and not e.lyric]
    nearby = [(e, box) for e, box in nearby if box is not None]
    geometry = {}
    for e in candidates:
        info = coverage_geometry(e)
        if info is not None:
            points, bounds, _ = info
            xs, ys = zip(*points)
            box = (min(xs), min(ys), max(xs), max(ys))
            geometry[e.source_index] = points, box
        elif rectangle_clip(e) is not None:
            # Scene-coordinate clip bounds also bound rotated/aligned paths.
            # They are sufficient for adjacency, but cannot prove fill coverage.
            geometry[e.source_index] = None, rectangle_clip(e)
    fullscreen_ids = {e.source_index for e in candidates if is_fullscreen_background(e)}
    selected, associated, enclosing_ids = set(fullscreen_ids), {}, set()
    measured_claims = []
    # Fullscreen fills do not compete with local panels or require font
    # measurement. Preserve source layers so both can sit beneath their text.
    for e in candidates:
        if e.source_index in fullscreen_ids:
            associated[e.source_index] = [caption for caption in captions
                if caption.kind == 'Dialogue' and caption.style == e.style and
                caption.name == e.name and not caption.state.get('p', 0) and
                min(caption.end_s, e.end_s) > max(caption.start_s, e.start_s)]
    for caption in eligible:
        for top, measured in _select_enclosing_caption_panels(
                caption, boxes[caption.source_index], candidates, geometry, fullscreen_ids):
            selected.add(top.source_index)
            enclosing_ids.add(top.source_index)
            associated.setdefault(top.source_index, []).append(caption)
            if measured and any(c.isalnum() for c in OVERRIDE_RE.sub('', caption.text)):
                measured_claims.append((top.source_index, caption))
    adjacent = _match_adjacent_caption_shapes(
        candidates, nearby, geometry, fullscreen_ids, selected)
    selected.update(adjacent)
    associated.update(adjacent)
    kept = []
    for e in candidates:
        if e.source_index not in selected:
            continue
        if (e.source_index in enclosing_ids and
                e.evidence.original_contour_points is not None):
            # Reconstructed enclosing panels hide the picture behind a caption.
            # Their original translucent paint may have depended on discarded
            # scene artwork underneath. Keep the simplified contour, colour
            # and pose, but make these enclosing panels opaque. Gradient bands
            # and adjacent decorative shapes retain their original opacity.
            e = replace_event(e, text=re.sub(r'\\([12])a&H[0-9a-f]+&',
                                            r'\\\1a&H00&', e.text, flags=re.I),
                              evidence=e.evidence)
        kept.append(e)
    # Retain the already proved measured relationship. Alpha normalization
    # changes paint, not the contour; do not repeat font/polygon containment.
    qualified = {e.source_index: e for e in kept if
                 e.source_index in enclosing_ids and
                 (info := coverage_geometry(e)) is not None and info[2] and
                 static_object_key(e, e.styles) is not None}
    ownership = [CaptionPanelOwnership(qualified[index], caption)
                 for index, caption in measured_claims if index in qualified]
    return kept, associated, ownership


def retain_unmeasured_backdrops(events, captions, kept, metric, *, scaled_borders=True):
    """Preserve baseline supports for unknown text, without equivalent copies."""
    caption_groups = {}
    for caption in captions:
        if (caption.kind == 'Dialogue' and not caption.state.get('p', 0) and
                OVERRIDE_RE.sub('', caption.text).strip()):
            caption_groups.setdefault((caption.style, caption.name), []).append(
                (caption, caption_bounds(caption, metric)))
    def fill_key(event):
        # Compare rendered fill footprints, not header spelling or unused
        # shadow/outline alpha. Never equate extra visible stroke/shadow paint.
        event = normalize_drawing_alignment(flatten_rectangular_border(
            event, scaled_borders=scaled_borders))
        st = event.state
        if (drawing_polygon(event) is None or st.get('1a', 0) >= 254 or
                st.get('3a', 0) < 254 and any(st.get(k, st.get('bord', 0))
                                            for k in ('xbord', 'ybord')) or
                st.get('4a', 0) < 254 and any(st.get(k, st.get('shad', 0))
                                            for k in ('xshad', 'yshad')) or
                'iclip' in st or 'clip' in st and rectangle_clip(event) is None):
            return None
        info = coverage_geometry(event)
        if info is None:
            return None
        points = tuple((round(x, 6), round(y, 6)) for x, y in info[0])
        if points[-1] == points[0]:
            points = points[:-1]
        polygon = min(order[i:]+order[:i] for order in (points, points[::-1])
                      for i in range(len(points)))
        return (event.start, event.end, event.layer, event.style, event.name,
                st.get('1c'), st.get('1a', 0), polygon, rectangle_clip(event))
    equivalents = {key for event in kept if (key := fill_key(event)) is not None}
    fullscreen_paints = {(v.start, v.end, v.layer, v.style, v.name,
                          v.state.get('1c'), v.state.get('1a', 0))
                         for v in kept if is_fullscreen_background(v)}
    fallback = []
    for event in events:
        if event.kind != 'Dialogue' or not event.state.get('p', 0):
            continue
        overlapping = [(caption, box) for caption, box in
                       caption_groups.get((event.style, event.name), [])
                       if min(caption.end_s, event.end_s) > max(caption.start_s, event.start_s)]
        # A known caption elsewhere cannot disprove the support needed by an
        # unknown caption in the same group. Retain the existing fallback
        # whenever any overlapping caption remains unmeasurable.
        if overlapping and all(box is not None for caption, box in overlapping):
            continue
        key = fill_key(event)
        if key is not None and key in equivalents:
            continue
        if (is_fullscreen_background(event) and
                (event.start, event.end, event.layer, event.style, event.name,
                 event.state.get('1c'), event.state.get('1a', 0)) in fullscreen_paints):
            continue
        fallback.append(event)
    return fallback


def _rectangle_polygon(points: list) -> bool:
    xs, ys = {x for x,y in points}, {y for x,y in points}
    return len(xs) == len(ys) == 2 and set(points) == {(x,y) for x in xs for y in ys}


def _same_caption_panel(panel: Event, points: list, owner: Event, owner_points: list) -> bool:
    """Match a panel footprint, allowing its existing stroke/rounding allowance."""
    if panel is owner or points == owner_points:
        return True
    if not _rectangle_polygon(points) or not _rectangle_polygon(owner_points):
        return False
    tolerance = max(2., 2*min(panel.unit, owner.unit))
    bounds = lambda ps: (min(x for x,y in ps), min(y for x,y in ps),
                         max(x for x,y in ps), max(y for x,y in ps))
    return all(abs(a-b) <= tolerance for a,b in zip(bounds(points), bounds(owner_points)))


def _covered_caption_panels(panels: list) -> set[tuple]:
    """Prove hidden rectangular fills separately from caption ownership/layering."""
    hidden = set()
    for lower, low_points in panels:
        if not _rectangle_polygon(low_points) or any(lower.state.get(k, lower.state.get(base, 0)) != 0
                for k,base in (('xbord','bord'),('ybord','bord'),('xshad','shad'),('yshad','shad'))):
            continue
        for upper, up_points in panels:
            if (int(upper.layer) <= int(lower.layer) or upper.style != lower.style or upper.name != lower.name or
                    upper.start_s > lower.start_s or upper.end_s < lower.end_s or not _rectangle_polygon(up_points)):
                continue
            if (min(x for x,y in up_points) <= min(x for x,y in low_points) and
                    max(x for x,y in up_points) >= max(x for x,y in low_points) and
                    min(y for x,y in up_points) <= min(y for x,y in low_points) and
                    max(y for x,y in up_points) >= max(y for x,y in low_points)):
                hidden.add(tuple(lower.fields()))
                break
    return hidden


def settle_caption_backdrop_layers(
    supports: CaptionSupportResult, events: list[Event], font_metrics: FontMetrics | None,
) -> CaptionSupportResult:
    """Settle final opaque captions above already proved local backgrounds.

    Late shadow normalization can make a caption readable after the text-stage
    layer proof. Only retained enclosing panels, full-lifetime exact-font
    coverage and identical style/actor authorize promotion. Adjacent decorations,
    fullscreen fills and unmeasured supports keep their source order.
    """
    if font_metrics is None or not font_metrics.available:
        return dataclass_replace(supports, events=events)

    # Production carries the proof from support selection. Older direct
    # constructors can establish it once; later reassociation never invents it.
    ownership = (supports.ownership if supports.ownership is not None else
                 _caption_panel_ownership(supports.kept, supports.associated, font_metrics))
    retained = {tuple(panel.fields()): panel for panel in supports.kept}
    panels, owners, normalized_ownership = {}, {}, []
    geometries, captions = {}, {}
    for relation in ownership:
        panel = relation.panel
        if id(panel) not in geometries:
            geometries[id(panel)] = coverage_geometry(panel)
        geometry = geometries[id(panel)]
        if geometry is None:
            continue
        points = geometry[0]
        if id(relation.caption) not in captions:
            normalized,_ = normalize_shadow_lettering([relation.caption])
            captions[id(relation.caption)] = normalized[0]
        caption = captions[id(relation.caption)]
        normalized_ownership.append(CaptionPanelOwnership(panel, caption))
        owners.setdefault(tuple(caption.fields()), []).append((panel, points))
        if tuple(panel.fields()) in retained:
            actual = retained[tuple(panel.fields())]
            panels[tuple(actual.fields())] = (actual, points)
    panels = list(panels.values())
    if not panels:
        return dataclass_replace(supports, events=events, ownership=list(ownership))
    families = {}
    for panel, points in panels:
        families.setdefault((panel.style, panel.name), []).append((panel, points))

    settled = []
    drawing_order = {tuple(event.fields()): index for index,event in enumerate(events) if event.state.get('p', 0)}
    for index,event in enumerate(events):
        if (event.kind != 'Dialogue' or event.state.get('p', 0) or
                not event.layer.lstrip('-').isdigit() or event.state.get('1a', 0) != 0 or
                (event.style, event.name) not in families or
                tuple(event.fields()) not in owners or
                not any(c.isalnum() for c in OVERRIDE_RE.sub('', event.text)) or
                get_pos(event.text) is None or static_object_key(event, event.styles) is None):
            settled.append(event)
            continue
        box = caption_bounds(event, font_metrics)
        layer = int(event.layer)
        # Preserve an independent card/mask already painted above this text.
        # Promoting merely to its layer can also expose a later text record.
        if box is not None and any(
            (int(panel.layer), drawing_order.get(tuple(panel.fields()), -1)) > (layer, index) and
            min(panel.end_s,event.end_s) > max(panel.start_s,event.start_s) and
            (not any(_same_caption_panel(panel,points,owner,owner_points)
                     for owner,owner_points in owners[tuple(event.fields())]) or
             panel.start_s > event.start_s+.001 or panel.end_s < event.end_s-.001) and
            min(x for x,y in points) < box[2] and max(x for x,y in points) > box[0] and
            min(y for x,y in points) < box[3] and max(y for x,y in points) > box[1]
            for panel,points in families[event.style,event.name]):
            settled.append(event)
            continue
        for panel, points in families[event.style, event.name]:
            if (panel.start_s <= event.start_s + .001 and panel.end_s >= event.end_s - .001 and
                    any(_same_caption_panel(panel, points, owner, owner_points)
                        for owner, owner_points in owners[tuple(event.fields())]) and
                    caption_panel_contains(panel, points, event, box)):
                layer = max(layer, int(panel.layer) + 1)
        settled.append(replace_event(event, layer=str(layer)) if layer != int(event.layer) else event)

    successors = {tuple(old.fields()): new for old,new in zip(events, settled)}
    ownership = [CaptionPanelOwnership(relation.panel, successors[tuple(relation.caption.fields())])
                 for relation in normalized_ownership if tuple(relation.caption.fields()) in successors]

    # Remove a lower rectangular support only when a retained opaque rectangle
    # covers all of its fill for its entire lifetime. Partial masks remain.
    hidden = _covered_caption_panels(panels)
    kept = [panel for panel in supports.kept if tuple(panel.fields()) not in hidden]
    settled = [event for event in settled if not (event.state.get('p', 0) and tuple(event.fields()) in hidden)]
    associated = {panel.source_index: [event for event in settled
        if event.kind == 'Dialogue' and not event.state.get('p', 0) and
        event.layer.lstrip('-').isdigit() and int(panel.layer) <= int(event.layer) and
        event.style == panel.style and event.name == panel.name and
        min(event.end_s, panel.end_s) > max(event.start_s, panel.start_s) and
        caption_panel_contains(panel, geometry[0], event, caption_bounds(event, font_metrics))]
        for panel in kept if (geometry := coverage_geometry(panel)) is not None}
    # Preserve associations for non-enclosing arrows/fullscreen/fallback shapes.
    for panel in kept:
        if not associated.get(panel.source_index):
            associated[panel.source_index] = list(supports.associated.get(panel.source_index, ()))
    counts = dict(supports.counts)
    counts['drawing_duplicates_removed'] += len(supports.kept) - len(kept)
    return dataclass_replace(supports, events=settled, kept=kept, associated=associated, counts=counts, ownership=ownership)
