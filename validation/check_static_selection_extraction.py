"""One-release movement audit for v220, not a constraint on future selection policy."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/static-selection-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == 'b43b72657ee00e6c5a5d1a44b744dfa427133d680e6655b77adc5e8e3011d9a7'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/static_selection.py').read_text())
names = {'StaticStateContext', 'StaticStateEvidence', 'StaticStateSamples',
    'StaticPoseEvidence', 'StaticStateSelection', 'select_static_state',
    'unrotated_text_state', 'upright_text_state', 'upright_transform_pose',
    '_prepare_static_state_evidence', '_static_state_geometry_is_settled',
    '_vote_static_state_holds', '_record_static_opaque_span',
    '_sample_static_state_intervals', '_choose_static_state_geometry',
    '_static_state_has_rotation', '_apply_static_upright_fallback',
    '_protect_sustained_static_geometry', '_static_state_colour_spans',
    '_vote_static_state_colours', '_apply_static_state_colour_vote'}
def selected(tree):
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names}
assert selected(old) == selected(module) and len(selected(module)) == 21
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if not (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names)
        and not (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id == '__version__')
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.static_selection')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]
assert imports == ['from __future__ import annotations', 'import math', 'import re',
    'from dataclasses import dataclass, field', 'from typing import Iterable',
    'from .event_model import Event',
    'from .ass_overrides import OverrideEvaluation, OverrideContinuation, apply_override',
    'from .transform_sampling import sample_transform_state, sample_transform_states']
report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, module_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('21 definitions/decorators unchanged; remaining engine and existing private modules unchanged except import/version.')
