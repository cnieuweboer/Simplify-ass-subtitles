import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare common-row timing, paint, call order and visible-map updates with v123."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
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
install_row_test_doubles(current, historical_fade_timing=True)

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('shared_interval_reference',
    ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER=(ROOT/'test-data/Overlord-22m06-source.ass').read_text(
    encoding='utf-8-sig').split('Dialogue:',1)[0]
LETTERS=list(zip('itsu',(488,505,525,552)))

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,RecordingMetric):return ('metric',value.mode,value.available)
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
    def __getattr__(self,name):
        value=getattr(self.engine,name)
        if not callable(value):return value
        def wrapped(*args,**kwargs):
            self.calls.append((name,snapshot((args,kwargs))))
            if self.mode=='failed_fit' and name in ('recover','recover_tracked'):return None
            return value(*args,**kwargs)
        return wrapped

def event(word,x,start=1,end=3,layer='0',tags='',y=78,**options):
    return dict(word=word,x=x,y=y,start=start,end=end,layer=layer,tags=tags,**options)

def row(timing='shared_start',name=''):
    return [event(word,x,start=1+.2*i if timing!='shared_start' else 1,
        end=3 if timing=='shared_end' else 2+.2*i,name=name)
        for i,(word,x) in enumerate(LETTERS)]

def change(descriptors,which,**changes):
    result=deepcopy(descriptors)
    for i,d in enumerate(result):
        if which(i,d):d.update(changes)
    return result

