"""Recorded-row ownership proofs and removal of redundant glyph effects."""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace as dataclass_replace, field

from .ass_overrides import (
    OverrideContinuation, tokenize_override, apply_override,
    evaluate_effective_state, OVERRIDE_RE,
)
from .source_poses import prefer_surviving_upright_poses
from .row_evidence import TextRow, CoveredFragmentRemoval
from .fragment_spans import index_fragment_spans, matching_fragment_spans
from .font_metrics import FontMetrics
from .glyph_placement import fit_fragment_anchor
from .event_model import Event
from .boundary_glyphs import match_boundary_glyph_effects
from .effect_validation import parse_effect_move, animated_shadow_painted_source
from .event_operations import event_override_tokens, replace_event, state_key
from .static_objects import static_object_key
from .caption_geometry import (
    get_pos, inline_layout_key, text_height, placement_key, text_layout_key,
)
from .text_freezing import simplify_text
from .caption_rendering import _source_caption_paint, render_simplified_caption
from .boundary_groups import nearby_boundary_groups


@dataclass(frozen=True)
class CoveredFragmentContext:
    """Original row evidence, timing indexes and caches owned by one removal pass.

    Row models are borrowed and read-only. Selected timing proofs are returned
    separately. The maps and caches are temporary and never stored on events.
    """
    visible: dict[int,str]
    animated: set[int]
    sources: dict[int,Event] | None
    metric: FontMetrics | None
    anchors: dict[int,list[tuple[str,float]]]
    models: dict[int,TextRow]
    layouts: dict[int,tuple]
    rows: dict[str,list[Event]]
    virtual: set[int]
    static_glyphs: dict[int,list[tuple[Event,str,tuple]]]
    row_indexes: dict[str,tuple | None]
    span_indexes: dict[tuple,tuple] = field(default_factory=dict,compare=False)
    shadow_sources: dict[int,bool] = field(default_factory=dict,compare=False)
    shadow_rows: set[int] = field(default_factory=set,compare=False)
    shadow_layers: dict[int,int] = field(default_factory=dict,compare=False)
    shadow_poses: dict[int,Event] = field(default_factory=dict,compare=False)



