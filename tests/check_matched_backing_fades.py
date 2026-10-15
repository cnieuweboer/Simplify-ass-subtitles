"""Shared caption fades carry proved backing paint without changing source poses."""
import test_paths
from pathlib import Path
from copy import deepcopy
import contextlib,hashlib,io,json,tempfile
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
PHASES=[(1,1.1,64),(1.1,1.3,0),(1.3,1.34,64),(1.34,1.38,180)]
checks=[]
def check(label,value):
    assert value,label;checks.append(label)
def row(body,start,end,layer):
    return f'Dialogue: {layer},{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{body}\n'
def fixture(*,phases=PHASES,projective=True,gradient=True,split=False,mutate=None,interleave=False):
    rows=[]
    for i,(start,end,alpha) in enumerate(phases):
        pos=(220+20*i,110+15*i)
        layout=f'\\an5\\pos({pos[0]},{pos[1]})'
        if projective:layout+=f'\\frz8\\frx1\\fry-4\\fax-.2\\org({pos[0]-7},{pos[1]})'
        for role in ('back','front'):
            a=alpha;extra=''
            if mutate:a,extra=mutate(i,role,alpha)
            head='{'+layout+f'\\alpha&H{a:02X}&'+extra+'}'
            if role=='back':
                body=r'{\bord6\1c&HEEEEEE&\3c&HEEEEEE&}AB '+(r'{\1c&HDDEEFF&\3c&HDDEEFF&}' if gradient else '')+'CD'
            else:
                body=r'{\bord0\1c&HCD8050&}AB '+(r'{\1c&HBC7040&}' if gradient else '')+'CD'
                if split:body=body.replace('AB',r'A{\1c&HCD8050&}B')
            rows.append(row(head+body,start,end,0))
            if role=='back' and interleave:rows.append(row(r'{\pos(250,120)}Independent',start,end,0))
    return HEADER+''.join(rows)
def parse(text):return list(s._resolve_document_state(s.parse_subtitle_document(text)).events.values())
def flatten(events):
    visible={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events}
    return s.flatten_stacked_text_copies(events,visible,set(),source_events={e.source_index:e for e in events},collect_rows=True)
def literal_paint(e):
    result=[]
    for sig,drawing,literal in s.static_object_key(e,e.styles,allow_unpositioned=True)[-1]:
        state=dict(sig.formatting)
        result.extend((char,tuple(state.get(k,state.get('bord',0) if k in ('xbord','ybord') else 0)
            for k in ('1c','3c','1a','3a','xbord','ybord'))) for char in literal)
    return result

for projective in (False,True):
    for gradient in (False,True):
        for split in (False,True):
            label=f'{projective}/{gradient}/{split}'
            events=parse(fixture(projective=projective,gradient=gradient,split=split));before=deepcopy(events)
            result=flatten(events)
            check(label+' one caption per phase',len(result.events)==4 and result.removed_count==4)
            check(label+' original immutable',events==before)
            for i,out in enumerate(sorted(result.events,key=lambda e:e.start_s)):
                front=events[2*i+1];back=events[2*i]
                ranges=s._literal_paint_ranges([front,back]);expected=[]
                for fragment,states in ranges:
                    expected.extend((c,(states[0]['1c'],states[1]['3c'],PHASES[i][2],PHASES[i][2],2.,2.)) for c in fragment)
                check(label+f' {i} complete gradient and coupled alpha',literal_paint(out)==expected)
                check(label+f' {i} literal geometry and interval',
                    s.static_text_paint_geometry(out,set(s.CAPTION_PAINT_TAGS))[0]==
                    s.static_text_paint_geometry(front,set(s.CAPTION_PAINT_TAGS))[0] and
                    (out.start,out.end)==(front.start,front.end))
            check(label+' repeat stack reduction stable',[e.fields() for e in flatten(result.events).events]==[e.fields() for e in result.events])

