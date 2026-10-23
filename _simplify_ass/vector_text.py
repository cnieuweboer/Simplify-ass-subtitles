"""Exact-font vector-caption recovery and source ownership.

Borrow source events, measurements, decoder profiles and optional diagnostics.
Drawing indexes, cue evidence, positive/negative source fits and proposal claims
remain call-local. The engine retains stage order and aggregate reporting.
"""
from __future__ import annotations

from bisect import bisect_right
import collections
from dataclasses import dataclass, replace as dataclass_replace
import math
import re
import statistics

from .ass_overrides import (
    DEFAULT_STATE, NUMBER, OverrideContinuation, apply_override,
    evaluate_effective_state, tokenize_override,
)
from .caption_geometry import get_pos, inline_layout_key
from .caption_rendering import render_simplified_caption, render_merged_caption
from .effect_validation import parse_effect_transform
from .event_model import Event
from .event_operations import event_override_tokens, replace_event
from .font_metrics import FontMetrics
from .font_outlines import FontOutlineMatcher, fit_cubic_points
from .font_reporting import FontProcessingReport
from .glyph_placement import fit_fragment_anchor
from .row_fitting import recover_font_row
from .static_objects import geometry_key
from .static_selection import unrotated_text_state
from .subtitle_document import format_time
from .text_freezing import simplify_text, simplify_visual_text
from .transform_sampling import sample_transform_state


@dataclass(frozen=True)
class VectorTextFitContext:
    """Per-call font measurement, blur policy and positive/negative outline-fit cache."""
    metric: FontMetrics
    max_blur: float
    cache: dict
    font_report: FontProcessingReport | None = None



