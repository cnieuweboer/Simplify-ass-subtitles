"""Authored soft contours/absence survive; uncertain reconstruction is repaired."""
import test_paths
from pathlib import Path
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json,tempfile,contextlib,io,subprocess
from PIL import Image,ImageChops
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'validation/contrast-fallback-checks';DEST.mkdir(exist_ok=True)
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
checks=[]
def check(label,value):
 assert value,label;checks.append(label)
def state(**changes):return {**s.DEFAULT_STATE,'fn':'Volkhov','fs':40,'an':5,'pos':(320,100),'shad':0,'bord':0,**changes}
def render(selected,sources):
 proof=s._source_caption_paint(selected,sources)
 text=s.render_simplified_caption(selected,'Soft caption',source_paint=proof)
 return proof,text,s.effective_state(text,s.DEFAULT_STATE,s.DEFAULT_STATE)
CASES=[('borderless',state(**{'1c':'FFFFFF'}),(0,0),0,'000000'),
       ('white authored border',state(bord=1,**{'1c':'FFFFFF','3c':'FFFFFF'}),(1,1),0,'FFFFFF'),
       ('pale outline',state(bord=.75,**{'1c':'FFFFFF','3c':'DDDDDD'}),(.75,.75),0,'DDDDDD'),
       ('translucent outline',state(bord=1.25,**{'1c':'FFFFFF','3c':'667788','3a':96}),(1.25,1.25),96,'667788'),
       ('axis widths',state(bord=2,xbord=.5,ybord=1.5,**{'1c':'FFFFFF','3c':'DDDDDD'}),(.5,1.5),0,'DDDDDD'),
       ('hidden outline',state(bord=3,**{'1c':'FFFFFF','3c':'FFFFFF','3a':255}),(0,0),0,'000000')]
for label,selected,widths,alpha,color in CASES:
 for reverse in (False,True):
  sources=[selected.copy(),selected.copy()]
  if reverse:sources.reverse()
  before=deepcopy((selected,sources));proof,text,out=render(selected,sources)
  check(label+' proved',proof is not None)
  check(label+' authored contour',out['3c']==color and out['3a']==alpha and tuple(out.get(k,out['bord']) for k in ('xbord','ybord'))==widths)
  check(label+' source immutable',before==(selected,sources))
  second=s.render_simplified_caption(out,'Soft caption',source_paint=s._source_caption_paint(out,[out]))
  check(label+' render repeat stable',second==text)
 for background in ('black','gray','white'):
  # Native source and proved output are pixel-identical for static unblurred paint.
  a=DEST/f'{label}-source.ass';b=DEST/f'{label}-current.ass'
  source='{'+''.join(s.render_tag(k,v) for k,v in selected.items() if k in {'fn','fs','an','pos','1c','3c','3a','bord','xbord','ybord','shad'})+'}Soft caption'
  frames=[]
  for path,body in ((a,source),(b,text)):
   path.write_text(HEADER+f'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{body}\n')
   r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s=640x360:r=1','-vf',f'settb=1/1000,setpts=PTS+2000,ass=filename={path}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
   frames.append(Image.frombytes('RGB',(640,360),r.stdout))
  check(label+' '+background+' exact native source paint',ImageChops.difference(*frames).getbbox() is None)
# Selected paint alone and incomplete/unsupported source evidence cannot bypass repair.
white=state(bord=1,**{'1c':'FFFFFF','3c':'FFFFFF'})
for label,sources in [('missing',[]),('clip',[{**white,'clip':'(0,0,100,100)'}]),
 ('conflicting',[white,{**white,'3c':'888888'}]),('invalid',[{**white,'3c':'invalid'}]),
 ('drawing',[{**white,'p':1}]),('layout mismatch',[{**white,'fs':41}]),
 ('negative width',[{**white,'bord':-1}]),('nonfinite width',[{**white,'bord':float('nan')}])]:
 proof,text,out=render(white,sources)
 check(label+' uncertain',proof is None)
 check(label+' repaired white on white',out['3c']=='000000' and out['3a']==0 and out['bord']==2)
fade_states=[state(bord=1,**{'1c':'FFFFFF','3c':'DDDDDD','1a':a,'3a':a}) for a in (0,64,128)]
proof=s._source_caption_paint(fade_states[-1],fade_states)
check('coupled fill/outline fades retain one held contour',proof is not None and proof.outline=='DDDDDD' and proof.outline_alpha==0 and proof.border==(1,1))
shadow=state(bord=1,xshad=1000,**{'1c':'000000','3c':'FFFFFF','4c':'FFFFFF','pos':(-680,100)})
body=s.render_simplified_caption(shadow,'a',source_paint=s._source_caption_paint(shadow,[shadow]),measurement=s.DocumentMeasurementContext(canvas=(640,360)))
paint=s.effective_state(body,s.DEFAULT_STATE,s.DEFAULT_STATE)
check('offcanvas shadow transfer invalidates foreground contour proof',paint['1c']=='FFFFFF' and paint['3c']=='000000' and paint['bord']==2)
for label,sources in [('translucent supporting fill',[state(**{'1c':'FFFFFF'}),state(**{'1c':'000000','1a':64})]),
 ('opaque alternate support',[state(**{'1c':'FFFFFF'}),state(**{'1c':'000000'})]),
 ('shadow support',[state(shad=2,**{'1c':'FFFFFF'})])]:
 check(label+' not proved borderless',s._source_caption_paint(state(**{'1c':'FFFFFF'}),sources) is None)
