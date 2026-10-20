"""Authored full-width strip/hold/exit sequences; proof requires no font backend."""
from dataclasses import replace
from _simplify_ass.ass_overrides import OverrideContinuation
from _simplify_ass.event_operations import replace_event
from _simplify_ass.subtitle_document import _resolve_document_state,format_time,parse_subtitle_document

HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name,Fontname,Fontsize,Alignment,Outline,Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''


def sliced_inputs(*, reverse=False, sentinel=True, pulse=False, partial=False,
                  bad_paint=False, competing=False, authored=False, unresolved=False):
    paint = r'\1c&HDDEEFF&\3c&H112233&'
    rows = []
    def strips(phase,boundary):
        for i in range(3):
            if partial and phase=='in' and i==1:
                continue
            start,end = (boundary-.5,boundary) if phase=='in' else (boundary,boundary+.5)
            move = r'\move(270,100,320,100)' if phase=='in' else r'\move(320,100,370,100)'
            alpha,final = ('FF','00') if phase=='in' else ('00','FF')
            tags = move+f'\\clip(0,{70+i*20},640,{90+i*20})\\alpha&H{alpha}&\\t(\\alpha&H{final}&)'
            if bad_paint and phase=='in' and i==0:tags+=r'\3c&HABCDEF&'
            rows.append(('Dialogue',start,end,tags,'Hello','2'))
    strips('in',1.)
    rows.append(('Dialogue',1.,3.,r'\pos(320,100)','Hello','2'))
    strips('out',3.)
    if pulse:
        rows.append(('Dialogue',1.,3.,r'\pos(320,100)\bord0\fscx150\fscy150\alpha&H80&\t(\fscx100\fscy100\alpha&HFF&)','Hello','3'))
    if competing:
        rows.append(('Dialogue',1.,4.,r'\pos(320,100)','Hello','2'));strips('out',4.)
    if authored:
        rows.append(('Comment',1.,3.,'', 'Hello' if authored is True else authored,'0'))
    raw = HEADER+''.join(f'{kind}: {layer},{format_time(a)},{format_time(b)},Default,,0,0,0,,{{{paint}{tags}}}{word}\n'
                         for kind,a,b,tags,word,layer in rows)
    events = [replace(e,row=8,lyric=True)
              for e in _resolve_document_state(parse_subtitle_document(raw)).events.values()]
    if sentinel:
        events.insert(1,replace_event(events[0],text=r'{\pos(320,290)}Independent',
                                      source_index=99999,row=0,lyric=False))
    if unresolved:
        events = [replace(e,state={},continuation=OverrideContinuation('Stale',True)) for e in events]
    if reverse:events.reverse()
    return events
