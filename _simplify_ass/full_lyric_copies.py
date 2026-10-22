"""Complete overlapping lyric-copy selection and its sparse visibility handoff."""
from __future__ import annotations

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

    Discover families from original anchors before discarding any match links.
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
    for group in grouped.values():
        # All original anchors get a proposal, including sources that the old
        # greedy walk could absorb before discovering their complete family.
        # Prefer the most supported original family, then authored source order.
        # Store only proposal sizes, not a quadratic table of source references.
        def matches(anchor: Event, other: Event) -> bool:
            return (other.duration >= 0 and
                    min(anchor.end_s, other.end_s) - max(anchor.start_s, other.start_s) >=
                    0.8 * min(anchor.duration, other.duration))

        proposals = sorted(
            ((sum(matches(anchor, other) for other in group), anchor)
             for anchor in group if anchor.duration > 0),
            key=lambda item: (-item[0], item[1].source_index))
        for size, e in proposals:
            if size < 2:
                break
            if e.source_index in removed:
                continue
            cluster = sorted((other for other in group if other.source_index not in removed
                              and other.source_index not in replacements and matches(e, other)),
                             key=lambda item: item.source_index)
            # A retained representative is claimed too. Neither it nor its
            # originals may participate in a second family in this invocation.
            if e.source_index in replacements:
                continue
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
                first, layer="0", start=format_time(earlier), end=format_time(later),
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
