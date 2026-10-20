"""Returning highlight stacks retain coherent paint and only own proved copies."""
import test_paths
from pathlib import Path
from copy import deepcopy
import json,contextlib,io,subprocess
from PIL import Image,ImageChops
import simplify_ass as s
from lyric_layer_fixtures import HEADER,event
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'validation/glow-pulse-checks';DEST.mkdir(exist_ok=True)
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
def fixture(*,reverse=False,whole=False,fill='C7F5B2',glow='1AC60D',base='FFFFFF',mutation='',boundaries='',hold_end=4,echo_end=None,echo_start=None):
 text=HEADER.replace('1,2,0,7,','1,0,0,5,')
 words=['Sun','moon','stars'];starts=[0,700,1400]
 if reverse:starts=starts[::-1]
 for j,(word,begin) in enumerate(zip(words,starts)):
  x=100+j*150;finish=begin+650
  main=f'\\an5\\alpha&H10&\\1c&H{base}&\\blur0.9\\t({begin},{begin+1},\\1c&H{fill}&\\fscx105\\fscy105)\\t({begin+1},{finish},\\1c&H{base}&\\fscx100\\fscy100)'
  if mutation=='cycle' and j==1:main+=r'\t(2500,2600,\1c&H123456&)'
  if mutation=='gradient' and j==1:main=r'\an5\alpha&H10&\1c&H123456&'
  if mutation=='moving' and j==1:main+=r'\move(250,100,260,100)'
  if mutation=='shared fade':main=r'\fad(120,240)'+main
  text+=event(word,x,4,(1,hold_end),main)
  contour=f'\\an5\\alpha&H30&\\blur8\\1c&H{glow}&'
  if mutation=='competing glow' and j==1:text+=event(word,x,2,(1,4),contour.replace(glow,'123456'))
  if mutation=='shared fade':contour=r'\fad(120,240)'+contour
  if mutation=='animated glow':contour+=f'\\t({begin},{begin+1},\\fscx105\\fscy105)\\t({begin+1},{finish},\\fscx100\\fscy100)'
  text+=event(word,x,3,(1,hold_end),contour)
  model=next(iter(s._resolve_document_state(s.parse_subtitle_document(HEADER+event(word,x,4,(1,4),r'\an5'))).events.values()))
  pieces=[(word,x)] if whole else s.authored_glyph_positions(metric,model.state,word,x,1)
  if mutation=='missing letter' and j==1:pieces=pieces[:-1]
  for n,(literal,px) in enumerate(pieces):
   if mutation=='wrong position' and j==1:px+=20
   tags=f'\\an5\\alpha&H60&\\blur3\\1c&H{fill}&\\t(\\alpha&HFF&\\blur8\\fscx130\\fscy130)'
   if mutation=='paint-changing echo' and j==1:tags=tags.replace(r'\blur8',r'\blur8\1c&HABCDEF&')
   if mutation=='whole scaled':tags+=r'\fscx105\fscy105'
   child_start=echo_start if j==0 and echo_start is not None else 1+begin/1000
   child_end=echo_end if j==2 and echo_end is not None else 1+finish/1000
   text+=event(literal,px,4,(child_start,child_end),tags)
 if boundaries:
  for j,word in enumerate(words):
   x=100+j*150
   text+=event(word,x+1,2,(1,4),r'\an5\alpha&H50&\1c&H000000&\blur1.5')
   for entering in (True,False):
    if boundaries=='exit only' and entering:continue
    if boundaries=='missing word' and j==1:continue
    times=(.75,1) if entering else (4,4.4)
    if boundaries=='gap':times=(.70,.95) if entering else (4.05,4.45)
    color='123456' if boundaries=='changed paint' and j==1 else base
    px=x+20 if boundaries=='wrong anchor' and j==1 else x
    tags=f'\\an5\\alpha&H{("FF" if entering else "10")}&\\1c&H{color}&\\blur0.9\\t(\\alpha&H{("10" if entering else "FF")}&\\blur3)'
    if boundaries=='animated geometry' and j==1:tags=tags.replace('\\blur3','\\blur3\\fscx120')
    text+=event(word,px,4,times,tags)
    if boundaries=='ambiguous' and j==1:text+=event(word,px,4,times,tags)
    # Both already-collapsed glow paint and retained offset backing have
    # independent source fades. They must follow the same proved lifecycle.
    for layer,anchor,alpha,color,blur in [(3,x,'30',glow,8),(2,x+1,'50','000000',1.5)]:
     tags=f'\\an5\\alpha&H{("FF" if entering else alpha)}&\\1c&H{color}&\\blur{blur}\\t(\\alpha&H{(alpha if entering else "FF")}&\\blur10)'
     text+=event(word,anchor,layer,times,tags)
 # A separate nearby caption must never become an owned effect.
 text+=event('Independent',550,5,(1,4),r'\an5\1c&H123456&')
 document=s._resolve_document_state(s.parse_subtitle_document(text));source=document.events
 if mutation=='scrolling':
  source={i:s.dataclass_replace(e,effect='Scroll up;0;360;5') if s.OVERRIDE_RE.sub('',e.text)=='moon' else e for i,e in source.items()}
 frozen=[];visible={}
 for e in source.values():
  t,w,_=s.simplify_visual_text(e.text,0,e.duration,e.defaults,e.styles,1)
  frozen.append(s.replace_event(e,text=t));visible[e.source_index]=w
 if mutation=='changed current literal':
  frozen=[s.replace_event(e,text=e.text+'Unrelated') if e.start_s==1.7 and len(s.OVERRIDE_RE.sub('',e.text))==1 else e for e in frozen]
 return text,source,frozen,visible
