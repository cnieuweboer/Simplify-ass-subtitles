"""Shared-interval row proof and reconstruction with pass-local visibility."""
from __future__ import annotations

import collections
import re
import statistics
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Mapping, MutableMapping

from .ass_overrides import (
    OVERRIDE_RE, apply_override, evaluate_effective_state, tokenize_override,
)
from .caption_geometry import (
    caption_bounds, get_pos, inline_layout_key, positioned_row_geometry,
    split_positioned_row_runs, text_height, text_layout_key,
)
from .caption_rendering import CAPTION_PAINT_TAGS, render_merged_caption
from .event_model import Event
from .event_operations import event_override_tokens, replace_event, state_key
from .font_metrics import FontMetrics
from .font_reporting import FontProcessingReport
from .row_fitting import recover_font_row, recover_tracked_font_row


@dataclass(frozen=True)
class SharedIntervalRowsResult:
    """Retained row/tail events, operation counts and pending visibility.

    The pass owns an overlay for all rounds. Callers apply its delta only
    after successful completion; source-history entries are never removed.
    """
    events: list[Event]
    rows_joined: int
    tails_retained: int
    visibility_updates: dict[int,str]


@dataclass(frozen=True)
class SharedIntervalContext:
    """Pass-owned visibility overlay, order/layer indexes and caption-bound cache."""
    visible: MutableMapping[int,str]
    metric: FontMetrics
    paint_tags: set[str]
    boxes: dict[int,tuple | None]
    order_index: dict[int,int]
    by_layer: dict[int,list[Event]]
    layer_indices: dict[int,list[int]]
    font_report: FontProcessingReport | None = None


@dataclass(frozen=True)
class SharedIntervalProposal:
    """A font-proven common row interval with its original safe placement slots."""
    members: frozenset[int]
    ordered: list[Event]
    first_start: Event
    first_end: Event
    body: str
    text: str
    valid_slots: list[Event]
    member_boxes: list[tuple]


@dataclass
class SharedIntervalEdits:
    """Generated rows/tails, original-slot replacements and accepted placement evidence."""
    next_index: int
    claimed: set[int] = field(default_factory=set)
    slots: dict[int,list[Event]] = field(default_factory=dict)
    accepted: list[tuple] = field(default_factory=list)
    rows: int = 0
    tails: int = 0


def merge_shared_interval_rows(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics | None,
    animated_sources: set[int], *, font_report: FontProcessingReport | None=None,
) -> SharedIntervalRowsResult:
    """Compact common visibility, then compact retained phase tails.

    Four rounds bound subdivision. Each round consumes a fragment at most
    once; no round can expand a glyph's original lifetime or alter its paint.
    Borrow visibility and expose pending rows/tails only through a local
    overlay. Return one sparse delta for the pipeline to apply after all rounds.
    """
    rows = tails = 0
    visibility_updates = {}
    pending_visibility = collections.ChainMap(visibility_updates,visible)
    eligible_sources = set(animated_sources)
    for _ in range(4):
        previous_ids = {e.source_index for e in events}
        events,count,retained = _merge_shared_interval_rows_once(
            events,pending_visibility,metric,eligible_sources, font_report=font_report)
        eligible_sources.update(e.source_index for e in events if e.source_index not in previous_ids)
        rows += count
        tails += retained
        if not count:
            break
    return SharedIntervalRowsResult(events,rows,tails,visibility_updates)


