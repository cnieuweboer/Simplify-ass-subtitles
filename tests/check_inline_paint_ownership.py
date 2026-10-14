"""Whole literal paint families preserve contours, gradients and base transparency."""
import test_paths
from pathlib import Path
from copy import deepcopy
import contextlib,hashlib,io,json,tempfile
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Volkhov,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Soft,Volkhov,40,&H60DDEEFF,&H000000FF,&H60CCDDDD,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1
Style: Other,Volkhov,42,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
checks=[]
def check(label,value):
    assert value,label;checks.append(label)
def event(body,start=1,end=2,layer=0):
    return f'Dialogue: {layer},{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{{\\pos(320,100)}}{body}\n'
def parse(text):return list(s._resolve_document_state(s.parse_subtitle_document(HEADER+text)).events.values())
def spans(e):
    obj=s.static_object_key(e,e.styles,allow_unpositioned=True);assert obj
    return [(literal,dict(sig.formatting)) for sig,draw,literal in obj[-1]]
def paints(e):
    result=[]
    for literal,state in spans(e):
        p=tuple(state.get(k,state.get('bord',0) if k in ('xbord','ybord') else 0)
                for k in ('1c','1a','3c','3a','xbord','ybord'))
        if max(p[4:])==0 or p[3]>=255:p=p[:2]+(None,None,0,0)
        result.extend((char,p) for char in literal)
    return result
def fixture(body):
    # Fully hidden phases use different tag boundaries; correspondence is to
    # the same literal, not the number or spelling of override blocks.
    literal=s.OVERRIDE_RE.sub('',body)
    return event(body)+event(r'\alpha&HFF&'.join(['{','}'])+literal[:1]+r'{\alpha&HFF&}'+literal[1:],2,2.04)+event(r'{\alpha&HFF&}'+literal,2.04,2.08)
CASES=[('borderless then outlined',r'A{\bord1\3c&HDDDDDD&}B'),
       ('mixed colors and independent contour alpha',r'{\bord.5\1c&H112233&\3c&H223344&\3a&H40&}A{\bord1.5\1c&H445566&\3c&H667788&\3a&H80&}B'),
       ('gradient',r'{\bord1\1c&H102030&\3c&H204060&}A{\1c&H405060&\3c&H6080A0&}B{\1c&H708090&\3c&HA0C0E0&}C'),
       ('coupled base transparency',r'{\bord1\1c&HDDEEFF&\3c&HCCDDDD&\alpha&H60&}A{\bord0\1c&HFFEEDD&\1a&H40&}B'),
       ('named paint reset',r'A{\rSoft}B'),
       ('empty reset after outlined prefix',r'{\bord1\3c&HDDDDDD&}A{\r}B'),
       ('literal whitespace correspondence',r'{\bord1\1c&H102030&} A {\bord0\1c&H708090&} B ')]
for name,body in CASES:
    events=parse(fixture(body));before=deepcopy(events)
    resolved=s._normalize_inline_frame_paint(events)
    check(name+' complete source proof',resolved is not None)
    check(name+' whole span paint retained',all(paints(e)==paints(events[0]) for e in resolved))
    check(name+' literal/geometry/lifetime retained',all(
        s.OVERRIDE_RE.sub('',a.text)==s.OVERRIDE_RE.sub('',b.text) and a.start_s==b.start_s and
        a.end_s==b.end_s and a.state['pos']==b.state['pos'] for a,b in zip(events,resolved)))
    check(name+' source immutable',events==before and [e.text for e in events]==[e.text for e in before])
    compact=s.compact_static_overrides(resolved,0)
    check(name+' paint survives compaction',[paints(e) for e in compact]==[paints(e) for e in resolved])
    joined,count=s.merge_static_timed_copies(compact,compact[0].styles)
    check(name+' phases settle with all spans',len(joined)==1 and count==2 and paints(joined[0])==paints(events[0]))
