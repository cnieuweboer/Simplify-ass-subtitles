"""Source-backed readable fade cores and synchronized caption handoffs.

Inputs remain borrowed; source-proof caches, collision indexes and replacement
buffers are call-local. Callers retain pipeline order, adoption and reporting.
"""
from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass, replace as dataclass_replace

from .ass_overrides import (
    DEFAULT_STATE, NUMBER, OVERRIDE_RE, OverrideContinuation, apply_override,
    effective_state, evaluate_effective_state, tokenize_override,
)
from .caption_geometry import get_pos, inline_layout_key, text_height
from .effect_validation import opaque_text_effect_state, parse_effect_transform
from .event_model import Event
from .event_operations import (
    _faded_cue_is_scrolling, event_override_tokens, literal_font_spans, replace_event,
)
from .row_evidence import TextRow
from .static_selection import unrotated_text_state
from .subtitle_document import format_time
from .text_freezing import without_inert_spacing_tail


@dataclass(frozen=True)
class FadedCueContext:
    """Private retained-cue indexes and source-proven family cores for one pass."""
    provenance: dict[int,list[TextRow]]
    groups: dict[tuple,dict[tuple,list[Event]]]
    family_proofs: dict[tuple,tuple]



@dataclass(frozen=True)
class FadedCueEvidence:
    """Collision-boundary fragment fade endpoints and priority shadow phases."""
    phase_slots: dict[tuple,dict[tuple,set[float]]]
    shadow_phases: set[tuple]



def shadow_lyric_fade_core(e: Event) -> tuple[dict,float,float] | None:
    """Prove one shadow glyph's opaque hold between entrance and fade tail.

    Only a short, one-way shadow-opacity entrance and stationary literal
    geometry qualify. Shadow offsets and colour may animate; other geometry,
    alpha pulses, clips, inline state and unsupported fade forms cannot prove
    a handoff. This supplies timing evidence, never a replacement caption.
    """
    e = without_inert_spacing_tail(e)
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    if (e.duration <= 0 or get_pos(e.text) is None or inline_layout_key(e) or
            state.get('1a',0) < 254 or state.get('3a',0) < 254 or
            state.get('borderstyle',1) != 1 or state.get('p',0) or
            not unrotated_text_state(state) or
            not any(abs(state.get(k,state.get('shad',0))) > 0
                    for k in ('xshad','yshad')) or
            any(k in state for k in ('clip','iclip','org'))):
        return None
    tokens = event_override_tokens(e)
    fades = [v for k,v in tokens if k == 'fad']
    if len(fades) != 1 or any(k in {'move','fade','r','alpha','k','kf','ko','kt'} for k,v in tokens):
        return None
    try:
        fade_in,fade_out = [float(v)/1000 for v in fades[0].strip('()').split(',')]
    except ValueError:
        return None
    if (not fades[0].startswith('(') or not fades[0].endswith(')') or
            not all(math.isfinite(v) and v >= 0 for v in (fade_in,fade_out)) or
            fade_out <= 0):
        return None
    entrance = fade_in
    reveals = []
    allowed = {'4a','4c','shad','xshad','yshad'}
    for tag,value in tokens:
        if tag != 't':
            continue
        transform = parse_effect_transform(value,e.duration,allowed,
            allow_instant=True,allow_after_end=True)
        if transform is None:
            return None
        begin,end,changes = transform
        if any(k == '4a' for k,v in changes):
            target = state.copy()
            target_continuation = evaluated.continuation
            for k,v in changes:
                target_continuation = apply_override(target,k,v,e.styles,e.defaults,target_continuation)
            if (target.get('4a') != 0 or end > 500*e.duration or
                    len([1 for k,v in changes if k == '4a']) != 1):
                return None
            reveals.append(end/1000)
    if state.get('4a',0) != 0:
        if state.get('4a',0) < 254 or len(reveals) != 1:
            return None
    elif reveals:
        return None
    entrance = max([entrance]+reveals)
    start,end = e.start_s+entrance,e.end_s-fade_out
    if not e.start_s <= start < end < e.end_s:
        return None
    return {**state,'1a':0,'3a':0,'shad':0,'xshad':0,'yshad':0},start,end



@dataclass(frozen=True)
class CueFadeFamily:
    """Current fragments and their source-proven protected display interval."""
    members: tuple[Event,...]
    core: tuple[float,float]
    xspan: tuple[float,float]



