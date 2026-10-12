"""V175 full-corpus regressions and AoT complete-line ownership diagnostics."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,json,os,subprocess,sys
root=Path(__file__).resolve().parents[1];workspace=root.parent
spec=importlib.util.spec_from_file_location('jitter_corpus_engine',root/'simplify_ass.py');s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)
manifest=json.loads((workspace/'regression-v172/manifest.json').read_text())
fixtures=manifest['fixtures']+[dict(name='Attack-on-Titan-S02E01-track3',source=str(workspace/'upload/Attack on Titan - S02E01 - track-3.original.ass'),sha256='47164f88f29aec5414742feda4c492fee7f85fea62611f986b42dcceb471cf99')]
destination=root/'validation/full-corpus-v175';destination.mkdir(exist_ok=True)
def additions(es):
    changes={}
    for e in es:
        if e.kind != 'Dialogue':continue
        changes.setdefault(e.start_s,[0,0]);changes[e.start_s][0]+=1
        changes.setdefault(e.end_s,[0,0]);changes[e.end_s][1]+=1
    active=0;peak=0;during=0
    for t,(starts,ends) in sorted(changes.items()):
        active-=ends
        if active: during+=starts
        peak=max(peak,starts);active+=starts
    return dict(peak_simultaneous_starts=peak,events_started_while_others_active=during)
def run(job):
    backend,f=job;name=f['name'];folder=destination/backend;folder.mkdir(exist_ok=True)
    env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']=backend
    env['PYTHONPATH']=os.pathsep.join([str(root/'validation/backend_startup'),str(workspace/'test-deps')])
    def convert(version,output):
        p=subprocess.run([sys.executable,str(root/'validation/measure_one.py'),'--engine',str(workspace/version/'simplify_ass.py'),'--source',f['source'],'--fonts',str(workspace/'regression-v172/fonts'),'--output',str(output)],env=env,capture_output=True,text=True)
        assert p.returncode==0,(name,backend,version,p.stdout,p.stderr)
        return json.loads(output.with_suffix('.json').read_text())
    if name.startswith('Attack'):
        baseline=workspace/'aot-investigation/v174-basic.ass' if backend=='windows' else folder/(name+'-v174.ass')
        old=json.loads(baseline.with_suffix('.json').read_text()) if baseline.exists() else convert('v174',baseline)
    else:
        baseline=workspace/'v174/validation/full-corpus-v174'/backend/(name+'-v174.ass')
        old=json.loads(baseline.with_suffix('.json').read_text())
    output=folder/(name+'-v175.ass');current=convert('v175',output)
    assert current['source_sha256']==old['source_sha256']==f['sha256']
    assert current['engine_sha256']==hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest()
    assert old['engine_sha256']==hashlib.sha256((workspace/'v174/simplify_ass.py').read_bytes()).hexdigest()
    before=s.load_subtitle_events(baseline)[1];after=s.load_subtitle_events(output)[1]
    unchanged=baseline.read_bytes()==output.read_bytes()
    result=dict(case=name,backend=backend,baseline=str(baseline),output=str(output),baseline_events=old['statistics']['output'],current_events=current['statistics']['output'],byte_identical=unchanged,baseline_statistics=old['statistics'],current_statistics=current['statistics'],baseline_seconds=old['wall_s'],current_seconds=current['wall_s'],before_additions=additions(before),after_additions=additions(after))
    if name.startswith('Attack'):
        # Literal full-line source families: same text, layer, font, known exact membership.
        source=s.load_subtitle_events(Path(f['source']))[1]
        literals={s.OVERRIDE_RE.sub('',e.text) for e in source if e.style=='ED-R' and e.layer in ('0','1') and not e.state.get('p')}
        retained=[e for e in after if e.style=='ED-R' and s.OVERRIDE_RE.sub('',e.text) in literals]
        assert len(retained)==24,(backend,len(retained))
        outside=lambda es:[e.fields() for e in es if not(e.style=='ED-R' and s.OVERRIDE_RE.sub('',e.text) in literals)]
        assert outside(before)==outside(after),(backend,'unrelated event changed')
        source_intervals={}
        for e in source:
            literal=s.OVERRIDE_RE.sub('',e.text)
            if e.style=='ED-R' and e.layer=='0' and literal in literals:source_intervals.setdefault(literal,[]).append(e)
        expected=[]
        for literal,es in source_intervals.items():
            components=[]
            for e in sorted(es,key=lambda e:e.start_s):
                if not components or e.start_s>components[-1][1]+1e-6:components.append([e.start_s,e.end_s])
                else:components[-1][1]=max(components[-1][1],e.end_s)
            expected.extend((literal,a,b) for a,b in components)
        assert sorted(expected)==sorted((s.OVERRIDE_RE.sub('',e.text),e.start_s,e.end_s) for e in retained)
        assert all(e.state['1a']==0 and e.state['bord']==2 and e.state['shad']==0 and not any(tag in e.text for tag in (r'\t(',r'\move(',r'\fad(',r'\blur')) for e in retained)
        result.update(accepted_complete_lines=24,remaining_effect_reasons={'word_echoes':'Short fading copies are outside the complete-line proof; substring ownership is deferred to v176.','opening_phases':'Phased glyph events require complete-row lifecycle ownership, deferred to v177.'},remaining_word_echoes=sum(e.style=='ED-R' and e.layer=='3' for e in after),unrelated_events_identical=True,caption_intervals_and_gaps_preserved=True,styles_before=dict(Counter(e.style for e in before if e.kind=='Dialogue')),styles_after=dict(Counter(e.style for e in after if e.kind=='Dialogue')))
    else:
        assert unchanged,(backend,name,'unexpected corpus change')
        assert old['statistics']==current['statistics'],(backend,name,'unexpected statistics change')
    print(backend,name,len(before),'->',len(after),'bytes equal',unchanged,round(current['wall_s'],2),flush=True)
    return result
jobs=[(b,f) for b in ('windows','raqm') for f in fixtures]
with ThreadPoolExecutor(max_workers=2) as pool:cases=list(pool.map(run,jobs))
parity={f['name']:(destination/'windows'/(f['name']+'-v175.ass')).read_bytes()==(destination/'raqm'/(f['name']+'-v175.ass')).read_bytes() for f in fixtures}
assert all(parity.values())
report=dict(runtime_sha256=hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest(),cases=cases,cross_backend_bytes_identical=parity)
(root/'validation/full-jitter-comparison-v175.json').write_text(json.dumps(report,indent=2)+'\n')
print('All 18 full-fixture comparisons passed',flush=True)