for label,kwargs in [
 ('letters',{}),('reverse',{'reverse':True}),('whole words',{'whole':True}),
 ('scaled words',{'whole':True,'mutation':'whole scaled'}),
 ('synchronized glow scale',{'mutation':'animated glow'}),
 ('shared fade',{'mutation':'shared fade'}),
 ('nonwhite base',{'base':'E8B0A0'}),
 ('other palette',{'fill':'F5C7B2','glow':'C61A0D'}),
]:
 text,source,events,visible=fixture(**kwargs);before=deepcopy((source,events,visible))
 out,count=s.flatten_stacked_text_copies(events,visible,set(source),source_events=source,font_metrics=metric)
 parents=[e for e in out if e.layer=='4']
 check(label+': one event per word',len(parents)==3)
 check(label+': removal count',count==len(events)-len(out))
 check(label+': settled near-white fill',all(max(abs(int(e.state['1c'][i:i+2],16)-int(kwargs.get('base','FFFFFF')[i:i+2],16)) for i in (0,2,4))<20 and e.state['1c']!=kwargs.get('fill','C7F5B2') for e in parents))
 check(label+': subdued contour',all(0<e.state['3a']<255 and e.state['3c']!=kwargs.get('glow','1AC60D') for e in parents))
 check(label+': original foreground order',all(e.layer=='4' for e in parents))
 check(label+': independent text retained',any('Independent' in e.text for e in out))
 check(label+': timing retained',all((e.start_s,e.end_s)==(1,4) for e in parents))
 check(label+': inputs immutable',before==(source,events,visible))
 check(label+': static result',all(not any(tag=='t' for tag,value in s.event_override_tokens(e)) for e in out))
 check(label+': repeat stable',s.flatten_stacked_text_copies(out,visible,set(source),source_events=source,font_metrics=metric)[0]==out)
 if label=='letters':
  path=DEST/'static.ass';path.write_text(HEADER+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in out))
  def frame(at):
   r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=640x360:r=1','-vf',f'settb=1/1000,setpts=PTS+{at},ass=filename={path}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
   return Image.frombytes('RGB',(640,360),r.stdout)
  a,b=frame(1200),frame(3500);check('native static hold',ImageChops.difference(a,b).getbbox() is None)
  check('native green pixels',sum(g>r*1.15 and g>b*1.15 for r,g,b in zip(*(band.tobytes() for band in a.split())))>100)
