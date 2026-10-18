"""One-release v223 movement audit, not a constraint on future freezing policy."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/text-freezing-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == '65cb74afed35482e8df444d6b0d38f4c4f8169d9b0a405f7fcc323664776f637'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/text_freezing.py').read_text())
names = {'FrozenBlock', 'SAFE_SIMPLE_TAGS', 'safe_override', 'simplify_text',
         '_freeze_inputs', 'freeze_block', 'simplify_visual_text'}
def symbol(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None
def selected(tree):
    return {symbol(n): ast.dump(n, include_attributes=False) for n in tree.body if symbol(n) in names}
assert selected(old) == selected(module) and len(selected(module)) == 7
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if symbol(n) not in names | {'__version__'}
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.text_freezing')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for node in module.body:
    assert (symbol(node) in names or isinstance(node, (ast.Import, ast.ImportFrom)) or
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and
            isinstance(node.value.value, str)), 'Unexpected module implementation'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]
assert imports == ['from __future__ import annotations', 'import re', 'from dataclasses import dataclass', 'from typing import Iterable', 'from .ass_overrides import DEFAULT_STATE, NUMBER, OVERRIDE_RE, OverrideContinuation, OverrideEvaluation, apply_override, resolve_event_style, tokenize_override', 'from .static_selection import StaticPoseEvidence, StaticStateSelection, select_static_state', 'from .caption_rendering import render_tag']

report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_and_constants_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, module_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Five functions, frozen result and whitelist unchanged; remaining engine and existing private modules unchanged except import/version.')
