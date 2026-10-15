"""General layered-contour examples; no corpus-specific matching assumptions."""
from pathlib import Path
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
ScaledBorderAndShadow: yes
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def event(body,layer,start=1,end=3,layout=r'\pos(320,100)'):
    return f'Dialogue: {layer},{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{{{layout}}}{body}\n'
def fixture(*,inline=True,same_layer=False,split=False,inner_extra='',front_extra='',width=2,layout=r'\pos(320,100)',dark=False):
    # The inner contour is deliberately low contrast; the wider outer contour
    # is a different color. A neutral contrast choice would visibly change it.
    fill=r'{\bord0\1c&HDDDDEE&'+front_extra+'}AB'
    inner=r'{\bord'+str(width)+r'\1c&H000000&\3c&HBBBBCC&'+inner_extra+'}AB'
    outer=r'{\bord6\blur4\1c&H000000&\3c&H4499EE&}AB'
    if inline:
        fill+=r'{\1c&H99DDCC&} CD'
        inner+=r'{\3c&H88CCBB&} CD'
        outer+=r'{\3c&H88EECC&} CD'
    if split:
        fill=fill.replace('AB',r'A{\1c&HDDDDEE&}B')
        inner=inner.replace('AB',r'A{\3c&HBBBBCC&}B')
    text=HEADER+event(outer,0,layout=layout)+event(inner,0 if same_layer else 1,layout=layout)+event(fill,0 if same_layer else 2,layout=layout)
    if dark:
        for old,new in [('DDDDEE','000000'),('99DDCC','BBDDCC'),('BBBBCC','889966'),('88CCBB','223311')]:
            text=text.replace(old,new)
    return text
def parse(text):return list(s._resolve_document_state(s.parse_subtitle_document(text)).events.values())
def context(events,sources=None):
    paint=set(s.CAPTION_PAINT_TAGS)|{'c','alpha'}
    return s.StackedTextContext({},[],{},paint,set(),{e.source_index:e for e in (events if sources is None else sources)})
def flatten(events,sources=None):
    return s.flatten_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},
        source_events={e.source_index:e for e in (events if sources is None else sources)})
def paints(event):
    result=[]
    for fragment,states in s._literal_paint_ranges([event]):
        state=states[0]
        result.extend((char,tuple(state.get(k,state.get('bord',0) if k in ('xbord','ybord') else 0)
             for k in ('1c','3c','1a','3a','xbord','ybord'))) for char in fragment)
    return result