# Splitting a readable hold does not remove or manufacture the temporal proof.
split_phases=[(1,1.1,64),(1.1,1.2,0),(1.2,1.3,0),(1.3,1.34,64),(1.34,1.38,180)]
check('split opaque support still proves all fade phases',len(flatten(parse(fixture(phases=split_phases))).events)==5)
for label,changes in [
    ('different fades',dict(mutate=lambda i,r,a:(a if r=='front' else min(255,a+1),''))),
    ('shifted foreground',dict(mutate=lambda i,r,a:(a,r'\frz9' if i==2 and r=='front' else ''))),
    ('no opaque support',dict(phases=[(1,1.1,64),(1.1,1.2,100),(1.2,1.3,180)])),
    ('opacity reversal',dict(phases=[(1,1.1,0),(1.1,1.2,100),(1.2,1.3,64),(1.3,1.4,180)])),
    ('returning pulse',dict(phases=[(1,1.1,0),(1.1,1.2,100),(1.2,1.3,0),(1.3,1.4,180)])),
    ('interleaved object',dict(interleave=True)),
    ('masked source',dict(mutate=lambda i,r,a:(a,r'\clip(0,0,640,360)'))),
    ('independent contour fade',dict(mutate=lambda i,r,a:(a,r'\3a&H80&' if i==2 and r=='back' else ''))),
    ('independent shadow',dict(mutate=lambda i,r,a:(a,r'\xshad3' if r=='back' else ''))),
    ('no readable hold',dict(phases=[(1,1.1,64),(1.1,1.11,0),(1.11,1.2,180)])),
    ('separate cues',dict(phases=[(1,1.1,0),(1.2,1.3,100),(1.3,1.4,180)]))]:
    events=parse(fixture(**changes))
    context,_=s._prepare_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},set(),.16,{e.source_index:e for e in events})
    check(label+' keeps uncertain composite guard',not context.matched_backing_fades)
    last=max(e.start_s for e in events)
    check(label+' faint planes remain separate',sum(e.start_s==last and s.OVERRIDE_RE.sub('',e.text)=='AB CD'
        for e in flatten(events).events)==2)
events=parse(fixture());events[-1]=s.replace_event(events[-1],text=events[-1].text[:-2]+r'{\1c&H0000FF&}CD')
context,_=s._prepare_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},set(),.16,{e.source_index:e for e in events})
check('intentional temporal color remains independent',not context.matched_backing_fades)
events=parse(fixture());events[-1]=s.replace_event(events[-1],text=events[-1].text[:-2]+r'{\1c&HBD7141&}CD')
context,_=s._prepare_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},set(),.16,{e.source_index:e for e in events})
check('tiny temporal palette uses existing two-level bound',len(context.matched_backing_fades)==3)
events=parse(fixture());masked={e.source_index:e for e in events}
masked[events[-1].source_index]=s.replace_event(events[-1],text=r'{\clip(0,0,640,360)}'+events[-1].text)
context,_=s._prepare_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},set(),.16,masked)
check('earlier mask removal cannot manufacture source proof',not context.matched_backing_fades)
masked[events[-1].source_index]=s.replace_event(events[-1],text=r'{\t(0,40,\clip(0,0,640,360))}'+events[-1].text)
context,_=s._prepare_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},set(),.16,masked)
check('earlier animated mask removal cannot manufacture source proof',not context.matched_backing_fades)
events=parse(fixture().replace(r'\bord6',r'\bord0\xbord0\ybord6'))
result=flatten(events)
check('axis-specific backing contour preserved',len(result.events)==4 and all(
    paint[-2:]==(0.,2.) for e in result.events for char,paint in literal_paint(e)))
events=parse(fixture(interleave=True))
events=[s.replace_event(e,layer='unknown') if s.OVERRIDE_RE.sub('',e.text)=='Independent' else e for e in events]
context,_=s._prepare_stacked_text_copies(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events},set(),.16,{e.source_index:e for e in events})
check('unknown compositing order cannot authorize removal',not context.matched_backing_fades)

metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
with tempfile.TemporaryDirectory() as directory:
    source=Path(directory)/'source.ass';output=Path(directory)/'simple.ass';again=Path(directory)/'again.ass'
    source.write_text(fixture());before=source.read_bytes();report=s.FontProcessingReport()
    with contextlib.redirect_stdout(io.StringIO()):
        s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metric,font_report=report)
        s.simplify_ass(output,again,s.SimplifyConfig(),font_metrics=metric)
    check('full pipeline exact font',not report.missing_families)
    check('full pipeline preserves source',before==source.read_bytes())
    check('full pipeline four scrolling phases',len(s.load_subtitle_events(output)[1])==4)
    check('full pipeline repeat stable',output.read_bytes()==again.read_bytes())

(ROOT/'validation/matched-backing-fade-checks.json').write_text(json.dumps(dict(version=s.__version__,
    engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'matched backing fade checks passed')
