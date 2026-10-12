"""Cross-lane handoffs: authored changes and common source-safe overlap windows."""
import test_paths
import ast,contextlib,hashlib,importlib.util,io,json,sys,tempfile
from pathlib import Path
from copy import deepcopy
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def check(label,value):
    assert value,label
    checks.append(label)
HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def fixture(reference=(1,4.13,4.13,7.5), core=None, x=320,y=130,third=None):
    specs=[('Left text',1,4.4,320,80),('Right text',4,7.5,320,80),
           ('Other left',reference[0],reference[1],x,y),('Other right',reference[2],reference[3],x,y)]
    if third:specs.extend(third)
    text=HEADER+''.join('Dialogue: 0,'+s.format_time(a)+','+s.format_time(b)+',Default,,0,0,0,,{\\pos('+str(px)+','+str(py)+')}'+word+'\n' for word,a,b,px,py in specs)
    doc=s._resolve_document_state(s.parse_subtitle_document(text));events=list(doc.events.values());rows=[]
    for i,e in enumerate(events):
        protected=[(1.3,3.8),(4.6,7.2)][i] if i<2 else core[i-2] if core and i<4 else None
        rows.append(s.TextRow(e,[(e,s.OVERRIDE_RE.sub('',e.text),s.get_pos(e.text))],phase_core=protected))
    return events,rows
es,rs=fixture();before=deepcopy((es,rs))
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('clean reference supplies exact authored handoff',n==1 and out[0].end_s==out[1].start_s==4.13)
check('reference stays unchanged',out[2] is es[2] and out[3] is es[3])
check('inputs remain borrowed',[(e.fields(),e.state) for e in es]==[(e.fields(),e.state) for e in before[0]] and [vars(r) for r in rs]==[vars(r) for r in before[1]])
check('only timing changes',all(a.text==b.text and a.layer==b.layer and a.fields()[3:]==b.fields()[3:] for a,b in zip(es,out)))
check('second filter pass is idempotent',s.trim_faded_cue_overlaps(out,rs,{})[1]==0)
es,rs=fixture((1,4.3,3.9,7.5),((1.2,4),(4.2,7.2)))
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('both overlapping lanes share safe handoff',n==2 and out[0].end_s==out[1].start_s==out[2].end_s==out[3].start_s==4.1)
check('all readable cores preserved',all(e.start_s<=r.phase_core[0]<r.phase_core[1]<=e.end_s for e,r in zip(out,rs)))
check('overlap groups are independent of event order', [e.fields() for e in reversed(s.trim_faded_cue_overlaps(list(reversed(es)),list(reversed(rs)),{})[0])]==[e.fields() for e in out])
for label,kwargs in [
 ('separate horizontal lane',dict(x=600)),
 ('same vertical lane',dict(y=80)),('authored boundary outside overlap',dict(reference=(1,4.5,4.5,7.5))),
 ('boundary cuts outgoing core',dict(reference=(1,3.7,3.7,7.5))),
 ('conflicting reference boundaries',dict(third=[('Third left',1,4.3,320,180),('Third right',4.3,7.5,320,180)])),
 ('same-lane third caption',dict(third=[('Third overlapping',3.9,4.5,320,130)])),
]:
 es,rs=fixture(**kwargs);out,n=s.trim_faded_cue_overlaps(es,rs,{})
 check('independent fallback: '+label,(out[0].end_s==4.4 and out[1].start_s==4) if label=='same vertical lane' else out[0].end_s==out[1].start_s==4.2)
es,rs=fixture((1,4.5,3.9,7.5),((1.2,4.45),(4.46,7.2)))
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('disjoint safe windows retain independent boundaries',n==2 and out[0].end_s==4.2 and out[2].end_s==4.46)
es,rs=fixture((1,4.3,3.9,7.5),((1.2,4.4),(4.1,7.2)))
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('overlapping protected cores never authorize shared trimming',n==1 and out[0].end_s==4.2 and out[2] is es[2])
es,rs=fixture(y=300)
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('distant top and bottom rows can synchronize',n==1 and out[0].end_s==4.13)
for i in (2,3):
    es[i]=s.replace_event(es[i],text=es[i].text.replace('}',r'\an2}',1))
rs=rs[:2]
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('different vertical alignment bands can synchronize',n==1 and out[0].end_s==4.13)

# A compatible third lane shares the intersection of all three windows.
es,rs=fixture((1,4.3,3.9,7.5),((1.2,4),(4.2,7.2)),third=[
    ('Third outgoing',1,4.35,320,180),('Third incoming',3.95,7.5,320,180)])
from dataclasses import replace
rs[4]=replace(rs[4],phase_core=(1.25,4.05));rs[5]=replace(rs[5],phase_core=(4.15,7.2))
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('three overlapping rows share one safe boundary',n==3 and all(out[i].end_s==out[i+1].start_s==4.1 for i in (0,2,4)))

