"""Complete source glyph lifecycles, readable paint and atomic row ownership."""
from __future__ import annotations

import collections
import math
import re
import statistics
import unicodedata
from dataclasses import dataclass, replace as dataclass_replace

from .ass_overrides import (
    tokenize_override,
    apply_override,
    OVERRIDE_RE,
    DEFAULT_STATE,
)
from .caption_clearance import _glyph_replacement_row_is_clear
from .caption_geometry import (
    NUM,
    POS_RE,
    get_pos,
    inline_layout_key,
    text_height,
    text_layout_key,
)
from .caption_rendering import (
    CAPTION_PAINT_TAGS,
    _source_caption_paint,
    render_simplified_caption,
    render_tag,
    render_merged_caption,
)
from .effect_validation import parse_effect_transform
from .event_model import Event
from .event_operations import (
    event_override_tokens,
    event_evaluation,
    replace_event,
    _faded_cue_is_scrolling,
)
from .font_metrics import FontMetrics
from .font_reporting import FontProcessingReport
from .glyph_placement import (
    authored_glyph_positions,
    matches_authored_glyph_positions,
)
from .row_evidence import (
    TextRow,
    TextPhaseRowsResult,
)
from .row_fitting import recover_font_row
from .static_selection import (
    unrotated_text_state,
    select_static_state,
)
from .subtitle_document import format_time


@dataclass(frozen=True)
class GlyphPhaseLife:
    """One source-proved glyph position through its complete paint lifecycle."""
    members: tuple[Event,...]
    pose: Event
    literal: str
    start_s: float
    end_s: float
    core: tuple[float,float]
    # A syllable can bridge several glyphs. Its whole source family must be
    # owned by the completed row before any shared replacement is consumed.
    required_members: frozenset[int] = frozenset()


