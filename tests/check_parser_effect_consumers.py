#!/usr/bin/env python3
"""Compare direct span consumers, paint-copy reduction and reveals with v157."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
import importlib.util,json,math,random,sys
import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields,static_span_comparison_fields
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('parser_effect_reference',ROOT/'test-data/simplify_ass-v157-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
def snapshot(value):
 if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
 if type(value).__name__=='StaticSpanSignature':return snapshot(static_span_comparison_fields(value))
 if type(value).__name__=='DocumentMeasurementContext':return (value.canvas,value.script_wrap_mode)
 if isinstance(value,float) and not math.isfinite(value):return repr(value)
 if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
 if isinstance(value,set):return frozenset(value)
 if hasattr(value,'__dict__'):return snapshot(vars(value))
 return value

def fixtures(name):
 path=ROOT/'tests'/name;namespace={'__file__':str(path),'__name__':'parser_effect_fixtures'}
 exec(compile(path.read_text().split('SPY_NAMES=')[0],str(path),'exec'),namespace)
 return namespace

stack=fixtures('check_stacked_copy_stages.py')
modes=('static','empty_flags','animated','partly_animated','source_static','source_animated','empty_sources')
stack_cases=0
for case in stack['CASES']:
 for order in ('original','reverse','shuffle'):
  for mode in modes:
   if case.get('static_only') and mode not in ('static','empty_flags'):continue
   compared=[]
   for module in (previous,current):
    events=stack['parse'](module,case['records']);visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    if case.get('missing_visible') and events:visible.pop(events[1].source_index)
    ids=[e.source_index for e in events]
    animated=None if mode=='static' else set(ids) if mode in ('animated','source_animated') else set(ids[:1]) if mode=='partly_animated' else set()
    sources={e.source_index:e for e in stack['parse'](module,case['records'],True,case)} if mode.startswith('source_') else {} if mode=='empty_sources' else None
    if sources and case.get('missing_source'):sources={}
    if order=='reverse':events.reverse()
    elif order=='shuffle':random.Random(158).shuffle(events)
    before=deepcopy(snapshot((events,visible,animated,sources)))
    refusal=patch.object(module,'static_text_paint_caption',return_value=None) if case.get('reject_caption') else nullcontext()
    with refusal:out,n=module.flatten_stacked_text_copies(events,visible,animated,source_events=sources)
    check(case['name']+order+mode+module.__version__+' input ownership',before==snapshot((events,visible,animated,sources)))
    compared.append((snapshot(out),n,[any(e is source for source in events) for e in out]))
   check(case['name']+order+mode+' stacked parity',compared[0]==compared[1]);stack_cases+=1

reveal=fixtures('check_progressive_reveal_stages.py');reveal_cases=0
for case in reveal['CASES']:
 for order in ('original','reversed','shuffled'):
  for map_mode in ('complete','missing_all','missing_one','wrong_one'):
   compared=[]
   for module in (previous,current):
    events,visible=reveal['inputs'](module,case['records'],order,map_mode)
    before=deepcopy(snapshot((events,visible)))
    result=module.collapse_progressive_text_reveals(events,visible)
    check(case['name']+order+map_mode+module.__version__+' input ownership',before==snapshot((events,visible)))
    updated={**visible,**result.visibility_updates}
    compared.append((snapshot(result.events),result.removed_count,result.visibility_updates,updated,
                     result.events is events,[any(e is source for source in events) for e in result.events]))
   check(case['name']+order+map_mode+' reveal parity',compared[0]==compared[1]);reveal_cases+=1

report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
            stacked_scenarios=len(stack['CASES']),stacked_comparisons=stack_cases,
            reveal_scenarios=len(reveal['CASES']),reveal_comparisons=reveal_cases)
(ROOT/'validation/parser-effect-consumer-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'parser effect consumer checks passed')
