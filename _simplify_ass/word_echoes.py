"""Source-owned word fade/jitter proof and atomic echo removal."""
from __future__ import annotations

import math
import statistics
from dataclasses import replace as dataclass_replace
from typing import Iterable

from .ass_overrides import DEFAULT_STATE
from .caption_geometry import get_pos, inline_layout_key, text_height, text_layout_key
from .event_model import Event
from .event_operations import event_evaluation
from .font_metrics import FontMetrics
from .fragment_spans import index_fragment_spans, matching_fragment_spans
from .glyph_placement import authored_glyph_positions, fit_fragment_anchor
from .row_evidence import CoveredFragmentRemoval
from .static_objects import static_object_key
from .static_selection import unrotated_text_state


def _word_echo_layout(e: Event) -> tuple:
    """Match authored paragraph geometry independently of paint and position."""
    return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,
            text_layout_key(e))


def _word_echo_families(events: list[Event]) -> Iterable[list[Event]]:
    """Collect nearby frame copies before testing the entire displacement box."""
    components = []
    for e in sorted(events,key=lambda e:(e.start_s,e.end_s,e.source_index)):
        pos = get_pos(e.text)
        for component,end in reversed(components):
            first = component[0]
            if (e.start_s <= end[0]+1e-6 and
                    all(abs(a-b) <= .25*text_height(first)
                        for a,b in zip(pos,get_pos(first.text)))):
                component.append(e)
                end[0] = max(end[0],e.end_s)
                break
        else:
            components.append(( [e], [e.end_s] ))
    for component,_ in components:
        yield component


def _prove_word_echo_family(members: list[Event]) -> bool:
    """Prove dense short fade frames or faint copies with repeated jitter."""
    frames = {}
    height = text_height(members[0])
    positions = [get_pos(e.text) for e in members]
    if any(max(p[axis] for p in positions)-min(p[axis] for p in positions)
           > .06*height+1e-6 for axis in (0,1)):
        return False
    for e in members:
        frames.setdefault((e.start_s,e.end_s),[]).append(e)
    ordered = sorted(frames)
    if (len(ordered) < 3 or len(members) < 8 or any(abs(a[1]-b[0]) > 1e-6
                               for a,b in zip(ordered,ordered[1:]))):
        return False
    alphas,centers = [],[]
    for interval in ordered:
        copies = frames[interval]
        values = {e.state.get('1a',0) for e in copies}
        if len(values) != 1:
            return False
        alphas.append(values.pop())
        centers.append(tuple(statistics.mean(get_pos(e.text)[axis] for e in copies)
                             for axis in (0,1)))
    fade = (alphas[0] <= 128 and alphas[-1] >= 224 and
            alphas[-1]-alphas[0] >= 64 and
            all(a <= b for a,b in zip(alphas,alphas[1:])))
    reversals = 0
    for axis in (0,1):
        signs = [1 if b[axis] > a[axis] else -1 for a,b in zip(centers,centers[1:])
                 if abs(b[axis]-a[axis]) > .001*height]
        reversals = max(reversals,sum(a != b for a,b in zip(signs,signs[1:])))
    return fade or (min(alphas) >= 128 and reversals >= 2)


def _owned_word_echo_anchors(caption: Event, literal: str, word: str,
                              metric: FontMetrics) -> list[float]:
    """Disambiguate repeated literal occurrences with the retained exact font."""
    unit = .06*text_height(caption)
    glyphs = authored_glyph_positions(metric,caption.state,literal,
                                      get_pos(caption.text)[0],unit)
    if glyphs is None:
        return []
    index = index_fragment_spans(c for c,_ in glyphs)
    # The shared index ignores spaces. Keep only actual contiguous literals;
    # a word must not match letters on opposite sides of an authored space.
    occurrences = set()
    offset = literal.find(word)
    while offset >= 0:
        occurrences.add(sum(not c.isspace() for c in literal[:offset]))
        offset = literal.find(word,offset+1)
    anchors = []
    for first,last in matching_fragment_spans(index,word):
        if first not in occurrences:
            continue
        xs = [x for _,x in glyphs[first:last+1]]
        fragments = [c for c,_ in glyphs[first:last+1]]
        anchor = fit_fragment_anchor(metric,caption.state,xs,fragments,word,unit,
                                     exact_size=True,allow_tracking=True)
        if anchor is not None:
            anchors.append(anchor)
    return anchors


