"""Canonical full-copy families without importing the engine or optional backends."""
from dataclasses import replace
from _simplify_ass.subtitle_document import _resolve_document_state, parse_subtitle_document, format_time
from _simplify_ass.event_model import EventEvidence
from _simplify_ass.frame_pose import _frame_pose_intervals

HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def full_copy_inputs(*,variant='complete',tags=r'\1c&HFFFFFF&\3c&HDDDDDD&\3a&H60&\bord1.25'):
    def record(word,start,end,position=320,name=''):
        return f'Dialogue: 2,{format_time(start)},{format_time(end)},Default,{name},0,0,0,,'+r'{\pos('+str(position)+',100)'+tags+'}'+word+'\n'
    if variant=='chain':
        specs=[('ABCD',1.5,4.5,320),('AB CD',1,4,320),('ABCD',2,5,320)]
    else:
        specs=[('AB CD' if variant=='pose' else 'ABCD',1,4,320),
               ('AB CD',5 if variant=='gap' else 1.1,8 if variant=='gap' else 4.1,400 if variant=='separate' else 320)]
    text=HEADER+''.join(record(*spec) for spec in specs)+record('Independent',6,7,100,'unrelated')
    events=list(_resolve_document_state(parse_subtitle_document(text)).events.values())
    for event in events:event.lyric=True;event.row=0
    if variant=='chain':events[0],events[1]=events[1],events[0]
    if variant=='pose':
        events=[replace(e,evidence=EventEvidence(frame_pose_intervals=_frame_pose_intervals(e),
                    original_contour_points=((1.,1.),(2.,2.)),opaque_spans=((e.start_s,e.end_s),))) for e in events]
    visible={e.source_index:e.text.rsplit('}',1)[-1] for e in events}
    visible[999999]='historical source'
    return events,visible


def transitive_copy_inputs(*,foreign='none',insertion=2,layer='0',foreign_layer='0',
                           marker_tags='',marker_layout=None):
    """Four linked originals, optionally separated by independent painted ink."""
    records=[f'Dialogue: {layer},{format_time(1+n*.5)},{format_time(4+n*.5)},Default,,0,0,0,,'+
        r'{\pos(320,100)\bord1.25\3c&HDDDDDD&}ABCD'+'\n' for n in range(4)]
    if foreign!='none':
        start,end=(6,7) if foreign=='outside' else (2,5)
        layout=marker_layout if marker_layout is not None else r'\pos('+('100' if foreign=='distant' else '320')+',100)'
        marker=f'Dialogue: {foreign_layer},{format_time(start)},{format_time(end)},Default,independent,0,0,0,,'+'{'+layout+r'\1c&H0000FF&'+marker_tags+'}XXXX\n'
        records.insert(insertion,marker)
    events=list(_resolve_document_state(parse_subtitle_document(HEADER+''.join(records))).events.values())
    for event in events:event.lyric=not event.name;event.row=0
    visible={event.source_index:event.text.rsplit('}',1)[-1] for event in events}
    return events,visible
