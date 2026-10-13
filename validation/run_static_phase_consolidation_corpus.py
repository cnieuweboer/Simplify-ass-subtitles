"""Fresh v186 comparisons against hash-verified v185 corpus outputs."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/static-phase-consolidation-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
records=[]
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
 source=ROOT/case['source'];assert sha(source)==case['sha256']
 baseline=ROOT/'validation/late-phase-corpus/windows'/(case['name']+'.ass')
 old=json.loads(baseline.with_suffix('.json').read_text())
 assert old['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v185.py')
 assert old['source_sha256']==sha(source) and old['output_sha256']==sha(baseline) and old['missing_families']==[]
 output=DEST/baseline.name
 subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),
  '--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
 new=json.loads(output.with_suffix('.json').read_text())
 assert new['missing_families']==[],('Missing required exact font; stop',case['name'],new['missing_families'])
 assert sha(output)==sha(baseline),(case['name'],'output changed; investigate before accepting')
 assert new['statistics']==old['statistics'],(case['name'],'counter changes',new['statistics'],old['statistics'])
 events=s.load_subtitle_events(output)[1]
 _,count=s.merge_static_timed_copies(events,events[0].styles,font_metrics=s.FontMetrics([ROOT/'fonts']),text_only=True)
 assert count==0,(case['name'],'final exact phases not settled')
 record=dict(case=case['name'],source_sha256=sha(source),baseline_sha256=sha(baseline),output_sha256=sha(output),
  byte_identical=True,statistics_identical=True,events=len(events),old_wall_s=old['wall_s'],wall_s=new['wall_s'])
 records.append(record)
 (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,runtime_sha256=sha(ROOT/'simplify_ass.py'),
  reference_sha256=sha(ROOT/'tests/references/simplify_ass_v185.py'),completed=len(records),cases=records),indent=2)+'\n')
 print(case['name'],'output/statistics identical to v185; final phases settled',flush=True)
print('All nine full corpus outputs/counters match v185; no missing fonts')