def text_cue_lane(e: Event, pos: tuple[float,float], state: dict) -> tuple:
    return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
            round(pos[1],4),(int(state.get('an',2))-1)//3)



def derive_staggered_fade_cores(events: list[Event], rows: list[TextRow],
                                sources: dict[int,Event]) -> list[TextRow]:
    """Attach complete source-fade cores to already validated reconstructed rows.

    Each fragment must match one stationary original source in text, font,
    layout and anchor. Protect the intersection of their fully readable
    intervals, without requiring synchronized glyph entrances or exits.
    Borrow all inputs; only returned row successors receive the new core.
    Existing phase proofs and ambiguous or incomplete rows are untouched.
    """
    current = {e.source_index:e for e in events}
    claims = collections.Counter(row.base.source_index for row in rows if not row.virtual)
    forbidden = {'t','move','clip','iclip','org','fade','r','k','kf','ko','kt','fax','fay','p'}
    cache = {}
    output = []
    for row in rows:
        caption = current.get(row.base.source_index)
        pos = get_pos(caption.text) if caption is not None else None
        if (row.virtual or row.phase_core is not None or
                claims[row.base.source_index] != 1 or caption is None or
                caption.kind != 'Dialogue' or caption.text != row.base.text or len(row.pieces) < 2 or
                pos is None or not all(math.isfinite(v) for v in pos) or
                _faded_cue_is_scrolling(caption) or
                not opaque_text_effect_state(caption.state) or
                not unrotated_text_state(caption.state) or
                re.search(r'\\[Nn]|[\r\n]',caption.text) or
                ''.join(OVERRIDE_RE.sub('',caption.text).split()) !=
                ''.join(''.join(word.split()) for piece,word,anchor in row.pieces) or
                len({piece.source_index for piece,word,anchor in row.pieces}) != len(row.pieces)):
            output.append(row)
            continue
        lane = text_cue_lane(caption,pos,caption.state)
        intervals = []
        for piece,word,anchor in row.pieces:
            index = piece.source_index
            source = sources.get(index)
            if index not in cache:
                cache[index] = (_parse_faded_source_evidence(source,forbidden)
                                if source is not None and source.source_index == index and
                                source.kind == 'Dialogue' and not _faded_cue_is_scrolling(source) and
                                not OVERRIDE_RE.search(source.text,
                                    re.match(r'(?:\{[^}]*\})*',source.text).end()) and
                                source.duration > 0 and all(math.isfinite(v) for v in
                                    (source.start_s,source.end_s)) else None)
            proof = cache[index]
            slot = _faded_cue_slot(piece,anchor) if anchor is not None and len(anchor) == 2 else None
            if (source is None or proof is None or not word.strip() or
                    piece.kind != 'Dialogue' or anchor is None or len(anchor) != 2 or
                    not all(math.isfinite(v) for v in anchor) or
                    source.style != caption.style or proof[0] != lane or
                    # Reconstruction serializes anchors to two decimals in
                    # some paths. Permit only that subpixel rounding error;
                    # text/font/layout identity must still match exactly.
                    math.dist(proof[1][0],anchor) > .0071 or
                    slot is None or proof[1][1:] != slot[1:] or
                    OVERRIDE_RE.sub('',piece.text).strip() != word.strip() or
                    proof[2] <= 0 or proof[3] <= 0 or
                    source.start_s < caption.start_s-1e-7 or
                    source.end_s > caption.end_s+1e-7):
                break
            intervals.append((source.start_s+proof[2],source.end_s-proof[3]))
        if len(intervals) != len(row.pieces):
            output.append(row)
            continue
        core = max(start for start,end in intervals),min(end for start,end in intervals)
        output.append(dataclass_replace(row,phase_core=core)
                      if caption.start_s < core[0] < core[1] < caption.end_s else row)
    return output



