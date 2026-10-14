"""Fresh v197 proved-backing paint comparisons against verified v196."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verify-existing',action='store_true',help='Verify already-generated outputs with current engine/source/output hashes')
args=parser.parse_args()
DEST=ROOT/'validation/proved-backing-paint-corpus/windows';DEST.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
records=[]
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
 source=ROOT/case['source'];assert sha(source)==case['sha256']
 baseline=ROOT/'validation/karaoke-completion-bound-corpus/windows'/(case['name']+'.ass')
 old=json.loads(baseline.with_suffix('.json').read_text())
 assert old['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v196.py')
 assert old['source_sha256']==sha(source) and old['output_sha256']==sha(baseline) and old['missing_families']==[]
 output=DEST/baseline.name
 if not args.verify_existing:subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),'--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
 new=json.loads(output.with_suffix('.json').read_text())
 assert new['engine_sha256']==sha(ROOT/'simplify_ass.py') and new['source_sha256']==sha(source) and new['output_sha256']==sha(output)
 assert not new['missing_families'],new['missing_families']
 assert output.read_bytes()==baseline.read_bytes(),(case['name'],'unexplained corpus change')
 assert new['statistics']==old['statistics'],(case['name'],'statistics changed')
 records.append(dict(case=case['name'],source_sha256=sha(source),output_sha256=sha(output),byte_identical=True,statistics_identical=True,wall_s=new['wall_s']))
 (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,engine_sha256=sha(ROOT/'simplify_ass.py'),cases=records),indent=2)+'\n')
 print(case['name'],'byte-identical output and statistics',flush=True)
source=ROOT/'test-data/Goblin-Slayer-S01E02-track6-source.ass'
output=DEST/'Goblin-Slayer-S01E02-track6.ass'
if not args.verify_existing:subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(ROOT/'simplify_ass.py'),'--source',str(source),'--fonts',str(ROOT/'fonts'),'--output',str(output)],cwd=ROOT,env=env,check=True)
new=json.loads(output.with_suffix('.json').read_text());assert not new['missing_families']
assert new['engine_sha256']==sha(ROOT/'simplify_ass.py')
baseline=ROOT/'validation/karaoke-completion-bound-corpus/windows/Goblin-Slayer-S01E02-track6.ass'
old=json.loads(baseline.with_suffix('.json').read_text())
assert old['engine_sha256']==sha(ROOT/'tests/references/simplify_ass_v196.py')
assert old['source_sha256']==sha(source) and old['output_sha256']==sha(baseline)
assert new['source_sha256']==sha(source) and new['output_sha256']==sha(output)
old_events=s.load_subtitle_events(baseline)[1];new_events=s.load_subtitle_events(output)[1]
assert len(old_events)==len(new_events)
changed=[]
for a,b in zip(old_events,new_events):
 assert a.fields()[:9]==b.fields()[:9], 'event metadata/timing changed'
 assert s.OVERRIDE_RE.sub('',a.text)==s.OVERRIDE_RE.sub('',b.text), 'literal changed'
 if a.text!=b.text:
  assert b.style in {'ED-ROM','ED-ENG'}, 'unrelated caption changed'
  assert all(a.state.get(k)==b.state.get(k) for k in set(a.state)|set(b.state) if k not in {'1c','3c','3a'}), 'nonpaint formatting changed'
  assert 0<b.state.get('3a',0)<255, 'recovered paint lost subdued alpha'
  changed.append(dict(style=b.style,start_s=b.start_s,end_s=b.end_s,fill=b.state.get('1c'),outline=b.state.get('3c'),alpha=b.state.get('3a')))
assert changed, 'no proved backing recovered'
diff={k:(old['statistics'].get(k),new['statistics'].get(k)) for k in set(old['statistics'])|set(new['statistics']) if old['statistics'].get(k)!=new['statistics'].get(k)}
assert set(diff) <= {'text_colors_normalized'},diff
if diff:assert 0<new['statistics']['text_colors_normalized']<=len(changed)
records.append(dict(case='Goblin-Slayer-S01E02-track6',source_sha256=sha(source),output_sha256=sha(output),changed_captions=changed,events=len(new_events),statistics_identical=not diff,statistics_changes=diff,wall_s=new['wall_s']))
(DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,engine_sha256=sha(ROOT/'simplify_ass.py'),cases=records),indent=2)+'\n')
print('Nine corpus outputs/statistics unchanged; supplied ending changes only proved paint:',len(changed),'captions')
