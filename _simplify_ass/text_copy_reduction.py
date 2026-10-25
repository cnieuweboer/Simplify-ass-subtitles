"""Exact duplicate removal, strict redundancy and early static-sign paint selection.

Inputs stay borrowed; indexes, ranks and removal state belong to one call.
Callers retain stage order, lyric handoffs and aggregate reporting.
"""
from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right

from .ass_overrides import (
    OverrideContinuation, tokenize_override, resolve_event_style,
    apply_override, DEFAULT_STATE,
)
from .event_model import Event
from .static_objects import StaticSpanSignature, static_object_key
from .caption_geometry import get_pos, text_height, text_layout_key, compatible_text_layout


def event_identity_for_dedup(e: Event, visible: str) -> tuple:
    pos = get_pos(e.text)
    rounded_pos = None if pos is None else (round(pos[0] / e.unit, 1) * e.unit, round(pos[1] / e.unit, 1) * e.unit)
    return (
        e.layer, e.start, e.end, e.style, e.name,
        e.margin_l, e.margin_r, e.margin_v,
        visible, rounded_pos, text_layout_key(e), e.text,
    )


def has_translucent_paint(e: Event) -> bool:
    """Keep compositing evidence whenever a literal span uses partial alpha.

    Check all paint channels conservatively, including styles and inline
    resets. The cached final state cannot describe an earlier painted span.
    Animated alpha is also unsafe until the normal freezing pass resolves it.
    Fully hidden channels cannot accumulate visible paint.
    """
    default = resolve_event_style(e.styles, e.style, e.defaults or DEFAULT_STATE)
    state = default.copy()
    continuation = OverrideContinuation()
    for part in re.split(r'(\{[^}]*\})', e.text):
        if part.startswith('{') and part.endswith('}'):
            for name, value in tokenize_override(part[1:-1]):
                if name in {'t', 'fad', 'fade', 'k', 'kf', 'ko', 'kt'}:
                    return True
                continuation = apply_override(state,name,value,e.styles,default,continuation)
        elif part and any(state.get(f'{channel}a', 0) not in (0, 255)
                          for channel in range(1, 5)):
            return True
    return False