def collect_faded_cue_families(events: list[Event], rows: list[TextRow],
                               sources: dict[int,Event]) -> list[CueFadeFamily]:
    """Recover fade boundaries across source-backed staggered fragments.

    Every retained fragment must match its original text, anchor and layout.
    Only stationary opaque sources with paint-only transforms qualify; the
    caller may supply sources whose oscillating rotations were already proved
    and normalized. Common starts/ends identify fade families, not arbitrary
    temporal proximity. This helper supplies evidence, never trims timing.
    Rows are borrowed successors adopted from preceding evidence passes.
    """
    provenance = {}
    for row in rows:
        if not row.virtual:
            provenance.setdefault(row.base.source_index,[]).append(row)
    layout = ('fn','fs','fscx','fscy','fsp','an','b','i','u','s','fax','fay','pbo')
    paint = {'c','1c','2c','3c','4c','bord','xbord','ybord','shad','xshad','yshad','blur','be'}
    cache = {}
    def proof(piece,word,pos):
        index = piece.source_index
        if index not in cache:
            source = sources.get(index)
            data = None
            if source is not None and source.kind == 'Dialogue' and source.duration > 0:
                source = without_inert_spacing_tail(source)
                tokens = event_override_tokens(source)
                prefix = re.match(r'(?:\{[^}]*\})*',source.text).end()
                state = effective_state(source.text,source.defaults,source.styles)
                fades = [v for k,v in tokens if k == 'fad']
                if (fades and all(re.fullmatch(r'\(\s*'+NUMBER+r'\s*,\s*'+NUMBER+r'\s*\)',v)
                                  for v in fades) and
                        get_pos(source.text) is not None and not state.get('p',0) and
                        state.get('1a',0) == 0 and unrotated_text_state(state) and
                        not OVERRIDE_RE.search(source.text,prefix) and
                        not any(k in {'move','fade','clip','iclip','org','p','r','k','kf','ko','kt'}
                                for k,v in tokens) and
                        all(k in paint for tag,value in tokens if tag == 't'
                            for k,v in tokenize_override(value[1:-1]))):
                    values = [tuple(float(v)/1000 for v in fade[1:-1].split(',')) for fade in fades]
                    if all(math.isfinite(v) and v >= 0 for fade in values for v in fade):
                        # If repeated fade tags differ, protect the union of
                        # their fully visible intervals. No parser-order guess
                        # can authorize cutting a possibly stable frame.
                        ingress = min(f[0] for f in values)
                        tail = min(f[1] for f in values)
                        if ingress+tail < source.duration:
                            data = (source,state,ingress,tail)
            cache[index] = data
        data = cache[index]
        if data is None:
            return None
        source,state,ingress,tail = data
        if (source.style != piece.style or source.name != piece.name or
                (source.margin_l,source.margin_r,source.margin_v) !=
                (piece.margin_l,piece.margin_r,piece.margin_v) or
                OVERRIDE_RE.sub('',source.text).strip() != word.strip() or
                math.dist(get_pos(source.text),pos) > .001 or
                any(state.get(k,DEFAULT_STATE.get(k)) != piece.state.get(k,DEFAULT_STATE.get(k))
                    for k in layout)):
            return None
        return source,ingress,tail
    groups = {}
    for e in events:
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or pos is None or not opaque_text_effect_state(e.state) or
                not unrotated_text_state(e.state) or e.effect.split(';',1)[0].strip().casefold()
                in {'banner','scroll up','scroll down'}):
            continue
        evidence = provenance.get(e.source_index,[])
        valid = not (len(evidence) > 1 or evidence and evidence[0].base.text != e.text)
        pieces = evidence[0].pieces if valid and evidence else [(e,OVERRIDE_RE.sub('',e.text),pos)]
        details = [proof(piece,word,anchor) for piece,word,anchor in pieces] if valid else []
        # Record one-sided proofs too: a held suffix can prove the outgoing
        # tail while an incoming word phase independently proves its entrance.
        for phase,boundary in ((0,e.start_s),(1,e.end_s)):
            supported = (details and all(item is not None for item in details) and
                all(abs((source.start_s if phase == 0 else source.end_s)-boundary) < .001 and
                    (ingress if phase == 0 else tail) > 0 for source,ingress,tail in details))
            key = (text_cue_lane(e,pos,e.state),phase,round(boundary,2))
            groups.setdefault(key,[]).append((e,pieces,details if supported else None))
    candidates = {}
    for (lane,phase,boundary),items in groups.items():
        if any(details is None for e,pieces,details in items):
            continue
        anchors = [(anchor[0],word,piece) for e,pieces,details in items
                   for piece,word,anchor in pieces if word.strip()]
        anchors.sort(key=lambda item:item[0])
        if (sum(len(word.strip()) for x,word,piece in anchors) < 4 or
                len({round(x,4) for x,word,piece in anchors}) != len(anchors) or
                any(b[0]-a[0] > 2*max(text_height(a[2]),text_height(b[2]))
                    for a,b in zip(anchors,anchors[1:]))):
            continue
        members = tuple(e for e,pieces,details in items)
        details = [item for e,pieces,data in items for item in data]
        core = (min(source.start_s+ingress for source,ingress,tail in details),
                max(source.end_s-tail for source,ingress,tail in details))
        if not core[0] < core[1]:
            continue
        identity = tuple(sorted(e.source_index for e in members))
        family = CueFadeFamily(members,core,(anchors[0][0],anchors[-1][0]))
        if identity in candidates:
            previous = candidates[identity]
            family = CueFadeFamily(members,(min(core[0],previous.core[0]),
                                            max(core[1],previous.core[1])),family.xspan)
        candidates[identity] = family
    # Phase coordinators may already have proved a settled core without an
    # opaque source \fad (for example separate opacity-transform legs). Adopt
    # that evidence only for complete, unchanged current cue groups.
    explicit = {}
    for e in events:
        pos = get_pos(e.text)
        if pos is not None and opaque_text_effect_state(e.state) and unrotated_text_state(e.state):
            explicit.setdefault((text_cue_lane(e,pos,e.state),e.start,e.end),[]).append(e)
    for members in explicit.values():
        evidence = [provenance.get(e.source_index,[]) for e in members]
        if not all(len(rs) == 1 and rs[0].base.text == e.text and rs[0].phase_core is not None
                   and e.start_s <= rs[0].phase_core[0] < rs[0].phase_core[1] <= e.end_s
                   for e,rs in zip(members,evidence)):
            continue
        cores = [rs[0].phase_core for rs in evidence]
        xs = [pos[0] for rs in evidence for piece,word,pos in rs[0].pieces]
        if not xs:
            continue
        core = (min(c[0] for c in cores),max(c[1] for c in cores))
        identity = tuple(sorted(e.source_index for e in members))
        candidates[identity] = CueFadeFamily(tuple(members),core,(min(xs),max(xs)))
    claims = collections.Counter(index for identity in candidates for index in identity)
    return [family for identity,family in candidates.items()
            if all(claims[index] == 1 for index in identity)]



