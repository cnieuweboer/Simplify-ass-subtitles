"""Authored backing/hold/pulse rows; font-free proof or exact Volkhov paint."""
from _simplify_ass.ass_overrides import OVERRIDE_RE
from _simplify_ass.event_operations import replace_event
from _simplify_ass.subtitle_document import _resolve_document_state,format_time,parse_subtitle_document

FAMILY = 'Volkhov'
HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name,Fontname,Fontsize,Alignment,Outline,Shadow
Style: Default,Volkhov,40,5,0,0
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''


def backed_inputs(*, reverse=False, sentinel=True, incomplete=False, competing=False):
    records = []
    for i,word in enumerate('Abcd'):
        x = 100+50*i
        start = 1.3+i*.2
        for layer,a,b,tags in [
            (1,1,4,r'\1c&H000000&\1a&H10&\blur5.7'),
            (2,1,4,r'\1c&HC6DDEA&\blur.675'),
            (3,start,start+.2,r'\1c&H6468FF&\blur1.35\t(0,200,\1c&HC6DDEA&\blur.675)'),
        ]:
            records.append(f'Dialogue: {layer},{format_time(a)},{format_time(b)},Default,,0,0,0,,{{\\pos({x},100){tags}}}{word}\n')
    doc = _resolve_document_state(parse_subtitle_document(HEADER+''.join(records)))
    events = [replace_event(e,row=7,lyric=True) for e in doc.events.values()]
    if incomplete:
        del events[-3]
    if competing:
        events += [replace_event(e,layer='0',source_index=e.source_index+10000)
                   for e in events if e.layer=='1']
    if sentinel:
        other = replace_event(events[0],text=r'{\pos(320,280)\1c&H123456&}Independent',
                              source_index=99999,row=0,lyric=False)
        events.insert(1,other)
    if reverse:
        events.reverse()
    words = {e.source_index:OVERRIDE_RE.sub('',e.text) for e in events}
    positions = {e.source_index:((320.,280.) if e.source_index==99999 else
                                (100.+50*'Abcd'.index(words[e.source_index]),100.))
                 for e in events}
    return events,words,positions
