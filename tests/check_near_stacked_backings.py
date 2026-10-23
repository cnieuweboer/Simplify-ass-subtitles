"""Subpixel stroke correspondence precedes pose reduction and preserves source order."""
import test_paths
from pathlib import Path
from copy import deepcopy
import contextlib
import io
import tempfile
import simplify_ass as s

ROOT = Path(__file__).resolve().parents[1]
metric = s.FontMetrics([ROOT/'fonts'])
assert metric.matching_face('Volkhov',0,False)
HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name,Fontname,Fontsize,Alignment,Outline,Shadow
Style: Default,Volkhov,63,5,0,0
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
def row(tags,word='A complete caption',layer=0,start=1,end=2):
    return f'Dialogue: {layer},{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{{{tags}}}{word}\n'
def fixture(back='',front='',word='A complete caption',x=960,phases=((1,2,0),),peer=None):
    lines=[]
    for start,end,alpha in phases:
        fade=rf'\alpha&H{alpha:02X}&'
        lines.append(row(rf'\pos({x},500)\bord3.6\1c&HEAE9E7&\3c&HEAE9E7&'+fade+back,word,0,start,end))
        if peer:lines.append(row(r'\pos(960,500)\bord0\1c&H0000FF&','XXXXXXXXXXXXXXXXXXXX',0,start,end))
        lines.append(row(r'\pos(960.015,500)\bord0\1c&H272627&'+fade+front,word,0 if peer=='same-layer' else 1,start,end))
    return HEADER+''.join(lines)
def parse(text):
    return list(s._resolve_document_state(s.parse_subtitle_document(text)).events.values())
def flatten(events,sources=None,fonts=metric):
    return s.flatten_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},
        source_events={e.source_index:e for e in (events if sources is None else sources)},font_metrics=fonts)
checks=0
def check(value,label):
    global checks
    assert value,label
    checks+=1

for back,front in [('', ''),(r'\frz20',r'\frz20.01'),(r'\fscx105',r'\fscx105.01'),
                   (r'\b1',r'\b1'),(r'\b1\i1',r'\b1\i1')]:
    events=parse(fixture(back,front));before=deepcopy(events)
    out,n=flatten(events)
    check(n==1 and len(out)==1,'one caption')
    check((out[0].start,out[0].end)==(events[-1].start,events[-1].end),'original timing')
    check(s.get_pos(out[0].text)==s.get_pos(events[-1].text) and s.text_layout_key(out[0])==s.text_layout_key(events[-1]),'foreground pose')
    check(out[0].state['1c']=='272627' and out[0].state['3c']=='EAE9E7' and out[0].state['bord']==2,'proved paint and cap')
    check(events==before,'borrowed source immutable')
    check([e.fields() for e in flatten(out)[0]]==[e.fields() for e in out],'repeat stable')
for back,front,x in [(r'\fscx110','',960),(r'\frz5','',960),(r'\fry10',r'\fry10',960),
                     (r'\clip(0,0,1920,1080)','',960),(r'\3c&H0000FF&','',960),
                     (r'\1a&H80&\3a&H80&',r'\1a&H80&',960),('','',961)]:
    events=parse(fixture(back,front,x=x));out,n=flatten(events)
    check(n==0 and all(a is b for a,b in zip(events,out)),'uncertain pair retained')
for word,expected in [('Hi',True),('A'*180,False)]:
    out,n=flatten(parse(fixture(r'\fscx100.08',word=word)))
    check(bool(n)==expected,'width-aware displacement')
events=parse(fixture(back=r'\fscx110',word=r'AB CD{\fscx1}'))
check(flatten(events)[1]==0,'trailing reset cannot hide visible geometry divergence')
events=parse(fixture());check(flatten(events,fonts=None)[1]==0,'no substituted font geometry')
raw=list(s.parse_subtitle_document(fixture(r'\frz20',r'\frz20.005',x=959.995)).events.values())
working=parse(fixture(r'\frz20',r'\frz20.005',x=959.995))
working[0]=s.replace_event(working[0],text=working[0].text.replace('959.995','960'))
working[1]=s.replace_event(working[1],text=working[1].text.replace('20.005','20.01'))
before=[dict(e.state) for e in raw]
check(flatten(working,raw)[1]==1,'unresolved source and rounded working position/angle')
check([dict(e.state) for e in raw]==before,'source formatting not adopted in place')
sources=deepcopy(events);sources[0]=s.replace_event(sources[0],text=r'{\clip(0,0,1920,1080)}'+sources[0].text)
check(flatten(events,sources)[1]==0,'original mask not erased')
sources=deepcopy(events);sources[0]=s.replace_event(sources[0],text=r'{\t(\fscx110)}'+sources[0].text)
check(flatten(events,sources)[1]==0,'original geometry transform not erased')
sources=parse(fixture(front=r'\t(-375,1625,\1c&H272627&)'))
check(flatten(events,sources)[1]==1,'paint-only source animation does not block geometry ownership')
for back,front,expected in [(r'\t(0,400,\alpha&HFF&)',r'\t(0,400,\alpha&HFF&)',1),
                            (r'\t(0,400,\alpha&HFF&)',r'\t(0,600,\alpha&HFF&)',0),
                            (r'\fad(100,200)',r'\fad(100,200)',1),
                            (r'\fad(100,200)',r'\fad(100,400)',0)]:
    events=parse(fixture());sources=parse(fixture(back,front))
    check(flatten(events,sources)[1]==expected,'source opacity timing survives equal frozen opacity')