def _faded_cue_slot(e: Event, pos: tuple[float,float]) -> tuple | None:
    """Identify literal font spans and layout at the original fragment anchor."""
    e = without_inert_spacing_tail(e)
    spans = literal_font_spans(e)
    if not spans or any(re.search(r'\\[Nn]|[\r\n]',text) for text,font in spans):
        return None
    # Outer whitespace does not identify a glyph; internal spaces do.
    spans = list(spans)
    spans[0] = (spans[0][0].lstrip(),spans[0][1])
    spans[-1] = (spans[-1][0].rstrip(),spans[-1][1])
    spans = tuple((text,font.casefold()) for text,font in spans if text)
    if not spans:
        return None
    return (tuple(round(v,4) for v in pos),spans,
            tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
                  ('fs','fscx','fscy','fsp','an','b','i','u','s','q','pbo','encoding')))



def _apply_faded_cue_families(context: FadedCueContext, cue_families: list[CueFadeFamily] | None) -> None:
    """Regroup only complete proved families, preserving separately painted cues."""
    for family in cue_families or ():
        members = family.members
        key = text_cue_lane(members[0],get_pos(members[0].text),members[0].state)
        timed = context.groups.get(key,{})
        ids = {e.source_index for e in members}
        if not ids <= {e.source_index for group in timed.values() for e in group}:
            continue
        start,end = min(e.start_s for e in members),max(e.end_s for e in members)
        timing = (round(start,2),round(end,2))
        # Do not absorb a separately painted caption into a proved family.
        if any(e.source_index not in ids for e in timed.get(timing,())):
            continue
        for old in list(timed):
            timed[old] = [e for e in timed[old] if e.source_index not in ids]
            if not timed[old]:
                del timed[old]
        timed[timing] = list(members)
        context.family_proofs[key,timing] = (*family.core,*family.xspan)



