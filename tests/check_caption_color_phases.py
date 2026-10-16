"""Whole-caption paint intent, duration limits, counters and repeat conversion."""
import test_paths
from stacked_contour_cases import *
import contextlib,io,tempfile,math,hashlib,json,subprocess
from copy import deepcopy
from PIL import Image,ImageChops
checks=[]
def check(label,value):
 assert value,label;checks.append(label)
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
def fixture_phases(changes,hold,*,tiny=False,layout=r'\pos(320,100)'):
 colors=[f'{(i+1)*75079%0xFFFFFF:06X}' for i in range(changes+1)]
 if tiny:colors=['556677','566778']
 body=r'{\bord2\1c&H'+colors[0]+r'&\3c&H112244&'
 for i,color in enumerate(colors[1:],1):body+=rf'\t({i*hold*1000:g},{i*hold*1000:g},\1c&H{color}&)'
 return HEADER+event(body+'}Complete caption',0,end=1+(changes+1)*hold,layout=layout),colors
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder)
 for n,hold,config,retained,reason in [
  (1,1,s.SimplifyConfig(color_phase_change_interval=1e-320),True,None),
  (1,1,s.SimplifyConfig(color_phase_change_interval=1e308),False,'rate'),
  (1,1,s.SimplifyConfig(),True,None),(2,1,s.SimplifyConfig(),False,'rate'),
  (3,1.5,s.SimplifyConfig(),True,None),(25,2,s.SimplifyConfig(),True,None),
  (25,1,s.SimplifyConfig(),False,'rate'),(2,.2,s.SimplifyConfig(),False,'both'),
  (2,.2,s.SimplifyConfig(color_phase_change_interval=0),False,'hold'),
  (2,.2,s.SimplifyConfig(color_phase_min_hold=0),False,'rate'),
  (25,.2,s.SimplifyConfig(color_phase_min_hold=0,color_phase_change_interval=0),True,None),
  (1,2,s.SimplifyConfig(color_phase_min_hold=3),False,'hold'),
  (1,2,s.SimplifyConfig(color_phase_change_interval=5),False,'rate')]:
  name=f'{n}/{hold}/{config.color_phase_min_hold}/{config.color_phase_change_interval}'
  text,colors=fixture_phases(n,hold);a,b,c=(folder/x for x in ('source.ass','out.ass','again.ass'));a.write_text(text);before=a.read_bytes()
  with contextlib.redirect_stdout(io.StringIO()):
   stats=s.simplify_ass(a,b,config,font_metrics=metric)
   s.simplify_ass(b,c,config,font_metrics=metric)
  events=s.load_subtitle_events(b)[1]
  check(name+' expected phase count',len(events)==(n+1 if retained else 1))
  check(name+' complete text',all(s.OVERRIDE_RE.sub('',e.text)=='Complete caption' for e in events))
  check(name+' sequential exact boundaries',events[0].start_s==1 and events[-1].end_s==1+(n+1)*hold and all(x.end==y.start for x,y in zip(events,events[1:])))
  check(name+' original unchanged',a.read_bytes()==before)
  check(name+' full pipeline repeat stable',b.read_bytes()==c.read_bytes())
  check(name+' genuine contribution counts',stats['color_phase_changes_removed']==(0 if retained else n) and stats['color_phase_captions_limited']==int(not retained))
  if retained:
   check(name+' paint order preserved',[e.state['1c'] for e in events]==colors)
  else:
   check(name+' explicit reason',stats['color_phase_limits'][0]['reason']==reason)
   warnings=s.text_drop_warnings(stats);check(name+' structured notice',len(warnings)==1 and warnings[0]['changes']==n)
 # Ordinary unpositioned complete text uses the same source paint proof.
 text,colors=fixture_phases(1,1,layout='');a.write_text(text)
 with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
 check('unpositioned source phases',len(s.load_subtitle_events(b)[1])==2)
 # Tiny paint noise does not acquire a temporal phase or a removal count.
 text,_=fixture_phases(1,1,tiny=True);a.write_text(text)
 with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
 check('two-level noise not meaningful',stats['color_phase_changes_preserved']==stats['color_phase_changes_removed']==0)
 # Native renderer agrees with authored instantaneous color changes.
 text,_=fixture_phases(3,1.5);a.write_text(text)
 with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
 def frame(path,at):
  p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=640x360:r=1','-vf',
   f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
   '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
  return Image.frombytes('RGB',(640,360),p.stdout)
 for at in (.99,1.1,2.49,2.5,3.9,4,5.5,6.99,7):
  check(f'native phase boundary {at}',ImageChops.difference(frame(a,at),frame(b,at)).getbbox() is None)
