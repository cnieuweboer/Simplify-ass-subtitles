"""Original-source row proofs, effect removal and paint-family handoffs."""
from __future__ import annotations

import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace as dataclass_replace, field

from .ass_overrides import (
    OverrideContinuation, tokenize_override, apply_override,
    evaluate_effective_state, effective_state, OVERRIDE_RE, DEFAULT_STATE,
)
from .row_evidence import TextRow, _index_source_fragment_visibility
from .fragment_spans import index_fragment_spans, matching_fragment_spans
from .font_metrics import FontMetrics
from .font_reporting import FontProcessingReport
from .row_fitting import recover_font_row
from .glyph_placement import fit_fragment_anchor
from .event_model import Event
from .effect_validation import parse_effect_transform
from .event_operations import event_override_tokens, event_evaluation
from .caption_geometry import (
    NUM, inline_layout_key, text_height, placement_key, text_layout_key,
)
from .static_selection import unrotated_text_state
from .backed_glyph_pulses import collapse_backed_glyph_pulses
from .sliced_text import collapse_sliced_text_sequences
from .static_objects import static_text_paint_geometry


@dataclass(frozen=True)
class SourceFragmentRowContext:
    """Original row geometry, contiguous fragment index and private per-row matching cache."""
    row: TextRow
    first: Event
    chosen: list[Event]
    height: float
    anchors: dict
    span_index: tuple
    gaps: list[int]
    syllables: dict
    top_layer: int
    layout_tags: set[str]


@dataclass(frozen=True)
class SourceFragmentCandidate:
    """One admitted source with its position, initial anchors, resolved state and delayed flag."""
    event: Event
    pos: tuple
    nearby: list
    state: dict
    delayed: bool


@dataclass(frozen=True)
class SourceFragmentEvidence:
    """Existing paint candidates and distinct animated word/anchor evidence for one row."""
    candidates: list[Event]
    evidence: set


@dataclass(frozen=True)
class SourceFragmentRemoval:
    """Working events, independently writable rows and the effect-removal count.

    Row geometry, timing, visibility and source provenance remain historical
    evidence even when their paint sources are removed from the working list.
    The caller adopts rows before reconstruction; supplied rows are borrowed.
    """
    events: list[Event]
    rows: list[TextRow]
    removed_effects: int
    paint_families: list[TextRow] = field(default_factory=list)