def _find_faded_cue_collisions(groups: dict) -> tuple[list,set]:
    """Find isolated consecutive overlaps before inspecting source overrides."""
    # Examine source overrides only for boundaries involved in a collision.
    # This avoids another expensive state-parsing pass over large animations.
    pairs = []
    wanted = set()
    for key,timed in groups.items():
        ordered = sorted(timed)
        previous_end = float('-inf')
        for i,(start,end) in enumerate(ordered[:-1]):
            next_start,next_end = ordered[i+1]
            if (start < next_start < end < next_end and
                    previous_end <= next_start and
                    (i+2 == len(ordered) or ordered[i+2][0] >= end)):
                pairs.append((key,(start,end),(next_start,next_end)))
                wanted.update(((key,0,start),(key,1,end),
                               (key,0,next_start),(key,1,next_end)))
            previous_end = max(previous_end,end)
    return pairs,wanted



def _parse_faded_source_evidence(e: Event, forbidden: set) -> tuple | None:
    """Require one finite source fade and stationary opaque fragment identity."""
    tokens = event_override_tokens(e)
    fades = [value for tag,value in tokens if tag == 'fad']
    if (len(fades) != 1 or not fades[0].startswith('(') or not fades[0].endswith(')') or
            any(tag in forbidden for tag,value in tokens)):
        return None
    try:
        fade_in,fade_out = [float(v) / 1000 for v in fades[0].strip('()').split(',')]
    except ValueError:
        return None
    # A final syllable may begin partway through the cue-wide fade tail.
    # Its nominal fade can exceed this phase's duration; the complete row
    # must still agree on a positive non-fading cue interval below.
    if not all(math.isfinite(v) and v >= 0 for v in (fade_in,fade_out)):
        return None
    pos = get_pos(e.text)
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    if (pos is None or not opaque_text_effect_state(state) or
            not unrotated_text_state(state)):
        return None
    key = text_cue_lane(e,pos,state)
    identity = _faded_cue_slot(dataclass_replace(e,state=state,continuation=evaluated.continuation),pos)
    if identity is None:
        return None
    return key,identity,fade_in,fade_out



def _collect_faded_cue_evidence(source_events: dict[int,Event], wanted: set) -> FadedCueEvidence:
    """Inspect only collision boundaries, preferring complete shadow-fade proofs."""
    evidence = FadedCueEvidence({},set())
    families = {key[:5] for key,phase,time in wanted}
    boundaries = {(key[:5],phase,time) for key,phase,time in wanted}
    forbidden = {'t','move','clip','iclip','org','fade','k','kf','ko','kt'}
    for e in source_events.values():
        family = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
        start,end = round(e.start_s,2),round(e.end_s,2)
        if (e.kind != 'Dialogue' or _faded_cue_is_scrolling(e) or family not in families or
                r'\fad(' not in e.text.lower() or
                (family,0,start) not in boundaries and (family,1,end) not in boundaries):
            continue
        shadow_core = shadow_lyric_fade_core(e)
        if shadow_core is not None:
            state,core_start,core_end = shadow_core
            pos = get_pos(e.text)
            key = text_cue_lane(e,pos,state)
            identity = _faded_cue_slot(dataclass_replace(e,state=state,continuation=OverrideContinuation()),pos)
            if identity is not None:
                for phase,time,core in ((0,start,core_start),(1,end,core_end)):
                    phase_key = (key,phase,time)
                    if phase_key in wanted:
                        evidence.phase_slots.setdefault(phase_key,{}).setdefault(identity,set()).add(round(core,2))
                        evidence.shadow_phases.add(phase_key)
            continue
        source = _parse_faded_source_evidence(e,forbidden)
        if source is None:
            continue
        key,identity,fade_in,fade_out = source
        for phase,time,fade,core in ((0,start,fade_in,start+fade_in),
                                     (1,end,fade_out,end-fade_out)):
            phase_key = (key,phase,time)
            if fade > 0 and phase_key in wanted:
                evidence.phase_slots.setdefault(phase_key,{}).setdefault(identity,set()).add(round(core,2))
    return evidence



