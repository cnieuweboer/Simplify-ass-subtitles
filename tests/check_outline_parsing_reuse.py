"""Validate pass-local parsing reuse against the immutable v171 implementation."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch
from override_module_test_helpers import patch_interpreter_bindings
import ast, hashlib, importlib.util, json, sys
import simplify_ass as s
from executable_ast_audit import executable_ast

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('outline_reference',ROOT/'test-data/simplify_ass-v171-reference.py')
old = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = old
spec.loader.exec_module(old)
checks = []
def check(name, value):
    assert value, name
    checks.append(name)

# Token reuse must preserve the canonical ordered parser, including continuation.
texts = [r'{\rOther\fs\anbogus}{\an7\q2}literal{\r\fs+2}',
         r'{\rMissing\fs\i}{\rOther\b\fs+2}A',
         r'{\a999\an9}{\an1}B', r'{\rOther}{\fs\q}C',
         r'{\3c&H1300FE&)}A', r'{\r}{\an7}A', 'plain', '',
         r'{\t(0,100,\3c&HFF0000&)\clip(0,0,100,100)}A']
for index,text in enumerate(texts):
    for empty_default in (False, True):
        default = {} if empty_default else {**s.DEFAULT_STATE,'fn':'Base','fs':25}
        styles = {'Default':{**s.DEFAULT_STATE,'fn':'Fallback'},
                  'Other':{**s.DEFAULT_STATE,'fn':'Other','fs':42,'q':1}}
        before = deepcopy((default,styles))
        tokens = tuple(token for block in s.OVERRIDE_RE.findall(text) for token in s.tokenize_override(block))
        expected = old.evaluate_effective_state(text,default,styles)
        with patch_interpreter_bindings(s,'tokenize_override',side_effect=AssertionError('reparsed stream')):
            actual = s.evaluate_effective_state(text,default,styles,tokens=iter(tokens))
        check(f'formatting parity {index}/{empty_default}',actual.formatting==expected.formatting)
        check(f'continuation parity {index}/{empty_default}',
              (actual.continuation.reset_style,actual.continuation.alignment_set)==
              (expected.continuation.reset_style,expected.continuation.alignment_set))
        check(f'borrowed defaults/styles {index}/{empty_default}',(default,styles)==before)

# The optional payload only removes tokenization: all strict validation remains.
values = [r'(\3c&HFF0000&)',r'(1,\blur2)',r'(0,500,\3c&HFF0000&)',
          r'(0,500,2,\blur2)',r'(500,0,\blur2)',r'(0,0,\blur2)',
          r'(0,1200,\blur2)',r'(0,500,-1,\blur2)',r'(nan,500,\blur2)',
          r'(0,inf,\blur2)',r'(0,500,\fs90)',r'(0,500,\t(0,1,\blur2))',
          '(0,500)',r'(0,500,1,2,\blur2)',r'(bad,\blur2)',r'(\unknown2)',
          r'(0,500,\3c&H1300FE&))',r'(0,500,\blur2\bord3)']
for value in values:
    for instant in (False,True):
        for after in (False,True):
            changes = s.tokenize_override('\\'+value[1:-1].partition('\\')[2])
            before = changes.copy()
            kwargs = dict(allow_instant=instant,allow_after_end=after)
            expected = old.parse_effect_transform(value,1,{'3c','blur','bord'},**kwargs)
            with patch_interpreter_bindings(s,'tokenize_override',side_effect=AssertionError('reparsed payload')):
                actual = s.parse_effect_transform(value,1,{'3c','blur','bord'},parsed_changes=changes,**kwargs)
            check(f'transform parity {value}/{instant}/{after}',actual==expected)
            check(f'borrowed changes {value}/{instant}/{after}',changes==before)

fixture = ROOT/'test-data/Sword-S01E02-ending-sweep-source.ass'
document = s._resolve_document_state(s.read_subtitle_document(fixture))
metric = s.FontMetrics([ROOT/'fonts'])
events = list(document.events.values())
visible = MappingProxyType({e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events})
group = [e for e in events if s.get_pos(e.text)==(680.07,82.2)]
chosen = next(e for e in group if e.layer=='1')
context = s.StackedTextContext({},[],{},set(),set(),MappingProxyType(document.events),metric)
before = deepcopy(events)
with patch.object(s,'event_override_tokens',wraps=s.event_override_tokens) as parse:
    evidence = s._collect_outline_strip_evidence(chosen,group,context)
    profile = s._profile_outline_strip_sweep(chosen,evidence,context)
    first = parse.call_count
    again = s._profile_outline_strip_sweep(chosen,evidence,context)
    check('second proof reuses all original token streams',parse.call_count==first)
    parsed_ids = [id(call.args[0]) for call in parse.call_args_list]
    check('each original source parsed only once',len(parsed_ids)==len(set(parsed_ids)))
check('repeated sweep profile identical',profile==again)
check('borrowed source event state/history unchanged',events==before)
check('proof records animation without rescanning',evidence.animated)
check('static paint still rejects transformed evidence',s._representative_static_strip_outline(chosen,evidence) is None)
source,rect,state = evidence.strips[0]
tokens = evidence.tokens_for(source)
replacement = replace(source,text=source.text+r'{\3c&H000000&}')
check('same-index replacement gets fresh tokens',evidence.tokens_for(replacement)!=tokens)
check('replacement retains independent identity',replacement.source_index==source.source_index and id(replacement)!=id(source))
check('cache retains exact source object',evidence.source_tokens[id(source)][0] is source)
fresh = s._collect_outline_strip_evidence(chosen,group,context)
check('next family owns a fresh cache',fresh.source_tokens is not evidence.source_tokens and id(replacement) not in fresh.source_tokens)
with patch_interpreter_bindings(s,'tokenize_override',wraps=s.tokenize_override) as tokenize:
    actual = s._profile_outline_strip_transition(source,state,tokens=tokens)
check('each transform payload parsed once',tokenize.call_count==sum(name=='t' for name,value in tokens))
check('transition equals old proof',actual==old._profile_outline_strip_transition(source,state))

# Production sources can be unresolved: reusing tokens must still resolve defaults.
unresolved = MappingProxyType({i:replace(e,state={},continuation=s.OverrideContinuation()) for i,e in document.events.items()})
ctx = replace(context,source_events=unresolved)
borrowed = deepcopy(list(unresolved.values()))
with patch.object(s,'event_override_tokens',wraps=s.event_override_tokens) as parse:
    unresolved_evidence = s._collect_outline_strip_evidence(chosen,group,ctx)
check('unresolved source initial paint matches resolved proof',
      [(rect,state) for source,rect,state in unresolved_evidence.strips]==
      [(rect,state) for source,rect,state in evidence.strips])
check('unresolved sources remain unresolved and borrowed',list(unresolved.values())==borrowed)
check('unresolved source streams parsed only once',parse.call_count==len(unresolved_evidence.strips))

old_metric = old.FontMetrics([ROOT/'fonts'])
for label,source_path in [('karaoke',fixture),('static',ROOT/'test-data/Sword-S01E02-ending-outline-source.ass')]:
    a = old._resolve_document_state(old.read_subtitle_document(source_path))
    b = s._resolve_document_state(s.read_subtitle_document(source_path))
    av = {i:old.OVERRIDE_RE.sub('',e.text) for i,e in a.events.items()}
    bv = {i:s.OVERRIDE_RE.sub('',e.text) for i,e in b.events.items()}
    expected,count_a = old.flatten_stacked_text_copies(list(a.events.values()),av,set(a.events),source_events=a.events,font_metrics=old_metric)
    actual,count_b = s.flatten_stacked_text_copies(list(b.events.values()),MappingProxyType(bv),set(b.events),source_events=MappingProxyType(b.events),font_metrics=metric)
    check(label+' complete pass output parity',[e.fields() for e in actual]==[e.fields() for e in expected])
    check(label+' reduction count parity',count_a==count_b)

def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a = definitions(ROOT/'test-data/simplify_ass-v171-reference.py')
# Audit the frozen v172 optimization; current semantic checks above still run
# against the live engine. v173's ink change has its own bounded audit.
b = definitions(ROOT/'test-data/simplify_ass-v172-reference.py')
changed = {name for name in a if ast.dump(a[name])!=ast.dump(b[name])}
allowed = {'OutlineStripEvidence','evaluate_effective_state',
           '_collect_outline_strip_evidence','_representative_static_strip_outline',
           '_profile_outline_strip_transition','_profile_outline_strip_sweep',
           '_render_stacked_text_caption','parse_effect_transform'}
check('bounded production changes exactly declared',changed==allowed and a.keys()==b.keys())
check('malformed color tolerance unchanged',ast.dump(a['apply_override'])==ast.dump(b['apply_override']))
report = dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),
              checks_passed=len(checks),checks=checks,changed_definitions=sorted(changed),new_definitions=[],
              sources_parsed_once=True,transform_payloads_parsed_once=True)
(ROOT/'validation/outline-parsing-reuse-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'outline parsing reuse/parity/ownership checks passed')
