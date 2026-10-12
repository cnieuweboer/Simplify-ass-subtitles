"""Compare eight full conversions with v170: explicit q and safe fade handoffs only.

Full originals, prior outputs and complete fonts are external review fixtures.
"""
from pathlib import Path
import collections,hashlib,json,re,sys
root=Path(__file__).resolve().parents[1];old=root.parent/'release170-work';sys.path.insert(0,str(root))
import simplify_ass as s
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();h=sha(root/'simplify_ass.py')
fixture_root=root.parent/'expanded-tests-v107'
manifest=json.loads((fixture_root/'manifest.json').read_text())
source_paths={c['id']:fixture_root/c['source'] for c in manifest['cases']}
cases=[]
for output in sorted((root/'validation/suite').glob('*.ass')):
 name=output.stem;j=json.loads(output.with_suffix('.json').read_text());p=json.loads((old/'validation/suite'/output.with_suffix('.json').name).read_text())
 assert j['engine_sha256']==h and j['engine_version']==s.__version__,name
 assert j['source']==p['source'],name
 for key in ('font_measurement_available','raqm','harfbuzz_available','unavailable_requested_faces','missing_during_conversion','used_faces','text_drop_warnings'):
  assert j[key]==p[key],(name,key)
 cases.append((name,old/'validation/suite'/output.name,output,source_paths[name],p['statistics'],j['statistics']))
for name,report_name,output_name,prior_name,source in [
 ('Sword-S01E01-track6','sword-track6.json','Sword-S01E01-track6.ass','Sword-S01E01-track6.ass',root.parent/'twintails-verification/Reincarnated as a Sword - S01E01_track6_[eng].ass'),
 ('Sword-S01E02-track5','sword-episode2-statistics.json','Sword-S01E02-track5-v171.ass','Sword-S01E02-track5-v170.ass',root.parent/'upload/Reincarnated as a Sword - S01E02 - track-5.original.ass')]:
 j=json.loads((root/'validation'/report_name).read_text());p=json.loads((old/'validation'/report_name).read_text())
 assert j['runtime_sha256']==h,name
 assert j['source_sha256']==sha(source),name
 cases.append((name,old/'outputs'/prior_name,root/'outputs'/output_name,source,p['statistics'],j['statistics']))
results=[]
for name,prior,output,source,previous_stats,stats in cases:
 a=list(s._resolve_document_state(s.read_subtitle_document(prior)).events.values());b=list(s._resolve_document_state(s.read_subtitle_document(output)).events.values())
 originals=list(s._resolve_document_state(s.read_subtitle_document(source)).events.values())
 assert len(a)==len(b),name
 changes=[];timed=[]
 for x,y in zip(a,b):
  if x.fields()==y.fields():continue
  before=x.fields();after=y.fields();before[1:3]=after[1:3]
  strip=lambda text:re.sub(r'\\q[0-3](?!\d)','',text)
  before[-1]=strip(before[-1]);after[-1]=strip(after[-1]);assert before==after,(name,x.fields(),y.fields())
  assert x.state.get('q') is None and y.state.get('q')==2,(name,x.text,y.text)
  assert {k:v for k,v in x.state.items() if k!='q'}=={k:v for k,v in y.state.items() if k!='q'},(name,'resolved state')
  assert x.start_s<=y.start_s<y.end_s<=x.end_s,(name,'expanded exposure')
  changes.append(dict(style=x.style,name=x.name,literal=s.OVERRIDE_RE.sub('',x.text),old_start=x.start,old_end=x.end,start=y.start,end=y.end,q=2))
  if x.start!=y.start or x.end!=y.end:timed.append((x,y))
 handoffs=[];claimed=set()
 for x,y in timed:
  if x.end==y.end:continue
  matches=[(u,v) for u,v in timed if u.start!=v.start and s.text_cue_lane(u,s.get_pos(u.text),u.state)==s.text_cue_lane(x,s.get_pos(x.text),x.state) and v.start==y.end]
  assert len(matches)==1,(name,'unpaired handoff')
  u,v=matches[0]
  assert x.start_s<u.start_s<x.end_s<u.end_s
  assert y.end_s==round((u.start_s+x.end_s)/2,2),(name,'unexpected handoff')
  # Independently check source foreground fades for both boundary cuts.
  def cores(cue,phase):
   found=[];literal=s.OVERRIDE_RE.sub('',cue.text).strip();lane=s.text_cue_lane(cue,s.get_pos(cue.text),cue.state)
   for event in originals:
    pos=s.get_pos(event.text)
    if event.kind!='Dialogue' or pos is None or s.text_cue_lane(event,pos,event.state)!=lane:continue
    word=s.OVERRIDE_RE.sub('',event.text).strip()
    if not word or word not in literal or not s.opaque_text_effect_state(event.state) or 'clip' in event.state or 'iclip' in event.state:continue
    value=event.start_s if phase==0 else event.end_s;expected=cue.start_s if phase==0 else cue.end_s
    if abs(value-expected)>.001:continue
    fades=[arg for tag,arg in s.event_override_tokens(event) if tag=='fad']
    if len(fades)!=1:continue
    fade_in,fade_out=[float(z)/1000 for z in fades[0][1:-1].split(',')]
    found.append(event.start_s+fade_in if phase==0 else event.end_s-fade_out)
   assert found,(name,'missing original foreground fade',cue.text,phase)
   return min(found) if phase==0 else max(found)
  assert cores(x,1)<=y.end_s<=cores(u,0),(name,'cut protected source exposure')
  claimed.update((x.source_index,u.source_index));handoffs.append(dict(left=s.OVERRIDE_RE.sub('',x.text),right=s.OVERRIDE_RE.sub('',u.text),boundary=y.end))
 assert claimed=={x.source_index for x,y in timed},(name,'unreviewed timing changes')
 stat_changes={k:[previous_stats[k],value] for k,value in stats.items() if previous_stats[k]!=value}
 assert set(stat_changes)<={'cue_overlaps_trimmed'},(name,stat_changes)
 assert stats['cue_overlaps_trimmed']-previous_stats['cue_overlaps_trimmed']==len(handoffs)
 if not changes:assert prior.read_bytes()==output.read_bytes(),name
 results.append(dict(case=name,events=stats['output'],peak_concurrent=stats['max_concurrent_out'],output_bytes_identical=prior.read_bytes()==output.read_bytes(),wrapping_restored=len(changes),fade_handoffs=len(handoffs),handoffs=handoffs,statistics_changes=stat_changes,all_other_event_fields_identical=True,source_fade_exposure_preserved=True))
assert len(results)==8
report=dict(version=s.__version__,reference_version='2026.10.11.170',runtime_sha256=h,complete_subtitles=8,byte_identical_outputs=sum(x['output_bytes_identical'] for x in results),event_counts_and_peak_concurrency_unchanged=True,only_explicit_wrapping_and_source_fade_handoffs_changed=True,fade_handoffs=sum(x['fade_handoffs'] for x in results),cases=results)
(root/'validation/full-conversion-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print('Eight full comparisons passed: four byte-identical; four retain authored wrapping and fix 14 source-fade handoffs; all counts and peak concurrency unchanged')
