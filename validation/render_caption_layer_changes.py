"""Sample every changed Sword caption interval against its v182 rendering."""
from pathlib import Path
import hashlib,json,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/caption-layer-renders';DEST.mkdir(exist_ok=True)
summary=json.loads((ROOT/'validation/caption-layer-corpus/windows/summary.json').read_text())
assert summary['runtime_sha256']==hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()
records=[]
for case in summary['cases']:
    if not case['added']:continue
    name=case['case'];old=ROOT/'validation/lyric-layer-corpus/windows'/(name+'-current.ass')
    new=ROOT/'validation/caption-layer-corpus/windows'/(name+'.ass')
    assert hashlib.sha256(old.read_bytes()).hexdigest()==case['baseline_hash']
    assert hashlib.sha256(new.read_bytes()).hexdigest()==case['first_hash']
    es=s.load_subtitle_events(new)[1];changed={tuple(fields) for fields in case['added']}
    intervals={(e.start_s,e.end_s) for e in es if tuple(e.fields()) in changed}
    if name in ('Sword-S01E01','Sword-S01E01-track6'):
        # Explicitly retain the independent-card masking regression even when
        # none of that interval's caption layers change in the fixed output.
        intervals.add((125.9,125.93))
    for start,end in sorted(intervals):
        at=(start+end)/2;frames=[]
        for path in (old,new):
            run=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1',
                '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
                '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
            frames.append(Image.frombytes('RGB',(1920,1080),run.stdout))
        diff=ImageChops.difference(*frames)
        records.append(dict(case=name,time=at,interval=[start,end],pixel_identical=diff.getbbox() is None,bbox=diff.getbbox()))
        if diff.getbbox() is not None:
            board=Image.new('RGB',(3840,1110),'#202020');draw=ImageDraw.Draw(board)
            for x,label,frame in [(0,'v182',frames[0]),(1920,'v183',frames[1])]:
                draw.text((x+8,8),f'{name} / {at:.3f}s / {label}',fill='white');board.paste(frame,(x,30))
            board.save(DEST/(name+f'.{at:.3f}.comparison.png'))
        (DEST/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
        print(name,round(at,3),'same pixels',diff.getbbox() is None,flush=True)
print(len(records),'changed-interval render pairs completed',flush=True)
