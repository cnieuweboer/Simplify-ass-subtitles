"""Verify v168 changes documentation and release identity, not executable policy."""
import test_paths  # Resolve the repository for direct test execution.
import ast
import hashlib
import json
from pathlib import Path
from executable_ast_audit import executable_ast

ROOT = Path(__file__).resolve().parents[1]
# Documentation-only provenance belongs to the frozen release, not later fixes.
current = ROOT/'test-data/simplify_ass-v168-reference.py'
reference = ROOT/'test-data/simplify_ass-v167-reference.py'


def executable(path):
    tree = executable_ast(ast.parse(path.read_text()))
    versions = [n for n in tree.body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets)]
    assert len(versions) == 1
    versions[0].value = ast.Constant('release identity')
    return ast.dump(tree, include_attributes=False)


assert executable(current) == executable(reference), 'Executable source changed'
report = dict(version='2026.10.11.168', reference_version='2026.10.11.167',
              runtime_sha256=hashlib.sha256(current.read_bytes()).hexdigest(),
              executable_ast_identical_excluding_docstrings_and_version=True)
(ROOT/'validation/documentation-only-checks.json').write_text(json.dumps(report, indent=2)+'\n')
print('Complete executable AST identical to v167 excluding docstrings and version')
