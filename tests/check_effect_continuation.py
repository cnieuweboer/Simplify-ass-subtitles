#!/usr/bin/env python3
"""Compare remaining validation/rendering callers with immutable v160."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import importlib.util,json,math,sys
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
from event_evidence_test_helpers import event_comparison_fields,override_test_evaluation
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('effect_continuation_reference',ROOT/'test-data/simplify_ass-v160-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
PRIVATE={'_canvas','_script_wrap_mode','_reset_style','_alignment_set'}
checks=[];callers=set();cases=0

def check(name,condition):
 assert condition,name
 checks.append(name)
def snapshot(value):
 if type(value).__name__ in ('RecordingMetric','FontSpacing','FontMetrics'):return 'font-metric'
 if type(value).__name__=='Event':return ('Event',complete_snapshot(event_comparison_fields(value)))
 if isinstance(value,float) and not math.isfinite(value):return repr(value)
 if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items() if k not in PRIVATE}
 if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
 if isinstance(value,set):return frozenset(snapshot(v) for v in value)
 if hasattr(value,'__dict__'):return snapshot(vars(value))
 return value
def complete_snapshot(value):
 if isinstance(value,float) and not math.isfinite(value):return repr(value)
 if isinstance(value,dict):return {k:complete_snapshot(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return tuple(complete_snapshot(v) for v in value)
 return value
# Complete events retain history; loose dictionaries carry geometry/paint only.
def fixtures(name,delimiter):
 p=ROOT/'tests'/name;ns={'__file__':str(p),'__name__':'continuation_fixtures'}
 exec(compile(p.read_text().split(delimiter)[0],str(p),'exec'),ns);return ns
engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
def run(module,target,args):
 real=module.apply_override
 def watched(state,name,value,styles,default,continuation,**options):
  if module is current:
   check('clean effect parser input',not PRIVATE & state.keys())
   callers.add(sys._getframe(1).f_code.co_name)
  result=real(state,name,value,styles,default,continuation,**options)
  if module is current:check('clean effect parser output',not PRIVATE & state.keys())
  return result
 with patch.object(module,'apply_override',watched):return getattr(module,target)(*args)

def compare(label,target,inputs,*,expected_colour=None):
 global cases
 outputs=[]
 for module in (previous,current):
  args=inputs(module);before=deepcopy(snapshot(args));out=run(module,target,args)
  check(label+' borrowed input',before==snapshot(args))
  if expected_colour is not None:
   events=args[0]
   check(label+' complete row retained',len(out)==len(events)==3)
   if module is previous:
    check(label+' historical selection retains input',snapshot(out)==snapshot(events))
   else:
    check(label+' completed paint selected',all(e.state['1c']==expected_colour for e in out))
    check(label+' only paint formatting replaced',all(
     snapshot(module.replace_event(a,text=b.text))==snapshot(b) for a,b in zip(events,out)))
  outputs.append(snapshot(out))
 if expected_colour is None:check(label+' complete decision parity',outputs[0]==outputs[1])
 cases+=1

f=fixtures('check_shrinking_row_stages.py','SPY_NAMES=')
for c in f['CASES']:
 for order in ('original','reversed','shuffled'):
  for mode in ('available','unavailable','none','failed_fit'):
   compare(c['name']+order+mode,'collapse_shrinking_glyph_rows',lambda m:(f['inputs'](m,c['events'],order),None if mode=='none' else f['RecordingMetric'](engines[m],mode),2))
f=fixtures('check_karaoke_completion_stages.py','SPY_NAMES=')
for c in f['CASES']:
 for order in ('original','reversed','shuffled'):
  # v196 intentionally admits one-centisecond endpoint overhang; retain
  # parser/ownership checks while asserting its new destination paint.
  colour=f['AFTER'] if c['name'] in {'source runs before retained cue','source runs after retained cue'} else None
  compare(c['name']+order,'normalize_karaoke_completion_paint',lambda m:f['inputs'](m,c,order,order),expected_colour=colour)
f=fixtures('check_sliced_text_stages.py','SPY_NAMES=')
for c in f['CASES']:
 for order in ('original','reverse','shuffle'):
  def build(m):
   events,_=f['parse'](m,c)
   if order=='reverse':events.reverse()
   elif order=='shuffle':__import__('random').Random(161).shuffle(events)
   return (events,)
  compare(c['name']+order,'collapse_sliced_text_sequences',build)
f=fixtures('check_boundary_glyph_stages.py','NAMES=')
for c in f['CASES']:
 for order in ('original','reverse','shuffle'):
  for mode in ('real','unavailable','none','failed_fit','distant_fit'):
   compare(c['name']+order+mode,'match_boundary_glyph_effects',lambda m:(*f['inputs'](m,c,order,order),None if mode=='none' else f['RecordingMetric'](engines[m],mode)))
f=fixtures('check_vector_text_stages.py','NAMES=')
for c in f['CASES']:
 for order in ('original','reverse','shuffle'):
  compare(c['name']+order,'recover_vector_text_cues',lambda m:(f['inputs'](m,c,order),f['RecordingMetric'](engines[m],'real',c),0))

# Backed pulse and moving-chain builders are reusable before their historical
# call-order tracer. Exercise successful rows, malformed destinations, defaults,
# branch independence, empty caches, and movement/fade chains.
f=fixtures('check_backed_pulses.py','def call(')
for tags in ['',r'\r',r'\rMissing',r'\an0',r'\an0\r',r'\an7']:
 for order in ('original','reversed','shuffled'):
  for empty in (False,True):
   records=f['row']()
   for d in records:d['tags']=tags+d['tags'];d['empty_state']=empty
   compare('backed'+tags+order+str(empty),'collapse_backed_glyph_pulses',lambda m:f['inputs'](m,records,order))
f=fixtures('check_moving_glyphs.py','def call(')
for order in ('original','reversed','shuffled'):
 for tags in ['',r'\r',r'\rMissing',r'\an0',r'\an0\r']:
  records=[f['event'](tags=tags),f['event'](start=2,end=3,movement=(350,100,300,100),tags=tags),f['event'](start=3,end=5,tags=tags),f['event'](start=5,end=5.2,tags=tags+f['FADE'])]
  args=f['inputs'](current,records,order)
  # Independent real font engines; no reuse of caller-owned state.
  compare('moving'+tags+order,'collapse_moving_glyph_sequences',lambda m:(*f['inputs'](m,records,order),engines[m]))

# Arbitrary accepted override destinations expose reset-default and first-tag
# semantics even when the production admission sets are intentionally narrow.
for reset in (None,'','Other','Missing'):
 for alignment in (None,False,True):
  for text in [r'{\pos(10,20)}A',r'{\an0\rOther}A']:
   results=[]
   for m in (previous,current):
    default={**m.DEFAULT_STATE,'fs':40,'an':5};styles={'Other':{**default,'fs':60,'an':7},'':{**default,'fs':75,'an':8}}
    raw={**default}
    if reset is not None:raw['_reset_style']=reset
    if alignment is not None:raw['_alignment_set']=alignment
    e=m.Event('Dialogue','0','0:00:01.00','0:00:03.00','Default','','0','0','0','',text,1.,3.,1,defaults=default,styles=styles)
    branch_text=r'{\t(0,500,\fs\an0\rOther\fn\fs+2\an2)\t(500,1000,\r\fs\an7)}A'
    e.text=branch_text
    before=deepcopy(raw)
    if m is current:
     evaluated=override_test_evaluation(m,raw);e.state,e.continuation=evaluated.formatting,evaluated.continuation
     out=m._parse_backed_glyph_effects(e,e.state,{'fs','an','r','fn'},continuation=e.continuation)
    else:
     e.state=raw;out=m._parse_backed_glyph_effects(e,raw,{'fs','an','r','fn'})
    check('branch base preserved',raw==before)
    results.append(snapshot(out))
   check('ordered reset/default/latch transform destinations',results[0]==results[1])

report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),effect_cases=cases,clean_override_callers=sorted(callers),borrowed_inputs_unchanged=True)
(ROOT/'validation/effect-continuation-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'effect continuation checks passed;',cases,'effect cases')
