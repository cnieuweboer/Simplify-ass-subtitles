"""Complete source movement-chain proof and held-caption reconstruction.

Inputs and metrics remain borrowed; indexes, chain evidence and edits are local.
The text-effect sequence caller retains pipeline order and reporting.
"""
from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import math
import re
import unicodedata

from .ass_overrides import apply_override, evaluate_effective_state, effective_state, OVERRIDE_RE
from .event_model import Event
from .event_operations import event_override_tokens, literal_font_spans, replace_event
from .effect_validation import opaque_text_effect_state, parse_effect_move, parse_effect_transform
from .caption_geometry import get_pos, inline_layout_key, placement_key, text_layout_key
from .caption_rendering import _source_caption_paint, render_simplified_caption, render_tag
from .font_metrics import FontMetrics
from .glyph_placement import fit_fragment_anchor
from .static_selection import upright_text_state
from .subtitle_document import format_time
from .text_freezing import simplify_text


def _moving_glyph_source_families(source_events: dict[int,Event]) -> set[tuple]:
    """Reject impossible families before resolving every source override."""
    # This proof needs at least one moving fragment without transforms or
    # fades. Reject impossible families before resolving every source tag.
    families = set()
    for original in source_events.values():
        if (original.kind != 'Dialogue' or original.duration <= 0 or
                not re.search(r'\\move(?=[^A-Za-z]|$)',original.text,re.I) or
                not OVERRIDE_RE.sub('',original.text) or
                get_pos(original.text) is not None or
                inline_layout_key(original) and literal_font_spans(original) is None):
            continue
        tokens = event_override_tokens(original)
        if (sum(tag == 'move' for tag,value in tokens) == 1 and
                not any(tag in {'t','fad','fade'} for tag,value in tokens)):
            families.add((original.style,original.name))
    return families


def _moving_glyph_geometry(e: Event) -> tuple:
    """Identify authored placement/layout and supported literal font spans."""
    spans = literal_font_spans(e) if inline_layout_key(e) else ()
    if spans is not None and len(spans) <= 1:
        spans = ()
    return (e.style,e.name,placement_key(e)[:-1],text_layout_key(e),spans)


def _moving_glyph_paint(state: dict) -> tuple:
    """Identify foreground/outline paint used to match authored holds and fades."""
    return (state.get('1c'),state.get('3c'),state.get('3a',0),
            state.get('xbord',state.get('bord',0)),
            state.get('ybord',state.get('bord',0)))


def _index_moving_glyph_sources(source_events: dict[int,Event], families: set[tuple]) -> tuple[dict,dict,dict]:
    """Index eligible original stationary, moving and completely fading text phases."""
    static, moves, fades = {}, {}, {}
    for original in source_events.values():
        if ((original.style,original.name) not in families or
                original.kind != 'Dialogue' or original.duration <= 0 or
                inline_layout_key(original) and literal_font_spans(original) is None):
            continue
        word = simplify_text(original.text,visible_only=True)[1]
        if (not word or OVERRIDE_RE.sub('',original.text) != word or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word)):
            continue
        evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
        state = evaluated.formatting
        if not upright_text_state(state) or not opaque_text_effect_state(state):
            continue
        p = dataclass_replace(original,state=state,continuation=evaluated.continuation)
        parts = event_override_tokens(p)
        movement = [value for tag,value in parts if tag == 'move']
        transforms = [value for tag,value in parts if tag == 't']
        pos = get_pos(p.text)
        key = _moving_glyph_geometry(p)
        if not movement and not transforms and pos is not None:
            static.setdefault((key,word),[]).append(p)
        elif len(movement) == 1 and not transforms and pos is None:
            if any(tag in {'fad','fade'} for tag,value in parts):
                continue
            # Generated phase times can exceed centisecond event boundaries
            # by a frame; the matching held phase proves the intended landing.
            values = parse_effect_move(movement[0],p.duration,endpoint_slack=50)
            if values is None:
                continue
            moves.setdefault((key,p.start,p.end,values[3],_moving_glyph_paint(state)),[]).append((p,values,word))
        elif not movement and len(transforms) == 1 and pos is not None:
            transform = parse_effect_transform(transforms[0],p.duration,
                                               {'alpha','1a','3a','blur','be'})
            if transform is None or any(tag in {'fad','fade'} for tag,value in parts):
                continue
            begin,end,changes = transform
            final = state.copy()
            final_continuation = p.continuation
            for tag,value in changes:
                final_continuation = apply_override(final,tag,value,p.styles,p.defaults,final_continuation)
            if (final.get('1a',0) >= 254 and
                    (final.get('3a',0) >= 254 or
                     max(state.get('xbord',state.get('bord',0)),
                         state.get('ybord',state.get('bord',0))) <= .001)):
                fades.setdefault((key,p.start,word,pos),[]).append(p)
    return static,moves,fades


