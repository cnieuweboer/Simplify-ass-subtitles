#!/usr/bin/env python3
"""Compare frozen headers and verify explicit evidence accumulation and ownership."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
import importlib.util
import json
import sys
import simplify_ass as current
from event_evidence_test_helpers import selection_comparison_fields
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('freeze_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
TAGS=(
    '',r'\fs+2',r'\fs-2',r'\rOther\fs+2',r'\r\fs45',r'\rMissing\fnArial',
    r'\alpha&HFF&',r'\1a&H80&',r'\1a&HFF&\t(0,100,\1a&H00&)',
    r'\t(100,100,\1a&HFF&)',r'\t(100,100,\1a&HFF&)\t(200,200,\1a&H00&)',
    r'\alpha&HFF&\t(100,100,\rOther)',r'\blur8\be4',r'\t(0,1000,\blur8)',
    r'\bord0\shad0',r'\bord2\xbord3\ybord4',r'\bord2',
    r'\move(10,20,30,40)',r'\move(10,20,30,40,0,100)',
    r'\pos(10,20)\frz20\t(0,100,\frz0)',r'\frz0\t(0,1000,\frz720)',
    r'\fscx0\t(0,1000,\fscx100)',r'\p1\t(0,1000,\frz30)',
    r'\clip(0,0,100,100)\t(0,1000,\1c&HFF0000&)',
    r'\t(bad,\fs50)',r'\t(0,1000)',r'\t(0,1000,\pos(90,50)\an7\fs+2)',
    r'\t(0,1000,\1c&H123456&)\t(1000,2000,\1c&HABCDEF&)',
)
comparisons=[]
for tags in TAGS:
    for duration in (-1.,0.,.1,1.,3.):
        for max_blur in (0.,2.):
            for upright,crossings in ((False,False),(False,True),(True,False),(True,True)):
                for seed_mode in ('none','empty','seeded'):
                    results=[]
                    for module in (previous,current):
                        default={**module.DEFAULT_STATE,'fn':'Arial','fs':40,'pos':(10.,20.)}
                        styles={'other':{**default,'fs':50,'1c':'123456'}}
                        initial={**default,'xbord':5,'ybord':6,'xshad':3,'yshad':4}
                        opaque=None if seed_mode=='none' else [] if seed_mode=='empty' else [(-100.,0.)]
                        settled=None if seed_mode=='none' else [] if seed_mode=='empty' else [{'seed':True}]
                        before=deepcopy((initial,default,styles,opaque,settled))
                        result=module.freeze_block(tags,duration,initial,default,styles,max_blur,
                            opaque,settled,prefer_upright=upright,upright_crossings=crossings)
                        assert before[:3]==(initial,default,styles),'borrowed formatting changed'
                        assert before==(initial,default,styles,opaque,settled),'borrowed evidence changed'
                        if seed_mode=='seeded':
                            assert result.selection.settled_states[0] is settled[0],'seed snapshot identity changed'
                        results.append((result.text,selection_comparison_fields(result.selection)))
                    assert results[0]==results[1],(tags,duration,max_blur,upright,crossings,seed_mode)
                    comparisons.append(dict(tags=tags,duration=duration,max_blur=max_blur,
                        prefer_upright=upright,upright_crossings=crossings,seed_mode=seed_mode))
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
base={**current.DEFAULT_STATE,'fs':40,'pos':(10.,20.)}
opaque=[(-100.,0.)];seed={'seed':True};settled=[seed]
before=deepcopy((base,opaque,settled))
selected=current.select_static_state(base,[],{0.,1000.},{},base,
    prior_opaque_spans=opaque,prior_settled_states=settled)
check('early return preserves base dictionary identity',selected.state is base)
check('early return leaves seeds unchanged',before==(base,opaque,settled))
check('early return appends rather than merges',selected.opaque_spans==((-100.,0.),(0.,1000.)))
check('seed snapshot identity retained',selected.settled_states[0] is seed)
check('new static snapshot is independent',selected.settled_states[1] is not base
      and selected.settled_states[1]==base)
animated=current.select_static_state(base,[(0.,1000.,1.,[])],{0.,1000.},{},base,
    prior_opaque_spans=opaque,prior_settled_states=settled)
check('sampled touching span merges with seed',animated.opaque_spans==((-100.,1000.),))
check('sampled collection leaves borrowed seeds unchanged',before==(base,opaque,settled))
check('sampled return copies formatting',animated.state is not base)
check('sample snapshots distinct from chosen formatting',all(
    state is not animated.state for state in animated.settled_states))
for gap,merge in ((.0000005,True),(.000002,False)):
    result=current.select_static_state(base,[(0.,1000.,1.,[])],{0.,1000.},{},base,
        prior_opaque_spans=[(-100.,-gap)])
    check('strict touching tolerance '+str(gap),len(result.opaque_spans)==(1 if merge else 2))
disabled=current.select_static_state(base,[],set(),{},base)
check('disabled evidence remains None',disabled.opaque_spans is None and disabled.settled_states is None)
empty=current.select_static_state(base,[],set(),{},base,prior_opaque_spans=(),prior_settled_states=())
check('enabled empty evidence stays distinct',empty.opaque_spans==() and empty.settled_states==())
one=current.select_static_state(base,[],{100.},{},base,prior_opaque_spans=(),prior_settled_states=())
check('single boundary preserves zero-length opaque span',one.opaque_spans==((100.,100.),))
check('single boundary does not record settled state',one.settled_states==())
first=current.freeze_block('',1,base,base,{},0,prior_opaque_spans=(),prior_settled_states=())
second=current.freeze_block(r'\t(0,1000,\blur4)',1,base,base,{},0,
    prior_opaque_spans=first.selection.opaque_spans,prior_settled_states=first.selection.settled_states)
check('explicit repeated accumulation preserves overlapping spans',
      second.selection.opaque_spans==((0.,1000.),(0.,1000.)))
check('explicit repeated accumulation retains all settled snapshots',len(second.selection.settled_states)==2)
check('second call leaves first result intact',first.selection.opaque_spans==((0.,1000.),)
      and len(first.selection.settled_states)==1)
freeze=current.freeze_block(r'\blur8\be4',1,base,base,{},2,
    prior_settled_states=())
check('selected formatting retains blur clamp',freeze.selection.state['blur']==2
      and freeze.selection.state['be']==2)
check('settled snapshot retains pre-clamp paint',freeze.selection.settled_states[0]['blur']==8
      and freeze.selection.settled_states[0]['be']==4)
check('frozen selection state is not borrowed initial state',freeze.selection.state is not base)
calls=[];original=current.select_static_state
def recorded(*args,**kwargs):
    selection=original(*args,**kwargs);calls.append((args[0],selection));return selection
with patch.object(current,'select_static_state',side_effect=recorded):
    frozen=current.freeze_block('',1,base,base,{},0)
check('freeze passes through exact selection record',frozen.selection is calls[0][1])
check('freeze early selection retains parsed base identity',frozen.selection.state is calls[0][0])
check('freeze parsed base is independent of initial state',calls[0][0] is not base)
try:selected.state={}
except FrozenInstanceError:check('selection fields cannot be rebound',True)
else:raise AssertionError('mutable result fields')
selected.settled_states[1]['fs']=999
check('editing returned snapshot leaves input formatting unchanged',base['fs']==40)
check('editing returned snapshot leaves input seed unchanged',settled==[seed] and seed=={'seed':True})
report=dict(version=current.__version__,reference_version=previous.__version__,
    comparisons=len(comparisons),ownership_checks=len(checks),checks=checks,
    formatting_and_complete_accumulated_evidence_identical=True,
    caller_formatting_and_evidence_seeds_unchanged=True,cases=comparisons)
(ROOT/'validation/frozen-block-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(comparisons),'frozen-block comparisons;',len(checks),'ownership and identity checks passed')

