#!/usr/bin/env python3
"""Compare document measurement ownership and consumers with v156."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from copy import deepcopy
from dataclasses import FrozenInstanceError
import ast, contextlib, importlib.util, io, json, sys
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
from event_evidence_test_helpers import event_comparison_fields,static_span_comparison_fields

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('measurement_reference',ROOT/'test-data/simplify_ass-v156-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)

STYLES='''[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
Style: Other,Arial,60,7,1,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def raw(info,body=r'{\pos(320,180)}First\nsecond',style='Default'):
    return '[Script Info]\n'+info+'\n'+STYLES+f'Dialogue: 0,0:00:01.00,0:00:04.00,{style},,0,0,0,,{body}\n'

def documents(module,text):
    doc=module.parse_subtitle_document(text)
    with contextlib.redirect_stdout(io.StringIO()):
        prepared=module._prepare_text_document(doc,Path('fixture.ass'))
    return doc,prepared,module._resolve_document_state(doc)

def snapshot(event):return event_comparison_fields(event)
def first(doc):return next(iter(doc.events.values()))
def stripped(value):return {k:v for k,v in value.items() if k not in ('_canvas','_script_wrap_mode')}

def object_signature(key):
    if key is None:return None
    if len(key)==8:
        context=key[-2];metadata=(context.canvas,context.script_wrap_mode)
    else:
        state=dict(key[-1][0][0]);metadata=(state.get('_canvas'),state.get('_script_wrap_mode'))
    runs=tuple((tuple(sorted(stripped(dict(static_span_comparison_fields(signature))).items())),drawing,payload)
               for signature,drawing,payload in key[-1])
    return key[:6]+(metadata,runs)

resolutions=[('',None),('PlayResX: 640',None),('PlayResY: 360',None),
 ('PlayResX: 0\nPlayResY: 360',None),('PlayResX: nan\nPlayResY: inf',None),
 ('PlayResX: bad\nPlayResY: -5',None),('PlayResX: 640\nPlayResY: 360',(640,360)),
 ('playresx: 640.5\nPLAYRESY: 360.5',(640.5,360.5)),
 ('PlayResX: 640\nPlayResY: 360\nPlayResX: 1280\nPlayResY: 720',(1280,720)),
 ('PlayResX: 640\nPlayResY: 360\nPlayResX: nan\nPlayResY: nope',(640,360)),
 ('PlayResX: 640\nPlayResY: 360\n[Other]\nPlayResX: 2000',(640,360))]
metric=current.FontMetrics([ROOT/'fonts'])
old_metric=previous.FontSpacing([ROOT/'fonts'])
check('real measurement font available',metric.available)
for i,(info,canvas) in enumerate(resolutions):
    for wrap in range(4):
        for q in ('',r'\q0',r'\q1',r'\q2',r'\q3'):
            body='{'+r'\pos(320,180)'+q+r'}First\nsecond{\rOther\fs}third'
            text=raw(info+'\n[Script Info]\nWrapStyle: '+str(wrap),body)
            prior=documents(previous,text);docs=documents(current,text)
            for phase,(old,doc) in enumerate(zip(prior,docs)):
                name=f'resolution {i} wrap {wrap} {q} phase {phase}'
                e=first(doc);oe=first(old)
                check(name+' context',e.measurement.canvas==canvas and
                      e.measurement.script_wrap_mode==(wrap if phase==2 else None))
                check(name+' event parity',snapshot(e)==snapshot(oe))
                check(name+' unit parity',e.unit==oe.unit)
                check(name+' shared immutable context',e.measurement is doc.measurement)
                check(name+' formatting clean',all(not {'_canvas','_script_wrap_mode'} & st.keys()
                    for st in [e.state,e.defaults,*e.styles.values()]))
                check(name+' static signature',object_signature(current.static_object_key(e,e.styles))==
                      object_signature(previous.static_object_key(oe,oe.styles)))
                if phase==2:
                    check(name+' caption bounds',current.caption_bounds(e,metric)==previous.caption_bounds(oe,old_metric))
                before=deepcopy(snapshot(e))
                for changes in ({'end':'0:00:05.00','end_s':5},
                                {'text':r'{\rOther\q2\pos(100,100)}Changed\nline'},
                                {'style':'Other'}, {'style':'Missing'}, {'state':{'fs':25}},
                                {'text':r'{\rUnknown\fs+2}Reset'}):
                    changed=current.replace_event(e,**changes);older=previous.replace_event(oe,**changes)
                    # Direct state replacement intentionally supplied a clean dict
                    # in both builds; context remains on the new event.
                    if 'state' in changes:
                        check(name+' raw state edit context',changed.measurement is e.measurement and changed.state==changes['state'])
                    else:
                        check(name+' replacement parity '+repr(changes),snapshot(changed)==snapshot(older))
                        check(name+' replacement context '+repr(changes),changed.measurement is e.measurement)
                check(name+' no input mutation',before==snapshot(e))

for info,canvas in resolutions:
    for tags in (r'\an7\pos(0,0)\p1\bord0\shad0',r'\an7\pos(0,0)\p1\bord0\clip(0,0,640,360)',
                 r'\an7\pos(0,0)\p1\bord0\clip(1,0,640,360)',r'\an7\pos(0,0)\p1\bord0\rOther'):
        text=raw(info,'{'+tags+'}m 0 0 l 640 0 640 360 0 360')
        oe=first(documents(previous,text)[2]);e=first(documents(current,text)[2])
        check('fullscreen '+info+tags,current.is_fullscreen_background(e)==previous.is_fullscreen_background(oe))

for info,canvas in resolutions:
    for tags in (r'\pos(320,-500)\yshad680\4c&H0000FF&',r'\pos(-5000,180)\xshad5320',
                 r'\pos(320,180)\yshad50',r'\pos(320,-500)\yshad680\clip(0,0,640,360)',
                 r'\pos(320,-500)\yshad680\frz30',r'\pos(320,-500)\yshad680\4a&HFF&'):
        oe=first(documents(previous,raw(info,'{'+tags+'}Shadow'))[2])
        e=first(documents(current,raw(info,'{'+tags+'}Shadow'))[2])
        check('shadow rendering '+info+tags,current.render_simplified_caption(e.state,'Shadow',measurement=e.measurement)==
              previous.render_simplified_caption(oe.state,'Shadow'))

# Same formatting with different document context must keep former matching distinctions.
e=first(documents(current,raw('PlayResX: 640\nPlayResY: 360'))[2])
for context in (current.DocumentMeasurementContext(),current.DocumentMeasurementContext((640,360)),
                current.DocumentMeasurementContext((640,360),2),current.DocumentMeasurementContext((1280,720),0)):
    changed=current.replace_event(e,measurement=context)
    check('context participates in static matching '+repr(context),
          (current.static_object_key(e,e.styles)==current.static_object_key(changed,changed.styles))==(context==e.measurement))
try:e.measurement.canvas=(1,1)
except FrozenInstanceError:check('context immutable',True)
else:raise AssertionError('Mutable measurement context')

# Later Script Info also resolves context for earlier events, as style parsing did.
late=raw('',r'{\pos(320,180)}First\nsecond')+'[Script Info]\nPlayResX: 640\nPlayResY: 360\nWrapStyle: 2\n'
for phase,(old,doc) in enumerate(zip(documents(previous,late),documents(current,late))):
    check('late metadata parity '+str(phase),snapshot(first(old))==snapshot(first(doc)))

# Every production caption rendering call must propagate an event's context.
tree=ast.parse((ROOT/'simplify_ass.py').read_text())
render_calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
              and n.func.id=='render_simplified_caption']
check('all 24 render paths propagate context',len(render_calls)==24 and
      all(any(k.arg=='measurement' for k in call.keywords) for call in render_calls))
check('no legacy measurement keys in production',(ROOT/'simplify_ass.py').read_text().find('"_canvas"')==-1 and
      '_script_wrap_mode' not in (ROOT/'simplify_ass.py').read_text())
report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
            resolution_cases=len(resolutions),wrap_modes=4,explicit_q_cases=5,renderer_paths=len(render_calls))
(ROOT/'validation/measurement-context-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'measurement context checks passed')
