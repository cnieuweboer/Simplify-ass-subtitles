from event_evidence_test_helpers import event_comparison_fields, pose_comparison_fields, selection_comparison_fields
#!/usr/bin/env python3
"""Compare effect clustering, scale proof, geometry, paint and fallback order with v123."""
from pathlib import Path
from copy import deepcopy
import ast,contextlib,importlib.util,inspect,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('text_effect_sequence_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing, Outline, Shadow
Style: Default,Arial,40,0,5,100,100,0,2,0
Style: Other,Arial,40,0,5,100,100,0,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def snapshot(value):
 if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
 if value.__class__.__name__ in ('FontSpacing','FontMetrics'):return ('font_metrics',value.available)
 if isinstance(value,float) and not math.isfinite(value):return repr(value)
 if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()
                                  if k not in {'_upright_rotation','_sustained_geometry'}}
 if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
 if isinstance(value,set):return frozenset(snapshot(v) for v in value)
 if hasattr(value,'__dict__'):return snapshot(vars(value))
 return value

def phases():
 return [dict(start=1,end=2,tags=r'\1c&H112233&'),dict(start=2,end=3,tags=r'\1c&H445566&')]
def trail(count=3):
 return [dict(start=1,end=5,x=500+10*i,tags=rf'\fscx{80+10*i}\fscy{80+10*i}\1a&H{64-i*16:02X}&',layer=str(i)) for i in range(count)]
def change(records,predicate=lambda i,d:True,**changes):
 records=deepcopy(records)
 for i,d in enumerate(records):
  if predicate(i,d):d.update(changes)
 return records
CASES=[]
def case(name,records=None,**options):CASES.append(dict(name=name,records=phases() if records is None else records,**options))
case('touching paint phases',expected=1)
case('empty input',[],expected=0)
case('single caption',phases()[:1],expected=0)
case('identical nonanimated copies',change(phases(),tags=''),animated_expected=1,static_expected=0)
case('identical animated copies different layers',change(phases(),lambda i,d:i==1,tags='',layer='1'))
case('same paint but distinct effect fields',change(phases(),tags='',effect='authored'),animated_expected=1,static_expected=0)
case('strongly overlapping phases',[dict(start=1,end=3,tags=r'\1c&H112233&'),dict(start=1.2,end=3.2,tags=r'\1c&H445566&')],expected=1)
case('brief fade overlap',[dict(start=1,end=2,tags=r'\1c&H112233&'),dict(start=1.95,end=3,tags=r'\1c&H445566&')],expected=0)
case('nested highlight',[dict(start=1,end=5,tags=r'\1c&H112233&'),dict(start=2,end=3,tags=r'\1c&H445566&',layer='2')],expected=1)
case('shared end phases',[dict(start=1,end=3,tags=r'\1c&H112233&'),dict(start=2,end=3,tags=r'\1c&H445566&')],expected=1)
case('shared start phases',[dict(start=1,end=2,tags=r'\1c&H112233&'),dict(start=1,end=3,tags=r'\1c&H445566&')],expected=1)
for gap in [0,.0000009,.0000011,.01,.08]:
 case('timing gap '+str(gap),change(phases(),lambda i,d:i==1,start=2+gap),fractional_times=True,expected=1 if gap<=.000001 else 0)
for overlap in [.0000009,.0000011,.1,.799999,.8,.800001]:
 case('fade-overlap threshold '+str(overlap),[dict(start=1,end=2,tags=r'\1c&H112233&'),dict(start=2-overlap,end=3-overlap,tags=r'\1c&H445566&')],fractional_times=True,expected=1 if overlap<=.000001 or overlap>=.8 else 0)
for axis in ('x','y'):
 for delta in [7.1999,7.2,7.2001,40,200]:
  case('drifting '+axis+str(delta),change(phases(),lambda i,d:i==1,**{axis:500+delta if axis=='x' else 100+delta}),expected=0)
for field,value in [('margin_l','5'),('margin_r','5'),('margin_v','5'),('name','other'),('style','Other'),('text','Other'),('kind','Comment'),('unpositioned',True)]:
 case('mismatched '+field,change(phases(),lambda i,d:i==1,**{field:value}),expected=0)
