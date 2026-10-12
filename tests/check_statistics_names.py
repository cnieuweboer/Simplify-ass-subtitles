#!/usr/bin/env python3
"""Check report migration, canonical precedence and fresh CLI statistics."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import simplify_ass as s

ROOT = Path(__file__).resolve().parents[1]
checks = []
def ok(name,value):
    assert value,name
    checks.append(name)

old = {'prototype_scrolling_events_removed':12,
       'prototype_scrolling_concurrency_limit':4,
       'prototype_scrolling_blocks_removed':1,
       'prototype_scrolling_peak_after_reduction':5,
       'aggressive_copies':7,'original':30,'output':18}
expected = {'scrolling_events_dropped':12,'scrolling_concurrency_limit':4,
            'scrolling_blocks_dropped':1,'scrolling_peak_after_reduction':5,
            'stacked_text_copies_flattened':7,'original':30,'output':18}
ok('older counters convert to one canonical set',s.canonicalize_statistics(old)==expected)
ok('migration does not mutate the input report','scrolling_events_dropped' not in old)
ok('current report migration is idempotent',s.canonicalize_statistics(expected)==expected)
ok('mixed report counters are not added together',s.canonicalize_statistics(
   {**old,'scrolling_events_dropped':3})['scrolling_events_dropped']==3)
ok('current zero overrides a positive legacy count',s.text_drop_warnings(
   {**old,'scrolling_events_dropped':0})==[])
ok('current and older warning payloads agree',s.text_drop_warnings(old)==s.text_drop_warnings(expected))
ok('unrecognized future counters remain available',s.canonicalize_statistics({'future_counter':9})=={'future_counter':9})
for old_key,new_key in s.LEGACY_STAT_KEYS.items():
    ok(old_key+' has one unambiguous successor',s.canonicalize_statistics({old_key:11,new_key:2})=={new_key:2})

with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    source=directory/'input.ass'
    source.write_bytes((ROOT/'test-data/Overlord-22m06-source.ass').read_bytes())
    report=directory/'stats.json'
    result=subprocess.run([sys.executable,str(ROOT/'simplify_ass.py'),str(source),
       '--fonts-dir',str(ROOT/'fonts'),'--stats-json',str(report)],capture_output=True,text=True)
    ok('normal CLI conversion succeeds',result.returncode==0)
    data=json.loads(report.read_text())['tracks'][0]['stats']
    ok('fresh JSON reports contain no old aliases',not set(data)&set(s.LEGACY_STAT_KEYS))
    ok('fresh JSON contains drawing and scrolling counters',
       {'drawing_candidates','scrolling_events_dropped','supporting_shapes_retained'}<=set(data))
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation/statistics-naming-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(f'{len(checks)} statistics-naming checks passed')
