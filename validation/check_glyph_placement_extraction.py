"""One-release structural parity audit for the v217 placement extraction.

This bounds v217's movement against v216, rather than freezing future algorithms.
Behavioral contracts live in the current placement, font and row checks.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/glyph-placement-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == 'd23c1883b2c698f7326b2721c2e29372c169038ef8f806f3931664cc7bb8c499'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/glyph_placement.py').read_text())
names = {'fit_fragment_anchor', 'authored_glyph_positions', 'matches_authored_glyph_positions'}
def selected(tree):
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in names}
assert selected(old) == selected(module) and len(selected(module)) == 3
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if not (isinstance(n, ast.FunctionDef) and n.name in names)
        and not (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id == '__version__')
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.glyph_placement')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]
assert imports == ['from __future__ import annotations', 'import unicodedata',
                   'from .font_metrics import FontMetrics']
report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, placement_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Three definitions unchanged; remaining engine and existing private modules unchanged except import/version.')
