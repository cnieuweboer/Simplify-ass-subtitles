"""Replace the first four timing pairs that overlapped a discarded cache trial.

All raw measurements remain recorded; only two uncontended samples per version
and subtitle contribute to the report. Production code and input data are fixed.
Run after benchmark_outline_optimization.py has completed, not concurrently.
"""
from pathlib import Path
import hashlib,json,statistics,subprocess,sys
root=Path(__file__).resolve().parents[1]
workspace=root.parent
path=root/'validation/performance-results.json'
records=json.loads(path.read_text())
assert len(records)==32
report_path=root/'validation/full-conversion-comparison.json'
report=json.loads(report_path.read_text())
cases=json.loads((workspace/'performance171-work/fixture-inventory.json').read_text())
engines={'171':workspace/'release171-work/simplify_ass.py','172':root/'simplify_ass.py'}
for record in records:
    if record['case'] in {c['name'] for c in cases[:4]} and record['repeat']==1:
        record['timing_excluded']=True
        record['exclusion_reason']='Overlapped the preceding discarded pass-wide-cache trial; repeated after it completed.'
for number,case in enumerate(cases[:4]):
    for version in (['171','172'] if number%2==0 else ['172','171']):
        output=root/'validation/performance'/f"{case['name']}-v{version}-r3.ass"
        print('START clean repeat',case['name'],version,flush=True)
        subprocess.run([sys.executable,str(workspace/'performance171-work/measure_one.py'),
            '--engine',str(engines[version]),'--source',case['source'],
            '--fonts',str(workspace/'expanded-tests-v107/fonts'),'--output',str(output)],check=True)
        result=json.loads(output.with_suffix('.json').read_text())
        result.update(case=case['name'],repeat=3)
        records.append(result)
        path.write_text(json.dumps(records,indent=2)+'\n')
for item in report['cases']:
    all_samples=[x for x in records if x['case']==item['case']]
    assert len({x['output_sha256'] for x in all_samples})==1,item['case']
    assert all(x['statistics']==all_samples[0]['statistics'] for x in all_samples),item['case']
    selected=[x for x in all_samples if not x.get('timing_excluded')]
    for version in engines:
        values=[x['wall_s'] for x in selected if x['version'].endswith('.'+version)]
        assert len(values)==2,(item['case'],version)
        item['v'+version+'_samples']=values
        item['v'+version+'_seconds']=statistics.mean(values)
    item['reduction_pct']=100*(1-item['v172_seconds']/item['v171_seconds'])
report['aggregate_v171_s']=sum(x['v171_seconds'] for x in report['cases'])
report['aggregate_v172_s']=sum(x['v172_seconds'] for x in report['cases'])
report['aggregate_reduction_pct']=100*(1-report['aggregate_v172_s']/report['aggregate_v171_s'])
report.update(measurements=len(records),measurements_used_for_timing=32,timing_excluded=8,
              exclusion_reason='First four initial pairs overlapped discarded cache trial; replaced by clean third pairs.')
assert report['runtime_sha256']==hashlib.sha256(engines['172'].read_bytes()).hexdigest()
report_path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
