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
def fixture(*,reverse=False,whole=False,fill='C7F5B2',glow='1AC60D',base='FFFFFF',mutation=''):
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
  text+=event(word,x,4,(1,4),main)
  contour=f'\\an5\\alpha&H30&\\blur8\\1c&H{glow}&'
  if mutation=='competing glow' and j==1:text+=event(word,x,2,(1,4),contour.replace(glow,'123456'))
  if mutation=='shared fade':contour=r'\fad(120,240)'+contour
  if mutation=='animated glow':contour+=f'\\t({begin},{begin+1},\\fscx105\\fscy105)\\t({begin+1},{finish},\\fscx100\\fscy100)'
  text+=event(word,x,3,(1,4),contour)
  model=next(iter(s._resolve_document_state(s.parse_subtitle_document(HEADER+event(word,x,4,(1,4),r'\an5'))).events.values()))
  pieces=[(word,x)] if whole else s.authored_glyph_positions(metric,model.state,word,x,1)
  if mutation=='missing letter' and j==1:pieces=pieces[:-1]
  for n,(literal,px) in enumerate(pieces):
   if mutation=='wrong position' and j==1:px+=20
   tags=f'\\an5\\alpha&H60&\\blur3\\1c&H{fill}&\\t(\\alpha&HFF&\\blur8\\fscx130\\fscy130)'
   if mutation=='paint-changing echo' and j==1:tags=tags.replace(r'\blur8',r'\blur8\1c&HABCDEF&')
   if mutation=='whole scaled':tags+=r'\fscx105\fscy105'
   text+=event(literal,px,4,(1+begin/1000,1+finish/1000),tags)
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
  check('native green pixels',sum(g>r*1.15 and g>b*1.15 for r,g,b in a.getdata())>100)
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
originals=s.load_subtitle_events(fixture_path)[1]
for original in originals:
 if original.style!='OP - R' or s._returning_glow_highlight(original) is None:continue
 word=s.OVERRIDE_RE.sub('',original.text)
 check('real held word paint '+str(original.source_index),any(
  e.start_s==original.start_s and e.end_s==original.end_s and
  word in s.OVERRIDE_RE.sub('',e.text).replace(' ','') and
  e.state.get('1c')!='C7F5B2' and e.state.get('3a',0)>0 and int(e.state['1c'][2:4],16)>=int(e.state['1c'][4:],16) for e in es))
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'glow pulse paint checks passed')
