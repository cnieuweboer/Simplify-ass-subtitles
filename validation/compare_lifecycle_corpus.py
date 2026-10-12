"""Windows complete corpus parity, isolated opening change and complete text."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,os,subprocess,sys,hashlib
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));import simplify_ass as s
fs=json.loads((root/'test-data/corpus-manifest.json').read_text());dest=root/'validation/full-corpus-v177/windows';dest.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=os.pathsep.join([str(root/'validation/backend_startup'),str(root.parent/'test-deps')])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(f):
 name=f['name'];source=root/f['source'];assert sha(source)==f['sha256']
 baseline=root/'validation/full-corpus-v176/windows'/(name+'-v176.ass');output=dest/(name+'-v177.ass')
 p=subprocess.run([sys.executable,str(root/'validation/measure_one.py'),'--engine',str(root/'simplify_ass.py'),'--source',str(source),'--fonts',str(root/'fonts'),'--output',str(output)],env=env,capture_output=True,text=True);assert p.returncode==0,(name,p.stderr)
 old=json.loads(baseline.with_suffix('.json').read_text());current=json.loads(output.with_suffix('.json').read_text())
 before=s.load_subtitle_events(baseline)[1];after=s.load_subtitle_events(output)[1]
 if name.startswith('Attack'):
  unchanged=lambda es:[e.fields() for e in es if e.style!='OP-R']
  assert unchanged(before)==unchanged(after),'outside romanized opening changed'
  lines=[e for e in after if e.style=='OP-R'];assert len(lines)==21
  fixture=s.load_subtitle_events(root/'outputs/opening-probe.ass')[1]
  assert [e.fields() for e in lines]==[e.fields() for e in fixture if e.style=='OP-R']
 else:
  assert baseline.read_bytes()==output.read_bytes(),name
  assert old['statistics']==current['statistics'],name
 print(name,old['statistics']['output'],'->',current['statistics']['output'],flush=True)
 return dict(case=name,before=old['statistics'],after=current['statistics'],seconds=current['wall_s'],output_sha256=sha(output))
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,fs))
(root/'validation/full-lifecycle-comparison-v177.json').write_text(json.dumps(dict(runtime_sha256=sha(root/'simplify_ass.py'),backend='windows',cases=results),indent=2)+'\n')
print('9 Windows full-corpus comparisons passed')
