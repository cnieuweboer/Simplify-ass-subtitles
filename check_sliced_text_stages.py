from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare sliced-text admission, coverage, ownership and timing with version 144."""
from pathlib import Path
from copy import deepcopy
import ast, contextlib, importlib.util, json, math, random, sys, tempfile, trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sliced_text_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
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
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def sequence(x=500,y=100,text='Hello',start=1,end=2,strips=3,pulse=False):
    records=[]
    for phase in ('in','hold','out'):
        if phase=='hold':
            records.append(dict(start=start,end=end,x=x,y=y,text=text,phase=phase,row=8,lyric=True));continue
        for i in range(strips):
            records.append(dict(start=.5 if phase=='in' else end,end=start if phase=='in' else end+.5,
                x=x,y=y,text=text,phase=phase,clip=(0,70+i*60/strips,1920,70+(i+1)*60/strips)))
    if pulse:records.append(dict(start=start,end=end,x=x,y=y,text=text,phase='pulse',layer='1'))
    return records
def change(records,predicate=lambda i,d:True,**changes):
    records=deepcopy(records)
    for i,d in enumerate(records):
        if predicate(i,d):d.update(changes)
    return records
tile=lambda i,d:d.get('phase') in ('in','out')
hold=lambda i,d:d.get('phase')=='hold'
pulse=lambda i,d:d.get('phase')=='pulse'
incoming=lambda i,d:d.get('phase')=='in'
CASES=[]
def case(name,records=None,**options):CASES.append(dict(name=name,records=sequence() if records is None else records,**options))
case('complete sequence',expected=6,caption_start=.5)
case('complete sequence with pulse',sequence(pulse=True),expected=7)
case('empty input',[],expected=0)
case('ordinary positioned text',[dict(start=1,end=2,x=500,y=100)],expected=0)
case('no incoming phase',[d for d in sequence() if d['phase']!='in'],expected=0)
case('no outgoing phase',[d for d in sequence() if d['phase']!='out'],expected=0)
case('no held caption',[d for d in sequence() if d['phase']!='hold'],expected=0)
case('two strips',sequence(strips=2),expected=0)
case('four strips',sequence(strips=4),expected=8)
case('six strips',sequence(strips=6),expected=12)
case('missing middle incoming strip',[d for i,d in enumerate(sequence()) if i!=1],expected=0)
case('duplicate incoming strip',sequence()+[deepcopy(sequence()[1])],expected=0)
case('different incoming layer groups',sequence()+change([d for d in sequence() if d['phase']=='in'],layer='1'),expected=0)
case('different outgoing layer groups',sequence()+change([d for d in sequence() if d['phase']=='out'],layer='1'),expected=0)
case('duplicate held caption',sequence()+[deepcopy(sequence()[3])],expected=7)
case('different paint held copies',sequence()+change([deepcopy(sequence()[3])],extra=r'\1c&H123456&'),expected=0)
case('independent sequences',sequence()+sequence(900,text='Other'),expected=12)
case('independent sequence and refused strips',sequence()+sequence(900,text='Other',strips=2),expected=6)
case('shared entrance has competing owners',sequence()+[dict(start=1,end=3,x=500,y=100,phase='hold')]+[d for d in sequence(end=3) if d['phase']=='out'],expected=0)
case('negative numeric layers',change(sequence(),layer='-2'),expected=6)
case('nonnumeric held layer',change(sequence(),hold,layer='bad'),expected=0)
case('nonnumeric tile layer',change(sequence(),tile,layer='bad'),expected=0)
case('synthetic source ordering',change(sequence(),synthetic_ids=True),expected=6)
case('authored effect metadata',change(sequence(),effect='authored'),expected=6)
case('same leading literal font',change(sequence(),extra=r'\fnOther'),expected=6)
case('authored inline fonts',sequence(text=r'H{\fnOther}i'),expected=6)
case('empty inline font resets',sequence(text=r'H{\fn}i'),expected=6)
case('authored inline paint',sequence(text=r'H{\1c&H123456&}i'),expected=0)
case('authored inline reset',sequence(text=r'H{\r}i'),expected=0)
for body in ('', '   ',r'Hi\Nthere',r'Hi\nthere',r'Hi\hthere'):
    case('unsupported literal '+repr(body),sequence(text=body),expected=0)
for field,value in [('style','Other'),('name','other'),('margin_l','5'),('margin_r','5'),('margin_v','5'),('text','Other'),('kind','Comment')]:
    case('mismatched incoming '+field,change(sequence(),incoming,**{field:value}),expected=0)
for extra in (r'\clip(0,0,1920,1080)',r'\iclip(0,0,1920,1080)',r'\org(500,100)',r'\frz1',r'\frx1',r'\fry1',r'\fax1',r'\fay1',r'\shad1',r'\xshad1',r'\yshad1',r'\p1',r'\fad(0,100)',r'\fade(0,0,255,0,0,500,1000)',r'\k20',r'\kf20',r'\ko20',r'\1a&H80&',r'\3a&H80&'):
    case('unsupported hold '+extra,change(sequence(),hold,extra=extra),expected=0)
for extra in (r'\fs30',r'\fscx90',r'\fscy90',r'\1c&H123456&',r'\3c&H123456&',r'\bord3',r'\xbord3',r'\ybord3'):
    case('mismatched tile '+extra,change(sequence(),tile,extra=extra),expected=0)
for defaults in ({'borderstyle':3},{'_canvas':None},{'fs':0},{'fscx':0},{'fscy':-1},{'fs':float('nan')},{'fscx':float('inf')}):
    case('invalid defaults '+repr(defaults),change(sequence(),defaults_changes=defaults),expected=0)
for rect in ((1,70,1920,90),(0,70,1919,90),(0,71,1920,90),(0,70,1920,89),(0,70,1920,91),(0,90,1920,90),(1920,70,0,90)):
    case('strip rectangle '+repr(rect),change(sequence(),lambda i,d:i==0,clip=rect))
case('top coverage too short',change(sequence(),lambda i,d:i==0,clip=(0,79,1920,90)),expected=0)
case('bottom coverage too short',change(sequence(),lambda i,d:i==6,clip=(0,110,1920,121)),expected=0)
case('vector clip',change(sequence(),incoming,clip=r'(m 0 0 l 1920 0 1920 20 0 20)'),expected=0)
case('positioned moving strips',change(sequence(),tile,also_pos=True),expected=0)
case('wrong incoming anchor',change(sequence(),incoming,move=r'\move(450,100,501,100)'),expected=0)
case('wrong outgoing anchor',change(sequence(),lambda i,d:d['phase']=='out',move=r'\move(501,100,550,100)'),expected=0)
for move in (r'\move(500,100,500,100)',r'\move(499,100,500,100)',r'\move(450,100,500,100,0,550)',r'\move(450,100,500,100,0,551)',r'\move(450,100,500,100,100,50)',r'\move(450,100,nan,100)',r'\move(450,100,500)',r'\move(450,100,500,100)\move(450,100,500,100)'):
    case('incoming move '+move,change(sequence(),incoming,move=move))
for transform in (r'\t(\alpha&H00&)',r'\t(0,500,\alpha&H00&)',r'\t(2,\alpha&H00&)',r'\t(0,500,2,\alpha&H00&)',r'\t(0,550,\alpha&H00&)',r'\t(0,551,\alpha&H00&)',r'\t(0,0,\alpha&H00&)',r'\t(0,500,0,\alpha&H00&)',r'\t(nan,500,\alpha&H00&)',r'\t(0,500,\fs40)',r'\t(0,500,\fscx100)',r'\t(0,500,\1a&H00&)',r'\t(0,500,\alpha&H80&)',r'\t(0,500,\alpha&H00&)\t(0,500,\blur0)'):
    case('incoming transform '+transform,change(sequence(),incoming,transform=transform))
for delta in (-.01,.01):
    case('untouched entrance boundary '+str(delta),change(sequence(),incoming,end=1+delta),expected=0)
    case('untouched exit boundary '+str(delta),change(sequence(),lambda i,d:d['phase']=='out',start=2+delta),expected=0)
for extra in (r'\fscx50\fscy50',r'\fscx200\fscy200',r'\fscx1\fscy1'):
    case('pulse amplitude '+extra,change(sequence(pulse=True),pulse,extra=extra),expected=7)
for changes in ({'layer':'-1'},{'extra':r'\bord1'},{'extra':r'\1a&H00&'},{'extra':r'\1a&HFF&'},{'x':501},{'start':1.01},{'end':2.01},{'transform':r'\t(0,1000,\fscx90\fscy90\alpha&HFF&)'},{'transform':r'\t(0,1000,\fscx100\fscy100\alpha&H80&)'}):
    case('unrelated pulse '+repr(changes),change(sequence(pulse=True),pulse,**changes),expected=6)

def authored(text='Hello',start=1,end=2,**values):
    return dict(start=start,end=end,kind='Comment',text=text,unpositioned=True,**values)
case('authored lyric timing',sequence()+[authored()],expected=6,caption_start=1)
case('authored whitespace normalization',sequence()+[authored(' H e l l o ')],expected=6,caption_start=1)
for changes in ({'text':'Hell'},{'text':'hello'},{'style':'Other'},{'name':'other'},{'start':1.051},{'end':2.051},{'start':1,'end':1},{'kind':'Dialogue'}):
    d=authored();d.update(changes)
    case('nonmatching authored cue '+repr(changes),sequence()+[d],expected=6,caption_start=.5)
for delta in (-.049,.049):
    case('authored timing tolerance '+str(delta),sequence()+[authored(start=1+delta,end=2+delta)],expected=6,caption_start=1)
case('ordered fragment lyric',sequence(400,text='A')+sequence(500,text='B',start=1.2,end=2.2)+[authored('A B',end=2.2)],expected=12,caption_start=1,caption_end=2.2)
case('reversed fragment lyric',sequence(400,text='A')+sequence(500,text='B')+[authored('BA')],expected=12,caption_start=.5)
case('repeated horizontal anchors',sequence(500,text='A')+sequence(500,text='B')+[authored('AB')],expected=12,caption_start=.5)
case('different vertical cue groups',sequence(400,text='A')+sequence(500,y=101,text='B')+[authored('AB')],expected=12,caption_start=.5)

def parse(module,c):
    lines=[]
    for d in c['records']:
        phase=d.get('phase','hold');x=d.get('x',500);y=d.get('y',100)
        pos='' if d.get('unpositioned') or phase in ('in','out') and not d.get('also_pos') else rf'\pos({x},{y})'
        if phase in ('in','out'):
            rect=d.get('clip',(0,70,1920,90))
            clip=rect if isinstance(rect,str) else '('+','.join(str(v) for v in rect)+')'
            move=d.get('move',rf'\move({x-50},{y},{x},{y})' if phase=='in' else rf'\move({x},{y},{x+50},{y})')
            transform=d.get('transform',r'\t(\alpha&H00&)' if phase=='in' else r'\t(\alpha&HFF&)')
            tags=move+r'\clip'+clip+(r'\alpha&HFF&' if phase=='in' else r'\alpha&H00&')+transform
        elif phase=='pulse':tags=r'\bord0\fscx150\fscy150\alpha&H80&'+d.get('transform',r'\t(\fscx100\fscy100\alpha&HFF&)')
        else:tags=''
        tags=d.get('tags',tags)+d.get('extra','')
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer','0')},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l','0')},{d.get('margin_r','0')},{d.get('margin_v','0')},{d.get('effect','')},{{{pos}{tags}}}{d.get('text','Hello')}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values())
    for e,d in zip(events,c['records']):
        e.start_s,e.end_s=d['start'],d['end']
        if d.get('synthetic_ids'):e.source_index=10000-e.source_index*19
        e.row=d.get('row',3);e.lyric=d.get('lyric',False)
        defaults=d.get('defaults_changes',{}).copy()
        if hasattr(e,'measurement') and '_canvas' in defaults:
            e.measurement=module.dataclass_replace(e.measurement,canvas=defaults.pop('_canvas'))
        e.defaults.update(defaults)
    return events,doc.styles

SPY_NAMES=('get_pos','literal_font_spans','effective_state','dataclass_replace','event_override_tokens',
           'text_layout_key','opaque_text_effect_state','parse_effect_transform','apply_tag',
           'rectangle_clip','parse_effect_move','text_height','render_simplified_caption',
           'replace_event','simplify_text','format_time')
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

if '--calibrate' in sys.argv:
    for c in CASES:
        events,_=parse(previous,c);out,n=previous.collapse_sliced_text_sequences(events)
        if 'expected' in c:assert n==c['expected'],(c['name'],n,c['expected'])
        if 'caption_start' in c:
            replacements=[e for e in out if not any(e is original for original in events)]
            assert replacements and all(e.start_s==c['caption_start'] for e in replacements),(c['name'],'timing',[(e.start_s,e.end_s) for e in replacements])
    print(len(CASES),'scenario expectations validated');sys.exit()

tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_sliced_text_stages'])
checks=[]
for index,c in enumerate(CASES):
    if index and index%25==0:print(index,'scenarios compared',flush=True)
    for order in ('original','reverse','shuffle'):
        compared=[]
        for module in (previous,current):
            events,styles=parse(module,c)
            if order=='reverse':events.reverse()
            elif order=='shuffle':random.Random(125).shuffle(events)
            before=snapshot((events,styles));calls=[]
            with recording(module,calls):
                result=tracer.runfunc(module.collapse_sliced_text_sequences,events) if module is current else module.collapse_sliced_text_sequences(events)
            out,n=result
            assert before==snapshot((events,styles)),(c['name'],'input ownership')
            assert n==len(events)-len(out),(c['name'],'removal count')
            assert (out is events)==(n==0),(c['name'],'return identity')
            if n:assert [e.source_index for e in out]==sorted(e.source_index for e in out)
            if 'expected' in c:assert n==c['expected'],(c['name'],order,n,c['expected'])
            replacements=[e for e in out if not any(e is original for original in events)]
            if 'caption_start' in c:assert replacements and all(e.start_s==c['caption_start'] for e in replacements)
            if 'caption_end' in c:assert all(e.end_s==c['caption_end'] for e in replacements)
            if c['name']=='complete sequence':assert all(e.row==8 and e.lyric and module.get_pos(e.text)==(500.,100.) for e in replacements)
            compared.append((snapshot(result),calls,out is events,[any(e is original for original in events) for e in out]))
        assert compared[0]==compared[1],(c['name'],order,'v148 parity')
        checks.append(dict(case=c['name'],order=order,removed=n))

focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.collapse_sliced_text_sequences
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            captured.append((before,snapshot(result),snapshot((args,kwargs))));return result
        module.collapse_sliced_text_sequences=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=tracer.runfunc(module.simplify_ass,ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric)) if module is current else module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:module.collapse_sliced_text_sequences=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

audit=json.loads((ROOT/'validation/sliced-text-consolidation-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==15 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/sliced-text-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),input_events_and_styles_unchanged=True,complete_results_and_helper_calls_identical=True,retained_and_return_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'sliced-text comparisons across',len(CASES),'scenarios; 2 focused conversions; all 15 retained helpers exercised')