def remove_owned_word_echoes(events: list[Event], visible_map: dict[int,str],
                              captions: tuple[Event,...], sources: dict[int,Event],
                              metric: FontMetrics | None, *, max_piece_duration: float=.16
                              ) -> CoveredFragmentRemoval:
    """Atomically remove original word frames owned by one accepted full line.

    Exact font/layout/position, dense fade or jitter evidence, and one cue owner
    are required. Missing fonts or competing ownership preserve the family.
    Faint tails may follow the parent; they never extend its caption interval.
    """
    if not captions or metric is None or not metric.available:
        return CoveredFragmentRemoval(events,[],0)
    owners = {}
    for caption in captions:
        owners.setdefault(_word_echo_layout(caption),[]).append(caption)
    owner_styles = {caption.style for caption in captions}
    buckets = {}
    for e in events:
        source = sources.get(e.source_index)
        literal = visible_map.get(e.source_index,'')
        if source is not None and source.style in owner_styles and not source.state:
            evaluated = event_evaluation(source)
            source = dataclass_replace(source,state=evaluated.formatting,
                                       continuation=evaluated.continuation)
        if (source is None or not literal or any(c.isspace() for c in literal) or
                source.duration <= 0 or source.duration > max_piece_duration+1e-6 or
                source.start_s != e.start_s or source.end_s != e.end_s or
                get_pos(source.text) is None or inline_layout_key(source) or
                any(k in source.state for k in ('clip','iclip','org')) or
                not unrotated_text_state(source.state) or source.state.get('p',0) or
                source.state.get('borderstyle',1) != 1 or
                not math.isfinite(text_height(source)) or text_height(source) <= 0 or
                any(not math.isfinite(v) for v in get_pos(source.text))):
            continue
        layout = _word_echo_layout(source)
        if layout not in owners:
            continue
        obj = static_object_key(source,source.styles)
        if obj is None or len(obj[-1]) != 1 or obj[-1][0][1] or obj[-1][0][2] != literal:
            continue
        paint = tuple((k,source.state.get(k,DEFAULT_STATE.get(k))) for k in
                      ('1c','2c','3c','4c','bord','xbord','ybord','shad','blur','be'))
        buckets.setdefault((layout,literal,source.layer,paint),[]).append(source)
    removed,anchors = set(),{}
    for (layout,word,_,_),bucket in buckets.items():
        for members in _word_echo_families(bucket):
            if not _prove_word_echo_family(members):
                continue
            start,end = min(e.start_s for e in members),max(e.end_s for e in members)
            matches = []
            for caption in owners[layout]:
                literal = visible_map.get(caption.source_index,'')
                if (literal == word or start < caption.start_s-1e-6 or
                        start >= caption.end_s or end > caption.end_s+.8+1e-6 or
                        min(end,caption.end_s)-start < min(.16,.5*(end-start)) or
                        any(e.end_s > caption.end_s+1e-6 and e.state.get('1a',0) < 128
                            for e in members)):
                    continue
                key = (caption.source_index,word)
                if key not in anchors:
                    anchors[key] = _owned_word_echo_anchors(caption,literal,word,metric)
                unit = .06*text_height(caption)
                y = get_pos(caption.text)[1]
                for x in anchors[key]:
                    if all(abs(get_pos(e.text)[0]-x) <= unit+1e-6 and
                           abs(get_pos(e.text)[1]-y) <= unit+1e-6 for e in members):
                        matches.append(caption)
            if len(matches) == 1:
                removed.update(e.source_index for e in members)
    return CoveredFragmentRemoval([e for e in events if e.source_index not in removed],
                                   [],len(removed))
