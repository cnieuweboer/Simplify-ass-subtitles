"""Authored caption reconstruction across entrance, movement and held phases."""
from __future__ import annotations

import collections
import statistics
from dataclasses import dataclass, field
from typing import Mapping

from .caption_geometry import (
    get_pos, inline_layout_key, placement_key, text_height, text_layout_key,
)
from .caption_rendering import (
    _source_caption_paint, render_merged_caption, render_simplified_caption,
)
from .effect_validation import opaque_text_effect_state
from .event_model import Event
from .event_operations import replace_event, state_key
from .font_metrics import FontMetrics
from .font_reporting import FontProcessingReport
from .fragment_spans import index_fragment_spans, matching_fragment_spans
from .glyph_placement import (
    authored_glyph_positions, fit_fragment_anchor, matches_authored_glyph_positions,
)
from .row_evidence import TextRow, TextPhaseRowsResult
from .static_objects import static_object_key
from .static_selection import unrotated_text_state
from .subtitle_document import format_time
from .text_freezing import simplify_text


@dataclass(frozen=True)
class TranslatedPhaseContext:
    """Original events, measured movement profiles and the eligible phase pool."""
    visible: Mapping[int,str]
    metric: FontMetrics
    profiles: list[tuple]
    pool: dict[str,list[Event]]
    allids: dict[int,Event]
    font_report: FontProcessingReport | None = None


@dataclass(frozen=True)
class TranslatedCueLayout:
    """Authored cue geometry selected from translation or held-text evidence."""
    cue: Event
    text: str
    window: float
    seeds: list[tuple]
    sample: Event
    key: tuple
    delta: float
    y: float
    positions: list[tuple[str,float]]


@dataclass(frozen=True)
class TranslatedCueModel:
    """One complete glyph model with a cache owned by this cue alone."""
    layout: TranslatedCueLayout
    center: float
    xs: list[float]
    initial_start: float
    spans: tuple
    span_cache: dict[tuple,list[tuple[int,int]]] = field(default_factory=dict,compare=False)


@dataclass(frozen=True)
class TranslatedCuePhases:
    """Matched held text, entrance fragments and proved movement pulses."""
    stable: list[tuple[Event,tuple[int,int]]]
    entrances: list[tuple[Event,tuple[int,int]]]
    pulses: list[tuple[Event,tuple[int,int]]]


def _translated_layout_key(e: Event) -> tuple:
    """Match paragraph geometry while allowing scale and shear animation."""
    return (e.style,placement_key(e),tuple((k,v) for k,v in text_layout_key(e)
            if k not in {'fscx','fscy','fax','fay'}))


def _match_touching_phase_fragments(
    peers: list[Event], target: Event, poses: dict[int, tuple[float, float]],
    words: dict[int, str], metric: FontMetrics,
) -> list[tuple[list[Event], float]]:
    """Measure complete touching fragments at the target baseline in the exact font."""
    peers = sorted(peers,key=lambda e:poses[e.source_index][0])
    spans = index_fragment_spans(words[e.source_index] for e in peers)
    output = []
    for a,b in matching_fragment_spans(spans,words[target.source_index]):
        row = peers[a:b+1]
        if (len({state_key(p,{'pos'}) for p in row}) != 1 or
                any(abs(poses[p.source_index][1]-poses[target.source_index][1]) > .001 for p in row)):
            continue
        anchor = fit_fragment_anchor(metric, row[0].state,[poses[p.source_index][0] for p in row],
            [words[p.source_index] for p in row],words[target.source_index],target.unit,
            separate_glyphs=all(len(words[p.source_index]) == 1 for p in row),max_size_error=.1)
        if anchor is not None:
            output.append((row,anchor))
    return output


