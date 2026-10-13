"""Fresh nine-source conversion, checked against hash-verified v183 outputs."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/late-copy-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
records=[]
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
    source=ROOT/case['source'];assert sha(source)==case['sha256']
    baseline=ROOT/'validation/caption-layer-corpus/windows'/(case['name']+'.ass')
    meta=json.loads(baseline.with_suffix('.json').read_text())
    assert meta['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v183.py')
    assert meta['source_sha256']==sha(source) and meta['output_sha256']==sha(baseline)
    assert meta['missing_families']==[],('Missing baseline fonts',case['name'])
    output=DEST/(case['name']+'.ass')
    subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),
                    '--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],
                   cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
    new_meta=json.loads(output.with_suffix('.json').read_text())
    assert new_meta['missing_families']==[],('Missing required font; stop',case['name'],new_meta['missing_families'])
    old=s.load_subtitle_events(baseline)[1];new=s.load_subtitle_events(output)[1]
    expected,count=s.remove_late_complete_copies(old)
    # The v183 full corpus has no eligible residual complete-copy pairs.
    assert count==0 and sha(baseline)==sha(output),(case['name'],'unexpected corpus change')
    assert [e.fields() for e in expected]==[e.fields() for e in new],(case['name'],'unrelated output changed')
    diffs={k:(meta['statistics'].get(k),new_meta['statistics'].get(k))
           for k in meta['statistics'].keys()|new_meta['statistics'].keys()
           if meta['statistics'].get(k)!=new_meta['statistics'].get(k)}
    assert not diffs.keys()-{'deduped','output','max_concurrent_out'},(case['name'],'unrelated counter change',diffs)
    assert new_meta['statistics']['deduped']==meta['statistics']['deduped']+count
    assert new_meta['statistics']['output']==sum(e.kind=='Dialogue' for e in new)
    if case['name'].startswith('Attack'):
        for text,start in [('North Group',728.20),('South Group',729.16)]:
            flash=[e for e in new if s.OVERRIDE_RE.sub('',e.text)==text and abs(e.start_s-start)<.001 and e.state.get('1c')=='EAE9E7']
            assert len(flash)==1,('Different intentional paint removed',text)
    live={id(e) for e in expected}
    removed=[e.fields() for e in old if id(e) not in live]
    record=dict(case=case['name'],source_sha256=sha(source),baseline_sha256=sha(baseline),output_sha256=sha(output),
                byte_identical=sha(baseline)==sha(output),removed_copies=count,removed=removed,stats_differences=diffs)
    records.append(record)
    (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,runtime_sha256=sha(ROOT/'simplify_ass.py'),
        reference_sha256=sha(ROOT/'tests/references/simplify_ass_v183.py'),completed=len(records),cases=records),indent=2)+'\n')
    print(case['name'],count,'late copies removed','unchanged' if record['byte_identical'] else 'changed',flush=True)
print('9 corpus checks passed: only proved late duplicates removed; different AoT paints retained')