def _index_retained_moving_glyphs(events: list[Event], visible_map: dict[int,str]) -> dict[tuple,list[Event]]:
    """Index retained readable captions separately from their authored source phases."""
    current = {}
    for e in events:
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (pos is not None and word and
                (not inline_layout_key(e) or literal_font_spans(e) is not None) and
                upright_text_state(e.state)):
            # A long fade can outweigh its opaque hold during earlier phase
            # selection. The source hold still proves this exact text/pose;
            # restore its opaque paint only after the complete run is proven.
            current.setdefault((_moving_glyph_geometry(e),word,pos),[]).append(e)
    return current


def _retained_moving_glyph(context: MovingGlyphContext, p: Event) -> Event | None:
    """Match one retained caption covering a source hold, preferring opaque paint."""
    matches = [e for e in context.current.get((_moving_glyph_geometry(p),simplify_text(p.text,visible_only=True)[1],
                                       get_pos(p.text)),[])
               if e.start_s <= p.start_s+.001 and e.end_s >= p.end_s-.001]
    opaque = [e for e in matches if e.state.get('1a',0) == 0]
    if opaque:
        matches = opaque
    return matches[0] if len(matches) == 1 else None


def _group_moving_glyph_sequences(moves: dict[tuple,list[tuple]]) -> tuple[list[tuple],dict[tuple,list[tuple]]]:
    """Group unique authored destinations and index touching movement phases."""
    groups = []
    by_start = {}
    for (key,start,end,y,colors),peers in moves.items():
        peers.sort(key=lambda item:item[1][2])
        if (len({value[2] for p,value,word in peers}) != len(peers) or
                not any(math.dist(value[:2],value[2:4]) > p.unit for p,value,word in peers)):
            continue
        word = ''.join(char for p,value,char in peers)
        group = (key,start,end,y,colors,word,peers)
        groups.append(group)
        by_start.setdefault((key,start,word),[]).append(group)
    return groups,by_start


def _moving_glyph_group_fits(context: MovingGlyphContext, group: tuple, parent: Event) -> bool:
    """Prove an authored landing directly for whole fragments or by exact-font advances for glyph rows."""
    key,start,end,y,colors,word,peers = group
    pos = get_pos(parent.text)
    if len(peers) == 1:
        # A whole fragment repeats the authored stationary text exactly;
        # its recorded destination proves placement without font fitting.
        return math.dist(tuple(peers[0][1][2:4]),pos) <= .001
    if context.metric is None or not context.metric.available or abs(pos[1]-y) > parent.unit:
        return False
    anchor = fit_fragment_anchor(context.metric, parent.state,[value[2] for p,value,char in peers],
                                    [char for p,value,char in peers],word,parent.unit,
                                    allow_tracking=True,separate_glyphs=True)
    return anchor is not None and abs(anchor-pos[0]) <= 1.5*parent.unit


def _matching_moving_glyph_fades(context: MovingGlyphContext, group: tuple) -> list[Event] | None:
    """Require one matching fade at every authored glyph destination and one common finish."""
    key,start,end,y,colors,word,peers = group
    matches = [[p for p in context.fades.get((key,end,char,tuple(value[2:4])),[])
                if _moving_glyph_paint(p.state) == colors]
               for p,value,char in peers]
    if any(len(items) != 1 for items in matches):
        return None
    result = [items[0] for items in matches]
    return result if len({p.end for p in result}) == 1 else None


