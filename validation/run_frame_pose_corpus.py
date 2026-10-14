"""Fresh v200 corpus: unchanged content/paint/timing and witnessed source poses."""
from pathlib import Path
from collections import Counter,defaultdict
import contextlib,hashlib,io,json,os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s

DEST=ROOT/'validation/frame-pose-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
BASELINE=ROOT/'validation/current-policy-corpus/windows'
reference_hash='ab030e08b3162dcb59a8e7ad9386231f0d0945b7ab5639651dc31ddc12d034c8'
POSE=frozenset({'pos','org','fscx','fscy','frz','frx','fry','fax','fay'})
cases=json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
cases.append(dict(name='Goblin-Slayer-S01E02-track6',source='test-data/Goblin-Slayer-S01E02-track6-source.ass',
                  sha256='476e93d4d162af152b6ddddf4f715f301bec7373e67e8645c220b8360d38d017'))
def key(e,omit_pose=False):
    obj=s.static_object_key(e,e.styles,allow_unpositioned=True)
    assert obj is not None,(e.kind,e.text)
    spans=[]
    for signature,drawing,literal in obj[-1]:
        state=tuple((k,v) for k,v in signature.formatting if not (omit_pose and k in POSE))
        signature=(state,signature.continuation,drawing)
        if spans and spans[-1][0]==signature:spans[-1]=(signature,spans[-1][1]+literal)
        else:spans.append((signature,literal))
    return obj[:-1]+(tuple(spans),)
def timeline(events,omit_pose=False):
    changes=defaultdict(Counter)
    for e in events:
        if e.kind!='Dialogue':continue
        k=key(e,omit_pose);changes[e.start_s][k]+=1;changes[e.end_s][k]-=1
    live=Counter();result=[]
    for at,delta in sorted(changes.items()):
        live.update(delta);live=+live
        if not result or live!=result[-1][1]:result.append((at,live.copy()))
    return result
def pose(e):return tuple(e.state.get(k,s.DEFAULT_STATE.get(k)) for k in sorted(POSE))
def close(a,b):
    if isinstance(a,(tuple,list)) and isinstance(b,(tuple,list)):
        return len(a)==len(b) and all(close(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return abs(a-b)<=.011
    return a==b

engine_hash=sha(ROOT/'simplify_ass.py')
metrics=s.FontMetrics([ROOT/'fonts']);results=[]
for case in cases:
    source=ROOT/case['source'];baseline=BASELINE/(case['name']+'.ass')
    previous=json.loads(baseline.with_suffix('.json').read_text())
    assert sha(source)==case['sha256']==previous['source_sha256']
    assert previous['engine_sha256']==reference_hash and previous['output_sha256']==sha(baseline)
    assert not previous['missing_families']
    witnessed={};real=s._representative_frame_pose
    def capture(events):
        # Selection must always return a real supplied candidate. The before/after
        # comparison below also checks that changed final poses have that witness.
        chosen,intervals=real(events)
        assert any(chosen is e for e in events)
        witnessed.update((id(e),e) for e in events)
        return chosen,intervals
    s._representative_frame_pose=capture
    output=DEST/baseline.name;report=s.FontProcessingReport()
    import time
    started=time.perf_counter()
    try:
        with output.with_suffix('.log').open('w') as log,contextlib.redirect_stdout(log):
            stats=s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metrics,font_report=report)
    finally:s._representative_frame_pose=real
    elapsed=time.perf_counter()-started
    assert not report.missing_families,(case['name'],report.missing_families)
    assert sha(source)==case['sha256']
    before=s.load_subtitle_events(baseline)[1];after=s.load_subtitle_events(output)[1]
    assert timeline(before,True)==timeline(after,True),case['name']+' content/paint/font/layer/timing changed'
    changed=[]
    for e in after:
        if e.kind!='Dialogue':continue
        peers=[p for p in before if p.kind=='Dialogue' and p.start_s<e.end_s and p.end_s>e.start_s and key(p,True)==key(e,True)]
        if any(close(pose(p),pose(e)) for p in peers):continue
        matches=[p for p in witnessed.values() if p.style==e.style and p.name==e.name and
            s.OVERRIDE_RE.sub('',p.text)==s.OVERRIDE_RE.sub('',e.text) and
            p.start_s<e.end_s and p.end_s>e.start_s and close(pose(p),pose(e))]
        assert matches,(case['name'],e.style,e.text,'changed pose has no supplied source/derived candidate')
        changed.append(dict(style=e.style,text=s.OVERRIDE_RE.sub('',e.text),start_s=e.start_s,end_s=e.end_s,
                            before=[pose(p) for p in peers],after=pose(e)))
    assert sha(ROOT/'simplify_ass.py')==engine_hash,'Runtime changed during corpus validation'
    record=dict(case=case['name'],source_sha256=sha(source),engine_sha256=engine_hash,
        output_sha256=sha(output),statistics=stats,missing_families=[],wall_s=elapsed,
        output_bytes_identical=sha(output)==sha(baseline),paint_content_visibility_identical=True,
        full_timeline_identical=timeline(before)==timeline(after),pose_changes=changed,
        before_count=len(before),after_count=len(after),baseline_wall_s=previous['wall_s'])
    results.append(record);output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
    (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,cases=results,
        engine_sha256=sha(ROOT/'simplify_ass.py'),runner_sha256=sha(Path(__file__))),indent=2)+'\n')
    print(case['name'],'records',len(before),len(after),'changed poses',len(changed),
          'unchanged bytes',record['output_bytes_identical'],'seconds',round(elapsed,3),flush=True)
assert len(results)==10
