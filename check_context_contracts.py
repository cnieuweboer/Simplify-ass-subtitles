#!/usr/bin/env python3
"""Audit the final document/cache/branch ownership contracts without adapters."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType
import importlib.util
import json
import sys

import simplify_ass as s
from event_evidence_test_helpers import event_comparison_fields

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('contracts_reference', ROOT/'test-data/simplify_ass-v161-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
checks = []

def check(name, condition):
    assert condition, name
    checks.append(name)

def key_fields(value):
    if isinstance(value, tuple):
        return tuple(key_fields(x) for x in value)
    if hasattr(value, '__dict__'):
        return tuple((k,key_fields(v)) for k,v in vars(value).items())
    return value

HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
Style: Other,Other Font,60,7,4,3
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
tags = ['', r'\r', r'\rMissing', r'\rOther', r'\an0', r'\an7',
        r'\rOther\an0', r'\an0\rOther\fs', r'\rOther\fs+2', r'\q1\rOther']
for first in tags:
    for second in tags:
        body = '{'+r'\pos(320,180)'+first+'}A{'+second+'}B'
        text = HEADER+f'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{body}\n'
        raw = s.parse_subtitle_document(text)
        before = deepcopy(raw)
        prepared = s._prepare_text_document(raw, Path('contract.ass'))
        resolved = s._resolve_document_state(raw)
        original, working, event = [next(iter(doc.events.values())) for doc in (raw, prepared, resolved)]
        check('source records unchanged', vars(raw) == vars(before))
        check('text boundary creates events', working is not original and working.state is not original.state)
        check('text boundary borrows catalog', prepared.styles is raw.styles and working.styles is raw.styles)
        check('text boundary retains inactive context', prepared.measurement is raw.measurement and working.measurement.script_wrap_mode is None)
        check('measurement boundary copies style catalog', resolved.styles is not raw.styles and all(resolved.styles[k] is not v for k,v in raw.styles.items()))
        check('measurement cache distinct from defaults', event.state is not event.defaults and event.defaults is resolved.styles['Default'])
        check('measurement events share document context', event.measurement is resolved.measurement and event.measurement.script_wrap_mode == 2)
        check('raw metadata reused read-only', resolved.lines is raw.lines and resolved.fields is raw.fields)
        check('native parsed style values immutable', all(isinstance(v, (str,int,float)) for style in raw.styles.values() for v in style.values()))

        # Freeze the borrowed catalog and cache to expose writes through aliases.
        catalog = MappingProxyType({k:MappingProxyType(v.copy()) for k,v in resolved.styles.items()})
        borrowed = replace(event, state=MappingProxyType(event.state.copy()), defaults=catalog['Default'], styles=catalog)
        evaluation = s.event_evaluation(borrowed)
        check('cache view deliberately borrows', evaluation.formatting is borrowed.state and evaluation.continuation is borrowed.continuation)
        target = dict(evaluation.formatting)
        continuation = s.apply_override(target, 'r', 'Other', catalog, borrowed.defaults, evaluation.continuation)
        continuation = s.apply_override(target, 'fs', '', catalog, borrowed.defaults, continuation)
        check('local override leaves borrowed state intact', dict(borrowed.state) == event.state and target['fs'] == catalog['Other']['fs'])
        check('branch reset does not commit to source', borrowed.continuation == event.continuation)
        s.static_object_key(borrowed, catalog)
        s.literal_font_spans(borrowed)
        s.static_text_paint_geometry(borrowed, set(s.CAPTION_PAINT_TAGS))
        s.render_simplified_caption(borrowed.state, 'AB', measurement=borrowed.measurement)
        s.freeze_block(first+r'\t(0,500,\rOther\fs+2)', 3, borrowed.state, borrowed.defaults, catalog, 2,
                       continuation=borrowed.continuation)
        samples = list(s.sample_transform_states(borrowed.state, [(0,500,1,[('fs','80')])], [0,250,500], catalog, borrowed.defaults, continuation=borrowed.continuation))
        check('samples own independent buffers', len({id(x.formatting) for x in samples}) == len(samples) and all(x.formatting is not borrowed.state for x in samples))
        snapshots = [dict(x.formatting) for x in samples]
        samples[0].formatting['fs'] = -99
        check('sample mutation isolated', [dict(x.formatting) for x in samples[1:]] == snapshots[1:])
        selected = s.select_static_state(borrowed.state, [], set(), catalog, borrowed.defaults, continuation=borrowed.continuation)
        check('selection early return retains borrowed identity', selected.state is borrowed.state and selected.continuation is borrowed.continuation)

        timed = s.replace_event(borrowed, end_s=5, end='0:00:05.00')
        edited = s.replace_event(borrowed, state={**borrowed.state,'1c':'123456'})
        rewritten = s.replace_event(borrowed, text=r'{\rOther\an0\fs}New')
        check('timing successor shares read-only cache/history', timed.state is borrowed.state and timed.continuation is borrowed.continuation)
        check('resolved edit owns caller buffer, shares history', edited.state is not borrowed.state and edited.continuation is borrowed.continuation)
        check('text replacement recomputes pair', rewritten.state == s.evaluate_effective_state(rewritten.text, rewritten.defaults, catalog).formatting and rewritten.continuation == s.OverrideContinuation('Other',True))
        check('all replacements retain context', all(x.measurement is borrowed.measurement for x in (timed,edited,rewritten)))
        cleared = s.replace_event(borrowed,state={},continuation=s.OverrideContinuation('Other',True))
        check('clearing cache clears history', cleared.continuation == s.OverrideContinuation())
        fresh = s.event_evaluation(cleared)
        check('unresolved read owns result without caching', fresh.formatting == event.state and fresh.continuation == event.continuation and not cleared.state)
        for value, attr in ((borrowed.measurement,'canvas'),(borrowed.continuation,'reset_style')):
            try:
                setattr(value, attr, None)
            except FrozenInstanceError:
                check('shared records frozen',True)
            else:
                raise AssertionError('mutable shared record')
        # Complete final-version event semantics, not stripped formatting alone.
        prior = previous._resolve_document_state(previous.parse_subtitle_document(text))
        prior_event = next(iter(prior.events.values()))
        check('complete source-cache parity', event_comparison_fields(event) == event_comparison_fields(prior_event))
        check('static key parity', key_fields(s.static_object_key(event,event.styles)) == key_fields(previous.static_object_key(prior_event,prior_event.styles)))

report = dict(version=s.__version__,checks_passed=len(checks),source_cases=len(tags)**2,
              readonly_catalog_and_cache_probes=True,branch_buffers_independent=True,
              complete_event_history_preserved=True)
(ROOT/'validation/context-contract-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'final context contract checks passed')
