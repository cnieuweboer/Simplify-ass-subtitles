"""Fresh v189: only safe final tag serialization differs from hash-verified v188."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/final-static-compaction-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
records=[]
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
 source=ROOT/case['source'];assert sha(source)==case['sha256']
 baseline=ROOT/'validation/caption-ownership-corpus/windows'/(case['name']+'.ass')
 old=json.loads(baseline.with_suffix('.json').read_text())
 assert old['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v188.py')
 assert old['source_sha256']==sha(source) and old['output_sha256']==sha(baseline) and old['missing_families']==[]
 output=DEST/baseline.name
 subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),
  '--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
 new=json.loads(output.with_suffix('.json').read_text())
 assert new['engine_sha256']==sha(ROOT/'simplify_ass.py')
 assert new['source_sha256']==sha(source) and new['output_sha256']==sha(output)
 assert new['missing_families']==[],('Missing required exact font; stop',case['name'],new['missing_families'])
 before=s.load_subtitle_events(baseline)[1];after=s.load_subtitle_events(output)[1]
 expected=s.compact_static_overrides(before,2,final=True)
 assert [e.fields() for e in after]==[e.fields() for e in expected],(case['name'],'unexplained output change')
 assert len(before)==len(after) and new['statistics']==old['statistics'],(case['name'],'counts or statistics changed')
 changed=0;saved=0
 for a,b in zip(before,after):
  assert a.fields()[:-1]==b.fields()[:-1]
  if a.text!=b.text:
   assert s._finished_static_key(a)==s._finished_static_key(b),(case['name'],'literal formatting/history changed')
   assert s.OVERRIDE_RE.sub('',a.text)==s.OVERRIDE_RE.sub('',b.text)
   changed+=1;saved+=len(a.text)-len(b.text)
 assert [e.text for e in s.compact_static_overrides(after,2,final=True)]==[e.text for e in after]
 assert s.remove_late_complete_copies(after)[1]==0
 assert s.merge_static_timed_copies(after,after[0].styles,font_metrics=s.FontMetrics([ROOT/'fonts']),text_only=True)[1]==0
 records.append(dict(case=case['name'],source_sha256=sha(source),baseline_sha256=sha(baseline),output_sha256=sha(output),
  events=len(after),compacted=changed,saved_text_characters=saved,statistics_identical=True,span_formatting_history_equivalent=True))
 (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,runtime_sha256=sha(ROOT/'simplify_ass.py'),
  reference_sha256=sha(ROOT/'tests/references/simplify_ass_v188.py'),completed=len(records),cases=records),indent=2)+'\n')
 print(case['name'],changed,'records compacted;',saved,'text characters saved; formatting/history and statistics unchanged',flush=True)
print('All nine full corpus comparisons pass; final spelling settled; no missing fonts')