def _collect_translated_motion_profiles(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics, cue_styles: set[str],
) -> list[tuple]:
    """Find uniquely owned before/movement/after phases proving horizontal translation."""
    keys, poses, words, begins, ends, eligible = {}, {}, {}, {}, {}, []
    for e in events:
        word, pos = visible.get(e.source_index,''), get_pos(e.text)
        if (e.kind != 'Dialogue' or e.style not in cue_styles or not word or pos is None or e.duration <= 0 or
                any(c.isspace() for c in word) or inline_layout_key(e) or
                not opaque_text_effect_state(e.state) or not unrotated_text_state(e.state) or
                static_object_key(e,e.styles) is None):
            continue
        key = _translated_layout_key(e)
        keys[e.source_index], poses[e.source_index], words[e.source_index] = key,pos,word
        eligible.append(e)
        if not any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay')):
            begins.setdefault((key,round(e.start_s,2)),[]).append(e)
            ends.setdefault((key,round(e.end_s,2)),[]).append(e)
    proposals = []
    for e in eligible:
        key, pos = keys[e.source_index],poses[e.source_index]
        left = _match_touching_phase_fragments(ends.get((key,round(e.start_s,2)),[]),e,poses,words,metric)
        right = _match_touching_phase_fragments(begins.get((key,round(e.end_s,2)),[]),e,poses,words,metric)
        options = []
        for before,bx in left:
            for after,ax in right:
                delta = ax-bx
                if (state_key(before[0],{'pos'}) != state_key(after[0],{'pos'}) or
                        abs(delta) <= e.unit or not min(ax,bx)-e.unit <= pos[0] <= max(ax,bx)+e.unit):
                    continue
                if (len(before) == len(after) and any(
                        abs(poses[b.source_index][0]-poses[a.source_index][0]-delta) > 1.5*e.unit
                        for a,b in zip(before,after))):
                    continue
                options.append((before,after,delta))
        if len(options) == 1:
            before,after,delta = options[0]
            ids = {e.source_index}|{p.source_index for p in before+after}
            proposals.append((ids,after,e,before,delta))
    claims = {}
    for ids,after,e,before,delta in proposals:
        for index in ids:
            claims[index] = claims.get(index,0)+1
    return [p for p in proposals if all(claims[index] == 1 for index in p[0])]


def _prepare_translated_phases(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics, cues: list[Event], *,
    font_report: FontProcessingReport | None=None,
) -> TranslatedPhaseContext:
    """Collect original movement profiles and the eligible static phase pool once."""
    cue_styles = {e.style for e in cues}
    allids = {e.source_index:e for e in events}
    profiles = _collect_translated_motion_profiles(events,visible,metric,cue_styles)
    pool = {}
    for e in events:
        w = visible.get(e.source_index, '')
        p = get_pos(e.text)
        if (e.kind == 'Dialogue' and e.style in cue_styles and w and p and (e.duration > 0)
            and (not inline_layout_key(e)) and (static_object_key(e, e.styles) is not None)
            and unrotated_text_state(e.state) and (not any((k in e.state for k in ['clip', 'iclip', 'org'])))):
            pool.setdefault(e.style, []).append(e)
    return TranslatedPhaseContext(visible,metric,profiles,pool,allids, font_report=font_report)


def _select_translated_cue_layout(
    context: TranslatedPhaseContext, cue: Event,
) -> TranslatedCueLayout | None:
    """Select the authored row and its measured translation or held-text baseline."""
    text = simplify_text(cue.text, visible_only=True)[1]
    if len(''.join(text.split())) < 4 or cue.duration <= 0:
        return None
    # Scale lead-in/tail allowances with the cue, not a fixed time limit.
    window = 0.25 * cue.duration
    seeds = [p for p in context.profiles if p[2].style == cue.style and cue.start_s - 0.011 <= p[2].start_s
        and (p[2].end_s <= cue.end_s + 0.011)]
    if seeds:
        k = _translated_layout_key(seeds[0][3][0])
        delta = statistics.median((p[4] for p in seeds))
        if any((_translated_layout_key(p[3][0]) != k or abs(p[4] - delta) > p[2].unit + 0.1 * text_height(p[2]) for p in seeds)):
            return None
        sample = seeds[0][3][0]
        y = get_pos(sample.text)[1]
    else:
        options = [e for e in context.pool.get(cue.style, []) if opaque_text_effect_state(e.state)
            and e.start_s <= cue.start_s + window and (e.end_s >= cue.end_s - window)
            and (e.duration >= 0.5 * cue.duration) and (not any((abs(e.state.get(k, 0)) > 0.001 for k in ['fax',
            'fay'])))]
        if not options:
            return None
        sample = max(options, key=lambda e: e.duration)
        k = _translated_layout_key(sample)
        delta = 0
        y = get_pos(sample.text)[1]
    positions = authored_glyph_positions(context.metric, sample.state, text, 0, sample.unit)
    if not positions:
        return None
    return TranslatedCueLayout(cue,text,window,seeds,sample,k,delta,y,positions)


