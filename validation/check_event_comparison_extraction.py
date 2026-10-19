"""One-release v230 movement audit; not a constraint on future comparison policy."""
from pathlib import Path
import argparse
import ast
import copy
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/event-comparison-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == 'bb479c4a8cc666a3fe56aa7cd7ed101d40cd5bfb29cce31ede27a59d2f3af50c'
groups = {'caption_geometry': {'text_height', 'placement_key', 'text_layout_key', 'compatible_text_layout'},
          'event_operations': {'state_key'}}
names = set().union(*groups.values())
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())


def selected(tree, subset):
    return {n.name: ast.dump(n) for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in subset}


def normalize(tree, *, owner=None):
    body = []
    for original in tree.body:
        node = copy.deepcopy(original)
        if isinstance(node, ast.FunctionDef) and node.name in names:
            continue
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__'
                                                for t in node.targets):
            continue
        if isinstance(node, ast.ImportFrom):
            if owner == 'caption_geometry' and node.module == 'ass_overrides':
                node.names = [a for a in node.names if a.name != 'DEFAULT_STATE']
            if node.module in {'_simplify_ass.'+g for g in groups}:
                node.names = [a for a in node.names if a.name not in names]
        body.append(ast.dump(node))
    return body


assert len(selected(old, names)) == 5 and not selected(current, names)
assert normalize(old) == normalize(current), 'Unrelated engine implementation changed'
for owner, subset in groups.items():
    relative = Path('_simplify_ass')/(owner+'.py')
    before = ast.parse((args.baseline_engine.parent/relative).read_text())
    after = ast.parse((ROOT/relative).read_text())
    assert selected(old, subset) == selected(after, subset)
    assert normalize(before, owner=owner) == normalize(after, owner=owner)
    expected_imports = copy.deepcopy([n for n in before.body if isinstance(n, (ast.Import, ast.ImportFrom))])
    if owner == 'caption_geometry':
        override_import = next(n for n in expected_imports if isinstance(n, ast.ImportFrom)
                               and n.module == 'ass_overrides')
        override_import.names.insert(0, ast.alias(name='DEFAULT_STATE'))
    assert [ast.dump(n) for n in expected_imports] == [ast.dump(n) for n in after.body
                                            if isinstance(n, (ast.Import, ast.ImportFrom))]
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    if path.stem not in groups:
        assert path.read_bytes() == (ROOT/path.relative_to(args.baseline_engine.parent)).read_bytes()
report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical={k: sorted(v) for k, v in groups.items()},
    remaining_engine_ast_identical_except_imports_and_version=True,
    existing_owner_implementation_ast_identical=True, other_private_sources_byte_identical=True,
    added_dependency='caption_geometry.DEFAULT_STATE')
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Five comparison helpers unchanged; remaining engine and owners unchanged except aliases, version and canonical default-state import.')
