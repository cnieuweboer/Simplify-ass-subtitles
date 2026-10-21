"""Real-font shrinking rows using canonical document and glyph-placement owners."""
from dataclasses import replace
from _simplify_ass.ass_overrides import OverrideContinuation
from _simplify_ass.subtitle_document import _resolve_document_state, parse_subtitle_document, format_time
from _simplify_ass.glyph_placement import authored_glyph_positions

HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def shrinking_inputs(metric, *, variant='complete', unresolved=False, reverse=False):
    def record(text,start,end,name=''):
        return f'Dialogue: 0,{format_time(start)},{format_time(end)},Default,{name},0,0,0,,{text}\n'
    held=r'{\pos(500,100)\1c&HABCDEF&\3c&H123456&}abc'
    seed=_resolve_document_state(parse_subtitle_document(HEADER+record(held,1.5,3.5)))
    state=next(iter(seed.events.values())).state
    positions=authored_glyph_positions(metric,state,'abc',500,1)
    assert positions is not None,'Required exact Arial regular unavailable'
    lines=[]
    for i,(char,x) in enumerate(positions):
        if variant=='partial' and i==1:continue
        text=r'{\move('+f'{x},95,{x},100'+r')\t(0,500,\fscx50\fscy50\alpha&HFF&)}'+char
        lines.append(record(text,1,1.5))
    lines.append(record(held,1.51 if variant=='gap' else 1.5,3.5))
    if variant=='ambiguous':lines.append(record(held,1.5,3.5))
    if variant in ('fade','gap_fade','visible_predecessor'):
        fade=r'\t(500,600,\alpha&HFF&)' if variant=='gap_fade' else r'\t(1100,1200,\alpha&HFF&)' if variant=='fade' else ''
        lines.append(record(r'{\pos(500,100)'+fade+'}xyz',0,1.5))
    lines.append(record(r'{\pos(100,300)}Independent',5,6,'unrelated'))
    events=_resolve_document_state(parse_subtitle_document(HEADER+''.join(lines))).events
    if unresolved:events={k:replace(e,state={},continuation=OverrideContinuation()) for k,e in events.items()}
    return dict(reversed(list(events.items()))) if reverse else events