def match_translucent_glyph_particles(events: list[Event], row_evidence: list[TextRow],
                                      words: dict[int,str],
                                      animated_sources: set[int]) -> set[int]:
    """Prove dense, complete particle phases behind an opaque source row.

    Match original movement endpoints to authored glyph anchors, without font
    substitution or sampled geometry. Each repeated phase must cover every
    glyph exactly once; incomplete or multiply owned families remain intact.
    This matcher returns membership only and never changes foreground rows.
    """
    if not events or not row_evidence:
        return set()
    buckets = {}
    identity = lambda e: (e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
    geometry = {key for key,_ in text_layout_key(row_evidence[0].base)}
    varying = {"fscx","fscy","frz","frx","fry"}
    paint = {"alpha","1a","2a","3a","4a","c","1c","2c","3c","4c","blur","be"}
    for e in events:
        word = words.get(e.source_index,"")
        if (e.kind != "Dialogue" or e.source_index not in animated_sources or
                len(word) != 1 or word.isspace() or e.duration <= 0 or
                not e.layer.lstrip('-').isdigit() or inline_layout_key(e)):
            continue
        tags = [item for block in OVERRIDE_RE.findall(e.text)
                for item in tokenize_override(block)]
        moves = [value for tag,value in tags if tag == "move"]
        if (len(moves) != 1 or any(tag not in geometry|paint|{"move","fad","t"}
                                   for tag,value in tags)):
            continue
        try:
            move = tuple(float(v.strip()) for v in moves[0][1:-1].split(','))
        except ValueError:
            continue
        if (len(move) not in (4,6) or not all(math.isfinite(v) for v in move) or
                len(move) == 6 and not 0 <= move[4] <= move[5] <= 1000*e.duration):
            continue
        evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
        state = evaluated.formatting
        final = state.copy()
        final_continuation = evaluated.continuation
        states = [state]
        safe = True
        for tag,value in tags:
            if tag != "t":
                continue
            for name,argument in tokenize_override(value[1:-1]):
                if name not in varying|paint:
                    safe = False
                    break
                final_continuation = apply_override(final,name,argument,e.styles,e.defaults,final_continuation)
                states.append(final.copy())
        if (not safe or state.get("blur",0) <= 0 or
                any(min(s.get(k,0) for k in ("1a","3a","4a")) < 128 for s in states)):
            continue
        buckets.setdefault(identity(e),[]).append((e,word,move,state,states))
    for key,group in buckets.items():
        group.sort(key=lambda item:item[0].start_s)
        buckets[key] = ([item[0].start_s for item in group],group)

    families = []
    for row in row_evidence:
        if row.virtual or len(row.pieces) < 4:
            continue
        first = row.base
        foreground = [piece for piece,word,pos in row.pieces]
        if (first.duration <= 0 or any(len(word) != 1 or word.isspace() or
                piece.start != first.start or piece.end != first.end or
                piece.state.get("1a",0) != 0 or
                not piece.layer.lstrip('-').isdigit() or
                piece.source_index in animated_sources for piece,word,pos in row.pieces)):
            continue
        index = buckets.get(identity(first))
        if index is None:
            continue
        starts,group = index
        height = min(text_height(piece) for piece in foreground)
        radius = .25*height
        foreground_layer = min(int(piece.layer) for piece in foreground)
        phases = {}
        for e,word,move,state,states in group[
                bisect_left(starts,first.start_s-.25*first.duration):
                bisect_right(starts,first.end_s+.25*first.duration)]:
            if (e.duration > .25*first.duration or
                    e.end_s > first.end_s+.25*first.duration or
                    int(e.layer) >= foreground_layer):
                continue
            matches = []
            for glyph,(piece,text,pos) in enumerate(row.pieces):
                if (word != text or math.dist(move[:2],pos) > radius or
                        math.dist(move[2:4],pos) > radius or
                        any((str(state.get(k,"")).casefold() != str(piece.state.get(k,"")).casefold()
                             if k == "fn" else state.get(k) != piece.state.get(k))
                            for k in geometry) or
                        any(not .5*piece.state.get(k,100) <= s.get(k,100) <=
                                2*piece.state.get(k,100)
                            for s in states for k in ("fscx","fscy"))):
                    continue
                matches.append(glyph)
            if len(matches) == 1:
                phases.setdefault((e.layer,e.start,e.end),[]).append((matches[0],e))
        if (len(phases) < 3 or any(len(phase) != len(row.pieces) or
                len({glyph for glyph,e in phase}) != len(row.pieces) for phase in phases.values())):
            continue
        peers = [e for phase in phases.values() for glyph,e in phase]
        if max(e.end_s for e in peers)-min(e.start_s for e in peers) < .5*first.duration:
            continue
        families.append({e.source_index for e in peers})
    owners = {}
    for family in families:
        for index in family:
            owners[index] = owners.get(index,0)+1
    return set().union(*(family for family in families if all(owners[index] == 1 for index in family)))


def match_repeated_glyph_flashes(
    events: list[Event], words: dict[int, str], positions: dict[int, tuple[float, float] | None],
    metric: FontMetrics | None, *, font_report: FontProcessingReport | None=None,
) -> set[int]:
    """Prove complete repeated colour flashes over a held text row.

    Use the retained fragment geometry and exact font, including the existing
    font-size calibration for separately authored glyphs. A whole family must
    repeat every glyph, vary its paint, and stay within the foreground cue.
    Fixed same-layer flashes also qualify after their fades have been stripped.
    Return membership only; the held text, paint and timing remain untouched.
    """
    if metric is None or not metric.available:
        return set()
    paint = {'c','1c','2c','3c','4c','bord','xbord','ybord','blur','be'}
    parents, flashes = {}, {}
    for e in events:
        text,pos = words.get(e.source_index,''),positions.get(e.source_index)
        if (e.kind != 'Dialogue' or not text or pos is None or e.duration <= 0 or
                e.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'} or
                not e.layer.lstrip('-').isdigit() or
                any(not math.isfinite(v) for v in (*pos,e.start_s,e.end_s))):
            continue
        evaluated = event_evaluation(e)
        state = evaluated.formatting
        sample = dataclass_replace(e,state=state,continuation=evaluated.continuation)
        inline = inline_layout_key(sample)
        profile = static_text_paint_geometry(sample,paint) if inline else None
        if (state.get('p',0) or state.get('borderstyle',1) != 1 or
                inline and (profile is None or len(profile[0]) != 1) or
                not unrotated_text_state(state) or
                any(k in state for k in ('clip','iclip','org')) or
                any(abs(state.get(k,0)) > .001 for k in ('fax','fay'))):
            continue
        tokens = event_override_tokens(e)
        if any(tag in {'move','fade','k','kf','ko','kt'} for tag,value in tokens):
            continue
        transforms = [value for tag,value in tokens if tag == 't']
        if any(parse_effect_transform(value,e.duration,paint,allow_after_end=True) is None
               for value in transforms):
            continue
        layout = tuple((k,str(v).casefold() if k == 'fn' else v)
                       for k,v in text_layout_key(sample) if k != 'q')
        key = (e.style,e.name,placement_key(sample)[0],layout)
        border = max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord'))
        if (len(text) == 1 and not text.isspace() and border == 0 and
                not transforms and not unicodedata.combining(text) and
                unicodedata.bidirectional(text) not in {'R','AL','AN'}):
            flashes.setdefault(key,{}).setdefault(e.layer,[]).append(sample)
        elif border > 0 and state.get('1a',0) == 0:
            parents.setdefault((key,e.layer,e.start,e.end,pos[1]),[]).append(sample)
    indexes = {}
    for key,layers in flashes.items():
        indexes[key] = []
        for peers in layers.values():
            peers.sort(key=lambda e:e.start_s)
            indexes[key].append(([e.start_s for e in peers],peers))
    proposals = []
    for (key,layer,start,end,y),row in parents.items():
        if key not in indexes or sum(len(''.join(words[e.source_index].split())) for e in row) < 3:
            continue
        row.sort(key=lambda e:positions[e.source_index][0])
        if len({positions[e.source_index][0] for e in row}) != len(row):
            continue
        first = row[0]
        for starts,peers in indexes[key]:
            candidates = [e for e in peers[bisect_left(starts,first.start_s-1e-6):
                                           bisect_right(starts,first.end_s)]
                          if e.end_s <= first.end_s+1e-6 and e.duration <= .25*first.duration and
                             abs(positions[e.source_index][1]-y) <= first.unit]
            slots = {}
            for e in candidates:
                slots.setdefault((positions[e.source_index][0],words[e.source_index]),[]).append(e)
            if not slots or any(len(group) < 3 or
                    len({e.state.get('1c') for e in group}) < 3 or
                    max(e.end_s for e in group)-min(e.start_s for e in group) < .5*first.duration
                    for group in slots.values()):
                continue
            ordered = sorted(slots)
            ownership = [0]*len(ordered)
            complete = True
            for parent in row:
                text = words[parent.source_index]
                target = ''.join(text.split())
                px,py = positions[parent.source_index]
                options = []
                for i in range(len(ordered)-len(target)+1):
                    span = ordered[i:i+len(target)]
                    if ''.join(c for x,c in span) != target:
                        continue
                    xs = [x for x,c in span]
                    if any(b-a <= first.unit for a,b in zip(xs,xs[1:])):
                        continue
                    if not any(c.isspace() for c in text):
                        anchor = fit_fragment_anchor(metric, parent.state,xs,list(target),text,
                                                        parent.unit,allow_tracking=True,separate_glyphs=True,
                                                        max_size_error=.1)
                        fits = anchor is not None and abs(anchor-px) <= 1.5*parent.unit
                    else:
                        glyphs = [slots[slot][0] for slot in span]
                        fit = recover_font_row(metric, glyphs,list(target),max_size_error=.1, font_report=font_report)
                        fits = (fit is not None and ' '.join(fit[0].split()) == ' '.join(text.split()) and
                                (int(parent.state.get('an',5))-1)%3 == 1 and
                                abs(fit[1]-px) <= max(1.5*parent.unit,.1*text_height(parent)))
                    if fits:
                        options.append(i)
                if len(options) != 1:
                    complete = False; break
                for i in range(options[0],options[0]+len(target)):
                    ownership[i] += 1
            if complete and all(n == 1 for n in ownership):
                proposals.append({e.source_index for group in slots.values() for e in group})
    owners = {}
    for members in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    return {index for members in proposals if all(owners[i] == 1 for i in members)
            for index in members}


def _index_source_fragment_events(events: list[Event], words: dict[int,str], positions: dict) -> dict:
    """Index the last source for each identity when it has an authored word and position."""
    parsed = {e.source_index:e for e in events}
    indexed: dict[tuple,list[Event]] = {}
    for e in parsed.values():
        if positions.get(e.source_index) is not None and words.get(e.source_index):
            indexed.setdefault((e.style,e.name,e.margin_l,e.margin_r,e.margin_v),[]).append(e)
    return indexed


def _prove_source_fragment_visibility(row: TextRow, removed: set[int]) -> bool | None:
    """Require layered full-row visibility and remove alternate phases only after complete coverage."""
    # Short rows may prove complete particle phases, but retain the older
    # minimum for the broader layered-effect and foreground-paint rules.
    if (sum(len(''.join(word.split())) for _,word,_ in row.pieces) < 8 or
            len({paint_row[0].layer for paint_row in row.paint_rows}) < 2):
        return None
    first = row.base
    phases = _index_source_fragment_visibility(row)
    alternating = any(profile != ((first.start_s,first.end_s),) for profile in phases)
    if alternating:
        # Different segmentations can replace each other during a cue.
        # Require complete, nonoverlapping visibility and layered text
        # in every phase; a partial row cannot prove full-cue coverage.
        if (len(phases) < 2 or any(len({paint_row[0].layer for paint_row in peers}) < 2
                                  for peers in phases.values())):
            return None
        spans = sorted(span for profile in phases for span in profile)
        cursor = first.start_s
        complete = True
        for start,end in spans:
            if abs(start-cursor) > .001:
                complete = False
                break
            cursor = end
        if not complete or abs(cursor-first.end_s) > .001:
            return None
        selected = first.evidence.opaque_spans
        assert selected is not None, "Alternating source rows require visibility evidence"
        removed.update(e.source_index for profile,peers in phases.items()
                       if profile != selected for paint_row in peers for e in paint_row)
    return alternating


def _prepare_source_fragment_row(row: TextRow) -> SourceFragmentRowContext:
    """Retain authored glyph anchors, contiguous fragment indexing and per-row syllable cache."""
    first = row.base
    chosen = [e for e, _, _ in row.pieces]
    height = text_height(first)
    anchors = row.source_anchors
    # A highlight may spell several separately positioned glyphs.
    # Retain their original anchors before paint-based reconstruction
    # divides a gradient into differently coloured caption fragments.
    span_index = index_fragment_spans(word for _,word,_ in row.pieces)
    gaps = [0]
    for left,right in zip(row.pieces,row.pieces[1:]):
        gaps.append(gaps[-1]+(right[2][0]-left[2][0] > 2*height))
    syllables = {}
    top_layer = max(int(paint_row[0].layer) if paint_row[0].layer.lstrip('-').isdigit()
                    else 0 for paint_row in row.paint_rows)
    layout_tags = ({tag for tag,_ in text_layout_key(first)} - {'fscx','fscy'} |
                   {'a','r','fr','pos','move','clip','iclip','p'})
    return SourceFragmentRowContext(row,first,chosen,height,anchors,span_index,gaps,syllables,top_layer,layout_tags)


def _profile_source_fragment_candidate(e: Event, context: SourceFragmentRowContext, words: dict[int,str], positions: dict, animated_sources: set[int]) -> SourceFragmentCandidate | None:
    """Admit candidate lifetimes and resolve source state before the independent matching proofs."""
    delayed = context.first.end_s <= e.start_s <= context.first.end_s+.25*context.first.duration
    if not (context.first.start_s-.001 <= e.start_s and
            (e.start_s < context.first.end_s or delayed and e.source_index in animated_sources)):
        return None
    pos = positions[e.source_index]
    nearby = [anchor for anchor in context.anchors.get(words[e.source_index],[]) if
              abs(pos[0]-anchor[0]) <= context.height and abs(pos[1]-anchor[1]) <= .25*context.height]
    evaluated = event_evaluation(e)
    state = evaluated.formatting
    e.state = state
    e.continuation = evaluated.continuation
    return SourceFragmentCandidate(e,pos,nearby,state,delayed)


def _source_fragment_syllable_matches(context: SourceFragmentRowContext, target: str, pos: tuple) -> list:
    """Cache matching authored fragment spans, stopping once two nearby occurrences prove ambiguity."""
    query = (target,pos)
    if query not in context.syllables:
        matches = []
        # Search only the actual effect text, not all quadratic
        # combinations of a long row. Consider every occurrence,
        # but two nearby matches already establish ambiguity.
        for start,end in matching_fragment_spans(context.span_index,target):
            if context.gaps[start] != context.gaps[end]:
                continue
            a,b = context.row.pieces[start][2],context.row.pieces[end][2]
            anchor = ((a[0]+b[0])/2,(a[1]+b[1])/2)
            if (abs(pos[0]-anchor[0]) <= .12*context.height and
                    abs(pos[1]-anchor[1]) <= .06*context.height):
                matches.append(anchor)
                if len(matches) == 2:
                    break
        context.syllables[query] = matches
    matches = context.syllables[query]
    return matches


def _match_source_fragment_highlight(candidate: SourceFragmentCandidate, context: SourceFragmentRowContext, words: dict[int,str], animated_sources: set[int], removed: set[int]) -> None:
    """Remove only a uniquely matched nested animated highlight above an existing layered row."""
    e,pos,state = candidate.event,candidate.pos,candidate.state
    # This proof removes only a nested animated copy above an
    # existing layered row. It does not confirm a dense fade family
    # or normalize the underlying row's gradient paint.
    if (e.source_index in animated_sources and e.duration < context.first.duration-.011 and
            e.end_s <= context.first.end_s and e.start_s >= context.first.start_s and
            (int(e.layer) if e.layer.lstrip('-').isdigit() else 0) > context.top_layer and
            state.get('1a',0) < 128 and not state.get('p',0) and
            'clip' not in state and 'iclip' not in state and
            not inline_layout_key(e) and text_layout_key(e) == text_layout_key(context.first) and
            not re.search(r'\\(?:move|org)\s*\(',e.text,re.I)):
        transforms = [value for block in OVERRIDE_RE.findall(e.text)
                      for tag,value in tokenize_override(block) if tag == 't']
        moving = any(tag in context.layout_tags for value in transforms
                     for tag,_ in tokenize_override(value))
        target = ''.join(words[e.source_index].split())
        matches = _source_fragment_syllable_matches(context,target,pos)
        if not moving and len(matches) == 1:
            removed.add(e.source_index)


def _source_fragment_nearby_anchors(candidate: SourceFragmentCandidate, context: SourceFragmentRowContext, words: dict[int,str], animated_sources: set[int]) -> tuple[list,dict]:
    """Keep the existing distant-origin proof for rising transparent shrinking glyph copies."""
    e,pos,nearby,state = candidate.event,candidate.pos,candidate.nearby,candidate.state
    # Some fade copies rise and shrink about a distant origin. The
    # unchanged x anchor, explicit transparency and smaller scale tie
    # them to the same glyph even after they leave the baseline.
    if not nearby and e.source_index in animated_sources:
        origin = re.search(r"\\org\(\s*("+NUM+r")\s*,\s*("+NUM+r")",e.text,re.I)
        if origin:
            state = effective_state(e.text,e.defaults,e.styles)
            if (state.get("1a",0) > 0 and state.get("fscx",100) <= context.first.state.get("fscx",100)
                    and abs(float(origin[2])-pos[1]) > 20*context.height):
                nearby = [p for p in context.anchors.get(words[e.source_index],[]) if
                          abs(pos[0]-p[0]) <= .06*context.height and
                          abs(float(origin[1])-p[0]) <= .06*context.height and
                          abs(pos[1]-p[1]) <= 2*context.height]
    return nearby,state


def _source_fragment_layout_matches(state: dict, first: Event) -> bool:
    """Require compatible glyph font, size, alignment and unclipped nondrawing paint."""
    if (state.get("p",0) or "clip" in state or "iclip" in state or
            str(state.get("fn","")).casefold() != str(first.state.get("fn","")).casefold() or
            abs(state.get("fs",75)-first.state.get("fs",75)) > .05*first.state.get("fs",75) or
            any(state.get(k,DEFAULT_STATE.get(k)) != first.state.get(k,DEFAULT_STATE.get(k))
                for k in ("b","i","an"))):
        return False
    return True


def _source_fragment_delayed_particle_is_safe(candidate: SourceFragmentCandidate, state: dict, context: SourceFragmentRowContext, row_evidence: list[TextRow], words: dict[int,str], positions: dict) -> bool:
    """Require an actual fade and give a matching later stable row ownership of its glyph."""
    e,pos = candidate.event,candidate.pos
    # Delayed particles must actually fade. A new opaque lyric at
    # the same position is never an old row's decorative tail.
    if state.get("1a",0) <= 0 or not re.search(r"\\(?:move|fad|t)\(",e.text,re.I):
        return False
    # A matching anchor in a later stable row takes precedence;
    # repeated syllables alone cannot identify their owner.
    if any(other[0].start_s > context.first.start_s and
           other[0].start_s <= e.start_s < other[0].end_s and
           other[0].style == context.first.style and other[0].name == context.first.name and
           any(words[g.source_index] == words[e.source_index] and
               math.dist(positions[g.source_index],pos) <= .06*context.height for g in other)
           for peer in row_evidence for other in peer.paint_rows):
        return False
    return True


def _collect_source_fragment_candidates(context: SourceFragmentRowContext, indexed: dict, row_evidence: list[TextRow], words: dict[int,str], positions: dict, animated_sources: set[int], removed: set[int]) -> SourceFragmentEvidence:
    """Run highlight and particle safeguards before collecting dense-family paint evidence."""
    first = context.first
    candidates,evidence = [],set()
    for e in indexed.get((first.style,first.name,first.margin_l,first.margin_r,first.margin_v),[]):
        candidate = _profile_source_fragment_candidate(e,context,words,positions,animated_sources)
        if candidate is None:
            continue
        _match_source_fragment_highlight(candidate,context,words,animated_sources,removed)
        nearby,state = _source_fragment_nearby_anchors(candidate,context,words,animated_sources)
        if not nearby or not _source_fragment_layout_matches(state,first):
            continue
        if candidate.delayed and not _source_fragment_delayed_particle_is_safe(
                candidate,state,context,row_evidence,words,positions):
            continue
        pos = candidate.pos
        if e.source_index in animated_sources:
            anchor = min(nearby,key=lambda p:math.dist(p,pos))
            evidence.add((words[e.source_index],anchor[0]))
            candidates.append(e)
        elif (e.end_s <= first.end_s+.001 and any(math.dist(pos,p) <= .06*context.height for p in nearby)):
            candidates.append(e)
    return SourceFragmentEvidence(candidates,evidence)


def _select_source_fragment_foreground(row: TextRow, context: SourceFragmentRowContext, matched: SourceFragmentEvidence, alternating: bool, animated_sources: set[int], removed: set[int]) -> list[Event] | None:
    """Confirm only a dense nonalternating family, retaining static foreground paint and base sources."""
    candidates,evidence = matched.candidates,matched.evidence
    # Ordinary layered signs and isolated highlights are insufficient.
    if (alternating or len(evidence) < max(3, math.ceil(len(context.chosen)/2)) or
            sum(e.source_index in animated_sources for e in candidates) < 3*len(evidence)):
        return
    # Static foreground highlight paint provides the fill, while the base
    # row supplies geometry and timing. Use one paint across the whole row.
    paints = [e for e in candidates if e.source_index not in animated_sources]
    if not paints:
        paints = [e for paint_row in row.paint_rows for e in paint_row]
    kept = {e.source_index for e in context.chosen}
    removed.update(e.source_index for e in candidates if e.source_index not in kept)
    return paints


def remove_source_fragment_effects(
    events: list[Event], row_evidence: list[TextRow], words: dict[int, str],
    positions: dict[int, tuple[float, float] | None], animated_sources: set[int] | None=None, *,
    font_metrics: FontMetrics | None=None, font_report: FontProcessingReport | None=None,
) -> SourceFragmentRemoval:
    """Remove effects proven by original source rows and visibility phases.

    Use source text and anchors before freezing or coalescing glyph lifetimes.
    Return stable-row confirmation and foreground paint in independent row
    successors for reconstruction. Ambiguous or incomplete evidence stays
    intact. Source events and all supplied row containers are borrowed.
    """
    # Candidate profiling lazily resolves formatting. Isolate only unresolved
    # events, without resolving them earlier or changing matching order. Reuse
    # one successor for every reference to the same authored object.
    sources = {id(e):e for e in events}
    for row in row_evidence:
        sources[id(row.base)] = row.base
        for e,_,_ in row.pieces:
            sources[id(e)] = e
        for paint_row in row.paint_rows:
            sources.update((id(e),e) for e in paint_row)
        sources.update((id(e),e) for e in row.foreground)
    successors = {key:dataclass_replace(e,state={},continuation=OverrideContinuation()) for key,e in sources.items() if not e.state}
    events = [successors.get(id(e),e) for e in events]
    rows = [dataclass_replace(row,
        base=successors.get(id(row.base),row.base),
        pieces=[(successors.get(id(e),e),word,pos) for e,word,pos in row.pieces],
        paint_rows=[[successors.get(id(e),e) for e in paint_row] for paint_row in row.paint_rows],
        source_anchors={word:list(anchors) for word,anchors in row.source_anchors.items()},
        foreground=[successors.get(id(e),e) for e in row.foreground]) for row in row_evidence]
    animated_sources = animated_sources or set()
    indexed = _index_source_fragment_events(events,words,positions)
    removed = match_translucent_glyph_particles(events,rows,words,animated_sources)
    removed.update(match_repeated_glyph_flashes(events,words,positions,font_metrics, font_report=font_report))
    paint_families=[]
    for index,row in enumerate(rows):
        alternating = _prove_source_fragment_visibility(row,removed)
        if alternating is None:
            continue
        context = _prepare_source_fragment_row(row)
        matched = _collect_source_fragment_candidates(
            context,indexed,rows,words,positions,animated_sources,removed)
        foreground = _select_source_fragment_foreground(
            row,context,matched,alternating,animated_sources,removed)
        if foreground is not None:
            rows[index] = dataclass_replace(row,foreground=foreground,confirmed=True)
        paint_families.append(rows[index])
    output,pulses = collapse_backed_glyph_pulses(
        [e for e in events if e.source_index not in removed],words,positions,font_metrics)
    output,slices = collapse_sliced_text_sequences(output)
    return SourceFragmentRemoval(output,rows,len(removed)+pulses+slices,paint_families)
