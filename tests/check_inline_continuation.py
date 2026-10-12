#!/usr/bin/env python3
"""Compare migrated literal readers and their continuation traces with v158."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
import importlib.util,json,random,sys
import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields,static_span_comparison_fields,resolve_test_event,override_comparison_state

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inline_reference',ROOT/'test-data/simplify_ass-v158-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
PRIVATE={'_reset_style','_alignment_set'}
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def clean(state):return {k:v for k,v in state.items() if k not in PRIVATE}
def history(state):return (state.get('_reset_style'),state.get('_alignment_set'))
def snapshot(value):
    if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
    if type(value).__name__=='StaticSpanSignature':return snapshot(static_span_comparison_fields(value))
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

DEFAULT={**current.DEFAULT_STATE,'fs':40,'fn':'Arial','an':5,'bord':2,'shad':1}
STYLES={'Default':DEFAULT,'Other':{**DEFAULT,'fs':60,'fn':'Other Font','an':7,'bord':4,'shad':3},
        'Same':DEFAULT.copy(),'other':{**DEFAULT,'fs':30,'fn':'Lowercase','an':1}}
def event(module,text,styles):
    e=module.Event('Dialogue','0','0:00:01.00','0:00:03.00','Default','',
                   '0','0','0','',text,1.,3.,0,defaults=deepcopy(DEFAULT),styles=deepcopy(styles),
                   measurement=module.DocumentMeasurementContext((640.,360.),2))
    resolve_test_event(module,e)
    return e

def traced(module,action,*,isolated=True,canonical=False):
    trace=[]
    if module is previous and not canonical:
        real=module.apply_tag
        def watched(state,name,value,styles,default,event_tags=True):
            before=(deepcopy(clean(state)),history(state))
            out=real(state,name,value,styles,default,event_tags)
            trace.append((name,value,before,(deepcopy(clean(state)),history(state)),event_tags))
            return out
        with patch.object(module,'apply_tag',watched):out=action()
    else:
        real=module.apply_override
        def watched(state,name,value,styles,default,continuation,*,event_tags=True):
            check('clean literal evaluation buffer',not PRIVATE & state.keys())
            before=(deepcopy(state),(continuation.reset_style,continuation.alignment_set))
            successor=real(state,name,value,styles,default,continuation,event_tags=event_tags)
            check('clean literal successor',not PRIVATE & state.keys())
            trace.append((name,value,before,(deepcopy(state),(successor.reset_style,successor.alignment_set)),event_tags))
            return successor
        with patch.object(module,'apply_override',watched):
            if isolated:
                with patch.object(module,'apply_tag',create=True,side_effect=AssertionError('literal reader used compatibility adapter')):out=action()
            else:out=action()
    return out,trace

bodies=[
    'AB',r'{\rOther}{\fn}A{\fnArial}{\fn}B',r'{\rOther}A{\fn}B',
    r'{\rMissing}{\fn}{\fs}A',r'{\rOther}{\r}{\fn}{\fs}A',
    r'{\an0}{\rOther}{\an2}A{\r}{\an7}B',r'{\a12}A{\rOther}{\a1}B',
    r'{\pos(10,20)}{\rOther}{\pos(30,40)}A',
    r'{\rOther\1a&H80&}A{\r}B',r'{\1a&H00&}A{\1a&H80&}B',
    r'{\1a&HFF&}A{\3a&H80&}B',r'{\rOther}A{\fnOther Font}B',
    r'{\rOther}{\fn}A{}{\fnArial} {\fn}B{\fsp0}',
    r'{\rOther\an0}A{\rMissing\fs+2\fn}B',
    r'{\t(0,100,\1a&HFF&)}A',r'{\fad(20,30)}A',r'{\kf10}A',
    r'{\p1}m 0 0 l 10 10{\p0}A',r'{\org(1,2)\frz0}A{\rOther}B',
    r'{\org(1,2)}A{\frz20}B',r'{\rOther\bord\xbord8}A{\bord2}B',
    r'{\q0\rOther}A{\q2}B',r'{\clip(0,0,10,10)}A{\iclip(1,2,3,4)}B',
    '',r'{\rOther}',r'{\rOther}{\fn}{\fnArial}A{\fn}B',r'{\rOther} {\fn}B']
rng=random.Random(159)
tags=[r'\r',r'\rOther',r'\rSame',r'\rMissing',r'\rother',r'\an0',r'\an7',r'\a12',r'\fs',r'\fs+2',
      r'\fn',r'\fnArial',r'\1a&H80&',r'\3a&HFF&',r'\alpha&H00&',r'\1c&H123456&',r'\bord',r'\xbord8',r'\q2']
for i in range(180):
    bodies.append(''.join('{'+''.join(rng.choices(tags,k=rng.randint(0,4)))+'}'+rng.choice(['A','B',' ','','AB'])
                          for _ in range(rng.randint(1,6))))
font_cases=[r'{\rOther}{\fn}A{\fnArial}B{\fn}C',r'{\rMissing}{\fn}A{\fnArial}B',
            r'{\an0}{\rOther}{\an7\fn}A{\fnArial} B{\fn}C']
for i in range(120):
    font_cases.append('{'+rng.choice(tags[:9])+r'\rOther}' + ''.join(
        rng.choice([r'{\fn}',r'{\fnArial}','{}',r'{\fnOther Font}'])+rng.choice(['A','B',' ','','AB']) for _ in range(6)))
for empty_style in (False,True):
    styles=deepcopy(STYLES)
    if empty_style:styles['']={**DEFAULT,'fn':'Empty named style','fs':75,'an':8}
    for i,text in enumerate(bodies+font_cases):
        borrowed=deepcopy((DEFAULT,styles))
        old,old_trace=traced(previous,lambda:previous.effective_state(text,DEFAULT,styles))
        result,new_trace=traced(current,lambda:current.evaluate_effective_state(text,DEFAULT,styles))
        label=f'{empty_style}:{i}'
        check(label+' effective formatting',result.formatting==clean(old))
        check(label+' formatting insertion order',list(result.formatting)==list(clean(old)))
        check(label+' effective continuation',(result.continuation.reset_style,result.continuation.alignment_set)==history(old))
        check(label+' ordered trace',old_trace==new_trace)
        check(label+' projection API',current.effective_state(text,DEFAULT,styles)==clean(old))
        check(label+' complete cache history',override_comparison_state(result)==old)
        check(label+' borrowed defaults/styles',borrowed==(DEFAULT,styles))
        result.formatting['fs']=999
        check(label+' owned result buffer',DEFAULT['fs']==40 and current.effective_state(text,DEFAULT,styles)==clean(old))
        for name in ('literal_font_spans','has_translucent_paint','static_object_key'):
            outputs=[]
            for module in (previous,current):
                e=event(module,text,styles);before=deepcopy(snapshot(e))
                action=(lambda:getattr(module,name)(e,e.styles,allow_unpositioned=True)) if name=='static_object_key' else (lambda:getattr(module,name)(e))
                out,trace=traced(module,action,canonical=name=='static_object_key')
                check(label+name+' input ownership',before==snapshot(e))
                outputs.append((snapshot(out),trace))
                if module is current and name=='static_object_key' and out:
                    check(label+' clean signatures',all(not PRIVATE & dict(signature.formatting).keys() for signature,_,_ in out[-1]))
            check(label+name+' result/trace parity',outputs[0]==outputs[1])

# Header continuation must survive generated inline tag replay, including base
# border/shadow tags clearing axis overrides before the next fragment.
span_tags=('fn','fs','an','bord','xbord','ybord','shad','xshad','yshad','1c','1a')
for i,header in enumerate((r'{\rOther\an0}',r'{\rMissing\an7}',r'{\rOther}{\fn}',r'{\rOther\r}',r'{\an0\rOther\xbord8}')):
    paints=[{**DEFAULT,'fn':'','fs':0,'an':2,'bord':3,'xbord':8,'ybord':7},
            {**DEFAULT,'fn':'Arial','fs':48,'an':7,'bord':2,'xbord':8,'ybord':7,'shad':2,'xshad':4,'yshad':3},
            {**DEFAULT,'fn':'','fs':40,'an':5,'1c':'123456','1a':128}]
    outputs=[]
    for module in (previous,current):
        chosen=event(module,header+'ABC',STYLES);before=deepcopy(snapshot((chosen,paints)))
        out,trace=traced(module,lambda:module.render_caption_spans(header,['A','B','C'],' A B C ',paints,span_tags,chosen))
        check(str(i)+' renderer input ownership',before==snapshot((chosen,paints)))
        outputs.append((out,trace))
    check(str(i)+' renderer output/continuation parity',outputs[0]==outputs[1])

# Exercise the two inline consumers that also call unrelated legacy machinery.
for i,text in enumerate(bodies[:27]):
    outputs=[]
    for module in (previous,current):
        e=event(module,text,STYLES);before=deepcopy(snapshot(e))
        with patch.object(module,'simplify_visual_text',return_value=(text,0,0)):
            out,trace=traced(module,lambda:module.compact_static_overrides([e],2),isolated=False)
        outputs.append((snapshot(out),trace))
        check(str(i)+' compaction input ownership',before==snapshot(e))
    check(str(i)+' origin compaction parity',outputs[0]==outputs[1])

for i,text in enumerate((r'{\rOther\pos(100,100)}A{\bord2\xbord8}B{\shad2\xshad4}C',
                         r'{\an0\rOther\pos(100,100)}A{\1c&H123456&\blur4}B',
                         r'{\rOther\pos(100,100)}A{\fs20}B')):
    outputs=[]
    for module in (previous,current):
        e=event(module,text,STYLES);before=deepcopy(snapshot(e));captured=[]
        context=module._prepare_shared_interval_context([e],{0:'ABC'},None)
        def bounds(probe,metric):
            captured.append(clean(probe.state));return (10.,20.,30.,40.)
        with patch.object(module,'caption_bounds',bounds):
            out,trace=traced(module,lambda:module._shared_interval_bounds(context,e),isolated=False)
            again=module._shared_interval_bounds(context,e)
        check(str(i)+' bounds cache',out==again and len(captured)<=1)
        check(str(i)+' bounds input ownership',before==snapshot(e))
        outputs.append((out,captured,trace))
    check(str(i)+' inline bounds parity',outputs[0]==outputs[1])

# Held-glyph proof reads the emitted per-character paint without annotating rows
# or events. Include accepted/rejected rows and a reset across literal glyphs.
accepted=0
for i,(style_tags,inline,virtual,animated) in enumerate([
        ('','','',True),(r'\rOther',r'{\fnOther Font}',False,True),
        (r'\rOther\an0',r'{\fn}',False,True),
        ('',r'{\1c&H123456&}',False,True),('',r'{\fs60}',False,True),
        ('','',True,True),('','',False,False)]):
    outputs=[]
    for module in (previous,current):
        pieces=[]
        for j,char in enumerate('ABCD'):
            e=event(module,'{'+style_tags+r'\an5\shad0\pos('+str(100+20*j)+',100)}'+char,STYLES)
            e.source_index=j
            pieces.append((e,char,module.get_pos(e.text)))
        header='{'+style_tags+r'\an5\shad0\pos(130,100)}'
        base=event(module,header+'AB'+inline+'CD',STYLES)
        row=module.TextRow(base,pieces,virtual=bool(virtual));before=deepcopy(snapshot(row))
        out,trace=traced(module,lambda:module._collect_covered_held_glyphs([row],set(range(4)) if animated else set()))
        check(str(i)+' held glyph row ownership',before==snapshot(row))
        outputs.append((snapshot(out),trace))
        if module is current and out:accepted+=1
    check(str(i)+' held glyph proof parity',outputs[0]==outputs[1])
check('held glyph proof exercised acceptance',accepted>0)

e=event(current,r'{\rOther}{\fn}A{\fnArial}B{\fn}C',STYLES)
check('font reset continues over literals',current.literal_font_spans(e)==(('A','Other Font'),('B','Arial'),('C','Other Font')))
result=current.evaluate_effective_state(r'{\an0}{\rOther}A{\an2}',DEFAULT,STYLES)
check('invalid first alignment survives reset and literal',result.formatting['an']==5 and result.continuation.alignment_set is True)
try:result.continuation.alignment_set=False
except FrozenInstanceError:check('continuation immutable',True)
else:raise AssertionError('mutable continuation')
check('empty/default fallback',current.effective_state('A',{},STYLES)==clean(previous.effective_state('A',{},STYLES)))
check('undefined style fallback',current.effective_state(r'{\rMissing\fn\fs}A',{'fs':25},STYLES)==clean(previous.effective_state(r'{\rMissing\fn\fs}A',{'fs':25},STYLES)))
report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
            literal_cases=len(bodies+font_cases),empty_named_style_modes=2,override_trace_parity=True,
            borrowed_inputs_unchanged=True,formatting_buffers_owned=True)
(ROOT/'validation/inline-continuation-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'inline continuation checks passed')
