"""Fresh v181/v182 comparisons using identical restored fonts and sources."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'validation/lyric-layer-corpus/windows'
DEST.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
env = os.environ.copy()
env['ASS_REGRESSION_FONT_BACKEND'] = 'windows'
env['PYTHONPATH'] = str(ROOT / 'validation/backend_startup')
engines = {'v181': ROOT / 'tests/references/simplify_ass_v181.py',
           'current': ROOT / 'simplify_ass.py'}
records = []
for case in json.loads((ROOT / 'test-data/corpus-manifest.json').read_text()):
    source = ROOT / case['source']
    assert sha(source) == case['sha256']
    outputs, reports = {}, {}
    for label, engine in engines.items():
        output = DEST / (case['name'] + '-' + label + '.ass')
        subprocess.run([sys.executable, str(ROOT / 'validation/measure_one.py'),
                        '--engine', str(engine), '--source', str(source),
                        '--fonts', str(ROOT / 'fonts'), '--output', str(output)],
                       cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
        outputs[label] = output
        reports[label] = json.loads(output.with_suffix('.json').read_text())
        assert reports[label]['missing_families'] == [], ('Missing exact fonts; stop', case['name'], reports[label]['missing_families'])
    old, new = reports['v181']['statistics'], reports['current']['statistics']
    different = {k: (old.get(k), new.get(k)) for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
    record = dict(case=case['name'], source_sha256=sha(source),
                  output_identical=outputs['v181'].read_bytes() == outputs['current'].read_bytes(),
                  statistics_differences=different, missing_fonts=[],
                  hashes={label: sha(path) for label, path in outputs.items()})
    records.append(record)
    (DEST / 'summary.json').write_text(json.dumps(dict(
        runtime_sha256=sha(engines['current']), reference_sha256=sha(engines['v181']),
        completed=len(records), fresh_baselines=True, cases=records), indent=2) + '\n')
    assert record['output_identical'] and not different, record
    print(case['name'], 'fresh output/statistics identical; no missing fonts', flush=True)
print('9 complete v181/current corpus comparisons passed', flush=True)
