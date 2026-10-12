#!/usr/bin/env python3
"""Check selected-pose ownership, inline continuation and invalidation against v152."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import ast,contextlib,importlib.util,json,sys
import simplify_ass as current
from event_evidence_test_helpers import selection_comparison_fields
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pose_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
KEYS={'_upright_rotation','_sustained_geometry'}
def canonical(selection):
    values=selection_comparison_fields(selection)
    if values['settled_states'] is not None:
        values['settled_states']=tuple({k:v for k,v in state.items() if k not in KEYS}
                                       for state in values['settled_states'])
    return values
FIRST=(
    r'\pos(100,50)\frz0\t(0,100,\frz20)\t(100,1000,\frz40)',
    r'\move(100,50,100,100,0,100)\frz0\t(0,100,\frz20)\t(100,1000,\frz40)',
    r'\move(100,50,100,100,0,1000)\frz0\t(0,1000,\frz40)',
    r'\pos(100,100)\fs20\t(0,100,\fs60\fscx120\fscy130\frz20)\t(100,1000,\frz40)',
    r'\pos(100,50)\frz20\t(0,1000,\frz720)',
    r'\pos(100,50)\alpha&HFF&\frz47\t(0,1000,\frz55)',
)
TAIL=(
    '',r'\1c&H123456&',r'\blur4',r'\fs+2',r'\pos(120,70)',
    r'\frz15',r'\p1',r'\p0',r'\clip(0,0,1000,1000)',
    r'\r',r'\rOther',r'\rMissing',r'\rOther\t(0,1000,\frz720)',
    r'\t(0,1000,\rOther)',r'\t(0,1000,\fs60)',
    r'\t(0,1000,\1c&HFF0000&)',r'\t(0,1000,\frz20)',
    r'\t(0,100,\frz-20)\t(100,1000,\frz20)',
)
comparisons=[]
for first in FIRST:
    for tail in TAIL:
        for duration in (.2,1.,2.81):
            for prefer,crossings in ((False,False),(False,True),(True,False),(True,True)):
                for max_blur in (0.,2.):
                    results=[]
                    for module in (previous,current):
                        default={**module.DEFAULT_STATE,'fn':'Arial','fs':40}
                        styles={'other':{**default,'fs':55,'1c':'123456'}}
                        initial=default.copy();pose=None;opaque=();settled=();continuation=None
                        steps=[]
                        for tags in (first,tail):
                            before=deepcopy((initial,default,styles,opaque,settled))
                            kwargs=dict(prefer_upright=prefer,upright_crossings=crossings,
                                prior_opaque_spans=opaque,prior_settled_states=settled)
                            kwargs['prior_pose']=pose
                            if module is current and continuation is not None:
                                kwargs['continuation']=continuation
                            result=module.freeze_block(tags,duration,initial,default,styles,max_blur,**kwargs)
                            assert before==(initial,default,styles,opaque,settled),'borrowed input changed'
                            steps.append((result.text,canonical(result.selection)))
                            initial=result.selection.state
                            opaque=result.selection.opaque_spans;settled=result.selection.settled_states
                            pose=result.selection.pose
                            if module is current:continuation=result.selection.continuation
                            if module is current:
                                assert not KEYS&initial.keys(),'pose in formatting'
                                assert all(not KEYS&state.keys() for state in settled),'pose in sampled formatting'
                        text='{'+first+'}A{'+tail+'}B'
                        visual=module.simplify_visual_text(text,max_blur,duration,default,styles,1,
                            upright_crossings=crossings)
                        results.append((steps,visual))
                    assert results[0]==results[1],(first,tail,duration,prefer,crossings,max_blur)
                    comparisons.append(dict(first=first,tail=tail,duration=duration,
                        prefer_upright=prefer,upright_crossings=crossings,max_blur=max_blur))
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
geometry=[['pos',[100.,50.]],['fs',40.]]
proof=current.StaticPoseEvidence(True,geometry)
geometry[0][1][0]=999;geometry.append(['fn','Other'])
check('protected geometry copies input containers',proof.sustained_geometry==(('pos',(100.,50.)),('fs',40.)))
try:proof.upright_rotation=False
except FrozenInstanceError:check('pose evidence record frozen',True)
else:raise AssertionError('mutable pose record')
try:proof.sustained_geometry[0][1][0]=0
except TypeError:check('protected coordinates immutable',True)
else:raise AssertionError('mutable coordinates')
check('empty protected geometry distinct from no proof',
    current.StaticPoseEvidence(True,()).sustained_geometry==()
    and current.StaticPoseEvidence(True).sustained_geometry is None)
base={**current.DEFAULT_STATE,'fn':'Arial','fs':40,'pos':(100.,50.)}
before=deepcopy(base)
unchanged=current.select_static_state(base,[],{0.,1000.},{},base,prior_pose=proof)
check('early selection retains original formatting dictionary',unchanged.state is base)
check('explicit unchanged continuation retains proof identity',unchanged.pose is proof)
check('early selection does not contaminate formatting',base==before and not KEYS&base.keys())
plain=current.select_static_state(base,[],{0.,1000.},{},base)
check('independent selection starts without inherited proof',
    not plain.pose.upright_rotation and plain.pose.sustained_geometry is None)
fresh=current.select_static_state(base,[(0.,100.,1.,[('frz','40')])],{0.,100.},{},base,
    prefer_upright=True,prior_pose=proof)
check('short animated selection invalidates stale hold proof',fresh.pose.sustained_geometry is None)
check('recomputed pose does not mutate incoming history',proof.sustained_geometry==(('pos',(100.,50.)),('fs',40.)))
for reset in (r'\r',r'\rOther',r'\rMissing'):
    frozen=current.freeze_block(reset,1,base,base,{'other':{**base,'fs':55}},0,prior_pose=proof)
    check(reset+' clears inherited selection proof',not frozen.selection.pose.upright_rotation
          and frozen.selection.pose.sustained_geometry is None)
paint=current.freeze_block(r'\1c&H123456&',1,base,base,{},0,prior_pose=proof)
check('authored paint continuation preserves selection proof',paint.selection.pose is proof)
motion=FIRST[1]
motion_base={k:v for k,v in base.items() if k!='pos'}
frozen=current.freeze_block(motion,1,motion_base,motion_base,{},0,prefer_upright=True,
    prior_settled_states=())
check('sustained source position outranks crossing fallback',frozen.selection.state['pos']==(100.,100.))
check('sustained position stored separately',dict(frozen.selection.pose.sustained_geometry)['pos']==(100.,100.))
check('selected pose marked upright',frozen.selection.pose.upright_rotation
      and current.unrotated_text_state(frozen.selection.state))
check('newly collected snapshots contain formatting only',all(not KEYS&s.keys()
      for s in frozen.selection.settled_states))
HEADER='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
source=current._resolve_document_state(current.parse_subtitle_document(HEADER+
    r'Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\pos(100,50)\frz0\t(0,100,\frz-20)\t(100,1000,\frz20)}word'+'\n'))
snapshot=deepcopy({k:vars(e) for k,e in source.events.items()})
normalized=current.normalize_animated_rotations(source.events)
check('rotation normalization does not mutate source events',snapshot=={k:vars(e) for k,e in source.events.items()})
check('rotation normalization consumes proof into formatting',
    all(current.unrotated_text_state(e.state) and not KEYS&e.state.keys() for e in normalized.values()))
event=next(iter(normalized.values()))
replaced=current.replace_event(event,text=r'{\pos(200,50)\fs60}different')
check('arbitrary replacement has resolved formatting without pose proof',
      replaced.state['pos']==(200.,50.) and replaced.state['fs']==60 and not KEYS&replaced.state.keys())
reparsed=current._normalize_text_result(source,current.TextProcessingResult(list(normalized.values()),{}))
check('render/reparse boundary carries only formatting',all(
    not KEYS&e.state.keys() for e in reparsed.events.values()))
original_events=list(source.events.values())
unchanged_list=current.prefer_surviving_upright_poses(original_events,{})
check('no-target surviving-pose return retains list identity',unchanged_list is original_events)
tree=ast.parse((ROOT/'simplify_ass.py').read_text())
check('legacy pose dictionary keys removed from production',not any(
    isinstance(n,ast.Constant) and n.value in KEYS for n in ast.walk(tree)))
(ROOT/'validation/pose-evidence-checks.json').write_text(json.dumps(dict(
    version=current.__version__,reference_version=previous.__version__,comparisons=len(comparisons),
    ownership_checks=len(checks),all_inline_selection_proof_and_rendering_identical=True,
    borrowed_inputs_unchanged=True,checks=checks,cases=comparisons),indent=2)+'\n')
print(len(comparisons),'pose-continuation comparisons;',len(checks),'ownership and boundary checks passed')