def infer_vector_text_cues(
    runs: dict, parsed: dict[int, Event], metric: FontMetrics, authored_styles: set[str], *,
    font_report: FontProcessingReport | None=None, outline_matcher: FontOutlineMatcher | None=None,
) -> list[tuple[Event, str]]:
    """Recover missing cue evidence only from decoded complete animation rows.

    Ordered instantaneous opacity switches prove syllable activation intervals.
    A synchronized full line may share that interval when its font, layer,
    placement margins, frame boundaries and entrance/exit fades agree. Neither
    guessed words nor a renderer-dependent frame rounding offset supplies timing.
    """
    if outline_matcher is None:
        outline_matcher = FontOutlineMatcher(metric)
    alphabet = set()
    for e in parsed.values():
        if e.kind == 'Dialogue' and not re.search(r'\\p[1-9]',e.text,re.I):
            alphabet.update(simplify_text(e.text,visible_only=True)[1])
    families = {}
    for style,group in runs.items():
        if style in authored_styles:
            continue
        for key,items in group:
            if len(items) < 3:
                continue
            lane = key[:6]+(key[6][1],key[7],round(items[0][0].start_s,2),round(items[-1][0].end_s,2))
            families.setdefault(lane,[]).append((key,items))
    decoded = []
    for family in families.values():
        family.sort(key=lambda run:run[0][6][0])
        activations = []
        for key,items in family:
            first = items[0][0]
            switches = []
            for tag,value in event_override_tokens(first):
                if tag != 't':
                    continue
                transform = parse_effect_transform(value,first.duration,{'1a','3a'},
                    allow_instant=True,allow_after_end=True)
                if transform is None or transform[0] != transform[1]:
                    continue
                target = first.defaults.copy()
                target_continuation = OverrideContinuation()
                for name,arg in transform[2]:
                    target_continuation = apply_override(target,name,arg,first.styles,first.defaults,target_continuation)
                if any(name == '1a' for name,arg in transform[2]):
                    switches.append((first.start_s+transform[0]/1000,target.get('1a',0)))
            if (len(switches) != 2 or switches[0][1] != 255 or switches[1][1] != 0 or
                    switches[0][0] >= switches[1][0]):
                break
            activation = (switches[0][0],switches[1][0])
            # Generated frames may retain transforms scheduled beyond their
            # own end. Those annotations alone are not timing evidence: the
            # subsequent frames must actually hide/show this backing glyph.
            starts = [e.start_s for e,p,s in items]
            def opacity_at(at):
                offset = bisect_right(starts,at)-1
                if offset < 0 or at >= items[offset][0].end_s:
                    return None
                event,_,base = items[offset]
                transforms = []
                for tag,value in event_override_tokens(event):
                    if tag == 't':
                        t = parse_effect_transform(value,event.duration,{'1a','3a','alpha'},
                            allow_instant=True,allow_after_end=True)
                        if t is not None:
                            transforms.append((t[0],t[1],1,t[2]))
                return sample_transform_state(base,transforms,1000*(at-event.start_s),
                    event.styles,event.defaults,continuation=event.continuation).formatting.get('1a',0)
            inside = [activation[0]+fraction*(activation[1]-activation[0]) for fraction in (.25,.75)]
            outside = [(a+b)/2 for a,b in ((items[0][0].end_s,activation[0]),
                        (activation[1],items[-1][0].start_s)) if a < b]
            if (not outside or any((opacity_at(at) or 0) < 254 for at in inside) or
                    not any((value := opacity_at(at)) is not None and value < 16 for at in outside)):
                break
            activations.append(tuple(round(v,2) for v in activation))
        core = None
        if (len(activations) == len(family) and all(a[0] <= b[0] and a[1] <= b[1]
                for a,b in zip(activations,activations[1:]))):
            core = (activations[0][0],activations[-1][1])
        first,last = family[0][1][0][0],family[0][1][-1][0]
        state = family[0][1][0][2]
        sync = (first.layer,first.name,first.margin_l,first.margin_r,first.margin_v,
                tuple(state.get(k) for k in ('fn','fs','fscx','fscy','b','i')),
                round(first.start_s,2),round(last.end_s,2))
        # Require whole-frame alpha entrances and exits for cross-row timing.
        def edge_fade(e,alpha):
            return any(tag == 't' and not re.match(r'\(\s*'+NUMBER,value) and
                (t := parse_effect_transform(value,e.duration,{'1a','3a'})) is not None and
                any(k == '1a' and v.upper().removeprefix('&H').rstrip('&') == alpha
                    for k,v in t[2]) for tag,value in event_override_tokens(e))
        synchronized = all(edge_fade(items[0][0],'00') and edge_fade(items[-1][0],'FF')
                           for key,items in family)
        if core is None and not synchronized:
            continue
        row,words = [],[]
        for key,items in family:
            sample,state = items[0][0],items[0][2]
            face = metric.matching_face(str(state.get('fn','')),state.get('b',0),False)
            if face is None:
                break
            path = tuple(v if isinstance(v,str) else statistics.median(item[1][i] for item in items)
                         for i,v in enumerate(items[0][1]))
            try:
                text = outline_matcher.decode_cubic_outline(face,path,state.get('fs',20),sample.unit,alphabet)
            except (OSError,ValueError,RuntimeError):
                text = None
            if text is None:
                break
            row.append(replace_event(sample,text=render_simplified_caption(state,text,p=0,fsp=0,measurement=sample.measurement)))
            words.append(text)
        else:
            if sum(c.isalnum() for text in words for c in text) < 3:
                continue
            text = words[0]
            if len(row) > 1:
                fit = recover_font_row(metric, row,words,max_size_error=.2, font_report=font_report)
                if fit is not None:
                    text = fit[0]
                elif all(not any(c.isspace() for c in word) for word in words):
                    text = ''.join(words)
                    if fit_fragment_anchor(metric, row[0].state,[get_pos(e.text)[0] for e in row],
                            words,text,row[0].unit,max_size_error=.2) is None:
                        continue
                else:
                    continue
            decoded.append((family,row,words,text,core,sync,synchronized))
    shared = {}
    for family,row,words,text,core,sync,synchronized in decoded:
        if core is not None and synchronized:
            shared.setdefault(sync,set()).add(core)
    cues = []
    for family,row,words,text,core,sync,synchronized in decoded:
        if core is None and synchronized and len(shared.get(sync,())) == 1:
            core = next(iter(shared[sync]))
        sample = family[0][1][0][0]
        if core is None or not sample.start_s < core[0] < core[1] < family[0][1][-1][0].end_s:
            continue
        # Internal cue evidence only; no inferred Comment is written to output.
        body = text if len(words) == 1 else ''.join(r'{\k0}'+word for word in words)
        # Keep measured spaces for the caption, while fragments identify paths.
        cues.append((replace_event(sample,kind='Comment',text=body,start=format_time(core[0]),
            start_s=core[0],end=format_time(core[1]),end_s=core[1]),text))
    return cues