def inputs(module,descriptors,order):
    lines=[]
    for d in descriptors:
        pos='' if d.get('unpositioned') else f"\\pos({d['x']},{d['y']})"
        tags=r'\an5'+pos+d['tags']
        lines.append(f"{d.get('kind','Dialogue')}: {d['layer']},{module.format_time(d['start'])},"
            f"{module.format_time(d['end'])},ED-R,{d.get('name','')},0,0,0,{d.get('effect','')},{{{tags}}}{d['word']}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values());animated=set()
    for i,(e,d) in enumerate(zip(events,descriptors)):
        if d.get('synthetic_ids'):e.source_index=1000-i*17
        if d.get('lyric'):e.lyric=True
        if d.get('animated',True):animated.add(e.source_index)
        if 'state' in d:e.state={**e.state,**d['state']}
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    if order=='reversed':events.reverse()
    if order=='shuffled':random.Random(118).shuffle(events)
    return events,visible,animated

def glyphs(module,events,at):
    result=Counter()
    for e in events:
        if e.kind=='Dialogue' and e.start_s<=at<e.end_s:
            result.update(c for c in module.simplify_text(e.text,visible_only=True)[1] if not c.isspace())
    return result

def call(module,events,visible,metric,animated,tracer):
    calls=[];originals={}
    for name in ('caption_bounds','positioned_row_geometry','render_merged_caption','split_positioned_row_runs'):
        original=getattr(module,name);originals[name]=original
        def wrapped(*args,_name=name,_original=original,**kwargs):
            calls.append((_name,snapshot((args,kwargs))))
            return _original(*args,**kwargs)
        setattr(module,name,wrapped)
    try:
        result=(tracer.runfunc(module._merge_shared_interval_rows_once,events,visible,metric,animated, font_report=font_test_report(metric))
            if module is current else module._merge_shared_interval_rows_once(events,visible,metric,animated, font_report=font_test_report(metric)))
        return result,calls
    finally:
        for name,original in originals.items():setattr(module,name,original)

base=row();cases=[('empty',[]),('shared_start',base),('shared_end',row('shared_end')),
    ('directional_sweep',row('sweep')),('equal_time',change(base,lambda i,d:True,end=2)),
    ('short_common_interval',change(base,lambda i,d:True,end=1.03)),
    ('exact_40ms',change(base,lambda i,d:True,end=1.04)),
    ('too_few_fragments',base[:3]),('duplicate_anchor',change(base,lambda i,d:i==1,x=488)),
    ('three_fragments_after_size_change',change(base,lambda i,d:i==1,tags=r'\fs65')),
    ('independent_vertical_band',base+[event('X',490,start=1.1,end=2.2,y=68)]),
    ('no_animation',change(base,lambda i,d:True,animated=False)),
    ('lyric_without_animation',change(base,lambda i,d:True,animated=False,lyric=True)),
    ('synthetic_ids',change(base,lambda i,d:True,synthetic_ids=True)),
    ('separate_names',change(base,lambda i,d:i%2==0,name='other')),
    ('tail_on_both_sides',row('sweep')),
    ('translucent_fill',change(base,lambda i,d:True,tags=r'\1a&H80&')),
    ('style_box',change(base,lambda i,d:True,state={'borderstyle':3})),
    ('inline_candidate',base[:3]+[event(r'u{\1c&HFF0000&}x',552,end=2.6)]),
    ('explicit_linebreak',change(base,lambda i,d:True,word=r'i\Nt')),
    ('unpositioned',change(base,lambda i,d:True,unpositioned=True)),
    ('comment',change(base,lambda i,d:True,kind='Comment')),
    ('nonnumeric_layer',change(base,lambda i,d:True,layer='invalid')),
    ('negative_layer',change(base,lambda i,d:True,layer='-1')),
    ('scrolling_effect',change(base,lambda i,d:True,effect='Scroll up;0;1080;20')),
]
for name,tags in (('clip',r'\clip(400,40,600,100)'),('rotation',r'\frz2'),
    ('movement',r'\move(100,78,120,78)'),('transform',r'\t(\1c&HFFFFFF&)'),
    ('fade',r'\fad(0,100)'),('karaoke',r'\k20'),('origin',r'\org(100,100)')):
    cases.append((name,change(base,lambda i,d:True,tags=tags)))
colours=('0000FF','00FF00','FF0000','ABCDEF')
cases.append(('paint_spans',[dict(d,tags=r'\xbord1.25\ybord2.5\3a&H40&\xshad3\yshad4\1c&H'+colours[i]+'&')
    for i,d in enumerate(base)]))
cases.append(('mixed_borders',[dict(d,tags=r'\bord'+str(i+1)+r'\3a&H'+f'{i*32:02X}'+'&')
    for i,d in enumerate(base)]))
cases.append(('tracked_row',[dict(d,x=d['x']+2*i,tags=r'\fsp2') for i,d in enumerate(base)]))
mixed=[dict(d,layer=str(i%2)) for i,d in enumerate(base)]
cases.append(('mixed_layers',mixed))
for name,neighbor in (
    ('interleaved',event('X',515,name='other')),
    ('equivalent_layer_spelling',event('X',515,name='other',layer='00')),
    ('long_occluder',event('X'*20,760,name='other')),
    ('later_safe_slot',event('X',575,name='other')),
    ('inline_paint_extent',event(r'X{\blur12\be2\xbord30\ybord20\xshad-10\yshad15}X',575,name='other')),
    ('inline_geometry_uncertain',event(r'X{\fs120}X',575,name='other')),
    ('clipped_uncertain',event('X',575,name='other',tags=r'\clip(400,40,600,100)')),
    ('temporally_disjoint_neighbor',event('X',515,start=4,end=5,name='other')),
    ('lower_layer_neighbor',event('X',515,name='other',layer='-1')),
    ('higher_layer_neighbor',event('X',515,name='other',layer='1')),
):
    cases.append((name,base[:1]+[neighbor]+base[1:]))
cases.append(('mixed_layer_interleaving',mixed[:1]+[event('X',515,name='other')]+mixed[1:]))
a=row(name='A');b=[dict(d,x=d['x']-86,name='B') for d in base]
cases.append(('joint_placement',[a[0],event('X',552,name='other'),b[0],*a[1:],*b[1:]]))
cases.append(('two_disjoint_rows',a+change(b,lambda i,d:True,start=4,end=6)))
cases.append(('same_layer_overlap_conflict',[a[0],b[0],a[1],b[1],a[2],b[2],a[3],b[3]]))
for count in (5,33,65):
    cases.append((f'window_size_{count}',[event('i',100+25*i,end=3+.01*i) for i in range(count)]))

tracer=trace.Trace(count=True,trace=False);checks=[]
engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
for name,descriptors in cases:
    for order in ('original','reversed','shuffled'):
        for mode in ('real','failed_fit'):
            compared=[]
            for module in (previous,current):
                events,visible,animated=inputs(module,descriptors,order)
                before=deepcopy(snapshot((events,animated)));original_map=deepcopy(visible)
                metric=RecordingMetric(engines[module],mode)
                result,calls=call(module,events,visible,metric,animated,tracer)
                assert before==snapshot((events,animated)),(name,order,mode,'source mutation')
                assert all(visible[k]==v for k,v in original_map.items()),(name,'original visible entry changed')
                compared.append(snapshot((result,visible,calls,metric.calls,result[0] is events)))
            assert compared[0]==compared[1],(name,order,mode)
            after,rows,tails=result
            times=sorted({t for e in events+after for t in (e.start_s,e.end_s)})
            for at in times+[(a+b)/2 for a,b in zip(times,times[1:])]:
                assert glyphs(current,events,at)==glyphs(current,after,at),(name,order,mode,at,'glyph lifetime')
            assert len({e.source_index for e in after})==len(after),(name,'unique IDs')
            bounds_ids=[args[0][0]['source_index'] for method,args in calls if method=='caption_bounds']
            assert len(set(bounds_ids))==len(bounds_ids),(name,'bounds recomputed')
            checks.append(dict(case=name,order=order,mode=mode,rows=rows,tails=tails,
                added_visible_entries=len(visible)-len(original_map),bounds_measurements=len(bounds_ids),
                same_list=after is events))

# The early guard must leave both the list and visible mapping untouched.
for mode in ('none','unavailable'):
    compared=[]
    for module in (previous,current):
        events,visible,animated=inputs(module,base,'original')
        metric=None if mode=='none' else RecordingMetric(engines[module],mode)
        result,calls=call(module,events,visible,metric,animated,tracer)
        assert result==(events,0,0) and result[0] is events and not calls
        compared.append(snapshot((result,visible,getattr(metric,'calls',[]))))
    assert compared[0]==compared[1],mode
    checks.append(dict(case='font_guard',mode=mode,rows=0,tails=0,same_list=True))
by_name={c['case']:c for c in checks if c.get('order')=='original' and c['mode']=='real'}
assert by_name['shared_start']['rows']==1 and by_name['shared_start']['tails']==3
assert by_name['directional_sweep']['rows']==1 and by_name['directional_sweep']['tails']==6
assert by_name['joint_placement']['rows']==2
assert by_name['later_safe_slot']['rows']==1
for name in ('interleaved','long_occluder','mixed_layer_interleaving','translucent_fill','style_box','no_animation'):
    assert by_name[name]['rows']==0,(name,by_name[name])
assert all(c['same_list'] for c in checks if c['rows']==0)

focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module._merge_shared_interval_rows_once
        def wrapped(events,visible,metric,animated_sources):
            before=snapshot((events,visible,animated_sources))
            result=(tracer.runfunc(original,events,visible,metric,animated_sources)
                if module is current else original(events,visible,metric,animated_sources))
            captured.append(snapshot((before,result,events,visible,animated_sources)))
            return result
        module._merge_shared_interval_rows_once=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=module.simplify_ass(ROOT/'test-data'/fixture,output,
                        module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((snapshot(captured),output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:module._merge_shared_interval_rows_once=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

helpers={entry['helper'] for entry in json.loads(
    (ROOT/'validation/shared-interval-extraction-blocks.json').read_text())}
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
assert len(coverage)==14 and all(c['exercised'] for c in coverage.values()),coverage
(ROOT/'validation/shared-interval-stage-checks.json').write_text(json.dumps(dict(
    reference='v123',comparisons=len(checks),font_geometry_and_render_calls_identical=True,
    visible_map_updates_identical=True,source_events_unchanged=True,
    glyph_lifetimes_preserved=True,bounds_cache_per_pass_verified=True,
    focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(f'{len(checks)} shared-interval stage comparisons; font/geometry/render calls identical; 2 focused conversions; all 14 helpers exercised')
