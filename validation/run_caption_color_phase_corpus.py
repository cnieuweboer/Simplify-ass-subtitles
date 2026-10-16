"""Fresh exact-font corpus comparison against the hash-bound v208 outputs.

Requires validation/representative-paint-corpus/summary.json and its private assets.
Writes differences as evidence; review their behavior before accepting a release.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/caption-color-phase-corpus';DEST.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
BASE=ROOT/'validation/demon-opening-diagnosis/simplify_ass_v208.py'
assert sha(BASE)=='2868f9d81a9eb9273ab77365d21d609142e902a04846adf43060dfe5f1abb519'
previous=json.loads((ROOT/'validation/representative-paint-corpus/summary.json').read_text())
assert previous['engine_sha256']==sha(BASE)
fonts=previous['font_sha256'];assert all(sha(ROOT/p)==value for p,value in fonts.items())
engine_sha=sha(ROOT/'simplify_ass.py');env=os.environ.copy()
env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
def convert(case):
    old=case['current'];source=Path(old['source']);baseline=Path(old['output']);before=sha(source)
    assert old['engine_sha256']==sha(BASE) and old['source_sha256']==before and old['output_sha256']==sha(baseline)
    assert not old['missing_families']
    folder=ROOT/('test-data/Solo-Leveling-S01E02-fonts' if case['case']=='Solo-Leveling-S01E02' else 'fonts')
    output=DEST/(case['case']+'.ass')
    with output.with_suffix('.log').open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),
            '--source',str(source),'--fonts',str(folder),'--output',str(output)],cwd=ROOT,env=env,check=True,stdout=log,stderr=log)
    new=json.loads(output.with_suffix('.json').read_text())
    assert new['engine_sha256']==engine_sha and not new['missing_families'] and sha(source)==before
    a=s.load_subtitle_events(baseline)[1];b=s.load_subtitle_events(output)[1]
    records=lambda es:[tuple(e.fields()) for e in es]
    removed=Counter(records(a))-Counter(records(b));added=Counter(records(b))-Counter(records(a))
    stats={k:[old['statistics'].get(k),new['statistics'].get(k)] for k in old['statistics'].keys()|new['statistics'].keys() if old['statistics'].get(k)!=new['statistics'].get(k)}
    result=dict(case=case['case'],baseline=old,current=new,events_identical=records(a)==records(b),
        bytes_identical=baseline.read_bytes()==output.read_bytes(),before_count=len(a),after_count=len(b),
        removed_records=sum(removed.values()),added_records=sum(added.values()),
        changed_styles=sorted({record[3] for record in removed|added}),statistics_changes=stats)
    print(case['case'],{k:result[k] for k in ['before_count','after_count','changed_styles','statistics_changes']},flush=True)
    return result
with ThreadPoolExecutor(max_workers=3) as pool:cases=list(pool.map(convert,previous['cases']))
assert engine_sha==sha(ROOT/'simplify_ass.py') and all(sha(ROOT/p)==value for p,value in fonts.items())
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=engine_sha,baseline_sha256=sha(BASE),
    harness_sha256=sha(Path(__file__)),font_sha256=fonts,cases=cases),indent=2)+'\n')
print(len(cases),'fresh hash-bound exact-font corpus comparisons completed',flush=True)