# Unsupported geometry/ramp animation and independent transparency cannot
# manufacture a source-owned whole-caption palette.
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder);a=folder/'source.ass';b=folder/'out.ass'
 for label,tags in [('hidden source colors',r'\alpha&HFF&\t(2000,2000,\alpha&H00&)\t(1000,1000,\1c&HFFFFFF&)'),
                    ('continuous color',r'\t(0,2000,\1c&HFFFFFF&)'),
                    ('geometry change',r'\t(1000,1000,\fs50\1c&HFFFFFF&)'),
                    ('independent transparency',r'\1a&H40&\t(1000,1000,\1c&HFFFFFF&)')]:
  a.write_text(HEADER+event('{'+r'\bord2\1c&H000000&'+tags+'}Complete caption',0,end=5));before=a.read_bytes()
  with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
  check(label+' does not grant phase ownership',stats['color_phase_changes_preserved']==stats['color_phase_changes_removed']==0)
  check(label+' source unchanged',before==a.read_bytes())
 # A borderless prefix and outlined suffix retain distinct source contours.
 a.write_text(HEADER+event(r'{\bord0\1c&H2288CC&\t(2000,2000,\1c&HCC8822&)}AB{\bord2\3c&H112244&}CDEF',0,end=5))
 with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
 events=s.load_subtitle_events(b)[1]
 check('mixed contour family keeps both phases',len(events)==2)
 for e in events:
  widths=[p[1][4] for p in paints(e)]
  check('borderless and outlined spans retained',widths==[0,0,2,2,2,2])
 # Color changes staggered over the row are a sweep, not global steps.
 records=[]
 for i,word in enumerate(('AB','CD','EF','GH')):
  records.append(event(r'{\bord2\1c&H000000&'+rf'\t({500+i*700},{500+i*700},\1c&HFFFFFF&)'+'}'+word,
                       0,end=5,layout=rf'\pos({220+i*65},100)'))
 a.write_text(HEADER+''.join(records))
 with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
 check('staggered row does not count as global color changes',stats['color_phase_changes_removed']==stats['color_phase_changes_preserved']==0)
 # Intervening same-glyph-area content invalidates layered ownership.
 a.write_text(HEADER+event(r'{\bord2\1c&H000000&\3c&H112244&\t(2000,2000,\3c&HCCAA88&)}Complete caption',0,end=5)+
   event(r'{\bord0\1c&HFFFFFF&}Complete caption',2,end=5)+event(r'{\bord0\1c&HFFFFFF&}Foreign',1,end=5))
 with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
 check('intervening content blocks phase proof',stats['color_phase_changes_preserved']==0)
 # Source frame splitting and redundant paint copies do not change phase intent.
 for duplicate in (False,True):
  records=[]
  for start,end,color in [(1,2,'446688'),(2,3,'446688'),(3,4,'886644'),(4,5,'886644')]:
   if duplicate:records.append(event(r'{\bord2\1c&H000000&\3c&H112244&}Complete caption',0,start=start,end=end))
   records.append(event(r'{\bord'+('0' if duplicate else '2')+r'\1c&H'+color+r'&\3c&H112244&}Complete caption',1,start=start,end=end))
  a.write_text(HEADER+''.join(records))
  with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
  es=s.load_subtitle_events(b)[1]
  check(f'{duplicate} frame splitting and copies retain coherent foreground phases',
        [(e.start_s,e.end_s,e.state['1c']) for e in es]==[(1,3,'446688'),(3,5,'886644')])
  check(f'{duplicate} count switches once, not frames or layers',stats['color_phase_changes_preserved']==1)