def _fit_translated_cue_model(
    context: TranslatedPhaseContext, layout: TranslatedCueLayout,
) -> TranslatedCueModel | None:
    """Require one complete authored glyph model, then create its cue-local span cache."""
    candidates = [e for e in context.pool.get(layout.cue.style, []) if _translated_layout_key(e) == layout.key
        and layout.cue.start_s - layout.window - 0.001 <= e.start_s <= layout.cue.start_s + layout.window + 0.001
        and (e.end_s <= layout.cue.end_s + layout.window + 0.001)
        and (abs(get_pos(e.text)[1] - layout.y) <= 0.25 * text_height(layout.sample)) and (not any((abs(e.state.get(k,
        0)) > 0.001 for k in ['fax', 'fay']))) and (e.state.get('fscx') == layout.sample.state.get('fscx'))
        and (e.state.get('fscy') == layout.sample.state.get('fscy')) and (e.state.get('1c') == layout.sample.state.get('1c'))]
    # Full font geometry must account for every authored nonspace glyph.
    first = [e for e in candidates if context.visible[e.source_index] == layout.positions[0][0]]
    models = {}
    glyph_spans = index_fragment_spans(c for c,x in layout.positions)
    for e in first:
        center = get_pos(e.text)[0] - layout.positions[0][1]
        matches = [[p for p in candidates if context.visible[p.source_index] == char
            and abs(get_pos(p.text)[0] - (center + offset)) <= 1.5 * layout.sample.unit] for char, offset in layout.positions]
        for ids, new, phase, before, d in layout.seeds:
            for b in before:
                word = context.visible[b.source_index]
                if len(word) <= 1:
                    continue
                for a, z in matching_fragment_spans(glyph_spans, word):
                    gp = authored_glyph_positions(context.metric, layout.sample.state, word, 0, layout.sample.unit)
                    if (gp
                        and abs(get_pos(b.text)[0] - (center + layout.positions[a][1] - gp[0][1])) <= layout.sample.unit + 0.1 * text_height(layout.sample)):
                        for i in range(a, z + 1):
                            matches[i].append(b)
        if any((not m for m in matches)):
            continue
        if (layout.seeds and any((not all((any((p.source_index == b.source_index for m in matches for p in m))
            for b in before)) for ids, new, p, before, d in layout.seeds))):
            continue
        models[round(center, 1)] = (center, matches)
    if len(models) != 1:
        return None
    center, matches = next(iter(models.values()))
    xs = [center + x for c, x in layout.positions]
    initial_start = (min([b.start_s for ids, new, phase, before, d in layout.seeds for b in before] + [p.start_s
        for group in matches for p in group if (p.end_s > layout.cue.start_s + 0.011 or abs(p.end_s-layout.cue.start_s) < .001)
        and abs(get_pos(p.text)[1] - layout.y) <= layout.sample.unit and (state_key(p, {'pos'}) == state_key(layout.sample, {'pos'}))],
        default=layout.cue.start_s))
    spans = glyph_spans
    return TranslatedCueModel(layout,center,xs,initial_start,spans)


def _translated_span_options(
    context: TranslatedPhaseContext, model: TranslatedCueModel,
    e: Event, dx: float = 0, travel: bool = False,
) -> list[tuple[int,int]]:
    """Cache exact occurrence/anchor matches within one authored cue only."""
    layout = model.layout
    key = (e.source_index,dx,travel)
    if key in model.span_cache:
        return model.span_cache[key]
    word = context.visible[e.source_index]
    poss = []
    for a, b in matching_fragment_spans(model.spans, ''.join(word.split())):
        anchor = (fit_fragment_anchor(context.metric, layout.sample.state, model.xs[a:b + 1], [c for c, x in layout.positions[a:b + 1]], word,
            layout.sample.unit) if not any((c.isspace() for c in word)) else None)
        if anchor is None:
            if any((c.isspace() for c in word)):
                g = authored_glyph_positions(context.metric, layout.sample.state, word, 0, layout.sample.unit)
                if g and len(g) == b - a + 1:
                    anchor = model.xs[a] - g[0][1]
                if (anchor is not None and (not matches_authored_glyph_positions(context.metric, layout.sample.state,
                    model.xs[a:b + 1], word, anchor, layout.sample.unit))):
                    anchor = None
        if anchor is not None:
            px, py = get_pos(e.text)
            if (min(anchor, anchor + dx) - layout.sample.unit <= px <= max(anchor, anchor + dx) + layout.sample.unit
                if travel else abs(px - anchor - dx) <= layout.sample.unit + 0.1 * text_height(layout.sample)):
                poss.append((a, b))
    model.span_cache[key] = poss
    return poss


