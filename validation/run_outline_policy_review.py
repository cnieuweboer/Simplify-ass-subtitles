"""Compare the retained caption cap with an isolated authored-width experiment.

The experimental engine is an ignored local copy, never production policy.
Every conversion uses actual fonts and hash-verified v201 corpus sources/outputs.
"""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, os, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import simplify_ass as s

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compare-authored', action='store_true')
args = parser.parse_args()
DEST = ROOT/'validation/outline-policy-corpus'
DEST.mkdir(exist_ok=True)
BASE = ROOT/'validation/inline-paint-corpus/windows'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
engine = ROOT/'simplify_ass.py'
engine_hash = sha(engine)
baseline_hash = '4a6db3f70593e8b97c26013721ad25b4549eff70e70a78444e309e72af0f78d1'
cases = json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
cases.append(dict(name='Goblin-Slayer-S01E02-track6',
    source='test-data/Goblin-Slayer-S01E02-track6-source.ass',
    sha256='476e93d4d162af152b6ddddf4f715f301bec7373e67e8645c220b8360d38d017'))
for case in cases:
    baseline = BASE/(case['name']+'.ass')
    previous = json.loads(baseline.with_suffix('.json').read_text())
    assert previous['engine_sha256'] == baseline_hash
    assert sha(ROOT/case['source']) == previous['source_sha256'] == case['sha256']
    assert sha(baseline) == previous['output_sha256'] and not previous['missing_families']

engines = [('capped', engine)]
if args.compare_authored:
    text = engine.read_text()
    expression = 'tuple(min(MAX_PROVED_CAPTION_BORDER,w) for w in widths)'
    assert text.count(expression) == 1, 'Reinspect source-proof policy before experimenting'
    candidate = DEST/'authored-experiment.py'
    candidate.write_text(text.replace(expression, 'widths'))
    engines.append(('authored-experiment', candidate))
env = os.environ.copy()
env['ASS_REGRESSION_FONT_BACKEND'] = 'windows'
env['PYTHONPATH'] = str(ROOT/'validation/backend_startup')

def convert(task):
    case, label, runtime = task
    output = DEST/label/(case['name']+'.ass')
    subprocess.run([sys.executable, str(ROOT/'validation/measure_one.py'),
        '--engine', str(runtime), '--source', str(ROOT/case['source']),
        '--fonts', str(ROOT/'fonts'), '--output', str(output)],
        cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    report = json.loads(output.with_suffix('.json').read_text())
    assert report['engine_sha256'] == sha(runtime)
    assert not report['missing_families'] and sha(ROOT/case['source']) == case['sha256']
    previous = json.loads((BASE/output.name).with_suffix('.json').read_text())
    if label == 'capped':
        assert sha(output) == previous['output_sha256'], case['name']+' capped output changed'
        assert report['statistics'] == previous['statistics'], case['name']+' capped statistics changed'
    print(case['name'], label, report['statistics']['output'], flush=True)
    return dict(case=case['name'], policy=label, engine_sha256=sha(runtime),
        source_sha256=case['sha256'], output_sha256=sha(output),
        output_bytes_identical=sha(output)==previous['output_sha256'],
        changed_statistics={k:[previous['statistics'].get(k),v]
            for k,v in report['statistics'].items() if previous['statistics'].get(k)!=v},
        missing_families=[], wall_s=report['wall_s'])

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    records = list(pool.map(convert, [(case,label,runtime) for case in cases for label,runtime in engines]))
assert sha(engine) == engine_hash
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=engine_hash,
    baseline_engine_sha256=baseline_hash, experiment=bool(args.compare_authored), cases=records), indent=2)+'\n')