def _index_glyph_phase_slots(parsed: dict[int,Event], metric: FontMetrics,
                              max_piece_duration: float,
                              font_report: FontProcessingReport | None) -> tuple[list,dict,list]:
    """Normalize exact-font anchors, retaining rejected nearby text as blockers."""
    profiles = {}
    for e in parsed.values():
        if e.kind != 'Dialogue' or e.duration <= 0:
            continue
        literal = OVERRIDE_RE.sub('',e.text)
        if len(literal) != 1 or literal.isspace():
            continue
        profile = profiles.setdefault((e.style,e.name),[0,0])
        profile[0] += bool(re.search(r'\\fad\s*\(',e.text,re.I))
        profile[1] += e.duration <= max_piece_duration+1e-6
    families = {key for key,(fades,frames) in profiles.items() if fades >= 8 and frames >= 12}
    families.update((e.style,e.name) for e in parsed.values() if e.kind == 'Dialogue' and
                    re.search(r'\\t\s*\(',e.text) and re.search(r'\\fsc[xy]',e.text))
    slots,spatial,obstacles,widths,endpoints = [],{}, {},{},[]
    forbidden = {'t','move','fade','clip','iclip','org','p','r','k','kf','ko','kt'}
    for source in sorted(parsed.values(),key=lambda e:(e.start_s,e.end_s,e.source_index)):
        family = (source.style,source.name)
        if family not in families or source.kind != 'Dialogue' or source.duration <= 0:
            continue
        literal = OVERRIDE_RE.sub('',source.text)
        if not literal.strip():
            continue
        evaluated = event_evaluation(source)
        e = dataclass_replace(source,state=evaluated.formatting,continuation=evaluated.continuation)
        pos = get_pos(e.text)
        height = text_height(e)
        alignment = int(e.state.get('an',5))
        if not math.isfinite(height) or height <= 0 or alignment not in range(1,10):
            continue
        if pos is None:
            obstacles.setdefault(family,[]).append([e,None,height])
            continue
        if any(not math.isfinite(v) for v in pos):
            continue
        # Rejected geometry is still evidence of a possible missing glyph.
        approximate = (pos[0],pos[1]+((alignment-1)//3-1)*height/2)
        obstacle = [e,approximate,height]
        obstacles.setdefault(family,[]).append(obstacle)
        prefix = re.match(r'(?:\{[^}]*\})*',e.text).end()
        tokens = event_override_tokens(e)
        if (len(literal) != 1 or literal.isspace() or unicodedata.combining(literal) or
                unicodedata.bidirectional(literal) in {'R','AL','AN'} or
                OVERRIDE_RE.search(e.text,prefix) or _faded_cue_is_scrolling(e) or
                any(tag in forbidden for tag,value in tokens) or
                not unrotated_text_state(e.state) or
                any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay','fsp','pbo')) or
                any(not math.isfinite(e.state.get(k,0)) or e.state.get(k,0) <= 0
                    for k in ('fs','fscx','fscy')) or
                e.state.get('borderstyle',1) != 1 or
                str(e.state.get('fn','')).startswith('@') or
                not e.layer.lstrip('-').isdigit()):
            continue
        fade_values = [value for tag,value in tokens if tag=='fad']
        fade = None
        if fade_values:
            if len(fade_values) != 1 or not re.fullmatch(r'\(\s*'+NUM+r'\s*,\s*'+NUM+r'\s*\)',fade_values[0]):
                continue
            fade = tuple(float(v)/1000 for v in fade_values[0][1:-1].split(','))
            if any(not math.isfinite(v) or v < 0 for v in fade) or (fade[0]>0)==(fade[1]>0):
                continue
        elif e.duration > max_piece_duration+1e-6:
            continue
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,
               tuple((k,v) for k,v in text_layout_key(e) if k != 'an'))
        width_key = (key,literal)
        if width_key not in widths:
            face = metric.matching_face(str(e.state.get('fn','')),e.state.get('b',0),bool(e.state.get('i',0)))
            factor = metric.ass_em_scale(face) if face is not None else None
            width = None
            if face is not None and factor is not None and ord(literal) in face.cmap:
                try:
                    width = metric.measure(face,literal,bool(e.state.get('kerning',False)))*e.state.get('fs',20)*e.state.get('fscx',100)/100/1024*factor
                except (OSError,ValueError,RuntimeError):
                    pass
            widths[width_key] = width
            if width is None and font_report is not None:
                font_report.missing_families.add(str(e.state.get('fn','')))
        width = widths[width_key]
        if width is None or not math.isfinite(width) or width <= 0:
            continue
        center = (pos[0]+(.5-((alignment-1)%3)/2)*width,approximate[1])
        obstacle[1] = center
        tags = ''.join('\\'+tag+value for tag,value in tokens if tag not in {'pos','an','a'})
        canonical = replace_event(e,text='{'+tags+r'\an5'+('\\pos('+','.join(format(v,'.12g') for v in center)+')')+'}'+literal)
        if fade is not None:
            endpoints.append((canonical,fade))
        unit = .06*height
        cell = (math.floor(center[0]/unit),math.floor(center[1]/unit))
        candidates = {i for dx in (-1,0,1) for dy in (-1,0,1)
                      for i in spatial.get((key,literal,cell[0]+dx,cell[1]+dy),[])
                      if all(abs(a-b) <= unit+1e-6 for a,b in zip(center,get_pos(slots[i][0][0].text))) and
                      (any(other_fade is not None and other_fade[0] and
                           other.layer != canonical.layer and
                           abs(other.start_s-canonical.start_s) <= 1e-6 and
                           abs(other.end_s-canonical.end_s) <= 1e-6 and
                           all(abs(a-b) <= .001*height+1e-6 for a,b in zip(center,get_pos(other.text)))
                           for other,other_fade in slots[i])
                       if fade is not None and fade[0] else
                       any(abs(other.end_s-canonical.start_s) <= 1e-6 and
                           (other_fade is None or other_fade[1] == 0)
                           for other,other_fade in slots[i]))}
        if len(candidates) > 1:
            continue
        if candidates:
            index = candidates.pop()
        else:
            if fade is None or not fade[0]:
                continue
            index = len(slots);slots.append([])
            spatial.setdefault((key,literal,*cell),[]).append(index)
        slots[index].append((canonical,fade))
    return slots,obstacles,endpoints


def _profile_glyph_replacement(source: Event) -> tuple[Event,dict,float] | None:
    """Recognize one stationary readable syllable shrinking into a fading exit."""
    literal = OVERRIDE_RE.sub('',source.text)
    if (source.kind != 'Dialogue' or source.duration <= 0 or not literal or
            any(c.isspace() or unicodedata.combining(c) or
                unicodedata.bidirectional(c) in {'R','AL','AN'} for c in literal) or
            '\\' in literal or _faded_cue_is_scrolling(source) or not source.layer.lstrip('-').isdigit()):
        return None
    evaluated = event_evaluation(source)
    e = dataclass_replace(source,state=evaluated.formatting,continuation=evaluated.continuation)
    state = e.state
    if (get_pos(e.text) is None or inline_layout_key(e) or not unrotated_text_state(state) or
            state.get('an') != 5 or state.get('borderstyle',1) != 1 or
            any(k in state for k in ('clip','iclip','org')) or
            any(abs(state.get(k,0)) > .001 for k in ('fax','fay','fsp','p','pbo')) or
            any(abs(state.get(k,state.get('shad',0))) > .001 for k in ('xshad','yshad')) or
            not all(math.isfinite(v) for v in get_pos(e.text)) or
            not 0 <= state.get('1a',0) < 128):
        return None
    final = state.copy();continuation = e.continuation;scaled = False;fade_begin = None
    for tag,value in event_override_tokens(e):
        if tag in {'move','fad','fade','r','k','kf','ko','kt'}:
            return None
        if tag != 't':
            continue
        # A target-free transform has no visual effect (including template
        # annotations with unused timing); it supplies no evidence either.
        if not tokenize_override(value[1:-1]):
            continue
        transform = parse_effect_transform(value,e.duration,
            {'fscx','fscy','alpha','1a','3a','4a','blur','be'},allow_instant=True)
        if transform is None:
            return None
        begin,_,changes = transform
        previous = final.copy()
        for name,argument in changes:
            continuation = apply_override(final,name,argument,e.styles,e.defaults,continuation)
        for axis in ('fscx','fscy'):
            a,b = previous.get(axis,100),final.get(axis,100)
            if not all(math.isfinite(v) and v > 0 for v in (a,b)) or b > a+.001:
                return None
            scaled |= b < a-.001
        if final.get('1a',0) < previous.get('1a',0):
            return None
        if final.get('1a',0) > previous.get('1a',0):
            fade_begin = e.start_s+begin/1000
    if not scaled or final.get('1a',0) < 254:
        return None
    return e,final,fade_begin


def _prove_replacement_glyph_lives(endpoints: list, parsed: dict[int,Event],
                                  metric: FontMetrics) -> list[GlyphPhaseLife]:
    """Bridge complete letter stacks through uniquely owned whole-syllable phases.

    Only original source evidence is used. Shared pulse ownership is provisional
    until the ordinary whole-row font, obstacle and competing-claim proofs pass.
    """
    def family(e):
        return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,
                tuple((k,v) for k,v in text_layout_key(e) if k not in {'an','fscx','fscy'}))
    entries,tails = {},{}
    for e,fade in endpoints:
        if e.state.get('1a',0) != 0 or e.state.get('3a',0) != 0:
            continue
        key = family(e)
        if fade[0]:
            entries.setdefault(key,[]).append((e,fade))
        else:
            tails.setdefault((key,e.layer,get_pos(e.text),OVERRIDE_RE.sub('',e.text)),[]).append((e,fade))
    profiles,cohorts = [],{}
    for source in parsed.values():
        # Avoid parsing unrelated ordinary text and already sampled frames.
        if not re.search(r'\\t\s*\(',source.text) or not re.search(r'\\fsc[xy]',source.text):
            continue
        profile = _profile_glyph_replacement(source)
        if profile is None:
            continue
        profiles.append(profile)
        pulse,final,fade_begin = profile;key = family(pulse);pos = get_pos(pulse.text)
        literal = OVERRIDE_RE.sub('',pulse.text);groups = {}
        for entry,fade in entries.get(key,[]):
            anchor = get_pos(entry.text);height = text_height(entry)
            if (abs(entry.end_s-pulse.start_s) > .011 or
                    abs(anchor[1]-pos[1]) > .02*height):
                continue
            word = OVERRIDE_RE.sub('',entry.text)
            options = [(tail,exit_fade) for tail,exit_fade in tails.get((key,entry.layer,anchor,word),[])
                       if pulse.start_s-.011 <= tail.start_s <= pulse.end_s+.011 and
                       tail.end_s >= fade_begin-.011 and
                       text_layout_key(entry) == text_layout_key(tail)]
            if len(options) != 1:
                continue
            tail,exit_fade = options[0]
            groups.setdefault((entry.start_s,tail.end_s,tail.start_s,entry.layer),[]).append(
                (entry,tail,fade,exit_fade))
        stacks = []
        for group,pairs in groups.items():
            pairs.sort(key=lambda p:get_pos(p[0].text)[0])
            xs = [get_pos(p[0].text)[0] for p in pairs]
            if (''.join(OVERRIDE_RE.sub('',p[0].text) for p in pairs) != literal or
                    len(set(xs)) != len(xs) or int(group[-1]) >= int(pulse.layer) or
                    not matches_authored_glyph_positions(metric,final,xs,literal,pos[0],.05*text_height(pairs[0][0]))):
                continue
            stacks.append((group,pairs))
        if (not stacks or len({g[-1] for g,p in stacks}) != len(stacks) or
                len({g[:3] for g,p in stacks}) != 1 or
                len({tuple(get_pos(p[0].text) for p in pairs) for g,pairs in stacks}) != 1):
            continue
        for group,pairs in stacks:
            cohort = cohorts.setdefault((key,group[0],group[1],pos[1]),{})
            cohort.setdefault(group[-1],{}).update({p[0].source_index:p for p in pairs})

    # Complete interior pairs prove cue bounds and the observed before/after
    # paint relation. Boundary syllables may legitimately have no entrance or
    # no post-highlight hold; borrow that relation only when it is unambiguous.
    proposals = []
    paint_tags = set(CAPTION_PAINT_TAGS)
    def paint_key(state):
        return tuple((k,state.get(k,DEFAULT_STATE.get(k))) for k in sorted(paint_tags))
    for pulse,final,fade_begin in profiles:
        pos = get_pos(pulse.text);literal = OVERRIDE_RE.sub('',pulse.text)
        expected = authored_glyph_positions(metric,final,literal,pos[0],.05*text_height(pulse))
        if expected is None:
            continue
        for (key,start,end,y),layers in cohorts.items():
            if (family(pulse) != key or not start-.011 <= pulse.start_s < end or
                    abs(y-pos[1]) > .02*text_height(pulse)):
                continue
            stacks = [];donors = set()
            for layer,known in sorted(layers.items(),key=lambda item:int(item[0])):
                if int(layer) >= int(pulse.layer):
                    break
                palette = {}
                for entry,tail,ingress,exit_fade in known.values():
                    palette.setdefault(paint_key(entry.state),{}).setdefault(paint_key(tail.state),tail.state)
                    donors.update((entry.source_index,tail.source_index))
                reference = next(iter(known.values()))
                pairs = []
                for char,x in expected:
                    radius = .075*text_height(reference[0])
                    before = [(e,f) for e,f in entries.get(key,[]) if e.layer == layer and
                              e.start_s == start and abs(e.end_s-pulse.start_s) <= .011 and
                              OVERRIDE_RE.sub('',e.text) == char and
                              abs(get_pos(e.text)[0]-x) <= radius and abs(get_pos(e.text)[1]-y) <= .001]
                    after = [(e,f) for (k,l,anchor,word),phases in tails.items()
                             if k == key and l == layer and word == char and
                             abs(anchor[0]-x) <= radius and abs(anchor[1]-y) <= .001
                             for e,f in phases if e.end_s == end and
                             pulse.start_s-.011 <= e.start_s <= pulse.end_s+.011]
                    if (len(before)>1 or len(after)>1 or not before and not after or
                            not before and abs(pulse.start_s-start)>.011 or
                            not after and abs(fade_begin-end)>.011):
                        break
                    entry,ingress = before[0] if before else (None,reference[2])
                    tail,exit_fade = after[0] if after else (None,reference[3])
                    if entry is not None and tail is not None and (
                            get_pos(entry.text) != get_pos(tail.text) or
                            text_layout_key(entry) != text_layout_key(tail)):
                        break
                    if tail is not None:
                        state = tail.state
                    else:
                        choices = palette.get(paint_key(entry.state),{})
                        if len(choices) != 1:
                            break
                        selected = next(iter(choices.values()))
                        state = {**entry.state,**{k:selected[k] for k in paint_tags if k in selected}}
                    pairs.append((entry,tail,ingress,exit_fade,state))
                else:
                    stacks.append((layer,pairs))
                    continue
                break
            if len(stacks) != len(layers):
                continue
            # Every plane must describe the same letters and anchors. Shared
            # source IDs authorize only atomic whole-cue ownership downstream.
            anchors = [tuple(get_pos((p[1] or p[0]).text) for p in pairs) for layer,pairs in stacks]
            if len(set(anchors)) != 1:
                continue
            members = tuple(e for layer,pairs in stacks for p in pairs for e in p[:2] if e is not None)+(pulse,)
            required = frozenset(donors)|frozenset(e.source_index for e in members)
            lives = []
            for i,(entry,tail,ingress,exit_fade,state) in enumerate(stacks[-1][1]):
                supports = [pairs[i][4] for layer,pairs in stacks]
                proof = _source_caption_paint(state,supports)
                if proof is None:
                    break
                source = tail or entry
                text = render_simplified_caption(state,expected[i][0],source_paint=proof,measurement=source.measurement)
                # Keep original anchor precision until the whole-row advance
                # fit finishes; this is an evidence pose, not final output.
                anchor = get_pos(source.text)
                text = POS_RE.sub(lambda _: '\\pos('+','.join(format(v,'.12g') for v in anchor)+')',text,count=1)
                pose = replace_event(source,text=text,effect='')
                owned = tuple(e for layer,pairs in stacks for e in pairs[i][:2] if e is not None)+(pulse,)
                core = (min(entry.end_s,start+ingress[0]) if entry is not None else start,
                        max(tail.start_s,end-exit_fade[1]) if tail is not None else fade_begin)
                if core[1]-core[0] < .32-1e-6:
                    break
                lives.append(GlyphPhaseLife(owned,pose,expected[i][0],start,max(end,pulse.end_s),core,required))
            else:
                proposals.append((frozenset(e.source_index for e in members),lives))
    claims = collections.Counter(i for ids,lives in proposals for i in ids)
    return [life for ids,lives in proposals if all(claims[i] == 1 for i in ids) for life in lives]