for label,kwargs,accepted in [
 ('late 40 ms letters',dict(hold_end=3,echo_end=3.04),True),
 ('late 50 ms letters',dict(hold_end=3,echo_end=3.05),True),
 ('early 40 ms letters',dict(hold_end=3,echo_start=.96),True),
 ('late 50 ms whole copies',dict(hold_end=3,echo_end=3.05,whole=True),True),
 ('overhang 60 ms',dict(hold_end=3,echo_end=3.06),False),
 ('overhang 100 ms despite nearby pulse',dict(hold_end=3,echo_end=3.10),False),
 ('early 60 ms',dict(hold_end=3,echo_start=.94),False),
 ('late missing glyph',dict(hold_end=3,echo_end=3.04,mutation='missing letter'),False),
 ('late changed paint',dict(hold_end=3,echo_end=3.04,mutation='paint-changing echo'),False),
 ('late wrong anchor',dict(hold_end=3,echo_end=3.04,mutation='wrong position'),False),
 ('late cyclic foreground',dict(hold_end=3,echo_end=3.04,mutation='cycle'),False),
]:
 _,source,events,visible=fixture(**kwargs);before=deepcopy((source,events,visible))
 out,count=s.flatten_stacked_text_copies(events,visible,set(source),source_events=source,font_metrics=metric)
 parents=[e for e in out if e.layer=='4']
 check(label+': complete ownership',len(parents)==3 if accepted else len(parents)>3)
 check(label+': inputs immutable',before==(source,events,visible))
 if accepted:
  check(label+': held timing unchanged',all((e.start_s,e.end_s)==(1,3) for e in parents))
  check(label+': settled paint',all(e.state['1a']==0 and 0<e.state['3a']<255 for e in parents))
  check(label+': repeat stable',s.flatten_stacked_text_copies(out,visible,set(source),source_events=source,font_metrics=metric)[0]==out)
 else:
  check(label+': no partial row palette',not any(e.state.get('3a',0)>0 and e.layer=='4' and e.duration==2 for e in out))
