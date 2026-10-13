"""Fresh nine-source validation against the hash-verified v184 baseline."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/late-phase-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
metrics=s.FontMetrics([ROOT/'fonts']);records=[]
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
 source=ROOT/case['source'];assert sha(source)==case['sha256']
 baseline=ROOT/'validation/late-copy-corpus/windows'/(case['name']+'.ass')
 meta=json.loads(baseline.with_suffix('.json').read_text())
 assert meta['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v184.py')
 assert meta['source_sha256']==sha(source) and meta['output_sha256']==sha(baseline) and meta['missing_families']==[]
 output=DEST/baseline.name
 subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),
  '--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
 new_meta=json.loads(output.with_suffix('.json').read_text())
 assert new_meta['missing_families']==[],('Missing font; stop',case['name'],new_meta['missing_families'])
 old=s.load_subtitle_events(baseline)[1];new=s.load_subtitle_events(output)[1]
 expected,count=s.merge_late_static_phases(old,metrics)
 assert [e.fields() for e in expected]==[e.fields() for e in new],(case['name'],'unrelated output changed')
 assert s.merge_late_static_phases(new,metrics)==(new,0),('Late phases not settled',case['name'])
 diffs={k:(meta['statistics'].get(k),new_meta['statistics'].get(k)) for k in meta['statistics'].keys()|new_meta['statistics'].keys()
  if meta['statistics'].get(k)!=new_meta['statistics'].get(k)}
 assert not diffs.keys()-{'static_merged','output'},(case['name'],'unrelated counter changed',diffs)
 assert new_meta['statistics']['static_merged']==meta['statistics']['static_merged']+count
 record=dict(case=case['name'],joins=count,old_events=len(old),new_events=len(new),byte_identical=sha(output)==sha(baseline),
  source_sha256=sha(source),baseline_sha256=sha(baseline),output_sha256=sha(output),stats_differences=diffs)
 records.append(record)
 (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,runtime_sha256=sha(ROOT/'simplify_ass.py'),
  reference_sha256=sha(ROOT/'tests/references/simplify_ass_v184.py'),completed=len(records),cases=records),indent=2)+'\n')
 print(case['name'],count,'exact late joins',len(old),'->',len(new),flush=True)
print('All nine full corpus conversions match only the final static-phase proof; no missing fonts')
