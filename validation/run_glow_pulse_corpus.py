"""Fresh v194 comparisons against the verified v193 corpus plus the new failure."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/chant-overhang-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
records=[]
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
 source=ROOT/case['source'];assert sha(source)==case['sha256']
 baseline=ROOT/'validation/owned-backing-corpus/windows'/(case['name']+'.ass')
 old=json.loads(baseline.with_suffix('.json').read_text())
 assert old['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v193.py')
 assert old['source_sha256']==sha(source) and old['output_sha256']==sha(baseline) and old['missing_families']==[]
 output=DEST/baseline.name
 subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),'--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
 new=json.loads(output.with_suffix('.json').read_text())
 assert new['engine_sha256']==sha(ROOT/'simplify_ass.py') and new['source_sha256']==sha(source) and new['output_sha256']==sha(output)
 assert not new['missing_families'],new['missing_families']
 assert output.read_bytes()==baseline.read_bytes(),(case['name'],'unexplained corpus change')
 assert new['statistics']==old['statistics'],(case['name'],'statistics changed')
 records.append(dict(case=case['name'],source_sha256=sha(source),output_sha256=sha(output),byte_identical=True,statistics_identical=True,wall_s=new['wall_s']))
 (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,engine_sha256=sha(ROOT/'simplify_ass.py'),cases=records),indent=2)+'\n')
 print(case['name'],'byte-identical output and statistics',flush=True)
source=ROOT/'test-data/Goblin-Slayer-S01E02-track6-source.ass'
output=DEST/'Goblin-Slayer-S01E02-track6.ass'
subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),'--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True)
new=json.loads(output.with_suffix('.json').read_text());assert not new['missing_families']
assert new['engine_sha256']==sha(ROOT/'simplify_ass.py')
baseline=ROOT/'validation/owned-backing-corpus/windows/Goblin-Slayer-S01E02-track6.ass'
old=json.loads(baseline.with_suffix('.json').read_text())
assert old['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v193.py')
assert old['source_sha256']==sha(source) and old['output_sha256']==sha(baseline)
old_events=s.load_subtitle_events(baseline)[1];new_events=s.load_subtitle_events(output)[1]
affected={'OP - R Chant'}
assert [e.fields() for e in old_events if e.style not in affected]==[e.fields() for e in new_events if e.style not in affected]
assert len(new_events)<len(old_events)
assert not new['missing_families']
print('Nine established corpus outputs/statistics unchanged; chant effects simplified; all other supplied-track styles unchanged')