# One broad reference spans two independent horizontal caption groups.
es,rs=fixture(x=320,third=[('Separate outgoing',1,4.4,450,180),('Separate incoming',4,7.5,450,180)])
for i in (0,1):
    es[i]=s.replace_event(es[i],text=es[i].text.replace('320,80','150,80'))
    rs[i]=s.TextRow(es[i],[(es[i],s.OVERRIDE_RE.sub('',es[i].text),(150,80))],phase_core=rs[i].phase_core)
for i in (2,3):
    e=es[i];rs[i]=s.TextRow(e,[(e,'Other',(100,130)),(e,'words',(500,130))])
rs[4]=replace(rs[4],phase_core=(1.3,3.8));rs[5]=replace(rs[5],phase_core=(4.6,7.2))
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('reference shared by competing groups is ignored',n==2 and out[0].end_s==out[4].end_s==4.2)

for label,tag in [('drawing',r'\p1'),('live fade',r'\fad(10,10)'),
                  ('clip',r'\clip(0,0,640,360)'),('transform',r'\t(0,10,\fs50)')]:
    es,rs=fixture()
    for i in (2,3):es[i]=s.replace_event(es[i],text=es[i].text.replace('}',tag+'}',1))
    out,n=s.trim_faded_cue_overlaps(es,rs[:2],{})
    check('unsupported reference ignored: '+label,out[0].end_s==4.2)
for invalid_size in (0,float('nan')):
    es,rs=fixture()
    for i in (2,3):es[i]=replace(es[i],state={**es[i].state,'fs':invalid_size})
    out,n=s.trim_faded_cue_overlaps(es,rs[:2],{})
    check('invalid font size reference ignored: '+str(invalid_size),out[0].end_s==4.2)
es,rs=fixture((3.7,4.13,4.13,7.5))
out,n=s.trim_faded_cue_overlaps(es,rs,{})
check('reference must cover complete outgoing protected core',out[0].end_s==4.2)

spec=importlib.util.spec_from_file_location('handoff_reference',ROOT/'tests/references/simplify_ass_v180.py')
reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)
source=ROOT/'test-data/Attack-on-Titan-S02E01-opening-source.ass'
digest=hashlib.sha256(source.read_bytes()).hexdigest()
metrics=s.FontMetrics([ROOT/'fonts'])
check('exact source font available',metrics.matching_face('Clearface SSi',True,False) is not None)
with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
    baseline_path=Path(folder)/'v180.ass'
    reference.simplify_ass(source,baseline_path,reference.SimplifyConfig(),font_metrics=reference.FontMetrics([ROOT/'fonts']))
    output=Path(folder)/'synchronized.ass'
    stats=s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metrics)
    events=s.load_subtitle_events(output)[1]
    lanes=[sorted([e for e in events if e.style==style],key=lambda e:e.start_s) for style in ('OP-E','OP-R')]
    check('both actual lyric lanes have twenty clean handoffs',all(len(lane)==21 and all(a.end_s==b.start_s for a,b in zip(lane,lane[1:])) for lane in lanes))
    check('all twenty AoT handoffs synchronized exactly',all(a.end_s==b.end_s for a,b in zip(lanes[0][:-1],lanes[1][:-1])))
    baseline=s.load_subtitle_events(baseline_path)[1]
    baseline=[e for e in baseline if e.style in ('OP-E','OP-R')]
    for style,lane in zip(('OP-E','OP-R'),lanes):
        old=sorted([e for e in baseline if e.style==style],key=lambda e:e.start_s)
        check(style+' text paint placement and event count unchanged',len(old)==len(lane) and all(a.fields()[3:]==b.fields()[3:] and a.layer==b.layer for a,b in zip(old,lane)))
    again=Path(folder)/'again.ass'
    s.simplify_ass(output,again,s.SimplifyConfig(),font_metrics=metrics)
    check('synchronized AoT output byte-idempotent',again.read_bytes()==output.read_bytes())
check('source bytes preserved',hashlib.sha256(source.read_bytes()).hexdigest()==digest)
from executable_ast_audit import executable_ast
def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
a=definitions(ROOT/'tests/references/simplify_ass_v180.py');b=definitions(ROOT/'simplify_ass.py')
check('only synchronization helper added',set(b)-set(a)=={'synchronize_faded_cue_handoffs'} and not set(a)-set(b))
check('runtime integration confined to overlap filter',{name for name in a if ast.dump(a[name])!=ast.dump(b[name])}=={'trim_faded_cue_overlaps'})
(ROOT/'validation/synchronized-handoff-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'synchronized handoff checks passed; twenty actual cross-lane handoffs agree')
