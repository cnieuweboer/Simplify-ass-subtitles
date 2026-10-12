"""AST normalization limited to the row extraction's ownership/API changes."""
import ast, copy, inspect
from font_geometry_test_helpers import ROW_NAMES

def normalized_row_algorithm(node):
    class Normalize(ast.NodeTransformer):
        def visit_FunctionDef(self,n):
            n=self.generic_visit(n)
            if n.body and isinstance(n.body[0],ast.Expr) and isinstance(n.body[0].value,ast.Constant) and isinstance(n.body[0].value.value,str):n.body[0].value.value=inspect.cleandoc(n.body[0].value.value)
            n.name=next(old for old,new in ROW_NAMES.items() if new==n.name)
            n.args.args[0]=ast.arg(arg='self')
            pairs=[(a,d) for a,d in zip(n.args.kwonlyargs,n.args.kw_defaults) if a.arg!='font_report']
            n.args.kwonlyargs=[a for a,d in pairs];n.args.kw_defaults=[d for a,d in pairs]
            return n
        def visit_Attribute(self,n):
            n=self.generic_visit(n)
            if isinstance(n.value,ast.Name) and n.value.id=='metrics':
                n.value=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr='metrics',ctx=ast.Load())
                if n.attr=='available':n.value=ast.Name(id='self',ctx=ast.Load())
            return n
        def visit_Call(self,n):
            n=self.generic_visit(n)
            n.keywords=[k for k in n.keywords if k.arg!='font_report']
            if isinstance(n.func,ast.Name) and n.func.id in ROW_NAMES.values():
                old=next(old for old,new in ROW_NAMES.items() if new==n.func.id)
                assert isinstance(n.args[0],ast.Name) and n.args[0].id=='metrics'
                n.args=n.args[1:];n.func=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr=old,ctx=ast.Load())
            return n
        def visit_If(self,n):
            n=self.generic_visit(n)
            if ast.unparse(n.test)=='font_report is not None':
                assert len(n.body)==1 and isinstance(n.body[0],ast.Expr)
                expression=n.body[0]
                assert ast.unparse(expression.value.func)=='font_report.missing_families.add'
                expression.value.func=ast.parse('self.missing.add').body[0].value
                return expression
            return n
    return Normalize().visit(copy.deepcopy(node))


def normalized_font_caller(node, *, reference):
    """Normalize explicit resource wiring, never numeric or admission logic."""
    class Normalize(ast.NodeTransformer):
        def visit_FunctionDef(self,n):
            self.function=n.name
            n=self.generic_visit(n)
            if not reference:
                pairs=[(a,d) for a,d in zip(n.args.kwonlyargs,n.args.kw_defaults)
                    if a.arg not in {'font_report','outline_matcher'}]
                n.args.kwonlyargs=[a for a,d in pairs];n.args.kw_defaults=[d for a,d in pairs]
            return n
        def visit_arg(self,n):
            n=self.generic_visit(n)
            if reference and n.arg=='font_spacing':n.arg='font_metrics'
            return n
        def visit_keyword(self,n):
            n=self.generic_visit(n)
            if reference and n.arg=='font_spacing':n.arg='font_metrics'
            return n
        def visit_Name(self,n):
            if reference and n.id=='FontSpacing':n.id='FontMetrics'
            if reference and n.id=='font_spacing':n.id='font_metrics'
            return n
        def visit_Attribute(self,n):
            n=self.generic_visit(n)
            if reference:
                if n.attr=='font_spacing':n.attr='font_metrics'
                if n.attr=='metrics' and ast.unparse(n.value) in {'metric','context.metric'}:return n.value
                if n.attr=='outline_matcher' and ast.unparse(n.value)=='metric':return ast.Name(id='outline_matcher',ctx=ast.Load())
            elif getattr(self,'function',None)=='main' and ast.unparse(n.value)=='font_report':
                if n.attr in {'rows_joined','missing_families'}:
                    return ast.Attribute(value=ast.Name(id='metric',ctx=ast.Load()),
                        attr={'rows_joined':'merged','missing_families':'missing'}[n.attr],ctx=n.ctx)
            return n
        def visit_Call(self,n):
            # Keep the receiver before rewriting its attribute expression.
            row_method=n.func.attr if reference and isinstance(n.func,ast.Attribute) and n.func.attr in ROW_NAMES else None
            if row_method:
                owner=self.visit(n.func.value)
                n.args=[owner]+[self.visit(a) for a in n.args]
                n.keywords=[self.visit(k) for k in n.keywords]
                n.func=ast.Name(id=ROW_NAMES[row_method],ctx=ast.Load())
                return n
            n=self.generic_visit(n)
            if not reference:n.keywords=[k for k in n.keywords if k.arg not in {'font_report','outline_matcher'}]
            elif getattr(self,'function',None)=='main' and isinstance(n.func,ast.Name) and n.func.id=='FontMetrics' and any(k.arg=='metrics' for k in n.keywords):
                return next(k.value for k in n.keywords if k.arg=='metrics')
            return n
        def visit_IfExp(self,n):
            n=self.generic_visit(n)
            if reference and isinstance(n.orelse,ast.Constant) and n.orelse.value is None:
                body=ast.unparse(n.body)
                if body in {'font_metrics.metrics','context.metric'}:
                    return ast.Name(id='font_metrics',ctx=ast.Load()) if body=='font_metrics.metrics' else n.body
            return n
        def visit_Assign(self,n):
            n=self.generic_visit(n)
            if reference and getattr(self,'function',None)=='simplify_ass' and ast.unparse(n) in {'font_metrics = font_metrics.metrics','font_metrics = font_metrics'}:return None
            if not reference and getattr(self,'function',None)=='main' and any(isinstance(t,ast.Name) and t.id in {'font_report','outline_matcher'} for t in n.targets):return None
            return n
        def visit_AnnAssign(self,n):
            if not reference and isinstance(n.target,ast.Name) and n.target.id=='font_report':return None
            return self.generic_visit(n)
        def visit_If(self,n):
            if not reference:
                test=ast.unparse(n.test)
                if test.startswith('outline_matcher is None') or test.startswith('outline_matcher is not None'):
                    # The only new behavior is catalog-identity validation;
                    # default matcher construction replaces the removed owner.
                    assert self.function in {'simplify_ass','_simplify_text_and_vectors','recover_vector_text_cues','infer_vector_text_cues'}
                    return None
                if test=='context.font_report is not None':
                    assert len(n.body)==1 and not n.orelse
                    statement=n.body[0]
                    if isinstance(statement,ast.AugAssign):
                        assert ast.unparse(statement.target)=='context.font_report.rows_joined'
                        owner='context.font_metrics' if self.function in {'_reconstruct_shared_glyph_rows','_join_text_row'} else 'context.metric'
                        statement.target=ast.parse(owner+'.merged').body[0].value
                        statement.target.ctx=ast.Store()
                        return statement
                    assert isinstance(statement,ast.Expr) and ast.unparse(statement.value.func)=='context.font_report.missing_families.add'
                    statement.value.func=ast.parse('context.metric.missing.add').body[0].value
                    return statement
            return self.generic_visit(n)
        def visit_Expr(self,n):
            if isinstance(n.value,ast.Constant) and isinstance(n.value.value,str):return None
            return self.generic_visit(n)
    return Normalize().visit(copy.deepcopy(node))
