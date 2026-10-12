from pathlib import Path
import contextlib
import hashlib
import json
import sys
import time

root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import simplify_ass as s

source = root.parent/'twintails-verification/Reincarnated as a Sword - S01E01_track6_[eng].ass'
output = root/'outputs/Sword-S01E01-track6.ass'
output.parent.mkdir(exist_ok=True)
before = hashlib.sha256(source.read_bytes()).hexdigest()
metric = s.FontMetrics([root.parent/'expanded-tests-v107/fonts'])
font_report = s.FontProcessingReport()
outline_matcher = s.FontOutlineMatcher(metric)
started = time.perf_counter()
with (root/'validation/sword-track6.log').open('w') as log, contextlib.redirect_stdout(log):
    statistics = s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metric, font_report=font_report,outline_matcher=outline_matcher)
old = root.parent/'release169-work'
reference = json.loads((old/'validation/sword-track6.json').read_text())
report = {'version':s.__version__,'seconds':time.perf_counter()-started,
    'engine_sha256':hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest(),
    'output_identical_to_v169':output.read_bytes()==(old/'outputs/Sword-S01E01-track6.ass').read_bytes(),
    'statistics_identical_to_v169':statistics==reference['statistics'],
    'source_unchanged':before==hashlib.sha256(source.read_bytes()).hexdigest(),
    'statistics':statistics}
(root/'validation/sword-track6.json').write_text(json.dumps(report,indent=2)+'\n')
assert all(report[key] for key in ('statistics_identical_to_v169','source_unchanged'))
# Paint differences are proved separately against the parser-corrected reference.
print('Sword track6: statistics identical to v169; source unchanged; outline-only comparison in check_full_outline_sweeps.py')