def _prove_faded_source_core(evidence: FadedCueEvidence, key: tuple, timing: tuple,
                              identities: list) -> tuple | None:
    """Require complete unambiguous entrances and tails for the fully visible row."""
    unique = set(identities)
    entrance = evidence.phase_slots.get((key,0,timing[0]),{})
    tail = evidence.phase_slots.get((key,1,timing[1]),{})
    if (None in unique or len(unique) != len(identities) or
            unique != entrance.keys() or unique != tail.keys()):
        return None
    starts = set().union(*entrance.values())
    ends = set().union(*tail.values())
    shadow_pair = ((key,0,timing[0]) in evidence.shadow_phases and
                   (key,1,timing[1]) in evidence.shadow_phases)
    if shadow_pair:
        # Staggered reveal endpoints can differ between letters. Every
        # glyph still needs one unambiguous entrance and tail; protect the
        # interval during which the complete row is fully visible.
        if any(len(v) != 1 for v in (*entrance.values(),*tail.values())):
            return None
    elif len(starts) != 1 or len(ends) != 1:
        return None
    core_start,core_end = (max(starts),min(ends)) if shadow_pair else (next(iter(starts)),next(iter(ends)))
    xs = [identity[0][0] for identity in identities]
    return ((core_start,core_end,min(xs),max(xs))
                          if timing[0] < core_start < core_end < timing[1] else None)



def _prove_faded_cue_core(context: FadedCueContext, evidence: FadedCueEvidence,
                           key: tuple, timing: tuple) -> tuple | None:
    """Prefer family and ordered phase cores before fragment source-fade proofs."""
    members = context.groups[key][timing]
    if (key,timing) in context.family_proofs:
        return context.family_proofs[key,timing]
    if len(members) == 1:
        e = members[0]
        row_evidence = context.provenance.get(e.source_index,[])
        if (len(row_evidence) == 1 and row_evidence[0].phase_core is not None and
                row_evidence[0].base.text == e.text):
            row = row_evidence[0]
            start,end = row.phase_core
            xs = [pos[0] for piece,text,pos in row.pieces]
            return ((start,end,min(xs),max(xs))
                if timing[0] < start < end < timing[1] else None)
    identities = []
    for e in members:
        row_evidence = context.provenance.get(e.source_index,[])
        if len(row_evidence) > 1 or row_evidence and row_evidence[0].base.text != e.text:
            identities.append(None)
        elif row_evidence:
            identities.extend(_faded_cue_slot(piece,pos) for piece,text,pos in row_evidence[0].pieces)
        else:
            identities.append(_faded_cue_slot(e,get_pos(e.text)))
    return _prove_faded_source_core(evidence,key,timing,identities)



def _select_readable_core_handoff(left: tuple, right: tuple, a: tuple,
                                   b: tuple) -> float | None:
    """Choose a representable centisecond inside both the collision and protected gap."""
    if a[1] > b[0]:return None
    # A handoff inside both the collision and the gap between stable cores
    # preserves every stable frame and all exposure outside the collision.
    low,high = max(right[0],a[1]),min(left[1],b[0])
    if low > high:
        return None
    # ASS cue boundaries have centisecond precision. A rounded midpoint
    # outside this interval would cut a protected frame.
    first,last = math.ceil(low*100-1e-7),math.floor(high*100+1e-7)
    if first > last:
        return None
    boundary = min(last/100,max(first/100,round((low+high)/2,2)))
    return boundary



def _select_faded_cue_handoff(left: tuple, right: tuple, a: tuple | None,
                               b: tuple | None) -> float | None:
    """Require shared row extent before the common readable-core clock proof."""
    if a is None or b is None or min(a[3],b[3]) < max(a[2],b[2]):return None
    return _select_readable_core_handoff(left,right,a,b)