def _prove_glyph_phase_lives(slots: list, max_piece_duration: float) -> list[GlyphPhaseLife]:
    """Walk unique touching entrance/frame/exit paths, then own their paint stack."""
    lives = []
    for slot in slots:
        starts = {}
        for e,fade in slot:
            starts.setdefault((e.layer,round(e.start_s,6)),[]).append((e,fade))
        paths = {}
        for entry,fade in slot:
            if fade is None or not fade[0] or fade[1]:
                continue
            path = [entry];current = entry;exit_event = None;exit_fade = None
            while len(path) <= len(slot):
                following = starts.get((entry.layer,round(current.end_s,6)),[])
                if len(following) != 1:
                    break
                event,tail = following[0]
                if tail is not None:
                    if (tail[0] == 0 and tail[1] > 0 and
                            all(abs(a-b) <= .001*text_height(entry)+1e-6
                                for a,b in zip(get_pos(entry.text),get_pos(event.text)))):
                        path.append(event);exit_event,exit_fade = event,tail
                    break
                if event.duration > max_piece_duration+1e-6:
                    break
                path.append(event);current = event
            if exit_event is None or len(path)-2 < 1:
                continue
            start,end = entry.start_s,exit_event.end_s
            core = (min(entry.end_s,start+fade[0]),max(exit_event.start_s,end-exit_fade[1]))
            if core[1]-core[0] < .32-1e-6:
                continue
            paths.setdefault((start,end),[]).append((entry.layer,path,core))
        for (start,end),layers in paths.items():
            if len({layer for layer,path,core in layers}) != len(layers):
                continue
            readable = [p for p in layers if all(e.state.get('1a',0)<128 for e in p[1])]
            if not readable:
                continue
            foreground = max(readable,key=lambda p:int(p[0]))
            members = [e for layer,path,core in layers for e in path]
            claimed = {e.source_index for e in members}
            pulse_start,pulse_end = foreground[1][0].end_s,foreground[1][-1].start_s
            extra = [e for e,fade in slot if e.source_index not in claimed and
                     start < e.end_s and e.start_s < end]
            # Only short lower paint layers wholly inside the highlight may
            # be owned without their own complete entrance/exit path.
            if any(e.duration > max_piece_duration+1e-6 or int(e.layer) >= int(foreground[0]) or
                   e.start_s < pulse_start-1e-6 or e.end_s > pulse_end+1e-6 for e in extra):
                continue
            members += extra
            pose = foreground[1][0]
            positions = [get_pos(e.text) for e in members]
            if any(max(p[a] for p in positions)-min(p[a] for p in positions) > .12*text_height(pose)+1e-6 for a in (0,1)):
                continue
            # Readable saturated source intervals provide colour dwell. Fade
            # ramps cannot overweight a brief foreground against a long hold.
            paint_events = []
            for e in members:
                fades = [v for tag,v in event_override_tokens(e) if tag=='fad']
                a,b = e.start_s,e.end_s
                if fades:
                    ingress,tail = (float(v)/1000 for v in fades[0][1:-1].split(','))
                    a,b = min(b,a+ingress),max(a,b-tail)
                if b > a:
                    paint_events.append(replace_event(e,start_s=a,end_s=b,start=format_time(a),end=format_time(b)))
            paint = dict(select_static_state(pose.state,[],set(),pose.styles,pose.defaults,
                paint_events=paint_events,continuation=pose.continuation).state)
            contours = [e.state for e in members if e.state.get('3c')==paint.get('3c') and
                        e.state.get('3a',0)==0 and max(e.state.get(k,e.state.get('bord',0)) for k in ('xbord','ybord'))>0]
            if contours:
                paint.update(bord=2,xbord=2,ybord=2,**{'3a':0})
            tags = ''.join('\\'+tag+value for tag,value in event_override_tokens(pose) if tag!='fad')
            tags += ''.join(render_tag(k,paint[k]) for k in ('1c','3c','1a','3a','bord','xbord','ybord') if k in paint)
            chosen = replace_event(pose,text='{'+tags+'}'+OVERRIDE_RE.sub('',pose.text))
            lives.append(GlyphPhaseLife(tuple(members),chosen,OVERRIDE_RE.sub('',pose.text),start,end,foreground[2]))
    return lives


