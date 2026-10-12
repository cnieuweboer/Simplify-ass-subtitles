from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare row reconstruction, evidence and caller-visible changes with v153."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import json
import statistics
import sys
import trace

import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('row_reference',
    ROOT/'test-data/simplify_ass-v153-reference.py')
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

def glyph(text,x,start=1,end=4,**options):
    return {'text':text,'x':x,'start':start,'end':end,**options}

def row(text='ABCD',start=1,end=4,**options):
    return [glyph(c,100+24*i,start,end,**options) for i,c in enumerate(text)]

def authored(text='ABCD',start=1,end=4):
    return glyph(text,0,start,end,kind='Comment')

class ControlledMetric:
    """Deterministic spacing outcomes exercise the row engine's decision paths."""
    def __init__(self,mode):
        self.mode = mode
        self.available = mode!='unavailable'
        self.merged = 0
        self.calls = []
    def recover(self,ordered,fragments):
        self.calls.append(('recover',tuple(e.source_index for e in ordered),tuple(fragments)))
        if self.mode in {'reject','fullwidth'}:
            return None
        text = ''.join(fragments)
        if self.mode=='mismatched':
            text = 'different'
        return text,statistics.median(current.get_pos(e.text)[0] for e in ordered),100,100,5
    def recover_tracked(self,ordered,fragments):
        result = self.recover(ordered,fragments)
        return (*result,1.5) if result else None
    def fit_fullwidth_run(self,ordered,fragments):
        self.calls.append(('fullwidth',tuple(fragments)))
        return (statistics.median(current.get_pos(e.text)[0] for e in ordered),100) if self.mode=='fullwidth' else None

