"""Compare the current engine with a private, hash-bound color-phase corpus.

Restore the v209 corpus summary/outputs and the Blood+/Kill la Kill investigation
assets described in docs/CAPTION_COLOR_PHASES.md. Media and fonts stay private.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import argparse,hashlib,json,os,subprocess,sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
ASSETS=ROOT/'validation/kill-color-phase-investigation'
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--baseline-engine',type=Path,default=ASSETS/'simplify_ass_v209.py')
ap.add_argument('--baseline-summary',type=Path,default=ASSETS/'v209-corpus-summary.json')
ap.add_argument('--baseline-sha256',default='ef208de366002785624fab02fa94d96d93ba6f40fc8a05e5d6b38616dc875abf')
ap.add_argument('--output-dir',type=Path,default=ROOT/'validation/caption-glow-phase-corpus')
args=ap.parse_args();BASE=args.baseline_engine;DEST=args.output_dir;DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
baseline_sha=args.baseline_sha256
assert sha(BASE)==baseline_sha
previous=json.loads(args.baseline_summary.read_text())
assert previous['engine_sha256']==baseline_sha
fonts=previous['font_sha256'];assert all(sha(ROOT/p)==value for p,value in fonts.items())
engine_sha=sha(ROOT/'simplify_ass.py');env=os.environ.copy()
env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')

def measure(engine,source,font_folder,output):
    with output.with_suffix('.driver.log').open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(engine),
            '--source',str(source),'--fonts',str(font_folder),'--output',str(output)],
            cwd=ROOT,env=env,check=True,stdout=log,stderr=log)
    result=json.loads(output.with_suffix('.json').read_text())
    assert not result['missing_families'] and result['engine_sha256']==sha(engine)
    return result

jobs=[]
for case in previous['cases']:
    old=case['current'];assert old['engine_sha256']==baseline_sha and not old['missing_families']
    source=Path(old['source']);output=Path(old['output'])
    assert sha(source)==old['source_sha256'] and sha(output)==old['output_sha256']
    font_folder=ROOT/('test-data/Solo-Leveling-S01E02-fonts' if case['case']=='Solo-Leveling-S01E02' else 'fonts')
    if case['case'] in {'Blood-S01E13','Kill-la-Kill-S01E20'}:font_folder=source.parent.parent/'fonts'
    jobs.append((case['case'],source,font_folder,old))
for name,folder,track in [('Blood-S01E13','blood-color-phase-investigation',2),
                          ('Kill-la-Kill-S01E20','kill-color-phase-investigation',3)]:
    if any(job[0]==name for job in jobs):continue
    assets=ROOT/'validation'/folder;source=assets/f'subtitles/track-{track}.original.ass'
    font_folder=assets/'fonts'
    fonts.update({str(p.relative_to(ROOT)):sha(p) for p in font_folder.glob('*') if p.is_file()})
    jobs.append((name,source,font_folder,None))

def compare(job):
    name,source,font_folder,old=job;before=sha(source)
    if old is None:old=measure(BASE,source,font_folder,DEST/(name+'.baseline.ass'))
    assert (DEST/(name+'.ass')).resolve() not in {source.resolve(),Path(old['output']).resolve()}
    new=measure(ROOT/'simplify_ass.py',source,font_folder,DEST/(name+'.ass'))
    assert before==sha(source)==new['source_sha256'] and new['engine_sha256']==engine_sha
    baseline=Path(old['output']);output=Path(new['output'])
    assert sha(baseline)==old['output_sha256']
    records=lambda p:[tuple(e.fields()) for e in s.load_subtitle_events(p)[1]]
    a=records(baseline);b=records(output);removed=Counter(a)-Counter(b);added=Counter(b)-Counter(a)
    result=dict(case=name,baseline=old,current=new,bytes_identical=baseline.read_bytes()==output.read_bytes(),
        before_count=len(a),after_count=len(b),changed_styles=sorted({e[3] for e in removed|added}),
        removed_records=sum(removed.values()),added_records=sum(added.values()),
        statistics_changes={k:[old['statistics'].get(k),new['statistics'].get(k)]
            for k in old['statistics'].keys()|new['statistics'].keys()
            if old['statistics'].get(k)!=new['statistics'].get(k)})
    print(name,{k:result[k] for k in ('bytes_identical','before_count','after_count','changed_styles')},flush=True)
    return result

with ThreadPoolExecutor(max_workers=3) as pool:cases=list(pool.map(compare,jobs))
assert engine_sha==sha(ROOT/'simplify_ass.py') and all(sha(ROOT/p)==value for p,value in fonts.items())
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=engine_sha,baseline_sha256=baseline_sha,
    harness_sha256=sha(Path(__file__)),font_sha256=fonts,cases=cases),indent=2)+'\n')
print(len(cases),'fresh exact-font corpus comparisons completed',flush=True)
