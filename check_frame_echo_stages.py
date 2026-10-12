from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Check frame-echo proofs, ownership and helper-call order against version 139."""
from pathlib import Path
from copy import deepcopy
import ast, contextlib, importlib.util, json, math, random, sys, tempfile, trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frame_echo_reference', ROOT/'test-data/simplify_ass-v152-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER = '''[Script Info]
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
    if isinstance(value, float) and not math.isfinite(value): return repr(value)
    if isinstance(value, dict): return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return tuple(snapshot(v) for v in value)
    if isinstance(value, set): return frozenset(snapshot(v) for v in value)
    if hasattr(value, '__dict__'): return snapshot(vars(value))
    return value

def echoes(flat=False, count=3, chain=1, duration=.05):
    layers = [5] if flat else [0,1]
    records = []
    for frame in range(chain+1):
        start,end = (1,2) if frame==0 else (2+(frame-1)*duration,2+frame*duration)
        points = [500] if frame==0 else [500+20*frame+2*(i-(count-1)/2) for i in range(count)]
        for x in points:
            for layer in layers:
                records.append(dict(start=start,end=end,x=x,layer=str(layer),
                    tags=(r'\1c&HFFFFFF&\bord1' if flat or layer else r'\1c&H000000&\bord3')+
                         (r'\1a&H80&' if frame else ''),phase=frame,row=3 if frame else 8,lyric=frame==0))
    return records

def change(records, predicate=lambda i,d:True, **changes):
    records=deepcopy(records)
    for i,d in enumerate(records):
        if predicate(i,d): d.update(changes)
    return records

CASES=[]
def case(name, records=None, **options):
    CASES.append(dict(name=name,records=echoes() if records is None else records,**options))
exit_piece=lambda i,d:d.get('phase',0)>0
case('stacked exit',expected=5,anchor_layer='0')
case('flattened exit',echoes(True),expected=2,anchor_layer='5')
case('stacked chain',echoes(chain=3),expected=15)
case('flattened chain',echoes(True,chain=3),expected=6)
for flat in (False,True):
    for count in (2,4,5):
        case(f'{flat} offsets {count}',echoes(flat,count=count),expected=0 if count==2 else count*(1 if flat else 2)-1)
    case(f'{flat} long moving exit',echoes(flat,duration=.4),expected=0,moving_expected=2 if flat else 5)
    case(f'{flat} no opaque hold',[d for d in echoes(flat) if d['phase']],expected=0)
    case(f'{flat} transparent hold',change(echoes(flat),lambda i,d:not d['phase'],tags=r'\1a&H80&'),expected=0)
    case(f'{flat} invisible exit',change(echoes(flat),exit_piece,tags=r'\1a&HFF&'),expected=0)
    case(f'{flat} fully opaque exit',change(echoes(flat),exit_piece,tags=r'\1c&HFFFFFF&\bord1'),expected=2 if flat else 0)
    case(f'{flat} short hold',change(echoes(flat),lambda i,d:not d['phase'],start=1.99),expected=0 if flat else 5)
    for gap in (-.0000011,-.0000009,.0000009,.0000011,.1):
        case(f'{flat} touching tolerance {gap}',change(echoes(flat),exit_piece,start=2+gap,end=2.05+gap))
    for field,value in [('kind','Comment'),('effect','authored'),('style','Other'),('name','label'),
                        ('margin_l','5'),('margin_r','5'),('margin_v','5'),('unpositioned',True),('text','Different')]:
        case(f'{flat} mismatched {field}',change(echoes(flat),exit_piece,**{field:value}),expected=0)
    for tags in (r'\fnOther',r'\clip(0,0,100,100)',r'\iclip(0,0,100,100)',r'\p1',r'\frz15',r'\fs30',r'\bord5',r'\shad2',r'\xbord5'):
        case(f'{flat} exit tags {tags}',change(echoes(flat),exit_piece,
             extra=tags))
    for scale in (89.99,90,110,110.01):
        case(f'{flat} scale tolerance {scale}',change(echoes(flat),exit_piece,extra=rf'\fscx{scale}\fscy{scale}'))
    case(f'{flat} authored inline geometry',change(echoes(flat),exit_piece,text=r'He{\fnOther}llo'),expected=0)
    case(f'{flat} same-family overlap',echoes(flat)+[dict(start=1.5,end=2.03,x=800,layer='5')])
    case(f'{flat} unrelated-family overlap',echoes(flat)+[dict(start=1.5,end=2.03,x=800,layer='5',name='other')],expected=2 if flat else 5)
    case(f'{flat} persistent repeated labels',echoes(flat)+change([d for d in echoes(flat) if d['phase']],start=2.05,end=4))
    case(f'{flat} reversed movement',change(echoes(flat),exit_piece,x=None))
    case(f'{flat} synthetic source identifiers',change(echoes(flat),synthetic_ids=True),expected=2 if flat else 5)
case('empty input',[],expected=0)
case('only opaque stack',[d for d in echoes() if not d['phase']],expected=0)
case('blank events',change(echoes(),text=''),expected=5)
case('missing stack layer',echoes()[:-1],expected=0)
case('duplicate stack layer',echoes()+[deepcopy(echoes()[-1])],expected=0)
case('nonnumeric layers',change(echoes(),layer='bad'),expected=0)
case('negative layers',change(echoes(),lambda i,d:d['layer']=='0',layer='-2'),expected=5)
case('one offset paint differs',change(echoes(),lambda i,d:i==2,extra=r'\1c&HAB1234&'),expected=0)
case('whole stack continuity changes',change(echoes(),exit_piece,extra=r'\4c&HAB1234&'),expected=0)
case('one offset width differs',change(echoes(),lambda i,d:i==2,extra=r'\bord8'),expected=0)
case('one offset layout differs',change(echoes(),lambda i,d:i==2,extra=r'\fscx90'),expected=0)
case('borderstyle other',change(echoes(),state_changes={'borderstyle':3}),expected=0)
case('hold paint profiles differ',change(echoes(),lambda i,d:i==1,layer='0'),expected=0)
for span in (.039,.04,.041,20,20.001):
    records=echoes()
    for d in records:
        if d['phase']: d['x']=540+(d['x']-520)*span/4
    case(f'offset span {span}',records)
case('uneven spacing',change(echoes(),lambda i,d:i in (4,5),x=520.5),expected=0)
case('offset direction differs from travel',change(echoes(),exit_piece,y=120),expected=0)
case('noncollinear offsets',change(echoes(),lambda i,d:i in (4,5),y=101),expected=0)
case('insufficient travel',change(echoes(),exit_piece,x=503),expected=0)
case('flat distance over five heights',change(echoes(True),exit_piece,x=750),expected=0)
for move in (r'\move(0,100,100,100)',r'\move(100,100,0,100)',r'\move(0,100,100,100,0,450)',
             r'\move(0,100,100,100,0,451)',r'\move(0,100,100,100,100,50)',r'\move(0,100,0,100)',
             r'\move(0,100,1,100)',r'\move(0,100,0,200)',r'\move(0,0,nan,0)',r'\move(0,0,100)',
             r'\move(0,0,100,0)\move(0,0,100,0)'):
    case('long source '+move,change(echoes(duration=.4),exit_piece,source_tags=move))
for changes in ({'omit_source':True},{'source_start':2.01},{'source_end':2.39},
                {'source_start':2.399,'source_end':2.399},{'source_text':r'He{\fnOther}llo'},
                {'source_tags':r'\move(100,100,0,100)'}):
    case('one inconsistent source '+repr(changes),change(echoes(duration=.4),lambda i,d:i==2,**changes))

def parse(module,c,source=False,moving=False):
    lines=[]
    for d in c['records']:
        x=d.get('x',500);x=1000-(500+20*d['phase']+2*(len(lines)//2-2)) if x is None else x
        y=d.get('y',100)
        pos='' if d.get('unpositioned') else rf'\pos({x},{y})'
        tags=d.get('tags','')+d.get('extra','')
        if source:
            tags=d.get('source_tags', tags+(rf'\move({x-30},{y},{x+30},{y})' if moving and d.get('phase') else ''))
            if '\\move' in tags.lower():pos=''
        body=d.get('source_text',d.get('text','Hello')) if source else d.get('text','Hello')
        start=d.get('source_start',d['start']) if source else d['start']
        end=d.get('source_end',d['end']) if source else d['end']
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer','0')},{module.format_time(start)},{module.format_time(end)},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l','0')},{d.get('margin_r','0')},{d.get('margin_v','0')},{d.get('effect','')},{{{pos}{tags}}}{body}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values())
    for e,d in zip(events,c['records']):
        e.start_s=d.get('source_start',d['start']) if source else d['start']
        e.end_s=d.get('source_end',d['end']) if source else d['end']
        if d.get('synthetic_ids'):e.source_index=10000-e.source_index*19
        e.lyric=d.get('lyric',False);e.row=d.get('row',3)
        e.state.update(d.get('state_changes',{}))
    return events,doc.styles

SPY_NAMES=('get_pos','inline_layout_key','text_layout_key','text_height','state_key',
           'event_override_tokens','parse_effect_move','render_simplified_caption','replace_event')
@contextlib.contextmanager
def recording(module,calls):
    originals={name:getattr(module,name) for name in SPY_NAMES}
    def wrap(name,original):
        def run(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            calls.append((name,before,snapshot(result)));return result
        return run
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)

def evidence(module,c,mode):
    if mode=='none':return None
    if mode=='empty':return {}
    return {e.source_index:e for e,d in zip(parse(module,c,True,mode=='moving')[0],c['records']) if not d.get('omit_source')}

if '--calibrate' in sys.argv:
    for c in CASES:
        for mode in ('static','moving'):
            events,_=parse(previous,c);out,n=previous.collapse_frame_text_echoes(events,.16,source_events=evidence(previous,c,mode))
            expected=c.get('moving_expected',c.get('expected')) if mode=='moving' else c.get('expected')
            if expected is not None:assert n==expected,(c['name'],mode,n,expected)
    print(len(CASES),'scenario expectations validated');sys.exit()

tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_frame_echo_stages'])
checks=[]
for index,c in enumerate(CASES):
    if index and index%25==0:print(index,'scenarios compared',flush=True)
    for order in ('original','reverse','shuffle'):
        for mode in ('none','empty','static','moving'):
            for limit in (.04,.16,1.):
                compared=[]
                for module in (previous,current):
                    events,styles=parse(module,c);sources=evidence(module,c,mode)
                    if order=='reverse':events.reverse()
                    elif order=='shuffle':random.Random(124).shuffle(events)
                    before=snapshot((events,styles,sources));calls=[]
                    with recording(module,calls):
                        result=tracer.runfunc(module.collapse_frame_text_echoes,events,limit,source_events=sources) if module is current else module.collapse_frame_text_echoes(events,limit,source_events=sources)
                    out,n=result
                    assert before==snapshot((events,styles,sources)),(c['name'],'input ownership')
                    assert out is not events and n==len(events)-len(out),(c['name'],'result ownership/count')
                    expected=c.get('moving_expected',c.get('expected')) if mode=='moving' else c.get('expected')
                    if limit==.16 and expected is not None:assert n==expected,(c['name'],order,mode,n,expected)
                    if limit==.16 and c.get('anchor_layer') and n:
                        replacements=[e for e in out if not any(e is original for original in events)]
                        assert all(module.get_pos(e.text)==(500.,100.) and e.row==8 and e.lyric and e.layer==c['anchor_layer'] for e in replacements)
                    compared.append((snapshot(result),calls,[any(e is original for original in events) for e in out]))
                assert compared[0]==compared[1],(c['name'],order,mode,limit,'v148 parity')
                checks.append(dict(case=c['name'],order=order,source=mode,limit=limit,removed=n))

focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.collapse_frame_text_echoes
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            captured.append((before,snapshot(result),snapshot((args,kwargs))));return result
        module.collapse_frame_text_echoes=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=tracer.runfunc(module.simplify_ass,ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric)) if module is current else module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:module.collapse_frame_text_echoes=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

audit=json.loads((ROOT/'validation/frame-echo-consolidation-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==15 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/frame-echo-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),input_events_styles_and_sources_unchanged=True,complete_results_and_helper_calls_identical=True,retained_and_return_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'frame-echo comparisons across',len(CASES),'scenarios; 2 focused conversions; all 15 retained helpers exercised')
