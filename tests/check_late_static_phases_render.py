"""Exact late phase joins: lifetime/order proofs, Overlord timeline and pixels."""
import test_paths
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import ast,collections,contextlib,hashlib,io,json,subprocess
from PIL import Image,ImageChops
import simplify_ass as s
from lyric_layer_fixtures import HEADER,event
from executable_ast_audit import executable_ast

ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'validation/late-static-phases';DEST.mkdir(exist_ok=True)
metrics=s.FontMetrics([ROOT/'fonts']);checks=[]
assert metrics.matching_face('Volkhov',0,False) is not None,'Missing Volkhov regular'
def check(name,condition):
 assert condition,name
 checks.append(name)
def merge(events,owner):
 return s.merge_static_timed_copies(events,events[0].styles if events else {},font_metrics=owner,text_only=True)
def parsed(rows):return list(s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(rows))).events.values())
def pair(tags='',x=100,layer=0,times=((1,2),(2,4)),first_tags=''):
 return parsed([event('same',100,0,times[0],first_tags),event('same',x,layer,times[1],tags)])
def verify_timeline(old,new,name):
 boundaries=sorted({t for e in old+new if e.kind=='Dialogue' for t in (e.start_s,e.end_s)})
 for left,right in zip(boundaries,boundaries[1:]):
  mid=(left+right)/2
  def paints(es):return collections.Counter(s.static_object_key(e,e.styles) for e in es if e.kind=='Dialogue' and e.start_s<=mid<e.end_s)
  check(name+f': exact paint/multiplicity over {left}-{right}',paints(old)==paints(new))
es=pair();before=deepcopy(es);out,n=merge(es,metrics)
check('touching identical holds join',n==1 and len(out)==1 and out[0].start_s==1 and out[0].end_s==4)
check('cache/history/context borrowed by timing successor',out[0].state is es[0].state and out[0].continuation is es[0].continuation and out[0].measurement is es[0].measurement)
check('records styles caches and source fields immutable',[vars(e) for e in es]==[vars(e) for e in before])
verify_timeline(es,out,'simple join')
check('idempotent',merge(out,metrics)==(out,0))
for name,options in [('gap',dict(times=((1,2),(2.01,4)))),('overlap',dict(times=((1,2.01),(2,4)))),
 ('color',dict(tags=r'\1c&HFEFFFF&')),('outline',dict(tags=r'\3c&HFFFFFF&')),('border',dict(tags=r'\bord1')),
 ('layer',dict(layer=1)),('anchor',dict(x=100.01)),('font',dict(tags=r'\fnOther')),
 ('size',dict(tags=r'\fs40.01')),('emphasis',dict(tags=r'\b1')),('spacing',dict(tags=r'\fsp.01')),
 ('fade',dict(tags=r'\fad(10,10)',first_tags=r'\fad(10,10)')),
 ('transform',dict(tags=r'\t(\frz5)',first_tags=r'\t(\frz5)'))]:
 es=pair(**options);check(name+' remains separate',merge(es,metrics)==(es,0))
for name,tags in [('inline gradient',r''),('partial opacity',r'\alpha&H80&')]:
 literal=r'sa{\1c&H123456&}me' if name=='inline gradient' else 'same'
 es=parsed([event(literal,100,0,t,tags) for t in ((1,2),(2,4))]);out,n=merge(es,metrics)
 check(name+' identical phases join unchanged',n==1);verify_timeline(es,out,name)
for name,peer,expected in [
 ('peer ended at handoff',event('Foreground',100,0,(1,2)),1),
 ('peer starts at handoff',event('Foreground',100,0,(2,4)),0),
 ('peer crosses handoff',event('Foreground',100,0,(1.9,2.1)),0),
 ('peer on other layer',event('Foreground',100,1,(1,4)),1),
 ('spatially separate peer',event('Foreground',400,0,(1,4)),1),
 ('unknown moving peer',event('Foreground',400,0,(1,4),r'\move(400,100,100,100)'),0),
 ('blurred peer',event('Foreground',400,0,(1,4),r'\blur1'),0),
 ('shadow peer',event('Foreground',400,0,(1,4),r'\shad2'),0),
 ('underline peer',event('Foreground',400,0,(1,4),r'\u1'),0),
 ('spacing peer',event('Foreground',400,0,(1,4),r'\fsp-1'),0),
 ('reset/decorated peer',event('Foreground',400,0,(1,4),r'\rLyric\u1'),0),
 ('active drawing peer',event('m 0 0 l 10 0 10 10',400,0,(1,4),r'\p1'),0),
 ('drawing ended at handoff',event('m 0 0 l 10 0 10 10',100,0,(1,2),r'\p1'),1),
 ('unknown inline layout',event(r'Fore{\fs60}ground',400,0,(1,4)),0)]:
 es=parsed([event('same',100,0,(1,2)),peer,event('same',100,0,(2,4))]);out,n=merge(es,metrics)
 check(name,n==expected)
 check(name+': stable on repeat',merge(out,metrics)==(out,0))
 if name=='spatially separate peer':check('unavailable measurements preserve uncertain order',merge(es,None)==(es,0))
