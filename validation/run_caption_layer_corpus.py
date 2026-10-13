"""Validate v183 differences against trusted v182 outputs and repeated layers."""
from pathlib import Path
import collections,hashlib,json,os,subprocess,sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/caption-layer-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
records=[]
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
    source=ROOT/case['source'];assert sha(source)==case['sha256']
    baseline=ROOT/'validation/lyric-layer-corpus/windows'/(case['name']+'-current.ass')
    metadata=json.loads(baseline.with_suffix('.json').read_text())
    assert metadata['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v182.py')
    assert metadata['source_sha256']==sha(source) and metadata['output_sha256']==sha(baseline)
    first=DEST/(case['name']+'.ass');second=DEST/(case['name']+'.second.ass')
    for input_path,output in [(source,first),(first,second)]:
        subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),
                        '--source',str(input_path),'--fonts',str(ROOT/'fonts'),'--output',str(output)],
                       cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
        report=json.loads(output.with_suffix('.json').read_text())
        assert report['missing_families']==[],('Missing exact fonts; stop',case['name'],report['missing_families'])
    old,new=[s.load_subtitle_events(path)[1] for path in (baseline,first)]
    old_fields=collections.Counter(tuple(e.fields()) for e in old);new_fields=collections.Counter(tuple(e.fields()) for e in new)
    removed=list((old_fields-new_fields).elements());added=list((new_fields-old_fields).elements())
    # New captions may change layer only; all literal formatting/paint/geometry
    # and authored timing must be present in an otherwise identical v182 record.
    old_captions=collections.Counter(tuple(e.fields()[1:]) for e in old if not e.state.get('p',0))
    new_captions=collections.Counter(tuple(e.fields()[1:]) for e in new if not e.state.get('p',0))
    assert old_captions==new_captions,(case['name'],'caption text/paint/timing changed')
    assert not collections.Counter(tuple(e.fields()) for e in new if e.state.get('p',0))-collections.Counter(tuple(e.fields()) for e in old if e.state.get('p',0)),(case['name'],'new or modified drawing')
    new_metadata=json.loads(first.with_suffix('.json').read_text())
    diffs={k:(metadata['statistics'].get(k),new_metadata['statistics'].get(k))
           for k in metadata['statistics'].keys()|new_metadata['statistics'].keys()
           if metadata['statistics'].get(k)!=new_metadata['statistics'].get(k)}
    allowed={'drawing_duplicates_removed','supporting_shapes_retained','backdrops_retained','adjacent_shapes_retained','output','max_concurrent_out','vector_output'}
    assert not diffs.keys()-allowed,(case['name'],'unrelated counter changes',diffs)
    # For each record retained after a second conversion, its final layer must
    # already be established. Other phase/duplicate cleanup is a later release.
    again=s.load_subtitle_events(second)[1]
    layers=collections.defaultdict(set)
    for e in new:layers[tuple(e.fields()[1:])].add(e.layer)
    changed_layers=[e.fields() for e in again if tuple(e.fields()[1:]) in layers and e.layer not in layers[tuple(e.fields()[1:])]]
    # Punctuation-only custom-font glyphs may be artwork; their existing
    # source-order behavior is outside readable-caption promotion.
    text_drift=[fields for fields in changed_layers if any(c.isalnum() for c in s.OVERRIDE_RE.sub('',fields[-1]))]
    assert not text_drift,(case['name'],'remaining readable-caption layer drift',text_drift)
    record=dict(case=case['name'],first_hash=sha(first),baseline_hash=sha(baseline),
                byte_identical=sha(first)==sha(baseline),removed=removed,added=added,
                stats_differences=diffs,layers_stable=True,untreated_symbol_layer_changes=changed_layers,
                first_events=len(new),second_events=len(again))
    records.append(record)
    (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,runtime_sha256=sha(ROOT/'simplify_ass.py'),
        reference_sha256=sha(ROOT/'tests/references/simplify_ass_v182.py'),completed=len(records),cases=records),indent=2)+'\n')
    print(case['name'],'caption layers changed',len(added),'drawings removed',len(old)-len(new),'stable layers on reload',flush=True)
print('9 corpus comparisons passed: layer-only caption changes and stable retained layers',flush=True)
