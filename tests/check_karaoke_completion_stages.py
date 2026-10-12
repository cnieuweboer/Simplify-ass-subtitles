import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare karaoke source filtering, transition proof, sweep ordering and paint edits with v129."""
from pathlib import Path
from copy import deepcopy
from collections.abc import Iterator
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('karaoke_completion_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
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
BEFORE='112233';AFTER='445566'
def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,Iterator):return ('iterator',type(value).__name__)
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def event(word='A',x=100,y=100,start=1,end=5,tags='',**options):return dict(word=word,x=x,y=y,start=start,end=end,tags=tags,**options)
def sequence(begins=(2,2.2,2.4),ends=None,words=('A','B','C'),entrance=False):
    ends=tuple(b+.2 for b in begins) if ends is None else ends;retained=[];sources=[]
    for i,(word,begin,end) in enumerate(zip(words,begins,ends)):
        x=100+i*30;start=1.2 if entrance else 1
        retained.append(event(word,x,tags=rf'\1c&H{BEFORE}&',link=(i,'entrance' if entrance else 'before')))
        if entrance:sources.append(event(word,x,end=1.2,tags=rf'\1c&H{BEFORE}&\frz15',group=i,phase='entrance'))
        sources.extend([event(word,x,start=start,end=begin,tags=rf'\1c&H{BEFORE}&',group=i,phase='before'),
            event(word,x,start=begin,end=end,tags=rf'\1c&H{BEFORE}&\t(0,{(end-begin)*1000:.6f},\1c&H{AFTER}&)',group=i,phase='transition'),
            event(word,x,start=end,end=5,tags=rf'\1c&H{AFTER}&',group=i,phase='after')])
    return dict(retained=retained,sources=sources)
def changed(data,side='sources',predicate=lambda i,d:True,**changes):
    result=deepcopy(data)
    for i,d in enumerate(result[side]):
        if predicate(i,d):d.update(changes)
    return result
transition=lambda i,d:d.get('phase')=='transition'
after=lambda i,d:d.get('phase')=='after'
before=lambda i,d:d.get('phase')=='before'
BASE=sequence();CASES=[]
def case(name,data=None,expected=None,**options):CASES.append(dict(name=name,data=BASE if data is None else data,expected=expected,**options))
case('complete forward sweep',expected=3,colour=AFTER)
case('complete reverse sweep',sequence(begins=(2.4,2.2,2)),3,colour=AFTER)
case('independent monotonic start/end directions',sequence(begins=(2,2.1,2.2),ends=(3,2.9,2.8)),3,colour=AFTER)
case('absorbed rotating entrances',sequence(entrance=True),3,colour=AFTER)
case('simultaneous activation',sequence(begins=(2,2,2)),0)
case('unordered activation',sequence(begins=(2,2.4,2.2)),0)
case('unordered completion',sequence(begins=(2,2.1,2.2),ends=(3,3.4,3.2)),0)
case('empty inputs',dict(retained=[],sources=[]),0)
case('single retained fragment',dict(retained=BASE['retained'][:1],sources=BASE['sources']),0)
case('no matching sources',dict(retained=BASE['retained'],sources=[]),0)
case('two-fragment sweep',sequence(begins=(2,2.2),words=('ab','cd')),2,colour=AFTER)
case('multiple word fragments',sequence(words=('Alpha','beta','gamma')),3,colour=AFTER)
case('source-phase ordering reversed',dict(retained=BASE['retained'],sources=list(reversed(BASE['sources']))),3,colour=AFTER)
case('retained gradient uses shared destination',changed(BASE,'retained',tags=r'\1c&H778899&'),3,colour=AFTER)
different_paints=deepcopy(BASE)
for d in different_paints['sources']:
    if d['group']==1 and d['phase'] in ('transition','after'):
        d['tags']=d['tags'].replace(AFTER,'123456')
case('different destination paints',different_paints,0)
case('no transforms in source',changed(BASE,predicate=transition,tags=rf'\1c&H{BEFORE}&'),0)
case('no primary-colour change',changed(BASE,predicate=transition,tags=r'\1c&H112233&\t(0,200,\3c&HFFFFFF&)'),0)
case('two transforms in one phase',changed(BASE,predicate=transition,tags=r'\1c&H112233&\t(0,100,\1c&H445566&)\t(100,200,\3c&HFFFFFF&)'),0)
case('unsupported geometry transform',changed(BASE,predicate=transition,tags=r'\1c&H112233&\t(0,200,\1c&H445566&\fs50)'),0)
case('unsupported alpha transform',changed(BASE,predicate=transition,tags=r'\1c&H112233&\t(0,200,\1c&H445566&\alpha&HFF&)'),0)
case('invalid transform',changed(BASE,predicate=transition,tags=r'\1c&H112233&\t(bad,\1c&H445566&)'),0)
case('source fill translucent',changed(BASE,predicate=transition,tags=r'\1a&H01&\1c&H112233&\t(0,200,\1c&H445566&)'),0)
case('source outline translucent',changed(BASE,predicate=transition,tags=r'\3a&H01&\1c&H112233&\t(0,200,\1c&H445566&)'),0)
case('source drawing phase',changed(BASE,predicate=transition,tags=r'\p1\1c&H112233&\t(0,200,\1c&H445566&)'),0)
case('source inline phase',changed(BASE,predicate=transition,word=r'A{\1c&H112233&}'),None)
case('source layout mismatch',changed(BASE,predicate=transition,tags=r'\fs41\1c&H112233&\t(0,200,\1c&H445566&)'),0)
case('source clipped phase',changed(BASE,predicate=transition,tags=r'\clip(0,0,1000,1000)\1c&H112233&\t(0,200,\1c&H445566&)'),0)
case('competing duplicate source phase',dict(retained=BASE['retained'],sources=BASE['sources']+[deepcopy(BASE['sources'][1])]),0)
case('missing source phase',dict(retained=BASE['retained'],sources=BASE['sources'][:1]+BASE['sources'][2:]),0)
case('colour cycles have two transitions',dict(retained=BASE['retained'],sources=BASE['sources']+[event('A',100,start=3,end=3.2,tags=r'\1c&H445566&\t(0,200,\1c&H112233&)',group=0,phase='cycle')]),0)
case('source temporal gap',changed(BASE,predicate=after,start=3),0)
case('source temporal overlap',changed(BASE,predicate=after,start=2),0)
case('source initial gap',changed(BASE,predicate=before,start=1.02),0)
case('source incomplete tail',changed(BASE,predicate=after,end=4.98),0)
case('source runs before retained cue',changed(BASE,predicate=before,start=.99),0)
case('source runs after retained cue',changed(BASE,predicate=after,end=5.01),0)
case('unrelated before-hold paint',changed(BASE,predicate=before,tags=r'\1c&H778899&'),0)
case('unrelated completed-hold paint',changed(BASE,predicate=after,tags=r'\1c&H778899&'),0)
# A late transform may begin after the end of its source phase; it is rejected by the parser.
case('transform beyond phase lifetime',changed(BASE,predicate=transition,tags=r'\1c&H112233&\t(300,400,\1c&H445566&)'),0)
for hold in (.019,.02,.021):
    ends=tuple(5-hold+i*.005 for i in range(3));begins=tuple(e-.2 for e in ends)
    case('completed hold threshold '+str(hold),sequence(begins=begins,ends=ends),0 if hold<.02 else 3 if hold>.02 else None)
# One complete hold is enough; other fragments still need exact source coverage.
no_hold=deepcopy(BASE)
for i,d in enumerate(no_hold['sources']):
    if d['phase']=='transition':d['end']=5
    if d['phase']=='after':d['start']=5
case('no explicit completed hold',no_hold,0)
one_hold=deepcopy(no_hold)
for d,original in zip(one_hold['sources'],BASE['sources']):
    if d['group']==0:d.update(original)
case('one completed fragment is enough',one_hold,3,colour=AFTER)
for tag in (r'\clip(0,0,1000,1000)',r'\iclip(0,0,1000,1000)',r'\org(100,100)',r'\frz15',r'\1a&H01&'):
    case('retained guard '+tag,changed(BASE,'retained',tags=tag),0)
case('retained missing word',changed(BASE,'retained',missing_word=True),0)
case('retained unpositioned',changed(BASE,'retained',position=False),0)
case('retained comment',changed(BASE,'retained',kind='Comment'),0)
case('duplicate row anchors',changed(BASE,'retained',x=100),0)
case('row anchors too distant',changed(BASE,'retained',predicate=lambda i,d:i==2,x=500),None)
for spacing in (120,120.001):
    spaced=deepcopy(BASE)
    for i,d in enumerate(spaced['retained']):d['x']=100+i*spacing
    for d in spaced['sources']:d['x']=100+d['group']*spacing
    case('row anchor spacing '+str(spacing),spaced,3 if spacing==120 else 0,**({'colour':AFTER} if spacing==120 else {}))
case('retained inline layout',changed(BASE,'retained',word=r'A{\fs40}B'),0)
case('retained y splits row',changed(BASE,'retained',predicate=lambda i,d:i==0,y=101),2)
case('retained style splits row',changed(BASE,'retained',predicate=lambda i,d:i==0,style='Other'),2)
case('retained name splits row',changed(BASE,'retained',predicate=lambda i,d:i==0,name='other'),2)
case('retained margin splits row',changed(BASE,'retained',predicate=lambda i,d:i==0,margin_l=10),2)
case('retained end string splits row',changed(BASE,'retained',predicate=lambda i,d:i==0,end_text='0:00:05.0'),2)
case('source name mismatch',changed(BASE,name='other'),0)
case('source margin mismatch',changed(BASE,margin_l=10),0)
case('source kind mismatch',changed(BASE,kind='Comment'),0)
case('source anchor mismatch',changed(BASE,x=101),0)
case('source literal mismatch',changed(BASE,word='Z'),0)
# Keep original colours while changing only the equivalent rotation representation.
turns=deepcopy(BASE)
for d in turns['sources']:d['tags']=r'\frz360'+d['tags']
case('whole-turn source rotation matching',turns,3,colour=AFTER)
turns2=deepcopy(turns)
for d in turns2['retained']:d['tags']=r'\frz-360'+d['tags']
case('opposite whole-turn representations',turns2,3,colour=AFTER)
for channel in ('3c','bord','xbord','ybord','blur','be'):
    data=deepcopy(BASE);value='&HABCDEF&' if channel=='3c' else '3'
    for d in data['sources']:
        if d['phase']=='transition':d['tags']=d['tags'].replace(r'\1c&H445566&)',rf'\1c&H445566&\{channel}{value})')
        if d['phase']=='after':d['tags']+=rf'\{channel}{value}'
    case('destination paint field '+channel,data,3,colour=AFTER)
leading=deepcopy(BASE)
for d in leading['retained']:d['leading_literal']=True
case('retained literal before first override',leading,3)
noise=deepcopy(BASE);noise['sources']+=[event('Z',900,start=0,end=100,tags=r'\t(bad)'),event('A',100,start=0,end=100,name='other'),event('A',100,start=0,end=100,kind='Comment')]
case('unneeded sources are filtered',noise,3,colour=AFTER)
case('source linking absent',changed(BASE,'retained',no_link=True),3,colour=AFTER)
case('visible-map metadata entry retained',expected=3,colour=AFTER)

def inputs(module,c,event_order,source_order):
    data=c['data'];records=data['sources']+data['retained'];lines=[]
    for d in records:
        tags=(f"\\pos({d['x']},{d['y']})" if d.get('position',True) else '')+d['tags']
        body=d['word']+'{'+tags+'}' if d.get('leading_literal') else '{'+tags+'}'+d['word']
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer',0)},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l',0)},0,0,,{body}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));parsed=list(doc.events.values());n=len(data['sources']);sources=parsed[:n];events=parsed[n:]
    links={}
    for e,d in zip(parsed,records):
        e.start_s,e.end_s=d['start'],d['end']
        if 'end_text' in d:e.end=d['end_text']
        if 'group' in d:links[d['group'],d['phase']]=e.source_index
    for e,d in zip(events,data['retained']):
        if not d.get('no_link') and d['link'] in links:e.source_index=links[d['link']]
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e,d in zip(events,data['retained']) if not d.get('missing_word')};visible[999999]='metadata'
    if event_order=='reversed':events.reverse()
    if event_order=='shuffled':random.Random(130).shuffle(events)
    if source_order=='reversed':sources.reverse()
    if source_order=='shuffled':random.Random(130).shuffle(sources)
    return events,visible,{e.source_index:e for e in sources}
SPY_NAMES=('get_pos','inline_layout_key','upright_text_state','unrotated_text_state',
    'effective_state','placement_key','text_layout_key','text_height','simplify_text',
    'event_override_tokens','parse_effect_transform','apply_tag','render_tag','replace_event')
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
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_karaoke_completion_stages']);checks=[]
for i,c in enumerate(CASES):
    if i%20==0:print(i,'karaoke-completion scenarios compared',flush=True)
    for event_order in ('original','reversed','shuffled'):
        for source_order in ('original','reversed','shuffled'):
            compared=[]
            for module in (previous,current):
                events,visible,sources=inputs(module,c,event_order,source_order);before=snapshot((events,visible,sources));calls=[]
                with recording(module,calls):out=tracer.runfunc(module.normalize_karaoke_completion_paint,events,visible,sources) if module is current and event_order=='original' and source_order=='original' else module.normalize_karaoke_completion_paint(events,visible,sources)
                assert before==snapshot((events,visible,sources)),(c['name'],'input ownership')
                changed_count=sum(a is not b for a,b in zip(out,events))
                if c['expected'] is not None:assert changed_count==c['expected'],(c['name'],'expected replacements',changed_count,c['expected'])
                if 'colour' in c:assert all(e.state['1c']==c['colour'] for e in out),(c['name'],'destination paint')
                assert len(out)==len(events)
                for e,original in zip(out,events):
                    assert e.source_index==original.source_index and e.start_s==original.start_s and e.end_s==original.end_s and e.fields()[:9]==original.fields()[:9],(c['name'],'identity/timing/metadata')
                    for field in ('fn','fs','fscx','fscy','fsp','an','b','i','u','s','frz','frx','fry','pos'):
                        assert e.state.get(field)==original.state.get(field),(c['name'],'geometry',field)
                compared.append((snapshot(out),calls,out is events,[a is b for a,b in zip(out,events)]))
            assert compared[0]==compared[1],(c['name'],event_order,source_order,'v129 equivalence')
            checks.append(dict(case=c['name'],event_order=event_order,source_order=source_order))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.normalize_karaoke_completion_paint
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            captured.append((before,snapshot(result),snapshot((args,kwargs))));return result
        module.normalize_karaoke_completion_paint=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.normalize_karaoke_completion_paint=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/karaoke-completion-extraction-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==12 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/karaoke-completion-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,complete_results_and_helper_calls_identical=True,return_and_retained_event_identity_identical=True,geometry_timing_metadata_and_count_unchanged=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'karaoke-completion comparisons across',len(CASES),'scenarios; 2 focused conversions; all 12 helpers exercised')