def _index_authored_vector_text_cues(parsed: dict[int,Event]) -> tuple[dict,set,set]:
    """Index unique unformatted text/karaoke comments and styles with possible drawing cues."""
    cues = {}
    for e in parsed.values():
        if e.kind != 'Comment' or e.duration <= 0:
            continue
        text = simplify_text(e.text,visible_only=True)[1]
        if (not text.strip() or re.search(r'\\[Nn]|[\r\n]',text) or
                any(tag not in {'k','kf','ko','kt'} for tag,value in event_override_tokens(e))):
            continue
        cues.setdefault((e.style,e.start_s,e.end_s,text),e)
    authored_styles = {cue.style for cue in cues.values()}
    styles = authored_styles|{e.style for e in parsed.values() if e.kind == 'Dialogue' and
                             re.search(r'\\p1(?![\dA-Za-z])',e.text,re.I)}
    return cues,authored_styles,styles



def _profile_vector_text_drawing(e: Event, geometry: set, transform_paint: set) -> tuple | None:
    """Validate stationary cubic drawing geometry and build its font/layout/skeleton identity."""
    tokens = event_override_tokens(e)
    if (inline_layout_key(e) or any(tag in {'move','clip','iclip','org','r'} or
            tag == 't' and any(k not in transform_paint for k,v in
                tokenize_override(value.strip('()'))) for tag,value in tokens)):
        return None
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    pos = get_pos(e.text)
    if (pos is None or state.get('p',0) != 1 or int(state.get('an',5)) != 5 or
            state.get('pbo',0) or state.get('borderstyle',1) != 1 or
            not unrotated_text_state(state) or any(abs(state.get(k,0)) > .001
                for k in ('fax','fay','u','s','i')) or
            any(state.get(k,100) != 100 for k in ('fscx','fscy')) or
            not all(math.isfinite(v) for v in (*pos,state.get('fs',20)))):
        return None
    path = geometry_key(e.text)
    skeleton = tuple(v if isinstance(v,str) else None for v in path)
    if not path or any(v not in {'m','l','b'} for v in path if isinstance(v,str)):
        return None
    key = (e.style,e.layer,e.name,e.margin_l,e.margin_r,e.margin_v,pos,
           tuple(state.get(k,DEFAULT_STATE.get(k)) for k in sorted(geometry)),skeleton)
    return key,path,evaluated



def _index_vector_text_sources(parsed: dict[int,Event], styles: set) -> tuple[dict,dict]:
    """Keep admissible drawing groups separate from same-style readable backing text."""
    groups, backing = {}, {}
    geometry = {'fn','fs','fsp','fscx','fscy','an','b','i','u','s','pbo','encoding'}
    transform_paint = {'alpha','1a','2a','3a','4a','c','1c','2c','3c','4c',
                       'bord','xbord','ybord','blur','be'}
    for e in parsed.values():
        if e.kind != 'Dialogue' or e.style not in styles or e.duration <= 0:
            continue
        if not re.search(r'\\p1(?![\dA-Za-z])',e.text,re.I):
            if simplify_text(e.text,visible_only=True)[1].strip():
                backing.setdefault(e.style,[]).append(e)
            continue
        profile = _profile_vector_text_drawing(e,geometry,transform_paint)
        if profile is not None:
            key,path,evaluated = profile
            sample = dataclass_replace(e,state=evaluated.formatting,continuation=evaluated.continuation)
            groups.setdefault(key,[]).append((sample,path,evaluated.formatting))
    return groups,backing



def _group_vector_text_runs(groups: dict) -> dict:
    """Form time-connected noncompeting drawing runs with the original gap/overlap tolerances."""
    runs = {}
    for key,items in groups.items():
        items.sort(key=lambda item:(item[0].start_s,item[0].end_s))
        components = []
        latest = float('-inf')
        for item in items:
            if not components or item[0].start_s > latest+.011:
                components.append([])
            components[-1].append(item)
            latest = max(latest,item[0].end_s)
        for component in components:
            if any(b[0].start_s < a[0].end_s-.001 for a,b in zip(component,component[1:])):
                continue
            runs.setdefault(key[0],[]).append((key,component))
    return runs



