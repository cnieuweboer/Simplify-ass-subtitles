"""Complete overlapping lyric-copy selection and its sparse visibility handoff."""
from __future__ import annotations

from dataclasses import replace as dataclass_replace
from .event_model import Event
from .caption_clearance import (
    _caption_implicit_anchor, _glyph_replacement_row_is_clear,
    _caption_order_is_unchanged as _copy_order_is_unchanged,
)
from .caption_geometry import caption_bounds, get_pos, placement_key
from .static_selection import select_static_state
from .caption_rendering import render_simplified_caption, _source_caption_paint
from .event_operations import replace_event, _frame_pose_key
from .frame_pose import _preserve_frame_pose_support
from .subtitle_document import format_time
from .text_visibility import TextVisibilityResult
from .font_metrics import FontMetrics


def _original_copy_components(group: list[Event]) -> list[list[Event]]:
    """Connected original overlap evidence; points cannot create a link."""
    pending = {e.source_index:e for e in group if e.duration > 0}
    components = []
    while pending:
        seed = pending.pop(min(pending))
        component, frontier = [seed], [seed]
        while frontier:
            anchor = frontier.pop()
            peers = [e for e in pending.values() if
                     min(anchor.end_s,e.end_s)-max(anchor.start_s,e.start_s) >=
                     .8*min(anchor.duration,e.duration)]
            for peer in peers:
                pending.pop(peer.source_index)
                component.append(peer)
                frontier.append(peer)
        components.append(component)
    for point in (e for e in group if e.duration == 0):
        owners = [component for component in components if
                  any(e.start_s <= point.start_s <= e.end_s for e in component)]
        if len(owners) == 1:
            owners[0].append(point)
    return [sorted(component,key=lambda e:e.source_index) for component in components]


def _copy_peer_is_clear(family: list[Event], other: Event, visible_map,
                        font_metrics: FontMetrics | None) -> bool:
    """Borrow the shared measured ink proof, without voting on family paint."""
    if font_metrics is None:
        return False
    best = max(family,key=lambda e:(visible_map[e.source_index].count(' '),
                                   e.effect == '',-e.source_index))
    # Paint voting preserves the preferred original geometry. Bound the ordinary
    # renderer's geometry (including shadow transfer) and original stroke ink.
    probe = replace_event(best,text=render_simplified_caption(
        best.state,visible_map[best.source_index],measurement=best.measurement))
    probe,available = _caption_implicit_anchor(probe)
    if probe is None:
        return False
    try:
        layer = int(other.layer)
    except ValueError:
        layer = 0
    # Geometry query only: include this peer in the primitive's layer range.
    probe = dataclass_replace(probe,layer=str(layer))
    box = caption_bounds(probe,font_metrics) if available is not None else None
    if available is not None and (box is None or box[2]-box[0] > available):
        return False
    core = min(e.start_s for e in family),max(e.end_s for e in family)
    return _glyph_replacement_row_is_clear(probe,core,
        {e.source_index for e in family},layer,{other.source_index:other},
        font_metrics,family+[probe])


def _copy_output_layer(family: list[Event], events: list[Event], visible_map,
                       order: dict[int,tuple[int,int] | None],
                       font_metrics: FontMetrics | None) -> str:
    """Retain layer normalization only where it cannot cross independent ink."""
    first = min(family,key=lambda e:e.source_index)
    original = order[first.source_index]
    if original is None:
        return first.layer
    normalized = 0,original[1]
    if original == normalized:
        return '0'
    members = {e.source_index for e in family}
    core = min(e.start_s for e in family),max(e.end_s for e in family)
    for other in events:
        if (other.kind != 'Dialogue' or other.duration <= 0 or
                other.source_index in members or
                other.start_s >= core[1] or other.end_s <= core[0]):
            continue
        if _copy_order_is_unchanged(family,other,order,normalized):
            continue
        if not _copy_peer_is_clear(family,other,visible_map,font_metrics):
            return first.layer
    return '0'