def synchronize_faded_cue_handoffs(context: FadedCueContext, pairs: list,
                                   proven: dict) -> dict:
    """Choose shared safe boundaries for uniquely paired separate text lanes.

    Touching captions can supply an authored boundary. Overlapping lanes can
    instead share the intersection of their source-protected handoff windows.
    All evidence is borrowed; ambiguous associations keep independent timing.
    """
    records = {}
    def caption(key,timing):
        members = context.groups[key][timing]
        if len(members) != 1:
            return None
        e = members[0]
        size = float(e.state.get('fs',20))
        literal = OVERRIDE_RE.sub('',e.text).replace(r'\h',' ').strip()
        if (not math.isfinite(size) or size <= 0 or
                not all(math.isfinite(v) for v in get_pos(e.text)) or
                not literal or re.search(r'\\[Nn]|[\r\n]',literal) or
                e.state.get('p',0) or
                any(tag in {'move','t','clip','iclip','org','fade','fad','k','kf','ko','kt','p','r'}
                    for tag,value in event_override_tokens(e))):
            return None
        evidence = context.provenance.get(e.source_index,[])
        if len(evidence) > 1 or evidence and evidence[0].base.text != e.text:
            return None
        xs = [anchor[0] for piece,word,anchor in evidence[0].pieces] if evidence else [get_pos(e.text)[0]]
        if not xs or not all(math.isfinite(x) for x in xs):
            return None
        return literal,(min(xs),max(xs)),size
    for key,left,right in pairs:
        a,b = proven.get((key,left)),proven.get((key,right))
        if _select_faded_cue_handoff(left,right,a,b) is None:
            continue
        outgoing,incoming = caption(key,left),caption(key,right)
        if outgoing is None or incoming is None or outgoing[0] == incoming[0]:
            continue
        low = math.ceil(max(right[0],a[1])*100-1e-7)
        high = math.floor(min(left[1],b[0])*100+1e-7)
        records[key,left,right] = (low,high,a[:2],b[:2],outgoing,incoming)
    anchors = {}
    for key,timed in context.groups.items():
        ordered = sorted(timed)
        for left,right in zip(ordered,ordered[1:]):
            if left[1] != right[0]:
                continue
            outgoing,incoming = caption(key,left),caption(key,right)
            if outgoing is None or incoming is None or outgoing[0] == incoming[0]:
                continue
            boundary = round(left[1]*100)
            if any(t not in (left,right) and t[0] <= boundary/100 <= t[1] for t in ordered):
                continue
            anchors[key,left,right] = (boundary,boundary,left,right,outgoing,incoming)
    def related(one,two):
        key,left,right = one
        other,other_left,other_right = two
        if key == other:
            return False
        a,b = records[one],(records.get(two) or anchors[two])
        size = max(a[4][2],a[5][2],b[4][2],b[5][2])
        # Require distinct visual rows, including top/bottom translations.
        if not math.isfinite(size) or size <= 0 or abs(key[5]-other[5]) < .5*size:
            return False
        if max(a[0],b[0]) > min(a[1],b[1]):
            return False
        for phase in (2,3):
            if max(a[phase][0],b[phase][0]) >= min(a[phase][1],b[phase][1]):
                return False
            if two in anchors and not (b[phase][0] <= a[phase][0] and a[phase][1] <= b[phase][1]):
                return False
            x,y = a[phase+2][1],b[phase+2][1]
            if min(x[1],y[1]) < max(x[0],y[0]):
                return False
        return True
    neighbors = {identity:[] for identity in records}
    for one in records:
        for two in (*records,*anchors):
            if related(one,two):
                neighbors[one].append(two)
    result,visited = {},set()
    for identity in records:
        if identity in visited:
            continue
        component,pending = set(),[identity]
        while pending:
            one = pending.pop()
            if one in component:
                continue
            component.add(one)
            pending.extend(two for two in neighbors[one] if two in records)
        visited.update(component)
        references = {two for one in component for two in neighbors[one] if two in anchors}
        all_items = component | references
        # At most one transition per lane; conflicting authored boundaries
        # or competing overlap pairs cannot establish a common handoff.
        if len({item[0] for item in all_items}) != len(all_items):
            continue
        # An authored transition must also be unique to this component.
        if any(other not in component and ref in linked
               for ref in references for other,linked in neighbors.items()):
            continue
        values = [records.get(item) or anchors[item] for item in all_items]
        low,high = max(v[0] for v in values),min(v[1] for v in values)
        if low > high or len(all_items) < 2:
            continue
        boundary = min(high,max(low,round((low+high)/2)))/100
        result.update({item:boundary for item in component})
    return result