def _measure_vector_text_outline(run: tuple, text: str, context: VectorTextFitContext) -> list | None:
    """Prove exact command skeleton and sampled median control points at a plausible font size."""
    key,items = run
    state = items[0][2]
    face = context.metric.matching_face(str(state.get('fn','')),state.get('b',0),False)
    if face is None:
        if context.font_report is not None:
            context.font_report.missing_families.add(str(state.get('fn','')))
        return None
    outline = context.metric.cubic_outline(face,text)
    if outline is None or tuple(v if isinstance(v,str) else None for v in outline[0]) != key[-1]:
        return None
    sample = [items[i] for i in sorted({round(j*(len(items)-1)/4) for j in range(5)})]
    measured = tuple(v if isinstance(v,str) else statistics.median(item[1][i] for item in sample)
                     for i,v in enumerate(outline[0]))
    fitted = fit_cubic_points(outline[0],measured)
    if fitted is None:
        return None
    scale,_,_,error = fitted
    nominal = context.metric.ass_em_scale(face)
    if nominal is None:
        return None
    nominal *= state.get('fs',20)/outline[1]
    # Font drawing exporters and renderers use different line metrics.
    # Permit the same modest sizing variance, never arbitrary path fits.
    tolerance = max(items[0][0].unit,.05*state.get('fs',20))
    if nominal <= 0 or abs(scale-nominal) > .2*nominal or error > tolerance:
        return None
    return sample



def _select_vector_text_paint(sample: list, text: str, context: VectorTextFitContext) -> Event | None:
    """Freeze sampled drawings and choose the longest opaque sample for recovered caption paint."""
    visible = []
    for e,path,state in sample:
        body,_,_ = simplify_visual_text(e.text,context.max_blur,e.duration,e.defaults,e.styles,2)
        frozen = replace_event(e,text=body)
        if frozen.state.get('1a',0) < 16:
            visible.append(frozen)
    if not visible:
        return None
    chosen = max(visible,key=lambda e:e.duration)
    result = replace_event(chosen,text=render_simplified_caption(chosen.state,text,p=0,measurement=chosen.measurement))
    return result



def _fit_vector_text_outline(run: tuple, text: str, context: VectorTextFitContext) -> Event | None:
    """Cache both rejected and reconstructed outline fits by the original source/text identity."""
    key,items = run
    cache_key = (items[0][0].source_index,text)
    if cache_key in context.cache:
        return context.cache[cache_key]
    context.cache[cache_key] = None
    sample = _measure_vector_text_outline(run,text,context)
    if sample is None:
        return None
    result = _select_vector_text_paint(sample,text,context)
    if result is None:
        return None
    context.cache[cache_key] = result
    return result



def _select_vector_text_cue_runs(runs: dict, cue: Event, start: float, end: float) -> dict:
    """Admit drawing runs covering a cue within its original allowance and group horizontal lanes."""
    candidates = {}
    for run in runs.get(cue.style,()):
        key,items = run
        allowance = max(.25*cue.duration,2*statistics.median(e.duration for e,p,s in items))
        if (items[0][0].start_s > start+.011 or items[-1][0].end_s < end-.011 or
                items[0][0].start_s < start-allowance or items[-1][0].end_s > end+allowance):
            continue
        lane = key[:6]+(key[6][1],key[7])
        candidates.setdefault(lane,[]).append(run)
    return candidates



def _recover_vector_text_fragment_anchor(
    row: list[Event], words: list[str], text: str, metric: FontMetrics, *,
    font_report: FontProcessingReport | None=None,
) -> tuple | None:
    """Use the existing space-aware recovery, then only the original no-space anchor fallback."""
    x,y = get_pos(row[0].text)
    if len(row) > 1:
        measured = [dataclass_replace(e,state={**e.state,'fsp':0}) for e in row]
        recovered = recover_font_row(metric, measured,words,max_size_error=.2, font_report=font_report)
        if recovered is not None and recovered[0] == text:
            x = recovered[1]
        elif not any(c.isspace() for c in text):
            x = fit_fragment_anchor(metric, measured[0].state,
                [get_pos(e.text)[0] for e in row],words,text,row[0].unit,max_size_error=.2)
            if x is None:
                return None
        else:
            return None
    return x,y