for boundary in ['both','exit only','missing word','gap','changed paint','wrong anchor','animated geometry','ambiguous']:
 _,source,events,visible=fixture(boundaries=boundary);before=deepcopy((source,events,visible))
 result=s.flatten_stacked_text_copies(events,visible,set(source),source_events=source,font_metrics=metric,collect_rows=True)
 parents=[e for e in result.events if e.layer=='4']
 accepted=boundary in {'both','exit only'}
 check(boundary+': boundary ownership',len(parents)==3 if accepted else len(parents)>3)
 check(boundary+': immutable boundaries',before==(source,events,visible))
 check(boundary+': counter accounting',result.removed_count+result.phase_merged==len(events)-len(result.events))
 check(boundary+': protected core',len(result.rows)==3 and all(r.phase_core==(1,4) for r in result.rows) if accepted else not result.rows)
 if accepted:
  check(boundary+': complete lifetime',all((e.start_s,e.end_s)==((.75,4.4) if boundary=='both' else (1,4.4)) for e in parents))
  check(boundary+': settled paint throughout',all(e.state['1a']==0 and 0<e.state['3a']<255 for e in parents))
  check(boundary+': collapsed glow boundaries removed',not any(e.layer=='3' for e in result.events))
  shadows=[e for e in result.events if e.layer=='2']
  check(boundary+': backing lifetime and own paint',len(shadows)==3 and all(e.state['1a']==80 and e.state['1c']=='000000' and (e.start_s,e.end_s)==(parents[0].start_s,parents[0].end_s) for e in shadows))
  families=s.collect_faded_cue_families(result.events,result.rows,source)
  check(boundary+': overlap evidence handoff',len(families)==1 and families[0].core==(1,4))
  again=s.flatten_stacked_text_copies(result.events,visible,set(source),source_events=source,font_metrics=metric)[0]
  check(boundary+': repeated coordination stable',again==result.events)
  repeated=s.replace_event(parents[0],source_index=30000,start=parents[0].end,end=s.format_time(parents[0].end_s+2),start_s=parents[0].end_s,end_s=parents[0].end_s+2)
  pair=[parents[0],repeated];words={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in pair}
  check(boundary+': repeated word cue separation',s.coalesce_lyric_phases(pair,words,phase_groups={e.source_index:e.source_index for e in pair})[1]==0)

  # A later complete cue overlaps only in the flattened boundary phases.
  later=[s.replace_event(e,source_index=e.source_index+20000,start=s.format_time(e.start_s+3.3),
          end=s.format_time(e.end_s+3.3),start_s=e.start_s+3.3,end_s=e.end_s+3.3) for e in parents]
  later_rows=[s.TextRow(e,[(e,s.OVERRIDE_RE.sub('',e.text),s.get_pos(e.text))],phase_core=(4.3,7.3)) for e in later]
  combined=parents+later;rows=result.rows+later_rows
  families=s.collect_faded_cue_families(combined,rows,source)
  trimmed,count=s.trim_faded_cue_overlaps(combined,rows,source,cue_families=families)
  check(boundary+': fade collision removed',count==1 and max(e.end_s for e in trimmed[:3])==min(e.start_s for e in trimmed[3:]))
  check(boundary+': every core preserved',all(e.start_s<=1 and e.end_s>=4 for e in trimmed[:3]) and all(e.start_s<=4.3 and e.end_s>=7.3 for e in trimmed[3:]))
  check(boundary+': backing ownership carried',all(len(r.owned_backing)==1 for r in result.rows))
  later_shadows=[s.replace_event(e,source_index=e.source_index+20000,start=s.format_time(e.start_s+3.3),
          end=s.format_time(e.end_s+3.3),start_s=e.start_s+3.3,end_s=e.end_s+3.3) for e in shadows]
  later_rows=[s.dataclass_replace(r,owned_backing=(paint,)) for r,paint in zip(later_rows,later_shadows)]
  combined=parents+later+shadows+later_shadows;rows=result.rows+later_rows
  before=deepcopy((combined,rows,source))
  families=s.collect_faded_cue_families(combined,rows,source)
  aligned,count=s.trim_faded_cue_overlaps(combined,rows,source,cue_families=families)
  byid={e.source_index:e for e in aligned}
  check(boundary+': all paint shares handoff',all((byid[paint.source_index].start,byid[paint.source_index].end)==(byid[r.base.source_index].start,byid[r.base.source_index].end) for r in rows for paint in r.owned_backing))
  check(boundary+': timing inputs immutable',before==(combined,rows,source))
  check(boundary+': paint unchanged',all(byid[e.source_index].text==e.text for e in combined))
  independent=s.replace_event(shadows[0],source_index=40000)
  untouched=s.trim_faded_cue_overlaps(combined+[independent],rows,source,cue_families=families)[0][-1]
  check(boundary+': independent translucent text protected',untouched==independent)
  changed_paint=s.replace_event(shadows[0],text=shadows[0].text+'!')
  altered=[changed_paint if e.source_index==changed_paint.source_index else e for e in combined]
  got={e.source_index:e for e in s.trim_faded_cue_overlaps(altered,rows,source,cue_families=families)[0]}
  check(boundary+': changed backing rejected',got[changed_paint.source_index]==changed_paint)
  core_snapshot=s.replace_event(shadows[0],start=s.format_time(1),end=s.format_time(4),start_s=1,end_s=4)
  core_rows=[s.dataclass_replace(r,owned_backing=(core_snapshot,)) if r is rows[0] else r for r in rows]
  got={e.source_index:e for e in s.trim_faded_cue_overlaps(combined,core_rows,source,cue_families=families)[0]}
  check(boundary+': source core snapshot permits acquired phases',got[shadows[0].source_index].end==got[parents[0].source_index].end)

  competing=s.dataclass_replace(rows[1],owned_backing=rows[1].owned_backing+(shadows[0],))
  ambiguous=[competing if r is rows[1] else r for r in rows]
  got={e.source_index:e for e in s.trim_faded_cue_overlaps(combined,ambiguous,source,cue_families=families)[0]}
  check(boundary+': competing backing owners rejected',got[shadows[0].source_index]==shadows[0])
  joined=s.replace_event(shadows[0],text=shadows[0].text+' '+s.OVERRIDE_RE.sub('',shadows[1].text))
  joined_row=s.TextRow(joined,[(e,s.OVERRIDE_RE.sub('',e.text),s.get_pos(e.text)) for e in shadows[:2]])
  joined_events=[e for e in combined if e.source_index not in {p.source_index for p in shadows[:2]}]+[joined]
  got={e.source_index:e for e in s.trim_faded_cue_overlaps(joined_events,rows+[joined_row],source,cue_families=families)[0]}
  check(boundary+': complete joined backing follows owners',got[joined.source_index].end==got[parents[0].source_index].end)
  incomplete=s.dataclass_replace(joined_row,pieces=joined_row.pieces+[(independent,'unowned',s.get_pos(independent.text))])
  got={e.source_index:e for e in s.trim_faded_cue_overlaps(joined_events,rows+[incomplete],source,cue_families=families)[0]}
  check(boundary+': incomplete backing lineage protected',got[joined.source_index]==joined)

  changed=[s.dataclass_replace(r,phase_core=(3.9,7.3)) for r in later_rows]
  families=s.collect_faded_cue_families(combined,result.rows+changed,source)
  check(boundary+': contradictory core rejected',s.trim_faded_cue_overlaps(combined,result.rows+changed,source,cue_families=families)[1]==0)