def reconstruct_glyph_lifecycles(parsed: dict[int,Event], metric: FontMetrics | None, *,
                                  max_piece_duration: float=.16,
                                  font_report: FontProcessingReport | None=None) -> TextPhaseRowsResult:
    """Replace only complete source-owned, exact-font letter phase rows.

    Geometry/timing determine membership independently of colour. Every glyph
    needs a readable entrance-to-exit path with explicit highlight frames.
    Unclaimed nearby content and competing rows reject atomic replacement.
    """
    events = list(parsed.values())
    if metric is None or not metric.available:
        return TextPhaseRowsResult(events,0,[],{})
    slots,obstacles,endpoints = _index_glyph_phase_slots(parsed,metric,max_piece_duration,font_report)
    lives = _prove_glyph_phase_lives(slots,max_piece_duration)
    lives += _prove_replacement_glyph_lives(endpoints,parsed,metric)
    groups = {}
    bands = {}
    for life in sorted(lives,key=lambda l:get_pos(l.pose.text)[1]):
        e = life.pose
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,text_layout_key(e))
        y = get_pos(e.text)[1]
        anchors = bands.setdefault(key,[])
        if not anchors or abs(y-anchors[-1]) > .02*text_height(e):
            anchors.append(y)
        groups.setdefault((key,len(anchors)-1),[]).append(life)
    runs = []
    for group in groups.values():
        run = []
        for life in sorted(group,key=lambda l:(l.start_s,get_pos(l.pose.text)[0],l.end_s)):
            if run:
                first,last = run[0],run[-1]
                x,y = get_pos(life.pose.text);lx,ly = get_pos(last.pose.text)
                height = text_height(first.pose)
                core_start = max(l.core[0] for l in run+[life]);core_end = min(l.core[1] for l in run+[life])
                if (x <= lx+.02*height or abs(y-ly) > .02*height or
                        life.end_s < last.end_s-.011 or core_end-core_start < .32-1e-6):
                    runs.append(run);run=[]
            run.append(life)
        if run:runs.append(run)
    proposals = []
    for run in runs:
        if len(run) < 4:
            continue
        ordered = [l.pose for l in run];fragments = [l.literal for l in run]
        replacement = any(l.required_members for l in run)
        fit = recover_font_row(metric,ordered,fragments,max_size_error=.05,
                               font_report=font_report,fit_scale=replacement)
        if fit is None:
            continue
        literal,center,sx,sy,alignment = fit
        core = (max(l.core[0] for l in run),min(l.core[1] for l in run))
        start,end = min(l.start_s for l in run),max(l.end_s for l in run)
        members = {e.source_index for l in run for e in l.members}
        if any(not life.required_members <= members for life in run):
            continue
        xs = [get_pos(e.text)[0] for e in ordered];y = statistics.median(get_pos(e.text)[1] for e in ordered);height=text_height(ordered[0])
        if any(e.source_index not in members and e.start_s < core[1] and e.end_s > core[0] and
               (pos is None or abs(pos[1]-y) <= .15*height and
                xs[0]-height <= pos[0] <= xs[-1]+height)
               for e,pos,h in obstacles.get((ordered[0].style,ordered[0].name),[])):
            continue
        # Verify every glyph against the completed literal at the retained
        # font size, not merely successive pairwise spacing fits.
        measured = {**ordered[0].state,'fscx':sx}
        if not matches_authored_glyph_positions(metric,measured,xs,literal,center,.05*height):
            continue
        body = render_merged_caption(ordered,fragments,literal,animated=True,
            an=alignment,pos=(center,y),fscx=sx,fscy=sy,fsp=0)
        if body is None:
            continue
        index = min(members)
        caption = replace_event(ordered[0],text=body,source_index=index,
            start=format_time(start),end=format_time(end),start_s=start,end_s=end,effect='')
        if replacement:
            highest = max(int(e.layer) for life in run for e in life.members)
            if not _glyph_replacement_row_is_clear(caption,core,members,highest,parsed,metric,ordered):
                continue
        row = TextRow(caption,[(e,word,get_pos(e.text)) for e,word in zip(ordered,fragments)],phase_core=core)
        proposals.append((members,row,literal))
    claims = collections.Counter(i for ids,row,literal in proposals for i in ids)
    accepted = [(ids,row,literal) for ids,row,literal in proposals if all(claims[i]==1 for i in ids)]
    removed = set().union(*(ids for ids,row,literal in accepted)) if accepted else set()
    replacements = {row.base.source_index:row.base for ids,row,literal in accepted}
    output = [replacements.get(e.source_index,e) for e in events if e.source_index not in removed or e.source_index in replacements]
    return TextPhaseRowsResult(output,len(removed)-len(accepted),[row for ids,row,literal in accepted],
                               {row.base.source_index:literal for ids,row,literal in accepted})