def _translated_held_spans(
    context: TranslatedPhaseContext, model: TranslatedCueModel, e: Event,
    before_ids: set[int], after_ids: set[int], effect_ends: dict[float,list[Event]],
) -> set[tuple[int,int]] | None:
    """Match held text; None rejects the entire event before other phase fallbacks."""
    layout = model.layout
    oldopts = _translated_span_options(context,model,e)
    newopts = _translated_span_options(context,model,e, layout.delta)
    if e.source_index in after_ids:
        opts = set(newopts)
    elif e.source_index in before_ids:
        opts = set(oldopts)
    elif e.end_s < layout.cue.end_s - layout.window:
        if layout.seeds and e.start_s < model.initial_start - 0.011:
            return None
        opts = set(oldopts)
    elif e.start_s >= layout.cue.start_s + layout.window:
        opts = set(newopts)
    else:
        opts = set(oldopts + newopts)
    if len(opts) == 1 and e.start_s >= layout.cue.end_s and e.source_index not in after_ids:
        # A late held tail needs its own touching effect phase.
        # The next cue's entrance cannot be backing for this row.
        opts = {span for span in opts if any(
            abs(p.end_s-e.start_s) <= .001 and any(
                max(span[0],ab[0]) <= min(span[1],ab[1])
                for ab in _translated_span_options(context,model,p,layout.delta,True))
            for p in effect_ends.get(round(e.start_s,2),[]))}
    return opts


def _translated_entrance_spans(
    context: TranslatedPhaseContext, model: TranslatedCueModel, e: Event, px: float,
) -> list[tuple[int,int]]:
    """Match entrance text, recovering recorded glyph anchors for a misread prefix."""
    layout = model.layout
    opts = _translated_span_options(context,model,e)
    if not opts:
        # A prior simplification may have mistaken a narrow
        # letter for a space in an entrance prefix. Match every
        # rendered glyph to the complete row instead of trusting
        # that partial transcript. Missing held glyphs still
        # reject the whole cue below.
        recorded = authored_glyph_positions(context.metric, 
            e.state,context.visible[e.source_index],px,e.unit)
        owners = [[i for i,(c,x) in enumerate(zip(
            [c for c,x in layout.positions],model.xs)) if c == char and
            abs(x-gx) <= layout.sample.unit+.2*text_height(layout.sample)]
            for char,gx in (recorded or [])]
        if (len(owners) >= 4 and all(len(indices) == 1 for indices in owners) and
                all(a[0] < b[0] for a,b in zip(owners,owners[1:]))):
            opts = [(owners[0][0],owners[-1][0])]
    return opts


def _covered_translated_pulses(
    context: TranslatedPhaseContext, model: TranslatedCueModel,
    stable: list[tuple[Event,tuple[int,int]]],
    pulses: list[tuple[Event,list[tuple[int,int]]]],
) -> list[tuple[Event,tuple[int,int]]]:
    """Prove moving pulses against touching or already-held translated backing."""
    layout = model.layout
    # An earlier merge may already hold a whole phrase over a later
    # syllable pulse. Its measured translated span proves that pulse too;
    # do not require the held event to begin again at every word boundary.
    covered_pulses = []
    for e,options in pulses:
        covered = [span for span in options if all(
            any(a <= i <= b and p.start_s <= e.end_s+.001 and p.end_s > e.end_s+.011 and
                (a,b) in _translated_span_options(context,model,p,layout.delta) for p,(a,b) in stable)
            for i in range(span[0],span[1]+1))]
        # Repeated words can have overlapping travel segments. Their
        # exact occurrence is immaterial when the complete held caption
        # already contains every candidate; ownership is still cue-wide.
        if covered:
            covered_pulses.append((e,covered[0]))
    return covered_pulses


