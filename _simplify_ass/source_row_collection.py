"""Original-source row admission, resolved views and visibility evidence.

Inputs stay borrowed; grouping and row buffers belong to one call. Callers
retain timing-map adoption, effect membership, reconstruction and reporting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace as dataclass_replace

from .ass_overrides import (
    tokenize_override, apply_override, evaluate_effective_state,
    OVERRIDE_RE, DEFAULT_STATE,
)
from .row_evidence import TextRow
from .font_metrics import FontMetrics
from .glyph_placement import authored_glyph_positions
from .event_model import Event
from .effect_validation import parse_effect_transform
from .event_operations import event_override_tokens
from .caption_geometry import NUM, get_pos, inline_layout_key, text_height, text_layout_key
from .text_freezing import freeze_block, simplify_text
from .caption_clearance import _glyph_replacement_row_is_clear
from .caption_rendering import CAPTION_PAINT_TAGS


@dataclass
class CollectedSourceText:
    """Collected rows plus explicitly resolved successors of borrowed events.

    The caller adopts events for working formatting. Row events separately
    own sampled paint and immutable authored visibility; the input map and
    its events are never modified by collection.
    """
    events: dict[int,Event]
    rows: list[TextRow]
    words: dict[int,str]
    positions: dict[int,tuple[float,float] | None]


def _source_fragment_opacity_is_coupled(e: Event) -> bool:
    """A fill visibility profile owns only contours/shadows fading with it."""
    # Fill-only visibility cannot stand for a still-visible outline
    # or shadow. Require every painted plane to share the opacity
    # progression; otherwise it remains independent source content.
    tokens = event_override_tokens(e)
    body = OVERRIDE_RE.sub(lambda m:'{'+''.join('\\'+k+v
        for k,v in tokenize_override(m[1]) if k != 't')+'}',e.text)
    base = evaluate_effective_state(body,e.defaults,e.styles)
    states = [base.formatting]
    continuation = base.continuation
    for tag,value in tokens:
        if tag != 't':
            continue
        transform = parse_effect_transform(value,e.duration,
            set(CAPTION_PAINT_TAGS)|{'alpha','c'},allow_instant=True)
        if transform is None:
            return False
        state = states[-1].copy()
        for k,v in transform[2]:
            continuation = apply_override(state,k,v,e.styles,e.defaults,continuation)
        states.append(state)
    for state in states:
        for channel,widths,default in [(3,('xbord','ybord'),'bord'),(4,('xshad','yshad'),'shad')]:
            if (max(abs(state.get(k,state.get(default,0))) for k in widths)>0 and
                    state.get(f'{channel}a',0) != state.get('1a',0)):
                return False
    return True


def _matching_source_row_fragmentations(rows: list[list[Event]], positions: dict,
                                         metric: FontMetrics) -> bool:
    """Compare literal glyph anchors independently of word/letter segmentation.

    Expand each authored fragment with its exact font at its held size. This
    compares real anchors, including spaces within complete captions, without
    fitting a different size or inventing spacing for the fragmented version.
    Contextual shaping and missing glyphs remain unproved.
    """
    reference = None
    layout = text_layout_key(rows[0][0])
    for row in rows:
        glyphs = []
        for e in row:
            if (text_layout_key(e) != layout or
                    OVERRIDE_RE.search(e.text,re.match(r'(?:\{[^}]*\})*',e.text).end())):
                return False
            # The visible-word map trims edge whitespace. ASS anchoring still
            # includes that authored advance, so measure the literal itself.
            literal = OVERRIDE_RE.sub('',e.text)
            expanded = authored_glyph_positions(metric,e.state,literal,
                                                 positions[e.source_index][0],e.unit)
            if expanded is None:
                return False
            glyphs.extend(expanded)
        if reference is None:
            reference = glyphs
        elif (len(glyphs) != len(reference) or
                any(a != b or abs(x-y)>1.5*row[0].unit
                    for (a,x),(b,y) in zip(reference,glyphs))):
            return False
    return True


def collect_source_text_rows(parsed: dict[int, Event], animated: set[int], *,
                              font_metrics: FontMetrics | None = None) -> CollectedSourceText:
    """Record duplicated layout-stable rows before transformations lose timing.

    This collector records text and geometry only. Effect membership belongs
    to remove_source_fragment_effects; paint and text output belong to
    reconstruct_text_rows. Color-only transforms do not change row geometry.
    Visibility intervals distinguish whole-cue rows from alternating layouts.
    Resolve eligible working events into the returned map, never the inputs.
    Sampled row paint and opacity history belong to separate row successors.
    """
    groups: dict[tuple, list[Event]] = {}
    words = {}
    positions = {}
    resolved = dict(parsed)
    for index, e in parsed.items():
        if e.kind != "Dialogue" or e.duration <= 0:
            continue
        words[e.source_index] = simplify_text(e.text,visible_only=True)[1]
        pos = get_pos(e.text)
        if pos is None:
            move = re.search(r"\\move\(\s*("+NUM+r")\s*,\s*("+NUM+r")", e.text, re.I)
            if move:
                pos = (float(move[1]), float(move[2]))
        positions[e.source_index] = pos
        transforms = [value for block in OVERRIDE_RE.findall(e.text)
                      for tag,value in tokenize_override(block) if tag == "t"]
        moving_layout = any(re.search(r"\\(?:fs(?:c[xy]|p)?|fr[xyz]?|fa[xy]|pos|move|org|clip|iclip|fn|an)(?=[^A-Za-z]|$)",
                                     value,re.I) for value in transforms)
        if (pos is None or not words[e.source_index] or moving_layout or
                re.search(r"\\(?:move|clip|iclip|p[1-9]\d*|org|fad|fade)\b", e.text, re.I)):
            continue
        evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
        e = dataclass_replace(e,state=evaluated.formatting,continuation=evaluated.continuation)
        resolved[index] = e
        if (inline_layout_key(e) or any(abs(e.state.get(k,100)) <= .01 for k in ('fscx','fscy')) or
                any(abs(e.state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        profile = ((e.start_s,e.end_s),)
        if transforms and any(tag in {'alpha','1a','r'} for transform in transforms
                              for tag,_ in tokenize_override(transform[1:-1])):
            frozen = freeze_block(''.join(OVERRIDE_RE.findall(e.text)),e.duration,
                                  e.defaults,e.defaults,e.styles,0,prior_opaque_spans=())
            state = frozen.selection.state
            opaque_spans = frozen.selection.opaque_spans
            if not opaque_spans:
                continue
            profile = tuple((e.start_s+a/1000,e.start_s+b/1000) for a,b in opaque_spans)
            e = dataclass_replace(e,state=state,continuation=frozen.selection.continuation)
        if e.state.get('1a',0) != 0:
            continue
        e = dataclass_replace(e,state=dict(e.state),
                              evidence=dataclass_replace(e.evidence,opaque_spans=profile))
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
               e.start,e.end,pos[1],
               tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
                     ("fn","fs","fscx","fscy","fsp","b","i","an")))
        groups.setdefault((*key,profile,e.layer),[]).append(e)

    families: dict[tuple,list[list[Event]]] = {}
    norm = lambda value: "".join(value.split())
    for key, group in groups.items():
        ordered = sorted(group,key=lambda e: positions[e.source_index][0])
        if ((len(ordered) < 4 and (font_metrics is None or not font_metrics.available)) or
                len({positions[e.source_index][0] for e in ordered}) != len(ordered)):
            continue
        text = norm("".join(words[e.source_index] for e in ordered))
        families.setdefault((*key[:-2],text),[]).append(ordered)

    evidence = []
    for rows in families.values():
        mixed = len({tuple(words[e.source_index] for e in row) for row in rows}) > 1
        short_layout = any(len(row)<4 for row in rows)
        profiles = {row[0].evidence.opaque_spans for row in rows}
        measured_alternation = (mixed and len(profiles)>1 and
                                font_metrics is not None and font_metrics.available)
        if measured_alternation:
            if (not _matching_source_row_fragmentations(rows,positions,font_metrics) or
                    not all(_source_fragment_opacity_is_coupled(e) for row in rows for e in row)):
                continue
            members = {e.source_index for row in rows for e in row}
            if any(not e.layer.lstrip('-').isdigit() for row in rows for e in row):
                continue
            low = min(int(e.layer) for row in rows for e in row)
            high = max(int(e.layer) for row in rows for e in row)
            # Reuse the source-row compositing proof. Holding a selected phase
            # over the cue must not move it across independent intervening ink.
            probes = min(rows,key=len)
            poses = [e for row in rows for e in row]
            if any(not _glyph_replacement_row_is_clear(
                    dataclass_replace(e,layer=str(low)),(e.start_s,e.end_s),members,high,
                    parsed,font_metrics,poses) for e in probes):
                continue
        elif short_layout:
            # Complete/short layouts enter only the source alternation proof,
            # never the dense-particle or ordinary stable-row heuristics.
            continue
        chosen = max(rows,key=lambda row:(sum(b-a for a,b in row[0].evidence.opaque_spans),
                                         -row[0].evidence.opaque_spans[0][0] if measured_alternation else 0,
                                         len(row),int(row[0].layer) if row[0].layer.lstrip('-').isdigit() else 0))
        first = chosen[0]
        height = text_height(first)
        if not measured_alternation and any(abs(positions[row[0].source_index][0]-positions[first.source_index][0]) > .5*height or
               abs(positions[row[-1].source_index][0]-positions[chosen[-1].source_index][0]) > .5*height
               for row in rows):
            continue
        anchors: dict[str,list[tuple[float,float]]] = {}
        for paint_row in rows:
            for e in paint_row:
                anchors.setdefault(words[e.source_index],[]).append(positions[e.source_index])
        evidence.append(TextRow(
            first, [(e, words[e.source_index], positions[e.source_index]) for e in chosen],
            paint_rows=rows, source_anchors=anchors))
    return CollectedSourceText(resolved,evidence,words,positions)

