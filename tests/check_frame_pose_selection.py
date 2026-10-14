"""Source frame support survives repainting, splitting, copies and repeated joins."""
import test_paths
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import contextlib,hashlib,io,json,random,tempfile
import simplify_ass as s

ROOT=Path(__file__).resolve().parents[1]
HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Volkhov,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
checks=[]
def check(label,condition):
    assert condition,label;checks.append(label)
def records(specs,*,layer=0,tags='',literal='Moving sign'):
    return ''.join(f'Dialogue: {layer},{s.format_time(a)},{s.format_time(b)},Default,,0,0,0,,'+
        rf'{{\pos({x},100)\1c&HFFFFFF&\3c&HDDDDDD&\alpha&H{alpha:02X}&{tags}}}'+literal+'\n'
        for a,b,x,alpha in specs)
def parse(specs,**kw):
    doc=s._resolve_document_state(s.parse_subtitle_document(HEADER+records(specs,**kw)))
    return list(doc.events.values())
def annotate(events):
    return [replace(e,evidence=s.EventEvidence(frame_pose_intervals=s._frame_pose_intervals(e))) for e in events]
def repaint(events):
    return [s.replace_event(e,text=e.text.replace('}',r'\alpha&H00&\3c&HCCCCCC&}',1)) for e in events]
def select(events):return s._representative_frame_pose(events)[0].state['pos']
def freeze(events,near=False):return s.freeze_vector_sequences(events,near_static=near)

SPECS=[(1,1.14,300,190),(1.14,1.19,320,0),(1.19,1.24,330,0),
       (1.24,1.29,330,0),(1.29,1.34,340,0),(1.34,1.48,360,220)]
source=annotate(parse(SPECS));before=deepcopy(source)
check('strongest source pose with most support selected',select(source)==(330,100))
normalized=repaint(source)
check('repainted output does not change source selection',select(normalized)==(330,100))
check('repaint keeps immutable source support',all(a.evidence.frame_pose_intervals == b.evidence.frame_pose_intervals
    for a,b in zip(source,normalized)))
check('source/cache/style inputs remain unchanged',[vars(e) for e in source]==[vars(e) for e in before])

split=[(1,1.14,300,190),(1.14,1.19,320,0)]+[
    (1.19+i*.01,1.20+i*.01,330,0) for i in range(10)]+[(1.29,1.34,340,0),(1.34,1.48,360,220)]
split_source=annotate(parse(split))
check('split pose retains its full accumulated support',select(split_source)==(330,100))
check('split plus normalized paint is invariant',select(repaint(split_source))==(330,100))
for order in ('forward','reverse','shuffle'):
    peers=list(normalized)
    if order=='reverse':peers.reverse()
    if order=='shuffle':random.Random(200).shuffle(peers)
    check(order+' selection order independent',select(peers)==(330,100))
    peers=[replace(e,source_index=999-i) for i,e in enumerate(peers)]
    check(order+' synthetic IDs do not decide geometry',select(peers)==(330,100))
# Many coincident records cannot give a weaker pose extra exposure.
duplicates=[*normalized,*[replace(normalized[1],source_index=1000+i) for i in range(20)]]
check('redundant copies do not inflate dwell',select(duplicates)==(330,100))

# A merged event's replacement lifetime must not become a new geometry vote.
chosen,intervals=s._representative_frame_pose(source)
expanded=s.replace_event(chosen,start=s.format_time(1),start_s=1,end=s.format_time(1.48),end_s=1.48,
    evidence=replace(chosen.evidence,frame_pose_intervals=intervals))
competitor=annotate(parse([(1.48,1.60,340,0)]))[0]
check('extended display time is not source dwell',select([expanded,competitor])==(340,100))
trimmed=s.replace_event(expanded,start=s.format_time(1.25),start_s=1.25)
check('source support clipped to surviving lifetime',sum(b-a for a,b,alpha in s._frame_pose_intervals(trimmed))<.041)

# Nominally equal ASS frame durations cannot be ranked by float subtraction.
ties=parse([(725.57,725.62,300,0),(725.62,725.66,320,0),(725.66,725.71,340,0)])
check('equal real dwell uses central support then earliest deterministic tie',select(ties)==(300,100))
equal=[replace(e,start_s=e.start_s+10000,end_s=e.end_s+10000) for e in ties]
check('time origin does not break nominal duration ties',select(equal)==(300,100))

# Source channel evidence recognizes real outline/shadow paint, not unused alpha.
outline=parse([(1,1.08,300,0),(1.08,1.18,330,0),(1.18,1.26,340,0)],tags=r'\1a&HFF&')
check('outline-only visibility uses outline channel',select(outline)==(330,100))
shadow=parse([(1,1.08,300,0),(1.08,1.18,330,0),(1.18,1.26,340,0)],tags=r'\1a&HFF&\3a&HFF&\shad2')
check('shadow-only visibility uses actual shadow channel',select(shadow)==(330,100))
no_shadow=parse(SPECS,tags=r'\4a&H00&')
check('unused opaque shadow cannot outrank foreground',select(no_shadow)==(330,100))
check('sustained readable hold beats brief opaque flash',select(parse([
    (1,1.2,320,64),(1.2,1.24,330,0)]))==(320,100))
check('equal dwell at a handoff selects the half-open central frame',select(parse([
    (1,1.1,320,0),(1.1,1.2,330,0)]))==(330,100))