def _copy_subfamilies(component: list[Event], events: list[Event], visible_map,
                      order: dict[int,tuple[int,int] | None],
                      font_metrics: FontMetrics | None) -> list[list[Event]]:
    """Keep independent ink between original planes when clearance is unproved.

    Uncontested paint order needs no measurements. A measured disjoint peer is
    not a barrier. Otherwise split at its actual layer/list position, retaining
    only original connected matches on each side. No rendered union is matched.
    """
    members = {e.source_index for e in component}
    pending, accepted = [component], []
    while pending:
        family = pending.pop()
        if len(family) < 2:
            accepted.append(family)
            continue
        core = min(e.start_s for e in family),max(e.end_s for e in family)
        first = min(family,key=lambda e:e.source_index)
        ranks = [order[e.source_index] for e in family]
        for other in events:
            if (other.kind != 'Dialogue' or other.duration <= 0 or
                    other.source_index in members or
                    other.start_s >= core[1] or other.end_s <= core[0]):
                continue
            rank = order[other.source_index]
            known = rank is not None and all(r is not None for r in ranks)
            if _copy_order_is_unchanged(family,other,order,order[first.source_index]):
                continue
            clear = _copy_peer_is_clear(family,other,visible_map,font_metrics)
            if clear:
                continue
            if known:
                sides = [[e for e in family if (order[e.source_index] < rank) == before]
                         for before in (True,False)]
                for side in sides:
                    pending.extend(_original_copy_components(side))
            else:
                # Unknown layer order cannot authorize moving text across ink.
                pending.extend([e] for e in family)
            # A smaller family can select another geometry. Check every foreign
            # peer again for each child; only original membership is refined.
            break
        else:
            accepted.append(family)
    return sorted(accepted,key=lambda family:min(e.source_index for e in family))


def collapse_full_lyric_copies(events: list[Event],
                               visible_map: dict[int, str], *,
                               font_metrics: FontMetrics | None = None) -> TextVisibilityResult:
    """Collapse overlapping full-line copies and return accepted caption text.

    Discover connected original families before discarding any match links.
    Each accepted family selects paint once; replacement spans never vote or
    authorize further removals. Borrow the visibility history without copying it.
    """
    visibility_updates: dict[int,str] = {}
    def norm(value: str) -> str:
        return "".join(value.split()).casefold()

    grouped: dict[tuple[str, str, str, int | None], list[Event]] = {}
    for e in events:
        visible = visible_map.get(e.source_index, "")
        if (e.kind == "Dialogue" and e.lyric and
                bool(norm(visible))):
            pos = get_pos(e.text)
            band = e.row if pos is not None else None
            grouped.setdefault((e.style, e.name, norm(visible), band, get_pos(e.text), placement_key(e)), []).append(e)

    removed: set[int] = set()
    replacements: dict[int, Event] = {}
    order = {}
    for index,event in enumerate(events):
        try:
            order[event.source_index] = int(event.layer),index
        except ValueError:
            order[event.source_index] = None
    for group in grouped.values():
        families = [family for component in _original_copy_components(group)
                    for family in _copy_subfamilies(component,events,visible_map,order,font_metrics)]
        for cluster in families:
            if len(cluster) < 2:
                continue
            # Prefer the author's spaced lyric when both a generated row and a
            # full-line copy exist, rather than keeping the inferred spacing.
            best = max(cluster, key=lambda item: (
                visible_map[item.source_index].count(" "),
                item.effect == "", -item.source_index))
            first = min(cluster, key=lambda item: item.source_index)
            earlier = min(item.start_s for item in cluster)
            later = max(item.end_s for item in cluster)
            state = select_static_state(best.state,[],set(),best.styles,best.defaults,
                                        paint_events=cluster,continuation=best.continuation).state
            text = render_simplified_caption(state, visible_map[best.source_index],
                                      outline_states=[e.state for e in cluster],measurement=best.measurement,
                                      source_paint=_source_caption_paint(state,[best.state]) if
                                      max(best.state.get(k,best.state.get('bord',0)) for k in ('xbord','ybord')) > 0 and
                                      best.state.get('3a',0) < 255 else
                                      _source_caption_paint(state,[e.state for e in cluster]))
            caption = replace_event(
                first, layer=_copy_output_layer(cluster,events,visible_map,order,font_metrics),
                start=format_time(earlier), end=format_time(later),
                start_s=earlier, end_s=later, effect="",
                text=text)
            # Paint selection can choose another member's font geometry. Use a
            # compatible original as the pose reference, never a rendered union.
            pose_key = _frame_pose_key(caption)
            pose_source = next((item for item in [best] + cluster
                                if _frame_pose_key(item) == pose_key), best)
            replacements[first.source_index] = _preserve_frame_pose_support(pose_source,caption,cluster)
            visibility_updates[first.source_index] = visible_map[best.source_index]
            removed.update(item.source_index for item in cluster if item != first)

    return TextVisibilityResult([replacements.get(e.source_index, e) for e in events
            if e.source_index not in removed],len(removed),visibility_updates)
