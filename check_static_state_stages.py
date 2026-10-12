from event_evidence_test_helpers import event_comparison_fields, pose_comparison_fields, selection_comparison_fields
#!/usr/bin/env python3
"""Compare static selection and explicit accumulated evidence with v150."""
from pathlib import Path
from copy import deepcopy
from collections.abc import Iterator
import ast,contextlib,importlib.util,inspect,json,math,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('static_state_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
def snapshot(value):
    if type(value).__name__=="StaticStateSelection":return snapshot(selection_comparison_fields(value))
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,Iterator):return ('iterator',type(value).__name__)
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()
                                     if k not in {'_upright_rotation','_sustained_geometry'}}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
def transform(start=0,end=1000,accel=1,**changes):return (start,end,accel,list(changes.items()))
CASES=[]
def case(name,transforms=None,boundaries=(0,1000),**options):
    CASES.append(dict(name=name,transforms=[] if transforms is None else transforms,boundaries=boundaries,**options))
case('unchanged state')
case('unchanged empty boundaries',boundaries=())
case('unchanged single boundary',boundaries=(100,))
case('empty paint iterable',paint=[])
case('paint with no sample intervals',boundaries=(),paint=[])
case('empty transform changes',[transform()])
case('sample empty boundaries',[transform()],boundaries=())
case('sample single boundary',[transform()],boundaries=(100,))
case('paint-only animation',[transform(**{'1c':'&HFF0000&','blur':'3'})])
case('no-op geometry animation',[transform(fs='40',pos='(100,50)')])
case('settled geometry over rotated lead',[transform(0,100,frz='20'),transform(100,1000,**{'1c':'&HFF0000&'})],boundaries=(0,100,1000))
case('settled upright hold outranks longer rotated hold',[transform(100,100,frz='20')],boundaries=(0,100,1000),pose={'frz':0.})
case('sustained own position',[transform(0,100,pos='(100,100)',frz='20'),transform(100,1000,frz='40')],boundaries=(0,100,1000),pose={'pos':(100.,100.),'frz':0.},protected=('pos',))
case('sustained own size',[transform(0,100,fs='60',fscx='120',fscy='130',frz='20'),transform(100,1000,frz='40')],boundaries=(0,100,1000),pose={'fs':60.,'fscx':120.,'fscy':130.,'frz':0.},protected=('fs','fscx','fscy'))
case('upright coherent moving fallback',[transform(pos='(100,100)',frz='40')],pose={'pos':(100.,50.),'frz':0.},unprotected=('pos',))
case('short sizing cannot prove hold',[transform(0,20,fs='60',frz='20'),transform(20,200,frz='40')],boundaries=(0,20,200),unprotected=('fs',))
case('paint subdivisions accumulate position hold',[transform(0,100,pos='(100,100)',frz='20'),transform(100,1000,frz='40'),transform(200,300,**{'1c':'&H0000FF&'}),transform(400,500,**{'1c':'&H00FF00&'}),transform(600,700,**{'1c':'&HFF0000&'})],boundaries=(0,100,200,300,400,500,600,700,1000),pose={'pos':(100.,100.)},protected=('pos',))
for end in (249.999,250,250.001):
    case('minimum sustained duration '+str(end),boundaries=(0,end),paint=[],base={'_upright_rotation':True},protected=('pos',) if end>=250 else (),unprotected=('pos',) if end<250 else ())
for split in (499.999,500,500.001):
    case('strict majority '+str(split),[transform(split,split,pos='(100,100)')],boundaries=(0,split,1000),base={'_upright_rotation':True},unprotected=('pos',) if split==500 else ())
case('clear stale protected geometry',[transform(frz='40')],base={'_upright_rotation':True,'_sustained_geometry':{'pos':(1,2)}},boundaries=(0,100),unprotected=('pos',))
for missing in ('pos','fn','fs','fscx','fscy','fsp','an','b','i','u','s'):
    case('missing hold field '+missing,[transform(frz='40')],remove=(missing,))
for axis in ('fr','frz','frx','fry'):
    for target in ('0','180','360','720','-360'):
        case('rotation '+axis+' '+target,[transform(**{axis:target})],base={axis if axis!='fr' else 'frz':20})
