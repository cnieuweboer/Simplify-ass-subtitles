import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare progressive reveal parsing, strip coverage, caption choice and gaps with v155."""
from pathlib import Path
from copy import deepcopy
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current, historical_fade_timing=True)
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('progressive_reference',ROOT/'test-data/simplify_ass-v155-reference.py')
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
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def event(prefix=1,start=1,end=1.1,word='abcd',x=500,y=100,tags='',**options):
    return dict(prefix=prefix,start=start,end=end,word=word,x=x,y=y,tags=tags,**options)
def sequence(strips=0,gap=0):
    records=[]
    for phase,n in enumerate((1,2,3,4)):
        start=1+phase*(.1+gap);end=start+.1 if n<4 else 2+3*gap
        if strips and n<4:
            for i in range(strips):records.append(event(n,start,end,clip=(0,85+15*i/strips,1000,85+15*(i+1)/strips),phase=phase,strip=i))
        else:records.append(event(n,start,end,phase=phase))
    return records
def change(records,predicate=lambda i,d:True,**changes):
    result=deepcopy(records)
    for i,d in enumerate(result):
        if predicate(i,d):d.update(changes)
    return result
BASE=sequence();TILES=sequence(6);CASES=[]
def case(name,records=None,expected=None,**options):CASES.append(dict(name=name,records=BASE if records is None else records,expected=expected,**options))
case('complete touching reveal',expected=3,intervals=((1,2),))
case('complete tiled reveal',TILES,18,intervals=((1,2),))
case('small authored gaps',sequence(gap=.02),0,intervals=((1,1.1),(1.12,1.22),(1.24,1.34),(1.36,2.06)),complete=True)
case('maximum chain gap',sequence(gap=.08),0,complete=True)
case('gap beyond chain tolerance',sequence(gap=.09),0)
case('empty input',[],0)
case('ordinary static caption',[event(4)],0)
case('missing complete hold',BASE[:3],0)
case('only one incomplete prefix',[BASE[0],BASE[-1]],0)
case('one repeated prefix',[BASE[0],{**BASE[1],'prefix':1},BASE[-1]],0)
case('complete copy before last prefix',[event(4,1,2),event(1,1.1,1.2),event(2,1.2,1.3)],0)
case('retracting prefixes',[event(3),event(2,1.1,1.2),event(1,1.2,1.3),BASE[-1]],0)
case('simultaneous increasing phases',change(BASE,start=1),3,intervals=((1,2),))
case('simultaneous shorter prefix starts a separate chain',BASE+[event(1,1.2,1.3)],2)
case('overlapping phases',change(BASE,lambda i,d:i<3,end=1.5),3,intervals=((1,2),))
case('duplicate complete holds',BASE+[deepcopy(BASE[-1])],4)
case('duplicate prefix copies',BASE+[deepcopy(BASE[1])],4)
case('two separated reveals',BASE+change(BASE,start=4,end=5),6)
case('two distant signs',BASE+change(BASE,x=700),6)
case('different caption styles',BASE+change(BASE,style='Other'),6)
case('different caption layers',BASE+change(BASE,layer=1),6)
case('different row margins',change(BASE,lambda i,d:i==1,margin_l=10),None)
case('unrelated event retained',BASE+[event(4,4,5,word='other',name='other')],3)
case('changed full literal',change(BASE,lambda i,d:i==1,word='wxyz'),None)
case('nearby positioned prefix',change(BASE,lambda i,d:i==1,x=501),3)
case('distant x prefix',change(BASE,lambda i,d:i==1,x=520),None)
case('distant y prefix',change(BASE,lambda i,d:i==1,y=101),None)
case('different foreground paints',[{**d,'tags':r'\1c&H123456&' if i==3 else r'\1c&HABCDEF&'} for i,d in enumerate(BASE)],3,colour='123456')
case('opaque hold outranks longer translucent hold',BASE+[event(4,1.3,4,tags=r'\1a&H60&')],4,alpha=0)
case('longer hold wins paint tie',BASE+[event(4,1.3,4,tags=r'\1c&H123456&')],4,colour='123456')
case('earliest source wins hold tie',BASE+[event(4,1.3,2,tags=r'\1c&H123456&')],4,colour='FFFFFF')
case('translucent foreground retained',change(BASE,tags=r'\1a&H40&'),3,alpha=64)
case('max readable foreground retained',change(BASE,tags=r'\1a&H7F&'),3,alpha=127)
case('foreground too transparent',change(BASE,tags=r'\1a&H80&'),0)
for name,tags in (
    ('rotation',r'\frz10'),('inverse clip',r'\iclip(0,0,1000,1000)'),('origin',r'\org(500,100)'),
    ('animated source',r'\t(0,100,\blur2)'),('movement',r'\move(500,100,500,100)'),
    ('fade source',r'\fad(0,100)'),('karaoke source',r'\k10'),
    ('zero font size',r'\fs0'),('zero x scale',r'\fscx0'),('negative y scale',r'\fscy-1')):
    case(name,change(BASE,tags=tags),3 if name=='zero font size' else 0)
case('drawing payload',change(BASE,drawing=True),0)
case('effect field',change(BASE,effect='Banner'),0)
case('comment sources',change(BASE,kind='Comment'),0)
case('nonpositive source lifetimes',change(BASE,end=1),0)
case('unpositioned sources',change(BASE,position=False),0)
for name,word in (('hard line break',r'ab\Ncd'),('soft line break',r'ab\ncd'),('hard space',r'ab\hcd')):
    case(name,change(BASE,word=word),0)
case('visible text after hidden suffix',change(BASE,lambda i,d:i<3,tail=r'{\alpha&H00&}z'),0)
case('only fill hidden',change(BASE,lambda i,d:i<3,hidden=r'\1a&HFF&'),0)
case('hidden suffix changes layout',change(BASE,lambda i,d:i<3,hidden=r'\alpha&HFF&\fs30'),0)
case('reset makes suffix visible',change(BASE,lambda i,d:i<3,hidden=r'\alpha&HFF&\r'),0)
case('visible spans disagree on paint',change(BASE,lambda i,d:i==1,body=r'{\pos(500,100)}a{\1c&H123456&}b{\alpha&HFF&}cd'),None)
case('uppercase alpha tags',change(BASE,lambda i,d:i<3,hidden=r'\ALPHA&HFF&'),None)
case('full strip band with two strips',sequence(2),0)
case('three strips too thick',sequence(3),0)
case('five thin strips',sequence(5),15)
case('seven thin strips',sequence(7),21)
case('missing middle strip',[d for d in TILES if not (d.get('phase')==0 and d.get('strip')==2)],0)
case('duplicate complete strips',TILES+[deepcopy(TILES[0])],19)
case('strip temporal hole',change(TILES,lambda i,d:d.get('phase')==0 and d.get('strip')==2,end=1.05),0)
case('strip starts late',change(TILES,lambda i,d:d.get('phase')==0 and d.get('strip')==2,start=1.05),0)
case('touching strip replacement',change(TILES,lambda i,d:d.get('phase')==0 and d.get('strip')==2,end=1.05)+[{**TILES[2],'start':1.05}],19)
case('overlapping strip duplicate',TILES+[{**TILES[2],'start':1.02,'end':1.08}],19)
case('strip horizontal mismatch',change(TILES,lambda i,d:i==2,clip=(1,90,1000,92.5)),0)
case('strip geometric gap',change(TILES,lambda i,d:i==2,clip=(0,90.01,1000,92.5)),0)
case('strip geometric overlap',change(TILES,lambda i,d:i==2,clip=(0,89.99,1000,92.5)),0)
case('clipped complete hold',change(BASE,lambda i,d:i==3,clip=(0,0,1000,1000)),0)
case('vector clip',change(BASE,lambda i,d:i==0,clip='(m 0 0 l 100 0 100 100 0 100)'),None)
case('different span clips',change(BASE,lambda i,d:i<3,clip=(0,85,1000,87.5),hidden=r'\alpha&HFF&\clip(0,87.5,1000,90)'),0)
case('whole band authored gaps',sequence(6,gap=.02),15,complete=True)
for label,tags in (
    ('fill',r'\1c&H123456&'),('opacity',r'\1a&H40&'),
    ('outline',r'\3c&H123456&'),('stroke width',r'\bord3')):
    case('partial bands must not share '+label,
         change(TILES,lambda i,d:'strip' in d and d['strip']<3,tags=tags),0)
case('interleaved paint must not fill geometric holes',
     change(TILES,lambda i,d:'strip' in d and d['strip']%2==0,tags=r'\1c&H123456&'),0)
case('independent complete paint bands',TILES+
     change([d for d in TILES if 'strip' in d],tags=r'\1c&H123456&'),36)
case('partial additional paint band',TILES+[{**TILES[0],'tags':r'\1c&H123456&'}],0)
case('complete prefix phases may use different paints',
     [{**d,'tags':rf'\1c&H{d["phase"]+1:06X}&'} if 'strip' in d else d for d in TILES],18)
# A band below 30% of the text height cannot establish complete coverage.
case('short vertical band',[{**d,'clip':(0,85+d['strip']*1.5,1000,85+(d['strip']+1)*1.5)} if 'strip' in d else d for d in TILES],0)

def body(d):
    if 'body' in d:return d['body']
    pose=f"\\pos({d['x']},{d['y']})" if d.get('position',True) else ''
    clip=d.get('clip');cliptag='' if clip is None else r'\clip'+(clip if isinstance(clip,str) else '('+','.join(map(str,clip))+')')
    tags=pose+cliptag+d['tags']+(r'\p1' if d.get('drawing') else '')
    prefix=d['prefix'];word=d['word'];tail=d.get('tail','')
    return '{'+tags+'}'+word[:prefix]+('{' +d.get('hidden',r'\alpha&HFF&')+'}'+word[prefix:] if prefix<len(word) else '')+tail

def inputs(module,records,order,map_mode):
    lines=[]
    for d in records:
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer',0)},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l',0)},0,0,{d.get('effect','')},{body(d)}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));events=list(doc.events.values())
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    if map_mode=='missing_all':visible={}
    if map_mode=='missing_one' and events:visible.pop(events[0].source_index,None)
    if map_mode=='wrong_one' and events:visible[events[0].source_index]='mismatch'
    visible[999999]='unrelated map entry'
    if order=='reversed':events.reverse()
    if order=='shuffled':random.Random(128).shuffle(events)
    return events,visible
SPY_NAMES=('inline_layout_key','get_pos','static_object_key','geometry_key','state_key',
    'unrotated_text_state','rectangle_clip','text_height','render_simplified_caption','render_tag','replace_event')
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
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_progressive_reveal_stages']);checks=[]
for i,c in enumerate(CASES):
    if i%20==0:print(i,'progressive-reveal scenarios compared',flush=True)
    for order in ('original','reversed','shuffled'):
        for map_mode in ('complete','missing_one','missing_all','wrong_one'):
            compared=[]
            for module in (previous,current):
                events,visible=inputs(module,c['records'],order,map_mode);before=snapshot(events);before_visible=snapshot(visible);calls=[]
                with recording(module,calls):
                    result=tracer.runfunc(module.collapse_progressive_text_reveals,events,visible) if module is current and order=='original' and map_mode=='complete' else module.collapse_progressive_text_reveals(events,visible)
                if module is current:
                    assert before_visible==snapshot(visible),(c['name'],'borrowed visibility mutation')
                    out,count=result.events,result.removed_count
                    applied={**visible,**result.visibility_updates}
                    semantic_result=(out,count)
                else:
                    out,count=result
                    applied=visible
                    semantic_result=result
                assert before==snapshot(events),(c['name'],'input mutation')
                assert count==len(events)-len(out),(c['name'],'count semantics')
                if map_mode=='complete':
                    if c['expected'] is not None:assert count==c['expected'],(c['name'],'expected count',count,c['expected'])
                    if 'intervals' in c:assert sorted((e.start_s,e.end_s) for e in out)==list(c['intervals']),(c['name'],'intervals')
                    if c.get('complete'):assert all(module.simplify_text(e.text,visible_only=True)[1]=='abcd' and not module.inline_layout_key(e) for e in out),(c['name'],'complete caption per actual interval')
                    if 'alpha' in c:assert all(e.state['1a']==c['alpha'] for e in out),(c['name'],'retained fill opacity')
                    if 'colour' in c:assert all(e.state['1c']==c['colour'] for e in out),(c['name'],'selected paint')
                assert visible[999999]=='unrelated map entry'
                compared.append((snapshot(semantic_result),snapshot(applied),calls,out is events,
                    [e.source_index for e in out if any(e is original for original in events)]))
            assert compared[0]==compared[1],(c['name'],order,map_mode,'v155 equivalence')
            checks.append(dict(case=c['name'],order=order,visible_map=map_mode))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.collapse_progressive_text_reveals
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            if module is current:
                assert before==snapshot((args,kwargs)),(fixture,'borrowed pass inputs')
                semantic_result=(result.events,result.removed_count)
                applied={**args[1],**result.visibility_updates}
                after=snapshot(((args[0],applied),kwargs))
            else:
                semantic_result=result;after=snapshot((args,kwargs))
            captured.append((before,snapshot(semantic_result),after));return result
        module.collapse_progressive_text_reveals=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.collapse_progressive_text_reveals=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/progressive-reveal-consolidation-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==12 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/progressive-reveal-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,complete_results_visible_maps_and_helper_calls_identical=True,return_and_retained_event_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'progressive-reveal comparisons across',len(CASES),'scenarios; 2 focused conversions; all 12 retained helpers exercised')
