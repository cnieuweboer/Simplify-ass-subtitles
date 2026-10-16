"""One-release AST/source parity, not a permanent freeze on outline algorithms."""
from pathlib import Path
import argparse,ast,json
ROOT=Path(__file__).resolve().parents[1]
from runtime_manifest import runtime_manifest
folder=ROOT/'validation/font-outline-extraction'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-engine',type=Path,default=folder/'baseline-runtime/simplify_ass.py')
args=parser.parse_args()
base=args.baseline_engine.resolve().parent
assert args.baseline_engine.name=='simplify_ass.py'
assert runtime_manifest(args.baseline_engine)=={
 '_simplify_ass/__init__.py':'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '_simplify_ass/font_metrics.py':'76e92a49b13bba905ccbb97135fd9c5226866d8076083beef03d5bb96cdf6a54',
 'simplify_ass.py':'c04faf4d5d9d8ce497d9b7c54e6e13310ada8b545b400e41fb7f912364171f81',
}, 'Restore the exact pre-extraction v214 runtime for this bounded audit'
old=ast.parse((base/'simplify_ass.py').read_text());now=ast.parse((ROOT/'simplify_ass.py').read_text())
module=ast.parse((ROOT/'_simplify_ass/font_outlines.py').read_text())
names={'FontOutlineMatcher','fit_cubic_points'}
def definitions(tree):
 return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names}
assert definitions(old)==definitions(module) and not definitions(now)
def body(tree):
 return [ast.dump(n,include_attributes=False) for n in tree.body
         if not (isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names)
         and not (isinstance(n,ast.ImportFrom) and n.module=='_simplify_ass.font_outlines')
         and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))]
assert body(old)==body(now),'Unrelated engine executable code changed'
for name in ['__init__.py','font_metrics.py']:
 assert (base/'_simplify_ass'/name).read_bytes()==(ROOT/'_simplify_ass'/name).read_bytes()
imports=[ast.unparse(n) for n in module.body if isinstance(n,(ast.Import,ast.ImportFrom))]
assert imports==['from __future__ import annotations','import math','import statistics','from .font_metrics import FontMetrics']
report=dict(baseline_runtime_manifest=runtime_manifest(base/'simplify_ass.py'),runtime_manifest=runtime_manifest(ROOT/'simplify_ass.py'),moved_definitions_ast_identical=sorted(names),remaining_engine_ast_identical_except_import_and_version=True,existing_private_sources_byte_identical=True,outline_module_imports=imports)
(folder/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('Outline matcher and fitter AST-identical; only engine import/version wiring changed; no reverse imports.')