def match_departing_glyph_effects(
    events: list[Event], row_evidence: list[TextRow], source_events: dict[int, Event],
    metric: FontMetrics | None,
) -> set[int]:
    """Prove complete outline exits from retained fragments' original anchors.

    A whole letter group must spell its source fragment, begin within 50 ms
    of that fragment's end, and fit the exact font at its authored position.
    Moving, fading contours are decorative exits; partial or ambiguous groups stay.
    This proof uses source trajectories rather than frozen effect positions.
    """
    if metric is None or not metric.available or not any(not row.virtual for row in row_evidence):
        return set()
    groups = {}
    for e in events:
        original = source_events.get(e.source_index)
        if (original is None or e.kind != "Dialogue" or
                not re.search(r"\\move\s*\(",original.text,re.I)):
            continue
        word = simplify_text(original.text,visible_only=True)[1]
        if len(word) != 1 or word.isspace() or unicodedata.combining(word):
            continue
        tokens = [token for block in OVERRIDE_RE.findall(original.text)
                  for token in tokenize_override(block)]
        moves = [value for tag,value in tokens if tag == "move"]
        if len(moves) != 1 or inline_layout_key(original):
            continue
        move = parse_effect_move(moves[0],original.duration,endpoint_slack=.001)
        if move is None or move[:2] == move[2:4]:
            continue
        evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
        state = evaluated.formatting
        final = state.copy()
        final_continuation = evaluated.continuation
        opaque_fill = False
        for tag,value in tokens:
            if tag == "t":
                for name,argument in tokenize_override(value[1:-1]):
                    final_continuation = apply_override(final,name,argument,original.styles,original.defaults,final_continuation)
                    opaque_fill |= final.get("1a",0) < 254
        if (opaque_fill or state.get("1a",0) < 254 or state.get("3a",0) >= 128 or
                final.get("1a",0) < 254 or final.get("3a",0) < 254 or
                any(s.get("p",0) or s.get("borderstyle",1) != 1 or
                    any(k in s for k in ("clip","iclip","org")) or
                    any(abs(s.get(k,s.get("shad",0))) > 0 for k in ("xshad","yshad"))
                    for s in (state,final)) or
                any(abs(state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        layout = tuple((k,str(v).casefold() if k == "fn" else v)
                       for k,v in text_layout_key(dataclass_replace(original,state=state,continuation=evaluated.continuation)))
        key = (original.style,original.name,
               placement_key(dataclass_replace(original,state=state,continuation=evaluated.continuation))[0],layout)
        groups.setdefault(key,{}).setdefault(original.start_s,[]).append((e,move,word))
    boundary_index = {key:(sorted(phases),phases) for key,phases in groups.items()}
    proofs = []
    for row in row_evidence:
        if row.virtual:
            continue
        for piece,word,pos in row.pieces:
            original = source_events.get(piece.source_index)
            if (original is None or get_pos(original.text) is None or
                    math.dist(get_pos(original.text),pos) > piece.unit or
                    not word or any(c.isspace() or unicodedata.combining(c) or
                        unicodedata.bidirectional(c) in {"R","AL","AN"} for c in word) or
                    piece.state.get("1a",255) != 0 or inline_layout_key(original)):
                continue
            layout = tuple((k,str(v).casefold() if k == "fn" else v)
                           for k,v in text_layout_key(piece))
            key = (piece.style,piece.name,placement_key(piece)[0],layout)
            for boundary,candidates in nearby_boundary_groups(boundary_index,key,original.end_s):
                peers = sorted(candidates,key=lambda item:item[1][0])
                if (len(peers) != len(word) or "".join(item[2] for item in peers) != word or
                        not original.layer.lstrip("-").isdigit() or
                        any(not source_events[e.source_index].layer.lstrip("-").isdigit() or
                            int(source_events[e.source_index].layer) <= int(original.layer)
                            for e,move,char in peers) or
                        any(abs(move[1]-pos[1]) > piece.unit for e,move,char in peers)):
                    continue
                expected = fit_fragment_anchor(metric, piece.state,
                    [move[0] for e,move,char in peers],[char for e,move,char in peers],word,piece.unit)
                if expected is None or abs(expected-pos[0]) > 1.5*piece.unit:
                    continue
                proofs.append((piece.source_index,{e.source_index for e,move,char in peers}))
    effect_owners, caption_owners = {}, {}
    for source_index,members in proofs:
        caption_owners[source_index] = caption_owners.get(source_index,0)+1
        for index in members:
            effect_owners[index] = effect_owners.get(index,0)+1
    return {index for source_index,members in proofs
            if caption_owners[source_index] == 1 and
               all(effect_owners[index] == 1 for index in members)
            for index in members}



def match_staggered_row_effects(
    events: list[Event], row_evidence: list[TextRow], source_events: dict[int, Event],
    animated_sources: set[int], metric: FontMetrics | None,
) -> set[int]:
    """Prove complete animated copies at a recorded row's source phase ends.

    Normalize vertical alignment at the stable pose. Every source fragment
    must belong to exactly one copy, with phase offsets within 50 ms,
    monotonic timing and matching font geometry. Partial and ambiguous
    families stay.
    """
    if metric is None or not metric.available or not any(not row.virtual for row in row_evidence):
        return set()
    buckets = {}
    identity = lambda e: (e.style,e.name,placement_key(e)[0],
        tuple((k,str(v).casefold() if k == "fn" else v)
              for k,v in text_layout_key(e) if k not in {"an","org"}),
        (int(e.state.get("an",5))-1)%3)
    for e in events:
        original = source_events.get(e.source_index)
        if (original is None or e.kind != "Dialogue" or
                e.source_index not in animated_sources or get_pos(original.text) is None or
                inline_layout_key(original) or not re.search(r"\\t\s*\(",original.text,re.I)):
            continue
        # Literal edge spaces affect alignment. The visible-word collector
        # intentionally strips them, so retain the unrendered source payload.
        words = OVERRIDE_RE.sub("",original.text).replace(r"\h"," ")
        if not words.strip() or original.duration <= 0 or any(tag in words for tag in (r"\N",r"\n")):
            continue
        evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
        state = evaluated.formatting
        final = state.copy()
        final_continuation = evaluated.continuation
        moving = False
        for block in OVERRIDE_RE.findall(original.text):
            for tag,value in tokenize_override(block):
                if tag == "t":
                    for name,argument in tokenize_override(value[1:-1]):
                        moving |= name in {"pos","move","org","clip","iclip","p","r",
                                           "fn","fs","fsp","an","pbo","encoding","q"}
                        final_continuation = apply_override(final,name,argument,original.styles,original.defaults,final_continuation)
        if (moving or any(s.get("p",0) or s.get("1a",0) >= 128 or
                         any(k in s for k in ("clip","iclip")) or
                         any(abs(s.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))
                         for s in (state,final))):
            continue
        stable = dataclass_replace(original,state=final,continuation=final_continuation)
        if identity(dataclass_replace(original,state=state,continuation=evaluated.continuation)) != identity(stable):
            continue
        pos = get_pos(original.text)
        # For equal horizontal alignment, only the vertical box anchor moves.
        y = pos[1]+((int(final.get("an",5))-1)//3-1)*text_height(stable)/2
        buckets.setdefault(identity(stable),[]).append((original,words,(pos[0],y)))
    families = []
    for row in row_evidence:
        if row.virtual or len(row.pieces) < 4:
            continue
        first = row.pieces[0][0]
        key = identity(first)
        peers = buckets.get(key,[])
        if not peers:
            continue
        originals = [source_events.get(piece.source_index) for piece,word,pos in row.pieces]
        if any(e is None or e.duration <= 0 for e in originals):
            continue
        height = min(text_height(piece) for piece,word,pos in row.pieces)
        ys = [pos[1]+((int(piece.state.get("an",5))-1)//3-1)*text_height(piece)/2
              for piece,word,pos in row.pieces]
        duration = max(e.end_s for e in originals)-min(e.start_s for e in originals)
        longest = max(len("".join(words.split())) for e,words,pos in peers)
        spans = {}
        for index in range(len(row.pieces)):
            text = ""
            for last in range(index,len(row.pieces)):
                text += "".join(row.pieces[last][1].split())
                if len(text) > longest:
                    break
                spans.setdefault(text,[]).append((index,last))
        matched = []
        covered = [0]*len(row.pieces)
        for original,words,pos in peers:
            if abs(pos[1]-statistics.median(ys)) > .06*height:
                continue
            options = []
            for index,last in spans.get("".join(words.split()),[]):
                pieces = row.pieces[index:last+1]
                x = fit_fragment_anchor(metric, first.state,[point[0] for piece,word,point in pieces],
                                           [word for piece,word,point in pieces],words,first.unit)
                sources = originals[index:last+1]
                ends = [e.end_s for e in sources]
                delta = original.start_s-max(ends)
                if (x is None or max(ends)-min(ends) > .011 or abs(delta) > .05*duration or
                        abs(pos[0]-x) > .12*height or
                        not original.layer.lstrip("-").isdigit() or
                        any(not e.layer.lstrip("-").isdigit() or
                            (int(original.layer),original.source_index) <= (int(e.layer),e.source_index)
                            for e in sources)):
                    continue
                options.append((index,last,delta))
            if len(options) == 1:
                index,last,delta = options[0]
                matched.append((index,original,delta))
                for glyph in range(index,last+1):
                    covered[glyph] += 1
        if len(matched) < 4 or any(count != 1 for count in covered):
            continue
        matched.sort(key=lambda item:item[0])
        offsets = [delta for index,e,delta in matched]
        # Authored handoffs can vary by a few centiseconds across syllables.
        # Keep the tolerance bounded; the epsilon only absorbs float rounding.
        if (max(offsets)-min(offsets) > .05+1e-6 or
                any(a.start_s > b.start_s+.011 or a.end_s > b.end_s+.011
                    for (_,a,_),(_,b,_) in zip(matched,matched[1:]))):
            continue
        families.append({e.source_index for index,e,delta in matched})
    counts = {}
    for family in families:
        for index in family:
            counts[index] = counts.get(index,0)+1
    return set().union(*(family for family in families if all(counts[index] == 1 for index in family)))



def _collect_covered_held_glyphs(row_evidence: list[TextRow], animated_sources: set[int]):
    """Validate recorded held glyphs against the emitted per-character caption paint."""
    # A row extended across animation phases may also cover surviving held
    # glyphs. Match its recorded pieces and emitted per-character paint, not
    # substrings or nearby positions. Requiring unchanged scales avoids
    # treating an approximate font fit as proof of identical glyph geometry.
    static_glyphs = {}
    for row in row_evidence:
        if (row.virtual or len(row.pieces) < 2 or
                any(piece.source_index not in animated_sources or len(text) != 1 or
                    text.isspace() or unicodedata.combining(text) or
                    unicodedata.bidirectional(text) in {'R','AL','AN'} or
                    piece.layer != row.base.layer
                    for piece,text,pos in row.pieces)):
            continue
        state = row.base.defaults.copy()
        continuation = OverrideContinuation()
        painted = []
        for part in re.split(r"(\{[^}]*\})",row.base.text):
            if part.startswith('{'):
                for tag,value in tokenize_override(part[1:-1]):
                    continuation = apply_override(state,tag,value,row.base.styles,
                                                  row.base.defaults,continuation)
            else:
                painted.extend((char,state.copy(),continuation) for char in part if not char.isspace())
        if ''.join(char for char,state,_ in painted) != ''.join(text for piece,text,pos in row.pieces):
            continue
        glyphs = []
        for (piece,text,pos),(char,paint,paint_continuation) in zip(row.pieces,painted):
            if (piece.state.get('1a',0) != 0 or
                    paint.get('1a',0) != 0 or paint.get('3a',0) != 0 or
                    (int(paint.get('an',2))-1)//3 != (int(piece.state.get('an',2))-1)//3 or
                    abs(get_pos(row.base.text)[1]-pos[1]) > .001):
                continue
            emitted = dataclass_replace(piece,state=paint,continuation=paint_continuation)
            # Assembly preserves proved contours and simplifies uncertain paint,
            # shadows and blur. Validate the conversion rather than equating output
            # paint with the unsimplified held phase. Foreground formatting
            # and geometry, including per-glyph colours and scales, must agree.
            paint_key = state_key(emitted,{'pos','an'})
            if paint_key != state_key(piece,{'pos','an'}):
                normalized = replace_event(piece,text=render_simplified_caption(piece.state,text,measurement=piece.measurement,
                    source_paint=_source_caption_paint(piece.state,[piece.state])))
                if paint_key != state_key(normalized,{'pos','an'}):
                    continue
            glyphs.append((piece,text,pos))
        static_glyphs[row.base.source_index] = glyphs
    return static_glyphs



def _index_covered_row_times(rows: dict[str,list[Event]]):
    """Index original row order with start times and prefix maximum end times."""
    # Index each style's original row order by start time. Prefix maximum
    # ends keep earlier long-running captions in the candidate window.
    row_indexes = {}
    for style,group in rows.items():
        if any(not math.isfinite(t) for base in group for t in (base.start_s,base.end_s)):
            row_indexes[style] = None
            continue
        ordered = sorted(enumerate(group),key=lambda item:item[1].start_s)
        starts = [base.start_s for order,base in ordered]
        latest = []
        for order,base in ordered:
            latest.append(max(latest[-1] if latest else -math.inf,base.end_s))
        row_indexes[style] = (starts,latest,ordered)
    return row_indexes



def _prepare_covered_fragments(
    visible_map: dict[int, str], row_evidence: list[TextRow], animated_sources: set[int],
    source_events: dict[int, Event] | None, font_metrics: FontMetrics | None,
):
    """Build pass-local row evidence and indexes without rediscovering geometry."""
    anchors = {row.base.source_index: row.anchors for row in row_evidence}
    models = {row.base.source_index: row for row in row_evidence}
    layouts = {row.base.source_index: tuple(
        (key,str(value).casefold() if key == "fn" else value)
        for key,value in text_layout_key(row.pieces[0][0])
        if key not in {"fscx","fscy"}) for row in row_evidence}
    rows: dict[str,list[Event]] = {}
    virtual: set[int] = set()
    for row in row_evidence:
        rows.setdefault(row.base.style,[]).append(row.base)
        if row.virtual:
            virtual.add(row.base.source_index)
    static_glyphs = _collect_covered_held_glyphs(row_evidence,animated_sources)
    row_indexes = _index_covered_row_times(rows)
    return CoveredFragmentContext(visible_map,animated_sources,source_events,font_metrics,
        anchors,models,layouts,rows,virtual,static_glyphs,row_indexes)



def _covered_fragment_spans(context: CoveredFragmentContext, base: Event, visible: str, shadow_only: bool):
    """Cache recorded fragment spans separately for exact and shadow casefold matching."""
    key = (base.source_index,shadow_only)
    if key not in context.span_indexes:
        context.span_indexes[key] = index_fragment_spans(
            (text for text,x in context.anchors[base.source_index]),casefold=shadow_only)
    target = ''.join(visible.split())
    if shadow_only:
        target = target.casefold()
    yield from matching_fragment_spans(context.span_indexes[key],target)



def _covered_animated_shadow_source(context: CoveredFragmentContext, e: Event):
    """Cache original animated shadow paint, including copies transferred to foreground."""
    # Copy reduction can transfer animated shadow paint into the primary
    # channel. Retain the original evidence when checking its highlight
    # fragments; actor labels need not identify the same effect phase.
    if e.source_index not in context.shadow_sources:
        context.shadow_sources[e.source_index] = animated_shadow_painted_source(e,context.sources,context.animated)
    return context.shadow_sources[e.source_index]



def _covered_held_glyph_copy(context: CoveredFragmentContext, e: Event, visible: str, pos: tuple, base: Event):
    """Prove one stationary letter repeats an exactly placed recorded held glyph."""
    if (not context.static_glyphs.get(base.source_index) or
            e.source_index in context.animated or len(visible) != 1 or
            e.style != base.style or e.name != base.name or
            e.start_s < base.start_s or e.end_s > base.end_s):
        return False
    matches = [piece for piece,text,anchor in
               context.static_glyphs.get(base.source_index,[]) if text == visible and
               math.dist(pos,anchor) <= .001]
    if len(matches) != 1:
        return False
    piece = matches[0]
    return (e.layer == piece.layer and placement_key(e) == placement_key(piece) and
            state_key(e,{'pos'}) == state_key(piece,{'pos'}) and
            static_object_key(e,e.styles) is not None)



def _timed_covered_rows(context: CoveredFragmentContext, style: str, e: Event):
    """Search the indexed timing window while retaining original row order and tolerance."""
    index = context.row_indexes.get(style)
    if index is None or not all(math.isfinite(t) for t in (e.start_s,e.end_s)):
        return list(context.rows.get(style,[]))
    starts,latest,ordered = index
    # Expand the bounds by one floating-point step. The unchanged exact
    # comparisons below decide equality at the existing 0.15 s tolerance.
    left = bisect_left(latest,math.nextafter(e.end_s-.15,-math.inf))
    right = bisect_right(starts,math.nextafter(e.start_s+.15,math.inf))
    candidates = [(order,base) for order,base in ordered[left:right]
                  if not (e.start_s < base.start_s-.15 or e.end_s > base.end_s+.15)]
    return [base for order,base in sorted(candidates,key=lambda item:item[0])]



def _prepare_covered_shadow_rows(context: CoveredFragmentContext):
    """Identify complete animated shadow rows and their original source layers."""
    # A shadow-painted highlight may already have become a partial caption.
    # Prove ownership using its recorded source fragments, before inferred
    # tracking or its new paragraph anchor obscures the original glyph row.
    shadow_rows = {index for index,row in context.models.items() if not row.virtual and
                   row.pieces and all(_covered_animated_shadow_source(context,piece) for piece,_,_ in row.pieces)}
    shadow_layers = {index:max(int(piece.layer) if piece.layer.lstrip('-').isdigit() else 0
                             for piece,_,_ in context.models[index].pieces) for index in shadow_rows}
    context.shadow_rows.update(shadow_rows)
    context.shadow_layers.update(shadow_layers)



def _shared_covered_shadow_fade_core(context: CoveredFragmentContext, row: TextRow, base: Event):
    """Use one shared positive source fade to protect a completed remuxed lyric core."""
    fades = set()
    for piece,_,_ in row.pieces:
        original = (context.sources or {})[piece.source_index]
        values = [value for tag,value in event_override_tokens(original) if tag == 'fad']
        try:
            pair = tuple(float(v)/1000 for v in values[0].strip('()').split(','))
        except (IndexError,ValueError):
            break
        if (len(values) != 1 or len(pair) != 2 or
                not all(math.isfinite(v) and v > 0 for v in pair) or
                sum(pair) >= original.duration):
            break
        fades.add(pair)
    else:
        if len(fades) == 1:
            entrance,tail = next(iter(fades))
            return (round(base.start_s+entrance,2),round(base.end_s-tail,2))
    return None



def _select_covered_shadow_timing(events: list[Event], context: CoveredFragmentContext) -> dict[int,tuple[float,float]]:
    """Return proved cores keyed by row identity without modifying input evidence.

    Identity preserves the selected model when rows share a source index, and
    applies the same proof to repeated references to that model.
    """
    # Authored cue intervals protect the completed lyric while the shared
    # overlap pass trims only the surrounding reconstructed entrance/tail.
    # Require a complete, equally timed source glyph row and one exact cue.
    cue_comments = {}
    cores = {}
    if context.shadow_rows:
        for e in events:
            if e.kind == 'Comment':
                words = simplify_text(e.text,visible_only=True)[1]
                cue_comments.setdefault((e.style,words),[]).append(e)
    for index in context.shadow_rows:
        row = context.models[index]
        base = row.base
        if row.phase_core is not None or not all(
                round((context.sources or {})[piece.source_index].start_s,2) == round(base.start_s,2) and
                round((context.sources or {})[piece.source_index].end_s,2) == round(base.end_s,2)
                for piece,_,_ in row.pieces):
            continue
        cues = {(cue.start_s,cue.end_s) for cue in
                cue_comments.get((base.style,context.visible.get(index,'')),[]) if
                base.start_s < cue.start_s < cue.end_s < base.end_s}
        if len(cues) == 1:
            cores[id(row)] = next(iter(cues))
        elif not cue_comments.get((base.style,context.visible.get(index,''))):
            # Remuxed tracks often omit the authored Comment lines. A complete
            # coextensive shadow row can still prove its entrance/tail from one
            # shared fade. Animation/paint ownership was checked above; these
            # fades supply timing only, never permission to remove other rows.
            core = _shared_covered_shadow_fade_core(context,row,base)
            if core is not None:
                cores[id(row)] = core
    return cores



def _covered_shadow_fragment_copy(context: CoveredFragmentContext, piece: Event, text: str, pos: tuple, base: Event):
    """Match a nested shadow-painted fragment using the existing upright-pose proof."""
    if (not _covered_animated_shadow_source(context,piece) or base.source_index not in context.shadow_rows or
            piece.state.get('p',0) or inline_layout_key(piece) or
            any(k in piece.state for k in ('clip','iclip','org')) or
            piece.duration >= base.duration-.011 or
            piece.start_s < base.start_s-.15 or piece.end_s > base.end_s+.15 or
            piece.state.get('1a',0) != 0 or base.state.get('1a',0) != 0 or
            piece.state.get('1c') != base.state.get('1c') or
            not piece.layer.lstrip('-').isdigit() or
            int(piece.layer) <= context.shadow_layers[base.source_index] or
            placement_key(piece)[0] != placement_key(base)[0] or
            abs(pos[1]-get_pos(base.text)[1]) > .06*min(text_height(piece),text_height(base))):
        return False
    if piece.source_index not in context.shadow_poses:
        # The final rotation cleanup would select this same authored
        # upright pose. Use that helper here too, so a late pulse is not
        # mistaken for an independent angled letter merely because the
        # initial frozen sample preceded its readable pose.
        context.shadow_poses[piece.source_index] = prefer_surviving_upright_poses(
            [piece],context.sources or {})[0]
    pose = context.shadow_poses[piece.source_index]
    layout = tuple((key,str(value).casefold() if key == 'fn' else value)
                   for key,value in text_layout_key(pose) if key not in {'fscx','fscy'})
    if layout != context.layouts[base.source_index]:
        return False
    glyphs = context.anchors[base.source_index]
    matches = [(first,last) for first,last in _covered_fragment_spans(context,base,text,False) if
               abs(pos[0]-(glyphs[first][1]+glyphs[last][1])/2) <=
               .12*min(text_height(piece),text_height(base))]
    return len(matches) == 1



def _remove_covered_shadow_fragments(events: list[Event], context: CoveredFragmentContext, removed: set[int]):
    """Remove shadow fragment rows only when exactly one complete row owns them."""
    for e in events:
        pos = get_pos(e.text)
        text = context.visible.get(e.source_index,'')
        if e.kind != 'Dialogue' or not text or pos is None or e.source_index in removed:
            continue
        model = context.models.get(e.source_index)
        pieces = model.pieces if model is not None and not model.virtual else [(e,text,pos)]
        if not pieces or not all(_covered_animated_shadow_source(context,piece) for piece,_,_ in pieces):
            continue
        owners = [base for base in _timed_covered_rows(context,e.style,e) if base.source_index != e.source_index and
                  all(_covered_shadow_fragment_copy(context,piece,word,point,base) for piece,word,point in pieces)]
        if len(owners) == 1:
            removed.add(e.source_index)



def _covered_fragment_candidates(context: CoveredFragmentContext, e: Event, visible: str, pos: tuple):
    """Collect same-style rows and strictly nested animated cross-style highlights."""
    candidates = _timed_covered_rows(context,e.style,e)
    if e.source_index in (context.animated or set()):
        # Highlight copies may use a different style. Require matching
        # font geometry, exact fragment position/text and nested lifetime.
        for style in context.rows:
            if style == e.style:
                continue
            for base in _timed_covered_rows(context,style,e):
                if (e.name == base.name and e.duration <= .5*base.duration
                        and e.start_s >= base.start_s and e.end_s <= base.end_s
                        and all(e.state.get(tag) == base.state.get(tag)
                                for tag in ("fn","fs","an","b","i","frz"))
                        and abs(pos[1]-get_pos(base.text)[1]) <= e.unit
                        and any(text == visible and abs(pos[0]-x) <= e.unit
                                for text,x in context.anchors[base.source_index])):
                    candidates.append(base)
    return candidates



def _covered_fragment_copy_matches(context: CoveredFragmentContext, e: Event, visible: str, pos: tuple,
    base: Event, layout: tuple, shadow_only: bool):
    """Prove held, shadow or animated foreground copies from original row evidence."""
    if _covered_held_glyph_copy(context,e,visible,pos,base):
        return True
    # A substring and nearby anchor do not identify an effect copy.
    # Compare the source fragment layout: assembly may change the
    # row's alignment and scales, but not its font or caption identity.
    if (e.name != base.name or layout != context.layouts[base.source_index] or
            placement_key(e)[0] != placement_key(base)[0]):
        return False
    # Unassembled rows prove only shadow copies. Their font/layout
    # identity is checked above along with assembled rows.
    if base.source_index in context.virtual and not shadow_only:
        return False
    if not shadow_only:
        # Visible syllables need the same nested animated foreground
        # evidence as early source-row removal. Static labels remain
        # independent even when their text and position happen to fit.
        source_layer = max(int(piece.layer) if piece.layer.lstrip("-").isdigit() else 0
                           for piece,_,_ in context.models[base.source_index].pieces)
        if (e.source_index not in context.animated or
                e.duration >= base.duration-.011 or
                e.start_s < base.start_s or e.end_s > base.end_s or
                abs(pos[1]-get_pos(base.text)[1]) > .06*min(text_height(e),text_height(base)) or
                not e.layer.lstrip("-").isdigit() or int(e.layer) <= source_layer):
            return False
    if (e.duration > .8*base.duration and e.layer == base.layer or
            e.start_s < base.start_s-.15 or e.end_s > base.end_s+.15 or
            abs(pos[1]-get_pos(base.text)[1]) > .15*text_height(base)):
        return False
    glyphs = context.anchors[base.source_index]
    matches = []
    for index,last in _covered_fragment_spans(context,base,visible,shadow_only):
        if (abs(pos[0]-(glyphs[index][1]+glyphs[last][1])/2)
                <= ((.6 if len(visible)>2 else .24)*text_height(base)
                    if shadow_only else .12*min(text_height(e),text_height(base)))):
            matches.append((index,last))
    return len(matches) == 1



def _remove_covered_fragment_copies(events: list[Event], context: CoveredFragmentContext, removed: set[int]):
    """Test remaining fragments in event and candidate order, committing proved copies."""
    for e in events:
        pos = get_pos(e.text)
        visible = context.visible.get(e.source_index,"")
        if (e.kind != "Dialogue" or e.source_index in removed or e.source_index in context.anchors or pos is None or
                not visible or e.state.get("p",0) or
                inline_layout_key(e) or "clip" in e.state or "iclip" in e.state):
            continue
        layout = tuple((key,str(value).casefold() if key == "fn" else value)
                       for key,value in text_layout_key(e)
                       if key not in {"fscx","fscy"})
        shadow_only = (e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254 and
                       e.state.get("4a",0) < 254 and
                       any(abs(e.state.get(k,e.state.get("shad",0))) > 0
                           for k in ("xshad","yshad")))
        candidates = _covered_fragment_candidates(context,e,visible,pos)
        for base in candidates:
            if _covered_fragment_copy_matches(context,e,visible,pos,base,layout,shadow_only):
                removed.add(e.source_index)
                break



def remove_covered_fragment_effects(
    events: list[Event], visible_map: dict[int, str], row_evidence: list[TextRow],
    animated_sources: set[int] | None=None, source_events: dict[int, Event] | None=None,
    font_metrics: FontMetrics | None=None,
) -> CoveredFragmentRemoval:
    """Remove copies proven to repeat reconstructed, authored or virtual rows.

    Consume shared fragment anchors without guessing spacing or rediscovering
    rows. Visible overlays require nested animation evidence. Static glyphs
    can repeat an animated row's recorded glyphs with identical placement and
    source styling, provided the emitted paint is unchanged or matches its
    simplified caption form; virtual rows authorize only matching shadow copies. Original
    trajectories and exact font measurements prove entrance and exit groups.
    Input events, visibility and rows are borrowed. Return timing evidence in
    independent row successors, including proofs when no copies are removed.
    """
    animated_sources = animated_sources or set()
    context = _prepare_covered_fragments(visible_map,row_evidence,animated_sources,
        source_events,font_metrics)
    removed = (match_departing_glyph_effects(events,row_evidence,source_events,font_metrics)
               if source_events is not None else set())
    if source_events is not None:
        removed.update(match_boundary_glyph_effects(events,visible_map,source_events,font_metrics))
        removed.update(match_staggered_row_effects(events,row_evidence,source_events,animated_sources,font_metrics))
    _prepare_covered_shadow_rows(context)
    cores = _select_covered_shadow_timing(events,context)
    _remove_covered_shadow_fragments(events,context,removed)
    _remove_covered_fragment_copies(events,context,removed)
    rows = [dataclass_replace(row,
        pieces=list(row.pieces),
        paint_rows=[list(paint_row) for paint_row in row.paint_rows],
        source_anchors={word:list(anchors) for word,anchors in row.source_anchors.items()},
        foreground=list(row.foreground),
        phase_core=cores.get(id(row),row.phase_core)) for row in row_evidence]
    return CoveredFragmentRemoval(
        [e for e in events if e.source_index not in removed],rows,len(removed))

