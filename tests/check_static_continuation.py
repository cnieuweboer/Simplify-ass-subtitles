#!/usr/bin/env python3
"""Verify span continuation, signature equality and static matching against v157."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import importlib.util,json,random,sys
import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields,static_span_comparison_fields
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('static_continuation_reference',ROOT/'test-data/simplify_ass-v157-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
def snapshot(value):
 if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
 if type(value).__name__=='StaticSpanSignature':return snapshot(static_span_comparison_fields(value))
 if type(value).__name__=='DocumentMeasurementContext':return (value.canvas,value.script_wrap_mode)
 if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
 if isinstance(value,set):return frozenset(value)
 if hasattr(value,'__dict__'):return snapshot(vars(value))
 return value
HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
Style: Same,Arial,40,5,2,0
Style: Other,Arial,60,7,4,3
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def record(module,text,start=1,end=2,layer='0',kind='Dialogue',effect='',style='Default'):
 return f'{kind}: {layer},{module.format_time(start)},{module.format_time(end)},{style},,0,0,0,{effect},{text}\n'
def parse(module,records,wrap=2):
 doc=module._resolve_document_state(module.parse_subtitle_document(HEADER.replace('WrapStyle: 2','WrapStyle: '+str(wrap))+''.join(records)))
 return list(doc.events.values()),doc.styles

bodies=[
 r'{\pos(320,180)}Same',r'{\pos(320,180)\r}Same',r'{\pos(320,180)\rMissing}Same',
 r'{\pos(320,180)\rSame}Same',r'{\pos(320,180)\an5}Same',r'{\pos(320,180)\an0}Same',
 r'{\pos(320,180)\an0\an7}Same',r'{\pos(320,180)\a4}Same',
 r'{\pos(320,180)}A{}B',r'{\pos(320,180)}A{\r}B',r'{\pos(320,180)}A{\rMissing}B',
 r'{\pos(320,180)}A{\an5}B',r'{\pos(320,180)}A{\an0}B',
 r'{\pos(320,180)\r}A{\rMissing}B',r'{\pos(320,180)\rSame}A{\rSame}B',
 r'{\pos(320,180)\an0}A{\rOther\an7\fs}B{\r\fs}C',
 r'{\pos(320,180)\rSame}A{\r\fn}B',
 r'{\pos(320,180)\1a&H80&}A{\1a&H00&}B',r'{\pos(320,180)\clip(0,0,100,100)}A{\iclip(1,2,3,4)}B',
 r'{\pos(320,180)\p1}m 0 0 l 100 0 100 100 0 100{\p0}TEXT',
 'Same',r'{\r}Same',r'{\an0}Same',r'{\rOther\fs}Same',
 r'{\pos(320,180)\move(0,0,1,1)}Same',r'{\pos(320,180)\t(0,100,\fs80)}Same',
 r'{\pos(320,180)\fad(100,200)}Same',r'{\pos(320,180)\k20}Same','']
rng=random.Random(158)
choices=[r'\r',r'\rSame',r'\rOther',r'\rMissing',r'\runknown',r'\an0',r'\an5',r'\an7',r'\a12',r'\a4',
         r'\fs',r'\fs+2',r'\fs40',r'\fnArial',r'\bord2',r'\xbord3',r'\shad0',r'\q2',r'\1c&H123456&']
for i in range(100):
 bodies.append(r'{\pos(320,180)}'+''.join('{'+''.join(rng.choices(choices,k=rng.randint(0,4)))+'}'+
                 rng.choice(['A','B','Same',' ']) for _ in range(rng.randint(1,5))))
all_keys=[]
for module in (previous,current):
 keys=[]
 for i,text in enumerate(bodies):
  events,styles=parse(module,[record(module,text)])
  e=events[0];before=deepcopy(snapshot(e))
  for unpositioned in (False,True):
   key=module.static_object_key(e,styles,allow_unpositioned=unpositioned)
   keys.append(key)
   check(str(i)+module.__version__+' borrowed input',before==snapshot(e))
   if module is current and key is not None:
    for signature,_,_ in key[-1]:
     check(str(i)+' clean span formatting',not {'_reset_style','_alignment_set'} & dict(signature.formatting).keys())
     check(str(i)+' typed continuation',isinstance(signature.continuation,current.OverrideContinuation))
  # Literal geometry consumes the formatting component; matching retains history.
  paint={'1c','1a','3c','3a','4c','4a','bord','xbord','ybord','shad','blur','be'}
  profile=module.static_text_paint_geometry(e,paint)
  if module is current:
   old_e=parse(previous,[record(previous,text)])[0][0]
   check(str(i)+' paint geometry parity',snapshot(profile)==snapshot(previous.static_text_paint_geometry(old_e,paint)))
 all_keys.append(keys)
check('every complete signature canonical parity',snapshot(all_keys[0])==snapshot(all_keys[1]))
for i,old in enumerate(all_keys[0]):
 for j,other in enumerate(all_keys[0]):
  check(f'matching decision {i}:{j}',(old==other)==(all_keys[1][i]==all_keys[1][j]))
# Context-only boundaries must still prevent literal span coalescing.
def key(text):
 e,styles=parse(current,[record(current,text)]);return current.static_object_key(e[0],styles)
check('ordinary empty boundary coalesces',len(key(bodies[8])[-1])==1)
check('explicit reset boundary retained',len(key(bodies[9])[-1])==2)
check('explicit alignment boundary retained',len(key(bodies[11])[-1])==2)
check('empty and unknown resets match',key(bodies[1])==key(bodies[2]))
check('absent and explicit empty reset remain different',key(bodies[0])!=key(bodies[1]))
check('absent and consumed alignment remain different',key(bodies[0])!=key(bodies[4]))
check('valid same alignment and invalid alignment match',key(bodies[4])==key(bodies[5]))
signature=key(bodies[0])[-1][0][0]
try:signature.continuation=current.OverrideContinuation('',True)
except FrozenInstanceError:check('span signature immutable',True)
else:raise AssertionError('mutable matching signature')

for index in range(200):
 text1=rng.choice(bodies[:24]);text2=rng.choice(bodies[:24]);text3=rng.choice(bodies[:24])
 records=[];results=[]
 for module in (previous,current):
  events,styles=parse(module,[record(module,text1,1,2),record(module,text2,2,3),record(module,text3,3,4)],wrap=index%4)
  before=deepcopy(snapshot(events));out,n=module.merge_static_timed_copies(events,styles)
  check('timed merging borrowed '+str(index)+module.__version__,before==snapshot(events))
  results.append((snapshot(out),n))
 check('timed merging decision/output '+str(index),results[0]==results[1])

report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
           literal_cases=len(bodies),signature_comparisons=len(all_keys[0]),matching_pairs=len(all_keys[0])**2,
           timed_merge_cases=200)
(ROOT/'validation/static-continuation-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'static continuation checks passed')
