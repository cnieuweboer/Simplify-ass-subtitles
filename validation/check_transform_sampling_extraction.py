"""One-release structural parity audit for the v218 sampling extraction.

This bounds v218's movement against v217, rather than freezing future algorithms.
Behavioral contracts live in the current sampling, continuation and consumer checks.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/transform-sampling-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == '95cf3d022042ad6d6a96866a5d57e7f0dfce2d4d33477f7c5f4bbf4cd1f83523'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/transform_sampling.py').read_text())
names = {'font_size_transform_needs_replay', 'transform_weight', 'interpolate_transform_value',
         '_commit_transform_continuation', 'sample_transform_state', 'sample_transform_states'}
def selected(tree):
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in names}
assert selected(old) == selected(module) and len(selected(module)) == 6
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if not (isinstance(n, ast.FunctionDef) and n.name in names)
        and not (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id == '__version__')
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.transform_sampling')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]
assert imports == ['from __future__ import annotations', 'import math', 'import re', 'from typing import Iterable',
                   'from .ass_overrides import OverrideContinuation, OverrideEvaluation, apply_font_size, apply_override']
report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, sampling_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Six definitions unchanged; remaining engine and existing private modules unchanged except import/version.')