# Selected foreground authority is per corresponding literal, not a pooled
# palette of contours elsewhere in the line or in another decorative copy.
for name,body in CASES:
    foreground=parse(event(body,layer=2))[0]
    back=parse(event(r'{\bord2\1c&H888888&\3c&H123456&}'+s.OVERRIDE_RE.sub('',body),layer=1))[0]
    ranges=s._literal_paint_ranges([foreground,back]);assert ranges
    contour_states=[state for _,states in ranges for state in states]
    out=s.static_text_paint_caption(foreground,contour_states,set(s.CAPTION_PAINT_TAGS)|{'alpha','c'},source_events=[foreground,back])
    check(name+' inline stack keeps foreground contour spans',out is not None and all(
        a==b or (a[1][4:]==(0,0) and b[1][4:]==(2.,2.))
        for a,b in zip(paints(foreground),paints(s.replace_event(foreground,text=out)))))
# Paint-only reset is accepted; genuine geometry changes remain outside this proof.
for name,body in [('font size',r'A{\fs42}B'),('named layout reset',r'A{\rOther}B'),
                  ('clip',r'{\clip(0,0,100,100)}AB')]:
    events=parse(fixture(body));check(name+' preserves uncertain family',s._normalize_inline_frame_paint(events) is None)
unknown=parse(event(r'A{\1a&HFF&}B')+event(r'{\1a&HFF&}AB',2,2.04)+event(r'{\1a&HFF&}AB',2.04,2.08))
resolved=s._normalize_inline_frame_paint(unknown)
check('never-visible spacing literal stays hidden',resolved is not None and all(
    p[1][1]==255 and p[1][4:]==(0,0) for e in resolved for p in paints(e) if p[0]=='B'))
parent=parse(event(r'A{\alpha&HFF&}B{\alpha&H00&}C'))[0]
out=s.static_text_paint_caption(parent,[parent.state],set(s.CAPTION_PAINT_TAGS)|{'alpha','c'})
check('inline producer cannot invent a contour on a fully hidden spacing glyph',out is not None and
    [p for p in paints(s.replace_event(parent,text=out)) if p[0]=='B'][0][1][1:]==(255,None,None,0,0))
changed=parse(event(r'{\bord1\3c&H112233&}AB')+event(r'{\bord1\3c&H445566&\1a&H80&}A{\alpha&HFF&}B',2,2.04)+event(r'{\alpha&HFF&}AB',2.04,2.08))
check('intentional temporal contour change remains a phase',s._normalize_inline_frame_paint(changed) is None)
# The existing two-level complete-palette rule is reused, including gradient veto.
tiny=parse(fixture(r'{\1c&HFFFFFF&\bord1\3c&H101010&}A{\1c&HFDFDFD&\3c&H121212&}B'))
resolved=s._normalize_inline_frame_paint(tiny)
check('tiny whole-family fill and contour palette normalized',resolved is not None and len({p for c,p in paints(resolved[0])})==1)
phase_tiny=parse(event(r'{\bord1\1c&HFFFFFF&\3c&H101010&}AB')+
    event(r'{\bord1\1c&HFDFDFD&\3c&H121212&\alpha&H40&}A{\alpha&HFF&}B',2,2.04)+
    event(r'{\alpha&HFF&}AB',2.04,2.08))
resolved=s._normalize_inline_frame_paint(phase_tiny)
check('tiny color changes across source phases share the bounded policy',resolved is not None and
    all(paints(e)==paints(phase_tiny[0]) for e in resolved))
phase_fade=parse(event(r'{\bord1\1c&H112233&\3c&H445566&\alpha&H60&}AB')+
    event(r'{\bord1\1c&H112233&\3c&H445566&\alpha&H90&}A{\alpha&HFF&}B',2,2.04)+
    event(r'{\alpha&HFF&}AB',2.04,2.08))
resolved=s._normalize_inline_frame_paint(phase_fade)
check('coupled fade settles at translucent authored base',resolved is not None and
    all(paints(e)==paints(phase_fade[0]) for e in resolved))
independent_fade=parse(event(r'{\bord1\3c&H445566&\3a&H60&}AB')+
    event(r'{\bord1\3c&H445566&\3a&H60&\1a&H80&}A{\alpha&HFF&}B',2,2.04)+
    event(r'{\alpha&HFF&}AB',2.04,2.08))
resolved=s._normalize_inline_frame_paint(independent_fade)
check('primary fade retains independent contour transparency',resolved is not None and
    all(paints(e)==paints(independent_fade[0]) for e in resolved))
