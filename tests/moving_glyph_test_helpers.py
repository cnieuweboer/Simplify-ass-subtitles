"""Authored hold/move/hold chains with optional exact separate-glyph placement."""
from _simplify_ass.ass_overrides import OVERRIDE_RE
from _simplify_ass.event_operations import replace_event
from _simplify_ass.glyph_placement import authored_glyph_positions
from _simplify_ass.subtitle_document import _resolve_document_state,format_time,parse_subtitle_document

FAMILY = 'Arial'
HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name,Fontname,Fontsize,Alignment,Outline,Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''


def moving_inputs(*, reverse=False, sentinel=True, incomplete=False, competing=False,
                  glyphs=False, metric=None, inline=False):
    literal = r'AB{\fnArial}CD' if inline else 'ABCD'
    tags = r'\1c&HDDEEFF&\3c&H112233&'
    records = [(1.,2.,r'\pos(320,100)',literal),
               (2.,3.,r'\move(370,100,320,100)',literal),
               (3.,5.,r'\pos(320,100)',literal)]
    def events_for(rows):
        raw = HEADER+''.join(f'Dialogue: 2,{format_time(a)},{format_time(b)},Default,,0,0,0,,{{{pose}{tags}}}{word}\n'
                             for a,b,pose,word in rows)
        return [replace_event(e,row=7,lyric=True)
                for e in _resolve_document_state(parse_subtitle_document(raw)).events.values()]
    if glyphs:
        sample = events_for(records)[0]
        positions = authored_glyph_positions(metric,sample.state,'ABCD',320,sample.unit)
        assert positions is not None and len(positions)==4,'Required exact glyph placement unavailable'
        records = [records[0],*[(2.,3.,f'\\move({x+50},100,{x},100)',word)
                               for word,x in positions],records[-1]]
    events = events_for(records)
    if incomplete:
        events.pop()
    if competing:
        events.append(replace_event(events[0],source_index=10000))
    if sentinel:
        events.insert(1,replace_event(events[0],text=r'{\pos(320,280)}Independent',
                                     source_index=99999,row=0,lyric=False))
    sources = {e.source_index:e for e in events}
    visible = {e.source_index:OVERRIDE_RE.sub('',e.text) for e in events}
    if reverse:
        events.reverse();sources=dict(reversed(list(sources.items())))
    return events,visible,sources
