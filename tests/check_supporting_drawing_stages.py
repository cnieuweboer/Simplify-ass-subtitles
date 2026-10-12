import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare supporting drawing normalization, safeguards, coverage, paint and sequences with v149."""
from pathlib import Path
from copy import deepcopy
from collections.abc import Iterator
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('supporting_drawing_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,0,0
Style: Other,Arial,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
RECT='m 0 0 l 400 0 400 100 0 100'
PREFIX=r'\an7\pos(100,100)\p1\bord0\shad0'
def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,Iterator):return ('iterator',type(value).__name__)
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
def event(tags='',path=RECT,start=1,end=4,**options):return dict(tags=tags,path=path,start=start,end=end,**options)
def changed(data,predicate=lambda i,d:True,**changes):
    data=deepcopy(data)
    for i,d in enumerate(data):
        if predicate(i,d):d.update(changes)
    return data
def polygon(points):return 'm '+' '.join(str(v) for v in points[0])+' l '+' '.join(str(v) for p in points[1:] for v in p)
points=[(x,(x//10)%3-1) for x in range(0,401,10)]
points+=[(400,100)]+[(x,100+(x//10)%3-1) for x in range(390,-1,-10)]
JAGGED=polygon(points)
BASE=[event()]
STRIPS=[event(r'\clip(100,0,300,1000)\1c&H0000FF&'),event(r'\clip(300,0,500,1000)\1c&HFF0000&')]
FRAMES=[event(r'\1a&H80&',start=1,end=1.1),event(r'\1a&H40&',start=1.1,end=1.2),event(start=1.2,end=4)]
CASES=[]
def case(name,data=BASE,expected=None,**options):CASES.append(dict(name=name,data=data,expected=expected,**options))
case('static rectangle',expected=1,colour='FFFFFF',alpha=0)
case('generic backdrop colour',[event(r'\1c&H1A2B3C&')],1,colour='1A2B3C',alpha=0)
case('translucent fill stays translucent',[event(r'\1a&H80&')],1,alpha=128)
case('identical opaque copies',BASE+BASE,1,counts={'drawing_duplicates_removed':1})
case('opaque paint retains original source order',[event(r'\1c&H0000FF&'),event(r'\1c&HFF0000&')],1,colour='FF0000',alpha=0)
case('translucent copies compose opacity',[event(r'\1a&H80&'),event(r'\1a&H80&')],1,alpha=64,counts={'drawing_duplicates_removed':1})
case('fully transparent fill omitted',[event(r'\1a&HFF&\3a&HFF&\4a&HFF&')],0)
case('nearly transparent fill omitted',[event(r'\1a&HFE&\3a&HFE&\4a&HFE&')],0)
case('nearby shadow supplies fill',[event(r'\1a&HFE&\3a&HFE&\xshad.01\4c&H123456&')],1,colour='123456',alpha=0)
case('distant shadow does not supply fill',[event(r'\1a&HFE&\3a&HFE&\xshad10')],0)
case('complete horizontal gradient strips',STRIPS,1,colour='800080',clip=(100,100,500,200),counts={'drawing_strips_collapsed':1})
case('weighted horizontal strips',[event(r'\clip(100,0,200,1000)\1c&H0000FF&'),event(r'\clip(200,0,500,1000)\1c&HFF0000&')],1,colour='BF0040')
case('complete vertical strips',[event(r'\clip(0,100,1000,150)\1c&H0000FF&'),event(r'\clip(0,150,1000,200)\1c&HFF0000&')],1,colour='800080')
case('unused strip edges clamp to actual fill',[event(r'\clip(0,0,300,1000)'),event(r'\clip(300,50,1000,500)')],1,clip=(100,100,500,200))
case('coincident strip copies compose before area averaging',STRIPS+[event(r'\clip(100,0,300,1000)\1c&H00FF00&')],1,colour='808000',counts={'drawing_strips_collapsed':2})
case('transparent strips retain their area',[event(r'\clip(100,0,300,1000)'),event(r'\clip(300,0,500,1000)\1a&HFF&\3a&HFF&\4a&HFF&')],1,colour='FFFFFF',alpha=128)
case('all gradient strips invisible',changed(STRIPS,tags=r'\clip(100,100,500,200)\1a&HFF&\3a&HFF&\4a&HFF&'),0)
case('mixed clipped and unclipped copies',BASE+[event(r'\clip(100,100,500,200)')],0,counts={'unsupported_drawings_excluded':2})
case('vector clip is unsupported',[event(r'\clip(m 100 100 l 500 100 500 200)')],0)
case('inverse clip is unsupported',[event(r'\iclip(100,100,500,200)')],0)
case('degenerate clipped fill',[event(r'\clip(100,100,100,200)')],0)
case('clip wholly outside actual fill',[event(r'\clip(600,100,700,200)')],0)
case('single clip preserves unseen-path mask',[event(r'\clip(200,120,400,180)')],1,clip=(200,120,400,180))
case('strip gap rejects',[event(r'\clip(100,100,299,200)'),event(r'\clip(300,100,500,200)')],0,counts={'unsupported_drawings_excluded':2})
case('large strip overlap rejects',[event(r'\clip(100,100,350,200)'),event(r'\clip(300,100,500,200)')],0)
case('tiny strip overlap allowed',[event(r'\clip(100,100,300.01,200)'),event(r'\clip(300,100,500,200)')],1)
case('strip height mismatch rejects',[event(r'\clip(100,100,300,199)'),event(r'\clip(300,100,500,200)')],0)
case('four-tile artwork rejects',[event(r'\clip(100,100,300,150)'),event(r'\clip(300,100,500,150)'),event(r'\clip(100,150,300,200)'),event(r'\clip(300,150,500,200)')],0)
case('different-layer copies remain independent',BASE+[event(layer=1)],2)
case('different-name copies remain independent',BASE+[event(name='other')],2)
case('different-style copies remain independent',BASE+[event(style='Other')],2)
case('different-margin copies remain independent',BASE+[event(margin_l=10)],2)
case('different geometry remains independent',BASE+[event(path='m 0 0 l 300 0 300 100 0 100')],2)
case('jagged contour retains original evidence',[event(path=JAGGED)],1,contour=True,counts={'drawing_contours_simplified':1})
case('translucent jagged contour retains evidence',[event(r'\1a&H80&',path=JAGGED)],1,contour=True,alpha=128)
case('simple trapezoid stays simple',[event(path='m 0 0 l 400 0 390 100 10 100')],1,path='m 0 0 l 400 0 390 100 10 100')
case('simple triangle is admitted',[event(path='m 0 0 l 200 100 0 100')],1)
case('independent subpaths reject',[event(path=RECT+' m 20 20 l 40 20 40 40')],0)
case('exterior sliver detaches',[event(path=RECT+' m 200 0 l 201 -1 202 0')],1,counts={'drawing_edge_slivers_detached':1})
case('interior sliver remains unsupported',[event(path=RECT+' m 200 0 l 201 1 202 0')],0)
case('curved unsupported path',[event(path='m 0 0 b 30 0 60 20 100 100')],0)
case('empty drawing body',[event(path='')],0)
case('drawing marker without drawing content',[event(path='hello')],0)
case('text only ignored',[event(prefix=r'\pos(300,150)',path='Hello')],0)
case('comment ignored',[event(kind='Comment')],0)
case('nonpositive source duration',[event(end=1)],0)
case('empty input',[],0)
case('mixed text and drawing rejected',[event(path=RECT+r'{\p0}Hello')],0)
case('mid-path layout change rejected',[event(path='m 0 0 l 400 0'+r'{\fscx100}'+' 400 100 0 100')],0)
case('drawing alignment normalized',[event(prefix=r'\an5\pos(300,150)\p1\bord0\shad0')],1)
case('drawing alignment absent position rejected',[event(prefix=r'\an7\p1\bord0\shad0')],0)
case('same-colour rectangular stroke expands',[event(r'\bord2\1c&HABCDEF&\3c&HABCDEF&')],1,colour='ABCDEF')
case('different-colour rectangular stroke retained as fill',[event(r'\bord2\1c&HABCDEF&\3c&H000000&')],1,colour='ABCDEF')
case('whole-turn rotation retained',[event(r'\frz360')],1)
case('vertical reflection allowed',[event(r'\fry180')],1)
for tag in (r'\frx10',r'\fax.1',r'\fay.1',r'\pbo1',r'\fry20'):
    case('static geometry guard '+tag,[event(tag)],0)
case('four-field move not a held entrance',[event(r'\move(0,0,100,100)',prefix=r'\an7\p1\bord0\shad0')],0)
case('completed short move entrance',[event(r'\move(0,0,100,100,0,500)',prefix=r'\an7\p1\bord0\shad0')],1,counts={'drawing_move_entrances_frozen':1})
case('move longer than entrance bound',[event(r'\move(0,0,100,100,0,601)',prefix=r'\an7\p1\bord0\shad0')],0)
case('move reaches entrance bound',[event(r'\move(0,0,100,100,0,600)',prefix=r'\an7\p1\bord0\shad0')],1)
case('move parser rejects malformed',[event(r'\move(bad)',prefix=r'\an7\p1\bord0\shad0')],0)
case('multiple moves rejected',[event(r'\move(0,0,100,100,0,100)\move(0,0,100,100,0,100)',prefix=r'\an7\p1\bord0\shad0')],0)
case('held short scale entrance',[event(r'\fscx1\fscy1\t(0,200,\fscx100\fscy100)')],1)
case('held shrinking scale exit',[event(r'\t(2400,3000,\fscx1\fscy1)')],1,counts={'drawing_scale_exits_frozen':1})
case('held entrance and shrinking exit',[event(r'\fscx1\fscy1\t(0,200,\fscx100\fscy100)\t(2600,3000,\fscx1\fscy1)')],1,counts={'drawing_scale_exits_frozen':1})
case('long scale entrance rejects',[event(r'\fscx1\t(0,2000,\fscx100)')],0)
case('growing scale exit rejects',[event(r'\t(2400,3000,\fscx200\fscy200)')],0)
case('unsupported rotation transform rejects',[event(r'\t(\frz90)')],0)
case('scale wobble rejects',[event(r'\t(0,200,\fscx110)\t(400,600,\fscx100)')],0)
case('paint transform allowed',[event(r'\1c&H123456&\t(0,200,\1c&HABCDEF&)')],1)
case('paint fades across one held event',[event(r'\fad(100,100)')],1)
case('pose-stable fade frame sequence',FRAMES,1,counts={'drawing_fade_frames_removed':2})
case('pose-changing frames stay separate',changed(FRAMES,lambda i,d:i==1,prefix=r'\an7\pos(110,100)\p1\bord0\shad0'),3,counts={'drawing_fade_frames_removed':0})
case('colour-changing frames stay separate',changed(FRAMES,lambda i,d:i==1,tags=r'\1a&H40&\1c&H123456&'),3)
case('overlapping fade frames stay separate',changed(FRAMES,lambda i,d:i==1,start=1.05),3)
case('gapped fade frames stay separate',changed(FRAMES,lambda i,d:i==1,start=1.12),3)
case('jagged fade sequence preserves contour evidence',changed(FRAMES,path=JAGGED),1,contour=True)
case('frame contour changes must not share evidence',[event(r'\1a&H80&',path=JAGGED,start=1,end=1.1),event(r'\1a&H40&',path=polygon([(x,y+(.5 if 0<x<400 else 0)) for x,y in points]),start=1.1,end=1.2),event(path=JAGGED,start=1.2,end=4)],3)
case('source effects cleared',[event(effect='opaque source metadata')],1)

def inputs(module,c,order):
    lines=[]
    for d in c['data']:
        text='{'+d.get('prefix',PREFIX)+d['tags']+'}'+d['path']
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer',0)},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l',0)},0,0,{d.get('effect','')},{text}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));events=list(doc.events.values())
    for e,d in zip(events,c['data']):e.start_s,e.end_s=d['start'],d['end']
    if order=='reverse':events.reverse()
    if order=='shuffle':random.Random(133).shuffle(events)
    return events
NAMES=('simplify_visual_text','replace_event','flatten_rectangular_border','normalize_drawing_alignment','detach_drawing_edge_slivers','drawing_polygon','simplify_drawing_contour','tokenize_override','recover_held_drawing_scale','parse_effect_move','get_pos','inline_layout_key','geometry_key','state_key','rectangle_clip','coverage_geometry','merge_tiled_clips','compose_drawing_paint','drawing_paint','render_tag','reduce_vector_layers','freeze_vector_sequences')
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
    if i%20==0:print(i,'supporting drawing scenarios compared',flush=True)
    for order in ('original','reverse','shuffle'):
        for container in ('list','tuple','generator'):
            for scaled_borders in (True,False):
                compared=[]
                for module in (previous,current):
                    events=inputs(module,c,order);before=snapshot(events);calls=[]
                    sources=events if container=='list' else tuple(events) if container=='tuple' else (e for e in events)
                    with recording(module,calls):
                        result=tracer.runfunc(module.reduce_supporting_drawings,sources,scaled_borders=scaled_borders) if module is current and order=='original' and container=='list' else module.reduce_supporting_drawings(sources,scaled_borders=scaled_borders)
                    out,counts=result;assert before==snapshot(events),(c['name'],'input ownership')
                    if c['expected'] is not None:assert len(out)==c['expected'],(c['name'],len(out),c['expected'])
                    assert counts['drawing_candidates']==len(out)
                    for key,value in c.get('counts',{}).items():assert counts[key]==value,(c['name'],key,counts[key],value)
                    if c.get('colour'):assert all(e.state['1c']==c['colour'] for e in out)
                    if 'alpha' in c:assert all(e.state['1a']==c['alpha'] for e in out)
                    if c.get('clip'):assert all(module.rectangle_clip(e)==c['clip'] for e in out)
                    if c.get('contour'):assert all(e.evidence.original_contour_points is not None for e in out)
                    if c.get('path'):assert all(module.geometry_key(e.text)==module.geometry_key(c['path']) for e in out)
                    assert [e.source_index for e in out]==sorted(e.source_index for e in out)
                    compared.append((snapshot(result),list(counts),calls,[any(e is source for source in events) for e in out]))
                assert compared[0]==compared[1],(c['name'],order,container,scaled_borders,'v149 parity')
                checks.append(dict(case=c['name'],order=order,container=container,scaled_borders=scaled_borders))
caption=event(path='Hello',prefix=r'\pos(300,150)',layer=2)
for name,data in [('Drawing-strips-source.ass',STRIPS+[caption]),('Drawing-motion-source.ass',[event(r'\t(2400,3000,\fscx1\fscy1)')]+[caption]),('Drawing-fade-sequence-source.ass',FRAMES+[caption])]:
    events=inputs(current,dict(data=data),'original')
    (ROOT/'test-data'/name).write_text(HEADER+''.join(e.kind+': '+','.join(e.fields())+'\n' for e in events))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass','Drawing-strips-source.ass','Drawing-motion-source.ass','Drawing-fade-sequence-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.reduce_supporting_drawings
        def wrapped(sources,*,scaled_borders=True):
            before=snapshot(sources);result=original(sources,scaled_borders=scaled_borders)
            captured.append((before,snapshot(result),snapshot(sources)));return result
        module.reduce_supporting_drawings=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.reduce_supporting_drawings=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/supporting-drawing-consolidation-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==10 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/supporting-drawing-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),inputs_unchanged=True,complete_results_counts_helper_calls_and_event_identity_identical=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'supporting drawing comparisons across',len(CASES),'scenarios;',len(focused),'focused conversions; all 10 retained helpers exercised')
