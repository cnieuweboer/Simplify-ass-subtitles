import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import contour_independent_contract as contract
from event_evidence_test_helpers import event_comparison_fields, row_comparison_fields
#!/usr/bin/env python3
"""Compare covered-fragment decisions and caller-owned evidence with v154."""
from copy import deepcopy
from pathlib import Path
import ast
import contextlib
import importlib.util
import json
import math
import sys
import tempfile
import trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current, historical_fade_timing=True)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('covered_reference',
    ROOT/'test-data/simplify_ass-v154-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
# Keep historical pass behavior while correcting its known hexadecimal suffix bug.
from outline_color_test_helpers import install_hex_parenthesis_reference_parser
install_hex_parenthesis_reference_parser(previous)
HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing, Outline, Shadow
Style: Default,Arial,40,0,5,100,100,0,2,0
Style: Highlight,Arial,40,0,5,100,100,0,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
SHADOW = r'\1a&HFF&\3a&HFF&\4a&H00&\shad2'

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if type(value).__name__ == "TextRow":return snapshot(row_comparison_fields(value))
    if isinstance(value,float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value,dict):
        return {key:snapshot(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):
        return tuple(snapshot(item) for item in value)
    if isinstance(value,set):
        return frozenset(snapshot(item) for item in value)
    if hasattr(value,'__dict__'):
        return snapshot(vars(value))
    return value

def record(module,text,x=100,start=2,end=3,layer=2,tags='',style='Default',name=''):
    return (f'Dialogue: {layer},{module.format_time(start)},{module.format_time(end)},'
        f'{style},{name},0,0,0,,'+r'{\an5\pos('+str(x)+',100)'+tags+'}'+text+'\n')

def inputs(module,case,animation,sources_enabled):
    parts = [record(module,c,100+20*i,1,5,0,tags=case.get('piece_tags',''))
             for i,c in enumerate('ABCD')]
    for d in case.get('copies',[]):
        parts.append(record(module,**d))
    for start,end in case.get('cues',[]):
        parts.append(f'Comment: 0,{module.format_time(start)},{module.format_time(end)},Default,,0,0,0,,ABCD\n')
    document = module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(parts)))
    original = list(document.events.values())
    pieces = [(e,c,module.get_pos(e.text)) for e,c in zip(original[:4],'ABCD')]
    base = module.replace_event(original[0],text=module.render_simplified_caption(
        original[0].state,'ABCD',pos=(130,100)),layer=str(case.get('base_layer',0)))
    if case.get('caption_tags'):
        base = module.replace_event(base,text=base.text.replace('}',case['caption_tags']+'}',1))
    if case.get('nonfinite'):
        base = module.dataclass_replace(base,end_s=math.inf)
    row = module.TextRow(base,pieces,virtual=case.get('virtual',False),
        phase_core=case.get('phase_core'))
    rows = [] if case.get('no_rows') else [row]
    if case.get('duplicate_row'):
        duplicate = module.TextRow(module.dataclass_replace(base,source_index=100000),pieces.copy())
        rows.append(duplicate)
    events = [base]+original[4:]
    visible = {e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    animated = ({e.source_index for e in original[:4]} if animation=='row' else
                {e.source_index for e in original if e.kind=='Dialogue'} if animation=='all' else set())
    sources = {e.source_index:deepcopy(e) for e in original} if sources_enabled else None
    if sources is not None and case.get('shadow_sources'):
        for index,e in list(sources.items()):
            if e.kind!='Dialogue':
                continue
            source_tags = SHADOW+case.get('source_fade',r'\fad(200,300)')
            if case.get('bad_last_fade') and index==original[3].source_index:
                source_tags = SHADOW+r'\fad(invalid,300)'
            sources[index] = module.replace_event(e,text=e.text.replace('}',source_tags+'}',1))
    return events,visible,rows,animated,sources

cases = [
    dict(name='empty_evidence',no_rows=True),
    dict(name='row_only'),
    dict(name='held_letter',copies=[dict(text='A',layer=0)]),
    dict(name='held_letter_displaced',copies=[dict(text='A',x=101,layer=0)]),
    dict(name='held_letter_longer',copies=[dict(text='A',start=.9,end=5.1,layer=0)]),
    dict(name='held_different_paint',copies=[dict(text='A',layer=0,tags=r'\1c&H123456&')]),
    dict(name='caption_paint_mismatch',caption_tags=r'\1c&H123456&',copies=[dict(text='A',layer=0)]),
    dict(name='base_layer_mismatch',base_layer=1,copies=[dict(text='A',layer=0)]),
    dict(name='nested_highlight',copies=[dict(text='B',x=120)]),
    dict(name='independent_static_label',copies=[dict(text='B',x=120)]),
    dict(name='same_layer_highlight',copies=[dict(text='B',x=120,layer=0)]),
    dict(name='wrong_actor',copies=[dict(text='B',x=120,name='other')]),
    dict(name='cross_style_highlight',copies=[dict(text='B',x=120,style='Highlight')]),
    dict(name='cross_style_multiletter',copies=[dict(text='BC',x=130,style='Highlight')]),
    dict(name='casefold_shadow',copies=[dict(text='bc',x=130,tags=SHADOW)]),
    dict(name='virtual_shadow',virtual=True,copies=[dict(text='bc',x=130,tags=SHADOW)]),
    dict(name='virtual_foreground',virtual=True,copies=[dict(text='B',x=120)]),
    dict(name='long_shadow_span',copies=[dict(text='BCD',x=140,tags=SHADOW)]),
    dict(name='shadow_time_edge',copies=[dict(text='BC',x=130,start=.85,end=5.15,tags=SHADOW)]),
    dict(name='shadow_past_time_edge',copies=[dict(text='BC',x=130,start=.84,end=5.16,tags=SHADOW)]),
    dict(name='shadow_beyond_baseline',copies=[dict(text='BC',x=130,tags=SHADOW+r'\frz20')]),
    dict(name='shadow_clipped',copies=[dict(text='BC',x=130,tags=SHADOW+r'\clip(0,0,500,500)')]),
    dict(name='inline_layout',copies=[dict(text=r'B{\fs50}C',x=130)]),
    dict(name='unmatched_text',copies=[dict(text='XYZ',x=130,tags=SHADOW)]),
    dict(name='mixed_copies',copies=[dict(text='A',layer=0),dict(text='B',x=120),
        dict(text='bc',x=130,tags=SHADOW),dict(text='XYZ',x=130)]),
    dict(name='authored_shadow_core',shadow_sources=True,cues=[(1.5,4.5)],copies=[dict(text='BC',x=130)]),
    dict(name='shared_fade_core',shadow_sources=True,copies=[dict(text='BC',x=130)]),
    dict(name='invalid_fade_core',shadow_sources=True,bad_last_fade=True),
    dict(name='zero_fade_core',shadow_sources=True,source_fade=r'\fad(0,300)'),
    dict(name='too_long_fade_core',shadow_sources=True,source_fade=r'\fad(3000,3000)'),
    dict(name='ambiguous_authored_core',shadow_sources=True,cues=[(1.5,4.5),(1.6,4.4)]),
    dict(name='existing_core',shadow_sources=True,cues=[(1.5,4.5)],phase_core=(1.4,4.6)),
    dict(name='duplicate_shadow_owner',shadow_sources=True,duplicate_row=True,copies=[dict(text='BC',x=130)]),
    dict(name='casefold_font',copies=[dict(text='bc',x=130,tags=SHADOW+r'\fnARIAL')]),
    dict(name='nonfinite_row_index',nonfinite=True,copies=[dict(text='BC',x=130,tags=SHADOW)]),
]
tracer = trace.Trace(count=True,trace=False)
checks = []
for case in cases:
    for animation in ('none','row','all'):
        for sources_enabled in (False,True):
            for measured in (False,True):
                results = []
                for module in (previous,current):
                    events,visible,rows,animated,sources = inputs(module,case,animation,sources_enabled)
                    before = snapshot((events,visible,animated,sources))
                    before_rows = snapshot(rows)
                    metric = module.FontMetrics([ROOT/'fonts']) if measured else None
                    args = (events,visible,rows,animated,sources,metric)
                    result = (tracer.runfunc(module.remove_covered_fragment_effects,*args)
                              if module is current else module.remove_covered_fragment_effects(*args))
                    assert before==snapshot((events,visible,animated,sources)),(case['name'],'input mutation')
                    if module is current:
                        assert before_rows==snapshot(rows),(case['name'],'row input mutation')
                        rows_out=result.rows
                        semantic_result=(result.events,result.removed_effects)
                    else:
                        rows_out=rows
                        semantic_result=result
                    results.append(snapshot((semantic_result,rows_out,font_test_report(metric).rows_joined if metric is not None else 0,
                        font_test_report(metric).missing_families if metric is not None else set())))
                assert results[0]==results[1],(case['name'],animation,sources_enabled,measured)
                checks.append(dict(case=case['name'],animation=animation,sources=sources_enabled,
                    measured=measured,removed=result.removed_effects,cores=[r.phase_core for r in result.rows]))

assert any(c['case']=='held_letter' and c['animation']=='row' and c['removed']==1 for c in checks)
assert any(c['case']=='virtual_shadow' and c['removed']==1 for c in checks)
assert any(c['case']=='authored_shadow_core' and c['cores']==[(1.5,4.5)] for c in checks)
assert any(c['case']=='shared_fade_core' and c['cores']==[(1.2,4.7)] for c in checks)
assert all(c['cores']==[None] for c in checks if c['case']=='invalid_fade_core')
assert all(c['cores']==[(1.4,4.6)] for c in checks if c['case']=='existing_core')

# Cache ownership: source IDs can repeat across different pass invocations.
case=dict(name='cache',copies=[dict(text='bc',x=130,tags=SHADOW)])
events,visible,rows,animated,sources=inputs(current,case,'all',True)
a=current._prepare_covered_fragments(visible,rows,animated,sources,None)
b=current._prepare_covered_fragments(visible,rows,animated,sources,None)
base=rows[0].base
assert list(current._covered_fragment_spans(a,base,'bc',False))==[]
assert list(current._covered_fragment_spans(a,base,'bc',True))==[(1,2)]
assert len(a.span_indexes)==2 and not b.span_indexes
assert a.shadow_sources is not b.shadow_sources and a.shadow_poses is not b.shadow_poses
first=a.span_indexes.copy()
assert list(current._covered_fragment_spans(a,base,'BC',False))==[(1,2)]
assert a.span_indexes==first

# Exercise target-pass evidence during two real conversions, including the
# existing entrance/exit proofs and font measurements.
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[]; original=module.remove_covered_fragment_effects
        def wrapped(*args,**kwargs):
            before=snapshot((args[:5],kwargs))
            result=(tracer.runfunc(original,*args,**kwargs) if module is current else original(*args,**kwargs))
            if module is current:
                assert before==snapshot((args[:5],kwargs)),(fixture,'input mutation')
                after_args=(*args[:2],result.rows,*args[3:5])
                semantic_result=(result.events,result.removed_effects)
            else:
                after_args=args[:5]
                semantic_result=result
            captured.append(snapshot((before,semantic_result,after_args,kwargs)))
            return result
        module.remove_covered_fragment_effects=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass'
                metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=module.simplify_ass(ROOT/'test-data'/fixture,output,
                        module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
                compared.append((snapshot(captured),output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:
            module.remove_covered_fragment_effects=original
    assert contract(compared[0]) == contract(compared[1]),fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),contour_independent_contract_identical=True))

audit=json.loads((ROOT/'validation/covered-fragment-helper-list.json').read_text())
helper_names=set(audit['helpers'])
lines={line for (filename,line),count in tracer.results().counts.items()
       if Path(filename).resolve()==Path(current.__file__).resolve() and count}
covered={}
for node in ast.parse(Path(current.__file__).read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in helper_names:
        statement_lines={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt)
                         and not isinstance(n,ast.FunctionDef) and n.lineno>node.lineno+1}
        covered[node.name]=dict(exercised=any(node.lineno<=line<=node.end_lineno for line in lines),
            statement_lines=len(statement_lines),executed_statement_lines=len(statement_lines&lines),
            unexecuted_lines=sorted(statement_lines-lines))
assert all(item['exercised'] for item in covered.values()),covered
report=dict(reference='v154',comparisons=len(checks),cache_assertions=6,
    focused_conversions=focused,helper_coverage=covered,checks=checks)
(ROOT/'validation/covered-fragment-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(f"{len(checks)} covered-fragment comparisons; 6 cache assertions; 2 focused conversions; all 15 helpers exercised")
