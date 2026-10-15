"""Regenerate v204/current with identical fonts and explain source-owned changes."""
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/syllable-lifecycles/corpus';DEST.mkdir(parents=True,exist_ok=True)
BASE=ROOT/'validation/syllable-lifecycles/simplify_ass_v204.py'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE)=='d3908aa37e55a2270e37e6f5230ffc81cfe5b3cbe75d8084c9dd6b1d7f4bd78a'
cases=json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
cases+=[dict(name='Goblin-Slayer-S01E02-track6',source='test-data/Goblin-Slayer-S01E02-track6-source.ass'),
        dict(name='Solo-Leveling-S01E02',source='test-data/Solo-Leveling-S01E02-source.ass',fonts='test-data/Solo-Leveling-S01E02-fonts')]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse-baseline',action='store_true');args=parser.parse_args()
engine_sha=sha(ROOT/'simplify_ass.py');baseline_sha=sha(BASE)
font_paths={ROOT/case.get('fonts','fonts') for case in cases}
font_sha={str(p.relative_to(ROOT)):sha(p) for folder in font_paths for p in sorted(folder.rglob('*')) if p.is_file()}
previous={}
if args.reuse_baseline:
    summary=json.loads((DEST/'summary.json').read_text())
    assert summary['baseline_sha256']==baseline_sha and summary['font_sha256']==font_sha
    previous={case['case']:case['baseline'] for case in summary['cases']}
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
def convert(case):
    source=ROOT/case['source'];fonts=ROOT/case.get('fonts','fonts');before=sha(source)
    if 'sha256' in case:assert before==case['sha256']
    reports={}
    for label,engine in [('v204',BASE),('current',ROOT/'simplify_ass.py')]:
        out=DEST/label/(case['name']+'.ass')
        if label=='v204' and args.reuse_baseline:
            prior=previous[case['name']]
            assert prior['engine_sha256']==baseline_sha and prior['source_sha256']==before
            assert prior['output_sha256']==sha(out) and json.loads(out.with_suffix('.json').read_text())==prior
        else:
            subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(engine),
                            '--source',str(source),'--fonts',str(fonts),'--output',str(out)],
                           cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
        reports[label]=json.loads(out.with_suffix('.json').read_text())
        assert not reports[label]['missing_families'],reports[label]
        assert reports[label]['source_sha256']==before
    old=s.load_subtitle_events(DEST/'v204'/(case['name']+'.ass'))[1]
    new=s.load_subtitle_events(DEST/'current'/(case['name']+'.ass'))[1]
    records=lambda events:[tuple(e.fields()) for e in events]
    old_fields,new_fields=records(old),records(new)
    changes=dict(before_count=len(old),after_count=len(new),events_identical=old_fields==new_fields,
                 removed_records=sum((Counter(old_fields)-Counter(new_fields)).values()),
                 added_records=sum((Counter(new_fields)-Counter(old_fields)).values()))
    if case['name']=='Solo-Leveling-S01E02':
        assert records([e for e in old if e.style!='ED - Romaji'])==records([e for e in new if e.style!='ED - Romaji'])
        captions=[e for e in new if e.style=='ED - Romaji'];assert len(captions)==16
        assert all(e.layer=='1' and e.state['1c']=='E1DFD8' and e.state['3c']=='000000' and e.state['bord']==1 for e in captions)
        assert all(a.end_s<=b.start_s for a,b in zip(captions,captions[1:]))
        changes['other_styles_identical']=True
    else:
        assert changes['events_identical'],(case['name'],changes)
        assert reports['v204']['statistics']==reports['current']['statistics'],case['name']
    assert sha(source)==before
    result=dict(case=case['name'],source_sha256=before,baseline=reports['v204'],current=reports['current'],**changes)
    print(case['name'],changes,flush=True)
    return result
with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(convert,cases))
assert engine_sha==sha(ROOT/'simplify_ass.py') and baseline_sha==sha(BASE)
assert font_sha=={str(p.relative_to(ROOT)):sha(p) for folder in font_paths for p in sorted(folder.rglob('*')) if p.is_file()}
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=engine_sha,baseline_sha256=baseline_sha,font_sha256=font_sha,cases=results),indent=2)+'\n')
print(len(results),'fresh same-font corpus comparisons passed',flush=True)
