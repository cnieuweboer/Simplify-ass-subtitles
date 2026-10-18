"""One-release v221 movement audit, not a constraint on future document policy."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/subtitle-document-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == 'c70a33315e914f1846823e39ff4bc56f586aa4036be4a675f6ee16dc990a52ca'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/subtitle_document.py').read_text())
names = {'SubtitleDocument', 'EVENT_FIELDS', 'GENERATED_MARKER', 'parse_time',
    'format_time', 'peak_concurrent_events', 'parse_dialogue', 'read_subtitle',
    'script_resolution', 'parse_subtitle_document', 'read_subtitle_document',
    '_resolve_document_state', 'mark_generated', 'render_subtitle_document',
    'write_subtitle_document', 'load_subtitle_events'}
def symbol(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None
def selected(tree):
    return {symbol(n): ast.dump(n, include_attributes=False) for n in tree.body if symbol(n) in names}
assert selected(old) == selected(module) and len(selected(module)) == 16
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if symbol(n) not in names | {'__version__'}
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.subtitle_document')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for node in module.body:
    assert (symbol(node) in names or isinstance(node, (ast.Import, ast.ImportFrom)) or
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and
            isinstance(node.value.value, str)), 'Unexpected module implementation'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]
assert imports == ['from __future__ import annotations', 'import codecs', 'import math',
    'import re', 'from dataclasses import dataclass, field, replace as dataclass_replace',
    'from pathlib import Path', 'from typing import Iterable',
    'from .event_model import Event, DocumentMeasurementContext',
    'from .ass_overrides import DEFAULT_STATE, parse_styles, resolve_event_style, evaluate_effective_state']
report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_and_constants_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, module_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('13 functions, document record and two constants unchanged; remaining engine and existing private modules unchanged except import/version.')
