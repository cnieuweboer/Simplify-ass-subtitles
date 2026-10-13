"""Native exact-font entrance, hold and exit samples of settled lyric lifecycles."""
from pathlib import Path
import sys,json,hashlib,subprocess
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/glow-boundary-renders';DEST.mkdir(exist_ok=True)
path=ROOT/'validation/glow-boundary-corpus/windows/Goblin-Slayer-S01E02-track6.ass'
report=json.loads(path.with_suffix('.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert report['engine_sha256']==sha(ROOT/'simplify_ass.py') and report['output_sha256']==sha(path) and not report['missing_families']
baseline=ROOT/'validation/settled-glow-corpus/windows/Goblin-Slayer-S01E02-track6.ass'
source=ROOT/'test-data/Goblin-Slayer-S01E02-track6-source.ass'
original=s.load_subtitle_events(source)[1];lines,events,_,_=s.load_subtitle_events(path)
header='\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'
def frame(p,at):
 r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1','-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={p}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 return Image.frombytes('RGB',(1920,1080),r.stdout).crop((0,0,1920,160))
results=[]
for style in ['OP - R','OP - R Chant']:
 static=DEST/(style.replace(' ','_')+'.ass')
 static.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events if e.style==style))
 intervals=sorted({(e.start_s,e.end_s) for e in original if e.style==style and s._returning_glow_highlight(e) is not None})
 for start,end in intervals:
  held=[e for e in events if e.style==style and e.layer=='4' and e.start_s <= (start+end)/2 < e.end_s]
  if style=='OP - R Chant' and (not held or any(e.state.get('1a',0)!=0 or e.state.get('3a',0)==0 for e in held)):
   # Unproved neighboring chant families keep their existing effect fallback.
   continue
  assert held,(start,end)
  lifetime=(max(e.start_s for e in held),min(e.end_s for e in held))
  samples=sorted(set([start+(end-start)*.25,start+(end-start)*.75,lifetime[0]+.03,lifetime[1]-.03]))
  render_path=static
  if style=='OP - R Chant':
   # Inspect each accepted stack separately; another unproved effect can
   # appear during its boundary interval without belonging to this stack.
   render_path=DEST/f'chant-{start:.2f}.ass'
   intervals={(e.start,e.end) for e in held}
   render_path.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events if e.style==style and (e.start,e.end) in intervals))
  first=frame(render_path,samples[0])
  rendered=[frame(render_path,at) for at in samples[1:]]
  last=rendered[-1]
  assert sum(g>r*1.04 and g>b*1.04 for r,g,b in first.getdata())>100,('No green caption pixels',start,end)
  identical=all(ImageChops.difference(first,last).getbbox() is None for last in rendered)
  results.append(dict(style=style,start_s=start,end_s=end,lifetime=lifetime,samples=samples,static_lifecycle=identical))
  assert identical,(start,end)
  if style=='OP - R':
   # Timing extension must retain the already-corrected held appearance.
   reference=frame(baseline,start+(end-start)*.5)
   core=frame(path,start+(end-start)*.5)
   assert ImageChops.difference(reference,core).getbbox() is None,('Held appearance changed',start,end)
   results[-1]['held_appearance_unchanged']=True
  print(start,end,'pixel-identical static lifecycle',flush=True)
static=DEST/'OP_-_R.ass'
frame(static,145).crop((0,0,1100,160)).save(DEST/'opening-static.png')
frame(source,145).crop((0,0,1100,160)).save(DEST/'opening-original.png')
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),output_sha256=sha(path),samples=results),indent=2)+'\n')