def _reconstruct_vector_text_family(family: list, words: list[str], text: str, cue: Event, start: float, end: float, context: VectorTextFitContext) -> tuple | None:
    """Fit every fragment before rendering one authored caption and recording all consumed sources."""
    row = [_fit_vector_text_outline(run,word,context) for run,word in zip(family,words)]
    if any(e is None for e in row):
        return None
    anchor = _recover_vector_text_fragment_anchor(row,words,text,context.metric, font_report=context.font_report)
    if anchor is None:
        return None
    x,y = anchor
    body = render_merged_caption(row,words,text,animated=True,an=5,pos=(x,y),fscx=100,fscy=100)
    if body is None:
        return None
    members = {e.source_index for run in family for e,p,s in run[1]}
    first = min(members)
    caption = replace_event(row[0],source_index=first,text=body,start=cue.start,
        start_s=start,end=cue.end,end_s=end,effect='')
    return members,caption



def _propose_vector_text_cue(cue: Event, start: float, end: float, text: str, runs: dict, backing: dict, context: VectorTextFitContext) -> tuple | None:
    """Reject text-backed cues and require one fully reconstructed whole-line or fragment family."""
    if any(min(e.end_s,end)-max(e.start_s,start) >= .5*cue.duration
           for e in backing.get(cue.style,())):
        return None
    candidates = _select_vector_text_cue_runs(runs,cue,start,end)
    fragments = [part.strip() for part in re.split(
        r'\{[^}]*\\[kK](?:f|o|t)?\d+[^}]*\}',cue.text) if part.strip()]
    options = []
    for family in candidates.values():
        family.sort(key=lambda run:run[0][6][0])
        words = [text] if len(family) == 1 else fragments
        if (len(words) != len(family) or ''.join(''.join(w.split()) for w in words) !=
                ''.join(text.split())):
            continue
        option = _reconstruct_vector_text_family(family,words,text,cue,start,end,context)
        if option is not None:
            options.append(option)
    return options[0] if len(options) == 1 else None



def _apply_vector_text_ownership(parsed: dict[int,Event], proposals: list) -> tuple[dict[int,Event],int]:
    """Accept only uniquely owned drawing sources, preserving dictionary order and recovered-cue count."""
    claims = collections.Counter(index for members,caption in proposals for index in members)
    accepted = [(members,caption) for members,caption in proposals
                if all(claims[index] == 1 for index in members)]
    if not accepted:
        return parsed,0
    consumed = set().union(*(members for members,caption in accepted))
    result = {index:e for index,e in parsed.items() if index not in consumed}
    result.update((caption.source_index,caption) for members,caption in accepted)
    return result,len(accepted)



def recover_vector_text_cues(
    parsed: dict[int, Event], metric: FontMetrics | None, max_blur: float=0.0, *,
    font_report: FontProcessingReport | None=None, outline_matcher: FontOutlineMatcher | None=None,
) -> tuple[dict[int, Event], int]:
    """Recover authored captions proven by complete exact-font drawing rows.

    A comment is only a text candidate. Each whole line or karaoke fragment
    must match the font's contour commands and control points at a plausible
    common size, across a time-connected drawing run covering its cue. Existing
    font spacing checks prove fragment order and authored spaces. Clipped,
    moving, rotated, incomplete, competing and already text-backed cues reject.
    No effect names, source-line annotations or subtitle-specific values matter.
    """
    if metric is None or not metric.available:
        return parsed,0
    if outline_matcher is not None and outline_matcher.metrics is not metric:
        raise ValueError('Outline matcher must use the supplied FontMetrics owner.')
    if outline_matcher is None:
        outline_matcher = FontOutlineMatcher(metric)
    cues,authored_styles,styles = _index_authored_vector_text_cues(parsed)
    if not styles:
        return parsed,0
    groups,backing = _index_vector_text_sources(parsed,styles)
    runs = _group_vector_text_runs(groups)
    for cue,text in infer_vector_text_cues(runs,parsed,metric,authored_styles, font_report=font_report, outline_matcher=outline_matcher):
        cues.setdefault((cue.style,cue.start_s,cue.end_s,text),cue)
    context = VectorTextFitContext(metric,max_blur,{}, font_report=font_report)
    proposals = []
    for (_,start,end,text),cue in cues.items():
        proposal = _propose_vector_text_cue(cue,start,end,text,runs,backing,context)
        if proposal is not None:
            proposals.append(proposal)
    return _apply_vector_text_ownership(parsed,proposals)