def _shared_interval_bounds(context: SharedIntervalContext, e: Event) -> tuple | None:
    """Cache original caption bounds, including every inline paint extent."""
    if e.source_index not in context.boxes:
        probe = e
        if inline_layout_key(e):
            prefix = re.match(r'(?:\{[^}]*\})*',e.text).end()
            suffix = e.text[prefix:]
            tokens = [token for block in OVERRIDE_RE.findall(suffix)
                      for token in tokenize_override(block)]
            if any(tag not in context.paint_tags for tag,value in tokens):
                context.boxes[e.source_index] = None
                return None
            evaluation = evaluate_effective_state(e.text[:prefix],e.defaults,e.styles)
            state,continuation = evaluation.formatting,evaluation.continuation
            states = [state.copy()]
            for tag,value in tokens:
                continuation = apply_override(state,tag,value,e.styles,e.defaults,continuation)
                states.append(state.copy())
            state = dict(e.state)
            for k in ('xbord','ybord','xshad','yshad'):
                state[k] = max(abs(p.get(k,p.get(k[1:],0))) for p in states)
            for k in ('blur','be'):
                state[k] = max(abs(p.get(k,0)) for p in states)
            # Replacing text reparses its formatting. Install the accumulated
            # source extents afterwards, or a narrow final span can erase the
            # larger border/shadow/blur footprint needed for compositing proof.
            probe = replace_event(e,text=e.text[:prefix]+OVERRIDE_RE.sub('',suffix))
            probe = replace_event(probe,state=state)
        box = caption_bounds(probe,context.metric)
        if box is not None:
            pad = 2*abs(probe.state.get('blur',0))+abs(probe.state.get('be',0))
            box = (box[0]-pad,box[1]-pad,box[2]+pad,box[3]+pad)
        context.boxes[e.source_index] = box
    return context.boxes[e.source_index]


def _prepare_shared_interval_context(
    events: list[Event], visible: MutableMapping[int, str], metric: FontMetrics, *,
    font_report: FontProcessingReport | None=None,
) -> SharedIntervalContext:
    """Index original file order and numeric layers once for this pass."""
    paint_tags = CAPTION_PAINT_TAGS
    boxes = {}
    order_index = {e.source_index:i for i,e in enumerate(events)}
    by_layer = {}
    for e in events:
        if e.kind == 'Dialogue' and e.layer.lstrip('-').isdigit():
            by_layer.setdefault(int(e.layer),[]).append(e)
    layer_indices = {}
    for layer,peers in by_layer.items():
        peers.sort(key=lambda e:order_index[e.source_index])
        layer_indices[layer] = [order_index[e.source_index] for e in peers]
    return SharedIntervalContext(visible,metric,paint_tags,boxes,order_index,by_layer,layer_indices, font_report=font_report)


def _group_shared_interval_candidates(context: SharedIntervalContext, events: list[Event], animated_sources: set[int]) -> dict[tuple,list[Event]]:
    """Group eligible frozen fragments by original layout and geometry."""
    buckets = {}
    for e in events:
        word = context.visible.get(e.source_index,'')
        if (e.kind != 'Dialogue' or not word or e.duration <= 0 or e.effect or
                not (e.lyric or e.source_index in animated_sources) or
                get_pos(e.text) is None or not e.layer.lstrip('-').isdigit() or e.state.get('p',0) or
                e.state.get('1a',0) != 0 or e.state.get('borderstyle',1) != 1 or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay')) or
                any(tag in e.text for tag in (r'\N',r'\n')) or
                OVERRIDE_RE.search(e.text,re.match(r'(?:\{[^}]*\})*',e.text).end()) or
                any(tag in {'t','move','fad','fade','k','kf','ko','kt'}
                    for tag,value in event_override_tokens(e))):
            continue
        key = (e.style,e.name,e.row,e.margin_l,e.margin_r,e.margin_v,
               tuple((k,v) for k,v in text_layout_key(e) if k != 'q'),
               state_key(e,{'pos','q',*context.paint_tags}))
        buckets.setdefault(key,[]).append(e)
    return buckets


def _shared_interval_row_bands(buckets: dict[tuple,list[Event]]) -> list[list[Event]]:
    """Separate candidate buckets into their original vertical bands."""
    bands = []
    for bucket in buckets.values():
        current = []
        for e in sorted(bucket,key=lambda p:get_pos(p.text)[1]):
            if current and get_pos(e.text)[1]-get_pos(current[0].text)[1] > .15*min(
                    text_height(e),min(text_height(p) for p in current)):
                bands.append(current)
                current = []
            current.append(e)
        bands.append(current)
    return bands


