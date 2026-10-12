from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare boundary glyph classification, matching, fitting and ownership with v130."""
from pathlib import Path
from copy import deepcopy
from collections.abc import Iterator
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('boundary_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
Style: Other,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,Iterator):return ('iterator',type(value).__name__)
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
engine=engines[current];assert engine.available
sample=current._resolve_document_state(current.parse_subtitle_document(HEADER+r'Dialogue: 0,0:00:01.50,0:00:03.50,Default,,0,0,0,,{\pos(500,100)}abc'+'\n'))
STATE=next(iter(sample.events.values())).state
def event(word,x=500,start=1.5,end=3.5,phase='hold',tags='',**options):
    return dict(word=word,x=x,y=100,start=start,end=end,phase=phase,tags=tags,**options)
def sequence(word='abc',phase='entrance',fsp=0):
    state=dict(STATE,fsp=fsp);positions=row_test_call(engine, 'authored_glyph_positions', state,word,500,1);assert positions is not None
    tags=rf'\fsp{fsp}' if fsp else ''
    glyphs=[event(c,x=x,start=1 if phase=='entrance' else 3.5,end=1.5 if phase=='entrance' else 4,phase=phase,tags=tags) for c,x in positions]
    return glyphs+[event(word,tags=tags)]
def changed(data,predicate=lambda i,d:d['phase']!='hold',**changes):
    data=deepcopy(data)
    for i,d in enumerate(data):
        if predicate(i,d):d.update(changes)
    return data
BASE=sequence();EXIT=sequence(phase='exit');CASES=[]
def case(name,data=BASE,expected=None,**options):CASES.append(dict(name=name,data=data,expected=expected,**options))
case('complete rotating entrance',expected=3)
case('complete flying exit',EXIT,3)
case('one caption owns entrance and exit independently',BASE[:3]+EXIT[:3]+BASE[3:],6)
case('authored tracking',sequence(fsp=2),3)
case('two glyphs cannot prove removal',sequence('ab'),0)
case('multiple retained words',BASE[:3]+[event('a',x=BASE[0]['x']),event('bc',x=row_test_call(engine, 'fragment_anchor', STATE,[d['x'] for d in BASE[1:3]],['b','c'],'bc',1,allow_tracking=True))],3)
absorbed=deepcopy(BASE[:3]);absorbed[0]['ret_end']=3.5
absorbed+=[event('bc',x=row_test_call(engine, 'fragment_anchor', STATE,[d['x'] for d in BASE[1:3]],['b','c'],'bc',1,allow_tracking=True))]
case('absorbed entrance glyph is protected',absorbed,2)
case('absorbed entrance closest boundary used once',changed(absorbed,lambda i,d:i==0,ret_start=1.48),2)
case('all glyphs absorbed into retained holds',changed(BASE[:3],ret_end=3.5),0)
case('extended exit is not protected',changed(EXIT,ret_end=5),0)
case('extended entrance must retain same literal',changed(absorbed,lambda i,d:i==0,ret_word='z'),0)
case('extended entrance must retain same anchor',changed(absorbed,lambda i,d:i==0,ret_x=600),0)
case('extended entrance must retain upright geometry',changed(absorbed,lambda i,d:i==0,ret_tags=r'\frz15'),0)
case('extended entrance must retain opaque paint',changed(absorbed,lambda i,d:i==0,ret_tags=r'\1a&H01&'),0)
case('long frozen entrance cannot prove a held word',BASE[:3],0)
case('missing glyph',BASE[:2]+BASE[3:],0)
case('missing caption',BASE[:3],0)
case('wrong held literal',changed(BASE,lambda i,d:d['phase']=='hold',word='xyz'),0)
case('caption with spaces is rejected',changed(BASE,lambda i,d:d['phase']=='hold',word='a bc'),0)
case('duplicate glyphs at one boundary',BASE+BASE[:3],0)
case('duplicate held words',BASE+BASE[3:],0)
case('duplicate glyph anchors',changed(BASE,lambda i,d:i==1,x=BASE[0]['x']),0)
case('competing entrances share one held owner',BASE+changed(BASE[:3],end=1.52),0)
case('competing exits share one held owner',EXIT+changed(EXIT[:3],start=3.52),0)
case('entrance within timing tolerance',changed(BASE,lambda i,d:d['phase']=='hold',start=1.55),3)
case('entrance outside timing tolerance',changed(BASE,lambda i,d:d['phase']=='hold',start=1.551),0)
case('exit within timing tolerance',changed(EXIT,lambda i,d:d['phase']=='hold',end=3.55),3)
case('exit outside timing tolerance',changed(EXIT,lambda i,d:d['phase']=='hold',end=3.551),0)
case('brief independent held caption',changed(BASE,lambda i,d:d['phase']=='hold',end=1.55),3)
case('held anchor outside font fit',changed(BASE,lambda i,d:d['phase']=='hold',x=510),0)
case('held font unavailable',changed(BASE,lambda i,d:d['phase']=='hold',tags=r'\fnMissingFont'),0)
case('source y differs',changed(BASE,y=101),0)
case('source name differs',changed(BASE,name='other'),0)
case('source style differs',changed(BASE,style='Other'),0)
case('source placement differs',changed(BASE,margin_l=10),0)
case('source font differs',changed(BASE,tags=r'\fnMissingFont'),0)
case('retained caption source anchor differs',changed(BASE,lambda i,d:d['phase']=='hold',ret_x=501),0)
case('retained caption transparent',changed(BASE,lambda i,d:d['phase']=='hold',ret_tags=r'\1a&H01&'),0)
case('retained caption rotated',changed(BASE,lambda i,d:d['phase']=='hold',ret_tags=r'\frz15'),0)
case('retained caption clipped',changed(BASE,lambda i,d:d['phase']=='hold',ret_tags=r'\clip(0,0,1000,1000)'),0)
case('retained comment',changed(BASE,ret_kind='Comment'),0)
case('source not indexed',BASE,0,missing_sources=True)
case('missing caption visible text',BASE,0,missing_visible=True)
case('empty input',[],0)
for literal in ('','ab',' ', '\u0301'):
    case('source glyph guard '+repr(literal),changed(BASE,word=literal),0)
for tags in (r'\1a&H01&',r'\p1',r'\clip(0,0,1000,1000)',r'\org(1,1)',r'\shad1',r'\fax.01',r'\fay-.01'):
    case('source paint geometry guard '+tags,changed(BASE,tags=tags),0)
for fad in ('',r'\fad(100,0)\fad(100,0)',r'\fad(bad,0)',r'\fad(100)',r'\fad(nan,0)',r'\fad(-1,0)',r'\fad(100,0)\fade(255,0,255,0,100,400,500)',r'\fad(0,0)',r'\fad(600,0)',r'\fad(100,1)'):
    case('entrance fade '+repr(fad),changed(BASE,fade=fad),0)
for transform in ('',r'\t(bad)',r'\t(0,500,\fs50)',r'\t(0,500,\frz15)',r'\t(0,200,\frz0)\t(200,500,\frz0)'):
    case('entrance transform '+repr(transform),changed(BASE,transform=transform),0)
case('entrance originally upright',changed(BASE,rotation=0),0)
case('entrance without source position',changed(BASE,source_position=False),0)
case('source inline layout',changed(BASE,inline=True),0)
case('source zero duration',changed(BASE,end=1),0)
for move in ('(bad)','(1,2,3)','(nan,100,500,120)','(500,100,500,100)'):
    case('invalid flying move '+move,changed(EXIT,move=move),0)
case('exit also has source position',changed(EXIT,source_position=True),0)
case('exit also has transform',changed(EXIT,transform=r'\t(0,500,\frz0)'),0)
case('exit initially rotated',changed(EXIT,rotation=15),0)
case('exit wrong fade direction',changed(EXIT,fade=r'\fad(100,0)'),0)
case('exit fade exceeds slack',changed(EXIT,fade=r'\fad(0,551)'),0)
case('exit fade meets slack bound',changed(EXIT,fade=r'\fad(0,550)'),3)
case('exit move uses endpoint slack',changed(EXIT,move_time=(0,550)),3)
case('exit move exceeds endpoint slack',changed(EXIT,move_time=(0,551)),0)
case('unrelated caption retained',BASE+[event('unrelated',x=1000,start=10,end=11,name='other')],3)

def inputs(module,c,event_order,source_order):
    lines=[];data=c['data']
    for d in data:
        x,y=d['x'],d['y'];phase=d['phase'];tags=d['tags']
        if phase=='entrance':
            tags=(rf'\pos({x},{y})' if d.get('source_position',True) else '')+rf"\frz{d.get('rotation',30)}"+d.get('fade',r'\fad(100,0)')+d.get('transform',r'\t(0,500,\frz0)')+tags
        elif phase=='exit':
            move=d.get('move',f"({x},{y},{x},{y+20}"+(','+','.join(map(str,d['move_time'])) if 'move_time' in d else '')+')')
            tags=(rf'\pos({x},{y})' if d.get('source_position',False) else '')+r'\move'+move+rf"\frz{d.get('rotation',0)}"+d.get('fade',r'\fad(0,500)')+d.get('transform','')+tags
        else:tags=rf'\pos({x},{y})'+tags
        word=d['word']+(r'{\fs41}' if d.get('inline') else '')
        lines.append(f"Dialogue: {d.get('layer',0)},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l',0)},0,0,,{{{tags}}}{word}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));sources=list(doc.events.values());events=[]
    for original,d in zip(sources,data):
        original.start_s,original.end_s=d['start'],d['end']
        text=rf"{{\pos({d.get('ret_x',d['x'])},{d['y']}){d['tags']}{d.get('ret_tags','')}}}"+d.get('ret_word',d['word'])
        e=module.replace_event(original,text=text,start_s=d.get('ret_start',d['start']),end_s=d.get('ret_end',d['end']),kind=d.get('ret_kind','Dialogue'))
        events.append(e)
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events};visible[-999]='metadata'
    if c.get('missing_visible') and events:visible.pop(events[-1].source_index)
    if c.get('missing_sources'):sources=[]
    if event_order=='reverse':events.reverse()
    if event_order=='shuffle':random.Random(131).shuffle(events)
    if source_order=='reverse':sources.reverse()
    if source_order=='shuffle':random.Random(131).shuffle(sources)
    return events,visible,{e.source_index:e for e in sources}
class RecordingMetric:
    def __init__(self,engine,mode):self.engine,self.mode,self.calls=engine,mode,[]
    @property
    def available(self):return self.mode!='unavailable' and self.engine.available
    def fragment_anchor(self,*args,**kwargs):
        result=row_test_call(self.engine, 'fragment_anchor', *args,**kwargs)
        if self.mode=='failed_fit':result=None
        if self.mode=='distant_fit' and result is not None:result+=100
        self.calls.append((snapshot((args,kwargs)),result));return result
NAMES=('inline_layout_key','get_pos','upright_text_state','placement_key','text_layout_key','simplify_text','event_override_tokens','effective_state','opaque_text_effect_state','parse_effect_transform','unrotated_text_state','apply_tag','parse_effect_move','nearby_boundary_groups')
@contextlib.contextmanager
def recording(module,calls):
    originals={name:getattr(module,name) for name in NAMES}
    def wrap(name,original):
        def run(*args,**kwargs):calls.append((name,snapshot((args,kwargs))));return original(*args,**kwargs)
        return run
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix]);checks=[]
for i,c in enumerate(CASES):
    if i%20==0:print(i,'boundary glyph scenarios compared',flush=True)
    for event_order in ('original','reverse','shuffle'):
        for source_order in ('original','reverse','shuffle'):
            for mode in ('real','none','unavailable','failed_fit','distant_fit'):
                compared=[]
                for module in (previous,current):
                    events,visible,sources=inputs(module,c,event_order,source_order);before=snapshot((events,visible,sources));calls=[]
                    metric=None if mode=='none' else RecordingMetric(engines[module],mode)
                    with recording(module,calls):
                        args=(events,visible,sources,metric)
                        out=tracer.runfunc(module.match_boundary_glyph_effects,*args) if module is current and event_order=='original' and source_order=='original' and mode=='real' else module.match_boundary_glyph_effects(*args)
                    assert before==snapshot((events,visible,sources)),(c['name'],'input ownership')
                    expected=c['expected'] if mode=='real' else 0
                    if expected is not None:assert len(out)==expected,(c['name'],mode,len(out),expected)
                    assert out<={e.source_index for e in events}
                    compared.append((out,calls,None if metric is None else metric.calls))
                assert compared[0]==compared[1],(c['name'],event_order,source_order,mode,'v130 parity')
                checks.append(dict(case=c['name'],event_order=event_order,source_order=source_order,metric=mode))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.match_boundary_glyph_effects
        def wrapped(events,visible,sources,metric):
            before=snapshot((events,visible,sources));result=original(events,visible,sources,metric)
            captured.append((before,snapshot(result),snapshot((events,visible,sources))));return result
        module.match_boundary_glyph_effects=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.match_boundary_glyph_effects=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/boundary-glyph-extraction-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==12 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/boundary-glyph-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,complete_results_helper_calls_and_font_fits_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'boundary glyph comparisons across',len(CASES),'scenarios; 2 focused conversions; all 12 helpers exercised')
