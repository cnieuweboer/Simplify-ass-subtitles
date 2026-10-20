"""One-release v232 movement audit, not a constraint on future scrolling policy."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/effect-validation-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == 'ae10a25edee1ecb8a4c7fd40a5762c1036405903119c61a618a9094a11783b02'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/effect_validation.py').read_text())
operations = ast.parse((ROOT/'_simplify_ass/event_operations.py').read_text())
names = {'parse_effect_transform', 'parse_effect_move', 'event_override_tokens'}
def symbol(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None
def selected(tree):
    return {symbol(n): ast.dump(n, include_attributes=False) for n in tree.body if symbol(n) in names}
assert selected(old) == {**selected(module), **selected(operations)} and len(selected(old)) == 3
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if symbol(n) not in names | {'__version__'}
        and not (isinstance(n, ast.ImportFrom) and (n.module == '_simplify_ass.effect_validation' or n.module == '_simplify_ass.event_operations' and [a.name for a in n.names] == ['event_override_tokens']))]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for node in module.body:
    assert (symbol(node) in names or isinstance(node, (ast.Import, ast.ImportFrom)) or
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and
            isinstance(node.value.value, str)), 'Unexpected module implementation'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    if path.name != 'event_operations.py':
        assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
old_operations = ast.parse((args.baseline_engine.parent/'_simplify_ass/event_operations.py').read_text())
remaining = ast.parse((ROOT/'_simplify_ass/event_operations.py').read_text())
remaining.body = [n for n in remaining.body if symbol(n) != 'event_override_tokens']
for node in remaining.body:
    if isinstance(node, ast.ImportFrom) and node.module == 'ass_overrides':
        node.names = [alias for alias in node.names if alias.name != 'tokenize_override']
assert ast.dump(old_operations) == ast.dump(remaining), 'Unrelated event operations changed'
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]


report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    event_operations_unchanged_except_reader_and_canonical_tokenizer_import=True,
    other_private_modules_byte_identical=True, module_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Three source-effect helpers unchanged; remaining engine unchanged except imports/version; event operations gains only the raw reader and canonical tokenizer import; other private modules unchanged.')