case('invisible primary channels',change(phases(),tags=r'\1a&HFF&'),expected=0)
case('only latter phase visible',change(phases(),lambda i,d:i==0,tags=r'\1a&HFF&'),expected=1)
case('translucent paint phases',change(phases(),lambda i,d:i==1,tags=r'\1a&H40&\1c&HABCDEF&'),expected=1)
case('drawing preserved',phases()+[dict(start=1,end=3,text=r'{\p1}m 0 0 l 10 0 10 10')],expected=1)
case('blank preserved',phases()+[dict(start=1,end=3,text='')],expected=1)
case('comment preserved',phases()+[dict(start=1,end=3,kind='Comment')],expected=1)
case('unpositioned rows preserved',change(phases(),unpositioned=True),expected=0)
case('missing visible-map entry',missing_visible=True,expected=0)
case('synthetic source ordering',change(phases(),synthetic_ids=True),expected=1)
case('independent captions',phases()+change(phases(),x=900),expected=2)
case('independent gaps',phases()+change(phases(),start=5,end=6),expected=2)
case('reverse component search',phases()+change(phases(),x=900,start=1.5,end=2.5),expected=2)
for tags in [r'\fs30',r'\fnOther',r'\fscx80',r'\fscy80',r'\frz15',r'\frx5',r'\fry5',r'\fsp2',r'\org(500,100)']:
 case('same-anchor geometry phase '+tags,change(phases(),lambda i,d:i==1,tags=tags),expected=1)
for tags in [r'\clip(0,0,100,100)',r'\iclip(0,0,100,100)']:
 case('clipped styling '+tags,change(phases(),lambda i,d:i==0,tags=tags),expected=1,clipped=True)
 case('all clipped styling '+tags,change(phases(),tags=tags),expected=1,clipped=True)
 case('clipped different names '+tags,change(change(phases(),tags=tags),lambda i,d:i==1,name='other'),expected=1,clipped=True)
 case('clipped invisible '+tags,change(phases(),tags=tags+r'\1a&HFF&'),expected=0)