case('rotation outside later boundary',[transform(1000,2000,frz='40')])
case('rotation outside earlier boundary',[transform(-1000,-1,frz='40')])
case('rotation starts at final boundary',[transform(1000,1500,frz='40')])
case('overlapping rotations',[transform(0,700,frz='360'),transform(300,1000,frx='360')],boundaries=(0,300,700,1000))
case('unsorted transforms',[transform(500,1000,frz='40'),transform(0,500,frz='0')],boundaries=(0,500,1000))
case('style reset geometry',[transform(0,100,r='Other'),transform(100,1000,frz='40')],boundaries=(0,100,1000))
case('reset to default',[transform(0,100,r=''),transform(100,1000,frz='40')],boundaries=(0,100,1000))
case('unknown reset style',[transform(r='Missing')])
case('legacy alignment alias',[transform(a='6',frz='40')])
case('relative font size',[transform(fs='+2',frz='40')])
case('negative font size offset',[transform(fs='-2',frz='40')])
case('position changes but constant size',[transform(pos='(100,100)',frz='40')])
for base in ({'p':1},{'fs':0},{'clip':'(0,0,100,100)'},{'iclip':'(0,0,100,100)'},{'fax':1},
             {'fscx':0},{'fscx':-.01},{'fscx':-.011},{'fscy':0},{'1a':255,'3a':255,'4a':255},
             {'1a':255,'3a':255,'4a':0,'shad':0},{'1a':255,'3a':255,'4a':0,'shad':2},
             {'1a':255,'3a':0,'4a':255,'bord':2},{'1a':255,'3a':0,'4a':255,'bord':0}):
    case('visibility '+repr(base),[transform(frz='40')],base=base)
for alpha in (0,238,239,240,253,254,255):
    case('primary strength '+str(alpha),[transform(**{'1a':str(alpha)})])
for tag in ('c','1c','2c','3c','4c'):
    case('animated colour channel '+tag,[transform(0,100,**{tag:'&H123456&'}),transform(100,200,**{tag:'&HABCDEF&'}),transform(200,1000,**{tag:'&H123456&'})],boundaries=(0,100,200,1000))
case('colour votes repeated interrupted holds',[transform(0,0,**{'1c':'&HFF0000&'}),transform(300,300,**{'1c':'&H00FF00&'}),transform(400,400,**{'1c':'&HFF0000&'})],boundaries=(0,300,400,1000),colour='FF0000')
def paint(start=0,end=4,layer='0',**state):return dict(start=start,end=end,layer=layer,state=state)
case('top opaque paint wins',paint=[paint(**{'1c':'FF0000'}),paint(layer='1',**{'1c':'0000FF'})],colour='0000FF')
case('duplicate backing cannot multiply votes',paint=[paint(**{'1c':'FF0000'}) for _ in range(8)]+[paint(layer='1',**{'1c':'0000FF'})],colour='0000FF')
case('repeated paint dwell',paint=[paint(**{'1c':'FF0000'}),paint(0,1,'1',**{'1c':'0000FF'})],colour='FF0000')
case('translucent top slightly weaker',paint=[paint(**{'1c':'FF0000'}),paint(layer='1',**{'1c':'0000FF','1a':128})],colour='FF0000')
case('translucent top slightly stronger',paint=[paint(**{'1c':'FF0000'}),paint(layer='1',**{'1c':'0000FF','1a':127})],colour='0000FF')
case('representative paint retains tie',base={'1c':'0000FF'},paint=[paint(0,1,**{'1c':'FF0000'}),paint(1,2,**{'1c':'0000FF'})],colour='0000FF')
case('layer parse fallback',paint=[paint(layer='bad',**{'1c':'FF0000'}),paint(layer='-1',**{'1c':'0000FF'})],colour='FF0000')
case('lowercase paint normalized',paint=[paint(**{'1c':'abcdef'})],colour='ABCDEF')
case('nonpositive event ignored',paint=[paint(2,2,**{'1c':'FF0000'})],colour='FFFFFF')
case('negative event ignored',paint=[paint(2,1,**{'1c':'FF0000'})],colour='FFFFFF')
for state in ({'1c':'bad'},{'1a':254},{'1a':255},{'fscx':.01},{'fscy':0}):
    case('paint cannot vote '+repr(state),paint=[paint(**{'1c':'FF0000',**state})],colour='FFFFFF')
case('unpainted outline cannot vote',paint=[paint(**{'3c':'FF0000','bord':0})])
case('painted outline can vote',paint=[paint(**{'3c':'FF0000','bord':2})])
case('offset shadow can vote',paint=[paint(**{'4c':'FF0000','xshad':2})])
case('unused shadow cannot vote',paint=[paint(**{'4c':'FF0000','shad':0})])

HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment
Style: Default,Arial,40,5
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def inputs(module,c,paint_mode,collector):
    default={**module.DEFAULT_STATE,'fs':40,'pos':(100.,50.)}
    base={**default,**deepcopy(c.get('base',{}))}
    for name in c.get('remove',()):base.pop(name,None)
    styles={'other':{**default,'fs':55,'pos':(900.,100.),'1c':'112233'}}
    transforms=deepcopy(c['transforms']);boundaries=set(c['boundaries'])
    descriptors=c.get('paint');events=[]
    if descriptors is not None:
        lines=[f"Dialogue: {d['layer']},{module.format_time(d['start'])},{module.format_time(d['end'])},Default,,0,0,0,,Hello\n" for d in descriptors]
        doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
        events=list(doc.events.values())
        for e,d in zip(events,descriptors):e.state={**default,**deepcopy(d['state'])};e.start_s,e.end_s=d['start'],d['end']
    seen=[]
    def recorded():
        for e in events:seen.append(e.source_index);yield e
    if descriptors is None:paint_events=None
    elif paint_mode=='generator':paint_events=recorded()
    elif paint_mode=='reverse':paint_events=list(reversed(events))
    else:paint_events=events
    opaque=None if collector=='none' else [] if collector=='empty' else [(-10.,0.)]
    settled=None if collector=='none' else [] if collector=='empty' else [{'seed':True}]
    prior_pose=None
    if module is current:
        upright=base.pop('_upright_rotation',False)
        protected=base.pop('_sustained_geometry',None)
        prior_pose=module.StaticPoseEvidence(upright,
            tuple(protected.items()) if protected is not None else None)
    return base,transforms,boundaries,styles,default,paint_events,opaque,settled,events,seen,prior_pose

