"""Native gradient/spacing comparisons and visibility audit of retained composites."""
from pathlib import Path
from collections import Counter
import hashlib,json,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/inline-paint-renders';DEST.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
BASE=ROOT/'validation/frame-pose-corpus/windows';CURRENT=ROOT/'validation/inline-paint-corpus/windows'
summary=json.loads((CURRENT/'summary.json').read_text())
assert summary['engine_sha256']==sha(ROOT/'simplify_ass.py') and len(summary['cases'])==10
records={c['case']:c for c in summary['cases']}
def read(path):
    lines,events,_,_=s.load_subtitle_events(path)
    header='\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'
    return header,events

def render(path,at,background):
    p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s=1920x1080:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    return Image.frombytes('RGB',(1920,1080),p.stdout)

cases=[('Shangri-S01E14','test-data/corpus/Shangri-S01E14.original.ass','Jelzés','The New Land',1317.,(300,300,1100,480)),
       ('Attack-on-Titan-S02E01-track3','test-data/Attack-on-Titan-S02E01-track3-source.ass','Sign','YarckeliDistrict',725.6,(150,80,1300,260))]
panels=[]
for name,source_name,style,literal,at,crop in cases:
    source=ROOT/source_name;current=CURRENT/(name+'.ass');baseline=BASE/current.name
    assert records[name]['source_sha256']==sha(source) and records[name]['output_sha256']==sha(current)
    paths=[]
    for label,path in [('source',source),('v200',baseline),('v201',current)]:
        header,events=read(path)
        subset=DEST/f'{name}-{label}.ass'
        selected=[e for e in events if e.kind=='Dialogue' and e.style==style and
            s.OVERRIDE_RE.sub('',e.text)==literal and e.start_s<=at<e.end_s]
        assert selected,(name,label,'missing native sample')
        subset.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in selected));paths.append(subset)
    for background in ('gray','white'):
        frames=[render(path,at,background).crop(crop) for path in paths]
        width,height=frames[0].size;panel=Image.new('RGB',(width,3*(height+25)),'#dddddd');draw=ImageDraw.Draw(panel)
        for i,(label,frame) in enumerate(zip(('original','v200','v201'),frames)):
            draw.text((5,i*(height+25)+5),label,fill='black');panel.paste(frame,(0,i*(height+25)+25))
        path=DEST/f'{name}-{background}.png';panel.save(path);panels.append(str(path.relative_to(ROOT)))
# Every added geometry record already has a source-paint witness in the corpus
# check. Native rendering determines whether these retained copies add on-screen
# work or merely preserve off-canvas source evidence.
name='Shangri-S01E14';header,after=read(CURRENT/(name+'.ass'));_,before=read(BASE/(name+'.ass'))
def key(e):return (e.kind,tuple(e.fields()[:-1]),s.OVERRIDE_RE.sub('',e.text),e.state.get('pos'))
available=Counter(key(e) for e in before);extras=[]
for e in after:
    k=key(e)
    if available[k]:available[k]-=1
    else:extras.append(e)
assert len(extras)==records[name]['retained_composite_records']
visible=[]
for i,e in enumerate(extras):
    subset=DEST/f'retained-{i}.ass';subset.write_text(header+'Dialogue: '+','.join(e.fields())+'\n')
    frame=render(subset,(e.start_s+e.end_s)/2,'gray')
    blank=Image.new('RGB',frame.size,frame.getpixel((0,0)))
    if ImageChops.difference(frame,blank).getbbox() is not None:visible.append(i)
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),panels=panels,
    retained_composites=len(extras),retained_composites_visible=visible),indent=2)+'\n')
print(len(panels),'native source/v200/v201 panels;',len(extras),'retained source copies;',len(visible),'visible on screen')
