"""One-release structural parity evidence for the v216 interpreter extraction.

This audit is bounded to this release, not a permanent freeze on parser changes.
Behavioral contracts live in the continuation and module tests.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
    default=ROOT/'validation/override-module-extraction/baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == 'a4319191ab65a378ce37f51f714b125dcaa50842f5cdf7331324c63079fb7545'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/ass_overrides.py').read_text())
names = {'OverrideContinuation','OverrideEvaluation','tokenize_override','resolve_event_style',
         'parse_styles','apply_font_size','apply_override','evaluate_effective_state','effective_state'}
constants = {'OVERRIDE_RE','TAG_NAMES','TAG_RE','NUMBER','DEFAULT_STATE','STYLE_TAGS'}
def node_name(node):
    if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None

def definitions(tree, selected):
    return {node_name(n): ast.dump(n, include_attributes=False) for n in tree.body if node_name(n) in selected}
assert definitions(old,names)==definitions(module,names) and not definitions(current,names)
assert definitions(old,constants-{'TAG_NAMES'})==definitions(module,constants-{'TAG_NAMES'})
def body(tree):
    return [ast.dump(n,include_attributes=False) for n in tree.body
            if node_name(n) not in names|constants|{'__version__'}
            and not (isinstance(n,ast.ImportFrom) and n.module=='_simplify_ass.ass_overrides')]
assert body(old)==body(current), 'Unrelated engine code or output policy changed'
for file in (args.baseline_engine.parent/'_simplify_ass').glob('*.py'):
    assert file.read_bytes()==(ROOT/'_simplify_ass'/file.name).read_bytes()
imports = [ast.unparse(n) for n in module.body if isinstance(n,(ast.Import,ast.ImportFrom))]
assert imports == ['from __future__ import annotations','from dataclasses import dataclass','import re','from typing import Iterable']
# Evaluate only the frozen grammar/policy declarations, without importing two
# different runtime packages into the same process.
ns = {}
for n in old.body:
    if node_name(n) in {'SAFE_SIMPLE_TAGS','TAG_NAMES'}:
        exec(compile(ast.Module(body=[n],type_ignores=[]),'<baseline vocabulary>','exec'),ns)
old_names = ns['TAG_NAMES']
ns2 = {}
for n in module.body:
    if node_name(n)=='TAG_NAMES':
        exec(compile(ast.Module(body=[n],type_ignores=[]),'<new vocabulary>','exec'),ns2)
new_names = ns2['TAG_NAMES']
assert len(old_names)==len(new_names)==51 and set(old_names)==set(new_names)
assert all(len(a)>=len(b) for a,b in zip(new_names,new_names[1:]))
assert ns['SAFE_SIMPLE_TAGS']<=set(new_names)
assert not any(isinstance(n,ast.Name) and n.id=='SAFE_SIMPLE_TAGS' for n in ast.walk(module))
report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical=sorted(names),unchanged_constants=sorted(constants-{'TAG_NAMES'}),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True,recognized_names_identical=sorted(new_names),
    output_whitelist_unchanged=True,interpreter_imports=imports)
output=ROOT/'validation/override-module-extraction/audit.json'
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2)+'\n')
print('Nine definitions and five constants identical; all 51 recognized tags retained; output policy and remaining engine unchanged.')
