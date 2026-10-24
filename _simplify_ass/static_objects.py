"""Complete static-span identity and ordered merging of touching phases.

Callers retain stage roles, source-evidence boundaries and report aggregation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import re

from .ass_overrides import (
    NUMBER, OVERRIDE_RE, OverrideContinuation, apply_override,
    resolve_event_style, tokenize_override,
)
from .caption_geometry import caption_bounds, get_pos
from .event_model import Event
from .event_operations import replace_event, state_key
from .font_metrics import FontMetrics
from .frame_pose import _preserve_frame_pose_support

@dataclass(frozen=True)
class StaticSpanSignature:
    """Literal formatting and parser history both participate in matching."""
    formatting: tuple
    continuation: OverrideContinuation


def geometry_key(text: str) -> tuple:
    """Compare vector tokens, not whitespace or decimal spelling."""
    raw = OVERRIDE_RE.sub("",text)
    return tuple(float(t) if re.fullmatch(NUMBER,t) else t.lower()
                 for t in re.findall(NUMBER+r"|[A-Za-z]",raw))


def static_object_key(e: Event, styles: dict, *,
                      allow_unpositioned: bool = False) -> tuple | None:
    """Describe every static text/drawing span, including inherited styling."""
    if e.kind != "Dialogue" or e.effect or e.duration <= 0:
        return None
    # Unpositioned subtitles participate in renderer collision placement.
    # Extending one could change that placement even with identical text.
    if not allow_unpositioned and get_pos(e.text) is None:
        return None
    default = resolve_event_style(styles, e.style)
    state = default.copy()
    continuation = OverrideContinuation()
    runs = []
    for part in re.split(r"(\{[^}]*\})", e.text):
        if part.startswith("{") and part.endswith("}"):
            for name, value in tokenize_override(part[1:-1]):
                if name in {"t", "move", "fad", "fade", "k", "kf", "ko", "kt"}:
                    return None
                continuation = apply_override(state,name,value,styles,default,continuation)
        elif part:
            normalized = state.copy()
            for clip in ("clip", "iclip"):
                if clip in normalized:
                    normalized[clip] = geometry_key(normalized[clip])
            signature = StaticSpanSignature(tuple(sorted(normalized.items())),continuation)
            drawing = state.get("p", 0) > 0
            payload = geometry_key(part) if drawing else part
            if runs and runs[-1][0] == signature and runs[-1][1] == drawing:
                runs[-1] = (signature, drawing, runs[-1][2] + payload)
            else:
                runs.append((signature, drawing, payload))
    # Document metadata previously participated in span signatures. Keep that
    # matching distinction explicit, outside the literal formatting signature.
    return (e.layer, e.style, e.name, e.margin_l, e.margin_r, e.margin_v, e.measurement,
            tuple(runs)) if runs else None


def _merge_static_phase_round(
    events: list[Event], styles: dict, font_metrics: FontMetrics | None, *,
    text_only: bool, row_sources: set[int] | None,
) -> tuple[list[Event], int]:
    """Join touching static phases using final paint and actual output order.

    No gaps, overlaps, geometry drift or representative paint selection. A
    same-layer peer between records must be provably spatially disjoint. Source
    indices belong to different reconstruction stages, so list order is the
    authority; retained records keep their original source identities.
    """
    groups, layers, boxes = {}, {}, {}
    for index, event in enumerate(events):
        try:
            layer = int(event.layer)
        except ValueError:
            # An invalid layer cannot establish a renderer ordering relation.
            layer = None
        if event.kind == 'Dialogue':
            layers.setdefault(layer, []).append(index)
        if layer is None:
            continue
        key = static_object_key(event, styles)
        if key is not None and (not text_only or all(not drawing for _, drawing, _ in key[-1])):
            key = (layer,) + key[1:]
            if row_sources is not None:
                # Shared-interval reconstruction groups by row and eligibility.
                # Identical paint cannot erase a boundary between those roles.
                eligible = event.lyric or event.source_index in row_sources
                key += ((event.row if eligible else None, eligible),)
            groups.setdefault(key, []).append(index)

    # Malformed peers still obstruct ordering; do not silently omit them.
    unknown = layers.get(None, ())
    if unknown:
        for layer, peers in layers.items():
            if layer is not None:
                peers.extend(unknown)

    def box(index):
        if index not in boxes:
            event = events[index]
            # Unknown/moving/drawing/blurred or automatically wrapped ink
            # cannot prove that changing record order is harmless.
            key = static_object_key(event, styles)
            eligible = (key is not None and all(not drawing for _, drawing, _ in key[-1])
                        and (event.state.get('q', event.measurement.script_wrap_mode) == 2
                             or len(OVERRIDE_RE.sub('', event.text)) == 1)
                        and event.state.get('borderstyle', 1) == 1
                        and not any(event.state.get(k, 0) for k in
                                    ('blur', 'be', 'fsp', 'u', 's', 'shad', 'xshad', 'yshad')))
            boxes[index] = caption_bounds(event, font_metrics) if eligible else None
        return boxes[index]

    replacements, removed = {}, set()
    for indices in groups.values():
        ordered = sorted(indices, key=lambda i: (events[i].start_s, events[i].end_s, i))
        overlapping, active = set(), []
        for index in ordered:
            active = [i for i in active if events[i].end_s > events[index].start_s]
            if active:
                overlapping.update(active)
                overlapping.add(index)
            active.append(index)
        first = ordered[0]
        current, members = events[first], {first}
        for index in ordered[1:]:
            event = events[index]
            can_join = (current.end == event.start and index not in overlapping
                        and not members.intersection(overlapping))
            if can_join:
                trial = members | {index}
                first = min(trial)
                pending_row = row_sources is not None and (
                    events[first].lyric or events[first].source_index in row_sources)
                # Moving a later record into the first record's slot changes
                # order only during that later record's own lifetime. A peer
                # which ended at the handoff is not a compositing conflict.
                for phase in trial:
                    for peer in layers[int(event.layer)]:
                        if (not first < peer < phase or peer in trial
                                or min(events[peer].end_s, event.end_s if pending_row else events[phase].end_s)
                                <= max(events[peer].start_s, current.start_s if pending_row else events[phase].start_s)):
                            continue
                        # Pending row reconstruction can change text spacing
                        # and ownership even for spatially disjoint peers.
                        # Keep its whole-row slot boundaries until it finishes.
                        if pending_row:
                            can_join = False
                            break
                        a, b = box(first), box(peer)
                        if (a is None or b is None or not
                                (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])):
                            can_join = False
                            break
                    if not can_join:
                        break
            if can_join:
                members.add(index)
                first = min(members)
                current = replace_event(events[first], start=current.start, start_s=current.start_s,
                                        end=event.end, end_s=event.end_s)
            else:
                if any(events[i].evidence.frame_pose_intervals is not None for i in members):
                    current = _preserve_frame_pose_support(events[min(members)],current,
                                                          (events[i] for i in members))
                replacements[min(members)] = current
                removed.update(members - {min(members)})
                current, members = event, {index}
        if any(events[i].evidence.frame_pose_intervals is not None for i in members):
            current = _preserve_frame_pose_support(events[min(members)],current,
                                                  (events[i] for i in members))
        replacements[min(members)] = current
        removed.update(members - {min(members)})
    return [replacements.get(i, event) for i, event in enumerate(events) if i not in removed], len(removed)


def merge_static_timed_copies(
    events: list[Event], styles: dict, *, font_metrics: FontMetrics | None=None,
    text_only: bool=False, row_sources: set[int] | None=None,
) -> tuple[list[Event], int]:
    """Settle exact touching phases without changing paint, gaps or overlaps.

    Use actual list order at every stage, retaining each survivor's source
    identity and borrowed cache/evidence. Invoke after consumers of individual
    phase evidence have finished, or supply row_sources to preserve the row
    and animation eligibility still needed by shared-interval reconstruction.
    Canonical identical phases then remain a valid handoff. Final caption support
    ownership is already committed, so that caller requests text-only merging;
    the text/vector stage retains its existing drawing-phase admission.
    Every contributing round strictly reduces records. A join can remove an
    obsolete ordering obstacle for another family, so settle this one proof
    without repeating effect selection or source reconstruction.
    """
    removed = 0
    while True:
        events, count = _merge_static_phase_round(events, styles, font_metrics,
                                                  text_only=text_only, row_sources=row_sources)
        removed += count
        if not count:
            return events, removed


def static_text_paint_geometry(e: Event, paint: set[str]):
    """Resolve literal spans, coalescing boundaries that change only paint."""
    obj = static_object_key(e,e.styles,allow_unpositioned=True)
    geometry = []
    if obj is not None:
        for signature,drawing,payload in obj[-1]:
            state = dict(signature.formatting)
            if drawing or state.get("borderstyle",1) != 1:
                return None
            layout = state_key(dataclass_replace(e,state=state,continuation=signature.continuation),paint | {"clip","iclip"})
            if geometry and geometry[-1][0] == layout:
                geometry[-1] = (layout,geometry[-1][1]+payload)
            else:
                geometry.append((layout,payload))
    return (tuple(geometry),obj[-1]) if geometry else None