def _shared_interval_sweep_candidates(bucket: list[Event]) -> list[list[Event]]:
    """Collect shared-boundary and directional sweeps with complete common visibility."""
    boundaries = {}
    for e in bucket:
        boundaries.setdefault(('start',e.start),[]).append(e)
        boundaries.setdefault(('end',e.end),[]).append(e)
    candidates = list(boundaries.values())
    # Staggered glyph entrances/exits need not share an exact boundary.
    # Grow directional sweeps only while the entire run retains a common
    # interval; never chain pairwise overlaps into a lifetime union.
    for boundary in ('start_s','end_s'):
        for direction in (1,-1):
            run = []
            for e in sorted(bucket,key=lambda p:(getattr(p,boundary),direction*get_pos(p.text)[0])):
                if run and (direction*(get_pos(e.text)[0]-get_pos(run[-1].text)[0]) <= e.unit or
                            e.end_s < run[-1].end_s-.011 or
                            min(e.end_s,min(p.end_s for p in run))-
                            max(e.start_s,max(p.start_s for p in run)) < .04-1e-6):
                    candidates.append(run)
                    run = []
                run.append(e)
            candidates.append(run)
    return candidates


def _shared_interval_candidate_windows(peers: list[Event]) -> list[list[Event]]:
    """Include complete rows and bounded prefix/suffix windows around independently timed edges."""
    runs = split_positioned_row_runs(peers)
    # A missing or independently timed edge glyph must not prevent
    # a proven prefix/suffix from sharing its own common interval.
    windows = []
    for run in runs:
        windows.append(run)
        if len(run) <= 32:
            windows.extend(run[left:right] for left in range(len(run)-3)
                           for right in range(left+4,len(run)+1)
                           if left or right != len(run))
        elif len(run) <= 64:
            for size in range(4,len(run)):
                windows.extend((run[:size],run[-size:]))
    return windows


def _shared_interval_slot_constraints(context: SharedIntervalContext, ordered: list[Event], members: frozenset[int], start: float, end: float, member_boxes: list[tuple]) -> list[Event] | None:
    """Preserve each original overlap relation when selecting available row slots."""
    # Preserve every overlapping glyph's relation to outside
    # objects. Disjoint glyphs may safely move to another slot.
    # Retain all fragment tails on their own layers.
    interleaved = False
    low_order = min((int(e.layer),context.order_index[e.source_index]) for e in ordered)
    high_order = max((int(e.layer),context.order_index[e.source_index]) for e in ordered)
    floor,ceiling = None,None
    for layer,peers_on_layer in context.by_layer.items():
        if not low_order[0] <= layer <= high_order[0]:
            continue
        first = bisect_right(context.layer_indices[layer],low_order[1]) if layer == low_order[0] else 0
        last = bisect_left(context.layer_indices[layer],high_order[1]) if layer == high_order[0] else len(peers_on_layer)
        for peer in peers_on_layer[first:last]:
            if (peer.source_index in members or
                    min(peer.end_s,end) <= max(peer.start_s,start)):
                continue
            box = _shared_interval_bounds(context,peer)
            peer_order = (layer,context.order_index[peer.source_index])
            relations = {(int(piece.layer),context.order_index[piece.source_index]) < peer_order
                         for piece,member_box in zip(ordered,member_boxes)
                         if box is None or member_box[0] < box[2] and box[0] < member_box[2] and
                         member_box[1] < box[3] and box[1] < member_box[3]}
            if len(relations) > 1:
                interleaved = True
                break
            if relations == {True}:
                ceiling = min(ceiling,peer_order) if ceiling is not None else peer_order
            elif relations == {False}:
                floor = max(floor,peer_order) if floor is not None else peer_order
        if interleaved:
            break
    if interleaved:
        return None
    slots_in_order = sorted(ordered,key=lambda e:(int(e.layer),context.order_index[e.source_index]))
    valid_slots = [e for e in slots_in_order if
        (floor is None or (int(e.layer),context.order_index[e.source_index]) > floor) and
        (ceiling is None or (int(e.layer),context.order_index[e.source_index]) < ceiling)]
    if not valid_slots:
        return None
    return valid_slots