# Corresponding source clocks differing below ASS event precision describe one
# synchronized boundary, not two tiny staggered changes.
parts=[]
for i,c in enumerate('ABCDEFGH'):
 e=parse(HEADER+event(r'{\bord2\1c&H112233&'+rf'\t({999 if i%2 else 1001},{999 if i%2 else 1001},\1c&HCCBBAA&)'+'}'+c,0,end=5,layout=rf'\pos({220+i*25},100)'))[0]
 e=s.dataclass_replace(e,source_index=500+i);parts.append((e,c,s.get_pos(e.text)))
row=s.TextRow(parts[0][0],parts,paint_rows=[[e for e,c,p in parts]],foreground=[e for e,c,p in parts])
timeline=s._caption_paint_timeline(row)
check('sub-centisecond clocks share one exact handoff',timeline is not None and [(a,b) for a,b,p in timeline.phases]==[(1,2),(2,5)])

# Source-owned outer contours follow the same phase decision as their complete
# foreground. Different styles and independent event splitting are incidental.
def glow_fixture(*,hold=.4,changes=3,split=False,gradient=False,layout=r'\pos(320,100)',
                 variant='',same_style=False):
 header=HEADER.replace('[Events]', 'Style: Halo,Volkhov,40,5,0,0,&H00FFFFFF,&H000000FF,&H00000000,&H00000000\n[Events]')
 colors=['335577','AA6633','4488AA','992255'][:changes+1]
 records=[]
 for i,color in enumerate(colors):
  start=1+i*hold;end=start+hold
  front=rf'{{\bord2\1c&H{color}&\3c&HFFFFFF&}}Complete caption'
  if gradient:front=front.replace('caption',r'{\1c&H'+color[::-1]+'&}caption')
  records.append(event(front,2,start=start,end=end,layout=layout))
  for j in range(2 if split else 1):
   a=start+(end-start)*j/(2 if split else 1);b=start+(end-start)*(j+1)/(2 if split else 1)
   shade='112244' if variant=='independent color' and i==1 else color
   alpha='60' if variant=='independent opacity' and i==1 else '40'
   width='7' if variant=='independent stroke' and i==1 else '5'
   body=rf'{{\bord{width}\blur2\1a&HFF&\3a&H{alpha}&\3c&H{shade}&}}Complete caption'
   if gradient:body=body.replace('caption',r'{\3c&H'+color[::-1]+'&}caption')
   if variant=='independent fill color' and i==1:body=r'{\1c&HCC4411&}'+body
   if variant=='independent fill exposure' and j==1:body=body.replace(r'\1a&HFF&',r'\1a&H00&')
   if variant=='coupled fill exposure' and i==0:body=body.replace(r'\1a&HFF&',r'\1a&H00&')
   if variant=='clip':body=r'{\clip(0,0,640,360)}'+body
   if variant=='gap' and i==1:a+=.05
   if variant=='outlasting' and i==len(colors)-1:b+=.1
   pos=r'\pos(330,100)' if variant=='different geometry' else layout
   line=event(body,0,start=a,end=b,layout=pos)
   if not same_style:line=line.replace(',Default,',',Halo,')
   records.append(line)
 if variant in ('interleaved','distant peer'):
  records.append(event(r'{\bord0}Independent',1,start=1,end=1+len(colors)*hold,
                       layout=r'\pos(320,100)' if variant=='interleaved' else r'\pos(320,290)'))
 return header+''.join(records)
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder);a=folder/'source.ass';b=folder/'out.ass';again=folder/'again.ass'
 for label,options,config,accepted in [
  ('limited glow',{},s.SimplifyConfig(),False),
  ('split glow',{'split':True},s.SimplifyConfig(),False),
  ('gradient glow',{'gradient':True},s.SimplifyConfig(),False),
  ('rotated glow',{'layout':r'\pos(320,100)\frz12'},s.SimplifyConfig(),False),
  ('implicit glow',{'layout':''},s.SimplifyConfig(),False),
  ('distant interleaved paint',{'variant':'distant peer'},s.SimplifyConfig(),False),
  ('accepted glow',{'hold':1.2,'changes':1},s.SimplifyConfig(max_blur=2),True),
  ('accepted split gradient',{'hold':1.2,'changes':1,'split':True,'gradient':True},s.SimplifyConfig(max_blur=2),True),
  ('unlimited glow',{},s.SimplifyConfig(color_phase_min_hold=0,color_phase_change_interval=0),True),
  ('retained blur',{},s.SimplifyConfig(max_blur=1),False),
  ('source composite exposure',{'variant':'coupled fill exposure'},s.SimplifyConfig(max_blur=1),False),
 ]:
  text=glow_fixture(**options);a.write_text(text);source=a.read_bytes()
  with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,config,font_metrics=metric)
  es=s.load_subtitle_events(b)[1];main=[e for e in es if e.layer=='2'];back=[e for e in es if e.layer=='0']
  expected=(options.get('changes',3)+1) if accepted else 1
  check(label+' complete phase families',len(main)==len(back)==expected)
  check(label+' counters count captions, not paint planes',stats['color_phase_captions_preserved' if accepted else 'color_phase_captions_limited']==1)
  for f,g in zip(main,back):
   check(label+' shared exact interval',(f.start,f.end)==(g.start,g.end))
   fp=paints(f);gp=paints(g)
   check(label+' shared span palette',[p[1][0] for p in fp]==[p[1][1] for p in gp])
   check(label+' authored contour transparency retained',all(p[1][3]==64 and p[1][4:]==(5,5) for p in gp))
   check(label+' complete literal retained',s.OVERRIDE_RE.sub('',f.text)==s.OVERRIDE_RE.sub('',g.text)=='Complete caption')
  if label=='source composite exposure':
   check('companion exposure comes from selected source appearance',back[0].state['1a']==(0 if main[0].state['1c']=='335577' else 255))
  check(label+' source immutable',a.read_bytes()==source)
  with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(b,again,config,font_metrics=metric)
  records=lambda path:[(e.fields()[:9],s.static_text_paint_geometry(e,set())[0]) for e in s.load_subtitle_events(path)[1]]
  check(label+' repeat paint, geometry and timing stable',records(b)==records(again))
  if label in ('accepted glow','accepted split gradient'):
   for at in (1.1,2.19,2.2,3.3):
    check(label+f' native authored phase {at}',ImageChops.difference(frame(a,at),frame(b,at)).getbbox() is None)
  if label in ('limited glow','retained blur'):
   check(label+' native composed caption stays static',ImageChops.difference(frame(b,1.1),frame(b,2.1)).getbbox() is None)
 a.write_text(glow_fixture(same_style=True))
 with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
 es=s.load_subtitle_events(b)[1]
 check('already flattened same-style stack remains one complete caption',len(es)==1 and s.OVERRIDE_RE.sub('',es[0].text)=='Complete caption')
 check('already flattened stack still applies one phase decision',stats['color_phase_captions_limited']==1 and stats['color_phase_changes_removed']==3)
 for variant in ('independent color','independent opacity','independent stroke','independent fill color','independent fill exposure','clip','gap','outlasting','different geometry','interleaved'):
  split=variant=='independent fill exposure'
  a.write_text(glow_fixture(variant=variant,split=split))
  with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
  es=s.load_subtitle_events(b)[1]
  if split:
   source=s._prepare_text_document(s.read_subtitle_document(a),a)
   prepared=s._prepare_source_text(source,set(),s.SimplifyConfig(),metric)
   check(variant+' cannot acquire companion ownership',all(not timeline.companions for timeline in prepared.paint_timelines))
  else:
   check(variant+' retains uncertain companion phases',len([e for e in es if e.layer=='0'])==4)
  check(variant+' foreground limits remain active',stats['color_phase_captions_limited']==1)

for key in ('color_phase_min_hold','color_phase_change_interval'):
 for v in (-1,float('nan'),float('inf')):
  try:s.SimplifyConfig(**{key:v})
  except ValueError:check(key+' rejects '+str(v),True)
  else:raise AssertionError(key+' accepted '+str(v))
(ROOT/'validation/caption-color-phase-checks.json').write_text(json.dumps(dict(checks_passed=len(checks),engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks=checks),indent=2)+'\n')
print(len(checks),'whole-caption phase checks passed')
