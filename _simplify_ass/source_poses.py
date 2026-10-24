"""Source-backed rotation normalization and surviving upright-pose recovery.

Sources and working events remain borrowed. Hold indexes and geometry proofs are
call-local; callers retain stage timing and any cross-candidate pose cache.
"""
from __future__ import annotations

import math
import re

from .ass_overrides import DEFAULT_STATE, NUMBER, OVERRIDE_RE, effective_state, tokenize_override
from .caption_geometry import get_pos, inline_layout_key
from .caption_rendering import render_tag
from .event_model import Event
from .event_operations import event_override_tokens, replace_event
from .static_selection import unrotated_text_state, upright_text_state
from .text_freezing import _freeze_inputs, freeze_block
from .transform_sampling import sample_transform_state


def normalize_animated_rotations(events: dict[int,Event]) -> dict[int,Event]:
    """Expose opaque oscillating text as upright source rows of fixed geometry.

    Preserve paint animation and provenance; only rotations and their unused
    origin are removed. Moving/resizing text is frozen normally later, where
    its complete pose can be selected at the same instant.
    """
    result = dict(events)
    for index,e in events.items():
        if (e.kind != 'Dialogue' or e.duration <= 0 or
                not re.search(r'\\t\s*\(',e.text) or
                not re.search(r'\\fr(?:[xyz])?(?=[+\-\d.])',e.text)):
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',e.text).group()
        if not prefix or OVERRIDE_RE.search(e.text,len(prefix)):
            continue
        tokens = [token for block in OVERRIDE_RE.findall(prefix)
                  for token in tokenize_override(block)]
        if any(tag in {'move','r','p'} for tag,_ in tokens):
            continue
        changing = {'fs','fscx','fscy','fsp','fn','b','i','u','s','a','an','r','p',
                    'fax','fay','pos','move','org','clip','iclip','t'}
        if any(tag in changing for name,value in tokens if name == 't'
               for tag,_ in tokenize_override(value[1:-1])):
            continue
        # One-way entrances/exits remain recognizable by the source effect
        # matchers. Only a repeated oscillation supplies an early static row.
        turns = []
        for name,value in tokens:
            if name == 't':
                for tag,argument in tokenize_override(value[1:-1]):
                    if tag in {'fr','frz'}:
                        try: turns.append(math.remainder(float(argument),360))
                        except ValueError: pass
        if len(turns) < 2 or not any(a*b < 0 for a,b in zip(turns,turns[1:])):
            continue
        frozen = freeze_block(''.join(OVERRIDE_RE.findall(prefix)),e.duration,
                              e.defaults,e.defaults,e.styles,0,prefer_upright=True)
        state = frozen.selection.state
        if not frozen.selection.pose.upright_rotation or not unrotated_text_state(state):
            continue
        if not (state.get('1a',0) == 0 or state.get('1a',0) >= 254 and
                state.get('3a',0) == 0 and
                max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0):
            continue
        block = re.sub(r'\\fr(?:[xyz])?'+NUMBER,'',prefix)
        block = re.sub(r'\\org\([^)]*\)','',block)
        result[index] = replace_event(e,text=r'{\frz0\frx0\fry0}'+block+e.text[len(prefix):])
    return result