# Real source IDs are not an ordering authority after support reconstruction.
es=parsed([event('same',100,0,(1,2)),event('Foreground',100,0,(2,4)),event('same',100,0,(2,4))])
for e in es:e.source_index=7
check('colliding source identities do not hide foreground',merge(es,metrics)==(es,0))
es=parsed([event('same',100,0,(2,4)),event('Foreground',100,0,(1,2)),event('same',100,0,(1,2))])
check('reverse source order checks displaced earlier lifetime',merge(es,metrics)==(es,0))
es=parsed([event('same',100,0,(2,4)),event('Foreground',100,0,(2,4)),event('same',100,0,(1,2))])
out,n=merge(es,metrics)
check('reverse source order joins when peer is already above retained first slot',n==1 and out[0].start_s==1 and out[1] is es[1])

# Compare the complete live pipeline with and without its final phase join.
# Both sides use current source paint; older contours are not a pixel oracle.
source=ROOT/'test-data/corpus/Overlord-S04E02.original.ass';source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
old_path=DEST/'Overlord.before-final-join.ass';new_path=DEST/'Overlord.current.ass'
real_merge=s.merge_static_timed_copies
def without_final_join(events,styles,**kwargs):
 if kwargs.get('text_only'):return events,0
 return real_merge(events,styles,**kwargs)
for path in (old_path,new_path):
 report=s.FontProcessingReport()
 with contextlib.redirect_stdout(io.StringIO()),patch.object(s,'merge_static_timed_copies',without_final_join if path==old_path else real_merge):
  stats=s.simplify_ass(source,path,s.SimplifyConfig(),font_metrics=metrics,font_report=report)
 check(path.name+': all exact fonts available',not report.missing_families)
 if path==old_path:old_stats=stats
 else:new_stats=stats
old=s.load_subtitle_events(old_path)[1];new=s.load_subtitle_events(new_path)[1]
expected,count=merge(old,metrics)
check('final joins remove redundant records',count>0 and len(old)-len(new)==count)
check('only final exact static joins change output',[s.static_object_key(e,e.styles,allow_unpositioned=True) for e in expected]==[s.static_object_key(e,e.styles,allow_unpositioned=True) for e in new] and [(e.start_s,e.end_s) for e in expected]==[(e.start_s,e.end_s) for e in new])
check('existing static merge counter records contribution',new_stats['static_merged']==old_stats['static_merged']+count)
check('final dialogue count correct',new_stats['output']==sum(e.kind=='Dialogue' for e in new))
check('max concurrency unchanged',new_stats['max_concurrent_out']==old_stats['max_concurrent_out'])
check('source unchanged',hashlib.sha256(source.read_bytes()).hexdigest()==source_hash)
check('no more late phase merges on output',merge(new,metrics)==(new,0))
verify_timeline(old,new,'Overlord')
# Match every atomic ending interval whose active record order differs. Include
# handoff boundaries: a join cannot bridge a gap or repaint an intentional phase.
bounds=sorted({t for e in old+new if 1278<=e.start_s<=1331 or 1278<=e.end_s<=1331 for t in (e.start_s,e.end_s)})
def render(path,at):
 run=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1',
  '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
  '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 return Image.frombytes('RGB',(1920,1080),run.stdout)
def active_order(es,t):return [s.static_object_key(e,e.styles) for e in es if e.kind=='Dialogue' and e.start_s<=t<e.end_s]
samples=set()
for a,b in zip(bounds,bounds[1:]):
 mid=(a+b)/2
 if active_order(old,mid)!=active_order(new,mid):samples.update((a,mid))
check('changed-order intervals exercised',len(samples)>0)
for at in sorted(samples):
 a,b=render(old_path,at),render(new_path,at)
 check(f'Overlord pixel-identical at {at:.3f}',ImageChops.difference(a,b).getbbox() is None)
check('all merged-phase boundaries preserved',all(e.start_s in {x.start_s for x in old} and e.end_s in {x.end_s for x in old} for e in new))
def definitions(path):return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
# Historical release scope is independent of current merger consolidation.
a,b=definitions(ROOT/'tests/references/simplify_ass_v184.py'),definitions(ROOT/'tests/references/simplify_ass_v185.py')
check('only two bounded phase helpers added',b.keys()-a.keys()=={'_merge_late_static_phase_round','merge_late_static_phases'} and not a.keys()-b.keys())
check('only final pipeline wiring changed',{name for name in a if ast.dump(a[name])!=ast.dump(b[name])}=={'simplify_ass'})
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks),late_joins=count,render_samples=len(samples),runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'late static phase checks passed;',count,'Overlord joins;',len(samples),'pixel-identical order/boundary samples')
