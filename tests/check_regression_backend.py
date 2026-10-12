"""Verify the selected default font backend in this process and a child."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from PIL import ImageFont, features
import json, os, subprocess, sys
import simplify_ass as s

ROOT=Path(__file__).resolve().parents[1]
backend=os.environ.get('ASS_REGRESSION_FONT_BACKEND')
assert backend in ('windows','raqm'), 'Run this check through validation/run_review_checks.py'
fonts=s.FontMetrics([ROOT/'fonts'])
face=fonts.matching_face('Nyala',False,False)
assert face is not None
width=fonts.measure(face,'Skill Bank ')
layout=fonts._loaded[face.key].layout_engine
expected=ImageFont.Layout.BASIC if backend=='windows' else ImageFont.Layout.RAQM
assert layout==expected
assert fonts.capabilities.raqm==(backend=='raqm')
assert fonts.line_ink_metrics(face,['Skill Bank ']) is not None
if backend=='windows':
    assert fonts.capabilities.harfbuzz and face.key in fonts._shaping_fonts

# A changed working directory must not lose backend setup or dependencies.
import tempfile
code='''import json,os
from PIL import ImageFont,features
import uharfbuzz
f=ImageFont.truetype(os.environ['ASS_REGRESSION_PROBE_FONT'],1024)
print(json.dumps(dict(backend=os.environ.get('ASS_REGRESSION_FONT_BACKEND'),layout=int(f.layout_engine),raqm=features.check_feature('raqm'))))'''
env=os.environ.copy();env['ASS_REGRESSION_PROBE_FONT']=face.path
with tempfile.TemporaryDirectory() as directory:
    result=subprocess.run([sys.executable,'-c',code],env=env,cwd=directory,capture_output=True,text=True,check=True)
child=json.loads(result.stdout)
assert child==dict(backend=backend,layout=int(expected),raqm=backend=='raqm')
report=dict(backend=backend,default_layout=int(layout),child=child,actual_font_measured=True,checks_passed=6)
(ROOT/'validation/regression-backend-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print('6 backend selection/inheritance checks passed:',backend)