def deduplicate_layers(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Collapse positioned duplicates without losing translucent compositing."""
    seen: dict[tuple, Event] = {}
    output: list[Event] = []
    removed = 0
    for e in events:
        if e.kind != "Dialogue":
            output.append(e)
            continue
        visible = visible_map.get(e.source_index, "")
        # Equal unpositioned text records can render on separate rows because
        # the renderer resolves collisions. Keep their original multiplicity;
        # later paint-copy stages require their own evidence before merging.
        # Drawings do not participate in text collision placement.
        if get_pos(e.text) is None and not e.state.get("p", 0):
            output.append(e)
            continue
        key = event_identity_for_dedup(e, visible)
        if key in seen and not has_translucent_paint(e):
            removed += 1
            continue
        seen[key] = e
        output.append(e)
    return output, removed


def reduce_static_sign_copies(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Remove proven redundant nonlyrics, then select representative sign paint.

    Lyrics still need their source/row context. The final invocation of the
    same redundancy proof receives the finished records after reconstruction.
    Effect-layer paint selection is deliberately confined to this early stage.
    """
    events, redundant = remove_redundant_text_copies(events, pending_lyrics=True)
    events, effects = select_static_sign_paint(events, visible_map)
    return events, redundant + effects


def select_static_sign_paint(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Choose representative fill from nonlyric, near-coincident effect copies.

    Unlike strict redundancy, this deliberately permits different paint/layers
    and the existing small size variation. Emphasis and spacing must agree.
    """
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or e.lyric or get_pos(e.text) is None:
            continue
        visible = visible_map.get(e.source_index, "")
        if visible:
            groups.setdefault((e.style, e.name, e.margin_l, e.margin_r,
                               e.margin_v, visible), []).append(e)

    def alpha(e: Event) -> int:
        return e.state.get("1a",0)

    def rank(e: Event) -> tuple:
        return (alpha(e), -int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
                -e.duration, e.source_index)

    removed: set[int] = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        # Partial alpha still contributes beneath another copy. Preserve it
        # for the paint reconstruction stages rather than calling it covered.
        group = [e for e in group if not has_translucent_paint(e)]
        if len(group) < 2:
            continue
        ranks = {e.source_index: rank(e) for e in group}
        positions = {e.source_index: get_pos(e.text) for e in group}
        heights = {e.source_index: text_height(e) for e in group}
        # A covering copy must be within 6% of THIS event's height in x,
        # because the original bound uses the smaller of the two heights.
        # The sorted window is only a candidate index. Only retained records
        # provide coverage; removed anchors cannot authorize further drift.
        finite = all(math.isfinite(positions[e.source_index][0]) and
                     math.isfinite(heights[e.source_index]) for e in group)
        by_x = sorted(group,key=lambda e: positions[e.source_index][0]) if finite else group
        xs = [positions[e.source_index][0] for e in by_x] if finite else None
        for e in sorted(group, key=rank):
            x, y = positions[e.source_index]
            radius = math.nextafter(.06*heights[e.source_index],math.inf)
            # Expand the radius and endpoints by one floating-point step so
            # subtraction rounding (including cancellation) cannot exclude a
            # pair accepted by the original distance test.
            left = bisect_left(xs,math.nextafter(x-radius,-math.inf)) if xs is not None else 0
            right = bisect_right(xs,math.nextafter(x+radius,math.inf)) if xs is not None else len(by_x)
            for index in range(left,right):
                other = by_x[index]
                if (other is e or other.source_index in removed
                        or ranks[other.source_index] >= ranks[e.source_index]):
                    continue
                ox, oy = positions[other.source_index]
                if (_near_containing_text_copy(e, other, heights[e.source_index],
                                               heights[other.source_index])
                        and compatible_text_layout(e, other)
                        and all(e.state.get(k) == other.state.get(k) for k in
                                ('b', 'i', 'u', 's', 'fsp', 'q', 'org', 'pbo',
                                 'borderstyle', 'encoding'))):
                    removed.add(e.source_index)
                    break
    return [e for e in events if e.source_index not in removed], len(removed)


def _near_containing_text_copy(event: Event, other: Event, height: float,
                               other_height: float) -> bool:
    """Whole-lifetime coverage at a near anchor; no timing or anchor extension."""
    x, y = get_pos(event.text)
    ox, oy = get_pos(other.text)
    radius = .06 * min(height, other_height)
    return (math.isfinite(radius) and other.start_s <= event.start_s
            and other.end_s >= event.end_s and abs(x - ox) <= radius
            and abs(y - oy) <= radius)


def remove_late_complete_copies(events: list[Event]) -> tuple[list[Event], int]:
    """Apply strict redundancy after reconstructed text and paint are final."""
    return remove_redundant_text_copies(events)


def remove_redundant_text_copies(events: list[Event], *, pending_lyrics: bool = False) -> tuple[list[Event], int]:
    """Remove static, wholly covered text records with identical literal spans.

    Compare every literal span, including paint, parser history and document
    context. Only the anchor may differ, within the existing six-percent text
    height bound. Require equal layers and preserve intervening compositing.
    Retained records alone provide coverage, so offset chains cannot drift.
    Borrow records, styles and formatting caches without modifying them.
    """
    groups: dict[tuple, list[tuple[int, Event]]] = {}
    layers: dict[int | None, list[int]] = {}
    heights: dict[int, float] = {}
    wrapping: set[int] = set()
    for index, event in enumerate(events):
        try:
            layer = int(event.layer)
        except ValueError:
            layer = None
        if event.kind == 'Dialogue':
            layers.setdefault(layer, []).append(index)
        if layer is None or (pending_lyrics and event.lyric):
            continue
        pos = get_pos(event.text)
        if (pos is None or not all(math.isfinite(v) for v in pos)
                or has_translucent_paint(event)):
            continue
        key = static_object_key(event, event.styles)
        if key is None:
            continue
        runs, span_heights = [], []
        for signature, drawing, payload in key[-1]:
            state = dict(signature.formatting)
            if (drawing or state.get('pos') != pos or state.get('clip') is not None
                    or state.get('iclip') is not None):
                break
            span_heights.append(max(event.unit, abs(state.get('fs', 20) * state.get('fscy', 100) / 100)))
            if state.get('q', event.measurement.script_wrap_mode) != 2:
                wrapping.add(index)
            runs.append((StaticSpanSignature(tuple((k, v) for k, v in signature.formatting
                                                  if k != 'pos'), signature.continuation), payload))
        else:
            # Match the whole record, however short it is. This proves one
            # redundant copy, not that a fragment has become a complete line.
            if runs:
                heights[index] = min(span_heights)
                groups.setdefault((layer,) + key[1:-1] + (tuple(runs),), []).append((index, event))

    unknown = layers.get(None, ())
    if unknown:
        for layer, peers in layers.items():
            if layer is not None:
                peers.extend(unknown)
                peers.sort()

    removed: set[int] = set()
    for group in groups.values():
        retained: list[tuple[int, Event]] = []
        for index, event in sorted(group, key=lambda item: (-item[1].duration, item[0])):
            x, y = get_pos(event.text)
            for other_index, other in retained:
                ox, oy = get_pos(other.text)
                if (not _near_containing_text_copy(event, other, heights[index], heights[other_index])
                        # Translating an automatically wrapped line can change
                        # its available width and actual rendered line breaks.
                        or ((x != ox or y != oy) and (index in wrapping or other_index in wrapping))):
                    continue
                low, high = sorted((index, other_index))
                peers = layers[int(event.layer)]
                if any(peer not in removed and events[peer].start_s < event.end_s
                       and events[peer].end_s > event.start_s
                       for peer in peers[bisect_right(peers, low):bisect_left(peers, high)]):
                    continue
                removed.add(index)
                break
            else:
                retained.append((index, event))
    return [event for index, event in enumerate(events) if index not in removed], len(removed)

