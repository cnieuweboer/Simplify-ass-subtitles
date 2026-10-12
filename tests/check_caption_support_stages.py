import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare enclosing panel selection and sparse adjacency with immutable v149."""
from pathlib import Path
from copy import deepcopy
import ast,contextlib,importlib.util,io,json,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('caption_support_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Sign,Arial,40,5,0,0
Style: Other,Arial,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
RECT='m 0 0 l 400 0 400 100 0 100'
ARROW='m 0 0 l 25 5 0 10'
MASK='m 100 100 l 500 120 490 220 110 200'
PREFIX=r'\an7\pos(100,100)\p1\bord0\shad0'
CONTOUR=((100,100),(500,100),(500,200),(100,200))

def panel(path=RECT,tags=PREFIX,layer='0',**options):return dict(type='panel',text='{'+tags+'}'+path,layer=str(layer),**options)
def caption(literal='Hello',tags=r'\an5\pos(300,150)',layer='2',**options):return dict(type='caption',text='{'+tags+'}'+literal,layer=str(layer),**options)
BASE=[panel(),caption()]
ARROW_ROW=[panel(ARROW,r'\an7\pos(340,145)\p1\bord0\shad0',layer='3'),caption()]
SCREEN=panel('m 0 0 l 1920 0 1920 1080 0 1080',r'\an7\pos(0,0)\p1\bord0\shad0',layer='-2')
MASK_ROW=[panel(MASK,r'\an7\pos(0,0)\p1\bord0\shad0',layer='1'),caption('Sword Mastery III',r'\pos(300,150)\frz343.8\frx1.77\fry1.84\fax.18\q2\clip('+MASK+')')]

def changed(data,predicate=lambda i,d:True,**updates):
    data=deepcopy(data)
    for i,d in enumerate(data):
        if predicate(i,d):d.update({k:v(i,d) if callable(v) else v for k,v in updates.items()})
    return data

def extra(data,tags,predicate=lambda i,d:True):
    return changed(data,predicate,text=lambda i,d:d['text'].replace('}',tags+'}',1))

CASES=[]
def case(name,data=BASE,**options):CASES.append(dict(name=name,data=data,**options))
case('one enclosing panel',kept=1)
case('no font cannot prove ordinary coverage',font=False,kept=0)
case('opaque arbitrary-colour panel',extra(BASE,r'\1c&H123456&',lambda i,d:i==0),kept=1)
case('translucent simple panel retains paint',extra(BASE,r'\1a&H80&',lambda i,d:i==0),kept=1,alpha=128)
case('higher panel wins complete interval',[panel(),panel(layer='1'),caption()],kept=1)
case('higher middle panel preserves lower tails',[panel(),panel(layer='1',start=2,end=3),caption()],kept=2)
case('consecutive panels preserve both',[panel(end=2),panel(layer='1',start=2),caption()],kept=2)
case('gap without a panel remains a gap',[panel(end=2),panel(layer='1',start=3),caption()],kept=2)
case('higher partial panel cannot erase another caption',[panel(),panel('m 0 0 l 150 0 150 100 0 100',r'\an7\pos(350,100)\p1\bord0\shad0',layer='1'),caption('Left',r'\pos(200,150)'),caption('Right',r'\pos(425,150)')],kept=2)
case('equal layers choose later source index',[panel(),panel(),caption()],kept=1)
case('negative panel layer remains eligible',changed(BASE,lambda i,d:i==0,layer='-2'),kept=1)
case('panel above caption rejected',changed(BASE,lambda i,d:i==0,layer='3'),kept=0)
case('nonnumeric panel layer rejected',changed(BASE,lambda i,d:i==0,layer='invalid'),kept=0)
case('nonnumeric caption layer rejected',changed(BASE,lambda i,d:i==1,layer='invalid'),kept=0)
case('different panel style rejected',changed(BASE,lambda i,d:i==0,style='Other'),kept=0)
case('different panel name rejected',changed(BASE,lambda i,d:i==0,name='Other'),kept=0)
case('any positive overlap supports caption',changed(BASE,lambda i,d:i==0,start=3.99),kept=1)
case('delayed panel supports caption',changed(BASE,lambda i,d:i==0,start=1.5),kept=1)
case('short backdrop supports caption',changed(BASE,lambda i,d:i==0,end=1.1),kept=1)
case('touching endpoints provide no coverage',changed(BASE,lambda i,d:i==0,start=4,end=5),kept=0)
case('no temporal overlap',changed(BASE,lambda i,d:i==0,start=5,end=6),kept=0)
case('one character can have an enclosing panel',[panel(),caption('X')],kept=1)
case('blank captions ignored',[panel(),caption('  ')],kept=0)
case('lyric captions ignored',changed(BASE,lambda i,d:i==1,lyric=True),kept=0)
case('comment captions ignored',changed(BASE,lambda i,d:i==1,kind='Comment'),kept=0)
case('drawing captions ignored',[panel(),caption(RECT,r'\pos(300,150)\p1')],kept=0)
case('fullscreen retained without captions',[SCREEN],kept=1)
case('fullscreen retained without font',[SCREEN,caption()],font=False,kept=1)
case('fullscreen plus uppermost local panel',[SCREEN,panel(),panel(layer='1'),caption()],kept=2)
case('fullscreen retains source layer even above caption',changed([SCREEN,caption()],lambda i,d:i==0,layer='9'),kept=1)
case('nonnumeric fullscreen layer cannot prove background',changed([SCREEN,caption()],lambda i,d:i==0,layer='bad'),kept=0)
case('fullscreen associations retain eligible source order',[SCREEN,caption(),caption('World'),caption('Lyrics',lyric=True),caption('Other',style='Other')],kept=1)
case('fullscreen associates only overlapping text',[SCREEN,caption(start=5,end=6),caption(kind='Comment'),caption(RECT,r'\p1\pos(300,150)')],kept=1)
case('fullscreen contour does not become opaque',extra(changed([SCREEN,caption()],lambda i,d:i==0,contour=CONTOUR),r'\1a&H80&',lambda i,d:i==0),kept=1,alpha=128)
case('clipped fullscreen is local',extra([SCREEN,caption()],r'\clip(0,0,960,1080)',lambda i,d:i==0),kept=1)
case('shared mask proves perspective text',MASK_ROW,kept=1)
case('shared mask works without fonts',MASK_ROW,font=False,kept=1)
case('shared mask parked elsewhere rejected',changed(MASK_ROW,lambda i,d:i==0,text=lambda i,d:d['text'].replace(r'\pos(0,0)',r'\pos(1000,0)')),font=False,kept=0)
case('different outline cannot prove masked text',changed(MASK_ROW,lambda i,d:i==0,text=lambda i,d:d['text'].replace('490','480')),font=False,kept=0)
case('shared mask above caption rejected',changed(MASK_ROW,lambda i,d:i==0,layer='3'),font=False,kept=0)
case('scaled mask denotes same outline',changed(MASK_ROW,lambda i,d:i==1,text=lambda i,d:d['text'].replace(r'\clip('+MASK+')',r'\clip(2,m 200 200 l 1000 240 980 440 220 400)')),font=False,kept=1)
case('panel clip inside measured text rejected',extra(BASE,r'\clip(290,145,310,155)',lambda i,d:i==0),kept=0)
case('panel clip outside measured text accepted',extra(BASE,r'\clip(100,100,500,200)',lambda i,d:i==0),kept=1)
case('reconstructed panel becomes opaque',extra(changed(BASE,lambda i,d:i==0,contour=CONTOUR),r'\1a&H80&\2a&H40&',lambda i,d:i==0),kept=1,alpha=0)
case('original contour cutout prevents coverage',changed(BASE,lambda i,d:i==0,contour=((100,100),(500,100),(500,200),(320,200),(320,130),(280,130),(280,200),(100,200))),kept=0)
case('small triangle retained by adjacency',ARROW_ROW,kept=1)
case('adjacency unavailable without font',ARROW_ROW,font=False,kept=0)
case('adjacent triangle preserves opacity',extra(ARROW_ROW,r'\1a&H80&',lambda i,d:i==0),kept=1,alpha=128)
case('short decorative shape rejected',changed(ARROW_ROW,lambda i,d:i==0,end=1.119),kept=0)
case('decorative shape at duration boundary',changed(ARROW_ROW,lambda i,d:i==0,end=1.12),kept=1)
case('adjacent shape at overlap boundary',changed(ARROW_ROW,lambda i,d:i==0,start=3.6,end=4.1),kept=1)
case('adjacent shape below overlap boundary',changed(ARROW_ROW,lambda i,d:i==0,start=3.61,end=4.1),kept=0)
case('far decorative shape rejected',changed(ARROW_ROW,lambda i,d:i==0,text=lambda i,d:d['text'].replace(r'\pos(340,145)',r'\pos(1000,145)')),kept=0)
case('wide triangle at size boundary',[panel('m 0 0 l 200 5 0 10',r'\an7\pos(340,145)\p1'),caption()],kept=1)
case('wide triangle above size boundary',[panel('m 0 0 l 201 5 0 10',r'\an7\pos(340,145)\p1'),caption()],kept=0)
case('tall triangle above size boundary',[panel('m 0 0 l 25 5 0 201',r'\an7\pos(340,145)\p1'),caption()],kept=0)
case('small rectangle cannot prove adjacency',[panel('m 0 0 l 25 0 25 10 0 10',r'\an7\pos(340,145)\p1'),caption()],kept=0)
case('reconstructed contour cannot prove adjacency',changed(ARROW_ROW,lambda i,d:i==0,contour=((340,145),(365,150),(340,155))),kept=0)
case('one-character caption cannot prove adjacency',[ARROW_ROW[0],caption('X')],kept=0)
case('adjacency rejects another style',changed(ARROW_ROW,lambda i,d:i==1,style='Other'),kept=0)
case('adjacency rejects another name',changed(ARROW_ROW,lambda i,d:i==1,name='Other'),kept=0)
case('curve with clip supplies no straight primitive',[panel('m 0 0 b 0 0 25 5 0 10',r'\an7\pos(340,145)\p1\clip(340,140,365,160)'),caption()],kept=0)
case('no measurable drawing geometry',[panel('m 0 0 b 0 0 25 5 0 10',r'\an7\pos(340,145)\p1'),caption()],kept=0)
FAR=[panel(ARROW,fr'\an7\pos({1000+i*50},600)\p1') for i in range(8)]
case('eight shapes remain sparse',[ARROW_ROW[0]]+FAR[:7]+[caption()],kept=1)
case('nine shapes block adjacency',[ARROW_ROW[0]]+FAR+[caption()],kept=0)
case('fullscreen fills do not count against sparsity',[SCREEN]*9+ARROW_ROW,kept=10)
case('adjacency takes first matching caption',[ARROW_ROW[0],caption(),caption('World')],kept=1)
case('duplicate candidate ID cannot reassociate arrow',[ARROW_ROW[0],dict(ARROW_ROW[0],same_id_as=0),caption(),caption('World')],kept=2)
case('duplicate enclosing panel ID preserves output identity',[panel(),panel(layer='1',same_id_as=0),caption()],kept=2)
case('empty candidates',[caption()],kept=0)
case('empty captions',[panel()],kept=0)

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,dict):return tuple((k,snapshot(v)) for k,v in value.items())
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if isinstance(value,(current.FontMetrics,previous.FontSpacing)):return 'font-metric'
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def inputs(module,c,order):
    lines=[]
    for d in c['data']:
        at=lambda value:f'0:00:{value:07.3f}'
        fields=[str(d.get('layer','0')),at(d.get('start',1)),at(d.get('end',4)),d.get('style','Sign'),d.get('name',''),'0','0','0','',d['text']]
        lines.append(d.get('kind','Dialogue')+': '+','.join(fields)+'\n')
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    all_events=list(doc.events.values());candidates=[];captions=[]
    for e,d in zip(all_events,c['data']):
        e.lyric=d.get('lyric',False)
        if 'contour' in d:
            e.evidence=module.EventEvidence(d['contour'])
        if 'same_id_as' in d:e.source_index=all_events[d['same_id_as']].source_index
        (candidates if d['type']=='panel' else captions).append(e)
    if order=='reverse-candidates':candidates.reverse()
    if order=='reverse-captions':captions.reverse()
    if order=='shuffle':random.Random(136).shuffle(candidates);random.Random(137).shuffle(captions)
    return candidates,captions

NAMES=('caption_bounds','coverage_geometry','rectangle_clip','is_fullscreen_background','caption_clip_outline','drawing_matches_caption_outline','polygon_covers_box','drawing_polygon','text_height','replace_event')
@contextlib.contextmanager
def recording(module,calls):
    originals={name:getattr(module,name) for name in NAMES}
    def wrapper(name,original):
        def run(*args,**kwargs):
            recorded_kwargs={k:v for k,v in kwargs.items() if k!='evidence'} if name=='replace_event' else kwargs
            calls.append((name,snapshot((args,recorded_kwargs))));return original(*args,**kwargs)
        return run
    for name,original in originals.items():setattr(module,name,wrapper(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)

metrics={module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix]);checks=[]
for c in CASES:
    for order in ('original','reverse-candidates','reverse-captions','shuffle'):
        for use_font in (False,True):
            compared=[]
            for module in (previous,current):
                candidates,captions=inputs(module,c,order);before=snapshot((candidates,captions));calls=[]
                metric=metrics[module] if use_font and c.get('font',True) else None
                with recording(module,calls):
                    result=tracer.runfunc(module.select_caption_supports,candidates,captions,metric) if module is current and order=='original' else module.select_caption_supports(candidates,captions,metric)
                assert snapshot((candidates,captions))==before,(c['name'],'input mutation')
                identity=[next((i for i,original in enumerate(candidates) if e is original),None) for e in result[0]]
                associated_identity=[(key,[next(i for i,original in enumerate(captions) if e is original) for e in values]) for key,values in result[1].items()]
                compared.append((snapshot(result),identity,associated_identity,calls))
                if module is previous and order=='original' and use_font:
                    assert len(result[0])==c['kept'],(c['name'],len(result[0]),c['kept'])
                    if 'alpha' in c:assert result[0][0].state['1a']==c['alpha'],(c['name'],result[0][0].state)
            assert compared[0]==compared[1],(c['name'],order,use_font)
            checks.append(dict(case=c['name'],order=order,font=use_font and c.get('font',True),identical=True))

# Preserve direct results even if a later whole-conversion check fails.
(ROOT/'validation/caption-support-direct-checks.json').write_text(json.dumps(dict(scenarios=len(CASES),direct_comparisons=len(checks),comparisons=checks),indent=2)+'\n')
points=[(x,(x//10)%3-1) for x in range(0,401,10)]+[(400,100)]+[(x,100+(x//10)%3-1) for x in range(390,-1,-10)]
jagged='m '+' '.join(str(v) for v in points[0])+' l '+' '.join(str(v) for p in points[1:] for v in p)
fixtures=[('Caption-support-intervals-source.ass',[panel(),panel(layer='1',start=2,end=3),caption()]),
          ('Caption-support-fullscreen-source.ass',[SCREEN,panel(),panel(layer='1'),caption()]),
          ('Caption-support-adjacent-source.ass',ARROW_ROW),
          ('Caption-support-mask-source.ass',MASK_ROW),
          ('Caption-support-paper-source.ass',[panel(jagged,PREFIX+r'\1a&H80&\2a&H40&'),caption()])]
focused=[]
for fixture,data in fixtures:
    panels,texts=inputs(current,dict(data=data),'original')
    events=sorted(panels+texts,key=lambda e:e.source_index)
    source=ROOT/'test-data'/fixture;source.write_text(HEADER+''.join(e.kind+': '+','.join(e.fields())+'\n' for e in events))
    compared=[]
    for module in (previous,current):
        captured=[];original=module.select_caption_supports
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            captured.append((before,snapshot(result),snapshot((args,kwargs))));return result
        module.select_caption_supports=wrapped
        try:
            with tempfile.TemporaryDirectory() as temp:
                output=Path(temp)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(io.StringIO()) as log:
                    stats=module.simplify_ass(source,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((output.read_bytes(),stats,log.getvalue(),captured,font_test_report(metric).rows_joined,set(font_test_report(metric).missing_families)))
        finally:module.select_caption_supports=original
    assert compared[0]==compared[1],(fixture,'focused complete conversion')
    assert captured,fixture
    focused.append(dict(fixture=fixture,statistics=compared[0][1],target_calls=len(compared[0][3]),identical=True))

tree=ast.parse((ROOT/'simplify_ass.py').read_text());coverage={}
hit={line for (filename,line),count in tracer.results().counts.items() if count and Path(filename).resolve()==(ROOT/'simplify_ass.py').resolve()}
for name in ('_select_enclosing_caption_panels','_match_adjacent_caption_shapes'):
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    statements={n.lineno for n in ast.walk(fn) if isinstance(n,ast.stmt) and n is not fn};statements.discard(fn.body[0].lineno)
    coverage[name]=dict(statement_lines=sorted(statements),executed_statement_lines=sorted(statements&hit),uncovered_statement_lines=sorted(statements-hit))
    assert statements<=hit,(name,statements-hit)
report=dict(version=current.__version__,reference=previous.__version__,scenarios=len(CASES),direct_comparisons=len(checks),focused_conversions=focused,helper_statement_coverage=coverage,comparisons=checks)
(ROOT/'validation/caption-support-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'direct comparisons across',len(CASES),'scenarios;',len(focused),'focused complete conversions')
print('Both helpers covered; support selection, association order, opacity and helper calls match v149')
