"""One-release structural parity audit for the v219 event-record extraction.

This bounds v219's movement against v218, rather than freezing future algorithms.
Behavioral contracts live in the current event, context and ownership checks.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/event-model-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == '1d34c8649382163d2c0c5b0212db39af0f270e92a25775fdc20c6d4f90c0c3f9'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/event_model.py').read_text())
names = {'Event', 'EventEvidence', 'DocumentMeasurementContext'}
def selected(tree):
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name in names}
assert selected(old) == selected(module) and len(selected(module)) == 3
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if not (isinstance(n, ast.ClassDef) and n.name in names)
        and not (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id == '__version__')
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.event_model')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]
assert imports == ['from __future__ import annotations', 'from dataclasses import dataclass, field',
                   'from .ass_overrides import OverrideContinuation']
report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, model_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Three record definitions/decorators unchanged; remaining engine and existing private modules unchanged except import/version.')
