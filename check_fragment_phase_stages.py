from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare fragment-chain proof, missing-text safeguards and ownership with v123."""
from pathlib import Path
from copy import deepcopy
import ast,contextlib,importlib.util,json,math,random,statistics,sys,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fragment_phase_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing, Outline, Shadow
Style: Default,Arial,40,0,5,100,100,0,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def snapshot(value):
 if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
 if isinstance(value,float) and not math.isfinite(value):return repr(value)
 if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
 if isinstance(value,set):return frozenset(snapshot(v) for v in value)
 if hasattr(value,'__dict__'):return snapshot(vars(value))
 return value

def parse(module,descriptors):
 lines=[]
 for d in descriptors:
  pos='' if d.get('unpositioned') else rf'\pos({d["x"]:.8f},{d.get("y",100)})'
  tags=r'\an5'+pos+d.get('tags','')
  lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer','0')},{module.format_time(d['start'])},{module.format_time(d['end'])},Default,{d.get('name','')},{d.get('margin','0')},0,0,{d.get('effect','')},{{{tags}}}{d['text']}\n")
 events=list(module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines))).events.values())
 for e,d in zip(events,descriptors):
  if d.get('fractional_time'):
   e.start_s,e.end_s=d['start'],d['end']
  if d.get('synthetic_ids'):e.source_index=10000-e.source_index*19
  if 'state' in d:e.state={**e.state,**d['state']}
  e.lyric=d.get('lyric',True);e.row=d.get('row',3)
 return events

planning_metric=current.FontMetrics([ROOT/'fonts'])
seed=parse(current,[dict(text='ABCDEFGH',x=500,start=1,end=5)])[0]
assert planning_metric.available

def sequence(words=('AB','CD','EF','GH'),*,phases=2,direction=1,y=100,offset=0,end=5):
 authored=''.join(word+(' ' if i==1 else '') for i,word in enumerate(words))
 glyphs=row_test_call(planning_metric, 'authored_glyph_positions', seed.state,authored,500+offset,seed.unit)
 assert glyphs is not None
 records=[];index=0
 for i,word in enumerate(words):
  points=[x for c,x in glyphs[index:index+len(word)]];index+=len(word)
  anchor=row_test_call(planning_metric, 'fragment_anchor', seed.state,points,list(word),word,seed.unit,exact_size=True)
  assert anchor is not None
  activation=2+.2*(i if direction==1 else len(words)-1-i)
  for c,x in zip(word,points):records.append(dict(text=c,x=x,y=y,start=1,end=activation,word_index=i,phase='glyph'))
  starts=[activation]+[3+.2*(i if direction==1 else len(words)-1-i)+.1*j for j in range(phases-1)]
  for j,a in enumerate(starts):
   records.append(dict(text=word,x=anchor,y=y,start=a,end=starts[j+1] if j+1<len(starts) else end,word_index=i,phase='word' if j==0 else 'tail'))
 return records

def change(records,which,**changes):
 records=deepcopy(records)
 for i,d in enumerate(records):
  if which(i,d):d.update(changes)
 return records

CASES=[]
def case(name,records=None,**options):CASES.append(dict(name=name,records=sequence() if records is None else records,**options))
case('complete two-phase words',must_merge=True)
case('one completed phase',sequence(phases=1),must_merge=True)
case('long same-anchor chain',sequence(phases=6),must_merge=True)
case('reverse activation direction',sequence(direction=-1),must_merge=True)
case('two joins with single-letter chains',sequence(('AB','CD','E','F')),must_merge=True)
case('single-letter-only row',sequence(('A','B','C','D')),must_reject=True)
case('one multi-fragment join',sequence(('AB','C','D','E')),must_reject=True)
case('three completed words',sequence(('AB','CD','EF')),must_reject=True)
case('five completed words',sequence(('AB','CD','EF','GH','IJ')),must_merge=True)
case('empty input',[],must_reject=True)
case('compressed terminal height',change(sequence(),lambda i,d:d['phase']=='tail',tags=r'\fscy35'),must_merge=True,restored_height=True)
case('longer preceding height',change(sequence(),lambda i,d:d['phase']=='word',tags=r'\fscy110'),restored_height=True)
for phase in ('glyph','word','tail'):
 for field,value in [('tags',r'\1a&H80&'),('tags',r'\frz10'),('tags',r'\fnMissing'),('tags',r'\fs42'),('tags',r'\fscx120'),('tags',r'\fsp2'),('layer','2'),('margin','10'),('y',101),('unpositioned',True),('kind','Comment')]:
  case('mismatched '+phase+' '+field+str(value),change(sequence(),lambda i,d:d['word_index']==1 and d['phase']==phase,**{field:value}))
case('inline font layout',change(sequence(),lambda i,d:d['word_index']==1 and d['phase']=='tail',text=r'C{\fnOther}D'),must_reject=True)
for word in ['A B','A\u0301','אב','A\nB']:
 case('unsupported literal '+repr(word),change(sequence(),lambda i,d:d['word_index']==0,text=word))
for phase in ('glyph','word','tail'):
 records=sequence();extra=deepcopy(next(d for d in records if d['word_index']==1 and d['phase']==phase));records.append(extra)
 case('duplicate '+phase+' at shared anchor',records,**({'must_reject':True} if phase!='glyph' else {}))
case('missing glyph',[d for d in sequence() if not (d['word_index']==1 and d['phase']=='glyph' and d['text']=='D')],must_reject=True)
case('missing completed phase',[d for d in sequence() if not (d['word_index']==1 and d['phase']=='word')],must_reject=True)
case('missing terminal phase',[d for d in sequence() if not (d['word_index']==1 and d['phase']=='tail')])
case('reversed glyph positions',change(sequence(),lambda i,d:d['word_index']==1 and d['phase']=='glyph' and d['text']=='D',x=next(d['x'] for d in sequence() if d['text']=='C' and d['phase']=='glyph')-1),must_reject=True)
for slack in [0.0009,0.0011,0.01]:
 case('touching-boundary slack '+str(slack),change(sequence(),lambda i,d:d['word_index']==1 and d['phase']=='glyph',end=2.2+slack,fractional_time=True))
for delta in [.01,.011,.012]:
 case('activation separation '+str(delta),change(sequence(),lambda i,d:d['word_index']==1 and d['phase']=='word',start=2+delta,fractional_time=True))
case('brief fragment exposure',change(sequence(),lambda i,d:d['phase']=='glyph',start=1.995),must_reject=True)
case('different terminal paint',change(sequence(),lambda i,d:d['word_index']==1 and d['phase']=='tail',tags=r'\1c&H112233&'),must_reject=True)
case('same nonempty event names',change(sequence(),lambda i,d:True,name='sign'),must_merge=True)
case('synthetic source-index order',change(sequence(),lambda i,d:True,synthetic_ids=True),must_merge=True)
case('missing visible fragment',missing_visible=True,must_reject=True)
case('render fitting rejection',reject_render=True,must_reject=True)
case('independent rows',sequence()+sequence(y=250,offset=100),must_merge=True,expected_rows=2)
# A fork has distinct terminal paint families sharing the same earlier phases.
fork=sequence();extra=[]
for d in fork:
 if d['phase']=='tail':
  d['tags']=r'\1c&H112233&';copy=deepcopy(d);copy['tags']=r'\1c&H445566&';extra.append(copy)
case('competing row ownership',fork+extra,must_reject=True)
for name,x,start,end,y in [('nearby unmatched text',500,2,3,100),('far unmatched text',1200,2,3,100),('earlier unmatched text',500,.1,.5,100),('later unmatched text',500,6,7,100),('different-lane unmatched text',500,2,3,250),('brief unmatched text',500,2.1,2.11,100)]:
 blocker=dict(text='Q',x=x,y=y,start=start,end=end,tags=r'\1c&H112233&',word_index=-1,phase='blocker')
 case(name,sequence()+[blocker],**({'must_reject':True} if name in ('nearby unmatched text','brief unmatched text') else {'must_merge':True}))

class RecordingMetric:
 def __init__(self,engine,mode):self.engine,self.mode,self.calls,self.merged=engine,mode,[],7
 @property
 def available(self):return self.mode!='unavailable' and self.engine.available
 def fragment_anchor(self,*args,**kwargs):
  self.calls.append(('anchor',snapshot((args,kwargs))))
  if self.mode=='reject_anchor':return None
  result=row_test_call(self.engine, 'fragment_anchor', *args,**kwargs)
  if result is not None and self.mode=='offset_anchor':result+=args[4]*.251
  return result
 def recover(self,*args,**kwargs):
  self.calls.append(('recover',snapshot((args,kwargs))))
  if self.mode=='reject_fit':return None
  return row_test_call(self.engine, 'recover', *args,**kwargs)

def inputs(module,c,order):
 events=parse(module,c['records']);visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
 visible[-999]='unrelated entry'
 if c.get('missing_visible'):visible.pop(events[1].source_index,None)
 if order=='reverse':events.reverse()
 elif order=='shuffle':random.Random(171).shuffle(events)
 return events,visible

SPY_NAMES=('static_object_key','inline_layout_key','opaque_text_effect_state','unrotated_text_state','state_key','text_layout_key','render_simplified_caption','render_merged_caption')
@contextlib.contextmanager
def recording(module,c,calls):
 originals={name:getattr(module,name) for name in SPY_NAMES}
 def wrap(name,original):
  def run(*args,**kwargs):
   result=None if c.get('reject_render') and name=='render_merged_caption' else original(*args,**kwargs)
   calls.append((name,snapshot((args,kwargs)),snapshot(result)));return result
  return run
 for name,original in originals.items():setattr(module,name,wrap(name,original))
 try:yield
 finally:
  for name,original in originals.items():setattr(module,name,original)

tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_fragment_phase_stages']);engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)};checks=[]
for case_index,c in enumerate(CASES):
 if case_index and case_index%20==0:print(case_index,'scenarios compared',flush=True)
 for order in ('original','reverse','shuffle'):
  for mode in ('none','unavailable','real','reject_anchor','offset_anchor','reject_fit'):
   compared=[]
   for module in (previous,current):
    events,visible=inputs(module,c,order);before=snapshot(events);old_visible=deepcopy(visible);calls=[]
    metric=None if mode=='none' else RecordingMetric(engines[module],mode)
    with recording(module,c,calls):
     result=(tracer.runfunc(module.collapse_fragment_phase_rows,events,visible,metric, font_report=font_test_report(metric)) if module is current else module.collapse_fragment_phase_rows(events,visible,metric, font_report=font_test_report(metric)))
    out,n,rows=result
    assert snapshot(events)==before,(c['name'],order,mode,'input events changed')
    assert n==len(events)-len(out),(c['name'],'removal count')
    assert getattr(metric,'merged',7)==7+len(rows),(c['name'],'font counter')
    expected_visible={**old_visible,**{r.base.source_index:module.simplify_text(r.base.text,visible_only=True)[1] for r in rows}}
    assert visible==expected_visible,(c['name'],'visible-map ownership')
    if mode=='real':
     if c.get('must_merge'):assert n>0,(c['name'],order,'baseline expected merge',n)
     if c.get('must_reject'):assert n==0,(c['name'],order,'baseline expected rejection',n)
     if c.get('expected_rows'):assert len(rows)==c['expected_rows']
     if c.get('restored_height') and n:assert all(e.state['fscy'] in (100,110) for r in rows for e,word,pos in r.pieces)
    assert all(r.phase_core is not None and r.base.start_s<r.phase_core[0]<r.phase_core[1]<r.base.end_s for r in rows)
    compared.append((snapshot(result),snapshot(visible),calls,getattr(metric,'calls',[]),getattr(metric,'merged',None),out is events))
   assert compared[0]==compared[1],(c['name'],order,mode,'v123 parity')
   checks.append(dict(case=c['name'],order=order,metric=mode,removed=n,rows=len(rows)))

# Real cue conversions exercise the pass with actual pipeline provenance.
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
 compared=[]
 for module in (previous,current):
  captured=[];original=module.collapse_fragment_phase_rows
  def wrapped(events,visible,metric):
   before=snapshot((events,visible));result=(tracer.runfunc(original,events,visible,metric) if module is current else original(events,visible,metric))
   captured.append((before,snapshot(result),snapshot((events,visible)),font_test_report(metric).rows_joined));return result
  module.collapse_fragment_phase_rows=wrapped
  try:
   import tempfile
   with tempfile.TemporaryDirectory() as directory:
    output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
    with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined))
  finally:module.collapse_fragment_phase_rows=original
 assert compared[0]==compared[1],fixture
 focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

audit=json.loads((ROOT/'validation/fragment-phase-extraction-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count}
coverage={}
for node in ast.parse(filename.read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
  statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
  coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==11 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/fragment-phase-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),input_events_unchanged=True,visible_map_and_font_counter_identical=True,validation_font_and_render_calls_identical=True,return_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'fragment-phase comparisons across',len(CASES),'scenarios; 2 focused conversions; all 11 helpers exercised')
