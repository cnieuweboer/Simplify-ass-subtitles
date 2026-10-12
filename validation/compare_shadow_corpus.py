"""Full-fixture differential runs on Windows/BASIC and RAQM font backends."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib, importlib.util, json, os, subprocess, sys
root=Path(__file__).resolve().parents[1]
workspace=root.parent
spec=importlib.util.spec_from_file_location('corpus_current',root/'simplify_ass.py')
engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine)
manifest=json.loads((workspace/'regression-v172/manifest.json').read_text())
destination=root/'validation/full-corpus-v174'
destination.mkdir(exist_ok=True)
def run(job):
    backend,fixture=job;name=fixture['name'];folder=destination/backend
    folder.mkdir(exist_ok=True)
    env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']=backend
    env['PYTHONPATH']=os.pathsep.join([str(root/'validation/backend_startup'),str(workspace/'test-deps')])
    paths=[];reports=[]
    for version in ('v173','v174'):
        source=workspace/version/'simplify_ass.py'
        output=folder/(name+'-'+version+'.ass')
        p=subprocess.run([sys.executable,str(root/'validation/measure_one.py'),'--engine',str(source),
                          '--source',fixture['source'],'--fonts',str(workspace/'regression-v172/fonts'),
                          '--output',str(output)],env=env,capture_output=True,text=True)
        assert p.returncode==0,(backend,name,version,p.stdout,p.stderr)
        paths.append(output);reports.append(json.loads(output.with_suffix('.json').read_text()))
    before=engine.load_subtitle_events(paths[0])[1];after=engine.load_subtitle_events(paths[1])[1]
    expected,count=engine.normalize_shadow_lettering(before)
    assert len(before)==len(after)
    assert all(a.fields()==b.fields() for a,b in zip(expected,after)),(backend,name,'unexpected output edit')
    assert [e.text for e in before if e.state.get('p')]==[e.text for e in after if e.state.get('p')]
    old_stats=reports[0]['statistics'];new_stats=reports[1]['statistics'].copy()
    assert new_stats.pop('shadow_lettering_normalized')==count
    assert new_stats==old_stats,(backend,name,'unexpected statistics edit')
    assert reports[0]['source_sha256']==reports[1]['source_sha256']==fixture['sha256']
    result=dict(backend=backend,case=name,normalized=count,events=len(after),rectangles_unchanged=True,
                only_expected_text_changes=True,existing_statistics_identical=True,
                baseline_seconds=reports[0]['wall_s'],current_seconds=reports[1]['wall_s'],
                before=str(paths[0]),after=str(paths[1]))
    print(backend,name,count,round(reports[1]['wall_s'],2),flush=True)
    return result
jobs=[(backend,fixture) for backend in ('windows','raqm') for fixture in manifest['fixtures']]
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,jobs))
report=dict(runtime_sha256=hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest(),cases=results)
(root/'validation/full-shadow-comparison-v174.json').write_text(json.dumps(report,indent=2)+'\n')
print('All 16 fixture/backend comparisons passed',flush=True)
