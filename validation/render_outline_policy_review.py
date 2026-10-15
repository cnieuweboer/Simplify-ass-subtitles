"""Native capped/authored-width comparisons; experiment is never production."""
from pathlib import Path
import hashlib, json, subprocess, sys
from PIL import Image, ImageChops, ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/outline-policy-renders';DEST.mkdir(exist_ok=True)
CORPUS=ROOT/'validation/outline-policy-corpus'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((CORPUS/'summary.json').read_text())
assert audit['experiment']
records={(r['case'],r['policy']):r for r in audit['cases']}
manifest=json.loads((ROOT/'test-data/corpus-manifest.json').read_text())
sources={c['name']:ROOT/c['source'] for c in manifest}
def subset(path,at,label):
    lines,events,_,_=s.load_subtitle_events(path)
    header='\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'
    active=[e for e in events if e.kind=='Dialogue' and e.start_s<=at<e.end_s]
    assert active,(path,at,'empty sample')
    out=DEST/(label+'.ass')
    out.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in active))
    return out
def render(path,at,background,size):
    result=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
        f'color=c={background}:s={size[0]}x{size[1]}:r=1','-vf',
        f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
        capture_output=True,check=True)
    return Image.frombytes('RGB',size,result.stdout)
def panel(label,frames,labels):
    w,h=frames[0].size;out=Image.new('RGB',(w*len(frames),h+25),'#dddddd');draw=ImageDraw.Draw(out)
    for i,(frame,title) in enumerate(zip(frames,labels)):
        out.paste(frame,(i*w,25));draw.text((i*w+5,5),title,fill='black')
    path=DEST/(label+'.png');out.save(path);return str(path.relative_to(ROOT))
results=[]
for name,at in [('Overlord-S04E02',133.2),('DemonSlayer-S04E02',1305.),
        ('Sword-S01E01-track6',1350.),('Attack-on-Titan-S02E01-track3',725.1)]:
    paths=[sources[name]]+[CORPUS/policy/(name+'.ass') for policy in ('capped','authored-experiment')]
    for policy,path in zip(('capped','authored-experiment'),paths[1:]):
        assert sha(path)==records[name,policy]['output_sha256']
    assert sha(paths[0])==records[name,'capped']['source_sha256']
    subsets=[subset(path,at,name+'-'+label) for path,label in zip(paths,('source','capped','authored'))]
    for background in ('gray','white'):
        frames=[render(path,at,background,(1920,1080)) for path in subsets]
        diff=ImageChops.difference(frames[1],frames[2]);box=diff.getbbox()
        image=panel(name+'-'+background,[f.resize((960,540)) for f in frames],
            ('original source', 'retained cap', 'authored-width experiment'))
        raw=diff.tobytes()
        results.append(dict(case=name,at=s.format_time(at),background=background,
            changed_pixels=sum(bool(r or g or b) for r,g,b in zip(raw[::3],raw[1::3],raw[2::3])),
            difference_box=box,panel=image))
header='''[Script Info]
PlayResX: 640
PlayResY: 360
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
for x,y,alpha in [(3.75,3.75,0),(6,6,0),(12,12,0),(.75,6,96)]:
    frames=[]
    for label,bx,by in [('capped',min(x,2),min(y,2)),('authored',x,y)]:
        path=DEST/f'synthetic-{x}-{y}-{label}.ass'
        path.write_text(header+'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,'+
            r'{\pos(320,100)\1c&HC6DDEA&\3c&H446688&'+f'\\xbord{bx}\\ybord{by}\\3a&H{alpha:02X}&'+'}Soft caption\n')
        frames.append(render(path,2.,'gray',(640,360)).crop((140,45,500,155)))
    results.append(dict(synthetic_widths=[x,y],alpha=alpha,
        panel=panel(f'synthetic-{x}-{y}',frames,('retained cap','authored width'))))
(DEST/'summary.json').write_text(json.dumps(dict(corpus_engine_sha256=audit['engine_sha256'],
    experiment_engine_sha256=sha(CORPUS/'authored-experiment.py'),comparisons=results),indent=2)+'\n')
print(len(results),'native outline comparisons')