events=parse(fixture(peer='interleaved'));out,n=flatten(events)
caption=next(e for e in out if s.OVERRIDE_RE.sub('',e.text)=='A complete caption')
check(n==1 and caption.layer=='1','retain original foreground above interleaved ink')
check(out[-1] is events[1],'independent peer identity')
events=parse(fixture(peer='interleaved'))
events=[s.replace_event(e,layer=str(layer)) for e,layer in zip(events,(-3,-1,-2))]
out,n=flatten(events)
caption=next(e for e in out if s.OVERRIDE_RE.sub('',e.text)=='A complete caption')
check(n==1 and caption.layer=='-2','negative layers do not normalize across higher independent ink')
events=parse(fixture(peer='same-layer'));check(flatten(events)[1]==0,'unrepresentable same-layer slot retains planes')
events=parse(fixture());events.append(s.replace_event(events[0],
    text=events[0].text.replace(r'\pos(960,500)',r'\pos(960.03,500)'),source_index=999))
check(flatten(events)[1]==0,'ambiguous triple not greedily paired')
# A unilateral frame split does not prove correspondence by approximate timing.
events=parse(fixture());back=events[0]
events=[s.replace_event(back,end=s.format_time(1.5),end_s=1.5),
        s.replace_event(back,start=s.format_time(1.5),start_s=1.5,source_index=999),events[-1]]
check(flatten(events)[1]==0,'unilateral split retains incomplete ownership')
# The existing shared-fade family proof can consume measured correspondence.
phases=((1,1.1,64),(1.1,1.3,0),(1.3,1.4,100),(1.4,1.5,180))
events=parse(fixture(phases=phases));out,n=flatten(events)
check(n==4 and len(out)==4,'shared near-coincident fade family')
check([e.state['1a'] for e in out]==[64,0,100,180] and all(e.state['3a']==e.state['1a'] for e in out),'fade timing and opacity')
check(all(e.state['3c']=='EAE9E7' and e.state['bord']==2 for e in out),'fade cap and palette')
for split in (False,True,'mixed'):
    phases=[(1+i*.04,1+(i+1)*.04,0) for i in range(12)]
    if split is True:phases=[(a+(b-a)*j/2,a+(b-a)*(j+1)/2,c) for a,b,c in phases for j in range(2)]
    text=fixture(phases=phases)
    if split=='mixed':
        events=parse(text)
        for i,e in enumerate(events):
            x,y=960+4*(i//2),500+3*(i//2)
            x+=.015 if i%2 or (i//2)%2==0 else 0
            events[i]=s.replace_event(e,text=e.text.replace(
                r'\pos(960.015,500)' if i%2 else r'\pos(960,500)',rf'\pos({x},{y})'))
        text=s.render_subtitle_document(s.parse_subtitle_document(text),events,final_newline=True)
    with tempfile.TemporaryDirectory() as directory:
        source=Path(directory)/'source.ass';output=Path(directory)/'simple.ass';again=Path(directory)/'again.ass'
        source.write_text(text);report=s.FontProcessingReport()
        with contextlib.redirect_stdout(io.StringIO()):
            s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metric,font_report=report)
            s.simplify_ass(output,again,s.SimplifyConfig(),font_metrics=metric)
        check(not report.missing_families and source.read_text()==text,'full pipeline exact font and source')
        check(len(s.load_subtitle_events(output)[1])==1,'paired frame splitting still reduces')
        check(output.read_bytes()==again.read_bytes(),'full pipeline repeat stable')
print(checks,'near-coincident backing checks passed')
