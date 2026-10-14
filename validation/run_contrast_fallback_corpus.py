"""Fresh v198 source-intent comparisons against hash-verified v197 outputs."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify-existing',action='store_true');args=parser.parse_args()
DEST=ROOT/'validation/contrast-fallback-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
cases=json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
cases.append(dict(name='Goblin-Slayer-S01E02-track6',source='test-data/Goblin-Slayer-S01E02-track6-source.ass',sha256='476e93d4d162af152b6ddddf4f715f301bec7373e67e8645c220b8360d38d017'))
def footprint_key(e,omit_pose=False):
 # Compare literal fill/geometry independently of intentional contour changes.
 obj=s.static_object_key(e,e.styles,allow_unpositioned=True)
 if obj is None:return tuple(e.fields()[:1]+e.fields()[3:])
 runs=[]
 for signature,drawing,literal in obj[-1]:
  state=tuple((k,v) for k,v in signature.formatting if k not in ({'3c','3a','bord','xbord','ybord'} | ({'pos','fscx','fscy','frz'} if omit_pose else set())))
  key=(state,signature.continuation,drawing)
  if runs and runs[-1][0]==key:runs[-1]=(key,runs[-1][1]+literal)
  else:runs.append((key,literal))
 return obj[:-1]+(tuple(runs),)
def footprint_timeline(events,omit_pose=False):
 from collections import Counter,defaultdict
 changes=defaultdict(Counter)
 for e in events:
  if e.kind!='Dialogue':continue
  key=footprint_key(e,omit_pose);changes[e.start_s][key]+=1;changes[e.end_s][key]-=1
 live=Counter();result=[]
 for time,delta in sorted(changes.items()):
  live.update(delta);live=+live
  if not result or live!=result[-1][1]:result.append((time,live.copy()))
 return result
def source_pose(e):
 keys=('fn','fs','b','i','an','frx','fry','frz','fax','fay','fscx','fscy')
 return tuple(e.state.get(k,s.DEFAULT_STATE.get(k)) for k in keys)+(s.get_pos(e.text),)
def pose_equal(a,b):
 if isinstance(a,(tuple,list)) and isinstance(b,(tuple,list)):
  return len(a)==len(b) and all(pose_equal(x,y) for x,y in zip(a,b))
 if isinstance(a,(int,float)) and isinstance(b,(int,float)):return abs(a-b)<=.011
 return a==b
def verify_authored_pose_changes(before,after,source):
 assert footprint_timeline(before,True)==footprint_timeline(after,True), 'text/fill/font/visibility changed'
 originals=s.load_subtitle_events(source)[1];changed=[]
 for e in after:
  word=s.OVERRIDE_RE.sub('',e.text)
  peers=[p for p in before if p.start_s<e.end_s and p.end_s>e.start_s and footprint_key(p,True)==footprint_key(e,True)]
  if peers and all(source_pose(p)==source_pose(e) for p in peers):continue
  matches=[p for p in originals if p.kind==e.kind and p.style==e.style and p.name==e.name and
   s.OVERRIDE_RE.sub('',p.text)==word and p.start_s<e.end_s and p.end_s>e.start_s and pose_equal(source_pose(p),source_pose(e))]
  assert matches,(e.style,word,'new pose not present in its authored source cue')
  changed.append(dict(style=e.style,text=word,start_s=e.start_s,end_s=e.end_s,pose=source_pose(e)))
 return changed
records=[]
for case in cases:
 source=ROOT/case['source'];assert sha(source)==case['sha256']
 baseline=ROOT/'validation/proved-backing-paint-corpus/windows'/(case['name']+'.ass')
 old=json.loads(baseline.with_suffix('.json').read_text())
 assert old['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v197.py') and old['source_sha256']==sha(source) and old['output_sha256']==sha(baseline) and not old['missing_families']
 output=DEST/baseline.name
 if not args.verify_existing:subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),'--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
 new=json.loads(output.with_suffix('.json').read_text())
 assert new['engine_sha256']==sha(ROOT/'simplify_ass.py') and new['source_sha256']==sha(source) and new['output_sha256']==sha(output) and not new['missing_families']
 before=s.load_subtitle_events(baseline)[1];after=s.load_subtitle_events(output)[1]
 changed=[];structural=[]
 for a,b in zip(before,after):
  if a.fields()!=b.fields():
   changed.append(dict(style=b.style,start_s=b.start_s,end_s=b.end_s,before=a.text,after=b.text))
   if a.fields()[:9]!=b.fields()[:9] or s.OVERRIDE_RE.sub('',a.text)!=s.OVERRIDE_RE.sub('',b.text) or s.text_layout_key(a)!=s.text_layout_key(b):structural.append(dict(before=a.fields(),after=b.fields()))
 diff={k:[old['statistics'].get(k),new['statistics'].get(k)] for k in set(old['statistics'])|set(new['statistics']) if old['statistics'].get(k)!=new['statistics'].get(k)}
 same_timeline=footprint_timeline(before)==footprint_timeline(after)
 authored_poses=[] if same_timeline else verify_authored_pose_changes(before,after,source)
 record=dict(footprint_timeline_identical=same_timeline,authored_pose_changes=authored_poses,case=case['name'],source_sha256=sha(source),output_sha256=sha(output),before_count=len(before),after_count=len(after),changed=changed,structural=structural,statistics_changes=diff,wall_s=new['wall_s'])
 records.append(record)
 (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,engine_sha256=sha(ROOT/'simplify_ass.py'),cases=records),indent=2)+'\n')
 print(case['name'],'events',len(before),len(after),'changed',len(changed),'structural',len(structural),'statistics',diff,flush=True)