for mutation in ['missing letter','wrong position','paint-changing echo','cycle','gradient','moving','competing glow','scrolling','changed current literal']:
 _,source,events,visible=fixture(mutation=mutation)
 out,count=s.flatten_stacked_text_copies(events,visible,set(source),source_events=source,font_metrics=metric)
 check(mutation+': no partial row palette',not any(e.state.get('3a',0)>0 and e.layer=='4' and e.duration==3 for e in out))
 check(mutation+': effect fragments retained',len(out)>4)
_,source,events,visible=fixture()
out,count=s.flatten_stacked_text_copies(events,visible,set(source),source_events=source,font_metrics=None)
check('missing metric keeps fragments',len(out)>4)
# Real source is local, never packaged with code. Compare the complete opening.
fixture_path=ROOT/'test-data/Goblin-Slayer-S01E02-track6-source.ass'
if not fixture_path.exists():
 raise FileNotFoundError('Missing local Goblin Slayer original; restore the uploaded fixture before this check')
report=s.FontProcessingReport()
with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(fixture_path,DEST/'Goblin.ass',s.SimplifyConfig(),font_metrics=metric,font_report=report)
check('real exact fonts available',not report.missing_families)
es=s.load_subtitle_events(DEST/'Goblin.ass')[1]
active=[e for e in es if e.style=='OP - R' and e.start_s<=145<e.end_s]
check('real first cue green foreground',any(e.state.get('1c')!='C7F5B2' and e.state.get('3a',0)>0 and int(e.state['1c'][2:4],16)>=int(e.state['1c'][4:],16) for e in active))
check('real first cue no highlight copies',not any(e.state.get('fscx',100)>100 for e in active))
foreground=[e for e in es if e.style=='OP - R' and e.layer=='4' and e.start_s<=165.6<e.end_s]
backing=[e for e in es if e.style=='OP - R' and e.layer=='2' and e.start_s<=165.6<e.end_s]
check('real Numb cue complete foreground',len(foreground)==4)
check('real Numb backing shares handoff',all(any(
 s.OVERRIDE_RE.sub('',p.text)==s.OVERRIDE_RE.sub('',e.text) and
 (p.start,p.end)==(e.start,e.end) for p in foreground) for e in backing) and len(backing)==4)
check('real Numb no backing before handoff',not any(e.start_s<=165.07<e.end_s for e in backing))
check('real Numb no backing after handoff',not any(e.start_s<=166.13<e.end_s for e in backing))

for start,end in [(190.21,191.67),(200.72,202.18)]:
 cue=[e for e in es if e.style=='OP - R Chant' and e.start_s <= (start+end)/2 < e.end_s]
 foreground=[e for e in cue if e.layer=='4']
 check('real chant retains all text '+str(start),''.join(s.OVERRIDE_RE.sub('',e.text).replace(' ','') for e in foreground)=='Tesrrounamadungeyeon')
 check('real chant settled opaque paint '+str(start),foreground and all(e.state.get('1a',0)==0 and 0<e.state.get('3a',0)<255 and e.state.get('fscx',100)==100 for e in foreground))
 check('real chant held interval preserved '+str(start),all(e.start_s<=start and e.end_s>=end for e in foreground))
 check('real chant no timed highlight copies '+str(start),not any(e.layer=='4' and e.start_s>start and e.end_s<end for e in es if e.style=='OP - R Chant'))
originals=s.load_subtitle_events(fixture_path)[1]
for original in originals:
 if original.style!='OP - R' or s._returning_glow_highlight(original) is None:continue
 word=s.OVERRIDE_RE.sub('',original.text)
 check('real held word paint '+str(original.source_index),any(
  e.start_s<=original.start_s and e.end_s>=original.end_s and
  word in s.OVERRIDE_RE.sub('',e.text).replace(' ','') and
  e.state.get('1c')!='C7F5B2' and e.state.get('3a',0)>0 and int(e.state['1c'][2:4],16)>=int(e.state['1c'][4:],16) for e in es))
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'glow pulse paint checks passed')
