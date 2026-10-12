import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare backed pulse decisions, call order and input ownership with v123."""
from pathlib import Path
from copy import deepcopy
import ast
import contextlib
import importlib.util
import json
import math
import random
import sys
import tempfile
import trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pulse_reference',
    ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing, Outline, Shadow
Style: Default,Arial,40,0,5,100,100,0,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
RETURN=r'\1c&H0000FF&\fscx150\fscy150\t(0,200,\1c&HFFFFFF&\fscx100\fscy100)'

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {key:snapshot(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return tuple(snapshot(item) for item in value)
    if isinstance(value,set):return frozenset(snapshot(item) for item in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def event(word='A',x=100,start=1,end=4,layer=1,tags='',**options):
    return dict(word=word,x=x,y=100,start=start,end=end,layer=layer,tags=tags,**options)

def row(times=(1.1,1.2,1.3,1.4),words='ABCD',xs=(100,140,180,220)):
    result=[]
    for word,x,t in zip(words,xs,times):
        result.extend((event(word,x,layer=0,tags=r'\1a&H80&'),event(word,x),
            event(word,x,start=t,end=t+.2,layer=2,tags=RETURN)))
    return result

def changed(descriptors,which,**changes):
    result=deepcopy(descriptors)
    for i,d in enumerate(result):
        if which(i,d):d.update(changes)
    return result

def inputs(module,descriptors,order):
    lines=[]
    for d in descriptors:
        pos='' if d.get('unpositioned') else f"\\pos({d['x']},{d['y']})"
        tags=r'\an5'+pos+d['tags']
        lines.append(f"Dialogue: {d['layer']},{module.format_time(d['start'])},"
            f"{module.format_time(d['end'])},Default,{d.get('name','')},0,0,0,,{{{tags}}}{d['word']}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values())
    words={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    positions={e.source_index:module.get_pos(e.text) for e in events}
    for e,d in zip(events,descriptors):
        if 'position' in d:positions[e.source_index]=d['position']
        if d.get('empty_state'):e.state={}
    if order=='reversed':events.reverse()
    if order=='shuffled':random.Random(117).shuffle(events)
    return events,words,positions

def call(module,events,words,positions,tracer):
    calls=[];originals={}
    for name in ('event_override_tokens','parse_effect_transform','render_simplified_caption'):
        original=getattr(module,name);originals[name]=original
        def wrapped(*args,_name=name,_original=original,**kwargs):
            calls.append((_name,snapshot((args,kwargs))))
            return _original(*args,**kwargs)
        setattr(module,name,wrapped)
    try:
        result=(tracer.runfunc(module.collapse_backed_glyph_pulses,events,words,positions)
            if module is current else module.collapse_backed_glyph_pulses(events,words,positions))
        return result,calls
    finally:
        for name,original in originals.items():setattr(module,name,original)

base=row();cases=[('empty',[]),('valid',base),
    ('no_backing',[d for d in base if d['layer']!=0]),
    ('no_pulses',[d for d in base if d['layer']!=2]),
    ('three_pulses',[d for d in base if not(d['word']=='D' and d['layer']==2)]),
    ('two_pulses',[d for d in base if not(d['word'] in 'CD' and d['layer']==2)]),
    ('reverse_activation',row((1.4,1.3,1.2,1.1))),
    ('scrambled_activation',row((1.1,1.3,1.2,1.4))),
    ('simultaneous_activation',row((1.1,)*4)),
    ('missing_backing',[d for d in base if not(d['word']=='D' and d['layer']==0)]),
    ('duplicate_backing',base+[deepcopy(base[0])]),
    ('duplicate_positions',row(xs=(100,100,180,220))),
    ('ambiguous_glyph',row(words='AABC',xs=(100,103,180,220))),
    ('competing_label',base+[event('E',160)]),
    ('distant_label',base+[event('E',500)]),
    ('brief_neighbor',base+[event('E',160,start=2,end=2.01)]),
    ('duplicate_top_hold',base+[deepcopy(base[1])]),
    ('empty_state',changed(base,lambda i,d:True,empty_state=True)),
    ('missing_position',changed(base,lambda i,d:d['word']=='A',position=None)),
    ('nan_position',changed(base,lambda i,d:d['word']=='A',position=(math.nan,100))),
    ('infinite_position',changed(base,lambda i,d:d['word']=='A',position=(math.inf,100))),
]
for name,tags in (
    ('transparent_foreground',r'\1a&H01&'+RETURN),
    ('transparent_backing',r'\1a&HFF&'),('opaque_backing',r'\1a&H00&'),
    ('moving',r'\move(100,100,110,100)'),('rotation',r'\frz5'),
    ('disallowed_transform',r'\t(0,200,\frz5)'),
    ('cycle',r'\1c&H0000FF&\t(0,100,\1c&H000000&)\t(100,200,\1c&HFFFFFF&)'),
    ('separate_components',r'\1c&H0000FF&\fscx150\fscy150\t(0,200,\1c&HFFFFFF&)\t(0,200,\fscx100\fscy100)'),
    ('negative_transformed_size',r'\t(0,100,\fscx-100)\t(100,200,\fscx100)'),
    ('zero_transformed_size',r'\t(0,100,\fscx0)\t(100,200,\fscx100)'),
    ('large_return',RETURN.replace('150','1000')),
    ('invalid_fade',r'\fad(0,-1)'),('duplicate_fade',r'\fad(0,0)\fad(0,0)'),
    ('unparsable_fade',r'\fad(no,0)'),('long_fade',r'\fade(0,255,0,0,1,2,3)'),
    ('shadow',r'\shad1'),('clip',r'\clip(0,0,200,200)'),
    ('invalid_size',r'\fs0'),('inline_layout',r'\fs40')
):
    layer=0 if name.endswith('backing') else 2
    cases.append((name,changed(base,lambda i,d:d['layer']==layer,tags=tags)))
cases.append(('invalid_layer',changed(base,lambda i,d:True,layer='nonnumeric')))
cases.append(('short_backing',changed(base,lambda i,d:d['layer']==0,end=1.2)))
cases.append(('no_common_hold',[d for d in base if d['layer']!=1]))
cases.append(('short_hold',changed(base,lambda i,d:d['layer']==1,end=1.01)))
cases.append(('missing_coverage',changed(base,lambda i,d:d['layer']==1,end=3.5)))
cases.append(('competing_pose',base+[event(word,x,layer=3,tags=r'\1c&HFF0000&')
    for word,x in zip('ABCD',(100,140,180,220))]))
cases.append(('brief_other_pose',base+[event(word,x,start=2,end=2.05,layer=3,tags=r'\1c&HFF0000&')
    for word,x in zip('ABCD',(100,140,180,220))]))
for gap in (0,.03):
    descriptors=[]
    for d in base:
        if d['layer']==0:
            descriptors.extend((dict(d,end=2),dict(d,start=2+gap)))
        else:descriptors.append(d)
    cases.append(('split_backing' if gap==0 else 'gapped_backing',descriptors))
for name,colours,sizes,duration in (
    ('converging_frames',('000000','888888','CCCCCC'),(180,140,110),.05),
    ('diverging_frames',('888888','000000','CCCCCC'),(140,180,110),.05),
    ('long_frame',('000000',),(180,),.12),
    ('outline_frames',('000000','888888','CCCCCC'),(180,140,110),.05),
    ('clipped_frames',('000000','BFBFBF'),(180,130),.05),
    ('clipped_small_return',('000000','222222'),(180,170),.05),
    ('single_clipped_frame',('000000',),(180,),.05),
):
    descriptors=[d for d in base if d['layer']!=2]
    for i,(word,x) in enumerate(zip('ABCD',(100,140,180,220))):
        start=4-duration*len(colours) if 'clipped' in name else 1.1+.2*i
        for j,(colour,size) in enumerate(zip(colours,sizes)):
            tags=f'\\1c&H{colour}&\\fscx{size}\\fscy{size}'
            if name=='outline_frames':tags+=r'\3c&HFFFFFF&'
            descriptors.append(event(word,x,start=start+j*duration,end=start+(j+1)*duration,layer=2,tags=tags))
    cases.append((name,descriptors))
tails=[]
for word,x in zip('ABCD',(100,140,180,220)):
    for layer,alpha in ((0,'80'),(1,'00')):
        tails.append(event(word,x,start=4,end=4.4,layer=layer,
            tags=r'\1a&H'+alpha+r'&\fad(0,400)\t(0,400,\1a&HFF&)'))
cases.extend((('complete_exit',base+tails),
    ('different_exit_end',base+changed(tails,lambda i,d:i==0,end=4.41)),
    ('missing_exit_foreground',base+tails[:-1]),
    ('exit_gap',base+changed(tails,lambda i,d:True,start=4.01)),
    ('final_fading_foreground',base+[event(word,x,start=3.8,end=4,layer=2,
        tags=r'\fad(0,200)\t(0,200,\1a&HFF&)') for word,x in zip('ABCD',(100,140,180,220))]),
    ('competing_proposals',base+[dict(d,layer=-1) for d in base if d['layer']==0]),
))

tracer=trace.Trace(count=True,trace=False);checks=[]
for name,descriptors in cases:
    for order in ('original','reversed','shuffled'):
        compared=[]
        for module in (previous,current):
            events,words,positions=inputs(module,descriptors,order)
            before=deepcopy(snapshot((events,words,positions)))
            result,calls=call(module,events,words,positions,tracer)
            assert before==snapshot((events,words,positions)),(name,order,'input mutation')
            compared.append(snapshot((result,calls,result[0] is events)))
        assert compared[0]==compared[1],(name,order)
        checks.append(dict(case=name,order=order,removed=result[1],
            same_list=result[0] is events,end_times=[e.end_s for e in result[0]]))
by_name={c['case']:c for c in checks if c['order']=='original'}
for name in ('valid','reverse_activation','simultaneous_activation','separate_components',
    'large_return','converging_frames','clipped_frames','final_fading_foreground'):
    assert by_name[name]['removed']>0,(name,by_name[name])
assert by_name['valid']['removed']==8
for name in ('two_pulses','scrambled_activation','duplicate_positions','ambiguous_glyph',
    'competing_label','duplicate_top_hold','cycle','negative_transformed_size',
    'zero_transformed_size','missing_coverage','competing_pose','diverging_frames',
    'long_frame','outline_frames','clipped_small_return','single_clipped_frame','competing_proposals'):
    assert by_name[name]['removed']==0,(name,by_name[name])
assert by_name['complete_exit']['removed']==16
assert by_name['complete_exit']['end_times']==[4.4]*4
assert by_name['different_exit_end']['removed']==8
assert all(c['same_list'] for c in checks if c['removed']==0)

focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.collapse_backed_glyph_pulses
        def wrapped(events,words,positions):
            before=snapshot((events,words,positions))
            result=(tracer.runfunc(original,events,words,positions)
                if module is current else original(events,words,positions))
            captured.append(snapshot((before,result,events,words,positions)))
            return result
        module.collapse_backed_glyph_pulses=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=module.simplify_ass(ROOT/'test-data'/fixture,output,
                        module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((snapshot(captured),output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:module.collapse_backed_glyph_pulses=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

helpers={entry['helper'] for entry in json.loads(
    (ROOT/'validation/backed-pulse-extraction-blocks.json').read_text())}
executed={line for (filename,line),count in tracer.results().counts.items()
    if Path(filename).resolve()==Path(current.__file__).resolve() and count}
coverage={}
for node in ast.parse(Path(current.__file__).read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in helpers:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt)
            and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and
            isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),
            statement_lines=len(statements),executed_statement_lines=len(statements&executed),
            unexecuted_lines=sorted(statements-executed))
assert len(coverage)==16 and all(c['exercised'] for c in coverage.values()),coverage
(ROOT/'validation/backed-pulse-checks.json').write_text(json.dumps(dict(
    reference='v123',comparisons=len(checks),validation_and_render_calls_identical=True,
    focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(f'{len(checks)} backed-pulse comparisons; checking/render calls identical; 2 focused conversions; all 16 helpers exercised')