SPY_NAMES=('sample_transform_states','sample_transform_state','apply_tag','upright_text_state','unrotated_text_state','upright_transform_pose')
@contextlib.contextmanager
def recording(module,calls):
    originals={name:getattr(module,name) for name in SPY_NAMES}
    def wrap(name,original):
        def run(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            if isinstance(result,Iterator):
                calls.append((name,'enter',before))
                def tracked():
                    for item in result:calls.append((name,'yield',snapshot(item)));yield item
                    calls.append((name,'exhausted'))
                return tracked()
            calls.append((name,before,snapshot(result)));return result
        return run
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)

tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_static_state_stages']);checks=[]
for index,c in enumerate(CASES):
    if index and index%25==0:print(index,'scenarios compared',flush=True)
    modes=('list','reverse','generator') if 'paint' in c else ('none',)
    for mode in modes:
        for collector in ('none','empty','seeded'):
            for prefer,crossings in ((False,False),(False,True),(True,False),(True,True)):
                compared=[]
                for module in (previous,current):
                    base,transforms,boundaries,styles,default,paint_events,opaque,settled,events,seen,prior_pose=inputs(module,c,mode,collector)
                    before=snapshot((base,transforms,boundaries,styles,default,events));calls=[]
                    evidence_before=snapshot((opaque,settled))
                    with recording(module,calls):
                        args=(base,transforms,boundaries,styles,default,paint_events,opaque,settled)
                        kwargs=dict(prefer_upright=prefer,upright_crossings=crossings)
                        if module is current:kwargs['prior_pose']=prior_pose
                        selection=tracer.runfunc(module.select_static_state,*args,**kwargs) if module is current else module.select_static_state(*args,**kwargs)
                    result=selection.state
                    proof=selection_comparison_fields(selection)['pose']
                    assert evidence_before==snapshot((opaque,settled)),(c['name'],'seed evidence changed')
                    assert before==snapshot((base,transforms,boundaries,styles,default,events)),(c['name'],'input ownership')
                    assert (result is base)==(not transforms and paint_events is None),(c['name'],'return identity')
                    if mode=='generator':assert seen==[e.source_index for e in events],(c['name'],'one paint iteration')
                    if prefer and crossings:
                        for key,value in c.get('pose',{}).items():assert result[key]==value,(c['name'],key,result[key],value)
                        for key in c.get('protected',()):assert key in (proof['sustained_geometry'] or {}),(c['name'],'protected',key)
                        for key in c.get('unprotected',()):assert key not in (proof['sustained_geometry'] or {}),(c['name'],'unprotected',key)
                    if 'colour' in c:assert result['1c']==c['colour'],(c['name'],'paint',result['1c'])
                    compared.append((snapshot(selection),calls,result is base,seen))
                assert compared[0]==compared[1],(c['name'],mode,collector,prefer,crossings,'v150 parity')
                checks.append(dict(case=c['name'],paint_mode=mode,collector=collector,prefer_upright=prefer,upright_crossings=crossings))

focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.select_static_state
        def wrapped(*args,**kwargs):
            bound=inspect.signature(original).bind(*args,**kwargs);bound.apply_defaults()
            arguments=dict(bound.arguments)
            opaque=arguments.pop('prior_opaque_spans')
            settled=arguments.pop('prior_settled_states')
            arguments['prior_pose']=pose_comparison_fields(arguments.pop('prior_pose',None),arguments['base'])
            before=snapshot((arguments,opaque,settled));seed_before=snapshot((opaque,settled))
            result=original(*args,**kwargs)
            assert seed_before==snapshot((opaque,settled)),'focused conversion changed evidence seeds'
            captured.append((before,snapshot(result),snapshot(arguments),result.state is arguments['base']))
            return result
        module.select_static_state=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=tracer.runfunc(module.simplify_ass,ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric)) if module is current else module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:module.select_static_state=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

audit=json.loads((ROOT/'validation/static-state-consolidation-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==12 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/static-state-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,seed_evidence_unchanged=True,complete_formatting_evidence_and_helper_calls_identical=True,return_identity_identical=True,paint_iterables_consumed_once=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'static-state comparisons across',len(CASES),'scenarios; 2 focused conversions; all 12 retained helpers exercised')
