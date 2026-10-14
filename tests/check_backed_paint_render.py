"""Proved backed rows retain subdued paint through rendering and reconstruction."""
import test_paths
from pathlib import Path
from copy import deepcopy
import contextlib,io,json,tempfile,subprocess
from PIL import Image,ImageChops
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'validation/backed-paint-checks';DEST.mkdir(exist_ok=True)
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
def check(name,value):
 assert value,name
 checks.append(name)
def fixture(*,color='000000',alpha=16,blur=5.7,mutation='',reverse=False):
 text=HEADER
 for i,word in enumerate('Abcd'):
  x=160+i*50;t=1.3+i*.2
  backing=rf'\1c&H{color}&\1a&H{alpha:02X}&\blur{blur}'
  if mutation=='different backing' and i==2:backing=backing.replace(color,'778899')
  if mutation=='stroke':backing+=r'\bord1'
  if mutation=='tracking':backing+=r'\fsp1'
  def event(layer,a,b,tags):return f'Dialogue: {layer},{s.format_time(a)},{s.format_time(b)},Default,,0,0,0,,{{\\an5\\pos({x},100){tags}}}{word}\n'
  if mutation=='scale frames':text+=event(1,1,1.2,backing+r'\fscx105\fscy105')+event(1,1.2,4,backing)
  elif mutation!='missing backing' or i!=2:text+=event(1,1,4,backing)
  if mutation=='duplicate backing' and i==2:text+=event(1,1,4,backing)
  text+=event(2,1,4,r'\1c&HC6DDEA&\blur0.675'+(r'\fsp1' if mutation=='tracking' else ''))
  text+=event(3,t,t+.2,r'\1c&H6468FF&\blur1.35\t(0,200,\1c&HC6DDEA&\blur0.675)'+(r'\fsp1' if mutation=='tracking' else ''))
 events=list(s._resolve_document_state(s.parse_subtitle_document(text)).events.values())
 if reverse:events.reverse()
 words={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events};positions={e.source_index:s.get_pos(e.text) for e in events}
 return text,events,words,positions
for color in ('000000','225577'):
 for alpha in (16,96,176):
  for blur in (3,5.7,9):
   outputs=[]
   for reverse in (False,True):
    _,events,words,positions=fixture(color=color,alpha=alpha,blur=blur,reverse=reverse)
    before=deepcopy((events,words,positions));out,removed=s.collapse_backed_glyph_pulses(events,words,positions,metric)
    label=f'{color} alpha={alpha} blur={blur} reverse={reverse}'
    check(label+' complete collapse',len(out)==4 and removed==8)
    check(label+' subdued representative contour',all(0<e.state['3a']<255 for e in out))
    check(label+' coherent row paint',len({(e.state['1c'],e.state['3c'],e.state['3a']) for e in out})==1)
    check(label+' source immutable',before==(events,words,positions))
    check(label+' literal timing geometry',[words[e.source_index] for e in out]==[s.OVERRIDE_RE.sub('',e.text) for e in out] and all((e.start_s,e.end_s,s.get_pos(e.text))==(1,4,positions[e.source_index]) for e in out))
    check(label+' no extra effects',all(not s.event_override_tokens(e) or not any(k in {'t','move','fad'} for k,v in s.event_override_tokens(e)) for e in out))
    outputs.append(sorted((s.get_pos(e.text),e.state) for e in out))
   check(f'{color} {alpha} {blur} ordering',outputs[0]==outputs[1])
_,events,words,positions=fixture(mutation='scale frames')
out,_=s.collapse_backed_glyph_pulses(events,words,positions,metric)
check('frame pulses excluded from resting backing palette',len(out)==4 and all(0<e.state.get('3a',0)<255 for e in out))
for mutation in ('different backing','stroke','tracking','missing backing','duplicate backing'):
 _,events,words,positions=fixture(mutation=mutation)
 before=deepcopy((events,words,positions));out,_=s.collapse_backed_glyph_pulses(events,words,positions,metric)
 check(mutation+' does not claim sampled paint',not any(e.state.get('3a',0)>0 and e.state.get('bord',0)>0 for e in out))
 check(mutation+' borrowed inputs unchanged',before==(events,words,positions))
_,events,words,positions=fixture()
out,_=s.collapse_backed_glyph_pulses(events,words,positions,None)
check('no font owner keeps fallback',all(e.state.get('3a',0)==0 for e in out))
# Ordinary rendering still uses the legacy contrast policy; proved paint is explicit.
ordinary=s.effective_state(s.render_simplified_caption({'1c':'FFFFFF','3c':'FFFFFF','bord':0},'a'),s.DEFAULT_STATE,s.DEFAULT_STATE)
check('ordinary fallback unchanged',ordinary['3c']=='000000' and ordinary['bord']==2 and ordinary['3a']==0)
# Normal conversions must preserve the proof beyond this pass.
with tempfile.TemporaryDirectory() as d:
 root=Path(d);source=root/'source.ass';out=root/'out.ass';again=root/'again.ass'
 source.write_text(fixture()[0]);before=source.read_bytes()
 with contextlib.redirect_stdout(io.StringIO()):
  s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=metric)
  s.simplify_ass(out,again,s.SimplifyConfig(),font_metrics=metric)
 output=s.load_subtitle_events(out)[1]
 check('pipeline retained contour opacity',bool(output) and all(0<e.state.get('3a',0)<255 for e in output))
 check('pipeline source unchanged',source.read_bytes()==before)
 check('pipeline repeat stable',out.read_bytes()==again.read_bytes())
 # Contrast against the old hard-border rendering on several backgrounds.
 lines,events,_,_=s.load_subtitle_events(out);old=root/'old.ass'
 old.write_text('\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'+''.join('Dialogue: '+','.join(s.replace_event(e,text=e.text.replace(s.render_tag('3a',e.state['3a']),r'\3a&H00&')).fields())+'\n' for e in events))
 for background in ('black','gray','white'):
  frames=[]
  for name,path in [('source',source),('current',out),('hard',old)]:
   r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s=640x360:r=1','-vf',f'settb=1/1000,setpts=PTS+3000,ass=filename={path}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
   image=Image.frombytes('RGB',(640,360),r.stdout);image.save(DEST/f'{background}-{name}.png');frames.append(image)
  check(background+' softened native result',ImageChops.difference(frames[1],frames[2]).getbbox() is not None)
(DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'proved backing paint checks passed')
