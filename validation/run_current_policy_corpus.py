"""Regenerate ten corpus sources and require unchanged output for test-only work."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline',type=Path,default=ROOT/'validation/contrast-fallback-corpus/windows',
                    help='verified current-engine outputs saved before the test changes')
args = parser.parse_args()
DEST = ROOT/'validation/current-policy-corpus/windows'
DEST.mkdir(parents=True,exist_ok=True)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
engine_hash = sha(ROOT/'simplify_ass.py')
cases = json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
cases.append(dict(name='Goblin-Slayer-S01E02-track6',
                  source='test-data/Goblin-Slayer-S01E02-track6-source.ass',
                  sha256='476e93d4d162af152b6ddddf4f715f301bec7373e67e8645c220b8360d38d017'))
baselines = []
# Validate every prerequisite before starting costly conversions.
for case in cases:
    source = ROOT/case['source']; baseline = args.baseline/(case['name']+'.ass')
    previous = json.loads(baseline.with_suffix('.json').read_text())
    assert sha(source)==case['sha256']==previous['source_sha256'], case['name']
    assert previous['engine_sha256']==engine_hash, 'baseline must use the unchanged production engine'
    assert previous['output_sha256']==sha(baseline) and not previous['missing_families'], case['name']
    baselines.append((case,source,baseline,previous))
env = os.environ.copy()
env['ASS_REGRESSION_FONT_BACKEND']='windows'
env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
records = []
for case,source,baseline,previous in baselines:
    output = DEST/baseline.name
    subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),
                    '--engine',str(ROOT/'simplify_ass.py'),'--source',str(source),
                    '--fonts',str(ROOT/'fonts'),'--output',str(output)],
                   cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
    current = json.loads(output.with_suffix('.json').read_text())
    assert current['engine_sha256']==engine_hash and sha(ROOT/'simplify_ass.py')==engine_hash
    assert current['source_sha256']==sha(source)==case['sha256']
    assert current['output_sha256']==sha(output)==previous['output_sha256'], case['name']+' output changed'
    assert current['statistics']==previous['statistics'], case['name']+' statistics changed'
    assert not current['missing_families'], (case['name'],current['missing_families'])
    records.append(dict(case=case['name'],source_sha256=sha(source),output_sha256=sha(output),
                        output_bytes_identical=True,statistics_identical=True,missing_families=[],
                        wall_s=current['wall_s']))
    print(case['name'],'output bytes and statistics identical',flush=True)
assert len(records)==10
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=engine_hash,
    runner_sha256=sha(Path(__file__)),baseline=str(args.baseline.resolve()),cases=records),indent=2)+'\n')