check('thick authored contours keep the existing two-unit budget',s._source_caption_paint(state(bord=3.75),[state(bord=3.75)]).border==(2,2))
# Animated row assembly retains independent contour alpha and width spans.
def event(i,tags):return f'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{{\\pos({200+i*40},100){tags}}}{"abc"[i]}\n'
es=list(s._resolve_document_state(s.parse_subtitle_document(HEADER+event(0,r'\bord0')+event(1,r'\bord1\3c&HDDDDDD&\3a&H60&')+event(2,r'\bord0'))).events.values())
body=s.render_merged_caption(es,list('abc'),'abc',animated=True,an=5,pos=(320,100),fscx=100,fscy=100)
obj=s.static_object_key(s.replace_event(es[0],text=body),es[0].styles,allow_unpositioned=True)
spans=[(dict(sig.formatting),literal) for sig,draw,literal in obj[-1] if literal]
check('per-fragment outline/absence preserved',[(p['bord'],p['3a']) for p,t in spans]==[(0,0),(1,96),(0,0)])
# Complete line jitter is a proved source route and normal conversions retain it.
with tempfile.TemporaryDirectory() as d:
 source=Path(d)/'source.ass';out=Path(d)/'out.ass';again=Path(d)/'again.ass'
 frames=''.join(f'Dialogue: 0,{s.format_time(1+i*.04)},{s.format_time(1+(i+1)*.04)},Default,,0,0,0,,{{\\pos({320+(.4 if i%2 else 0)},100)\\bord.75\\3c&HDDDDDD&}}Soft caption\n' for i in range(12))
 source.write_text(HEADER+frames);before=source.read_bytes()
 with contextlib.redirect_stdout(io.StringIO()):
  s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=metric)
  s.simplify_ass(out,again,s.SimplifyConfig(),font_metrics=metric)
 es=s.load_subtitle_events(out)[1]
 check('pipeline source contour retained',len(es)==1 and es[0].state['bord']==.75 and es[0].state['3c']=='DDDDDD')
 check('pipeline source unchanged',source.read_bytes()==before)
 check('pipeline repeat stable',out.read_bytes()==again.read_bytes())
# A reveal route deliberately retaining fill transparency also keeps its
# coupled authored contour transparency, instead of making it opaque.
translucent_text=HEADER+'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\\pos(320,100)\\bord1\\3c&HDDDDDD&\\alpha&H60&}Soft caption\n'
translucent=next(iter(s._resolve_document_state(s.parse_subtitle_document(translucent_text)).events.values()))
reveal=s._select_progressive_reveal_caption([(translucent,translucent.state)],[(translucent,'',translucent.state,None)],'Soft caption')
paint=s.effective_state(reveal.body,translucent.defaults,translucent.styles)
check('reveal preserves coupled fill and contour transparency',paint['1a']==96 and paint['3a']==96 and paint['bord']==1)
# Decorative contours cannot replace a selected foreground's original stroke.
stack_text=HEADER+'Dialogue: 1,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\\pos(320,100)\\1c&HFFFFFF&\\3c&H123456&\\3a&H40&\\bord2\\blur3}Held word\n'+'Dialogue: 2,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\\pos(320,100)\\1c&HC6DDEA&\\3c&HDDEEFF&\\bord.75}Held word\n'
doc=s._resolve_document_state(s.parse_subtitle_document(stack_text));events=list(doc.events.values())
visible={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events};before=deepcopy((events,doc.events))
held,count=s.flatten_stacked_text_copies(events,visible,set(doc.events),source_events=doc.events,font_metrics=metric)
check('original foreground stroke survives conflicting decorations',len(held)==1 and held[0].state['3c']=='DDEEFF' and held[0].state['bord']==.75)
check('original foreground source remains borrowed',before==(events,doc.events))
uncertain,_=s.flatten_stacked_text_copies(events,visible,set(doc.events),source_events=None,font_metrics=metric)
check('no original foreground proof keeps conflict fallback',len(uncertain)==1 and uncertain[0].state['bord']==2 and uncertain[0].state['3c']=='000000')
(DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'source contrast fallback checks passed')