def _fit_shared_interval_caption(context: SharedIntervalContext, ordered: list[Event], ys: list[float]) -> tuple[str,str] | None:
    """Prove exact-font spacing and render the retained per-fragment paint."""
    fragments = [context.visible[e.source_index] for e in ordered]
    fit = (recover_tracked_font_row(context.metric, ordered,fragments, font_report=context.font_report)
           if abs(ordered[0].state.get('fsp',0)) > .001 else
           recover_font_row(context.metric, ordered,fragments,allow_internal_spaces=True,
                          max_size_error=.1, font_report=context.font_report))
    if fit is None:
        return None
    text,x,sx,sy,an = fit[:5]
    tracking = fit[5] if len(fit) > 5 else ordered[0].state.get('fsp',0)
    body = render_merged_caption(ordered,fragments,text,animated=False,
        an=an,pos=(x,statistics.median(ys)),fscx=sx,fscy=sy,fsp=tracking,
        preserve_paint=True)
    if body is None:
        return None
    return body,text


def _prove_shared_interval_candidate(context: SharedIntervalContext, ordered: list[Event], tested: set[frozenset[int]]) -> SharedIntervalProposal | None:
    """Prove common timing, geometry, compositing order and a readable caption once per member set."""
    if len(ordered) < 4:
        return None
    first_start = max(ordered,key=lambda e:e.start_s)
    first_end = min(ordered,key=lambda e:e.end_s)
    start,end = first_start.start_s,first_end.end_s
    if end-start < .04-1e-6:
        return None
    geometry = positioned_row_geometry(ordered)
    if geometry is None:
        return None
    xs,ys = geometry
    members = frozenset(e.source_index for e in ordered)
    if members in tested:
        return None
    tested.add(members)
    member_boxes = [_shared_interval_bounds(context,e) for e in ordered]
    if any(box is None for box in member_boxes):
        return None
    clearance = 2*max(e.unit for e in ordered)
    member_boxes = [(box[0]-clearance,box[1]-clearance,
                     box[2]+clearance,box[3]+clearance) for box in member_boxes]
    valid_slots = _shared_interval_slot_constraints(context,ordered,members,start,end,member_boxes)
    if valid_slots is None:
        return None
    fitted = _fit_shared_interval_caption(context,ordered,ys)
    if fitted is None:
        return None
    body,text = fitted
    return SharedIntervalProposal(members,ordered,first_start,first_end,body,text,valid_slots,member_boxes)


def _collect_shared_interval_proposals(context: SharedIntervalContext, bands: list[list[Event]]) -> dict[frozenset[int],SharedIntervalProposal]:
    """Collect proven candidates before resolving competing row placements."""
    proposals = {}
    tested = set()
    for bucket in bands:
        candidates = _shared_interval_sweep_candidates(bucket)
        for peers in candidates:
            windows = _shared_interval_candidate_windows(peers)
            for ordered in windows:
                proposal = _prove_shared_interval_candidate(context,ordered,tested)
                if proposal is not None:
                    proposals[proposal.members] = proposal
    return proposals


def _compatible_shared_interval_slots(context: SharedIntervalContext, proposal: SharedIntervalProposal, accepted: list[tuple]) -> list[Event]:
    """Recheck a proposed placement against every already accepted overlapping row."""
    ordered,member_boxes = proposal.ordered,proposal.member_boxes
    start,end = proposal.first_start.start_s,proposal.first_end.end_s
    valid_slots = proposal.valid_slots
    # Independently safe placements can cross after two rows both move.
    # Recheck each overlapping accepted row against the original glyph
    # orders, then select a slot satisfying both sets of constraints.
    for peers,peer_boxes,peer_start,peer_end,peer_order in accepted:
        if min(end,peer_end) <= max(start,peer_start):
            continue
        relations = {(int(piece.layer),context.order_index[piece.source_index]) <
                     (int(peer.layer),context.order_index[peer.source_index])
                     for piece,box in zip(ordered,member_boxes)
                     for peer,peer_box in zip(peers,peer_boxes)
                     if box[0] < peer_box[2] and peer_box[0] < box[2] and
                     box[1] < peer_box[3] and peer_box[1] < box[3]}
        if len(relations) > 1:
            valid_slots = []
            break
        if relations:
            before = next(iter(relations))
            valid_slots = [e for e in valid_slots if
                ((int(e.layer),context.order_index[e.source_index]) < peer_order) == before]
            if not valid_slots:
                break
    return valid_slots


