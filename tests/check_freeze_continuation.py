#!/usr/bin/env python3
"""Compare freeze/selection/sampling formatting and history against immutable v159."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
import importlib.util,json,math,random,sys
import simplify_ass as current
from event_evidence_test_helpers import selection_comparison_fields,override_comparison_state,override_test_evaluation
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('freeze_continuation_reference',ROOT/'test-data/simplify_ass-v159-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
PRIVATE={'_reset_style','_alignment_set'}
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def snapshot(value):
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
def legacy(result):return override_comparison_state(result)
DEFAULT={**current.DEFAULT_STATE,'fn':'Arial','fs':40,'an':5,'pos':(100.,50.)}
STYLES={'Other':{**DEFAULT,'fn':'Other Font','fs':60,'an':7,'bord':4},
        'Same':DEFAULT.copy(),'other':{**DEFAULT,'fn':'Lowercase','fs':30,'an':1}}
SEEDS=[{}, {'_reset_style':''},{'_reset_style':'Other'},{'_reset_style':'Missing'},
       {'_alignment_set':True},{'_alignment_set':False},{'_reset_style':'Other','_alignment_set':False},
       {'_reset_style':'other','_alignment_set':True},{'_alignment_set':.25}]
TIMES=[-1.,0.,50.,100.,250.,500.,750.,1000.,1500.]
TRANSFORMS=[[],[(0.,1000.,1.,[])],
    [(0.,1000.,1.,[('r','Other'),('fs','+2'),('fn','')])],
    [(0.,1000.,1.,[('fs','+2'),('r','Other'),('fs','')])],
    [(0.,1000.,1.,[('an','0'),('r','Other'),('an','2')])],
    [(0.,1000.,1.,[('a','12'),('r','Missing'),('a','4')])],
    [(0.,1000.,1.,[('r','Other')]),(500.,1500.,1.,[('fs',''),('fn','')])],
    [(0.,500.,1.,[('r','Other')]),(500.,1000.,1.,[('r',''),('fs','+2')])],
    [(0.,500.,1.,[('r','Missing')]),(500.,1000.,1.,[('fn','')])],
    [(0.,1000.,2.,[('fs','+2')])],[(0.,1000.,1.,[('fs','-10')])],
    [(0.,1000.,1.,[('fs','60'),('fs','+2')])],
    [(0.,1000.,1.,[('pos','(10,20)'),('an','7')])],
    [(0.,1000.,1.,[('bord','2'),('xbord','8'),('shad','2'),('xshad','4')])],
    [(0.,1000.,1.,[('1c','&H123456&'),('alpha','&H80&')])],
    [(0.,1000.,1.,[('frz','720')])],[(0.,1000.,1.,[('frz','bad')])],
    [(100.,100.,1.,[('r','Other'),('fs','')])],
    [(1000.,100.,1.,[('fs','80')])],
    [(0.,500.,1.,[('clip','(0,0,100,100)')]),(500.,1000.,1.,[('iclip','(1,2,3,4)')])]]
rng=random.Random(160)
tags=[('r',''),('r','Other'),('r','Missing'),('r','other'),('fs',''),('fs','+2'),('fs','-10'),('fs','60'),
      ('fn',''),('fn','Arial'),('an','0'),('an','7'),('a','12'),('bord','2'),('xbord','8'),
      ('shad','0'),('xshad','3'),('pos','(120,70)'),('org','(1,2)'),('q','2'),('p','0'),
      ('1c','&H123456&'),('1a','&H80&'),('frz','720'),('frz','0')]
for i in range(75):
    TRANSFORMS.append([(rng.choice([0.,100.,500.]),rng.choice([100.,500.,1000.]),rng.choice([.5,1.,2.]),
                        rng.choices(tags,k=rng.randint(0,6))) for _ in range(rng.randint(1,4))])

# Canonical samplers never call the dictionary adapter, including fallbacks.
real=current.apply_override
def watched(state,name,value,styles,default,continuation,**options):
    check('clean canonical sampling buffer',not PRIVATE & state.keys())
    successor=real(state,name,value,styles,default,continuation,**options)
    check('clean canonical successor',not PRIVATE & state.keys())
    return successor

sampler_cases=selection_cases=freeze_cases=0
with (patch.object(current,'apply_tag',create=True,side_effect=AssertionError('migrated freeze path used legacy adapter')),
      patch.object(current,'apply_override',watched)):
    for empty_style in (False,True):
        styles=deepcopy(STYLES)
        if empty_style:styles['']={**DEFAULT,'fn':'Empty named style','fs':75,'an':8}
        for seed in SEEDS:
            base={**DEFAULT,**seed};evaluation=override_test_evaluation(current,base)
            borrowed=deepcopy(snapshot((base,styles,evaluation)))
            for i,transforms in enumerate(TRANSFORMS):
                for time_mode,times in [('ordered',TIMES),('reverse',TIMES[::-1]),('repeat',[0.,500.,500.,1000.])]:
                    prior=list(previous.sample_transform_states(base,transforms,times,styles,DEFAULT))
                    sampled=list(current.sample_transform_states(evaluation.formatting,transforms,times,styles,DEFAULT,
                                                                  continuation=evaluation.continuation))
                    label=f'{empty_style}:{seed}:{i}:{time_mode}'
                    check(label+' batch values/history',snapshot(prior)==snapshot([legacy(v) for v in sampled]))
                    check(label+' batch snapshots independent',len({id(v.formatting) for v in sampled})==len(sampled))
                    for at,result in zip(times,sampled):
                        old=previous.sample_transform_state(base,transforms,at,styles,DEFAULT)
                        one=current.sample_transform_state(evaluation.formatting,transforms,at,styles,DEFAULT,
                                                           continuation=evaluation.continuation)
                        check(label+str(at)+' single values/history',snapshot(old)==snapshot(legacy(one)))
                        check(label+str(at)+' result owns formatting',one.formatting is not evaluation.formatting)
                        check(label+str(at)+' history outside formatting',not PRIVATE & result.formatting.keys())
                    check(label+' borrowed seeds unchanged',borrowed==snapshot((base,styles,evaluation)))
                    sampler_cases+=1
                if i>=20:continue
                boundaries={0.,100.,500.,1000.}
                for upright,crossings in ((False,False),(False,True),(True,False),(True,True)):
                    options=dict(prior_opaque_spans=((-100.,0.),),prior_settled_states=({'seed':True},),
                                 prefer_upright=upright,upright_crossings=crossings)
                    before=deepcopy(snapshot(options))
                    old=previous.select_static_state(base,transforms,boundaries,styles,DEFAULT,**options)
                    selected=current.select_static_state(evaluation.formatting,transforms,boundaries,styles,DEFAULT,
                                                        continuation=evaluation.continuation,**options)
                    check(label+' selection formatting/history/evidence',snapshot(selection_comparison_fields(old))==
                          snapshot(selection_comparison_fields(selected)))
                    check(label+' selection borrowed evidence',before==snapshot(options))
                    check(label+' selected formatting clean',not PRIVATE & selected.state.keys())
                    check(label+' collected snapshots clean',all(not PRIVATE & v.keys() for v in selected.settled_states[1:]))
                    check(label+' seed snapshot identity',selected.settled_states[0] is options['prior_settled_states'][0])
                    selection_cases+=1
            for header in ('',r'\rOther\fn\fs',r'\rMissing\fn\fs',r'\an0\rOther\an7',
                           r'\t(0,1000,\an0\pos(120,70)\fs+2)',r'\rOther\t(0,1000,\r\fs+2)',
                           r'\frz20\t(0,1000,\rOther\frz720)',r'\move(100,50,120,70)'):
                initial=base;working=evaluation.formatting;continuation=evaluation.continuation
                for tail in (header,r'\fn\fs\an2',r'\r\fs+2',r'\rOther\an0\fn'):
                    inputs=deepcopy(snapshot((initial,working,continuation,styles)))
                    old=previous.freeze_block(tail,1.,initial,DEFAULT,styles,2.,prefer_upright=True,
                                              prior_opaque_spans=(),prior_settled_states=())
                    result=current.freeze_block(tail,1.,working,DEFAULT,styles,2.,prefer_upright=True,
                                                 continuation=continuation,prior_opaque_spans=(),prior_settled_states=())
                    check('continued frozen text/history/evidence '+repr((empty_style,seed,header,tail,old.text,result.text,
                          selection_comparison_fields(old.selection),selection_comparison_fields(result.selection))),old.text==result.text and
                          snapshot(selection_comparison_fields(old.selection))==snapshot(selection_comparison_fields(result.selection)))
                    check('freeze borrows formatting/history/styles',inputs==snapshot((initial,working,continuation,styles)))
                    initial=old.selection.state;working=result.selection.state;continuation=result.selection.continuation
                    freeze_cases+=1

# Identity and evidence ownership are distinct from parser continuation.
base=DEFAULT.copy();continuation=current.OverrideContinuation('Other',True)
pose=current.StaticPoseEvidence(True,(('pos',(100.,50.)),));opaque=[(-100.,0.)];seed={'seed':True};settled=[seed]
before=deepcopy((base,opaque,settled))
selected=current.select_static_state(base,[],{0.,1000.},STYLES,DEFAULT,continuation=continuation,
                                     prior_pose=pose,prior_opaque_spans=opaque,prior_settled_states=settled)
check('early return retains base identity',selected.state is base)
check('early return retains continuation identity',selected.continuation is continuation)
check('early return retains pose identity',selected.pose is pose)
check('early return borrows evidence seeds',before==(base,opaque,settled) and selected.settled_states[0] is seed)
check('new evidence snapshot independent',selected.settled_states[1] is not base)
try:selected.continuation.reset_style='Same'
except FrozenInstanceError:check('history immutable',True)
else:raise AssertionError('mutable continuation')
selected.settled_states[1]['fs']=999
check('evidence edits cannot affect chosen state',selected.state['fs']==40 and seed=={'seed':True})

# An absent history slot stays absent under the historical transform commit
# policy; ordered target defaults still use each reset before weighted fs.
sample=current.sample_transform_state(base,[(0.,1000.,1.,[('r','Other'),('fs','+2')])],500.,STYLES,DEFAULT)
check('target reset influences relative size',sample.formatting['fs']==66.)
check('new transform reset history not spuriously committed',sample.continuation.reset_style is None)
sample=current.sample_transform_state(base,[(0.,1000.,1.,[('an','7')])],500.,STYLES,DEFAULT,
                                      continuation=current.OverrideContinuation(alignment_set=False))
check('started transform consumes an existing false latch',sample.continuation.alignment_set is True)
branch=current.OverrideContinuation('Other',False)
left=current.sample_transform_state(base,[(0.,1000.,1.,[('an','7')])],500.,STYLES,DEFAULT,continuation=branch)
right=current.sample_transform_state(base,[(0.,1000.,1.,[('r','Same'),('fn','')])],1000.,STYLES,DEFAULT,continuation=branch)
check('independent branch history',branch==current.OverrideContinuation('Other',False) and
      left.continuation.alignment_set is True and right.continuation.reset_style=='Same' and right.continuation.alignment_set is False)
left.formatting['fs']=999
check('branch formatting independent',right.formatting['fs']==40 and base['fs']==40)

report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
            sampler_cases=sampler_cases,selection_cases=selection_cases,continued_freeze_steps=freeze_cases,
            continuation_seed_modes=len(SEEDS),empty_named_style_modes=2,canonical_adapter_disabled=True,
            selected_history_and_output_preserved=True,borrowed_inputs_unchanged=True)
(ROOT/'validation/freeze-continuation-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'freeze continuation checks passed;',sampler_cases,'sampler cases;',selection_cases,'selection cases;',freeze_cases,'continued freeze steps')