ramp=parse(fixture(r'{\bord1\1c&H101010&}A{\1c&H121212&}B{\1c&H141414&}C'))
resolved=s._normalize_inline_frame_paint(ramp)
check('ordered ramp wider than two levels does not chain',resolved is not None and
    paints(resolved[0])==paints(ramp[0]))
source_alpha=parse(event(r'{\1a&H40&}A{\1a&H60&}B')+event(r'{\alpha&HFF&}AB',2,2.04))
resolved=s._normalize_inline_frame_paint(source_alpha)
check('pose support uses visibility of all literal spans',resolved is not None and
    resolved[0].evidence.frame_pose_intervals[0][2][0]==80 and
    resolved[1].evidence.frame_pose_intervals[0][2][0]==255)
moving=parse(event('AB',1,1.1)+''.join(event(r'{\alpha&HFF&}A{\alpha&HFF&}B',1.1+i*.08,1.18+i*.08).replace('320,100','320.4,100') for i in range(4)))
visible={e.source_index:'AB' for e in moving}
held,count=s.merge_frame_animation(moving,visible,merge_near_static=True)
check('restored hidden exit does not manufacture pose exposure',len(held)==1 and count==4
    and held[0].state['pos']==(320,100))
gradient_body=CASES[1][1]
moving=parse(fixture(gradient_body).replace('0:00:02.00,0:00:02.04,Default,,0,0,0,,{\\pos(320,100)}',
    '0:00:02.00,0:00:02.04,Default,,0,0,0,,{\\pos(320.4,100)}').replace(
    '0:00:02.04,0:00:02.08,Default,,0,0,0,,{\\pos(320,100)}',
    '0:00:02.04,0:00:02.08,Default,,0,0,0,,{\\pos(320.6,100)}'))
held,count=s.merge_frame_animation(moving,{e.source_index:'AB' for e in moving},merge_near_static=True)
check('proved inline paint uses existing motion bounds and preserves paint',len(held)==1 and count==2
    and paints(held[0])==paints(moving[0]) and held[0].state['pos']==(320,100))
unproved,count=s.freeze_vector_sequences(moving,near_static=True)
check('unproved inline geometry still keeps its original guard',len(unproved)==3 and count==0)
composite=parse(event(r'{\1c&H445566&}A{\1c&H778899&}B',layer=1)+
    event(r'{\1c&HCCDDEE&\1a&H60&}A{\1c&HEEDDCC&\1a&H40&}B',layer=2))
visible={e.source_index:'AB' for e in composite}
out,count=s.flatten_stacked_text_copies(composite,visible)
check('translucent composite needs a backing proof before removing fills',count==0 and
    [e.text for e in out]==[e.text for e in composite])
shadow=parse(event(r'{\xshad1000\4c&HFFFFFF&}A{\1c&HCCCCCC&}B').replace('320,100','-680,100'))[0]
shadow.measurement=s.DocumentMeasurementContext(canvas=(640,360))
check('inline shadow transfer keeps geometry ownership with its proof',s.static_text_paint_caption(
    shadow,[shadow.state],set(s.CAPTION_PAINT_TAGS)|{'alpha','c'}) is None)
# Full conversion must preserve source spans through later matching and output.
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for name,body in CASES:
        source=directory/(name+'.ass');out=directory/(name+'.simple.ass');again=directory/(name+'.again.ass')
        source.write_text(HEADER+fixture(body));original=source.read_bytes();report=s.FontProcessingReport()
        with contextlib.redirect_stdout(io.StringIO()):
            s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=metric,font_report=report)
            s.simplify_ass(out,again,s.SimplifyConfig(),font_metrics=metric)
        es=s.load_subtitle_events(out)[1]
        check(name+' pipeline exact fonts',not report.missing_families)
        check(name+' pipeline retains one complete owned caption',len(es)==1 and paints(es[0])==paints(parse(event(body))[0]) and (es[0].start_s,es[0].end_s)==(1,2.08))
        check(name+' pipeline source immutable',source.read_bytes()==original)
        check(name+' pipeline repeat stable',out.read_bytes()==again.read_bytes())
(ROOT/'validation/inline-paint-ownership-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,
    engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'whole-span paint ownership checks passed')
