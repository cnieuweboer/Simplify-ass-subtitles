"""Exact embedded-font fades: actual viewport checks and translated paint crops."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/matched-backing-fade-renders';DEST.mkdir(exist_ok=True)
FONT=ROOT/'fonts/Shangri-S01E14-upload'
metric=s.FontMetrics([FONT]);face=metric.matching_face('Uniform',0,False)
assert face and Path(face.path).name=='Uniform-Bold.otf','Restore the supplied embedded Uniform Bold'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CURRENT=ROOT/'validation/matched-backing-fade-corpus/v203/Shangri-S01E14.ass'
report=json.loads(CURRENT.with_suffix('.json').read_text())
assert report['engine_sha256']==sha(ROOT/'simplify_ass.py') and report['output_sha256']==sha(CURRENT)
paths=[ROOT/'test-data/corpus/Shangri-S01E14.original.ass',
       ROOT/'validation/matched-backing-fade-corpus/v202/Shangri-S01E14.ass',CURRENT]
def read(path):
    lines,events,_,_=s.load_subtitle_events(path)
    header='\n'.join(lines[:next(i for i,l in enumerate(lines) if l.strip().casefold()=='[events]')+2])+'\n'
    return header,events
documents=[read(p) for p in paths]
def subset(header,events,path):
    path.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events));return path
def render(path,at,background):
    r=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i',f'color=c={background}:s=1920x1080:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={FONT}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    log=r.stderr.decode();assert re.search(r'fontselect: \(Uniform, 400, 0\) -> Uniform-Bold',log),log
    path.with_suffix('.render.log').write_text(log)
    return Image.frombytes('RGB',(1920,1080),r.stdout)
def ink(frame):return ImageChops.difference(frame,Image.new('RGB',frame.size,frame.getpixel((0,0)))).getbbox()
def translated(event):
    # Diagnostic translation of both anchor and rotation/perspective origin.
    # It is never written into the converter's output or the source subtitle.
    x,y=event.state['pos'];dx,dy=960-x,540-y
    def move(match):return '\\'+match[1]+'('+','.join(f'{float(v)+d:.12g}' for v,d in zip((match[2],match[3]),(dx,dy)))+')'
    text=re.sub(r'\\(pos|org)\(('+s.NUMBER+r'),\s*('+s.NUMBER+r')\)',move,event.text)
    return s.replace_event(event,text=text)
def expected(held,phase):
    # Independently authored unit fade: held readable RGBA, this phase's layout.
    # No backing-fade producer, span renderer or representative selector is used.
    palette=[]
    for sig,draw,literal in s.static_object_key(held,held.styles,allow_unpositioned=True)[-1]:
        state=dict(sig.formatting);palette.extend((c,state['1c'],state['3c']) for c in literal)
    layout=('an','pos','org','q','fn','fs','fscx','fscy','fsp','b','i','u','s','frz','frx','fry','fax','fay')
    header='{'+''.join(s.render_tag(k,phase.state[k]) for k in layout if k in phase.state)+'}'
    alpha=phase.state['1a'];body=header
    for char,fill,outline in palette:
        body+='{'+f'\\1c&H{fill}&\\3c&H{outline}&\\alpha&H{alpha:02X}&'+r'\bord2\shad0\blur0\be0}'+char
    return s.replace_event(phase,text=body,layer='0')
results=[]
for name in ('The Severed Sea','The Frontier Fleet','The New Land'):
    slug=name.replace(' ','-');held=next(e for e in documents[1][1] if s.OVERRIDE_RE.sub('',e.text)==name and e.start_s<=1323.05<e.end_s)
    for background in ('gray','white'):
        rows=[]
        for i,at in enumerate((1323.05,1323.10,1323.35,1323.75)):
            selected=[[e for e in events if e.kind=='Dialogue' and s.OVERRIDE_RE.sub('',e.text)==name and e.start_s<=at<e.end_s] for header,events in documents]
            assert all(selected) and len(selected[2])==1
            # Source supplies the phase's authored layout and fade alpha.
            front=min(selected[0],key=lambda e:e.state.get('bord',0));reference=expected(held,front)
            actual_path=subset(documents[2][0],selected[2],DEST/f'{slug}-{i}-actual.ass')
            expected_path=subset(documents[2][0],[reference],DEST/f'{slug}-{i}-expected.ass')
            actual=render(actual_path,at,background);independent=render(expected_path,at,background)
            assert ImageChops.difference(actual,independent).getbbox() is None,(name,at,'actual viewport differs')
            frames=[]
            for label,(header,_),events in zip(('source','v202','v203'),documents,selected):
                path=subset(header,[translated(e) for e in events],DEST/f'{slug}-{i}-{label}-translated.ass')
                frames.append(render(path,at,background).crop((700,450,1220,630)))
            path=subset(documents[2][0],[translated(reference)],DEST/f'{slug}-{i}-expected-translated.ass')
            assert ImageChops.difference(frames[2],render(path,at,background).crop((700,450,1220,630))).getbbox() is None
            row=Image.new('RGB',(1560,205),'#dddddd');draw=ImageDraw.Draw(row)
            for j,(label,frame) in enumerate(zip(('original','v202','v203'),frames)):
                row.paste(frame,(520*j,25));draw.text((520*j+5,5),s.format_time(at)+' '+label,fill='black')
            rows.append(row)
            results.append(dict(literal=name,at=s.format_time(at),background=background,
                actual_viewport_ink=ink(actual),native_expected_equal=True,translated_expected_equal=True))
        panel=Image.new('RGB',(1560,205*len(rows)))
        for i,row in enumerate(rows):panel.paste(row,(0,205*i))
        panel.save(DEST/f'{slug}-{background}.png')
(DEST/'summary.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),
    font_sha256=sha(Path(face.path)),comparisons=results,panels=6,
    note='Paint crops translate both pos and org for inspection; production scrolling geometry is unchanged.'),indent=2)+'\n')
print(len(results),'exact-font actual/translated comparisons; six source/v202/v203 panels')
