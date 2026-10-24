"""Caption ownership of glyph/word copies and authored source-row evidence."""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace as dataclass_replace

from .ass_overrides import tokenize_override, OVERRIDE_RE, DEFAULT_STATE
from .row_evidence import TextRow
from .font_metrics import FontMetrics
from .glyph_placement import fit_fragment_anchor, matches_authored_glyph_positions
from .event_model import Event
from .event_operations import event_evaluation, replace_event, state_key
from .static_objects import static_object_key
from .caption_geometry import (
    NUM, get_pos, inline_layout_key, text_height, placement_key, text_layout_key,
)
from .caption_rendering import (
    _source_caption_paint, render_simplified_caption, render_tag, render_merged_caption,
)
from .static_selection import unrotated_text_state


@dataclass(frozen=True)
class AuthoredLyricRowsResult:
    """Matched source IDs, new row proof and resolved source-cache successors.

    Inputs are borrowed. Only unresolved, evaluated sources appear in the
    update delta; aliases in the source map share one successor. Callers apply
    those updates before later source-state readers. Existing caches are reused.
    """
    removed_sources: set[int]
    row_additions: list[TextRow]
    source_updates: dict[int,Event]


@dataclass(frozen=True)
class FullLineCopyResult:
    """Retained captions, removal count and caller-applied source/row updates.

    Row additions include both moving authored rows and static scaffold rows.
    No caller-owned event, source map or row-evidence container is modified.
    """
    events: list[Event]
    removed_count: int
    row_additions: list[TextRow]
    source_updates: dict[int,Event]


@dataclass(frozen=True)
class FullLineCopyProof:
    """Complete fragment ownership evidence and the selected foreground column representatives."""
    ordered: list[Event]
    fragments: list[Event]
    assembled: str
    shadow_only: bool