case('clipped foreground opacity priority',[dict(start=1,end=3,tags=r'\clip(0,0,100,100)\1a&H00&'),dict(start=2,end=2.5,tags=r'\1a&H40&',layer='9')],expected=1,clipped=True)
case('nonnumeric layer rank',change(phases(),layer='bad'),expected=1)
case('negative layer rank',change(phases(),layer='-1'),expected=1)
case('inline authored fonts',change(phases(),text=r'H{\fnOther}el{\fnArial}lo'),expected=1)
case('inline authored paint',change(phases(),text=r'He{\1c&HABCDEF&}llo'),expected=0)
case('inline explicit line break',change(phases(),text=r'Hello\Nworld'),expected=1)
case('sustained paint beats midpoint flash',[dict(start=1,end=2,tags=r'\1c&H112233&'),dict(start=2,end=2.1,tags=r'\1c&HABCDEF&'),dict(start=2.1,end=3.1,tags=r'\1c&H112233&')],expected=2,paint='112233')
case('sustained paint without leading override',[dict(start=1,end=2,tags=r'\1c&H112233&',body_before_tags=True),dict(start=2,end=2.1,tags=r'\1c&HABCDEF&',body_before_tags=True),dict(start=2.1,end=3.1,tags=r'\1c&H112233&',body_before_tags=True)],expected=2,paint='112233')
case('sustained outline and shadow paint',[dict(start=1,end=2,tags=r'\3c&H112233&\4c&H445566&'),dict(start=2,end=2.1,tags=r'\3c&HABCDEF&\4c&HABCDEF&'),dict(start=2.1,end=3.1,tags=r'\3c&H112233&\4c&H445566&')],expected=2)
case('opaque top overlay controls votes',[dict(start=1,end=5,tags=r'\1c&H112233&',layer='0'),dict(start=1,end=5,tags=r'\1c&HABCDEF&',layer='4')],expected=1,paint='ABCDEF')
case('primary visibility changes geometry sample',[dict(start=1,end=3,tags=r'\1a&H80&\fs30'),dict(start=1,end=3,tags=r'\1a&H00&\fs40',layer='2')],expected=1)
case('upright source hold over rotated entrance',[dict(start=1,end=4,tags=r'\frz15',source_tags=r'\frz15'),dict(start=4,end=5,tags=r'\frz0',source_tags=r'\frz0')],expected=1,upright=True)
case('upright candidate without matching source geometry',[dict(start=1,end=4,tags=r'\frz15'),dict(start=4,end=5,tags=r'\frz0',source_tags=r'\frz15')],expected=1)
case('inline source cannot prove upright hold',[dict(start=1,end=4,tags=r'\frz15'),dict(start=4,end=5,tags=r'\frz0',source_text=r'H{\fnOther}ello')],expected=1)
case('missing original source for upright candidate',[dict(start=1,end=4,tags=r'\frz15'),dict(start=4,end=5,tags=r'\frz0',omit_source=True)],expected=1)
case('one flying and one stationary letter',change(phases(),text='A',source_tags=''),source_move_index=1,source_expected=0)
case('two original flying letters',change(phases(),text='A',source_tags=r'\move(500,100,550,100)'),expected=1)
case('case-insensitive original move',change(phases(),text='A'),source_move_index=1,move_tag=r'\MOVE(500,100,550,100)',source_expected=0)
case('three affine scale samples',trail(),scale_expected=2,static_expected=0,trail_pose=True)
case('four affine scale samples',trail(4),scale_expected=3,static_expected=0)
case('two scales are insufficient',trail(2),expected=0)
case('nonaffine scale path',change(trail(),lambda i,d:i==1,x=514),expected=0)
case('no distinct scales',change(trail(),tags=r'\fscx100\fscy100\1a&H40&'),expected=0)
case('vertical affine trail',change(trail(),lambda i,d:True,x=500)+[],vertical_trail=True,scale_expected=2,static_expected=0)
case('mismatched vertical scale',change(trail(),lambda i,d:i==1,tags=r'\fscx90\fscy92\1a&H30&'),expected=0)
case('mismatched trail font',change(trail(),lambda i,d:i==1,tags=r'\fscx90\fscy90\1a&H30&\fnOther'),expected=0)
case('mismatched trail name',change(trail(),lambda i,d:i==1,name='Other'),expected=0)
case('mismatched trail margins',change(trail(),lambda i,d:i==1,margin_l='10'),expected=0)
case('clipped trail cannot broaden',change(trail(),tags=r'\fscx90\fscy90\1a&H40&\clip(0,0,100,100)'),expected=0)
case('disjoint trail lifetimes',change(trail(),lambda i,d:i==0,start=.1,end=1),expected=0)
case('short shared trail interval',change(trail(),lambda i,d:i==0,end=1.1),scale_expected=2,static_expected=0)
case('excessive trail rotation',change(trail(),lambda i,d:i==1,tags=r'\fscx90\fscy90\1a&H30&\frz15'),expected=0)
case('opaque main fill alongside faded trail',trail()+[dict(start=1,end=5,x=522,tags=r'\fscx102\fscy102\1a&H00&',layer='4')],scale_expected=3,static_expected=0)
case('off-anchor main fill is refused',trail()+[dict(start=1,end=5,x=505,tags=r'\fscx102\fscy102\1a&H00&',layer='4')])
case('short opaque lead survives beside trail',trail()+[dict(start=.9,end=1,x=522,tags=r'\fscx102\fscy102\1a&H00&',layer='4')],scale_expected=2,static_expected=0,retained_lead=True)
case('all invisible trail',change(trail(),tags=r'\fscx90\fscy90\1a&HFF&'),expected=0)
case('same-position scales use exact phase fallback',change(trail(),x=500),expected=2)
case('moving word source handoff',[dict(start=1,end=2),dict(start=2,end=3,source_tags=r'\move(550,100,500,100)'),dict(start=3,end=4)],animated_expected=2,static_expected=0)

