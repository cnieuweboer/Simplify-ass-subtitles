"""Native libass samples of changed corpus intervals and the preserved ending gradient."""
from pathlib import Path
import hashlib,json,subprocess,sys
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/final-static-compaction-renders';DEST.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
def frame(path,at,width,height):
 result=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c=gray:s={width}x{height}:r=1',
  '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
  '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 return Image.frombytes('RGB',(width,height),result.stdout)
for case in json.loads((ROOT/'test-data/corpus-manifest.json').read_text()):
 before=ROOT/'validation/caption-ownership-corpus/windows'/(case['name']+'.ass')
 after=ROOT/'validation/final-static-compaction-corpus/windows'/before.name
 report=json.loads(after.with_suffix('.json').read_text());assert report['engine_sha256']==sha(ROOT/'simplify_ass.py') and report['output_sha256']==sha(after) and not report['missing_families']
 lines,a,_,_=s.load_subtitle_events(before);b=s.load_subtitle_events(after)[1]
 changed=[old for old,new in zip(a,b) if old.text!=new.text]
 times={(e.start_s+e.end_s)/2 for e in (changed[:1]+changed[len(changed)//2:len(changed)//2+1]+changed[-1:])}
 if case['name']=='DemonSlayer-S04E02':times.update((1291.1,1335.,1379.))
 width=int(s.script_resolution(lines,'x'));height=int(s.script_resolution(lines,'y'))
 for at in sorted(times):
  first,last=frame(before,at,width,height),frame(after,at,width,height)
  difference=ImageChops.difference(first,last)
  assert difference.getbbox() is None,(case['name'],at,difference.getbbox())
  records.append(dict(case=case['name'],time_s=at,pixel_identical=True,before_sha256=sha(before),after_sha256=sha(after)))
 (DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,runtime_sha256=sha(ROOT/'simplify_ass.py'),render_pairs=len(records),samples=records),indent=2)+'\n')
 print(case['name'],len(times),'pixel-identical corpus samples',flush=True)
print(len(records),'corpus render pairs passed')