def _trim_owned_cue_backing(events: list[Event], rows: list[TextRow],
                             replacements: dict[int,dict]) -> None:
    """Share a proved foreground handoff with its exact retained paint copies.

    Use ownership returned by the stack coordinator, including complete row
    successors. Neither similar text nor nearby timing can establish ownership.
    Ambiguous parents, incomplete joined paint rows and changed copies remain
    untouched. This only adds timing successors to the caller-owned buffer.
    """
    current = {e.source_index:e for e in events}
    owners,snapshots,provenance = {},{},{}
    for row in rows:
        if row.virtual or row.base.source_index not in current:
            continue
        parent = current[row.base.source_index]
        if row.base.text != parent.text:
            continue
        provenance.setdefault(parent.source_index,[]).append(row)
        for paint in row.owned_backing:
            owners.setdefault(paint.source_index,set()).add(parent.source_index)
            snapshots.setdefault(paint.source_index,[]).append(paint)
    def owner(piece):
        # Source-backed paint may already have acquired boundary phases;
        # timing is deliberately separate from its exact rendered identity.
        claims = owners.get(piece.source_index,set())
        copies = snapshots.get(piece.source_index,[])
        return (next(iter(claims)) if len(claims) == 1 and copies and
                all(piece.fields()[:1]+piece.fields()[3:] == p.fields()[:1]+p.fields()[3:]
                    for p in copies) else None)
    for paint in events:
        parent = owner(paint)
        parents = [parent] if parent is not None else []
        if not parents:
            evidence = provenance.get(paint.source_index,[])
            if len(evidence) == 1 and evidence[0].pieces:
                parents = [owner(piece) for piece,word,pos in evidence[0].pieces]
        if not parents or any(p is None for p in parents) or not any(p in replacements for p in parents):
            continue
        parents = set(parents)
        # A joined backing may have several word owners, but all must still
        # belong to the same cue before and after the proposed handoff.
        before = {(current[p].start,current[p].end) for p in parents}
        after = {(replacements.get(p,{}).get('start_s',current[p].start_s),
                  replacements.get(p,{}).get('end_s',current[p].end_s)) for p in parents}
        if len(before) != 1 or len(after) != 1:
            continue
        start,end = next(iter(after))
        start,end = max(paint.start_s,start),min(paint.end_s,end)
        if start >= end:
            continue
        changes = replacements.setdefault(paint.source_index,{})
        if start > paint.start_s:
            changes.update(start=format_time(start),start_s=start)
        if end < paint.end_s:
            changes.update(end=format_time(end),end_s=end)



def trim_faded_cue_overlaps(events: list[Event], rows: list[TextRow],
                            source_events: dict[int,Event], *,
                            cue_families: list[CueFadeFamily] | None = None) -> tuple[list[Event],int]:
    """Give consecutive static rows a clean handoff within their source fades.

    Reconstructed rows supply their original fragment anchors. Every retained
    fragment, including separate font spans, must match complete source fade
    entrances and tails at the cue's boundaries. Matched fragment phases can
    instead supply their complete ordered word-activation interval. Only rows
    whose protected cores are disjoint qualify. Ambiguous or incomplete groups,
    simultaneous cores and independent positions keep their original timing.
    Consume the caller's adopted row successors without updating their cores
    or historical fragment intervals. Only returned event timing changes.
    """
    provenance: dict[int,list[TextRow]] = {}
    for row in rows:
        if not row.virtual:
            provenance.setdefault(row.base.source_index,[]).append(row)
    groups: dict[tuple,dict[tuple,list[Event]]] = {}
    for e in events:
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or _faded_cue_is_scrolling(e) or pos is None or
                not opaque_text_effect_state(e.state) or not unrotated_text_state(e.state)):
            continue
        timing = (round(e.start_s,2),round(e.end_s,2))
        groups.setdefault(text_cue_lane(e,pos,e.state),{}).setdefault(timing,[]).append(e)
    context = FadedCueContext(provenance,groups,{})
    _apply_faded_cue_families(context,cue_families)
    pairs,wanted = _find_faded_cue_collisions(context.groups)
    if not pairs:
        return events,0
    evidence = _collect_faded_cue_evidence(source_events,wanted)
    proven = {}
    candidates = {(key,timing) for key,left,right in pairs for timing in (left,right)}
    for key,timing in candidates:
        proven[key,timing] = _prove_faded_cue_core(context,evidence,key,timing)

    synchronized = synchronize_faded_cue_handoffs(context,pairs,proven)
    replacements = {}
    trimmed = 0
    for key,left,right in pairs:
        a,b = proven.get((key,left)),proven.get((key,right))
        boundary = synchronized.get((key,left,right),_select_faded_cue_handoff(left,right,a,b))
        if boundary is None:
            continue
        for timing,time_field in ((left,'end'),(right,'start')):
            for e in context.groups[key][timing]:
                changes = replacements.setdefault(e.source_index,{})
                # A staggered family contains fragments that can already end
                # before (or begin after) the common handoff. Never extend them.
                value = min(e.end_s,boundary) if time_field == 'end' else max(e.start_s,boundary)
                changes.update({time_field:format_time(value),time_field+'_s':value})
        trimmed += 1
    _trim_owned_cue_backing(events,rows,replacements)
    return [replace_event(e,**replacements[e.source_index])
            if e.source_index in replacements else e for e in events],trimmed