# Use real requested tags and recorded state rather than synthetic proof results.
def parse(module,c,source=False):
 lines=[];descriptors=c['records']
 for i,d in enumerate(descriptors):
  pos='' if d.get('unpositioned') else rf'\pos({d.get("x",500)},{100+10*i if c.get("vertical_trail") else d.get("y",100)})'
  tags=(d.get('source_tags',d.get('tags','')) if source else d.get('tags',''))
  if source and c.get('source_move_index')==i:tags+=c.get('move_tag',r'\move(500,100,550,100)')
  if source and '\\move' in tags.lower():pos=''
  body=d.get('source_text',d.get('text','Hello')) if source else d.get('text','Hello')
  text=body+'{'+pos+tags+'}' if d.get('body_before_tags') else '{'+pos+tags+'}'+body
  lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer','0')},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l','0')},{d.get('margin_r','0')},{d.get('margin_v','0')},{d.get('effect','authored')},{text}\n")
 doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));events=list(doc.events.values())
 for e,d in zip(events,descriptors):
  if c.get('fractional_times'):e.start_s,e.end_s=d['start'],d['end']
  if d.get('synthetic_ids'):e.source_index=10000-e.source_index*19
  e.lyric=d.get('lyric',False);e.row=d.get('row',3)
 return events,doc.styles
SPY_NAMES=('get_pos','text_height','text_layout_key','placement_key','state_key','match_scale_trail','upright_text_holds','unrotated_text_state','select_static_state','render_tag','render_simplified_caption','replace_event','format_time','collapse_moving_glyph_sequences','normalize_karaoke_completion_paint')
@contextlib.contextmanager
def recording(module,calls,tracer):
 originals={name:getattr(module,name) for name in SPY_NAMES};original_target=module.flatten_text_effect_sequences
 def wrap(name,original):
  def run(*args,**kwargs):
   if name=='select_static_state':
    bound=inspect.signature(original).bind(*args,**kwargs);bound.apply_defaults()
    arguments=dict(bound.arguments)
    arguments['opaque_spans']=arguments.pop('prior_opaque_spans')
    arguments['settled_states']=arguments.pop('prior_settled_states')
    arguments['prior_pose']=pose_comparison_fields(arguments.pop('prior_pose',None),arguments['base'])
    before=snapshot(arguments);seeds=snapshot((arguments['opaque_spans'],arguments['settled_states']))
    result=original(*args,**kwargs)
    assert seeds==snapshot((arguments['opaque_spans'],arguments['settled_states']))
    value=selection_comparison_fields(result)
    calls.append((name,before,snapshot(value)));return result
   before=snapshot((args,kwargs));result=original(*args,**kwargs);calls.append((name,before,snapshot(result)));return result
  return run
 def target(*args,**kwargs):
  calls.append(('sequence_enter',snapshot((args,kwargs))))
  result=original_target(*args,**kwargs)
  calls.append(('sequence_exit',snapshot(result)));return result
 for name,original in originals.items():setattr(module,name,wrap(name,original))
 module.flatten_text_effect_sequences=target
 try:yield
 finally:
  for name,original in originals.items():setattr(module,name,original)
  module.flatten_text_effect_sequences=original_target

tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_text_effect_sequence_stages']);checks=[]
engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
# name, scale mode, animation provenance, source provenance, font mode
MODES=[('exact_static',False,'none','none','none'),('exact_empty_flags',False,'empty','none','none'),('scale_static',True,'none','none','none'),('exact_animated',False,'all','none','none'),('scale_animated',True,'all','none','none'),('scale_partial',True,'partial','none','none'),('scale_sources',True,'all','map','none'),('exact_sources',False,'all','map','none'),('scale_empty_sources',True,'all','empty','none'),('scale_font',True,'all','map','real'),('scale_unavailable_font',True,'all','map','unavailable')]
for case_index,c in enumerate(CASES):
 if case_index and case_index%25==0:print(case_index,'scenarios compared',flush=True)
 for order in ('original','reverse','shuffle'):
  for mode,scale,flags,evidence,font in MODES:
   compared=[]
   for module in (previous,current):
    events,styles=parse(module,c);visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events};visible[-999]='unrelated'
    if c.get('missing_visible') and len(events)>1:visible.pop(events[1].source_index)
    animated=None if flags=='none' else set() if flags=='empty' else set(e.source_index for e in events[:2] if flags=='partial') if flags=='partial' else set(e.source_index for e in events)
    source=parse(module,c,True)[0] if evidence=='map' else []
    sources=None if evidence=='none' else {e.source_index:e for e,d in zip(source,c['records']) if not d.get('omit_source')}
    metric=None if font=='none' else engines[module] if font=='real' else module.FontMetrics([])
    metric_before=font_test_report(metric).rows_joined if metric is not None else None
    if order=='reverse':events.reverse()
    elif order=='shuffle':random.Random(123).shuffle(events)
    before=snapshot((events,styles,animated,sources));calls=[]
    with recording(module,calls,tracer):
     result=tracer.runfunc(module.flatten_text_effect_sequences,events,visible,styles,animated,scale,source_events=sources,font_metrics=metric, font_report=font_test_report(metric)) if module is current else module.flatten_text_effect_sequences(events,visible,styles,animated,scale,source_events=sources,font_metrics=metric, font_report=font_test_report(metric))
    out,n=result
    assert before==snapshot((events,styles,animated,sources)),(c['name'],mode,'input ownership')
    assert n==len(events)-len(out),(c['name'],mode,'removal count')
    assert out is not events and [e.source_index for e in out]==sorted(e.source_index for e in out)
    expected=c.get('expected')
    if flags in ('none','empty'):expected=c.get('static_expected',expected)
    elif flags=='all':expected=c.get('animated_expected',expected)
    if scale and flags=='all':expected=c.get('scale_expected',expected)
    if evidence=='map':expected=c.get('source_expected',expected)
    if expected is not None:assert n==expected,(c['name'],mode,'known decision',n,expected)
    if c.get('paint') and n:
     prefix=module.re.match(r'(?:\{[^}]*\})*',out[0].text).group()
     assert module.effective_state(prefix,out[0].defaults,out[0].styles)['1c']==c['paint'],(c['name'],mode,'sustained literal paint')
    if c.get('upright') and evidence=='map' and flags=='all':assert out[0].state['frz']==0,(c['name'],mode,'proved upright hold')
    if c.get('clipped') and n:assert out[0].layer=='0' and out[0].effect==''
    if c.get('trail_pose') and n:assert out[0].state['fscx']==100 and module.get_pos(out[0].text)==(520.,100.)
    if c.get('retained_lead') and scale and flags=='all':assert any(e.start_s==.9 and e.end_s==1 for e in out)
    compared.append((snapshot(result),snapshot(visible),calls,[any(e is original for original in events) for e in out],None if metric is None else font_test_report(metric).rows_joined-metric_before))
   assert compared[0]==compared[1],(c['name'],order,mode,'v123 parity')
   checks.append(dict(case=c['name'],order=order,mode=mode,removed=n))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
 compared=[]
 for module in (previous,current):
  captured=[];original=module.flatten_text_effect_sequences
  def wrapped(*args,**kwargs):
   before=snapshot((args,kwargs));result=original(*args,**kwargs)
   captured.append((before,snapshot(result),snapshot((args,kwargs))));return result
  module.flatten_text_effect_sequences=wrapped
  try:
   with tempfile.TemporaryDirectory() as directory:
    output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
    with contextlib.redirect_stdout(None):stats=tracer.runfunc(module.simplify_ass,ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric)) if module is current else module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined))
  finally:module.flatten_text_effect_sequences=original
 assert compared[0]==compared[1],fixture
 focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/text-effect-sequence-extraction-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
  statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
  coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==11 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/text-effect-sequence-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),input_events_styles_flags_sources_unchanged=True,complete_results_visible_map_helper_calls_and_metric_counters_identical=True,retained_and_return_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'text-effect sequence comparisons across',len(CASES),'scenarios; 2 focused conversions; all 11 helpers exercised')
