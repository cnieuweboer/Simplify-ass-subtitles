"""One-release v224 movement audit, not a constraint on future geometry policy."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/caption-geometry-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == '0e02b5ee8f9295bc96f927a241e862c6ddb63c50a86319dc9689c5d8c3f3ddc4'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/caption_geometry.py').read_text())
names = {'NUM', 'POS_RE', 'get_pos', 'set_pos', 'inline_layout_key', 'caption_bounds'}
def symbol(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None
def selected(tree):
    return {symbol(n): ast.dump(n, include_attributes=False) for n in tree.body if symbol(n) in names}
assert selected(old) == selected(module) and len(selected(module)) == 6
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if symbol(n) not in names | {'__version__'}
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.caption_geometry')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for node in module.body:
    assert (symbol(node) in names or isinstance(node, (ast.Import, ast.ImportFrom)) or
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and
            isinstance(node.value.value, str)), 'Unexpected module implementation'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]
assert imports == ['from __future__ import annotations', 'import math', 'import re', 'from .ass_overrides import OVERRIDE_RE', 'from .event_model import Event', 'from .font_metrics import FontMetrics']

report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_and_constants_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, module_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Four functions and position patterns unchanged; remaining engine and existing private modules unchanged except import/version.')
