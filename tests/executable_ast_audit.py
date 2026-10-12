"""Test-only executable AST comparison, excluding documentation strings.

String literals used as values remain significant. Only the leading docstring
of a module, class or function is omitted; version handling belongs to the test.
"""
import ast
from copy import deepcopy


class _WithoutDocstrings(ast.NodeTransformer):
    def _body(self, node):
        self.generic_visit(node)
        if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant) and
                isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:]
        return node

    visit_Module = _body
    visit_ClassDef = _body
    visit_FunctionDef = _body
    visit_AsyncFunctionDef = _body


def executable_ast(node):
    """Return a private tree with documentation-only statements removed."""
    return _WithoutDocstrings().visit(deepcopy(node))
