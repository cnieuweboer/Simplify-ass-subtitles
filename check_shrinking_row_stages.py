from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare shrinking-row proof, ownership and fade handoffs with immutable v148."""
from pathlib import Path
from copy import deepcopy
import ast,contextlib,importlib.util,json,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('shrinking_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
class RecordingMetric:
    def __init__(self,engine,mode):self.engine,self.mode,self.calls=engine,mode,[]
    @property
    def available(self):return self.mode!='unavailable' and self.engine.available
    def matches_authored_glyph_positions(self,*args,**kwargs):
        result=False if self.mode=='failed_fit' else row_test_call(self.engine, 'matches_authored_glyph_positions', *args,**kwargs)
        self.calls.append((snapshot((args,kwargs)),result));return result

def event(word,start=1,end=1.5,x=500,y=100,tags='',move=None,**options):
    return dict(word=word,start=start,end=end,x=x,y=y,tags=tags,move=move,**options)
engine=current.FontMetrics([ROOT/'fonts']);assert engine.available
sample=current._resolve_document_state(current.parse_subtitle_document(HEADER+'Dialogue: 0,0:00:01.50,0:00:03.50,Default,,0,0,0,,{\\pos(500,100)}abc\n'))
state=next(iter(sample.events.values())).state
FADE=r'\t(0,500,\fscx50\fscy50\alpha&HFF&)'
def row(word='abc',**options):
    positions=row_test_call(engine, 'authored_glyph_positions', state,word,500,1);assert positions is not None
    return [event(c,x=x,move=(x,95,x,100),tags=FADE,**options) for c,x in positions]
def hold(word='abc',start=1.5,end=3.5,**options):return event(word,start,end,**options)
def changed(descriptors,predicate=lambda i,d:i<3,**options):
    result=deepcopy(descriptors)
    for i,d in enumerate(result):
        if predicate(i,d):d.update(options)
    return result
BASE=row()+[hold()];CASES=[]
def case(name,events,expected=None,**options):CASES.append(dict(name=name,events=events,expected=expected,**options))
case('complete touching row',BASE,3,start=1)
case('space-aware complete row',row('a b c')+[hold('a b c')],3,start=1)
case('hold covers complete burst at ending boundary',row()+[hold(start=.5,end=1.5)],3,start=.5)
case('different paint layers share held caption',row()+row(layer=1)+[hold()],6,start=1)
case('ambiguous boundary claims',row()+row(start=.8)+[hold()],0)
case('competing held owners',BASE+[hold()],0)
case('duplicate anchors',changed(BASE,lambda i,d:i==1,move=BASE[0]['move']),0)
case('incomplete row',BASE[:2]+BASE[3:],0)
case('wrong caption literal',row()+[hold('xyz')],0)
case('short held duration',row()+[hold(end=1.7)],0)
case('real entrance gap',row()+[hold(start=1.51)],0)
case('partial entrance overlap',row()+[hold(start=1.2)],0)
case('missing held owner',row(),0)
case('empty input',[],0)
case('unrelated static caption',[hold()],0)
case('unrelated event retained',BASE+[event('unrelated',start=4,end=5,name='other')],3,start=1)
case('named caption family',changed(BASE,lambda i,d:True,name='caption'),3,start=1)
case('mismatched caption family',row()+[hold(name='other')],0)
case('unknown font for complete row',[{**d,'tags':r'\fnAbsentFont'+d['tags']} for d in BASE],0)
case('font anchors too displaced',changed(BASE,lambda i,d:i==1,move=(BASE[1]['x']+3,95,BASE[1]['x']+3,100)),0)
case('allowed anchor error',changed(BASE,lambda i,d:i==1,move=(BASE[1]['x']+1,95,BASE[1]['x']+1,100)),3,start=1)
for name,tags in (
    ('growing',r'\t(0,500,\fscx120\fscy120\alpha&HFF&)'),
    ('unchanged x scale',r'\t(0,500,\fscx100\fscy50\alpha&HFF&)'),
    ('zero final scale',r'\t(0,500,\fscx0\fscy50\alpha&HFF&)'),
    ('missing scale axis',r'\t(0,500,\fscx50\alpha&HFF&)'),
    ('unfinished opacity',r'\t(0,500,\fscx50\fscy50\alpha&HFE&)'),
    ('outline remains visible',r'\t(0,500,\fscx50\fscy50\1a&HFF&)'),
    ('transform starts at event end',r'\t(500,500,\fscx50\fscy50\alpha&HFF&)'),
    ('transform exceeds slack',r'\t(0,560,\fscx50\fscy50\alpha&HFF&)'),
    ('invalid transform',r'\t(bad,\fscx50\fscy50\alpha&HFF&)'),
    ('unsupported transform change',r'\t(0,500,\fs20\fscx50\fscy50\alpha&HFF&)'),
    ('two transforms',FADE+r'\t(0,100,\blur2)'),
    ('transparent source',r'\alpha&HFF&'+FADE),
    ('transparent fill with visible outline',r'\1a&HFF&'+FADE),
    ('transparent fill with no outline',r'\1a&HFF&\bord0'+FADE),
    ('rotation',r'\frz10'+FADE),('clip',r'\clip(0,0,100,100)'+FADE),
    ('inverse clip',r'\iclip(0,0,100,100)'+FADE),('origin',r'\org(500,100)'+FADE),
    ('shear',r'\fax0.1'+FADE),('karaoke',r'\k20'+FADE),('fade timing',r'\fad(0,100)'+FADE),
    ('initial pos and move',r'\pos(500,100)'+FADE),('uppercase raw tags',FADE.upper())):
    case(name,changed(BASE,tags=tags),3 if name=='transparent fill with visible outline' else 0)
for name,movement in (
    ('horizontal drift',(480,95,485,100)),('far vertical source',(480,70,480,100)),
    ('timed move starts at event end',(480,95,480,100,500,500)),
    ('invalid move','(bad)'),('duplicate move','(480,95,480,100)\\move(480,95,480,100)')):
    case(name,changed(BASE,move=movement),0)
case('allowed timed move',[{**d,'move':(*d['move'],0,500)} if d['move'] else d for d in BASE],3,start=1)
case('zero source duration',changed(BASE,start=1.5),0)
case('comment source rows',changed(BASE,kind='Comment'),0)
case('multi-character fragments',changed(BASE,lambda i,d:i==0,word='ab'),0)
case('combining glyph',changed(BASE,lambda i,d:i==0,word='\u0301'),0)
case('space glyph',changed(BASE,lambda i,d:i==0,word=' '),0)
case('empty glyph',changed(BASE,lambda i,d:i==0,word=''),0)
case('inline layout',changed(BASE,lambda i,d:i==0,word='a{\\fs20}'),0)
for name,tags in (
    ('hold changes size',r'\t(0,100,\fs30)'),('hold translucent',r'\1a&H80&'),
    ('hold transformed opacity',r'\t(1500,2000,\alpha&HFF&)'),('hold invisible',r'\alpha&HFF&'),
    ('hold rotated',r'\frz10')):
    case(name,row()+[hold(tags=tags)],3 if name=='hold transformed opacity' else 0,**({'start':1} if name=='hold transformed opacity' else {}))
for name,tags,start in (
    ('terminal fade delays entrance',r'\t(1100,1200,\alpha&HFF&)',1.2),
    ('terminal fade preserves real gap',r'\t(500,600,\alpha&HFF&)',1),
    ('instant terminal fade',r'\t(1200,1200,\alpha&HFF&)',1.2),
    ('preceding remains visible','',1),
    ('preceding outline stays visible',r'\t(1100,1200,\1a&HFF&)',1),
    ('preceding shadow stays visible',r'\t(1100,1200,\1a&HFF&\3a&HFF&)',1),
    ('multiple preceding fade transforms',r'\t(1100,1200,\alpha&HFF&)\t(0,100,\1a&H00&)',1),
    ('preceding fade outside lifetime',r'\t(1100,1600,\alpha&HFF&)',1)):
    case(name,BASE+[hold('xyz',0,1.5,tags=tags)],3,start=start,previous_end=1.2 if start==1.2 else .6 if name=='terminal fade preserves real gap' else 1.5)
case('ambiguous preceding holds',BASE+[hold('xyz',0,1.5),hold('def',0,1.5)],3,start=1)
case('preceding different layer',BASE+[hold('xyz',0,1.5,layer=1,tags=r'\t(1100,1200,\alpha&HFF&)')],3,start=1)
case('preceding different position',BASE+[hold('xyz',0,1.5,x=501,tags=r'\t(1100,1200,\alpha&HFF&)')],3,start=1)

def inputs(module,descriptors,order):
    lines=[]
    for d in descriptors:
        if d['move'] is None:pose=f"\\pos({d['x']},{d['y']})"
        elif isinstance(d['move'],str):pose=r'\move'+d['move']
        else:pose=r'\move('+','.join(map(str,d['move']))+')'
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer',0)},{module.format_time(d['start'])},{module.format_time(d['end'])},Default,{d.get('name','')},0,0,0,,{{{pose}{d['tags']}}}{d['word']}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    items=list(doc.events.items())
    if order=='reversed':items.reverse()
    if order=='shuffled':random.Random(127).shuffle(items)
    return dict(items)
SPY_NAMES=('event_override_tokens','effective_state','parse_effect_move','parse_effect_transform',
    'simplify_text','simplify_visual_text','get_pos','apply_tag','inline_layout_key',
    'unrotated_text_state','placement_key','text_layout_key','replace_event','nearby_boundary_groups')
@contextlib.contextmanager
def recording(module,calls):
    originals={name:getattr(module,name) for name in SPY_NAMES}
    def wrap(name,original):
        def run(*args,**kwargs):
            calls.append((name,snapshot((args,kwargs))));return original(*args,**kwargs)
        return run
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_shrinking_row_stages']);checks=[]
engines={module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
for i,c in enumerate(CASES):
    if i%20==0:print(i,'shrinking-row scenarios compared',flush=True)
    for order in ('original','reversed','shuffled'):
        for mode in ('available','unavailable','none','failed_fit'):
            for blur in (0,2):
                compared=[]
                for module in (previous,current):
                    events=inputs(module,c['events'],order);before=snapshot(events);calls=[]
                    metric=None if mode=='none' else RecordingMetric(engines[module],mode)
                    with recording(module,calls):
                        args=(events,metric,blur)
                        result=tracer.runfunc(module.collapse_shrinking_glyph_rows,*args) if module is current and order=='original' and mode=='available' and blur==2 else module.collapse_shrinking_glyph_rows(*args)
                    out,count=result
                    assert before==snapshot(events),(c['name'],'input mutation')
                    assert (out is events)==(count==0),(c['name'],'return identity')
                    if mode=='available' and c['expected'] is not None:
                        assert count==c['expected'],(c['name'],'expected removal count',count,c['expected'])
                        if 'start' in c:
                            owner=next(e for e in out.values() if module.simplify_text(e.text,visible_only=True)[1] in ('abc','a b c'))
                            assert owner.start_s==c['start'],(c['name'],'handoff start',owner.start_s,c['start'])
                        if 'previous_end' in c:
                            predecessor=next(e for e in out.values() if module.simplify_text(e.text,visible_only=True)[1]=='xyz')
                            assert predecessor.end_s==c['previous_end'],(c['name'],'predecessor end',predecessor.end_s,c['previous_end'])
                    if mode in ('none','unavailable','failed_fit'):assert count==0,(c['name'],mode)
                    compared.append((snapshot(result),calls,[] if metric is None else metric.calls,
                        out is events,[k for k,e in out.items() if e is events.get(k)],list(out),
                        font_test_report(engines[module]).rows_joined,sorted(font_test_report(engines[module]).missing_families)))
                assert compared[0]==compared[1],(c['name'],order,mode,blur,'v148 equivalence')
                checks.append(dict(case=c['name'],order=order,metric=mode,max_blur=blur))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.collapse_shrinking_glyph_rows
        def wrapped(*args,**kwargs):
            before=snapshot((args[0],args[2:],kwargs));result=original(*args,**kwargs)
            captured.append((before,snapshot(result),snapshot(args[0])));return result
        module.collapse_shrinking_glyph_rows=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.collapse_shrinking_glyph_rows=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/shrinking-row-consolidation-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in {*audit['helpers'],'collapse_shrinking_glyph_rows'}:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==9 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/shrinking-row-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,complete_results_helper_and_font_calls_identical=True,return_and_retained_event_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'shrinking-row comparisons across',len(CASES),'scenarios; 2 focused conversions; all eight helpers and the main function exercised')