def _classify_translated_cue_phases(
    context: TranslatedPhaseContext, model: TranslatedCueModel,
) -> TranslatedCuePhases:
    """Match held text, then entrances, then movement effects in their original order."""
    layout = model.layout
    before_ids = {p.source_index for ids,after,phase,before,d in layout.seeds for p in before}
    after_ids = {p.source_index for ids,after,phase,before,d in layout.seeds for p in after}
    effect_ends = {}
    for p in context.pool.get(layout.cue.style,[]):
        changing = (any(abs(p.state.get(q,0)) > .001 for q in ('fax','fay')) or
                    any(p.state.get(q) != layout.sample.state.get(q) for q in ('fscx','fscy')))
        if (_translated_layout_key(p) == layout.key and changing and opaque_text_effect_state(p.state) and
                layout.cue.start_s-.011 <= p.start_s < layout.cue.end_s and
                abs(get_pos(p.text)[1]-layout.y) <= layout.sample.unit):
            effect_ends.setdefault(round(p.end_s,2),[]).append(p)
    stable = []
    entrances = []
    pulses = []
    for e in context.pool.get(layout.cue.style, []):
        if (_translated_layout_key(e) != layout.key or e.start_s < layout.cue.start_s - layout.window - 0.001 or e.end_s > layout.cue.end_s + layout.window + 0.001
            or (e.start_s >= layout.cue.end_s + layout.window) or (e.end_s <= layout.cue.start_s - layout.window)):
            continue
        w = context.visible[e.source_index]
        px, py = get_pos(e.text)
        flat = (not any((abs(e.state.get(q, 0)) > 0.001 for q in ['fax', 'fay']))
            and all((e.state.get(q) == layout.sample.state.get(q) for q in ['fscx', 'fscy'])))
        if flat and state_key(e, {'pos'}) == state_key(layout.sample, {'pos'}) and (abs(py - layout.y) <= layout.sample.unit):
            opts = _translated_held_spans(context,model,e,before_ids,after_ids,effect_ends)
            if opts is None:
                continue
            if len(opts) == 1:
                stable.append((e, next(iter(opts))))
                continue
        if (flat and e.duration <= layout.window + 0.001 and (e.start_s <= layout.cue.start_s + layout.window)
            and (e.end_s <= layout.cue.start_s + layout.window) and (abs(py - layout.y) <= 0.25 * text_height(layout.sample))
            and (e.state.get('1c') == layout.sample.state.get('1c'))):
            opts = _translated_entrance_spans(context,model,e,px)
            if len(opts) == 1:
                entrances.append((e, opts[0]))
                continue
        if (layout.delta and not flat and opaque_text_effect_state(e.state) and abs(py - layout.y) <= layout.sample.unit
            and (layout.cue.start_s - 0.011 <= e.start_s) and e.start_s < layout.cue.end_s
            and (e.end_s <= layout.cue.end_s + layout.window + 0.001)):
            pulses.append((e,_translated_span_options(context,model,e,layout.delta,True)))
    pulses = _covered_translated_pulses(context,model,stable,pulses)
    return TranslatedCuePhases(stable,entrances,pulses)


def _prove_translated_cue_coverage(
    context: TranslatedPhaseContext, model: TranslatedCueModel, phases: TranslatedCuePhases,
) -> tuple[set[int],list[Event]] | None:
    """Require complete animation and held backing with no competing persistent text."""
    layout = model.layout
    if any((not any((a <= i <= b for e, (a, b) in phases.stable)) for i in range(len(layout.positions)))):
        return None
    # Static matching fragments alone do not prove an animation.
    changed = {ab for e, ab in phases.entrances if abs(get_pos(e.text)[1] - layout.y) > e.unit or e.state.get('1a', 0) > 0}
    if not layout.seeds and len(changed) < 4:
        return None
    if layout.seeds and len(layout.seeds) < 2 and (len(phases.pulses) < 3 or
            sum(len(context.visible[e.source_index]) > 1 for e,span in phases.pulses) < 2):
        return None
    # Every glyph needs completed held backing, not only an early fragment.
    if any(not any(a <= i <= b and p.end_s >= layout.cue.end_s-layout.window and
                   (a,b) in _translated_span_options(context,model,p,layout.delta) for p,(a,b) in phases.stable)
           for i in range(len(layout.positions))):
        return None
    members = [e for e, span in phases.stable + phases.entrances + phases.pulses]
    ids = {e.source_index for e in members}
    if layout.seeds:
        ids.update((i for pi, new, e, before, d in layout.seeds for i in pi))
        members = [context.allids[i] for i in ids]
    blockers = [e for e in context.pool.get(layout.cue.style, []) if _translated_layout_key(e) == layout.key and e.source_index not in ids
        and (layout.cue.start_s - 0.011 <= e.start_s < layout.cue.end_s) and (min(e.end_s, layout.cue.end_s) - max(e.start_s,
        layout.cue.start_s) >= 0.5 * min(e.duration, layout.cue.duration)) and (e.duration >= layout.window)
        and (abs(get_pos(e.text)[1] - layout.y) <= 0.25 * text_height(layout.sample))
        and (model.xs[0] - text_height(layout.sample) <= get_pos(e.text)[0] <= model.xs[-1] + text_height(layout.sample))]
    if blockers:
        return None
    return ids,members


