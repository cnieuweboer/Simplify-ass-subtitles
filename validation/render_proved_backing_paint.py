"""Native original/v196/v197 ending comparisons on three backgrounds."""
from pathlib import Path
import json,hashlib,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/proved-backing-paint-renders';DEST.mkdir(exist_ok=True)
current=ROOT/'validation/proved-backing-paint-corpus/windows/Goblin-Slayer-S01E02-track6.ass'
previous=ROOT/'validation/karaoke-completion-bound-corpus/windows/Goblin-Slayer-S01E02-track6.ass'
source=ROOT/'test-data/Goblin-Slayer-S01E02-track6-source.ass'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads(current.with_suffix('.json').read_text())
assert report['engine_sha256']==sha(ROOT/'simplify_ass.py') and report['output_sha256']==sha(current) and report['source_sha256']==sha(source) and not report['missing_families']
def ending(path,name):
 lines,events,_,_=s.load_subtitle_events(path)
 header='\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'
 target=DEST/(name+'.ass');target.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events if e.style in {'ED-ROM','ED-ENG'}))
 return target
paths=[ending(p,n) for p,n in [(source,'original'),(previous,'v196'),(current,'v197')]]
def frame(path,at,background):
 r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s=1920x1080:r=1','-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 return Image.frombytes('RGB',(1920,1080),r.stdout).crop((200,15,1720,130))
results=[]
for at in (1241.7,1276.8,1299.9,1306.9,1321.8,1325.2):
 for background in ('black','gray','white'):
  frames=[frame(p,at,background) for p in paths]
  assert ImageChops.difference(frames[1],frames[2]).getbbox() is not None, (at,background,'no paint difference')
  panel=Image.new('RGB',(1520,3*140),'#dddddd');draw=ImageDraw.Draw(panel)
  for i,(name,im) in enumerate(zip(('original','v196 opaque border','v197 proved paint'),frames)):
   panel.paste(im,(0,i*140+25));draw.text((5,i*140+5),name,fill='black')
  file=DEST/f'ending-{at:.2f}-{background}.png';panel.save(file)
  results.append(dict(time_s=at,background=background,panel=str(file.relative_to(ROOT))))
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),source_sha256=sha(source),output_sha256=sha(current),samples=results),indent=2)+'\n')
print(len(results),'native full-ending comparison panels generated')