def _prove_moving_glyph_chain(context: MovingGlyphContext, seed: tuple) -> MovingGlyphChain | None:
    """Require one touching source hold and an unambiguous chain ending in a hold or complete fade."""
    key,start,end,y,colors,word,peers = seed
    parents = [p for p in context.static.get((key,word),[]) if p.end == start and
               _retained_moving_glyph(context,p) is not None and _moving_glyph_group_fits(context,seed,p)]
    if len(parents) != 1:
        return None
    parent = parents[0]
    before = _retained_moving_glyph(context,parent)
    chain = [seed]
    after = None
    after_source = None
    departing = None
    while True:
        last = chain[-1]
        holds = [p for p in context.static.get((key,word),[]) if p.start == last[2] and
                 get_pos(p.text) == get_pos(parent.text) and _moving_glyph_paint(p.state) == colors and
                 _retained_moving_glyph(context,p) is not None]
        if len(holds) == 1:
            after_source = holds[0]
            after = _retained_moving_glyph(context,after_source); break
        if holds:
            break
        departing = _matching_moving_glyph_fades(context,last)
        if departing is not None:
            break
        following = [g for g in context.by_start.get((key,last[2],word),[]) if
                     g[4] == colors and _moving_glyph_group_fits(context,g,parent)]
        if len(following) != 1 or following[0] in chain:
            break
        chain.append(following[0])
    if after is None and departing is None:
        return None
    return MovingGlyphChain(parent,before,chain,after,after_source)


def _match_moving_glyph_prefix(context: MovingGlyphContext, proof: MovingGlyphChain) -> Event | None:
    """Match only an exact touching authored word entrance to the proven retained hold."""
    key,start,end,y,colors,word,peers = proof.groups[0]
    # Authored fades at the start may survive separately when the
    # previous row overlaps. Only an exact, touching word phase belongs.
    prefixes = [p for p in context.static.get((key,word),[]) if p.end == proof.before.start and
                get_pos(p.text) == get_pos(proof.parent.text) and _moving_glyph_paint(p.state) == _moving_glyph_paint(proof.parent.state) and
                _retained_moving_glyph(context,p) is not None and
                any(tag == 'fad' for tag,value in event_override_tokens(p))]
    prefix_caption = _retained_moving_glyph(context,prefixes[0]) if len(prefixes) == 1 else None
    return prefix_caption


def _collect_moving_glyph_overlays(context: MovingGlyphContext, proof: MovingGlyphChain, source_ids: set[int]) -> None:
    """Include unique borderless word flashes only at recorded chain/hold boundaries."""
    key,start,end,y,colors,word,peers = proof.groups[0]
    boundaries = {group[2] for group in proof.groups}
    if proof.after_source is not None:
        boundaries.add(proof.after_source.end)
    # Word flashes and complete letter fades share the recorded word
    # boundaries. Their different paint is decorative, not a new caption.
    for boundary in boundaries:
        overlays = [p for p in context.fades.get((key,boundary,word,get_pos(proof.parent.text)),[])
                    if max(p.state.get('xbord',p.state.get('bord',0)),
                           p.state.get('ybord',p.state.get('bord',0))) <= .001]
        if len(overlays) == 1:
            source_ids.add(overlays[0].source_index)


def _match_moving_glyph_exit(context: MovingGlyphContext, proof: MovingGlyphChain, source_ids: set[int]) -> tuple[tuple,float] | None:
    """Match complete recorded exit fades and restore an absorbed source-word boundary safely."""
    key,start,end,y,colors,word,peers = proof.groups[0]
    final_group = proof.groups[-1]
    exit_group = (key,final_group[1],proof.after_source.end if proof.after_source is not None else final_group[2],
                  y,colors,word,final_group[6])
    exiting = _matching_moving_glyph_fades(context,exit_group)
    if exiting is not None:
        source_ids.update(p.source_index for p in exiting)
    finish = proof.after.end_s if proof.after is not None else final_group[6][0][0].end_s
    if exiting is not None and proof.after_source is not None:
        # Earlier phase reduction can absorb a one-letter fade into its
        # word. Restore the proven word boundary, preserving later cues.
        if proof.after.end_s > max(p.end_s for p in exiting)+.001:
            return None
        finish = proof.after_source.end_s
    return final_group,finish


