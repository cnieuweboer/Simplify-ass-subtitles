"""Complete overlapping lyric-copy selection and its sparse visibility handoff."""
from __future__ import annotations

import collections

from .event_model import Event
from .caption_geometry import get_pos, placement_key
from .static_selection import select_static_state
from .caption_rendering import render_simplified_caption, _source_caption_paint
from .event_operations import replace_event, _frame_pose_key
from .frame_pose import _preserve_frame_pose_support
from .subtitle_document import format_time
from .text_visibility import TextVisibilityResult


def collapse_full_lyric_copies(events: list[Event],
                               visible_map: dict[int, str]) -> TextVisibilityResult:
    """Collapse overlapping full-line copies and return accepted caption text.

    A private overlay preserves pending text for later clusters without
    changing the borrowed map or copying its history.
    """
    visibility_updates: dict[int,str] = {}
    visible_map = collections.ChainMap(visibility_updates,visible_map)
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
    # Keep accepted originals independently of the replacements' expanded spans.
    # Matching and paint selection continue to use the original working events.
    source_families: dict[int, dict[int, Event]] = {}
    for group in grouped.values():
        for e in group:
            if e.source_index in removed:
                continue
            cluster = [other for other in group if other.source_index not in removed and
                       min(e.end_s, other.end_s) - max(e.start_s, other.start_s) >=
                       0.8 * min(e.duration, other.duration)]
            if len(cluster) < 2:
                continue
            # Prefer the author's spaced lyric when both a generated row and a
            # full-line copy exist, rather than keeping the inferred spacing.
            best = max(cluster, key=lambda item: (
                visible_map[item.source_index].count(" "),
                item.effect == "", -item.source_index))
            first = min(cluster, key=lambda item: item.source_index)
            sources = {item.source_index: item for item in cluster}
            for item in cluster:
                sources.update(source_families.pop(item.source_index, {}))
            earlier = min(item.start_s for item in sources.values())
            later = max(item.end_s for item in sources.values())
            state = select_static_state(best.state,[],set(),best.styles,best.defaults,
                                        paint_events=cluster,continuation=best.continuation).state
            text = render_simplified_caption(state, visible_map[best.source_index],
                                      outline_states=[e.state for e in cluster],measurement=best.measurement,
                                      source_paint=_source_caption_paint(state,[best.state]) if
                                      max(best.state.get(k,best.state.get('bord',0)) for k in ('xbord','ybord')) > 0 and
                                      best.state.get('3a',0) < 255 else
                                      _source_caption_paint(state,[e.state for e in cluster]))
            caption = replace_event(
                first, layer="0", start=format_time(earlier), end=format_time(later),
                start_s=earlier, end_s=later, effect="",
                text=text)
            # Prefer the selected original pose. Pending accepted text can need
            # its previous caption as reference; only originals supply dwell.
            pose_source = best
            if _frame_pose_key(best) != _frame_pose_key(caption):
                pose_source = replacements.get(best.source_index, best)
            replacements[first.source_index] = _preserve_frame_pose_support(pose_source,caption,sources.values())
            source_families[first.source_index] = sources
            visibility_updates[first.source_index] = visible_map[best.source_index]
            removed.update(item.source_index for item in cluster if item != first)

    return TextVisibilityResult([replacements.get(e.source_index, e) for e in events
            if e.source_index not in removed],len(removed),visibility_updates)
