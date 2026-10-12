"""Windows-only complete-corpus checks; reuse verified v175 baselines."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import hashlib,importlib.util,json,os,subprocess,sys
root=Path(__file__).resolve().parents[1];workspace=root.parent
spec=importlib.util.spec_from_file_location('corpus_engine',root/'simplify_ass.py');s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)
fixtures=json.loads((root/'test-data/corpus-manifest.json').read_text());dest=root/'validation/full-corpus-v176/windows';dest.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=os.pathsep.join([str(root/'validation/backend_startup'),str(workspace/'test-deps')])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def activity(es):
 changes={}
 for e in es:
  if e.kind!='Dialogue':continue
  changes.setdefault(e.start_s,[0,0])[0]+=1;changes.setdefault(e.end_s,[0,0])[1]+=1
 active=peak=starts_peak=during=0
 for t,(starts,ends) in sorted(changes.items()):
  active-=ends
  if active:during+=starts
  active+=starts;peak=max(peak,active);starts_peak=max(starts_peak,starts)
 return dict(peak_active=peak,peak_starts=starts_peak,additions_while_active=during)
def run(f):
 name=f['name'];source=root/f['source'];assert sha(source)==f['sha256']
 baseline=root/'validation/full-corpus-v175/windows'/(name+'-v175.ass')
 baseline_report=baseline.with_suffix('.json')
 if name!='WitchHat-S01E02' and not name.startswith('Attack'):
  baseline=root/'outputs'/(name+'.ass')
 def convert(engine,path):
  cmd=[sys.executable,str(root/'validation/measure_one.py'),'--engine',str(engine),'--source',str(source),'--fonts',str(root/'fonts'),'--output',str(path)]
  p=subprocess.run(cmd,env=env,capture_output=True,text=True);assert p.returncode==0,(name,p.stdout,p.stderr)
  return json.loads(path.with_suffix('.json').read_text())
 if not f['baseline_reusable']:
  baseline=dest/(name+'-v175-baseline.ass');old=convert(root/'test-data/simplify_ass-v175-reference.py',baseline)
 else:old=json.loads(baseline_report.read_text())
 if name.startswith('Attack'):baseline=root/'outputs/Attack-on-Titan-S02E01-track3-v175.ass'
 output=dest/(name+'-v176.ass');current=convert(root/'simplify_ass.py',output)
 assert old['source_sha256']==current['source_sha256']==f['sha256']
 before=s.load_subtitle_events(baseline)[1] if baseline.exists() else None;after=s.load_subtitle_events(output)[1]
 result=dict(case=name,backend='windows',source_sha256=f['sha256'],baseline_sha256=old['output_sha256'],output_sha256=sha(output),baseline_events=old['statistics']['output'],current_events=current['statistics']['output'],baseline_statistics=old['statistics'],current_statistics=current['statistics'],byte_identical=old['output_sha256']==sha(output),baseline_seconds=old['wall_s'],current_seconds=current['wall_s'],before_activity=activity(before) if before is not None else None,after_activity=activity(after),baseline_regenerated=not f['baseline_reusable'])
 if name.startswith('Attack'):
  parents=lambda es:[e for e in es if e.style=='ED-R' and e.layer!='3']
  assert [e.fields() for e in parents(before)]==[e.fields() for e in parents(after)]
  assert len(parents(after))==24
  assert sum(e.style=='ED-R' and e.layer=='3' for e in before)==4413
  assert sum(e.style=='ED-R' and e.layer=='3' for e in after)==0
  outside=lambda es:[e.fields() for e in es if e.style!='ED-R']
  assert outside(before)==outside(after),'unrelated events changed'
  assert old['statistics']['output']-current['statistics']['output']==4413
  assert current['statistics']['covered_fragments']-old['statistics']['covered_fragments']==4413
  result.update(owned_word_echoes_removed=4413,retained_ending_lines=24,unrelated_events_identical=True,parent_text_paint_placement_timing_identical=True,styles_before=dict(Counter(e.style for e in before if e.kind=='Dialogue')),styles_after=dict(Counter(e.style for e in after if e.kind=='Dialogue')))
 else:
  assert result['byte_identical'],(name,'output changed')
  assert old['statistics']==current['statistics'],(name,'statistics changed')
 print(name,result['baseline_events'],'->',result['current_events'],'unchanged',result['byte_identical'],round(current['wall_s'],2),'seconds',flush=True)
 return result
with ThreadPoolExecutor(max_workers=2) as pool:cases=list(pool.map(run,fixtures))
report=dict(runtime_sha256=sha(root/'simplify_ass.py'),backend='windows',cases=cases)
(root/'validation/full-word-echo-comparison-v176.json').write_text(json.dumps(report,indent=2)+'\n')
print('All 9 Windows full-corpus comparisons passed',flush=True)
