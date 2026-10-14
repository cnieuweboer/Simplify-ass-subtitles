"""Native source/v197/v198 samples for soft lyrics and tracked signs."""
from pathlib import Path
import hashlib,json,subprocess,sys
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/contrast-fallback-renders';DEST.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
cases=[('Goblin-Slayer-S01E02-track6','test-data/Goblin-Slayer-S01E02-track6-source.ass',(292.,),(400,580,1500,810),{'Ep_Title'}),
 ('Goblin-Slayer-S01E02-track6','test-data/Goblin-Slayer-S01E02-track6-source.ass',(1241.7,1299.9,1325.2),(150,15,1770,140),{'ED-ROM','ED-ENG'}),
 ('Attack-on-Titan-S02E01-track3','test-data/Attack-on-Titan-S02E01-track3-source.ass',(725.5,725.75),(350,220,1300,830),{'Sign'})]
results=[]
for name,source_name,times,crop,styles in cases:
 source=ROOT/source_name;old=ROOT/'validation/proved-backing-paint-corpus/windows'/(name+'.ass');new=ROOT/'validation/contrast-fallback-corpus/windows'/(name+'.ass')
 report=json.loads(new.with_suffix('.json').read_text());assert report['engine_sha256']==sha(ROOT/'simplify_ass.py') and report['output_sha256']==sha(new) and not report['missing_families']
 paths=[]
 for label,p in [('original',source),('v197',old),('v198',new)]:
  lines,events,_,_=s.load_subtitle_events(p);header='\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'
  subset=DEST/f'{name}-{label}.ass';subset.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events if e.style in styles));paths.append(subset)
 for at in times:
  for background in ('gray','white'):
   frames=[]
   for p in paths:
    r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s=1920x1080:r=1','-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={p}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    frames.append(Image.frombytes('RGB',(1920,1080),r.stdout).crop(crop))
   width,height=frames[0].size;panel=Image.new('RGB',(width,3*(height+25)),'#dddddd');draw=ImageDraw.Draw(panel)
   for i,(label,frame) in enumerate(zip(('original','v197','v198'),frames)):
    draw.text((5,i*(height+25)+5),label,fill='black');panel.paste(frame,(0,i*(height+25)+25))
   file=DEST/f'{name}-{at:.2f}-{background}.png';panel.save(file);results.append(dict(case=name,time_s=at,background=background,panel=str(file.relative_to(ROOT))))
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),samples=results),indent=2)+'\n');print(len(results),'native source/v197/v198 comparison panels generated')
