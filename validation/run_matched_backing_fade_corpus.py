"""Fresh v203 comparison against v202 regenerated with the same embedded fonts."""
from pathlib import Path
from collections import Counter
import argparse,concurrent.futures,contextlib,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/matched-backing-fade-corpus';BASE=DEST/'v202';CURRENT=DEST/'v203'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--case')
parser.add_argument('--baseline-only',action='store_true',help='Regenerate v202 with current fonts before comparing')
parser.add_argument('--baseline-engine',type=Path,default=ROOT/'validation/outline-policy-corpus/simplify_ass_v202.py')
args=parser.parse_args()
cases=json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
cases.append(dict(name='Goblin-Slayer-S01E02-track6',source='test-data/Goblin-Slayer-S01E02-track6-source.ass',sha256='476e93d4d162af152b6ddddf4f715f301bec7373e67e8645c220b8360d38d017'))
engine_hash=sha(ROOT/'simplify_ass.py');baseline_hash='39a9502602d77636b5e6ceb3b682246c1a038c48eae7f86038b32e7d95fcd91d'
font_hashes={str(p.relative_to(ROOT/'fonts')):sha(p) for p in sorted((ROOT/'fonts').rglob('*')) if p.is_file()}
def geometry(e):
    if e.kind!='Dialogue':return None
    profile=s.static_text_paint_geometry(e,set(s.CAPTION_PAINT_TAGS))
    return (tuple(e.fields()[1:-1]),profile[0]) if profile is not None else None
def record(e):
    if e.kind!='Dialogue':return e.kind,tuple(e.fields())
    obj=s.static_object_key(e,e.styles,allow_unpositioned=True);assert obj is not None
    spans=[]
    for sig,draw,literal in obj[-1]:
        state={'blur':0.,'be':0.,**dict(sig.formatting)}
        fields=tuple(sorted((k,v) for k,v in state.items() if k not in {'2c','2a','4c','4a'}))
        spans.extend((c,draw,fields) for c in literal)
    return tuple(e.fields()[:-1]),tuple(spans)
if args.baseline_only:
    assert sha(args.baseline_engine)==baseline_hash
    env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
    def baseline(case):
        source=ROOT/case['source'];assert sha(source)==case['sha256']
        output=BASE/(case['name']+'.ass')
        subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(args.baseline_engine),
            '--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],env=env,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        report=json.loads(output.with_suffix('.json').read_text());assert not report['missing_families']
        print(case['name'],'v202 current-font baseline',report['statistics']['output'],flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(baseline,cases))
    assert font_hashes=={str(p.relative_to(ROOT/'fonts')):sha(p) for p in sorted((ROOT/'fonts').rglob('*')) if p.is_file()}
    (BASE/'font-sha256.json').write_text(json.dumps(font_hashes,indent=2)+'\n')
elif args.case:
    assert json.loads((BASE/'font-sha256.json').read_text())==font_hashes,'Regenerate the baseline for these fonts'
    case=next(c for c in cases if c['name']==args.case);source=ROOT/case['source'];output=CURRENT/(case['name']+'.ass');output.parent.mkdir(parents=True,exist_ok=True)
    previous=json.loads((BASE/output.name).with_suffix('.json').read_text())
    assert sha(source)==case['sha256']==previous['source_sha256'] and previous['engine_sha256']==baseline_hash
    assert sha(BASE/output.name)==previous['output_sha256'] and not previous['missing_families']
    witnesses=[];index=s._index_matched_backing_fades
    def capture(context,events):
        proofs=index(context,events)
        witnesses.extend(proofs.values())
        return proofs
    s._index_matched_backing_fades=capture
    metrics=s.FontMetrics([ROOT/'fonts']);report=s.FontProcessingReport();started=time.perf_counter()
    try:
        with output.with_suffix('.log').open('w') as log,contextlib.redirect_stdout(log):
            stats=s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metrics,font_report=report)
    finally:s._index_matched_backing_fades=index
    assert not report.missing_families and sha(source)==case['sha256'] and sha(ROOT/'simplify_ass.py')==engine_hash
    before=s.load_subtitle_events(BASE/output.name)[1];after=s.load_subtitle_events(output)[1]
    old=Counter(record(e) for e in before);new=Counter(record(e) for e in after)
    changed_before=old-new;changed_after=new-old
    expected=[s._render_matched_backing_fade(p,set(s.CAPTION_PAINT_TAGS)|{'alpha','c'}) for p in witnesses]
    allowed={geometry(e) for e in expected}
    allowed_paint={record(e) for e in expected}
    allowed_before={geometry(e) for p in witnesses for e in (p.foreground,p.backing)}|allowed
    unexplained_before=[e for e in before if changed_before[record(e)] and geometry(e) not in allowed_before]
    unexplained_after=[e for e in after if changed_after[record(e)] and geometry(e) not in allowed]
    assert not unexplained_before,(case['name'],'unproved old geometry',[(e.start,s.OVERRIDE_RE.sub('',e.text)) for e in unexplained_before[:5]])
    assert not unexplained_after,(case['name'],'unproved new geometry',[(e.start,s.OVERRIDE_RE.sub('',e.text)) for e in unexplained_after[:5]])
    assert all(record(e) in allowed_paint for e in after if changed_after[record(e)]),case['name']+' unproved final span paint'
    result=dict(case=case['name'],engine_sha256=engine_hash,baseline_engine_sha256=baseline_hash,
        source_sha256=sha(source),output_sha256=sha(output),statistics=stats,missing_families=[],
        output_bytes_identical=sha(output)==previous['output_sha256'],before_count=len(before),after_count=len(after),
        changed_before=sum(changed_before.values()),changed_after=sum(changed_after.values()),
        proved_fade_pairs=len(witnesses),proved_literals=dict(Counter(p.literal for p in witnesses)),
        source_geometry_timing_preserved=True,wall_s=time.perf_counter()-started)
    output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n');print(case['name'],result['before_count'],result['after_count'],'proved',len(witnesses),result['proved_literals'],flush=True)
else:
    assert json.loads((BASE/'font-sha256.json').read_text())==font_hashes,'Regenerate the baseline for these fonts'
    env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
    def run(c):
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--case',c['name']],cwd=ROOT,env=env,check=True)
        return json.loads((CURRENT/(c['name']+'.json')).read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,cases))
    assert sha(ROOT/'simplify_ass.py')==engine_hash
    assert font_hashes=={str(p.relative_to(ROOT/'fonts')):sha(p) for p in sorted((ROOT/'fonts').rglob('*')) if p.is_file()}
    (DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=engine_hash,baseline_engine_sha256=baseline_hash,font_sha256=font_hashes,cases=results),indent=2)+'\n')
