"""Native source/baseline/current comparisons for every changed corpus pose."""
from pathlib import Path
import hashlib,json,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/frame-pose-renders';DEST.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((ROOT/'validation/frame-pose-corpus/windows/summary.json').read_text())
assert summary['engine_sha256']==sha(ROOT/'simplify_ass.py') and len(summary['cases'])==10
sources={c['name']:ROOT/c['source'] for c in json.loads((ROOT/'test-data/corpus-manifest.json').read_text())}
sources['Goblin-Slayer-S01E02-track6']=ROOT/'test-data/Goblin-Slayer-S01E02-track6-source.ass'
def render(path,at,background):
    r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s=1920x1080:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    return Image.frombytes('RGB',(1920,1080),r.stdout)
results=[]
for case in summary['cases']:
    if not case['pose_changes']:continue
    source=sources[case['case']];current=ROOT/'validation/frame-pose-corpus/windows'/(case['case']+'.ass')
    baseline=ROOT/'validation/current-policy-corpus/windows'/current.name
    assert sha(source)==case['source_sha256'] and sha(current)==case['output_sha256']
    # Borrow resolved inputs read-only within this case. Repeated full ASS
    # parsing obscures renderer cost, especially for large animated sources.
    inputs=[(label,s.load_subtitle_events(path)[:2]) for label,path in
            [('source',source),('v198',baseline),('v200',current)]]
    for i,change in enumerate(case['pose_changes']):
        paths=[]
        for label,(lines,events) in inputs:
            header='\n'.join(lines[:next(j for j,line in enumerate(lines) if line.strip().casefold()=='[events]')+2])+'\n'
            subset=DEST/f'{case["case"]}-{i}-{label}.ass'
            chosen=[e for e in events if e.kind=='Dialogue' and e.style==change['style'] and
                e.start_s<change['end_s'] and e.end_s>change['start_s'] and
                (label=='source' or (s.OVERRIDE_RE.sub('',e.text)==change['text'] and
                    abs(e.start_s-change['start_s'])<1e-6 and abs(e.end_s-change['end_s'])<1e-6))]
            # Inspect the changed held caption separately from unchanged short
            # paint phases with the same literal; those phases can still vary.
            assert chosen,(case['case'],i,label,'missing caption interval')
            subset.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in chosen));paths.append(subset)
        at=(change['start_s']+change['end_s'])/2
        for background in ('gray','white'):
            frames=[render(p,at,background) for p in paths]
            # Crop a union around simplified sign paint; original source may
            # include decorative motion outside that crop. Panels are evidence,
            # not a pixel-equality requirement against an animated original.
            color=(128,128,128) if background=='gray' else (255,255,255)
            blank=Image.new('RGB',(1920,1080),color)
            boxes=[ImageChops.difference(blank,f).getbbox() for f in frames[1:]]
            assert boxes[-1] is not None,(case['case'],change['text'],'current simplified sign invisible')
            visible_boxes=[b for b in boxes if b is not None]
            crop=(max(0,min(b[0] for b in visible_boxes)-20),max(0,min(b[1] for b in visible_boxes)-20),
                  min(1920,max(b[2] for b in visible_boxes)+20),min(1080,max(b[3] for b in visible_boxes)+20))
            crops=[f.crop(crop) for f in frames];width,height=crops[0].size
            panel=Image.new('RGB',(width,3*(height+25)),'#dddddd');draw=ImageDraw.Draw(panel)
            for j,(label,frame) in enumerate(zip(('original','v198','v200'),crops)):
                draw.text((5,j*(height+25)+5),label,fill='black');panel.paste(frame,(0,j*(height+25)+25))
            file=DEST/f'{case["case"]}-{i}-{background}.png';panel.save(file)
            # The emitted pose remains static through its actual cue lifetime.
            for sample in (change['start_s']+.005,change['end_s']-.005):
                assert ImageChops.difference(frames[-1],render(paths[-1],sample,background)).getbbox() is None,(case['case'],i,'changing final pose')
            results.append(dict(case=case['case'],literal=change['text'],time_s=at,background=background,
                baseline_visible=boxes[0] is not None,current_visible=True,panel=str(file.relative_to(ROOT))))
    print(case['case'],'native changed-pose comparisons passed',flush=True)
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),samples=results),indent=2)+'\n')
print(len(results),'native comparison panels generated')
