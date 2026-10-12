from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare movement-chain decisions, source ownership and caption calls with v148."""
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

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('moving_reference',
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
FADE=r'\t(0,200,\1a&HFF&\3a&HFF&)'

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {key:snapshot(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return tuple(snapshot(item) for item in value)
    if isinstance(value,set):return frozenset(snapshot(item) for item in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

class RecordingMetric:
    def __init__(self,engine,mode):self.engine,self.mode,self.calls=engine,mode,[]
    @property
    def available(self):return self.mode!='unavailable' and self.engine.available
    def fragment_anchor(self,*args,**kwargs):
        self.calls.append(snapshot((args,kwargs)))
        if self.mode=='failed_anchor':return None
        return row_test_call(self.engine, 'fragment_anchor', *args,**kwargs)

def event(word='ABCD',start=1,end=2,x=300,y=100,tags='',movement=None,**options):
    return dict(word=word,start=start,end=end,x=x,y=y,tags=tags,movement=movement,**options)

def sequence(word='ABCD',tags='',phases=((2,3),),name=''):
    return [event(word,tags=tags,name=name)]+[
        event(word,start=start,end=end,tags=tags,name=name,movement=(350,100,300,100))
        for start,end in phases]+[event(word,start=phases[-1][1],end=5,tags=tags,name=name)]

def change(descriptors,which,**changes):
    result=deepcopy(descriptors)
    for i,d in enumerate(result):
        if which(i,d):d.update(changes)
    return result

def body(d,retained=False):
    if d['movement'] is None:pose=f"\\pos({d['x']},{d['y']})"
    elif isinstance(d['movement'],str):pose=r'\move'+d['movement']
    else:pose=r'\move('+','.join(str(v) for v in d['movement'])+')'
    if retained and d.get('frozen_move'):pose=f"\\pos({d['x']},{d['y']})"
    tags=d['tags']+(d.get('current_tags','') if retained else '')
    return '{'+r'\an5'+pose+tags+'}'+d['word']

def inputs(module,descriptors,order):
    lines=[]
    for d in descriptors:
        lines.append(f"{d.get('kind','Dialogue')}: {d.get('layer',0)},{module.format_time(d['start'])},"
            f"{module.format_time(d['end'])},Default,{d.get('name','')},0,0,0,,{body(d)}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    source_events={};events=[]
    for e,d in zip(doc.events.values(),descriptors):
        if not d.get('current_only'):source_events[e.source_index]=e
        if d.get('source_only'):continue
        retained=module.replace_event(e,text=body(d,True))
        if 'current_end' in d:
            retained=module.replace_event(retained,end=module.format_time(d['current_end']),end_s=d['current_end'])
        if 'current_start' in d:
            retained=module.replace_event(retained,start=module.format_time(d['current_start']),start_s=d['current_start'])
        events.append(retained)
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    if order=='reversed':
        events.reverse();source_events=dict(reversed(list(source_events.items())))
    if order=='shuffled':
        random.Random(119).shuffle(events)
        items=list(source_events.items());random.Random(119).shuffle(items);source_events=dict(items)
    return events,visible,source_events

def call(module,events,visible,sources,metric,tracer):
    calls=[];originals={}
    for name in ('event_override_tokens','effective_state','parse_effect_move',
                 'parse_effect_transform','literal_font_spans','render_simplified_caption'):
        original=getattr(module,name);originals[name]=original
        def wrapped(*args,_name=name,_original=original,**kwargs):
            calls.append((_name,snapshot((args,kwargs))))
            return _original(*args,**kwargs)
        setattr(module,name,wrapped)
    try:
        result=(tracer.runfunc(module.collapse_moving_glyph_sequences,events,visible,sources,metric)
            if module is current else module.collapse_moving_glyph_sequences(events,visible,sources,metric))
        return result,calls
    finally:
        for name,original in originals.items():setattr(module,name,original)

base=sequence();cases=[('empty',[]),('whole_fragment',base),
    ('no_movement',[base[0],base[-1]]),('missing_parent',base[1:]),
    ('missing_terminal',base[:-1]),('unretained_parent',change(base,lambda i,d:i==0,source_only=True)),
    ('unretained_terminal',change(base,lambda i,d:i==2,source_only=True)),
    ('parent_gap',change(base,lambda i,d:i==0,end=1.99)),
    ('terminal_gap',change(base,lambda i,d:i==2,start=3.01)),
    ('wrong_parent_anchor',change(base,lambda i,d:i==0,x=301)),
    ('wrong_terminal_anchor',change(base,lambda i,d:i==2,x=301)),
    ('terminal_wrong_paint',change(base,lambda i,d:i==2,tags=r'\1c&H0000FF&')),
    ('duplicate_parent',base+[deepcopy(base[0])]),
    ('duplicate_terminal',base+[deepcopy(base[2])]),
    ('duplicate_retained_parent',base+[dict(base[0],current_only=True)]),
    ('opaque_parent_preferred',base+[dict(base[0],current_only=True,current_tags=r'\1a&H80&')]),
    ('dim_retained_terminal',change(base,lambda i,d:i==2,current_tags=r'\1a&H80&\3a&H80&')),
    ('dim_retained_parent',change(base,lambda i,d:i==0,current_tags=r'\1a&H80&\3a&H80&')),
    ('clear_outline_axes',change(base,lambda i,d:i==2,current_tags=r'\xbord3\ybord4')),
    ('parent_current_starts_late',change(base,lambda i,d:i==0,current_start=1.01)),
    ('terminal_current_ends_early',change(base,lambda i,d:i==2,current_end=4.99)),
    ('two_moves',sequence(phases=((2,2.5),(2.5,3)))),
    ('three_moves',sequence(phases=((2,2.3),(2.3,2.6),(2.6,3)))),
    ('chain_gap',sequence(phases=((2,2.5),(2.51,3)))),
    ('ambiguous_following',sequence(phases=((2,2.5),(2.5,3)))+
        [event(start=2.5,end=3.2,movement=(400,100,300,100))]),
    ('whitespace_text',sequence('AB CD')),('combining_text',sequence('A\u0301BCD')),
    ('rtl_text',sequence('\u05d0\u05d1\u05d2\u05d3')),
    ('same_font_switch',sequence(r'AB{\fnArial}CD')),
    ('literal_font_switch',sequence(r'AB{\fnArial Narrow}CD')),
    ('unsupported_inline_layout',sequence(r'AB{\fs41}CD')),
    ('move_comment',change(base,lambda i,d:i==1,kind='Comment')),
    ('nonmoving_move',change(base,lambda i,d:i==1,movement=(300,100,300,100))),
    ('timed_move',change(base,lambda i,d:i==1,movement=(350,100,300,100,100,900))),
    ('endpoint_slack_50ms',change(base,lambda i,d:i==1,movement=(350,100,300,100,0,1050))),
    ('endpoint_slack_51ms',change(base,lambda i,d:i==1,movement=(350,100,300,100,0,1051))),
    ('backward_move_times',change(base,lambda i,d:i==1,movement=(350,100,300,100,900,100))),
    ('malformed_move',change(base,lambda i,d:i==1,movement='(350,100,300,100,5)')),
    ('nonfinite_move',change(base,lambda i,d:i==1,movement='(nan,100,300,100)')),
    ('duplicate_move',change(base,lambda i,d:i==1,tags=r'\move(350,100,300,100)')),
    ('move_transform',change(base,lambda i,d:i==1,tags=r'\t(\1c&HFFFFFF&)')),
    ('move_fade',change(base,lambda i,d:i==1,tags=r'\fad(0,100)')),
    ('frozen_current_mover',change(base,lambda i,d:i==1,frozen_move=True)),
    ('rotated_source',sequence(tags=r'\frz5')),
    ('translucent_source',sequence(tags=r'\1a&H80&')),
]
prefix=event(start=.5,end=1,tags=r'\fad(200,0)')
cases.extend((('touching_entrance',[prefix]+base),
    ('nonmatching_entrance_paint',[dict(prefix,tags=r'\fad(200,0)\1c&H0000FF&')]+base),
    ('nonmatching_entrance_position',[dict(prefix,x=302)]+base),
    ('entrance_gap',[dict(prefix,end=.99)]+base),
    ('ambiguous_entrance',[prefix,deepcopy(prefix)]+base),
))
exit=event(start=5,end=5.2,tags=FADE)
cases.extend((('recorded_exit',base+[exit]),
    ('absorbed_exit',change(base,lambda i,d:i==2,current_end=5.2)+[exit]),
    ('unsafe_absorbed_exit',change(base,lambda i,d:i==2,current_end=5.21)+[exit]),
    ('complete_fade_terminal',base[:-1]+[dict(exit,start=3,end=3.2)]),
    ('incomplete_fade_terminal',base[:-1]+[dict(exit,start=3,end=3.2,tags=r'\t(0,200,\1a&HFF&)')]),
    ('borderless_primary_fade',sequence(tags=r'\bord0')[:-1]+
        [event(start=3,end=3.2,tags=r'\bord0\t(0,200,\1a&HFF&)')]),
    ('invalid_fade_transform',base[:-1]+[dict(exit,start=3,end=3.2,tags=r'\t(0,200,\frz5)')]),
    ('fade_with_fad',base[:-1]+[dict(exit,start=3,end=3.2,tags=FADE+r'\fad(0,200)')]),
    ('ambiguous_exit',base+[exit,deepcopy(exit)]),
))
flash=event(start=3,end=3.2,tags=r'\bord0\1c&H0000FF&'+FADE)
cases.extend((('boundary_flash',base+[flash]),
    ('independent_flash',base+[dict(flash,start=3.01,end=3.21)]),
    ('outlined_flash',base+[dict(flash,tags=r'\bord2\1c&H0000FF&'+FADE)]),
    ('ambiguous_flash',base+[flash,deepcopy(flash)]),
))
cases.append(('shared_hold_ownership',base[:2]+[
    event(start=3,end=4),event(start=4,end=5,movement=(350,100,300,100)),event(start=5,end=6)]))
cases.append(('independent_chains',sequence(name='A')+sequence(name='B')))

# Use independent authored font measurements to place a known separate-glyph row.
geometry_metric=previous.FontSpacing([ROOT/'fonts'])
sample=inputs(previous,[event()],'original')[0][0]
positions=row_test_call(geometry_metric, 'authored_glyph_positions', sample.state,'ABCD',300,sample.unit)
assert positions is not None and len(positions)==4
glyph_moves=[event(word,start=2,end=3,x=x,movement=(x+50,100,x,100)) for word,x in positions]
glyph_base=[event()]+glyph_moves+[event(start=3,end=5)]
cases.extend((('separate_glyphs',glyph_base),
    ('partial_glyph_row',glyph_base[:4]+[glyph_base[-1]]),
    ('wrong_glyph_spacing',[glyph_base[0]]+[dict(d,movement=(d['x']+50,100,d['x']+(10 if i==1 else 0),100))
        for i,d in enumerate(glyph_moves)]+[glyph_base[-1]]),
    ('wrong_glyph_y',[glyph_base[0]]+[dict(d,movement=(d['x']+50,110,d['x'],110))
        for d in glyph_moves]+[glyph_base[-1]]),
    ('duplicate_glyph_destination',[glyph_base[0]]+[dict(d,movement=(d['x']+50,100,positions[0][1],100))
        for d in glyph_moves]+[glyph_base[-1]]),
))
glyph_fades=[event(word,start=5,end=5.2,x=x,tags=FADE) for word,x in positions]
cases.extend((('complete_glyph_exit',glyph_base+glyph_fades),
    ('partial_glyph_exit',glyph_base+glyph_fades[:-1]),
    ('different_glyph_exit_ends',glyph_base+change(glyph_fades,lambda i,d:i==0,end=5.21)),
    ('duplicate_glyph_exit',glyph_base+glyph_fades+[deepcopy(glyph_fades[0])]),
    ('separate_glyph_fade_terminal',glyph_base[:-1]+[dict(d,start=3,end=3.2) for d in glyph_fades]),
))

tracer=trace.Trace(count=True,trace=False);checks=[]
engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
for name,descriptors in cases:
    for order in ('original','reversed','shuffled'):
        for mode in ('none','real','unavailable','failed_anchor'):
            compared=[]
            for module in (previous,current):
                events,visible,sources=inputs(module,descriptors,order)
                before=deepcopy(snapshot((events,visible,sources)))
                metric=None if mode=='none' else RecordingMetric(engines[module],mode)
                result,calls=call(module,events,visible,sources,metric,tracer)
                assert before==snapshot((events,visible,sources)),(name,order,mode,'input mutation')
                compared.append(snapshot((result,calls,getattr(metric,'calls',[]),result[0] is events)))
            assert compared[0]==compared[1],(name,order,mode)
            output,removed=result
            checks.append(dict(case=name,order=order,mode=mode,removed=removed,
                same_list=output is events,font_anchor_calls=len(getattr(metric,'calls',[])),
                output_times=[(e.start_s,e.end_s) for e in output]))
            if name=='dim_retained_terminal' and removed:
                assert len(output)==1 and output[0].state['1a']==0 and output[0].state['3a']==0
            if name=='clear_outline_axes' and removed:
                assert len(output)==1 and output[0].state.get('xbord',output[0].state['bord'])==2
                assert output[0].state.get('ybord',output[0].state['bord'])==2
            if name=='whole_fragment' and mode=='none':assert removed==2 and output[0].start_s==1 and output[0].end_s==5
by_name={c['case']:c for c in checks if c['order']=='original' and c['mode']=='real'}
for name in ('whole_fragment','two_moves','three_moves','touching_entrance','recorded_exit','absorbed_exit',
    'complete_fade_terminal','boundary_flash','separate_glyphs','complete_glyph_exit','separate_glyph_fade_terminal'):
    assert by_name[name]['removed']>0,(name,by_name[name])
for name in ('missing_parent','missing_terminal','duplicate_parent','duplicate_terminal',
    'shared_hold_ownership','unsafe_absorbed_exit','partial_glyph_row','wrong_glyph_spacing',
    'duplicate_glyph_destination','whitespace_text','unsupported_inline_layout'):
    assert by_name[name]['removed']==0,(name,by_name[name])
assert by_name['independent_chains']['removed']==4
assert by_name['touching_entrance']['output_times']==[(.5,5)]
assert by_name['absorbed_exit']['output_times']==[(1,5)]
assert by_name['whole_fragment']['font_anchor_calls']==0
assert by_name['separate_glyphs']['font_anchor_calls']>0
assert all(c['same_list'] for c in checks if c['removed']==0)

focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.collapse_moving_glyph_sequences
        def wrapped(events,visible_map,source_events,metric):
            before=snapshot((events,visible_map,source_events))
            result=(tracer.runfunc(original,events,visible_map,source_events,metric)
                if module is current else original(events,visible_map,source_events,metric))
            captured.append(snapshot((before,result,events,visible_map,source_events)))
            return result
        module.collapse_moving_glyph_sequences=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=module.simplify_ass(ROOT/'test-data'/fixture,output,
                        module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((snapshot(captured),output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:module.collapse_moving_glyph_sequences=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

helpers=set(json.loads((ROOT/'validation/moving-glyph-consolidation-audit.json').read_text())['helpers'])
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
(ROOT/'validation/moving-glyph-checks.json').write_text(json.dumps(dict(
    reference=previous.__version__,version=current.__version__,scenarios=len(cases),comparisons=len(checks),source_validation_and_render_calls_identical=True,
    font_anchor_calls_identical=True,inputs_unchanged=True,
    focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(f'{len(checks)} moving-glyph comparisons; validation/font/render calls identical; 2 focused conversions; all 16 retained helpers exercised')