def adjacent_sustained_geometry(sources: dict[int,Event], targets: list[Event]) -> dict[int,dict]:
    """Prove a short phase's layout from a touching, longer source hold.

    Exact text/style context, compatible boundary geometry and one unique
    held layout are required. Rotation and paint are intentionally separate.
    A matching letter elsewhere on the screen supplies no evidence.
    """
    def family(e):
        return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,OVERRIDE_RE.sub('',e.text))
    wanted = {family(e) for e in targets}
    layout = ('pos','fn','fs','fscx','fscy','fsp','an','b','i','u','s','fax','fay','pbo','q')
    forbidden = {*layout,'fr','frz','frx','fry','r','p','clip','iclip','org'}
    starts,ends = {},{}
    for held in sources.values():
        key = family(held)
        if (held.kind != 'Dialogue' or held.duration < .25 or key not in wanted or
                inline_layout_key(held) or get_pos(held.text) is None):
            continue
        tokens = event_override_tokens(held)
        if (any(tag in {'move','fade','clip','iclip','org','p'} for tag,value in tokens) or
                any(tag in forbidden for name,value in tokens if name == 't'
                    for tag,value in tokenize_override(value[1:-1]))):
            continue
        state = effective_state(held.text,held.defaults,held.styles)
        if (state.get('p',0) or state.get('fs',20) <= 0 or
                not upright_text_state(state,include_shadow=True,include_outline=True)):
            continue
        changing_alpha = {tag for name,value in tokens if name == 't'
                          for tag,_ in tokenize_override(value[1:-1])
                          if tag in {'alpha','1a','3a','4a'}}
        visible_channel = '1a' if state.get('1a',0) < 239 else (
            '3a' if state.get('3a',0) < 239 and
            max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0 else '4a')
        if 'alpha' in changing_alpha or visible_channel in changing_alpha:
            continue
        fades = [re.findall(NUMBER,value) for name,value in tokens if name == 'fad']
        if len(fades) > 1 or any(len(values) != 2 for values in fades):
            continue
        fade = sum(max(0,float(v)) for values in fades for v in values)/1000
        dwell = max(0,held.duration-fade)
        if dwell < .25:
            continue
        data = (held,state,dwell)
        starts.setdefault((key,round(held.start_s*100)),[]).append(data)
        ends.setdefault((key,round(held.end_s*100)),[]).append(data)
    proven = {}
    for original in targets:
        if (original.kind != 'Dialogue' or original.duration <= 0 or inline_layout_key(original) or
                any(tag in {'clip','iclip','org','p'} for tag,_ in event_override_tokens(original))):
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        evaluation,transforms,_,_ = _freeze_inputs(''.join(OVERRIDE_RE.findall(prefix)),original.duration,
            original.defaults,original.defaults,original.styles)
        options = {}
        for at,index,boundary in ((0,ends,original.start_s),
                                  (original.duration*1000,starts,original.end_s)):
            pose = sample_transform_state(evaluation.formatting,transforms,at,original.styles,original.defaults,
                                          continuation=evaluation.continuation).formatting
            for centisecond in range(round(boundary*100)-1,round(boundary*100)+2):
                for held,state,dwell in index.get((family(original),centisecond),[]):
                    touching = held.end_s if at == 0 else held.start_s
                    if abs(touching-boundary) > .011 or dwell < max(.25,2*original.duration):
                        continue
                    # Centisecond cue rounding can cut a millisecond-based
                    # entrance slightly short. Allow two script pixels of
                    # boundary rounding, never a different screen location.
                    unit = 2*max(original.unit,held.unit)
                    if any(pose.get(k,DEFAULT_STATE.get(k)) != state.get(k,DEFAULT_STATE.get(k))
                           for k in layout if k not in {'pos','fs','fscx','fscy','fsp'}):
                        continue
                    if (pose.get('pos') is None or math.dist(pose['pos'],state['pos']) > unit or
                            abs(pose.get('fs',20)-state.get('fs',20)) > unit or
                            abs(pose.get('fsp',0)-state.get('fsp',0)) > unit or
                            any(abs(pose.get(k,100)-state.get(k,100))*state.get('fs',20)/100 > unit
                                for k in ('fscx','fscy'))):
                        continue
                    key = tuple(state.get(k,DEFAULT_STATE.get(k)) for k in layout)
                    options[key] = {k:state[k] for k in layout if k in state}
        if len(options) == 1:
            proven[original.source_index] = next(iter(options.values()))
    return proven



def prefer_surviving_upright_poses(events: list[Event], sources: dict[int,Event]) -> list[Event]:
    """Apply the general rotation policy after source effect cleanup.

    Earlier proofs use their established frozen geometry. Revisit only intact
    retained text, preserving its selected paint, timing and assembled rows.
    """
    geometry = {'fn','fs','fscx','fscy','fsp','b','i','u','s','an','a','pos','org',
                'fr','frz','frx','fry','fax','fay','pbo'}
    def inline_geometry(e):
        if not inline_layout_key(e):
            return False
        painted = False
        for part in re.split(r'(\{[^}]*\})',e.text):
            if part.startswith('{'):
                if painted and any(tag in geometry|{'r','t','p','clip','iclip'}
                                   for tag,_ in tokenize_override(part[1:-1])):
                    return True
            elif part:
                painted = True
        return False
    targets = {}
    for e in events:
        original = sources.get(e.source_index)
        if (e.kind == 'Dialogue' and original is not None and e.style == original.style and
                any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry')) and
                not inline_geometry(e) and not inline_geometry(original) and
                re.search(r'\\t\s*\(',original.text) and
                re.search(r'\\fr(?:[xyz])?(?=[+\-\d.])',original.text) and
                OVERRIDE_RE.sub('',e.text) == OVERRIDE_RE.sub('',original.text)):
            targets[e.source_index] = original
    if not targets:
        return events
    output = []
    proven_geometry = None
    for e in events:
        original = targets.get(e.source_index)
        if original is None:
            output.append(e)
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        frozen = freeze_block(''.join(OVERRIDE_RE.findall(prefix)),original.duration,
                              original.defaults,original.defaults,original.styles,0,
                              prefer_upright=True)
        state = frozen.selection.state
        if not frozen.selection.pose.upright_rotation or not unrotated_text_state(state):
            output.append(e)
            continue
        if proven_geometry is None:
            proven_geometry = adjacent_sustained_geometry(sources,list(targets.values()))
        protected = dict(frozen.selection.pose.sustained_geometry or ())
        state.update(proven_geometry.get(original.source_index,{}))
        state.update(protected)
        prefix_end = re.match(r'(?:\{[^}]*\})*',e.text).end()
        paint = ''.join('\\'+tag+value for block in OVERRIDE_RE.findall(e.text[:prefix_end])
                        for tag,value in tokenize_override(block) if tag not in geometry)
        pose = ''.join(render_tag(k,v) for k,v in state.items() if k in geometry-{'a','fr'})
        output.append(replace_event(e,text='{'+paint+pose+'}'+e.text[prefix_end:]))
    return output
