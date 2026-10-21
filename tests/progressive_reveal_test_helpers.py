"""Font-free reveal fixtures using the real document and span interpreters."""
from _simplify_ass.subtitle_document import (
    _resolve_document_state, parse_subtitle_document, format_time,
)


def reveal_inputs(*, gaps=False, strips=False, incomplete=False, tags='', sentinel=True):
    raw='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    for phase,prefix in enumerate((1,2,3,4)):
        start=1+phase*(.12 if gaps else .1)
        end=start+.1 if prefix<4 else 2+(.06 if gaps else 0)
        for strip in range(6 if strips and prefix<4 else 1):
            if incomplete and prefix==2 and strip==2:continue
            clip=(r'\clip(0,'+str(85+2.5*strip)+',1000,'+str(87.5+2.5*strip)+')') if strips and prefix<4 else ''
            body=r'{\pos(500,100)'+tags+clip+'}'+'abcd'[:prefix]
            if prefix<4:body+=r'{\alpha&HFF&}'+'abcd'[prefix:]
            raw+=f'Dialogue: 0,{format_time(start)},{format_time(end)},Default,,0,0,0,,{body}\n'
    doc=_resolve_document_state(parse_subtitle_document(raw))
    events=list(doc.events.values())
    for e in events:e.lyric=True;e.row=0
    if sentinel:
        from _simplify_ass.event_operations import replace_event
        events.append(replace_event(events[-1],source_index=99999,start=format_time(5),start_s=5,end=format_time(6),end_s=6,text=r'{\pos(100,300)}Independent'))
    visible={e.source_index:('Independent' if e.source_index==99999 else 'abcd') for e in events}
    visible[999999]='removed historical source'
    return events,visible
