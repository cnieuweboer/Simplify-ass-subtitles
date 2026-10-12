"""Verify v177 Windows checks, corpus parity and render evidence."""
from pathlib import Path
import hashlib,json,py_compile
r=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();h=sha(r/'simplify_ass.py')
x=json.loads((r/'validation/complete-regression-checks.json').read_text());assert x['runtime_sha256']==h and x['requested_backend']=='windows'
assert len(x['checks'])==61 and all(a['exit_code']==0 for a in x['checks'])
for n,v in x['harness_sha256'].items():assert sha(r/n)==v,n
for name,count in [('glyph-lifecycle-checks.json',84),('word-echo-checks.json',90)]:
 a=json.loads((r/'validation'/name).read_text());assert a['runtime_sha256']==h and a['checks_passed']==count
x=json.loads((r/'validation/full-lifecycle-comparison-v177.json').read_text());assert x['runtime_sha256']==h and len(x['cases'])==9
for a in x['cases']:
 if a['case'].startswith('Attack'):assert (a['before']['output'],a['after']['output'])==(3491,354)
 else:assert a['before']==a['after']
x=json.loads((r/'validation/lifecycle-render-checks.json').read_text());assert x['runtime_sha256']==h and len(x['checks'])==12 and x['static_hold_pixel_identical']
for p in r.glob('*.py'):py_compile.compile(str(p),doraise=True)
print('v177 verified: 61 Windows scripts; 84 lifecycle checks; 9 full-corpus comparisons; 12 render samples')
