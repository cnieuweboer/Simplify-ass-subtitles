"""One-release structural parity evidence against the private v212 baseline.

This audit records this extraction, rather than imposing a permanent numerical
freeze on future font work. Behavioral checks live in tests/check_font_module.py
and the existing font/reconstruction suites.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path,
                    default=ROOT/'validation/font-extraction-assessment/simplify_ass_v212.py')
args = parser.parse_args()
baseline = args.baseline.read_bytes()
assert hashlib.sha256(baseline).hexdigest() == '40cb8760e69be3f8917e8817fc2c4aef8ccc7f73d5646858b33b806720541e0f'
old = ast.parse(baseline)
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = (ROOT/'_simplify_ass/font_metrics.py').read_text()
assert module.count('Path(__file__).resolve().parent.parent / "fonts"') == 1
normalized = ast.parse(module.replace('Path(__file__).resolve().parent.parent / "fonts"',
                                     'Path(__file__).resolve().parent / "fonts"'))
names = {'FontFace','FontCapabilities','FontLineInkMetrics','FontMetrics'}
classes = lambda tree: {n.name: ast.dump(n,include_attributes=False) for n in tree.body
                        if isinstance(n,ast.ClassDef) and n.name in names}
assert classes(old) == classes(normalized)
assert not classes(current)
def body(tree):
    return [ast.dump(n,include_attributes=False) for n in tree.body
            if not (isinstance(n,ast.ClassDef) and n.name in names)
            and not (isinstance(n,ast.ImportFrom) and n.module=='_simplify_ass.font_metrics')
            and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))]
assert body(old) == body(current), 'Unrelated engine executable code changed'
report = dict(baseline_sha256=hashlib.sha256(baseline).hexdigest(),
              runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
              classes_unchanged_except_font_root=sorted(names),
              remaining_engine_executable_ast_unchanged=True)
(ROOT/'validation/font-measurement-extraction-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('Four extracted classes match v212 except the font root; remaining engine executable AST unchanged')
