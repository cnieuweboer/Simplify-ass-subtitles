#!/usr/bin/env python3
"""Compare explicit override continuation against v157."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
import ast,importlib.util,json,math,random,sys
import simplify_ass as current

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('override_reference',ROOT/'test-data/simplify_ass-v157-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
PRIVATE={'_reset_style','_alignment_set'}
def clean(state):return {k:v for k,v in state.items() if k not in PRIVATE}
def legacy_continuation(state):
 return current.OverrideContinuation(state.get('_reset_style'),state.get('_alignment_set'))
def compare(actual,expected):
 # NaN comparisons retain the same representation without implying finiteness.
 if isinstance(actual,float) and math.isnan(actual):return isinstance(expected,float) and math.isnan(expected)
 if isinstance(actual,dict) and isinstance(expected,dict):
  return actual.keys()==expected.keys() and all(compare(actual[k],expected[k]) for k in actual)
 if isinstance(actual,(list,tuple)) and isinstance(expected,(list,tuple)):
  return len(actual)==len(expected) and all(compare(a,b) for a,b in zip(actual,expected))
 return actual==expected

DEFAULT={**current.DEFAULT_STATE,'fs':40,'fn':'Arial','an':5,'bord':2,'shad':1}
STYLES={'Other':{**DEFAULT,'fs':60,'fn':'Other Font','an':7,'bord':4,'shad':3},
        'other':{**DEFAULT,'fs':30,'fn':'lowercase','an':1},
        '*Other':{**DEFAULT,'fs':22,'an':9}}
TOKENS=[('r',''),('r','Other'),('r','other'),('r','Missing'),('r','OTHER'),('r','*Other'),
 ('fn',''),('fn','Arial'),('fs',''),('fs','0'),('fs','-10'),('fs','-12'),('fs','+2'),('fs','-.5'),('fs','40'),('fs','bad'),
 ('an',''),('an','0'),('an','-1'),('an','10'),('an','7junk'),('an','+3'),('an',' 7'),('an','1.5'),('an','5'),
 ('a',''),('a','4'),('a','8'),('a','11'),('a','12'),('a','-1'),('a','5rest'),
 ('c','&H123456&'),('1c','bad!'),('alpha','&H80&'),('4a','&HFF&'),('3a','-1'),
 ('pos','(10,20)'),('pos','(30,40)'),('pos','(10)'),('org','(1,2)'),('org','(3,4)'),
 ('clip','(0,0,640,360)'),('iclip','(1,m 0 0 l 10 10)'),
 ('q','2'),('q',''),('p','1'),('p','0'),('pbo','10'),('b',''),('i','1'),
 ('bord','4'),('xbord','8'),('ybord','9'),('bord',''),('shad','2'),('xshad','7'),('yshad','8'),
 ('shad',''),('fr','15'),('frz',''),('blur','bad'),('t','(0,100,\\fs80)'),('fad','(100,200)'),('move','(1,2,3,4)')]
SEQUENCES=[
 [('r','Other'),('fs',''),('fn',''),('bord',''),('an','0'),('an','2')],
 [('an','0'),('r','Other'),('an','7'),('r',''),('fs','')],
 [('a','12'),('r','Missing'),('a','1')],
 [('an','7'),('r','Other'),('an','2')],
 [('r','Other'),('r','Missing'),('fs',''),('fn','')],
 [('r','Other'),('r',''),('fs','+2'),('fs','-10')],
 [('xbord','8'),('ybord','9'),('bord','2'),('xbord','4'),('shad','1'),('xshad','3')],
 [('pos','(10,20)'),('org','(1,2)'),('clip','(0,0,640,360)'),('q','2'),('p','1'),('pbo','8'),('r','Other')],
 TOKENS]
rng=random.Random(158)
SEQUENCES += [[rng.choice(TOKENS) for _ in range(rng.randint(1,35))] for _ in range(300)]
seeds=[{}, {'_reset_style':''}, {'_reset_style':'Other'}, {'_reset_style':'Missing'},
       {'_alignment_set':True},{'_alignment_set':False},
       {'_reset_style':'Other','_alignment_set':True}]
for empty_style in (False,True):
 styles=deepcopy(STYLES)
 if empty_style:styles['']={**DEFAULT,'fs':75,'fn':'Empty named style','an':8}
 for seed in seeds:
  for event_tags in (True,False):
   for index,sequence in enumerate(SEQUENCES):
    expected={**DEFAULT,**seed}
    state=clean(expected);continuation=legacy_continuation(expected)
    borrowed=deepcopy((styles,DEFAULT));initial_continuation=continuation
    for step,(name,value) in enumerate(sequence):
     previous.apply_tag(expected,name,value,styles,DEFAULT,event_tags)
     continuation=current.apply_override(state,name,value,styles,DEFAULT,continuation,event_tags=event_tags)
     label=f'{empty_style} {seed} event {event_tags} sequence {index} step {step}'
     check(label+' formatting',compare(state,clean(expected)))
     check(label+' rendered insertion order',list(state)==list(clean(expected)))
     check(label+' continuation',continuation==legacy_continuation(expected))
     check(label+' no parser history in formatting',not PRIVATE & state.keys())
    check('borrowed styles/defaults '+str(index),borrowed==(styles,DEFAULT))
    check('initial continuation unchanged '+str(index),initial_continuation==legacy_continuation({**DEFAULT,**seed}))

# Continuation crosses literal blocks without changing the original snapshots.
state=DEFAULT.copy();continuation=current.OverrideContinuation()
for block in (r'\rOther',r'\fs\fn\an0',r'\r\an7\fs+2'):
 for name,value in current.tokenize_override(block):
  continuation=current.apply_override(state,name,value,STYLES,DEFAULT,continuation)
check('inline reset defaults and invalid latch',state['fs']==48 and state['an']==7 and
      state['fn']=='Arial' and continuation==current.OverrideContinuation('',True))
try:continuation.reset_style='Other'
except FrozenInstanceError:check('continuation immutable',True)
else:raise AssertionError('mutable continuation')

state=DEFAULT.copy();context=current.OverrideContinuation('Other',True)
check('ordinary tags preserve continuation identity',current.apply_override(state,'fs','',STYLES,DEFAULT,context) is context)
check('consumed alignment preserves continuation identity',current.apply_override(state,'an','7',STYLES,DEFAULT,context) is context)
check('malformed paint preserves continuation identity',current.apply_override(state,'c','bad!',STYLES,DEFAULT,context) is context)

# Independent evaluation branches share only an immutable starting context.
seed=current.OverrideContinuation('Other',None);left=DEFAULT.copy();right=DEFAULT.copy()
left_context=current.apply_override(left,'an','0',STYLES,DEFAULT,seed)
right_context=current.apply_override(right,'an','3',STYLES,DEFAULT,seed)
check('branch independence',left['an']==7 and right['an']==3 and seed.alignment_set is None and
      left_context.alignment_set and right_context.alignment_set)

check('compatibility adapter removed',not hasattr(current,'apply_tag'))

source=(ROOT/'simplify_ass.py').read_text();tree=ast.parse(source)
engine=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='apply_override')
check('canonical evaluator does not read private dictionary keys',not any(
 isinstance(n,ast.Constant) and n.value in PRIVATE for n in ast.walk(engine)))
report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
 sequence_cases=len(SEQUENCES),initial_continuations=len(seeds),event_tag_modes=2,empty_named_style_modes=2,
 borrowed_defaults_and_styles_unchanged=True,rendered_insertion_order_preserved=True)
(ROOT/'validation/override-continuation-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'override continuation checks passed')
