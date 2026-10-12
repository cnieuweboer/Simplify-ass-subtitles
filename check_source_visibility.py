#!/usr/bin/env python3
"""Check read-only source collection, visibility phases and evidence ownership."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import ast
import importlib.util
import json
import random
import sys
from event_evidence_test_helpers import resolve_test_event
import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('opaque_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=previous
spec.loader.exec_module(previous)
HEADER='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
Style: Other,Arial,45,7,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def snapshot(value):
    if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def source(module,tags,order,initial):
    lines=[]
    for layer in range(4):
        tag=tags[layer%len(tags)]
        for i,word in enumerate(('ab','cd','ef','gh')):
            lines.append(f'Dialogue: {layer},0:00:10.00,0:00:14.00,Default,,0,0,0,,'
                +r'{\pos('+str(100+40*i)+',100)'+tag+'}'+word+'\n')
    doc=module.parse_subtitle_document(HEADER+''.join(lines))
    parsed=doc.events
    for e in parsed.values():
        if initial=='resolved':resolve_test_event(module,e)
        if initial=='stale':e.state={'fs':999,'sentinel':[]}
    pairs=list(parsed.items())
    if order=='reversed':pairs.reverse()
    if order=='shuffled':random.Random(150).shuffle(pairs)
    return dict(pairs),doc
CASES=[
    ('static',('',)),
    ('colour-only',(r'\t(0,1000,\1c&H0000FF&)',)),
    ('opacity entrance',(r'\1a&HFF&\t(0,500,\1a&H00&)',)),
    ('opacity exit',(r'\t(3500,4000,\1a&HFF&)',)),
    ('instant alternating',(r'\t(2000,2000,\1a&HFF&)',r'\1a&HFF&\t(2000,2000,\1a&H00&)')),
    ('multi-phase',(r'\t(1000,1000,\1a&HFF&)\t(2000,2000,\1a&H00&)\t(3000,3000,\1a&HFF&)',
                    r'\1a&HFF&\t(1000,1000,\1a&H00&)\t(2000,2000,\1a&HFF&)\t(3000,3000,\1a&H00&)')),
    ('transparent fill',(r'\1a&H80&',)),
    ('fully hidden',(r'\1a&HFF&',)),
    ('hidden reset',(r'\1a&HFF&\t(1000,1000,\rDefault)',)),
    ('global alpha',(r'\alpha&HFF&\t(1000,1000,\alpha&H00&)',)),
    ('different paint',(r'\1c&H0000FF&',r'\1c&HFF0000&')),
    ('font mismatch',(r'\fnArial',r'\fnMissing')),
    ('geometry transform',(r'\t(0,1000,\fs50)',)),
    ('moving',(r'\move(100,100,200,100)',)),
    ('clipped',(r'\clip(0,0,1000,1000)',)),
    ('inverse clipped',(r'\iclip(0,0,1000,1000)',)),
    ('drawing',(r'\p1',)),
    ('origin',(r'\org(0,0)',)),
    ('fade',(r'\fad(100,100)',)),
    ('zero scale',(r'\fscx0',)),
    ('rotation',(r'\frz10',)),
    ('shear',(r'\fax1',)),
    ('inline font',(r'\fs40',)),
]
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
comparisons=[]
for name,tags in CASES:
    for order in ('original','reversed','shuffled'):
        for initial in ('empty','resolved','stale'):
            old,_=source(previous,tags,order,initial)
            new,_=source(current,tags,order,initial)
            before=deepcopy({k:vars(e) for k,e in new.items()})
            identities={k:(id(e),id(e.state),id(e.defaults),id(e.styles)) for k,e in new.items()}
            previous_result=previous.collect_source_text_rows(old,set(old))
            old_rows,old_words,old_positions=previous_result.rows,previous_result.words,previous_result.positions
            result=current.collect_source_text_rows(new,set(new))
            assert before=={k:vars(e) for k,e in new.items()},(name,order,initial,'input mutated')
            assert identities=={k:(id(e),id(e.state),id(e.defaults),id(e.styles)) for k,e in new.items()}
            assert snapshot(previous_result.events)==snapshot(result.events),(name,order,initial,'resolved events')
            assert snapshot((old_rows,old_words,old_positions))==snapshot((result.rows,result.words,result.positions)),(name,order,initial,'collected evidence')
            assert tuple(result.events)==tuple(new)
            assert all(e.evidence.opaque_spans is None for e in result.events.values())
            for row in result.rows:
                assert row.base.evidence.opaque_spans is not None
                assert '_opaque_spans' not in row.base.state
                assert row.base.state is not result.events[row.base.source_index].state
                removed_old,removed_new=set(),set()
                proof_old=previous._prove_source_fragment_visibility(old_rows[result.rows.index(row)],removed_old)
                proof_new=current._prove_source_fragment_visibility(row,removed_new)
                assert (proof_old,removed_old)==(proof_new,removed_new),(name,'phase proof')
            comparisons.append(dict(case=name,order=order,initial_state=initial))

spans=[[10.,11.],[12.,14.]]
evidence=current.EventEvidence(original_contour_points=[[0,0],[1,1]],opaque_spans=spans)
spans[0][0]=0;spans.append([0,99])
check('span inputs deeply frozen',evidence.opaque_spans==((10.,11.),(12.,14.)))
try:evidence.opaque_spans=()
except FrozenInstanceError:check('visibility evidence frozen',True)
else:raise AssertionError('mutable evidence')
check('empty visibility differs from absent',current.EventEvidence(opaque_spans=()).opaque_spans==()
      and current.EventEvidence().opaque_spans is None)
events,doc=source(current,('',),'original','resolved')
e=next(iter(events.values()))
e.evidence=evidence
before=deepcopy(vars(e))
check('evidence excluded from ASS fields',e.fields()==current.replace_event(e,evidence=current.EventEvidence()).fields())
check('evidence excluded from grouping',current.state_key(e)==current.state_key(current.replace_event(e,evidence=current.EventEvidence())))
for name,changes in (
    ('text',dict(text=e.text+'!')),('style',dict(style='Other')),
    ('state',dict(state=dict(e.state))),('defaults',dict(defaults=dict(e.defaults))),
    ('styles',dict(styles=dict(e.styles))),('margin',dict(margin_l='10')),('unit',dict(unit=2))):
    check(name+' replacement clears unproved history',current.replace_event(e,**changes).evidence.opaque_spans is None)
for name,changes in (
    ('trim',dict(start='0:00:11.00',start_s=11)),
    ('extend',dict(end='0:00:15.00',end_s=15)),('layer',dict(layer='99')),
    ('effect',dict(effect='')),('index',dict(source_index=999))):
    changed=current.replace_event(e,**changes)
    check(name+' retains absolute source history without retiming',changed.evidence is evidence
          and changed.evidence.opaque_spans==((10.,11.),(12.,14.)))
paint=current.replace_event(e,text=e.text.replace(r'\pos',r'\1a&H80&\pos'),evidence=evidence)
check('explicit paint edit retains historical spans',paint.evidence is evidence and paint.state['1a']==128)
check('replacement does not alter source',vars(e)==before)
normalized=current._normalize_text_result(doc,current.TextProcessingResult(list(events.values()),{}))
check('normalization clears visibility evidence',all(ev.evidence.opaque_spans is None for ev in normalized.events.values()))
check('normalization preserves source evidence',vars(e)==before)
other=current.replace_event(e,start='0:00:12.00',start_s=12,evidence=current.EventEvidence())
row=current.TextRow(e,[],paint_rows=[[other]])
check('missing profile falls back to row base interval',tuple(current._index_source_fragment_visibility(row))==(((10.,14.),),))
empty=current.replace_event(other,evidence=current.EventEvidence(opaque_spans=()))
row.paint_rows=[[empty]]
check('empty profile is not treated as absent',tuple(current._index_source_fragment_visibility(row))==((),))
parsed,doc=source(current,('',),'original','empty')
result=current.collect_source_text_rows(parsed,set())
check('working opacity remains separate from visibility history',all(
    e.evidence.opaque_spans is None for e in result.events.values()))
check('whole-cue spans use absolute source timing',all(
    row.base.evidence.opaque_spans==((10.,14.),) for row in result.rows))
row=result.rows[0];original=deepcopy(vars(result.events[row.base.source_index]))
row.base.state['fs']=999
check('row paint cannot change returned working formatting',vars(result.events[row.base.source_index])==original)
tree=ast.parse((ROOT/'simplify_ass.py').read_text())
check('legacy visibility key removed from production',not any(
    isinstance(n,ast.Constant) and n.value=='_opaque_spans' for n in ast.walk(tree)))
report=dict(version=current.__version__,reference_version=previous.__version__,
    comparisons=len(comparisons),scenarios=len(CASES),collector_inputs_unchanged=True,
    resolved_working_events_identical=True,row_evidence_and_phase_selection_identical=True,
    ownership_checks=len(checks),checks=checks,cases=comparisons)
(ROOT/'validation/source-visibility-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(comparisons),'source-collection comparisons;',len(checks),'ownership and replacement checks passed')