def _render_translated_cue_proposal(
    model: TranslatedCueModel, ids: set[int], members: list[Event],
) -> tuple[set[int],TextRow,str] | None:
    """Use the shared renderer and retain complete glyph anchors for overlap proofs."""
    layout = model.layout
    body = render_merged_caption([layout.sample],[layout.text],layout.text,animated=False,
        an=int(layout.sample.state.get('an',5)),pos=(model.center+layout.delta,layout.y),
        fscx=layout.sample.state.get('fscx',100),fscy=layout.sample.state.get('fscy',100),
        fsp=layout.sample.state.get('fsp',0))
    if body is None:
        return None
    start = min((e.start_s for e in members))
    end = max((e.end_s for e in members))
    base = min(members, key=lambda e: e.source_index)
    caption = (replace_event(base, layer=layout.sample.layer, text=body, start=format_time(start), start_s=start,
        end=format_time(end), end_s=end))
    core = (layout.cue.start_s,layout.cue.end_s) if start < layout.cue.start_s < layout.cue.end_s < end else None
    # Supply the verified glyph anchors even when an earlier pass already
    # combined the held backing into one event. Its center alone is not
    # the row's horizontal extent for the shared overlap pass.
    pieces = [(replace_event(layout.sample,text=render_simplified_caption(
        {**layout.sample.state,'pos':(x+layout.delta,layout.y)},char,measurement=layout.sample.measurement,
        source_paint=_source_caption_paint(layout.sample.state,[layout.sample.state]))),char,(x+layout.delta,layout.y))
        for (char,offset),x in zip(layout.positions,model.xs)]
    row = TextRow(caption,pieces,phase_core=core)
    return ids,row,layout.text


def _apply_translated_cue_proposals(
    events: list[Event], context: TranslatedPhaseContext,
    proposals: list[tuple[set[int],TextRow,str]],
) -> TextPhaseRowsResult:
    """Resolve ownership across complete cues before consuming any source events."""
    # Resolve ownership across complete cues, never greedily by event order.
    claims = collections.Counter((i for ids, e, t in proposals for i in ids))
    accepted = [p for p in proposals if all((claims[i] == 1 for i in p[0]))]
    ids = set().union(*(p[0] for p in accepted)) if accepted else set()
    out = [e for e in events if e.source_index not in ids]+[row.base for ids,row,t in accepted]
    visibility_updates = {}
    for ids,row,t in accepted:
        visibility_updates[row.base.source_index] = t
        if context.font_report is not None:
            context.font_report.rows_joined += 1
    return TextPhaseRowsResult(sorted(out,key=lambda e:e.source_index),
        len(events)-len(out),[row for ids,row,t in accepted],visibility_updates)


def collapse_translated_phase_rows(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics | None, *,
    font_report: FontProcessingReport | None=None,
) -> TextPhaseRowsResult:
    """Flatten complete authored rows with measured entrance/translation phases.

    Touching before/after fragments prove a shared horizontal translation.
    The exact font and authored spaces must account for every glyph in the
    initial row and its held backing. Short bounce/fade phases may then vary
    in paint and grouping; moving syllables need a touching held successor.
    Without translation, at least four changing entrance fragments are needed.
    Missing text, competing persistent neighbors or shared ownership reject
    the cue. Neither actor names nor fixed effect timings/coordinates matter.
    Return protected rows and sparse visibility updates without modifying
    the input map; the pipeline applies them before subsequent consumers.
    """
    if metric is None or not getattr(metric,'available',False):
        return TextPhaseRowsResult(events,0,[],{})
    cues = [e for e in events if e.kind == 'Comment' and e.duration > 0]
    if not cues:
        return TextPhaseRowsResult(events,0,[],{})
    context = _prepare_translated_phases(events,visible,metric,cues, font_report=font_report)
    proposals = []
    for cue in cues:
        layout = _select_translated_cue_layout(context,cue)
        if layout is None:
            continue
        model = _fit_translated_cue_model(context,layout)
        if model is None:
            continue
        phases = _classify_translated_cue_phases(context,model)
        coverage = _prove_translated_cue_coverage(context,model,phases)
        if coverage is None:
            continue
        ids,members = coverage
        proposal = _render_translated_cue_proposal(model,ids,members)
        if proposal is not None:
            proposals.append(proposal)
    return _apply_translated_cue_proposals(events,context,proposals)
