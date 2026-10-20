"""One-release v233 movement audit, not a constraint on future echo policy."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
from runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'validation/frame-echo-extraction'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine', type=Path,
                    default=FOLDER/'baseline-runtime/simplify_ass.py')
args = parser.parse_args()
assert hashlib.sha256(args.baseline_engine.read_bytes()).hexdigest() == 'fa73f9764025052a0b136f042812c654beedea6a73ab2257a8ec5a73733e47e8'
old = ast.parse(args.baseline_engine.read_text())
current = ast.parse((ROOT/'simplify_ass.py').read_text())
module = ast.parse((ROOT/'_simplify_ass/frame_echoes.py').read_text())
names = {'_frame_echo_is_exit', 'FrameEchoHold', '_frame_echo_follows_motion', 'FrameEchoFamily', 'FrameEchoPaintProfile', '_profile_frame_echo', '_match_flattened_frame_echo', '_advance_flattened_frame_echo', 'collapse_frame_text_echoes', 'FrameEchoFrame', '_index_frame_echo_families', '_isolated_frame_echo_times', '_match_stacked_frame_echo', '_collapse_frame_echo_family', '_frame_echo_paint_profile', 'FrameEchoContext', '_recorded_frame_echo_motion', '_prepare_frame_echo_family', '_frame_echo_candidates', '_blocked_frame_echo_times', '_replace_frame_echo'}
def symbol(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None
def selected(tree):
    return {symbol(n): ast.dump(n, include_attributes=False) for n in tree.body if symbol(n) in names}
assert selected(old) == selected(module) and len(selected(module)) == 21
assert not selected(current)
def body(tree):
    return [ast.dump(n, include_attributes=False) for n in tree.body
        if symbol(n) not in names | {'__version__'}
        and not (isinstance(n, ast.ImportFrom) and n.module == '_simplify_ass.frame_echoes')]
assert body(old) == body(current), 'Unrelated engine behavior changed'
for node in module.body:
    assert (symbol(node) in names or isinstance(node, (ast.Import, ast.ImportFrom)) or
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and
            isinstance(node.value.value, str)), 'Unexpected module implementation'
for path in (args.baseline_engine.parent/'_simplify_ass').rglob('*.py'):
    relative = path.relative_to(args.baseline_engine.parent)
    assert path.read_bytes() == (ROOT/relative).read_bytes(), relative
imports = [ast.unparse(n) for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom))]


report = dict(baseline_runtime_manifest=runtime_manifest(args.baseline_engine),
    runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),
    moved_definitions_ast_identical=sorted(names),
    remaining_engine_ast_identical_except_import_and_version=True,
    existing_private_modules_byte_identical=True, module_imports=imports)
FOLDER.mkdir(parents=True, exist_ok=True)
(FOLDER/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
print('Sixteen frame-echo functions and five frozen records unchanged; remaining engine and existing private modules unchanged except import/version.')
