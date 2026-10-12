"""Counterbalanced fresh-process v171/v172 timing and byte-equivalence checks.

Uses the existing complete eight-fixture corpus and full extracted font catalog
in this workspace. Measurements are sequential; do not run other conversions
concurrently. Saved JSON records include inputs, engine hashes and raw samples.
"""
from pathlib import Path
import hashlib, json, shutil, statistics, subprocess, sys

root = Path(__file__).resolve().parents[1]
workspace = root.parent
destination = root/'validation/performance'
destination.mkdir(exist_ok=True)
cases = json.loads((workspace/'performance171-work/fixture-inventory.json').read_text())
engines = {'171':workspace/'release171-work/simplify_ass.py','172':root/'simplify_ass.py'}
records = []
for repeat in range(2):
    for number,case in enumerate(cases):
        order = ['171','172'] if (number+repeat)%2==0 else ['172','171']
        for version in order:
            output = destination/f"{case['name']}-v{version}-r{repeat+1}.ass"
            print('START',case['name'],version,repeat+1,flush=True)
            subprocess.run([sys.executable,str(workspace/'performance171-work/measure_one.py'),
                '--engine',str(engines[version]),'--source',case['source'],
                '--fonts',str(workspace/'expanded-tests-v107/fonts'),'--output',str(output)],check=True)
            result = json.loads(output.with_suffix('.json').read_text())
            result.update(case=case['name'],repeat=repeat+1)
            records.append(result)
            (root/'validation/performance-results.json').write_text(json.dumps(records,indent=2)+'\n')

summary = []
for case in cases:
    samples = {v:[x for x in records if x['case']==case['name'] and x['version'].endswith('.'+v)] for v in engines}
    outputs = [Path(x['output']).read_bytes() for x in samples['171']+samples['172']]
    assert all(b==outputs[0] for b in outputs),case['name']
    assert all(x['statistics']==samples['171'][0]['statistics'] for x in samples['171']+samples['172']),case['name']
    means = {v:statistics.mean(x['wall_s'] for x in samples[v]) for v in engines}
    item = dict(case=case['name'],v171_seconds=means['171'],v172_seconds=means['172'],
                reduction_pct=100*(1-means['172']/means['171']),
                v171_samples=[x['wall_s'] for x in samples['171']],
                v172_samples=[x['wall_s'] for x in samples['172']],
                output_bytes_identical=True,statistics_identical=True,
                events=samples['172'][0]['statistics']['output'],
                peak_concurrent=samples['172'][0]['statistics']['max_concurrent_out'])
    summary.append(item)
    name=case['name']+('.ass' if case['name']!='Sword-S01E02-track5' else '-v172.ass')
    shutil.copyfile(samples['172'][0]['output'],root/'outputs'/name)
totals={v:sum(x['v'+v+'_seconds'] for x in summary) for v in engines}
report=dict(version='2026.10.11.172',reference_version='2026.10.11.171',
            runtime_sha256=hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest(),
            repeats=2,measurements=len(records),cases=summary,
            aggregate_v171_s=totals['171'],aggregate_v172_s=totals['172'],
            aggregate_reduction_pct=100*(1-totals['172']/totals['171']),
            complete_subtitles=len(cases),byte_identical_outputs=len(cases),
            statistics_identical=True,event_counts_and_peak_concurrency_unchanged=True)
(root/'validation/full-conversion-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