def _preserve_shared_interval_fragment_tails(context: SharedIntervalContext, proposal: SharedIntervalProposal, edits: SharedIntervalEdits) -> None:
    """Keep both original fragment tails in their original slots with unique generated IDs."""
    ordered = proposal.ordered
    first_start,first_end = proposal.first_start,proposal.first_end
    start,end = first_start.start_s,first_end.end_s
    for piece in ordered:
        pieces = edits.slots.setdefault(piece.source_index,[])
        for before in (True,False):
            if before and piece.start_s < start or not before and piece.end_s > end:
                tail = replace_event(piece,source_index=edits.next_index,
                    **({'end':first_start.start,'end_s':start} if before else
                       {'start':first_end.end,'start_s':end}))
                edits.next_index += 1
                context.visible[tail.source_index] = context.visible[piece.source_index]
                pieces.append(tail)
                edits.tails += 1


def _apply_shared_interval_proposal(context: SharedIntervalContext, proposal: SharedIntervalProposal, valid_slots: list[Event], edits: SharedIntervalEdits) -> None:
    """Place one readable row, retain its tails and record the accepted original ordering."""
    ordered,members = proposal.ordered,proposal.members
    member_boxes = proposal.member_boxes
    first_start,first_end = proposal.first_start,proposal.first_end
    start,end = first_start.start_s,first_end.end_s
    body,text = proposal.body,proposal.text
    slot_piece = valid_slots[0]
    row = replace_event(ordered[0],source_index=edits.next_index,text=body,effect='',
        layer=slot_piece.layer,
        start=first_start.start,start_s=start,end=first_end.end,end_s=end)
    edits.next_index += 1
    context.visible[row.source_index] = text
    slot = slot_piece.source_index
    edits.slots[slot] = [row]
    _preserve_shared_interval_fragment_tails(context,proposal,edits)
    edits.claimed.update(members)
    edits.accepted.append((ordered,member_boxes,start,end,
                     (int(slot_piece.layer),context.order_index[slot_piece.source_index])))
    edits.rows += 1


def _apply_shared_interval_proposals(context: SharedIntervalContext, events: list[Event], proposals: dict[frozenset[int],SharedIntervalProposal]) -> tuple[list[Event],int,int]:
    """Rank proposals by saved overlap, claim members once and apply compatible rows in original slots."""
    edits = SharedIntervalEdits(max((e.source_index for e in events),default=-1)+1)
    for members,proposal in sorted(proposals.items(),key=lambda item:
            (-(len(item[0])-1)*(item[1].first_end.end_s-item[1].first_start.start_s),min(item[0]))):
        if edits.claimed & members:
            continue
        valid_slots = _compatible_shared_interval_slots(context,proposal,edits.accepted)
        if not valid_slots:
            continue
        _apply_shared_interval_proposal(context,proposal,valid_slots,edits)
    if not edits.rows:
        return events,0,0
    # Place rows/tails at their original event slots to preserve layer order.
    output = [piece for e in events for piece in edits.slots.get(e.source_index,[e])]
    return output,edits.rows,edits.tails


def _merge_shared_interval_rows_once(
    events: list[Event], visible: MutableMapping[int, str], metric: FontMetrics | None,
    animated_sources: set[int], *, font_report: FontProcessingReport | None=None,
) -> tuple[list[Event], int, int]:
    """Compact frozen rows inside common visibility, retaining all glyph tails.

    Shared boundaries or directional sweeps supply phase boundaries; exact-font measurements
    must prove the row. Never expand visibility, select new paint or geometry,
    or run source-dependent effect removal on the resulting time slices.
    Each original event is consumed at most once. Four fragments and 40 ms
    of shared visibility bound subdivision of short, low-benefit candidates.
    The outer pass supplies its owned writable overlay for generated text.
    """
    if metric is None or not metric.available:
        return events,0,0
    context = _prepare_shared_interval_context(events,visible,metric, font_report=font_report)
    buckets = _group_shared_interval_candidates(context,events,animated_sources)
    bands = _shared_interval_row_bands(buckets)
    proposals = _collect_shared_interval_proposals(context,bands)
    return _apply_shared_interval_proposals(context,events,proposals)
