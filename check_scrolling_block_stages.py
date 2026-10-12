from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare scrolling motion, matching, policy and reports with immutable v148."""
from pathlib import Path
from copy import deepcopy
from collections.abc import Iterator
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace,io
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('scrolling_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,0,0
Style: Other,Arial,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def snapshot(v):
    if type(v).__name__ == "Event":return snapshot(event_comparison_fields(v))
    if isinstance(v,type({}.values())):return tuple(snapshot(x) for x in v)
    if isinstance(v,Iterator):return ('iterator',type(v).__name__)
    if isinstance(v,float) and not math.isfinite(v):return repr(v)
    if isinstance(v,dict):return {k:snapshot(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return tuple(snapshot(x) for x in v)
    if isinstance(v,set):return frozenset(snapshot(x) for x in v)
    if isinstance(v,(current.FontMetrics,previous.FontSpacing)):return 'font-metric'
    if hasattr(v,'__dict__'):return snapshot(vars(v))
    return v

def frames(labels=('One','Two','Three'),positions=(300,550,1200),distance=700,duration=2,count=40,horizontal=False,start=1,extra='',origins=False,motion=None):
    rows=[]
    for row,literal in enumerate(labels):
        for i in range(count):
            fraction=i/(count-1) if count>1 else 0
            moving=positions[row]-distance*fraction
            x,y=(moving,100+row*200) if horizontal else (400,moving)
            if motion:x,y=motion(row,i,x,y)
            tags=extra(row,i) if callable(extra) else extra
            origin=fr'\org({x:g},{y:g})' if origins else ''
            at=start+i*duration/count
            rows.append(dict(text=fr'{{\an5\pos({x:g},{y:g})'+origin+tags+'}'+literal,start=at,end=at+duration/count,row=row,frame=i))
    return rows

def changed(data,predicate=lambda d:True,**changes):
    result=deepcopy(data)
    for d in result:
        if predicate(d):d.update({k:(v(d) if callable(v) else v) for k,v in changes.items()})
    return result
BASE=frames();CASES=[]
def case(name,data=BASE,**options):CASES.append(dict(name=name,data=data,**options))
case('coherent three-line scroll',reports=1,peak=3,removed=120)
case('upward scroll remains disabled at zero')
case('two spatial lines do not prove a block',frames(labels=('One','Two'),positions=(300,550)),reports=0)
case('single travelling line retained',frames(labels=('Solo',),positions=(300,)),reports=0)
case('short travel retained',frames(distance=400),reports=0)
case('short duration retained',frames(duration=.8,count=16),reports=0)
case('fewer than eight frames retained',frames(count=7,duration=.7,distance=300),reports=0)
case('eight frames at frame-duration bound',frames(positions=(90,150,340),distance=150,duration=1.28,count=8,motion=lambda r,i,x,y:(100,y)),resx=480,resy=270)
case('duration above frame bound retained',frames(count=10,duration=2),reports=0)
case('travel exactly half the canvas',frames(distance=540))
case('travel just below half the canvas',frames(distance=539.9),reports=0)
case('full travel without measured edge retained',frames(distance=540,positions=(850,900,980)),reports=0)
case('positive directional entry',frames(positions=(100,400,-150),distance=-700))
case('horizontal scroll',frames(distance=1250,positions=(400,800,2100),horizontal=True),reports=1)
case('horizontal positive entry',frames(distance=-1250,positions=(200,700,-400),horizontal=True))
case('small viewport scroll',frames(positions=(90,150,340),distance=200,motion=lambda r,i,x,y:(100,y)),resx=480,resy=270,reports=1)
case('no font evidence retained',font=False,reports=0)
case('unknown requested font retained',frames(extra=r'\fnNotAnAttachedFont'),reports=0)
case('large glyph uncertainty retained',frames(extra=r'\fs1200'),reports=0)
case('front-facing perspective bound',frames(extra=r'\frx5'))
case('steep perspective retained',frames(extra=r'\frx6'),reports=0)
case('changing distant rotation origins retained',frames(extra=r'\frz180\org(400,300)'),reports=0)
case('stable nearby rotation origin',frames(extra=r'\frz180',origins=True))
case('origin offset changes beyond bound',frames(extra=lambda r,i:fr'\frz1\org({400+100*i/39:g},{300+r*250-700*i/39:g})'))
case('rotation swing retained',frames(extra=lambda r,i:fr'\frz{3*i/39:g}'),reports=0)
case('rotation swing at tolerance',frames(extra=lambda r,i:fr'\frz{2*i/39:g}',origins=True))
case('scale swing retained',frames(extra=lambda r,i:fr'\fscx{100+31*i/39:g}'),reports=0)
case('scale ratio at tolerance',frames(extra=lambda r,i:fr'\fscx{100+30*i/39:g}'))
case('zero scale retained',frames(extra=r'\fscy0'),reports=0)
case('negative scale retained',frames(extra=r'\fscx-100'),reports=0)
case('live transform retained',frames(extra=r'\t(\fs50)'),reports=0)
case('live fade retained',frames(extra=r'\fad(100,100)'),reports=0)
case('live move retained',changed(BASE,text=lambda d:d['text'].replace(r'\pos(400,',r'\move(400,0,400,')),reports=0)
case('rectangular clip cannot prove edge',frames(extra=r'\clip(0,0,1920,1080)'),reports=0)
case('inverse clip cannot prove edge',frames(extra=r'\iclip(0,0,100,100)'),reports=0)
case('opposite direction line retained',frames(motion=lambda r,i,x,y:(x,y if r!=2 else 1200+700*i/39)),reports=0)
case('diagonal movement beyond bound retained',frames(motion=lambda r,i,x,y:(400+200*i/39,y)),reports=0)
case('small diagonal movement allowed',frames(motion=lambda r,i,x,y:(400+50*i/39,y)))
case('motion reversal retained',frames(motion=lambda r,i,x,y:(x,y+150 if 15<=i<25 else y)))
case('bounded entrance reversal uses held scroll',frames(motion=lambda r,i,x,y:(x,y+100 if i<3 else y)))
case('proof interval shorter than one second retained',frames(duration=1.2,count=10,motion=lambda r,i,x,y:(x,y+200 if i<2 else y)))
case('two speeds cannot become one block',frames(labels=('One','Two'),positions=(300,550))+frames(labels=('Three',),positions=(1200,),distance=1400),reports=0)
case('three coincident anchors are one spatial line',frames(positions=(300,301,302)),reports=0)
case('repeated literal in three spatial lines',frames(labels=('Repeated',)*3),reports=1)
case('inline paint remains admissible',changed(BASE,text=lambda d:d['text'].replace('One',r'O{\1c&H0000FF&}ne')),reports=1)
case('inline layout is not admissible',changed(BASE,text=lambda d:d['text'].replace('One',r'O{\fs80}ne')),reports=0)
case('paint copies join node and affect peak',BASE+changed(BASE,text=lambda d:d['text'].replace('}',r'\1c&HFF0000&}')),reports=1,peak=6,removed=240)
case('two lines with copies still lack third voter',frames(labels=('One','Two'),positions=(300,550))+frames(labels=('One','Two'),positions=(300,550),extra=r'\xbord0\1c&H123456&'),reports=0)
case('near-coincident paint tracks become members',BASE+frames(labels=('One',),positions=(304,),extra=r'\xbord0\1c&H123456&'),reports=1,peak=4,removed=160)
case('paint track does not cover common interval',BASE+frames(labels=('One',),positions=(304,),extra=r'\xbord0\1c&H123456&',start=1.2))
case('nearby distinct literal cannot join as paint copy',BASE+frames(labels=('Different',),positions=(304,),extra=r'\xbord0\1c&H123456&'))
case('same literal other style is independent',BASE+changed(frames(labels=('One',),positions=(304,)),style='Other'))
case('same literal other name is independent',BASE+changed(frames(labels=('One',),positions=(304,)),name='Other'))
case('same literal other layer is independent',BASE+changed(frames(labels=('One',),positions=(304,)),layer=1))
case('same literal different font is independent',BASE+frames(labels=('One',),positions=(304,),extra=r'\fnOtherFont'))
case('same literal different size is independent',BASE+frames(labels=('One',),positions=(304,),extra=r'\fs42'))
case('same literal different alignment is independent',BASE+frames(labels=('One',),positions=(304,),extra=r'\an7'))
case('paint track too far from voters',BASE+frames(labels=('One',),positions=(320,),extra=r'\xbord0\1c&H123456&'))
case('disconnected same-literal track retained',BASE+frames(labels=('One',),positions=(700,),distance=2,start=10),reports=1,removed=120)
case('unrelated static concurrency cannot trigger removal',BASE+[dict(text=r'{\pos(1500,800)}Unrelated '+str(i),start=1,end=3) for i in range(40)],reports=1,peak=3,removed=120)
case('two independent proved blocks',BASE+frames(labels=('Four','Five','Six'),start=10),reports=2,removed=240)
case('shared interval is shorter than one second',BASE+frames(labels=('Four','Five','Six'),start=2.2))
case('no transitive interval chaining',frames(labels=('One',),positions=(300,),start=1)+frames(labels=('Two',),positions=(550,),start=1.8)+frames(labels=('Three',),positions=(1200,),start=2.6),reports=0)
case('source index collisions deduplicate policy ownership',BASE+deepcopy(BASE),source_duplicates=True)
case('non-dialogue frames retained',changed(BASE,kind='Comment'),reports=0)
case('effect-bearing frames retained',changed(BASE,effect='Scroll up;0;100;20'),reports=0)
case('multiline frames retained',changed(BASE,text=lambda d:d['text']+r'\NExtra'),reports=0)
case('drawings retained',frames(extra=r'\p1'),reports=0)
case('gap interrupts motion chain',changed(BASE,lambda d:d['frame']>=20,start=lambda d:d['start']+2,end=lambda d:d['end']+2),reports=0)
case('empty input',[],reports=0)
case('crowded block at default policy boundary',frames(labels=tuple(f'Row {i}' for i in range(33)),positions=tuple(300+60*i for i in range(33)),origins=True),reports=1,peak=33,removed=1320)

def inputs(module,c,order):
    lines=[]
    for d in c['data']:
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer',0)},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},0,0,0,{d.get('effect','')},{d['text']}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));events=list(doc.events.values())
    for e,d in zip(events,c['data']):e.start_s,e.end_s=d['start'],d['end']
    if c.get('source_duplicates'):
        for i,e in enumerate(events):e.source_index=events[i%len(BASE)].source_index
    if order=='reverse':events.reverse()
    if order=='shuffle':random.Random(134).shuffle(events)
    return events
NAMES=('collect_scrolling_tracks','get_pos','text_height','caption_bounds','scroll_track_crosses_canvas','peak_concurrent_events')
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
metrics={module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
for i,c in enumerate(CASES):
    if i%10==0:print(i,'scrolling scenarios compared',flush=True)
    bases={module:inputs(module,c,'original') for module in (previous,current)}
    assert snapshot(bases[previous])==snapshot(bases[current]),(c['name'],'full input equivalence')
    before_by_module={module:[deepcopy(vars(e)) for e in events] for module,events in bases.items()}
    for order in ('original','reverse','shuffle'):
        for container in ('list','tuple'):
            for limit in (0,1,3,32,33):
                compared=[]
                for module in (previous,current):
                    events=list(bases[module])
                    if order=='reverse':events.reverse()
                    if order=='shuffle':random.Random(134).shuffle(events)
                    calls=[]
                    sources=events if container=='list' else tuple(events)
                    metric=metrics[module] if c.get('font',True) else None
                    with recording(module,calls) if order=='original' and container=='list' and limit==1 else contextlib.nullcontext():
                        args=(sources,c.get('resx',1920),c.get('resy',1080),metric)
                        result=tracer.runfunc(module.drop_overloaded_scrolling_blocks,*args,concurrency_limit=limit) if module is current and order=='original' and container=='list' and limit==1 else module.drop_overloaded_scrolling_blocks(*args,concurrency_limit=limit)
                    out,report=result;assert [vars(e) for e in bases[module]]==before_by_module[module],(c['name'],'input ownership')
                    owned={id(e) for e in events}
                    assert all(id(e) in owned for e in out),(c['name'],'retained identity')
                    if order=='original' and limit==1:
                        if 'reports' in c:assert len(report)==c['reports'],(c['name'],len(report),c['reports'])
                        if 'peak' in c:assert all(b['peak_concurrent']==c['peak'] for b in report),(c['name'],report)
                        if 'removed' in c:assert len(events)-len(out)==c['removed'],(c['name'],len(events)-len(out),c['removed'])
                    assert all(b['action']==('removed' if limit>0 and b['peak_concurrent']>limit else 'retained') for b in report)
                    out_ids={e.source_index for e in out}
                    assert [e.source_index for e in out]==[e.source_index for e in events if e.source_index in out_ids]
                    compared.append(([e.source_index for e in out],report,calls,[list(b) for b in report],[[list(t) for t in b['tracks']] for b in report]))
                assert compared[0]==compared[1],(c['name'],order,container,limit,'v148 parity')
                checks.append(dict(case=c['name'],order=order,container=container,concurrency_limit=limit))
    compared=[]
    for module in (previous,current):
        events=inputs(module,c,'original');before=snapshot(events)
        result=module.drop_overloaded_scrolling_blocks((e for e in events),c.get('resx',1920),c.get('resy',1080),metrics[module] if c.get('font',True) else None,concurrency_limit=1)
        assert snapshot(events)==before
        compared.append(snapshot(result))
    assert compared[0]==compared[1],(c['name'],'generator parity')
    checks.append(dict(case=c['name'],order='original',container='generator',concurrency_limit=1))
negative=[]
class Unreadable:
    def __iter__(self):raise AssertionError('negative policy consumed input')
for module in (previous,current):
    try:module.drop_overloaded_scrolling_blocks(Unreadable(),0,0,None,concurrency_limit=-1)
    except ValueError as e:negative.append(str(e))
assert negative==['Scrolling concurrency limit must be nonnegative.']*2
(ROOT/'validation/scrolling-direct-checks.json').write_text(json.dumps({'version':current.__version__,'reference':previous.__version__,'scenarios':len(CASES),'direct_comparisons':len(checks),'negative_limit_validation':True,'comparisons':checks},indent=2)+'\n')
focused=[]
fixtures=[('Scrolling-static-reduction-source.ass',BASE),('Scrolling-overloaded-source.ass',CASES[-1]['data']+[dict(text=r'{\pos(1500,800)}Unrelated',start=1,end=3)])]
for name,data in fixtures:
    events=inputs(current,dict(data=data),'original')
    (ROOT/'test-data'/name).write_text(HEADER+''.join(e.kind+': '+','.join(e.fields())+'\n' for e in events))
for fixture in ('Scrolling-static-reduction-source.ass','Scrolling-overloaded-source.ass'):
    for limit in (0,2,32,33):
        compared=[]
        for module in (previous,current):
            captured=[];original=module.drop_overloaded_scrolling_blocks
            def wrapped(events,resx,resy,metric,*,concurrency_limit=32):
                before=snapshot(events);result=original(events,resx,resy,metric,concurrency_limit=concurrency_limit)
                captured.append((before,snapshot(result),snapshot(events)));return result
            module.drop_overloaded_scrolling_blocks=wrapped
            try:
                with tempfile.TemporaryDirectory() as directory:
                    output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                    with contextlib.redirect_stdout(io.StringIO()):
                        stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(scroll_concurrency_limit=limit),font_metrics=metric, font_report=font_test_report(metric))
                    warnings=module.text_drop_warnings(stats)
                    compared.append((output.read_bytes(),snapshot(stats),warnings,captured,font_test_report(metric).rows_joined,set(font_test_report(metric).missing_families)))
            finally:module.drop_overloaded_scrolling_blocks=original
        assert compared[0]==compared[1],(fixture,limit,'focused conversion')
        stats=compared[0][1];expected=1320 if fixture=='Scrolling-overloaded-source.ass' and limit in (2,32) else 0
        assert stats['scrolling_events_dropped']==expected,(fixture,limit,stats)
        assert bool(compared[0][2])==bool(expected)
        focused.append(dict(fixture=fixture,concurrency_limit=limit,events_dropped=expected,statistics=stats,identical=True))
print(len(checks),'direct comparisons across',len(CASES),'scenarios;',len(focused),'focused conversions',flush=True)
tree=ast.parse((ROOT/'simplify_ass.py').read_text());audit=json.loads((ROOT/'validation/scrolling-block-consolidation-audit.json').read_text());coverage={}
for name in audit['helpers']:
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    statements={n.lineno for n in ast.walk(fn) if isinstance(n,ast.stmt) and n is not fn}
    if isinstance(fn.body[0],ast.Expr) and isinstance(fn.body[0].value,ast.Constant):statements.discard(fn.body[0].lineno)
    hit={line for (filename,line),count in tracer.results().counts.items() if Path(filename).resolve()==(ROOT/'simplify_ass.py').resolve() and count}
    coverage[name]={'statement_lines':sorted(statements),'executed_statement_lines':sorted(statements&hit),'uncovered_statement_lines':sorted(statements-hit)}
assert all(c['executed_statement_lines'] for c in coverage.values()),coverage
report={'version':current.__version__,'reference':previous.__version__,'scenarios':len(CASES),'direct_comparisons':len(checks),'negative_limit_validation':True,'focused_conversions':focused,'helper_statement_coverage':coverage,'comparisons':checks}
(ROOT/'validation/scrolling-block-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print('All six retained helpers exercised; reporting and ownership match v148',flush=True)