def make_inputs(module,case):
    lines = []
    for descriptor in case['events']:
        kind = descriptor.get('kind','Dialogue')
        tags = (r'\an5\pos('+str(descriptor['x'])+','+str(descriptor.get('y',100))+')'+
                descriptor.get('tags','')) if kind=='Dialogue' else ''
        text = ('{'+tags+'}' if tags else '')+descriptor['text']
        lines.append(f"{kind}: {descriptor.get('layer',0)},{module.format_time(descriptor['start'])},"
            f"{module.format_time(descriptor['end'])},Default,{descriptor.get('name','')},0,0,0,,{text}\n")
    document = module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events = list(document.events.values())
    for event,descriptor in zip(events,case['events']):
        event.lyric = descriptor.get('lyric',True) and event.kind=='Dialogue'
        event.row = descriptor.get('row',1)
    visible = {e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    animated = {events[i].source_index for i in case.get('animated',())}
    sources = {e.source_index:deepcopy(e) for e in events}
    source_rows = []
    if case.get('source_members'):
        pieces = [(events[i],visible[events[i].source_index],module.get_pos(events[i].text))
                  for i in case['source_members']]
        source = module.TextRow(pieces[0][0],pieces,
            paint_rows=[[e for e,_,_ in pieces]],source_anchors={'ABCD':[(100,100)]},
            foreground=[e for e,_,_ in pieces],confirmed=case.get('confirmed',True))
        if case.get('source_foreground'):
            source.foreground=[events[i] for i in case['source_foreground']]
        source_rows.append(source)
        if case.get('duplicate_source_row'):source_rows.append(source)
    spaces = ({(module.format_time(1),module.format_time(4),'Default','',1):set(case['blanks'])}
              if case.get('blanks') else {})
    return events,visible,spaces,animated,source_rows,sources

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,dict):
        return {key:snapshot(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return tuple(snapshot(item) for item in value)
    if isinstance(value,set):
        return frozenset(snapshot(item) for item in value)
    if hasattr(value,'__dict__'):
        return snapshot(vars(value))
    return value

cases = [
    {'name':'empty','events':[]},
    {'name':'singleton','events':row('A')},
    {'name':'authored_static','events':row()+[authored()]},
    {'name':'blank_spacing','events':[glyph(c,x) for c,x in zip('ABCD',[100,124,160,184])],'blanks':[142]},
    {'name':'unmeasured_fragments','events':row()},
    {'name':'paint_copies','events':row()+[glyph('B',124,layer=2,tags=r'\1a&H80&')]},
    {'name':'different_paint','events':[glyph(c,100+24*i,tags=r'\1c&H'+color+'&')
        for i,(c,color) in enumerate(zip('ABCD',['0000FF','00FF00','FF0000','FFFFFF']))]},
    {'name':'ineligible_geometry','events':row()+[
        glyph('R',220,tags=r'\frz20'),glyph('C',250,tags=r'\clip(0,0,1000,1000)'),
        glyph(r'A{\fs50}B',280),glyph(r'A\NB',300)]},
    {'name':'confirmed_source','events':row()+[authored()],'source_members':[0,1,2,3]},
    {'name':'source_virtual_fallback','events':row(),'source_members':[0,1,2,3]},
    {'name':'source_overlapping_anchors','events':[glyph(c,100+12*(i//2)) for i,c in enumerate('ABCD')],
        'source_members':[0,1,2,3]},
    {'name':'unconfirmed_source','events':row()+[authored()],'source_members':[0,1,2,3],'confirmed':False},
    {'name':'source_timing_mismatch','events':[glyph(c,100+24*i,end=4+.1*i) for i,c in enumerate('ABCD')],
        'source_members':[0,1,2,3]},
    {'name':'forward_sweep','events':[glyph(c,100+24*i,1+.1*i,4+.1*i) for i,c in enumerate('ABCD')],
        'animated':[0,1,2,3]},
    {'name':'reverse_sweep','events':[glyph(c,100+24*i,1+.1*(3-i),4+.1*(3-i)) for i,c in enumerate('ABCD')],
        'animated':[0,1,2,3]},
    {'name':'chain_without_shared_interval','events':[glyph(c,100+24*i,1+.7*i,2+.7*i) for i,c in enumerate('ABCD')],
        'animated':[0,1,2,3]},
    {'name':'partially_proven_animation','events':[glyph(c,100+24*i,1+.1*i,4+.1*i) for i,c in enumerate('ABCD')],
        'animated':[0,1,2]},
    {'name':'coextensive_entrance','events':[glyph(c,100+24*i,1+offset,4+offset)
        for i,(c,offset) in enumerate(zip('ABCD',[.08,.02,0,.10]))]},
    {'name':'coextensive_tail_trim','events':[glyph(c,100+24*i,1+offset,4+offset)
        for i,(c,offset) in enumerate(zip('ABCD',[.08,.02,0,.10]))]+
        [glyph(c,100+24*i,3.8+offset,6+offset)
        for i,(c,offset) in enumerate(zip('EFGH',[.08,.02,0,.10]))]},
    {'name':'shared_glyph_full_lifetime','events':row('ABCD',1,3)[:2]+[glyph('i',148,1,5)]+row('ABCD',1,3)[3:]+
        [glyph('E',100,3,5),glyph('F',124,3,5),glyph('G',172,3,5)]},
    {'name':'shared_glyph_authored','events':row('ABCD',1,3)[:2]+[glyph('i',148,1,5)]+row('ABCD',1,3)[3:]+
        [glyph('E',100,3,5),glyph('F',124,3,5),glyph('G',172,3,5),
         authored('ABiD',1,3),authored('EFiG',3,5)]},
    {'name':'shared_glyph_uncovered_tail','events':row('ABCD',1,3)[:2]+[glyph('i',148,1,6)]+row('ABCD',1,3)[3:]+
        [glyph('E',100,3,5),glyph('F',124,3,5),glyph('G',172,3,5)]},
    {'name':'shared_glyph_overlapping_cues','events':row('ABCD',1,3.2)[:2]+[glyph('i',148,1,5)]+row('ABCD',1,3.2)[3:]+
        [glyph('E',100,3,5),glyph('F',124,3,5),glyph('G',172,3,5)]},
    {'name':'shared_glyph_ambiguous_authored_spaces','events':row('ABCD',1,3)[:2]+[glyph('i',148,1,5)]+row('ABCD',1,3)[3:]+
        [glyph('E',100,3,5),glyph('F',124,3,5),glyph('G',172,3,5),
         authored('AB iD',1,3),authored('ABi D',1,3)]},
    {'name':'shared_glyph_conflicting_authored_text','events':row('ABCD',1,3)[:2]+[glyph('i',148,1,5)]+row('ABCD',1,3)[3:]+
        [glyph('E',100,3,5),glyph('F',124,3,5),glyph('G',172,3,5),authored('Not the row',1,3)]},
    {'name':'unclaimed_glyph_phase','events':[glyph(c,100+24*i,1,4+.1*i) for i,c in enumerate('ABCD')]+
        [glyph('A',100,4,5)],'animated':[0,1,2,3]},
    {'name':'occupied_gap','events':row('ABCD')+[glyph('X',136,.8,4.2)]},
    {'name':'occupied_coextensive_edge','events':[glyph(c,100+24*i,1+offset,4+offset)
        for i,(c,offset) in enumerate(zip('ABCD',[.08,.02,0,.10]))]+[glyph('X',196,.7,4.5)]},
    {'name':'tracked_row','events':row(tags=r'\fsp2')},
    {'name':'fullwidth_row','events':row('漢字文字')},
    {'name':'incompatible_vertical_band','events':[glyph(c,100+24*i,y=100+20*(i%2)) for i,c in enumerate('ABCD')]},
    {'name':'invalid_lifetimes','events':row()+[glyph('E',220,3,2),glyph('F',244,2,2)]},
    {'name':'static_non_lyric','events':row(lyric=False)+[authored()]},
]

cases.extend([
    {'name':'source_foreground_colour','events':row(tags=r'\1c&HFFFFFF&')+
        [glyph('A',100,layer=3,tags=r'\1c&H112233&')],
        'source_members':[0,1,2,3],'source_foreground':[4]},
    {'name':'duplicate_source_row_alias','events':row(tags=r'\1c&HFFFFFF&')+
        [glyph('A',100,layer=3,tags=r'\1c&H112233&')],
        'source_members':[0,1,2,3],'source_foreground':[4],'duplicate_source_row':True},
])

checks = []
tracer = trace.Trace(count=True,trace=False)
metrics = {module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
for case in cases:
    for mode in ('none','reject','fit','mismatched','fullwidth','unavailable','real'):
        for source_only,static_only in ((False,False),(True,False),(False,True),(True,True)):
            results = []
            for module in (previous,current):
                events,visible,spaces,animated,source_rows,sources = make_inputs(module,case)
                metric = None if mode=='none' else metrics[module] if mode=='real' else ControlledMetric(mode)
                input_before=snapshot((events,visible,spaces,animated,source_rows,sources))
                before = font_test_report(metric).rows_joined if metric else 0
                kwargs = {'source_rows':source_rows,'source_only':source_only,
                          'static_only':static_only,'source_events':sources}
                args = (events,visible,spaces,metric,animated)
                result = (tracer.runfunc(module.reconstruct_text_rows,*args,**kwargs)
                          if module is current else module.reconstruct_text_rows(*args,**kwargs))
                if module is current:
                    assert input_before==snapshot((events,visible,spaces,animated,source_rows,sources)),(case['name'],'borrowed inputs changed')
                    semantic=(result.events,result.merged_count,result.duplicate_count,result.rows)
                    # Apply the returned updates as a caller, after the pass has
                    # demonstrated that it did not write the shared map itself.
                    visible.update(result.visibility_updates)
                else:semantic=result
                results.append(snapshot((semantic,events,visible,spaces,sources,
                    font_test_report(metric).rows_joined-before if metric else 0,getattr(metric,'calls',[]),
                    font_test_report(metric).missing_families if metric is not None else set())))
            assert results[0]==results[1],(case['name'],mode,source_only,static_only)
            checks.append({'case':case['name'],'metric':mode,'source_only':source_only,
                'static_only':static_only,'events_rows_timing_counts_applied_visibility_and_font_counters_identical':True,'borrowed_inputs_unchanged':True})

report = {'version':current.__version__,'reference_version':previous.__version__,
          'comparisons_passed':len(checks),'comparisons':checks}
(ROOT/'validation/row-reconstruction-equivalence.json').write_text(json.dumps(report,indent=2)+'\n')
counts = tracer.results().counts
(ROOT/'validation/row-reconstruction-lines.json').write_text(json.dumps({
    str(line):count for (filename,line),count in counts.items()
    if Path(filename).resolve()==Path(current.__file__).resolve()},indent=2)+'\n')
print(len(checks),'row reconstruction equivalence comparisons passed')