def match_authored_lyric_rows(events: list[Event], visible_map: dict[int, str],
                              source_events: dict[int, Event]) -> AuthoredLyricRowsResult:
    """Prove complete captions from matching entrance and exit letter rows.

    Return removable source indices, row additions and resolved source updates
    for the existing covered-fragment pass. Original move endpoints prove
    placement; caption text and timing remain unchanged, and ambiguous or
    incomplete matches stay intact. Resolve private successors without caching
    into borrowed events, including when events and source-map entries alias.
    """
    removed: set[int] = set()
    row_evidence: list[TextRow] = []
    source_successors: dict[int,Event] = {}
    norm = lambda value: "".join(value.split()).casefold()
    moving: dict[tuple,list[tuple[Event,Event,list[float]]]] = {}
    captions: dict[tuple,list[tuple[Event,Event]]] = {}
    families = {(e.style,e.name) for e in events
                if visible_map.get(e.source_index,"") and
                (source := source_events.get(e.source_index)) is not None and
                re.search(r"\\move\s*\(",source.text,re.I)}
    for e in events:
        original = source_events.get(e.source_index)
        source = source_successors.get(id(original),original)
        words = visible_map.get(e.source_index, "")
        if ((e.style,e.name) not in families or source is None or
                e.kind != "Dialogue" or not words or
                source.duration <= 0 or inline_layout_key(e)):
            continue
        is_move = bool(re.search(r"\\move\s*\(",source.text,re.I))
        if not is_move and len(words) < 8:
            continue
        if not is_move and re.search(r"\\(?:t|fad(?:e)?)\s*\(",source.text,re.I):
            continue
        evaluated = event_evaluation(source)
        state = evaluated.formatting
        if not source.state:
            source = dataclass_replace(source,state=state,continuation=evaluated.continuation)
            source_successors[id(original)] = source
        # The input event list may contain the source object itself. Earlier
        # caching resolved that alias too; use its successor for the same proof.
        if e is original:
            e = source
        if (state.get("p",0) or state.get("1a",0) != 0 or
                any(k in state for k in ("clip","iclip","org")) or
                any(abs(state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        key = (e.style,e.name,placement_key(source)[0],
               tuple((k,v) for k,v in text_layout_key(source) if k != "an"))
        if is_move:
            tokens = [token for block in OVERRIDE_RE.findall(source.text)
                      for token in tokenize_override(block)]
            moves = [value for tag,value in tokens if tag == "move"]
            if (len(moves) != 1 or state.get("an") != 5 or
                    any(tag == "t" for tag,value in tokens)):
                continue
            try:
                values = [float(v) for v in moves[0].strip("()").split(",")]
            except ValueError:
                continue
            if len(values) not in (4,6) or not all(math.isfinite(v) for v in values):
                continue
            if len(values) == 6 and not 0 <= values[4] < values[5] <= 1000*source.duration+.001:
                continue
            moving.setdefault((key,source.start,source.end,source.layer),[]).append((e,source,values))
        elif get_pos(e.text) is None:
            captions.setdefault(key,[]).append((e,source))
    rows: dict[tuple,list[list[tuple[Event,Event,list[float]]]]] = {}
    for (key,start,end,layer),pieces in moving.items():
        if len(pieces) >= 8:
            rows.setdefault((key,"in",end),[]).append(pieces)
            rows.setdefault((key,"out",start),[]).append(pieces)
    for key,full_lines in captions.items():
        colliding = set()
        latest = None
        for full,source in sorted(full_lines,key=lambda pair:pair[0].start_s):
            if latest is not None and full.start_s < latest.end_s:
                colliding.update((full.source_index,latest.source_index))
            if latest is None or full.end_s > latest.end_s:
                latest = full
        for full,source in full_lines:
            # Style-based placement may move under ASS collision handling.
            # Overlapping unpositioned captions cannot prove this baseline.
            if full.source_index in colliding:
                continue
            height = text_height(source)
            alignment = int(source.state.get("an",2))
            if alignment not in range(1,10) or height <= 0:
                continue
            width,canvas_height = source.measurement.canvas or (0,0)
            left,right,vertical = placement_key(source)[0]
            expected_y = (canvas_height-vertical-height/2 if alignment <= 3 else
                          canvas_height/2 if alignment <= 6 else vertical+height/2)
            matched = {"in":[],"out":[]}
            adjacent = [(phase,pieces) for phase,boundary in
                        (("in",source.start),("out",source.end))
                        for pieces in rows.get((key,phase,boundary),[])]
            for phase,pieces in adjacent:
                first = pieces[0][1]
                if first.layer != source.layer:
                    continue
                offset = 2 if phase == "in" else 0
                ordered = sorted(pieces,key=lambda piece:piece[2][offset])
                positions = [tuple(values[offset:offset+2]) for e,original,values in ordered]
                xs,ys = [p[0] for p in positions],[p[1] for p in positions]
                if (norm("".join(visible_map[e.source_index] for e,original,values in ordered)) !=
                        norm(visible_map[full.source_index]) or
                        any(b-a <= full.unit for a,b in zip(xs,xs[1:])) or
                        max(ys)-min(ys) > .06*height or
                        abs(statistics.median(ys)-expected_y) > .06*height):
                    continue
                horizontal = (alignment-1)%3
                if (horizontal == 0 and not left <= xs[0] <= left+height or
                        horizontal == 2 and not width-right-height <= xs[-1] <= width-right or
                        horizontal == 1 and abs((xs[0]+xs[-1])/2-width/2) > height/2):
                    continue
                matched[phase].append((ordered,positions))
            if len(matched["in"]) != 1 or len(matched["out"]) != 1:
                continue
            entrance,positions = matched["in"][0]
            exit_row,exit_positions = matched["out"][0]
            if (any(visible_map[a[0].source_index] != visible_map[b[0].source_index]
                    for a,b in zip(entrance,exit_row)) or len(entrance) != len(exit_row) or
                    any(math.dist(a,b) > full.unit for a,b in zip(positions,exit_positions))):
                continue
            # Feed the established covered-fragment pass a real row model.
            # It owns nested syllable removal and its font/actor/layer guards.
            # The model's centered placement does not alter the caption.
            pieces = [(replace_event(original,text=render_simplified_caption(
                original.state,visible_map[e.source_index],an=5,pos=pos,measurement=original.measurement,
                source_paint=_source_caption_paint(original.state,[original.state]))),
                visible_map[e.source_index],pos)
                for (e,original,values),pos in zip(entrance,positions)]
            center = ((positions[0][0]+positions[-1][0])/2,statistics.median(p[1] for p in positions))
            base = replace_event(full,text=render_simplified_caption(full.state,visible_map[full.source_index],
                                                              an=5,pos=center,measurement=full.measurement,
                                                              source_paint=_source_caption_paint(full.state,[full.state])))
            row_evidence.append(TextRow(base,pieces))
            removed.update(e.source_index for row in (entrance,exit_row) for e,original,values in row)
    source_updates = {index:source_successors[id(event)] for index,event in source_events.items()
                      if id(event) in source_successors} if source_successors else {}
    return AuthoredLyricRowsResult(removed,row_evidence,source_updates)


def match_nested_glyph_copies(
    events: list[Event], visible_map: dict[int, str], metric: FontMetrics | None,
) -> set[int]:
    """Prove complete letter copies inside equally painted word fragments.

    Require near-coextensive nested timing and exact-font glyph spacing and
    anchors, rather than a shared word center alone. Every letter in a phase
    must have one owner; missing, extra or multiply owned letters keep that
    whole phase. Parent-only fragments are retained, including lone letters.
    """
    if metric is None or not metric.available:
        return set()
    groups = {}
    for e in events:
        word = visible_map.get(e.source_index,"")
        pos = get_pos(e.text)
        if (e.kind != "Dialogue" or not word or pos is None or e.effect or
                e.duration <= 0 or not e.layer.lstrip('-').isdigit() or
                e.state.get('1a',0) != 0 or e.state.get('p',0) or
                e.state.get('borderstyle',1) != 1 or inline_layout_key(e) or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay','fsp')) or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word) or
                OVERRIDE_RE.sub('',e.text) != word or
                any(not math.isfinite(v) for v in (*pos,e.start_s,e.end_s)) or
                static_object_key(e,e.styles) is None):
            continue
        key = (e.style,e.name,e.row,placement_key(e),state_key(e,{'pos'}))
        groups.setdefault(key,{}).setdefault((e.start,e.end,e.layer),[]).append(e)

    proposals = []
    for phases in groups.values():
        by_start = {}
        for (start,end,layer),group in phases.items():
            by_start.setdefault((start,layer),[]).extend(group)
        parents = [group for group in by_start.values()
                   if sum(len(visible_map[e.source_index]) > 1 for e in group) >= 4]
        children = sorted((group for group in phases.values()
                           if len(group) >= 8 and all(len(visible_map[e.source_index]) == 1
                                                    for e in group)),key=lambda g:g[0].start_s)
        starts = [group[0].start_s for group in children]
        for parent_group in parents:
            # Earlier phase merging can extend one held fragment beyond its
            # neighbors. It remains valid backing throughout the shorter cue;
            # keep that lifetime and use the common end only for phase lookup.
            parent = min(parent_group,key=lambda e:e.end_s)
            if len({get_pos(e.text) for e in parent_group}) != len(parent_group):
                continue
            for child_group in children[bisect_left(starts,parent.start_s-1e-6):
                                        bisect_right(starts,parent.start_s+.25+1e-6)]:
                child = child_group[0]
                if (child.end_s > parent.end_s+1e-6 or
                        parent.end_s-child.end_s > .25+1e-6 or
                        child.duration < .8*parent.duration or
                        child.start == parent.start and child.end == parent.end):
                    continue
                ordered = sorted(child_group,key=lambda e:get_pos(e.text)[0])
                xs = [get_pos(e.text)[0] for e in ordered]
                if any(b-a <= child.unit for a,b in zip(xs,xs[1:])):
                    continue
                letters = [visible_map[e.source_index] for e in ordered]
                owners = [0]*len(ordered)
                matched = 0
                for p in parent_group:
                    word = visible_map[p.source_index]
                    px,py = get_pos(p.text)
                    options = []
                    for index in range(len(ordered)-len(word)+1):
                        stop = index+len(word)
                        if (''.join(letters[index:stop]) != word or
                                any(abs(get_pos(e.text)[1]-py) > .25*p.unit
                                    for e in ordered[index:stop])):
                            continue
                        anchor = fit_fragment_anchor(metric, p.state,xs[index:stop],letters[index:stop],
                                                        word,p.unit,separate_glyphs=True,exact_size=True)
                        if anchor is not None and abs(anchor-px) <= .25*p.unit:
                            options.append((index,stop))
                    if len(options) > 1:
                        matched = -1; break
                    if options:
                        index,stop = options[0]
                        for i in range(index,stop):
                            owners[i] += 1
                        matched += len(word) > 1
                if matched >= 4 and all(owner == 1 for owner in owners):
                    proposals.append({e.source_index for e in child_group})
    ownership = {}
    for members in proposals:
        for index in members:
            ownership[index] = ownership.get(index,0)+1
    return {index for members in proposals if all(ownership[i] == 1 for i in members)
            for index in members}


def match_staggered_full_line_copies(
    events: list[Event], visible_map: dict[int, str], metric: FontMetrics | None,
) -> set[int]:
    """Match complete, near-coextensive glyph rows to retained full captions.

    Exact font advances and the authored spaces prove the whole row, including
    style-based caption placement. Actor labels may differ, but each letter
    row keeps its own label/layer and needs exactly one owner. Keep the full
    caption's formatting and timing; staggered copy lead-ins/tails are effects.
    """
    if metric is None or not metric.available:
        return set()
    captions, groups, unpositioned = [], {}, {}

    def geometry(e: Event) -> tuple:
        return (e.style,placement_key(e)[0],
                tuple((k,str(v).casefold() if k == 'fn' else v)
                      for k,v in text_layout_key(e) if k != 'an'),
                (int(e.state.get('an',2))-1)%3)

    for e in events:
        word = visible_map.get(e.source_index,'')
        if e.kind != 'Dialogue' or not word or e.duration <= 0:
            continue
        pos = get_pos(e.text)
        if pos is None and not e.state.get('p',0):
            collision_layer = int(e.layer) if e.layer.lstrip('+-').isdigit() else 0
            unpositioned.setdefault((collision_layer,(int(e.state.get('an',2))-1)//3),[]).append(e)
        if (not e.layer.lstrip('-').isdigit() or e.state.get('1a',0) != 0 or
                e.state.get('p',0) or e.state.get('borderstyle',1) != 1 or
                inline_layout_key(e) or not unrotated_text_state(e.state) or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay'))):
            continue
        if len(word) == 1 and not word.isspace() and pos is not None:
            key = (geometry(e),e.name,e.layer,e.row)
            groups.setdefault(key,[]).append(e)
        elif len(''.join(word.split())) >= 3:
            captions.append(e)
    if not captions or not groups:
        return set()

    # Default ASS placement can shift under collision handling. Only isolated
    # unpositioned captions prove a baseline, even across different styles.
    colliding = set()
    for peers in unpositioned.values():
        previous = None
        for e in sorted(peers,key=lambda item:item.start_s):
            if previous is not None and e.start_s < previous.end_s:
                colliding.update((previous.source_index,e.source_index))
            if previous is None or e.end_s > previous.end_s:
                previous = e
    indexes = {}
    for (key,name,layer,row),peers in groups.items():
        ordered = sorted(peers,key=lambda e:e.start_s)
        indexes.setdefault(key,[]).append((int(layer),[e.start_s for e in ordered],ordered))

    proposals = []
    for full in captions:
        key = geometry(full)
        families = indexes.get(key,[])
        if not families or full.source_index in colliding:
            continue
        pos = get_pos(full.text)
        canvas = full.measurement.canvas
        alignment = int(full.state.get('an',2))
        if alignment not in range(1,10) or static_object_key(
                full,full.styles,allow_unpositioned=True) is None:
            continue
        left,right,vertical = placement_key(full)[0]
        height = text_height(full)
        if pos is None:
            if canvas is None:
                continue
            width,canvas_height = canvas
            horizontal = (alignment-1)%3
            pos = (left if horizontal == 0 else width-right if horizontal == 2 else
                   (left+width-right)/2,
                   canvas_height-vertical if alignment <= 3 else
                   canvas_height/2 if alignment <= 6 else vertical)
        center_y = pos[1]+((alignment-1)//3-1)*height/2
        text = visible_map[full.source_index]
        # Stagger may grow with a long cue. Bound both endpoints and shared
        # visibility relative to that cue instead of assuming a fixed delay.
        allowance = .2*full.duration
        for layer,starts,peers in families:
            if layer > int(full.layer):
                continue
            candidates = peers[bisect_left(starts,full.start_s-allowance-1e-6):
                               bisect_right(starts,full.start_s+allowance+1e-6)]
            candidates = [e for e in candidates
                if abs(e.end_s-full.end_s) <= allowance+1e-6 and
                   min(e.end_s,full.end_s)-max(e.start_s,full.start_s) >=
                        .8*max(e.duration,full.duration)-1e-6 and
                   e.state.get('1c') == full.state.get('1c') and
                   abs(get_pos(e.text)[1]+((int(e.state.get('an',5))-1)//3-1)*
                       text_height(e)/2-center_y) <= full.unit]
            candidates.sort(key=lambda e:get_pos(e.text)[0])
            if (len(candidates) != len(''.join(text.split())) or
                    ''.join(visible_map[e.source_index] for e in candidates) != ''.join(text.split()) or
                    len({get_pos(e.text)[0] for e in candidates}) != len(candidates) or
                    not matches_authored_glyph_positions(metric, 
                        full.state,[get_pos(e.text)[0] for e in candidates],text,pos[0],full.unit)):
                continue
            # A caption that wraps is not the single row the letters prove.
            # Explicit no-wrap formatting can intentionally span the canvas.
            if full.state.get('q') != 2:
                if canvas is None:
                    continue
                face = metric.matching_face(str(full.state.get('fn','')),
                    full.state.get('b',0),bool(full.state.get('i',0)))
                try:
                    span = (metric.measure(face,text,bool(full.state.get('kerning',False)))*
                            metric.ass_em_scale(face)*full.state.get('fs',20)*
                            full.state.get('fscx',100)/100/1024+
                            full.state.get('fsp',0)*full.state.get('fscx',100)/100*(len(text)-1))
                except (OSError,ValueError,RuntimeError,TypeError):
                    continue
                if span > canvas[0]-left-right+full.unit:
                    continue
            if any(static_object_key(e,e.styles) is None for e in candidates):
                continue
            proposals.append({e.source_index for e in candidates})
    owners = {}
    for members in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    return {index for members in proposals if all(owners[i] == 1 for i in members)
            for index in members}


def _prove_full_line_fragment_copies(full: Event, group: list[Event],
                                     visible_map: dict[int,str], removed: set[int]) -> FullLineCopyProof | None:
    """Prove a complete spatial row and select its foreground columns without changing ownership."""
    norm = lambda value: "".join(value.split()).casefold()
    shadow_only = (full.state.get('1a',0) >= 254 and
                   full.state.get('3a',0) >= 254 and
                   full.state.get('4a',0) < 254 and
                   full.state.get('borderstyle',1) == 1 and
                   not full.state.get('p',0) and
                   not inline_layout_key(full) and
                   not any(k in full.state for k in ('clip','iclip','org')) and
                   unrotated_text_state(full.state) and
                   any(abs(full.state.get(k,full.state.get('shad',0))) > 0
                       for k in ('xshad','yshad')))
    full_length = len(norm(visible_map[full.source_index]))
    fx = [e for e in group if e is not full and e.source_index not in removed
          and 0 < len(norm(visible_map[e.source_index])) < full_length
          # Longer word/syllable copies need matching font geometry
          # and placement as well as the complete-row text proof below.
          and (len(visible_map[e.source_index]) <= 4 or
               (text_layout_key(e) == text_layout_key(full) and
                placement_key(e) == placement_key(full) and
                not e.state.get('p',0) and not inline_layout_key(e) and
                not any(k in e.state for k in ('clip','iclip','org')) and
                unrotated_text_state(e.state)))
          and abs(get_pos(e.text)[1]-get_pos(full.text)[1]) <= .1*text_height(full)]
    if shadow_only:
        # A complete shadow backing supplies authored text and its
        # exact caption anchor. Four opaque, equally timed fragments
        # with identical font/layout can prove its foreground without
        # requiring duplicate effect layers for every syllable.
        fx = [e for e in fx if e.state.get('1a',0) == 0 and
              text_layout_key(e) == text_layout_key(full) and
              placement_key(e) == placement_key(full)]
    if len(fx) < (4 if shadow_only else 8):
        return None
    columns: list[list[Event]] = []
    for e in sorted(fx,key=lambda e:get_pos(e.text)[0]):
        if columns and abs(get_pos(e.text)[0]-get_pos(columns[-1][0].text)[0]) <= .06*text_height(full):
            columns[-1].append(e)
        else:
            columns.append([e])
    if len(columns) < 4 or any(len({visible_map[e.source_index] for e in col}) != 1
                               for col in columns):
        return None
    assembled = "".join(visible_map[col[0].source_index] for col in columns)
    matches = (''.join(assembled.split()) == ''.join(visible_map[full.source_index].split())
               if shadow_only else norm(assembled) == norm(visible_map[full.source_index]))
    if not matches:
        return None
    xs = [get_pos(col[0].text)[0] for col in columns]
    if not min(xs) <= get_pos(full.text)[0] <= max(xs):
        return None
    # The author's complete, spaced text is the canonical caption.
    # Standard simplification gives it one opaque fill and contour instead of
    # translucent backing paint plus dozens of animated letters.
    ordered = [max(col,key=lambda e:(int(e.layer) if e.layer.lstrip('-').isdigit() else 0,
                                     e.source_index)) for col in columns]
    return FullLineCopyProof(ordered,fx,assembled,shadow_only)


def _render_proven_full_line_caption(full: Event, proof: FullLineCopyProof,
                                   visible_map: dict[int,str]) -> str | None:
    """Recover proved foreground paint while preserving authored text, placement and tracking spans."""
    ordered,assembled,shadow_only = proof.ordered,proof.assembled,proof.shadow_only
    prefix_end = re.match(r'(?:\{[^}]*\})*',full.text).end()
    tracking_tokens = [token for block in OVERRIDE_RE.findall(full.text[prefix_end:])
                       for token in tokenize_override(block)]
    tracking_only = (bool(tracking_tokens) and
        all(k == 'fsp' and re.fullmatch(NUM,v) and math.isfinite(float(v))
            for k,v in tracking_tokens) and
        len({tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
            ('1c','3c','b','i','u','s')) for e in ordered}) == 1)
    def paint_layout(e):
        return tuple((k,v) for k,v in text_layout_key(e)
                     if not tracking_only or k != 'fsp')
    # A nearly invisible full-line scaffold can carry the literal text
    # while its already-matched opaque letters carry the actual paint.
    # Reuse those colours only after the existing ownership proof, with
    # identical literal characters and font/layout/placement evidence.
    fragment_paint = shadow_only or (
        full.state.get('1a',0) >= 254 and full.state.get('3a',0) >= 254 and
        (not inline_layout_key(full) or tracking_only) and
        not any(k in full.state for k in ('clip','iclip','org')) and
        unrotated_text_state(full.state) and
        ''.join(assembled.split()) == ''.join(visible_map[full.source_index].split()) and
        all(e.state.get('1a',0) == 0 and
            paint_layout(e) == paint_layout(full) and
            (placement_key(e)[:3] == placement_key(full)[:3] if tracking_only else
             placement_key(e) == placement_key(full)) and
            not inline_layout_key(e) and
            not any(k in e.state for k in ('clip','iclip','org')) for e in ordered))
    if fragment_paint:
        body = render_merged_caption(ordered,
            [visible_map[e.source_index] for e in ordered],visible_map[full.source_index],
            animated=True,an=int(full.state.get('an',5)),pos=get_pos(full.text),
            fscx=full.state.get('fscx',100),fscy=full.state.get('fscy',100))
        if body is None:
            return None
        if tracking_only:
            # Authored spacing remains authoritative. Uniform proved
            # foreground paint can replace the scaffold header while
            # retaining its literal text and tracking spans exactly.
            body = body[:body.index('}')+1]+full.text[prefix_end:]
        if 'q' in full.state:
            body = '{'+render_tag('q',full.state['q'])+'}'+body
    else:
        body = render_simplified_caption(full.state,visible_map[full.source_index],measurement=full.measurement,
                                         source_paint=_source_caption_paint(full.state,[full.state]))
    return body


def remove_letters_over_full_lines(
    events: list[Event], visible_map: dict[int, str], source_events: dict[int, Event] | None=None,
    *, collect_rows: bool=False, font_metrics: FontMetrics | None=None,
) -> FullLineCopyResult:
    """Use retained full lines or word fragments over proven letter copies.

    Match complete text and placement, using either equal timing or paired
    entrance/exit rows. Near-coextensive full-line and word-fragment copies
    additionally require exact-font glyph positions. Nearby letters alone never prove
    caption ownership. Complete shadow backings can supply authored text and
    its anchor, while matching opaque fragments supply foreground paint.
    Opt into row collection to return additions for reconstruction and run
    authored-source matching. Source caches are returned as explicit updates.
    """
    removed = match_nested_glyph_copies(events,visible_map,font_metrics)
    removed.update(match_staggered_full_line_copies(events,visible_map,font_metrics))
    replacements: dict[int,Event] = {}
    row_additions: list[TextRow] = []
    source_updates: dict[int,Event] = {}
    if source_events is not None and collect_rows:
        authored = match_authored_lyric_rows(events,visible_map,source_events)
        removed.update(authored.removed_sources)
        row_additions.extend(authored.row_additions)
        source_updates = authored.source_updates
        if source_updates:
            successors = {id(source_events[index]):event for index,event in source_updates.items()}
            events = [successors.get(id(e),e) for e in events]
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind == "Dialogue" and get_pos(e.text) is not None and visible_map.get(e.source_index):
            groups.setdefault((e.style,e.name,e.start,e.end,e.row,
                               e.margin_l,e.margin_r,e.margin_v),[]).append(e)
    for group in groups.values():
        full_lines = [e for e in group if len(visible_map[e.source_index]) >= 8
                      and len(visible_map[e.source_index].split()) >= 2]
        for full in full_lines:
            if full.source_index in removed:
                continue
            proof = _prove_full_line_fragment_copies(full,group,visible_map,removed)
            if proof is None:
                continue
            body = _render_proven_full_line_caption(full,proof,visible_map)
            if body is None:
                continue
            replacements[full.source_index] = replace_event(
                full, text=body,
                layer="0", effect="")
            if collect_rows:
                row_additions.append(TextRow(replacements[full.source_index],
                    [(e,visible_map[e.source_index],get_pos(e.text)) for e in proof.ordered]))
            removed.update(e.source_index for e in proof.fragments)
    return FullLineCopyResult([replacements.get(e.source_index,e) for e in events
            if e.source_index not in removed],len(removed),row_additions,source_updates)
