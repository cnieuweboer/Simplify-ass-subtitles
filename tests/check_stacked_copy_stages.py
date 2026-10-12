import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare stacked-copy admission, paint and ownership with version 121."""
from pathlib import Path
from copy import deepcopy
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stacked_copy_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
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

def stack(*,shadow=False,unpositioned=False,count=2):
 return [dict(text='Hello',layer=str(i),tags=(r'\1a&HFF&\3a&HFF&\shad3' if shadow else '')+rf'\4c&H{["112233","445566","778899"][i%3]}&\bord{6-i}',unpositioned=unpositioned,effect='',lyric=False,row=i+4) for i in range(count)]
def change(records,predicate=lambda i,d:True,**changes):
 records=deepcopy(records)
 for i,d in enumerate(records):
  if predicate(i,d):d.update(changes)
 return records
CASES=[]
def case(name,records=None,**options):CASES.append(dict(name=name,records=stack() if records is None else records,**options))
case('opaque foreground',expected=1)
case('authored effects cleared',change(stack(),effect='authored'),expected=1)
case('empty input',[],expected=0)
case('single eligible caption',stack(count=1),expected=0)
case('translucent foreground above opaque backing',change(stack(),lambda i,d:i==1,tags=r'\1a&H40&\1c&H123456&'),expected=1)
case('fully translucent copies',change(stack(),tags=r'\1a&H80&'),expected=0)
case('invisible fill and outline without shadow',change(stack(),tags=r'\1a&HFF&\3a&HFF&'),expected=0)
for field,value in [('tags',r'\fnOther'),('tags',r'\fs42'),('tags',r'\fscx120'),('tags',r'\fscy80'),('tags',r'\fsp2'),('tags',r'\an7'),('tags',r'\frz12'),('tags',r'\frx5'),('tags',r'\fry5'),('tags',r'\fax.1'),('tags',r'\fay.1'),('tags',r'\b1'),('tags',r'\i1'),('tags',r'\q1'),('name','other'),('margin','20'),('x',550),('start',1.1),('end',4.9),('text','Other')]:
 case('mismatched '+field+str(value),change(stack(),lambda i,d:i==1,**{field:value}),expected=0)
for clip in ('clip','iclip'):
 case(clip+' stripes with complete foreground',change(stack(),lambda i,d:i==0,tags=rf'\{clip}(0,0,100,100)'),expected=1)
 case(clip+' stripes only',change(stack(),tags=rf'\{clip}(0,0,100,100)'),expected=1)
 case(clip+' without opaque fill',change(stack(),tags=rf'\{clip}(0,0,100,100)\1a&H40&'),expected=0)
case('unpositioned distinct layers',stack(unpositioned=True),expected=1)
case('unpositioned same layer rows',change(stack(unpositioned=True),layer='0'),expected=0)
case('unpositioned nonnumeric layers',change(stack(unpositioned=True),lambda i,d:i==1,layer='bad'),expected=0)
for kind,text in [('Dialogue','Different'),('Dialogue',''),('Dialogue',r'{\p1}m 0 0 l 10 0 10 10'),('Comment','Different')]:
 extra=dict(text=text,layer='1',unpositioned=True,kind=kind,start=2,end=3)
 case('collision peer '+kind+repr(text),stack(unpositioned=True)+[extra],expected=1 if kind=='Comment' else 0)
for start,end in [(0,1),(5,6),(0,1.01),(4.99,6)]:
 case('collision timing '+str((start,end)),stack(unpositioned=True)+[dict(text='Other',layer='1',unpositioned=True,start=start,end=end)],expected=0 if start<5 and end>1 else 1)
for payload in [r'A{\fnOther}B',r'A{\fs30}B',r'A{\fsp2}B',r'A{\rDefault}B',r'A\NB',r'A\h B',r'A{\1c&H123456&}B']:
 case('equal inline '+payload,change(stack(),text=payload),expected=1)
case('different earlier inline fonts equal final state',[dict(text=r'A{\fnOther}B{\fnArial}C',layer='0'),dict(text=r'A{\fnAnother}B{\fnArial}C',layer='1')],expected=0)
case('different inline tracking',[dict(text=r'A{\fsp2}B{\fsp0}C',layer='0'),dict(text=r'A{\fsp3}B{\fsp0}C',layer='1')],expected=0)
case('unsupported inline transform',change(stack(),text=r'A{\t(\fs50)}B'),expected=0)
case('inline translucent literal',change(stack(),text=r'A{\1a&H80&}B'),expected=0)
case('inline geometry profile refusal',change(stack(unpositioned=True),text=r'{\p1}m 0 0 l 10 0{\p0}Hello'),expected=0)
case('inline caption renderer refuses',change(stack(),text=r'A{\fs30}B'),reject_caption=True,expected=0)
case('static shadow-painted stack',stack(shadow=True),expected=1,static_shadow=True)
case('static translucent shadow',change(stack(shadow=True),tags=r'\1a&HFF&\3a&HFF&\shad-3\4a&H40&\4c&H987654&'),expected=1,static_shadow=True)
case('animated shadow contours',stack(shadow=True,count=3),expected=2)
case('animated no wider contour',change(stack(shadow=True),tags=r'\1a&HFF&\3a&HFF&\shad3\bord2'),expected=1)
case('invisible upper glow',change(stack(shadow=True,count=3),lambda i,d:i==2,tags=r'\1a&HFF&\3a&HFF&\4a&HFF&\shad3\bord8'),expected=2)
case('different shadow offsets',change(stack(shadow=True),lambda i,d:i==1,tags=r'\1a&HFF&\3a&HFF&\xshad4\yshad3'),static_expected=0)
case('zero shadow offsets',change(stack(shadow=True),tags=r'\1a&HFF&\3a&HFF&\shad0'),expected=0)
for tags in [r'\frz10',r'\frx5',r'\fry5',r'\fax.1',r'\fay.1',r'\org(500,100)',r'\clip(0,0,100,100)',r'\iclip(0,0,100,100)',r'\fs0',r'\fscx0',r'\fscy0']:
 case('static shadow safeguard '+tags,change(stack(shadow=True),tags=r'\1a&HFF&\3a&HFF&\shad3'+tags),static_expected=0 if tags not in (r'\fax.1',r'\fay.1',r'\fs0') else 1)
for key,value in [('fs',0),('fs',float('inf')),('fscx',float('nan')),('fscy',-1),('borderstyle',2),('xshad',float('inf'))]:
 case('static shadow state safeguard '+key,change(stack(shadow=True),state={key:value}),static_expected=0,static_only=True)
case('moving original source shadow',stack(shadow=True),source_tags=r'\move(500,100,550,100)',source_expected=0)
case('transformed original source shadow',stack(shadow=True),source_tags=r'\t(\fs50)',source_expected=0)
case('animated partition different glow scale',change(stack(shadow=True,count=3),lambda i,d:i==0,tags=r'\1a&HFF&\3a&HFF&\shad3\bord8\fscx120'),animated_expected=1,static_expected=0)
case('two shadows cannot partition',change(stack(shadow=True),lambda i,d:i==0,tags=r'\1a&HFF&\3a&HFF&\shad3\fscx120'),expected=0)
case('clipped animated family cannot partition',change(stack(shadow=True,count=3),lambda i,d:i==0,tags=r'\1a&HFF&\3a&HFF&\shad3\clip(0,0,100,100)'),expected=0)
case('inert spacing tail',change(stack(shadow=True),text=r'Hello{\fsp100} '))
case('effectless source lookup fallback',stack(shadow=True),missing_source=True,expected=1)
case('comment preservation',stack()+[dict(text='Hello',kind='Comment')],expected=1)
case('drawing preservation',stack()+[dict(text=r'{\p1}m 0 0 l 1 0 1 1')],expected=1)
case('blank preservation',stack()+[dict(text='')],expected=1)
case('missing visible-map entry',missing_visible=True,expected=0)
case('synthetic source order',change(stack(),synthetic_ids=True),expected=1)
case('negative layers',change(stack(),lambda i,d:i==0,layer='-2'),expected=1)
case('same layer positioned copies',change(stack(),layer='0'),expected=1)
case('independent text groups',stack()+change(stack(),text='Other',x=900),expected=2)
case('unsupported inline paint and supported family',stack()+change(stack(),text=r'X{\t(\fs50)}Y',x=900),expected=1)

def parse(module,records,source=False,c=None):
 lines=[]
 for d in records:
  pos='' if d.get('unpositioned') else rf'\pos({d.get("x",500)},100)'
  tags=pos+d.get('tags','')+(c.get('source_tags','') if source else '')
  lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer','0')},{module.format_time(d.get('start',1))},{module.format_time(d.get('end',5))},Default,{d.get('name','')},{d.get('margin','0')},0,0,{d.get('effect','')},{{{tags}}}{d['text']}\n")
 events=list(module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines))).events.values())
 for e,d in zip(events,records):
  if d.get('synthetic_ids'):e.source_index=10000-e.source_index*19
  if 'state' in d:e.state={**e.state,**d['state']}
  e.lyric=d.get('lyric',False);e.row=d.get('row',3)
 return events
SPY_NAMES=('collapse_frame_text_echoes','without_inert_spacing_tail','flatten_held_text_paint_copies','inline_layout_key','text_layout_key','static_object_key','static_text_paint_geometry','static_text_paint_caption','compact_static_overrides','render_simplified_caption','unrotated_text_state')
@contextlib.contextmanager
def recording(module,c,calls):
 originals={name:getattr(module,name) for name in SPY_NAMES}
 def wrap(name,original):
  def run(*args,**kwargs):
   before=snapshot((args,kwargs));result=None if c.get('reject_caption') and name=='static_text_paint_caption' else original(*args,**kwargs)
   calls.append((name,before,snapshot(result)));return result
  return run
 for name,original in originals.items():setattr(module,name,wrap(name,original))
 try:yield
 finally:
  for name,original in originals.items():setattr(module,name,original)

tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_stacked_copy_stages']);checks=[]
MODES=('static','empty_flags','animated','partly_animated','source_static','source_animated','empty_sources')
for case_index,c in enumerate(CASES):
 if case_index and case_index%25==0:print(case_index,'scenarios compared',flush=True)
 for order in ('original','reverse','shuffle'):
  for mode in MODES:
   if c.get('static_only') and mode not in ('static','empty_flags'):continue
   compared=[]
   for module in (previous,current):
    events=parse(module,c['records']);visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events};visible[-999]='unrelated'
    if c.get('missing_visible') and events:visible.pop(events[1].source_index)
    ids=[e.source_index for e in events]
    animated=None if mode=='static' else set(ids) if mode in ('animated','source_animated') else set(ids[:1]) if mode=='partly_animated' else set()
    sources={e.source_index:e for e in parse(module,c['records'],True,c)} if mode.startswith('source_') else {} if mode=='empty_sources' else None
    if sources and c.get('missing_source'):sources={}
    if order=='reverse':events.reverse()
    elif order=='shuffle':random.Random(122).shuffle(events)
    before=snapshot((events,visible,animated,sources));calls=[]
    with recording(module,c,calls):
     result=tracer.runfunc(module.flatten_stacked_text_copies,events,visible,animated,source_events=sources) if module is current else module.flatten_stacked_text_copies(events,visible,animated,source_events=sources)
    out,n=result
    assert before==snapshot((events,visible,animated,sources)),(c['name'],mode,'input ownership')
    assert n==len(events)-len(out),(c['name'],mode,'count')
    assert out is not events and [e.source_index for e in out]==sorted(e.source_index for e in out)
    # Known decisions use the direct route, before optional held-paint reductions.
    expected=c.get('expected') if mode in ('static','empty_flags','animated') else None
    if mode in ('static','empty_flags'):expected=c.get('static_expected',expected)
    if mode=='animated':expected=c.get('animated_expected',expected)
    if mode=='source_static':expected=c.get('source_expected')
    if expected is not None:assert n==expected,(c['name'],mode,'known decision',n,expected)
    if c.get('static_shadow') and n and mode in ('static','empty_flags'):
     assert out[0].lyric and out[0].layer=='0'
     assert module.get_pos(out[0].text)==(497.,97.) if 'translucent' in c['name'] else module.get_pos(out[0].text)==(503.,103.)
    compared.append((snapshot(result),calls,snapshot((events,visible,animated,sources)),[any(e is original for original in events) for e in out]))
   assert compared[0]==compared[1],(c['name'],order,mode,'v123 parity')
   checks.append(dict(case=c['name'],order=order,mode=mode,removed=n))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
 compared=[]
 for module in (previous,current):
  captured=[];original=module.flatten_stacked_text_copies
  def wrapped(events,visible,animated_sources=None,**kwargs):
   before=snapshot((events,visible,animated_sources,kwargs));result=tracer.runfunc(original,events,visible,animated_sources,**kwargs) if module is current else original(events,visible,animated_sources,**kwargs)
   captured.append((before,snapshot(result),snapshot((events,visible,animated_sources,kwargs))));return result
  module.flatten_stacked_text_copies=wrapped
  try:
   with tempfile.TemporaryDirectory() as directory:
    output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
    with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined))
  finally:module.flatten_stacked_text_copies=original
 assert compared[0]==compared[1],fixture
 focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/stacked-copy-extraction-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
  statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
  coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==13 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/stacked-copy-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,complete_results_and_helper_calls_identical=True,return_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'stacked-copy comparisons across',len(CASES),'scenarios; 2 focused conversions; all 13 helpers exercised')
