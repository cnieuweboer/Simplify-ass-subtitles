import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare drawing runs, cached outline proofs, fragment reconstruction and ownership with v148."""
from pathlib import Path
from copy import deepcopy
from collections.abc import Iterator
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('vector_text_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
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
    if isinstance(value,(RecordingMetric,current.FontMetrics,previous.FontSpacing)):return 'font-metric'
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
engine=engines[current];assert engine.available
face=measurement_fonts(engine).matching_face('Arial',0,False);assert face is not None
sample=current._resolve_document_state(current.parse_subtitle_document(HEADER+'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\pos(500,100)}abc\n'))
STATE=next(iter(sample.events.values())).state
def event(kind='Dialogue',word='abc',start=1,end=3,x=500,y=100,tags='',**options):return dict(kind=kind,word=word,start=start,end=end,x=x,y=y,tags=tags,**options)
def sequence(text='abc',parts=None,space=False,frames=6,**drawing_options):
    parts=[text] if parts is None else parts
    if len(parts)==1:anchors=[500]
    else:
        positions=row_test_call(engine, 'authored_glyph_positions', STATE,text,500,1);assert positions is not None
        anchors=[];offset=0
        for word in parts:
            length=len(word.strip());xs=[x for c,x in positions[offset:offset+length]];offset+=length
            anchor=row_test_call(engine, 'fragment_anchor', STATE,xs,list(word.strip()),word.strip(),1,max_size_error=.2);assert anchor is not None
            anchors.append(anchor)
    cue=text
    if len(parts)>1:
        chunks=[];cursor=0
        for word in parts:
            cursor+=len(word);spaces=''
            while cursor<len(text) and text[cursor].isspace():spaces+=text[cursor];cursor+=1
            chunks.append(r'{\k0}'+word+spaces)
        cue=''.join(chunks)
    records=[event('Comment',cue,start=1.2,end=2.8)]
    for group,(word,x) in enumerate(zip(parts,anchors)):
        records.extend(event(word=word,x=x,start=1+2*i/frames,end=1+2*(i+1)/frames,drawing=True,group=group,frame=i,frames=frames,**drawing_options) for i in range(frames))
    return records
def changed(data,predicate=lambda i,d:d.get('drawing'),**changes):
    data=deepcopy(data)
    for i,d in enumerate(data):
        if predicate(i,d):d.update(changes)
    return data
BASE=sequence();FRAG=sequence(parts=['a','bc']);SPACED=sequence(text='abc de',parts=list('abcde'),space=True);CASES=[]
def case(name,data=BASE,expected=None,**options):CASES.append(dict(name=name,data=data,expected=expected,**options))
case('complete whole-line outline',expected=1,literal='abc')
case('complete karaoke fragments',FRAG,1,literal='abc')
case('authored spaces reconstructed',SPACED,1,literal='abc de')
case('single-frame drawing run',sequence(frames=1),1,literal='abc')
case('longer sampled drawing run',sequence(frames=11),1,literal='abc')
case('duplicate authored comment keeps first',BASE+[deepcopy(BASE[0])],1,literal='abc')
case('same source cached across competing cue timings',BASE+[event('Comment','abc',start=1.3,end=2.7)],0,cache='positive')
case('failed source fit cached across cue timings',changed(BASE+[event('Comment','abc',start=1.3,end=2.7)],tags=r'\fnMissingFont'),0,cache='negative')
case('outline cached across competing cue timings',BASE+[event('Comment','abc',start=1.3,end=2.7)],0,cache='outline')
case('text-backed cue rejected',BASE+[event(word='existing',start=1.2,end=2.8)],0)
case('short readable backing retained',BASE+[event(word='existing',start=1.2,end=1.99)],1)
case('backing at half cue duration',BASE+[event(word='existing',start=1.2,end=2)],0)
case('other-style backing retained',BASE+[event(word='existing',style='Other')],1)
case('same-style blank backing retained',BASE+[event(word=' ')],1)
case('different reconstructed lanes are ambiguous',BASE+changed(BASE[1:],layer=1),0)
later=deepcopy(BASE)
for d in later:d['start']+=4;d['end']+=4;d['name']='later'
case('independent cues use separate drawing sources',BASE+later,2)
case('whole-line comment text mismatch',changed(BASE,lambda i,d:d['kind']=='Comment',word='xyz'),0)
case('fragment cue without karaoke splits',changed(FRAG,lambda i,d:d['kind']=='Comment',word='abc'),0)
case('missing fragment outline',FRAG[:7],0)
case('fragment literal mismatch',changed(FRAG,lambda i,d:d.get('drawing') and d['group']==1,word='zz'),0)
case('fragment lane differs in layer',changed(FRAG,lambda i,d:d.get('drawing') and d['group']==1,layer=1),0)
case('fragment lane differs in y',changed(FRAG,lambda i,d:d.get('drawing') and d['group']==1,y=101),0)
case('fragment anchor too far',changed(FRAG,lambda i,d:d.get('drawing') and d['group']==1,x=700),0)
case('space-aware recovery unavailable',SPACED,0,fail_recover=True)
case('no-space fragment anchor fallback',FRAG,1,fail_recover=True,literal='abc')
case('no-space fallback cannot fit',FRAG,0,fail_recover=True,fail_anchor=True)
case('wrong recovered text uses no-space fallback',sequence(text='abcde',parts=list('abcde')),1,mismatch_recover=True,literal='abcde')
case('wrong recovered text cannot replace authored spaces',SPACED,0,mismatch_recover=True)
case('merged caption renderer rejects',FRAG,0,fail_render=True)
case('font control-point fitter rejects',BASE,0,fail_fit=True)
case('font control-point error exceeds tolerance',BASE,0,large_error=True)
case('empty input',[],0)
case('no drawing or comment styles',[event(word='ordinary')],0)
case('no authored cue',BASE[1:],0)
case('empty authored cue',changed(BASE,lambda i,d:d['kind']=='Comment',word=' '),0)
case('multiline authored cue',changed(BASE,lambda i,d:d['kind']=='Comment',word=r'a\Nbc'),0)
case('formatted authored comment rejected',changed(BASE,lambda i,d:d['kind']=='Comment',word=r'{\fs40}abc'),0)
case('zero-duration comment',changed(BASE,lambda i,d:d['kind']=='Comment',end=1.2),0)
case('drawing source font unavailable',changed(BASE,tags=r'\fnMissingFont'),0)
case('unsupported drawing commands',changed(BASE,path='m 0 0 s 1 1 2 2 3 3'),0)
case('empty drawing path',changed(BASE,path=''),0)
case('different outline skeleton',changed(BASE,word='abd'),0)
case('outline scale too large',changed(BASE,scale=1.21),0)
case('outline scale too small',changed(BASE,scale=.79),0)
case('drawing fs nonfinite',changed(BASE,tags=r'\fsnan'),0)
case('drawing position absent',changed(BASE,position=False),0)
case('drawing source zero duration',changed(BASE,lambda i,d:d.get('drawing') and d['frame']==2,end=1+4/6),0)
case('source interval gap splits run',changed(BASE,lambda i,d:d.get('drawing') and d['frame']==2,start=1.69),0)
case('competing overlapping drawing events',BASE+[deepcopy(BASE[2])],0)
case('tiny overlaps within tolerance',changed(BASE,lambda i,d:d.get('drawing') and d['frame']==2,start=1+4/6-.0005),1)
case('run starts too late',changed(BASE,lambda i,d:d.get('drawing') and d['frame']==0,start=1.212),0)
case('run ends too early',changed(BASE,lambda i,d:d.get('drawing') and d['frame']==5,end=2.788),0)
case('run far beyond cue allowance',changed(BASE,lambda i,d:d.get('drawing') and d['frame']==0,start=-2),0)
case('no visible sample paint',changed(BASE,tags=r'\1a&HFF&'),0)
case('fill alpha at visibility threshold',changed(BASE,tags=r'\1a&H10&'),0)
case('fill alpha below visibility threshold',changed(BASE,tags=r'\1a&H0F&'),1)
longest=deepcopy(BASE)
for d,(start,end) in zip(longest[1:],[(1,1.2),(1.2,1.4),(1.4,2.2),(2.2,2.4),(2.4,2.6),(2.6,3)]):
    d['start'],d['end']=start,end
    if d['frame']==2:d['tags']=r'\1c&H123456&'
case('longest visible sample supplies paint',longest,1,colour='123456')
case('sampled invisible frames with opaque hold',changed(BASE,lambda i,d:d.get('drawing') and d['frame'] in (0,5),tags=r'\1a&HFF&'),1)
case('drawing transforms only paint',changed(BASE,tags=r'\1c&H123456&\t(0,200,\1c&HABCDEF&\blur1)'),1)
for tags in (r'\move(500,100,510,100)',r'\clip(0,0,1000,1000)',r'\iclip(0,0,1000,1000)',r'\org(500,100)',r'\r',r'\t(0,200,\fs50)',r'\an4',r'\pbo1',r'\frz15',r'\fax.01',r'\fay.01',r'\u1',r'\s1',r'\i1',r'\fscx99',r'\fscy99',r'\p2'):
    case('drawing geometry guard '+tags,changed(BASE,tags=tags),0)
case('trailing drawing override retains original handling',changed(BASE,inline=True),1)
case('drawing scale markers are exact',changed(BASE,p_marker=10),0)
case('unrelated events retain object identity',BASE+[event(word='ordinary',style='Other',start=10,end=11)],1)
case('middle drawing override rejected',changed(BASE,inline_mid=True),0)
case('rejected outline fit cached across cue timings',changed(BASE+[event('Comment','abc',start=1.3,end=2.7)],scale=1.21),0,cache='rejected_outline')
inferred=sequence(frames=10)[1:]
for d in inferred:
    d['tags']=r'\1a&HFF&' if 2<=d['frame']<8 else r'\1a&H00&'
    if d['frame']==0:d['tags']+=r'\t(400,400,\1a&HFF&)\t(1600,1600,\1a&H00&)'
    if d['frame']==1:d['tags']+=r'\t(200,200,\1a&HFF&)\t(1400,1400,\1a&H00&)'
case('drawing evidence infers missing cue',inferred,1,literal='abc',timing=(1.4,2.6))
case('authored cue takes precedence over inference',inferred+[event('Comment','abc',start=1.4,end=2.6)],1,literal='abc',timing=(1.4,2.6))

def path_for(d):
    if 'path' in d:return d['path']
    outline=measurement_fonts(engine).cubic_outline(face,d['word']);assert outline is not None
    scale=measurement_fonts(engine).ass_em_scale(face)*40/outline[1]*d.get('scale',1)
    return ' '.join(v if isinstance(v,str) else f'{v*scale:.8f}' for v in outline[0])
def inputs(module,c,order):
    lines=[]
    for d in c['data']:
        text=d['word']
        if d.get('drawing'):
            tags=(f"\\pos({d['x']},{d['y']})" if d.get('position',True) else '')+f"\\p{d.get('p_marker',1)}"+d['tags']
            path=path_for(d)
            if d.get('inline_mid'):
                pieces=path.split();path=' '.join(pieces[:3])+r'{\fs41}'+' '.join(pieces[3:])
            text='{'+tags+'}'+path+(r'{\fs41}' if d.get('inline') else '')
        elif d['kind']=='Dialogue':text=f"{{\\pos({d['x']},{d['y']}){d['tags']}}}"+text
        lines.append(f"{d['kind']}: {d.get('layer',0)},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l',0)},0,0,{d.get('effect','')},{text}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));events=list(doc.events.values())
    for e,d in zip(events,c['data']):e.start_s,e.end_s=d['start'],d['end']
    if order=='reverse':events.reverse()
    if order=='shuffle':random.Random(132).shuffle(events)
    return {e.source_index:e for e in events}
class RecordingMetric:
    def __init__(self,engine,mode,c):self.engine,self.mode,self.case,self.calls=engine,mode,c,[]
    @property
    def available(self):return self.mode!='unavailable' and self.engine.available
    @property
    def missing(self):return font_test_report(self.engine).missing_families
    def __getattr__(self,name):
        original=(lambda *args,**kwargs:row_test_call(self.engine,name,*args,**kwargs)) if name in ('recover','fragment_anchor') else getattr(self.engine,name)
        if name not in ('matching_face','cubic_outline','ass_em_scale','decode_cubic_outline','recover','fragment_anchor'):return original
        def run(*args,**kwargs):
            result=original(*args,**kwargs)
            if name=='cubic_outline' and self.mode=='outline_missing':result=None
            if name=='ass_em_scale' and self.mode=='nominal_missing':result=None
            if name=='recover' and self.case.get('fail_recover'):result=None
            if name=='recover' and self.case.get('mismatch_recover') and result is not None:result=('wrong',)+tuple(result[1:])
            if name=='fragment_anchor' and self.case.get('fail_anchor'):result=None
            self.calls.append((name,snapshot((args,kwargs)),snapshot(result)));return result
        return run
NAMES=('simplify_text','event_override_tokens','inline_layout_key','tokenize_override','effective_state','get_pos','unrotated_text_state','geometry_key','infer_vector_text_cues','fit_cubic_points','simplify_visual_text','replace_event','render_simplified_caption','render_merged_caption')
@contextlib.contextmanager
def recording(module,calls,c):
    originals={name:getattr(module,name) for name in NAMES}
    def wrap(name,original):
        def run(*args,**kwargs):
            calls.append((name,snapshot((args,kwargs))));result=original(*args,**kwargs)
            if name=='fit_cubic_points' and c.get('fail_fit'):return None
            if name=='fit_cubic_points' and c.get('large_error') and result is not None:return tuple(result[:3])+(100,)
            if name=='render_merged_caption' and c.get('fail_render'):return None
            return result
        return run
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix]);checks=[];cache_checks=[]
for i,c in enumerate(CASES):
    if i%20==0:print(i,'vector text scenarios compared',flush=True)
    for order in ('original','reverse','shuffle'):
        for mode in ('real','none','unavailable','outline_missing','nominal_missing'):
            for blur in (0,1):
                compared=[]
                for module in (previous,current):
                    parsed=inputs(module,c,order);before=snapshot(parsed);before_keys=list(parsed);calls=[];metric=None if mode=='none' else RecordingMetric(engines[module],mode,c)
                    missing_before=set(font_test_report(engines[module]).missing_families)
                    with recording(module,calls,c):
                        args=(parsed,metric,blur)
                        result=tracer.runfunc(module.recover_vector_text_cues,*args) if module is current and order=='original' and blur==0 else module.recover_vector_text_cues(*args)
                    out,n=result;assert before==snapshot(parsed) and before_keys==list(parsed),(c['name'],'input ownership')
                    expected=c['expected'] if mode=='real' else 0
                    if expected is not None:assert n==expected,(c['name'],mode,n,expected)
                    if n and any(k in c for k in ('literal','colour','timing')):
                        recovered=[e for idx,e in out.items() if idx in parsed and e is not parsed[idx]]
                        assert len(recovered)==n
                        if c.get('literal'):assert all(module.simplify_text(e.text,visible_only=True)[1]==c['literal'] for e in recovered)
                        if c.get('colour'):assert all(e.state['1c']==c['colour'] for e in recovered)
                        if c.get('timing'):assert all((e.start_s,e.end_s)==c['timing'] for e in recovered)
                    compared.append((snapshot(result),list(out),calls,None if metric is None else metric.calls,out is parsed,{idx:e is parsed.get(idx) for idx,e in out.items()},font_test_report(engines[module]).missing_families-missing_before))
                    if module is current and c.get('cache') and mode=='real' and order=='original' and blur==0:
                        metric_calls=[v for v in metric.calls if v[0] in ('matching_face','cubic_outline')]
                        assert sum(v[0]=='matching_face' for v in metric_calls)==1,(c['name'],'source cache miss count')
                        assert sum(v[0]=='cubic_outline' for v in metric_calls)==(0 if c['cache']=='negative' else 1)
                        cache_checks.append(dict(case=c['name'],one_source_fit=True))
                assert compared[0]==compared[1],(c['name'],order,mode,blur,'v148 parity')
                checks.append(dict(case=c['name'],order=order,metric=mode,max_blur=blur))
for name,data in [('Vector-text-whole-source.ass',BASE),('Vector-text-fragments-source.ass',SPACED),('Vector-text-inferred-source.ass',inferred)]:
    parsed=inputs(current,dict(data=data),'original')
    (ROOT/'test-data'/name).write_text(HEADER+''.join(e.kind+': '+','.join(e.fields())+'\n' for e in parsed.values()))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass','Vector-text-whole-source.ass','Vector-text-fragments-source.ass','Vector-text-inferred-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.recover_vector_text_cues
        def wrapped(parsed,metric,max_blur=0):
            before=snapshot(parsed);result=original(parsed,metric,max_blur)
            captured.append((before,snapshot(result),snapshot(parsed),result[0] is parsed));return result
        module.recover_vector_text_cues=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.recover_vector_text_cues=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/vector-text-consolidation-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==12 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/vector-text-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,complete_results_helper_calls_font_calls_missing_updates_and_event_identity_identical=True,cache_checks=cache_checks,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'vector text comparisons across',len(CASES),'scenarios;',len(cache_checks),'cache assertions;',len(focused),'focused conversions; all 12 retained helpers exercised')
