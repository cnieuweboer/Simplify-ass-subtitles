"""Fresh inline ownership comparison against hash-verified v200 corpus outputs."""
from pathlib import Path
from collections import Counter,defaultdict
import contextlib,hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/inline-paint-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
BASE=ROOT/'validation/frame-pose-corpus/windows'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
reference_hash='24e9c9b28f22e0a4d0c4a9f0c1a9313bea077709916a29edefb46b5b4ab574e2'
engine_hash=sha(ROOT/'simplify_ass.py')
cases=json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
cases.append(dict(name='Goblin-Slayer-S01E02-track6',source='test-data/Goblin-Slayer-S01E02-track6-source.ass',sha256='476e93d4d162af152b6ddddf4f715f301bec7373e67e8645c220b8360d38d017'))
def timeline(events,omit_paint=False):
    changes=defaultdict(Counter)
    for e in events:
        if e.kind!='Dialogue':continue
        obj=s.static_object_key(e,e.styles,allow_unpositioned=True);assert obj is not None
        runs=[]
        for signature,drawing,literal in obj[-1]:
            formatting=tuple((k,v) for k,v in signature.formatting if not (omit_paint and k in set(s.CAPTION_PAINT_TAGS)))
            sig=(formatting,signature.continuation,drawing)
            if runs and runs[-1][0]==sig:runs[-1]=(sig,runs[-1][1]+literal)
            else:runs.append((sig,literal))
        k=obj[:-1]+(tuple(runs),);changes[e.start_s][k]+=1;changes[e.end_s][k]-=1
    active=Counter();result=[]
    for at,delta in sorted(changes.items()):
        active.update(delta);active=+active
        if not result or result[-1][1]!=active:result.append((at,active.copy()))
    return result

def span_record(e,paint=True):
    if e.kind!='Dialogue':return (e.kind,tuple(e.fields()))
    obj=s.static_object_key(e,e.styles,allow_unpositioned=True);assert obj
    unused={'2c','2a','4c','4a'}
    omit=unused if paint else set(s.CAPTION_PAINT_TAGS)
    result=[]
    for signature,drawing,literal in obj[-1]:
        state={'blur':0.,'be':0.,**dict(signature.formatting)}
        fields=tuple(sorted((k,v) for k,v in state.items() if k not in omit))
        result.extend((char,fields,drawing) for char in literal)
    return (tuple(e.fields()[:-1]),tuple(result))
metrics=s.FontMetrics([ROOT/'fonts']);results=[]
for case in cases:
    source=ROOT/case['source'];baseline=BASE/(case['name']+'.ass')
    previous=json.loads(baseline.with_suffix('.json').read_text())
    assert sha(source)==case['sha256']==previous['source_sha256']
    assert previous['engine_sha256']==reference_hash and previous['output_sha256']==sha(baseline)
    assert not previous['missing_families']
    output=DEST/baseline.name;report=s.FontProcessingReport();start=time.perf_counter()
    retained=[];select=s._select_inline_stacked_text_foreground
    def capture(context,key,peers,spans):
        selected=select(context,key,peers,spans)
        if selected is None:retained.extend(peers)
        return selected
    s._select_inline_stacked_text_foreground=capture
    try:
        with output.with_suffix('.log').open('w') as log,contextlib.redirect_stdout(log):
            stats=s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metrics,font_report=report)
    finally:s._select_inline_stacked_text_foreground=select
    elapsed=time.perf_counter()-start
    assert not report.missing_families and sha(source)==case['sha256']
    before=s.load_subtitle_events(baseline)[1];after=s.load_subtitle_events(output)[1]
    identical=timeline(before)==timeline(after)
    geometry_identical=timeline(before,True)==timeline(after,True)
    available=Counter(span_record(e,False) for e in before);added=[]
    for e in after:
        key=span_record(e,False)
        if available[key]:available[key]-=1
        else:added.append(e)
    assert not +available,case['name']+' lost or changed existing literal geometry/timing/order fields'
    source_records={span_record(e) for e in retained}
    unmatched=[e for e in added if span_record(e) not in source_records]
    assert not unmatched,case['name']+' added record lacks a retained source paint witness'
    record=dict(case=case['name'],engine_sha256=engine_hash,source_sha256=sha(source),output_sha256=sha(output),statistics=stats,
        missing_families=[],wall_s=elapsed,before_count=len(before),after_count=len(after),
        output_bytes_identical=sha(output)==sha(baseline),full_timeline_identical=identical,
        geometry_content_visibility_identical=geometry_identical,
        existing_geometry_timing_preserved=True,retained_composite_records=len(added))
    results.append(record);output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
    (DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=engine_hash,cases=results),indent=2)+'\n')
    print(case['name'],len(before),len(after),'bytes same',record['output_bytes_identical'],'paint timeline same',identical,'geometry same',geometry_identical,flush=True)
assert sha(ROOT/'simplify_ass.py')==engine_hash,'Runtime changed during corpus validation'
assert len(results)==10
