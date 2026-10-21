"""Exact-font boundary families using canonical document/measurement owners."""
from dataclasses import replace
from _simplify_ass.ass_overrides import OverrideContinuation
from _simplify_ass.subtitle_document import _resolve_document_state, parse_subtitle_document, format_time
from _simplify_ass.glyph_placement import authored_glyph_positions, fit_fragment_anchor

HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def boundary_inputs(metric, *, phase='entrance', variant='complete', unresolved=False):
    def record(text,start,end):
        return f'Dialogue: 0,{format_time(start)},{format_time(end)},Default,,0,0,0,,{text}\n'
    held=r'{\pos(500,100)\1c&HABCDEF&\3c&H123456&}abc'
    seed=_resolve_document_state(parse_subtitle_document(HEADER+record(held,1.5,3.5)))
    state=next(iter(seed.events.values())).state
    positions=authored_glyph_positions(metric,state,'abc',500,1)
    assert positions is not None,'Required exact Arial regular unavailable'
    phases=('entrance','exit') if phase=='both' else (phase,)
    lines=[]
    for part in phases:
        for i,(char,x) in enumerate(positions):
            if variant=='partial' and i==1:continue
            text=(rf'{{\pos({x},100)\frz30\fad(100,0)\t(0,500,\frz0)}}' if part=='entrance' else
                  rf'{{\move({x},100,{x},120)\fad(0,500)}}')+char
            lines.append(record(text,1 if part=='entrance' else 3.5,1.5 if part=='entrance' else 4))
    if variant=='absorbed':
        anchor=fit_fragment_anchor(metric,state,[x for char,x in positions[1:]],['b','c'],'bc',1,allow_tracking=True)
        assert anchor is not None
        held=r'{\pos('+str(anchor)+',100)}bc'
    lines.append(record(held,1.55 if variant=='within' else 1.56 if variant=='gap' else 1.5,3.44 if variant=='gap' else 3.5))
    if variant=='ambiguous':lines.append(record(held,1.5,3.5))
    doc=_resolve_document_state(parse_subtitle_document(HEADER+''.join(lines)))
    sources=doc.events;events=[];visible={}
    for index,source in sources.items():
        char=source.text.rsplit('}',1)[-1]
        text=held if len(char)>1 else rf'{{\pos({dict(positions)[char]},100)}}'+char
        event=replace(source,text=text,state=state.copy(),continuation=OverrideContinuation())
        if variant=='absorbed' and char=='a':event=replace(event,end_s=3.5)
        events.append(event);visible[index]=char
    if unresolved:sources={k:replace(e,state={},continuation=OverrideContinuation()) for k,e in sources.items()}
    return events,visible,sources