hidden=parse([(1,1.1,320,255),(1.1,1.2,330,255)])
check('fully hidden fallback independent of input order',select(hidden)==select(list(reversed(hidden))))
readable=annotate(parse([(1,1.2,320,64),(1.2,1.24,330,0),(1.24,1.28,340,200)]))
held,count=freeze(readable)
check('frame pose and unfaded paint chosen independently',count==2 and held[0].state['pos']==(320,100)
    and held[0].state['1a']==0 and held[0].state['3a']==0)
check('unfaded paint does not rewrite source opacity evidence',
    held[0].evidence.frame_pose_intervals==readable[0].evidence.frame_pose_intervals)

# Formatting edits keep support only for the same literal and geometry.
base=source[2]
for label,text in [('position',base.text.replace('330,100','331,100')),
                   ('font',base.text.replace('}',r'\fnArial}',1)),
                   ('size',base.text.replace('}',r'\fs41}',1)),
                   ('clip',base.text.replace('}',r'\clip(0,0,640,360)}',1)),
                   ('literal',base.text+'!'),
                   ('inline geometry',base.text+'{\\fs50}X{\\fs40}Y')]:
    check(label+' invalidates old source support',s.replace_event(base,text=text).evidence.frame_pose_intervals is None)
check('measurement boundary invalidates old support',s.replace_event(base,
    measurement=s.DocumentMeasurementContext((1280,720))).evidence.frame_pose_intervals is None)
history=s.EventEvidence(((1,2),(3,4)),((1,1.2),),base.evidence.frame_pose_intervals)
with_history=replace(base,evidence=history)
paint_edit=repaint([with_history])[0]
check('paint edits do not resurrect contour/opaque-span proofs',paint_edit.evidence.original_contour_points is None and
    paint_edit.evidence.opaque_spans is None and paint_edit.evidence.frame_pose_intervals==history.frame_pose_intervals)

# Both frame-freezer stages consume the same source-based selection.
for specs in (SPECS,split):
    for near in (False,True):
        events=repaint(annotate(parse(specs)))
        out,count=freeze(events,near)
        check('frame stage '+str((len(events),near))+' reduces frames',len(out)==1 and count==len(events)-1)
        check('frame stage '+str((len(events),near))+' selected source pose',out[0].state['pos']==(330,100))
        check('frame stage '+str((len(events),near))+' source timing preserved',out[0].start_s==1 and out[0].end_s==1.48)
        check('frame stage '+str((len(events),near))+' repeats stably',freeze(out,near)==(out,0))

# Already static neighboring holds can settle bounded jitter without assigning
# one pose the extended display time of a previously frozen moving sequence.
small=parse([(1,2,320,0),(2,2.1,320.2,0),(2.1,3.1,320.4,0)])
out,count=freeze(small,True)
check('bounded near-static holds use same dwell policy',count==2 and out[0].state['pos']==(320,100))
check('real gaps stay separate',len(freeze(parse([(1,2,320,0),(2.02,3,320.2,0)]),True)[0])==2)
drift=parse([(1+i*.2,1+(i+1)*.2,320+i*.2,0) for i in range(12)])
out,count=freeze(drift,True)
check('bounded jitter cannot follow cumulative drift',len(out)>1 and all(
    s._near_static_frame_fits(e,p) for e in out for p in drift
    if p.start_s>=e.start_s-1e-6 and p.end_s<=e.end_s+1e-6))
check('final bound also checked against the selected source pose',
    len(freeze(parse([(1,1.2,320,0),(1.2,1.4,319.3,0),(1.4,2.4,320.7,0)]),True)[0])==3)

# Full conversion verifies the producer capture before real paint stacks make
# source fades opaque. Splitting frames and adding duplicate source paint copies
# must produce the same selected geometry, literal and source lifetime.
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
outputs=[]
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for i,specs in enumerate((SPECS,split)):
        for copies in (2,3):
            path=directory/f'{i}-{copies}.source.ass';output=path.with_suffix('.simple.ass')
            pipeline_specs=[(a,b,x,min(alpha,110)) for a,b,x,alpha in specs]
            path.write_text(HEADER+''.join(records(pipeline_specs,layer=layer,
                tags=r'\1c&HDDDDDD&\bord4\blur4' if layer==0 else '') for layer in range(copies)))
            original=path.read_bytes();report=s.FontProcessingReport()
            with contextlib.redirect_stdout(io.StringIO()):
                stats=s.simplify_ass(path,output,s.SimplifyConfig(),font_metrics=metric,font_report=report)
            events=[e for e in s.load_subtitle_events(output)[1] if e.kind=='Dialogue']
            check('pipeline '+str((i,copies))+' exact fonts available',not report.missing_families)
            check('pipeline '+str((i,copies))+' one complete source cue',len(events)==1 and
                events[0].state['pos']==(330,100) and s.OVERRIDE_RE.sub('',events[0].text)=='Moving sign' and
                events[0].start_s==1 and events[0].end_s==1.48)
            check('pipeline '+str((i,copies))+' source immutable',path.read_bytes()==original)
            outputs.append(events[0].fields())
    check('all full-pipeline representations equivalent',all(v==outputs[0] for v in outputs))

(ROOT/'validation/frame-pose-selection-checks.json').write_text(json.dumps(dict(version=s.__version__,
    checks_passed=len(checks),checks=checks,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'source frame pose checks passed')