def _render_moving_glyph_caption(proof: MovingGlyphChain, final_group: tuple, finish: float, prefix_caption: Event | None) -> Event:
    """Build the retained held caption with proven paint, source timing and authored font switches."""
    chosen = proof.after if proof.after is not None else proof.before
    state = final_group[6][0][0].state
    clear_axes = any(k in chosen.state and k not in state for k in ('xbord','ybord'))
    tags = ''.join(render_tag(k,state[k]) for k in ('1c','1a','3c','3a','bord','xbord','ybord')
                   if k in state and (state[k] != chosen.state.get(k) or
                                      k == 'bord' and clear_axes))
    prefix = re.match(r'(?:\{[^}]*\})*',chosen.text).end()
    text = (chosen.text[:prefix-1]+tags+chosen.text[prefix-1:] if prefix else
            ('{'+tags+'}' if tags else '')+chosen.text)
    if inline_layout_key(chosen):
        # Match the readable contour used by reconstructed neighbors while
        # retaining the authored font switches inside the whole fragment.
        spans = literal_font_spans(chosen)
        state = {**effective_state(text,chosen.defaults,chosen.styles),'fn':spans[0][1]}
        text = render_simplified_caption(state,chosen.text[prefix:],measurement=chosen.measurement,
                                         source_paint=_source_caption_paint(state,[state]))
    beginning = prefix_caption if prefix_caption is not None else proof.before
    caption = replace_event(chosen,start=beginning.start,start_s=beginning.start_s,
                            end=format_time(finish),end_s=finish,text=text,
                            source_index=proof.before.source_index)
    return caption


def _propose_moving_glyph_sequence(context: MovingGlyphContext, seed: tuple) -> tuple[set[int],Event] | None:
    """Combine a complete chain with its exact entrance/exit evidence before proposing replacement."""
    proof = _prove_moving_glyph_chain(context,seed)
    if proof is None:
        return None
    source_ids = {p.source_index for group in proof.groups for p,value,char in group[6]}
    source_ids.add(proof.before.source_index)
    prefix_caption = _match_moving_glyph_prefix(context,proof)
    if prefix_caption is not None:
        source_ids.add(prefix_caption.source_index)
    if proof.after is not None:
        source_ids.add(proof.after.source_index)
    _collect_moving_glyph_overlays(context,proof,source_ids)
    exit_match = _match_moving_glyph_exit(context,proof,source_ids)
    if exit_match is None:
        return None
    final_group,finish = exit_match
    caption = _render_moving_glyph_caption(proof,final_group,finish,prefix_caption)
    return source_ids,caption


def _apply_moving_glyph_proposals(events: list[Event], proposals: list[tuple[set[int],Event]]) -> tuple[list[Event],int]:
    """Reject every competing ownership claim before replacing consumed phases in source-index order."""
    ownership = {}
    for ids,caption in proposals:
        for index in ids:
            ownership[index] = ownership.get(index,0)+1
    accepted = [(ids,caption) for ids,caption in proposals
                if all(ownership[index] == 1 for index in ids)]
    if not accepted:
        return events,0
    consumed = set().union(*(ids for ids,caption in accepted))
    output = [e for e in events if e.source_index not in consumed]
    output.extend(caption for ids,caption in accepted)
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output)


def collapse_moving_glyph_sequences(
    events: list[Event], visible_map: dict[int, str], source_events: dict[int, Event],
    metric: FontMetrics | None,
) -> tuple[list[Event], int]:
    """Replace proven stationary/moving/stationary text with one held caption.

    A whole fragment must repeat at its exact authored destination. Isolated
    glyph runs instead need exact font advances and an authored word anchor.
    The run must end in the same completed text or a complete recorded fade.
    Consecutive moves with the same destination can share that proof.
    Only fades at those recorded phase boundaries belong to the run; partial,
    overlapping or ambiguous groups never authorize removal.
    """
    families = _moving_glyph_source_families(source_events)
    if not families:
        return events,0
    static,moves,fades = _index_moving_glyph_sources(source_events,families)
    current = _index_retained_moving_glyphs(events,visible_map)
    groups,by_start = _group_moving_glyph_sequences(moves)
    context = MovingGlyphContext(static,fades,current,by_start,metric)
    proposals = []
    for seed in sorted(groups,key=lambda group:(group[6][0][0].start_s,group[6][0][0].source_index)):
        proposal = _propose_moving_glyph_sequence(context,seed)
        if proposal is not None:
            proposals.append(proposal)
    return _apply_moving_glyph_proposals(events,proposals)


@dataclass(frozen=True)
class MovingGlyphContext:
    """Original phase indexes, retained captions and exact-font measurement for one movement pass."""
    static: dict[tuple,list[Event]]
    fades: dict[tuple,list[Event]]
    current: dict[tuple,list[Event]]
    by_start: dict[tuple,list[tuple]]
    metric: FontMetrics | None


@dataclass(frozen=True)
class MovingGlyphChain:
    """An authored parent/retained hold, complete movement chain and optional terminal hold."""
    parent: Event
    before: Event
    groups: list[tuple]
    after: Event | None
    after_source: Event | None
