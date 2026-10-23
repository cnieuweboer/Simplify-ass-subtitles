import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import contour_independent_contract as contract
from event_evidence_test_helpers import event_comparison_fields, row_comparison_fields
#!/usr/bin/env python3
"""Compare translated-phase decisions, evidence and font calls with v123."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import inspect
import json
import statistics
import sys
import trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('translation_reference',
    ROOT/'test-data/simplify_ass-v152-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing
Style: Default,Arial,40,0,5,100,100,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def event(text,x=0,start=1,end=4,**options):
    return dict(text=text,x=x,start=start,end=end,**options)

def glyphs(text='ABCD',start=1.1,end=4,**options):
    return [event(c,100+20*i,start,end,**options) for i,c in enumerate(text)]

def cue(text='ABCD',start=1,end=4):
    return event(text,start=start,end=end,kind='Comment')

def inputs(module,descriptors):
    lines = []
    for d in descriptors:
        kind = d.get('kind','Dialogue')
        tags = (r'\an5\pos('+str(d['x'])+','+str(d.get('y',100))+')'+d.get('tags',''))
        body = d['text'] if kind=='Comment' else '{'+tags+'}'+d['text']
        lines.append(f"{kind}: 0,{module.format_time(d['start'])},{module.format_time(d['end'])},Default,,0,0,0,,{body}\n")
    document = module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events = list(document.events.values())
    visible = {e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    return events,visible

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if type(value).__name__ == "TextRow":return snapshot(row_comparison_fields(value))
    if isinstance(value,dict):
        return {key:snapshot(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return tuple(snapshot(item) for item in value)
    if isinstance(value,set):
        return frozenset(snapshot(item) for item in value)
    if hasattr(value,'__dict__'):
        return snapshot(vars(value))
    return value

class ControlledMetric:
    """Simple exact glyph geometry; record calls to verify matching/cache order."""
    def __init__(self,mode='fit'):
        self.available = mode!='unavailable'
        self.mode,self.merged,self.calls = mode,0,[]
    def authored_glyph_positions(self,state,text,origin,unit):
        self.calls.append(('positions',text,origin,unit))
        if self.mode=='reject_positions':
            return None
        return [(c,origin+20*i-10*(len(text)-1)) for i,c in enumerate(text) if not c.isspace()]
    def fragment_anchor(self,state,xs,fragments,target,unit,**options):
        self.calls.append(('anchor',tuple(xs),tuple(fragments),target,unit,options))
        if self.mode=='reject_anchor' or ''.join(fragments)!=target:
            return None
        return statistics.median(xs)
    def matches_authored_glyph_positions(self,state,xs,text,origin,unit):
        self.calls.append(('match',tuple(xs),text,origin,unit))
        expected = self.authored_glyph_positions(state,text,origin,unit)
        return expected is not None and [x for c,x in expected]==list(xs)

held = glyphs()
entrances = glyphs(start=.9,end=1.1,y=104)
translated = (glyphs(start=1,end=1.2)+
    [event('AB',125,1.2,1.4,tags=r'\fax0.1'),event('CD',165,1.2,1.4,tags=r'\fax0.1')]+
    [event(c,130+20*i,1.4,4) for i,c in enumerate('ABCD')]+[cue()])
cases = [
    ('empty',[]),('no_cue',held),('static_only',held+[cue()]),
    ('changing_entrances',entrances+held+[cue()]),
    ('missing_held_glyph',entrances+held[:3]+[cue()]),
    ('insufficient_entrances',entrances[:3]+held+[cue()]),
    ('duplicate_cue',entrances+held+[cue(),cue()]),
    ('persistent_neighbor',entrances+held+[event('X',110),cue()]),
    ('ambiguous_model',entrances+held+glyphs(y=100)+[cue()]),
    ('short_authored',entrances+held+[cue('ABC')]),
    ('zero_cue',entrances+held+[cue(end=1)]),
    ('late_unproved_tail',entrances+held+[event('A',100,4,4.2),cue()]),
    ('rotated_glyph',entrances+held+[event('X',200,tags=r'\frz20'),cue()]),
    ('clipped_glyph',entrances+held+[event('X',200,tags=r'\clip(0,0,500,500)'),cue()]),
    ('inline_layout',entrances+held+[event(r'A{\fs50}B',300),cue()]),
    ('translation',translated),
    ('translation_duplicate_cue',translated+[cue()]),
    ('translation_missing_backing',translated[:-2]+[cue()]),
    ('translation_one_seed',translated[:5]+translated[6:]),
    ('spaced_authored',entrances+held+[cue('AB CD')]),
    ('entrance_recorded_prefix',held+[event('A BCD',130,.9,1.1,y=104)]+[cue()]),
    ('transparent_entrances',glyphs(start=.9,end=1.1,tags=r'\1a&H80&')+held+[cue()]),
    ('early_held_fragment',translated+[event('A',100,.5,.8)]),
]
tracer = trace.Trace(count=True,trace=False)
checks = []
for name,descriptors in cases:
    for mode in ('none','unavailable','reject_positions','reject_anchor','fit','real'):
        results = []
        for module in (previous,current):
            events,visible = inputs(module,descriptors)
            original = deepcopy(snapshot(events))
            metric = (None if mode=='none' else module.FontMetrics([ROOT/'fonts'])
                      if mode=='real' else ControlledMetric(mode))
            result = (tracer.runfunc(module.collapse_translated_phase_rows,events,visible,metric, font_report=font_test_report(metric))
                      if module is current else module.collapse_translated_phase_rows(events,visible,metric, font_report=font_test_report(metric)))
            if module is current:
                visible.update(result.visibility_updates)
                result = (result.events,result.removed_count,result.rows)
            assert snapshot(events)==original,(name,mode,'source mutation')
            results.append(snapshot((result,visible,font_test_report(metric).rows_joined if metric is not None else 0,
                getattr(metric,'calls',[]),font_test_report(metric).missing_families if metric is not None else set(),result[0] is events)))
        assert contract(results[0]) == contract(results[1]),(name,mode)
        checks.append(dict(case=name,mode=mode,removed=result[1],rows=len(result[2])))

# The same source event can belong to differently arranged authored cues.
# Its cached index must be cue-local, and dx/travel must remain distinct keys.
events,visible = inputs(current,[event('A',100),cue()])
sample,authored = events
metric = ControlledMetric()
context = current.TranslatedPhaseContext(visible,metric,[],{'Default':[sample]},
    {e.source_index:e for e in events})
models = []
for text,center in (('ABCD',130),('DABC',110)):
    positions = row_test_call(metric, 'authored_glyph_positions', sample.state,text,0,sample.unit)
    layout = current.TranslatedCueLayout(authored,text,.75,[],sample,
        current._translated_layout_key(sample),20,100,positions)
    models.append(current.TranslatedCueModel(layout,center,[center+x for c,x in positions],
        1,current.index_fragment_spans(c for c,x in positions)))
a,b = models
assert current._translated_span_options(context,a,sample)==[(0,0)]
count = len(metric.calls)
assert current._translated_span_options(context,a,sample)==[(0,0)] and len(metric.calls)==count
assert current._translated_span_options(context,b,sample)==[(1,1)]
assert a.span_cache is not b.span_cache
assert current._translated_span_options(context,a,sample,20)==[]
assert current._translated_span_options(context,a,sample,20,True)==[(0,0)]
assert len(a.span_cache)==3 and len(b.span_cache)==1

covered = {name:False for name in (
    '_translated_layout_key','_match_touching_phase_fragments',
    '_collect_translated_motion_profiles','_prepare_translated_phases',
    '_select_translated_cue_layout','_fit_translated_cue_model',
    '_translated_span_options','_translated_held_spans','_translated_entrance_spans',
    '_covered_translated_pulses','_classify_translated_cue_phases',
    '_prove_translated_cue_coverage','_render_translated_cue_proposal',
    '_apply_translated_cue_proposals')}
import ast
owner_file = inspect.getsourcefile(current.collapse_translated_phase_rows)
tree = ast.parse(Path(owner_file).read_text())
lines = {line for (filename,line),count in tracer.results().counts.items()
         if Path(filename).resolve()==Path(owner_file).resolve() and count}
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in covered:
        covered[node.name] = any(node.lineno<=line<=node.end_lineno for line in lines)
assert all(covered.values()),covered
assert any(c['case']=='changing_entrances' and c['mode']=='fit' and c['rows']==1 for c in checks)
assert any(c['case']=='translation' and c['mode']=='fit' and c['rows']==1 for c in checks)
# Protect the shared literal-boundary contract and the independent owners.
from dataclasses import replace
from typing import get_type_hints
import subprocess, tempfile
from _simplify_ass import fragment_spans, translated_phases
contract_checks=[]
def check_contract(name,condition):
    assert condition,name
    contract_checks.append(name)
for owner in (fragment_spans,translated_phases):
    for name,value in vars(owner).items():
        if (inspect.isfunction(value) or inspect.isclass(value)) and value.__module__==owner.__name__:
            check_contract('canonical alias '+name,getattr(current,name) is value)
            get_type_hints(value)
check_contract('existing translated records retain frozen bindings',all(cls.__dataclass_params__.frozen
    for cls in (translated_phases.TranslatedPhaseContext,translated_phases.TranslatedCueLayout,
                translated_phases.TranslatedCueModel,translated_phases.TranslatedCuePhases)))
new_model=replace(a,span_cache={})
new_model.span_cache[('probe',0,False)]=[]
check_contract('cache contents do not affect model equality',new_model==a)
check_contract('replacement cache stays independent',new_model.span_cache is not a.span_cache
    and ('probe',0,False) not in a.span_cache)

def spans(fragments,target,**options):
    return list(fragment_spans.matching_fragment_spans(fragment_spans.index_fragment_spans(fragments,**options),target))
check_contract('empty fragments contain no nonempty match',spans([],'A')==[])
check_contract('empty target produces no matches',spans(['A',''],'')==[])
check_contract('complete adjacent fragments match',spans(['AB','CD'],'ABCD')==[(0,1)])
check_contract('partial initial fragment is rejected',spans(['AB','CD'],'BCD')==[])
check_contract('partial terminal fragment is rejected',spans(['AB','CD'],'ABC')==[])
check_contract('repeated occurrences remain distinct',spans(['AB','AB'],'AB')==[(0,0),(1,1)])
check_contract('overlapping complete occurrences remain eligible',spans(list('AAA'),'AA')==[(0,1),(1,2)])
check_contract('empty fragments retain all recorded boundary alternatives',
    spans(['','A','','B',''],'AB')==[(0,3),(0,4),(1,3),(1,4)])
check_contract('index construction ignores Unicode whitespace',spans([' \tA\u00a0',' B\n'],'AB')==[(0,1)])
check_contract('target normalization remains the caller choice',spans(['A','B'],'A B')==[])
check_contract('default matching remains case sensitive',spans(['A'],'a')==[])
check_contract('optional casefold preserves expanded fragment boundaries',spans(['Stra','ße'],'strasse',casefold=True)==[(0,1)])
check_contract('casefold does not silently normalize the target',spans(['Stra','ße'],'Straße',casefold=True)==[])
check_contract('combining text remains literal',spans(['a','\u0301','b'],'a\u0301')==[(0,1)])
check_contract('literal matching introduces no Unicode composition',spans(['a','\u0301'],'á')==[])
check_contract('long captions have no span length cap',spans(['A'*4096,'B'*4096],'A'*4096+'B'*4096)==[(0,1)])
source=[' A ','B'];saved=source.copy();seen=[]
def fragments_once():
    for fragment in source:
        seen.append(fragment)
        yield fragment
index=fragment_spans.index_fragment_spans(fragments_once());saved_index=deepcopy(index)
check_contract('index consumes a single-pass iterable once',seen==source)
check_contract('index construction borrows source strings',source==saved)
check_contract('matching is repeatable without changing the borrowed index',
    list(fragment_spans.matching_fragment_spans(index,'AB'))==[(0,1)]
    and list(fragment_spans.matching_fragment_spans(index,'AB'))==[(0,1)] and index==saved_index)
other=fragment_spans.index_fragment_spans(source)
check_contract('index boundary maps are independently owned',index[1] is not other[1] and index[2] is not other[2])
with tempfile.TemporaryDirectory() as directory:
    code=("import sys;sys.path.insert(0,"+repr(str(ROOT))+");"
          "from _simplify_ass import fragment_spans;"
          "assert '_simplify_ass.event_model' not in sys.modules;"
          "from _simplify_ass import translated_phases;"
          "assert not any(n.split('.')[0] in {'simplify_ass','PIL','fontTools','uharfbuzz'} for n in sys.modules)")
    subprocess.run([sys.executable,'-I','-c',code],cwd=directory,check=True)
check_contract('standalone imports need no engine or optional font backends',True)

report = dict(reference='v123',comparisons=len(checks),cache_assertions=8,
    helpers_exercised=covered,checks=checks,contract_checks=contract_checks)
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation/translated-phase-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(f"{len(checks)} translated-phase comparisons; all 14 helpers exercised; 8 cache assertions; {len(contract_checks)} boundary/module checks")
