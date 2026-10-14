#!/usr/bin/env python3
"""Compare directly related selection consumers and paint generators with v159."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from pathlib import Path
from collections.abc import Iterator
import importlib.util,json,math,random,sys
import simplify_ass as current
from event_evidence_test_helpers import freeze_caption_policy_for_legacy_comparison
freeze_caption_policy_for_legacy_comparison(current)
from event_evidence_test_helpers import event_comparison_fields,selection_comparison_fields
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('freeze_consumer_reference',ROOT/'test-data/simplify_ass-v159-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def snapshot(value):
    if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
    if isinstance(value,Iterator):return 'iterator'
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
def fixtures(filename,delimiter):
    path=ROOT/'tests'/filename;namespace={'__file__':str(path),'__name__':'freeze_consumer_fixtures'}
    exec(compile(path.read_text().split(delimiter)[0],str(path),'exec'),namespace)
    return namespace

# Retain the existing semantic scenarios, without implementation call traces.
static=fixtures('check_static_state_stages.py','SPY_NAMES=');static_cases=0
for case in static['CASES']:
    for mode in (('list','reverse','generator') if 'paint' in case else ('none',)):
        for collector in ('none','empty','seeded'):
            for prefer,crossings in ((False,False),(False,True),(True,False),(True,True)):
                compared=[]
                for module in (previous,current):
                    static['current']=module
                    base,transforms,bounds,styles,default,paint,opaque,settled,events,seen,pose=static['inputs'](module,case,mode,collector)
                    before=deepcopy(snapshot((base,transforms,bounds,styles,default,events,opaque,settled)))
                    kwargs=dict(prefer_upright=prefer,upright_crossings=crossings,prior_pose=pose)
                    result=module.select_static_state(base,transforms,bounds,styles,default,paint,opaque,settled,**kwargs)
                    check(case['name']+' static inputs/evidence borrowed',before==snapshot((base,transforms,bounds,styles,default,events,opaque,settled)))
                    check(case['name']+' selector identity',(result.state is base)==(not transforms and paint is None))
                    if mode=='generator':check(case['name']+' single paint iteration',seen==[e.source_index for e in events])
                    compared.append(snapshot(selection_comparison_fields(result)))
                check(case['name']+' complete static policy parity',compared[0]==compared[1]);static_cases+=1

copies=fixtures('check_full_lyric_visibility.py','@contextmanager\ndef recording');copy_cases=0
for name,records in copies['CASES']:
    for order in ('original','reverse','shuffle'):
        for map_mode in ('complete','missing_one','missing_all','wrong_one'):
            for target in ('collapse_full_lyric_copies','coalesce_lyric_phases'):
                compared=[]
                for module in (previous,current):
                    events,visible=copies['inputs'](module,records,order,map_mode)
                    before=deepcopy(snapshot((events,visible)))
                    result=getattr(module,target)(events,visible)
                    if target=='collapse_full_lyric_copies':
                        output,count=result.events,result.removed_count
                        updates=result.visibility_updates
                    else:output,count=result;updates={}
                    check(name+target+' borrowed input',before==snapshot((events,visible)))
                    compared.append((snapshot(output),count,updates,
                        [any(e is source for source in events) for e in output]))
                check(name+target+' output/updates/identity parity',compared[0]==compared[1]);copy_cases+=1

sequences=fixtures('check_text_effect_sequence_stages.py','SPY_NAMES=');sequence_cases=0
for case in sequences['CASES']:
    for scale,evidence,flags in ((False,False,False),(False,True,True),(True,False,False),(True,True,True)):
        compared=[]
        for module in (previous,current):
            events,styles=sequences['parse'](module,case)
            visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
            if case.get('missing_visible') and len(events)>1:visible.pop(events[1].source_index)
            animated={e.source_index for e in events} if flags else None
            sources={e.source_index:e for e,d in zip(sequences['parse'](module,case,True)[0],case['records'])
                     if not d.get('omit_source')} if evidence else None
            before=deepcopy(snapshot((events,visible,styles,animated,sources)))
            out,count=module.flatten_text_effect_sequences(events,visible,styles,animated,scale,source_events=sources)
            check(case['name']+' effect inputs borrowed',before==snapshot((events,visible,styles,animated,sources)))
            compared.append((snapshot(out),count,[any(e is source for source in events) for e in out]))
        check(case['name']+' effect output/identity parity',compared[0]==compared[1]);sequence_cases+=1

report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
            static_policy_cases=static_cases,lyric_paint_consumer_cases=copy_cases,effect_sequence_cases=sequence_cases,
            borrowed_inputs_unchanged=True,paint_generators_consumed_once=True)
(ROOT/'validation/freeze-consumer-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'freeze consumer checks passed;',static_cases,'static cases;',copy_cases,'lyric paint cases;',sequence_cases,'effect sequence cases')
