"""Native exact-font samples of every affected top-left lyric hold."""
from pathlib import Path
import sys,json,hashlib,subprocess
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/settled-glow-renders';DEST.mkdir(exist_ok=True)
path=ROOT/'validation/settled-glow-corpus/windows/Goblin-Slayer-S01E02-track6.ass'
report=json.loads(path.with_suffix('.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert report['engine_sha256']==sha(ROOT/'simplify_ass.py') and report['output_sha256']==sha(path) and not report['missing_families']
source=ROOT/'test-data/Goblin-Slayer-S01E02-track6-source.ass'
original=s.load_subtitle_events(source)[1];lines,events,_,_=s.load_subtitle_events(path)
header='\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'
static=DEST/'opening.ass';static.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events if e.style=='OP - R'))
intervals=sorted({(e.start_s,e.end_s) for e in original if e.style=='OP - R' and s._returning_glow_highlight(e) is not None})
def frame(p,at):
 r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1','-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={p}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 return Image.frombytes('RGB',(1920,1080),r.stdout).crop((0,0,1920,160))
results=[]
for start,end in intervals:
 a,b=start+(end-start)*.25,start+(end-start)*.75
 first,last=frame(static,a),frame(static,b)
 assert sum(g>r*1.04 and g>b*1.04 for r,g,b in first.getdata())>100,('No green caption pixels',start,end)
 identical=ImageChops.difference(first,last).getbbox() is None
 results.append(dict(start_s=start,end_s=end,samples=[a,b],static_hold=identical))
 assert identical,(start,end)
 print(start,end,'pixel-identical static hold',flush=True)
frame(static,145).crop((0,0,1100,160)).save(DEST/'opening-static.png')
frame(source,145).crop((0,0,1100,160)).save(DEST/'opening-original.png')
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),output_sha256=sha(path),samples=results),indent=2)+'\n')
