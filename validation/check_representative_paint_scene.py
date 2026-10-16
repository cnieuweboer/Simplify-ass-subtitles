"""Hash-bound real opening validation after run_representative_paint_corpus.py.

Private corpus/fonts are prerequisites. Generated references and native panels
remain ignored development artifacts, never runtime recognition rules.
"""
from pathlib import Path
import contextlib,hashlib,io,json,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/representative-paint-corpus'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((DEST/'summary.json').read_text())
assert summary['engine_sha256']==sha(ROOT/'simplify_ass.py')
case=next(c for c in summary['cases'] if c['case']=='DemonSlayer-S04E02')
source=Path(case['current']['source']);output=Path(case['current']['output']);baseline=Path(case['baseline']['output'])
assert sha(source)==case['current']['source_sha256'] and sha(output)==case['current']['output_sha256']
assert sha(baseline)==case['baseline']['output_sha256']
original=s.load_subtitle_events(source)[1]
old=s.load_subtitle_events(baseline)[1];new=s.load_subtitle_events(output)[1]
wanted=lambda e:e.kind=='Dialogue' and e.style in {'OP - Romaji','OP - ENG'} and 72<e.start_s<162
old=[e for e in old if wanted(e)];new=[e for e in new if wanted(e)]
assert len(old)==len(new)==24
paint=set(s.CAPTION_PAINT_TAGS)|{'c','alpha'}
for a,b in zip(old,new):
    assert (a.style,a.start,a.end,s.OVERRIDE_RE.sub('',a.text))==(b.style,b.start,b.end,s.OVERRIDE_RE.sub('',b.text))
    assert s.static_text_paint_geometry(a,paint)[0]==s.static_text_paint_geometry(b,paint)[0]
    spans=s._literal_paint_ranges([b]);assert spans and all(states[0]['3c']!='000000' for _,states in spans)
    assert all(states[0].get(k,states[0].get('bord',0))==2 for _,states in spans for k in ('xbord','ybord'))
# Real source-row gradients survive the consumer rather than inheriting the
# first character's contour. Whole-caption phases still select one appearance.
for start in (105.79,128.69,131.32):
    event=next(e for e in new if e.style=='OP - Romaji' and abs(e.start_s-start)<.001)
    assert len({states[0]['3c'] for _,states in s._literal_paint_ranges([event])})>8
    planes=[e for e in original if e.kind=='Dialogue' and e.style=='OP - Romaji' and
            abs(e.start_s-start)<.001 and abs(e.end_s-event.end_s)<.001 and e.layer=='1']
    planes.sort(key=lambda e:s.get_pos(e.text)[0])
    authored=[(char,states[0]['3c']) for e in planes
              for text,states in s._literal_paint_ranges([s.dataclass_replace(e,effect='')])
              for char in text if not char.isspace()]
    retained=[(char,states[0]['3c']) for text,states in s._literal_paint_ranges([event])
              for char in text if not char.isspace()]
    assert retained==authored,(start,'source gradient literal correspondence')

for style in ('OP - Romaji','OP - ENG'):
    event=next(e for e in new if e.style==style and abs(e.start_s-117.43)<.001)
    assert {(states[0]['1c'],states[0]['3c']) for _,states in s._literal_paint_ranges([event])}=={('FFFFFF','DDD37F')}
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Mikadan',0,False)
# A repeat conversion is checked for the full file, including unrelated signs
# and the ending's already-proved gradient/lyric boundary.
again=DEST/'DemonSlayer-S04E02.again.ass';report=s.FontProcessingReport()
with (DEST/'repeat.log').open('w') as log,contextlib.redirect_stdout(log):
    s.simplify_ass(output,again,s.SimplifyConfig(),font_metrics=metric,font_report=report)
assert not report.missing_families and output.read_bytes()==again.read_bytes()
fonts=[];checks=[]
def frame(path,at):
    result=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    selected=[line for line in result.stderr.decode().splitlines() if 'fontselect:' in line]
    assert selected and all('Mikadan' in line for line in selected),selected
    fonts.extend(selected)
    return Image.frombytes('RGB',(1920,1080),result.stdout)
# Independently authored plain-caption references for real color/offset cases.
# Text and geometry are the unchanged prior release's; colors/widths come from
# the diagnosed source inner contour and completed foreground.
references={}
for start,fill,outline in [(89.53,'FFFFFF','073AA2'),(94.74,'FFFFFF','DDD37F'),
                           (117.43,'FFFFFF','DDD37F'),(123.27,'FFFFFF','DDD37F'),
                           (139.87,'FFFFFF','073AA2')]:
    records=[]
    for e in old:
        if abs(e.start_s-start)>.001:continue
        # Keep old geometry overrides, replace only the diagnosed paint.
        text=s.OVERRIDE_RE.sub(lambda m:'{'+''.join('\\'+tag+value for tag,value in s.tokenize_override(m[1]) if tag not in paint)+'}',e.text)
        text= '{'+rf'\1c&H{fill}&\3c&H{outline}&\bord2\xbord2\ybord2\shad0\xshad0\yshad0\blur0\be0\1a&H00&\3a&H00&'+'}'+text
        records.append(s.replace_event(e,text=text))
    document=s.parse_subtitle_document(output.read_text(encoding='utf-8-sig'))
    header_lines=[];in_events=False
    for line in document.lines:
        if line.strip().startswith('['):
            if in_events:break
            in_events=line.strip().casefold()=='[events]'
        if not line.startswith(('Dialogue:','Comment:')):header_lines.append(line.rstrip('\n'))
    header='\n'.join(header_lines)+'\n'
    reference=DEST/f'reference-{start}.ass'
    reference.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in records))
    references[start]=reference
for at,start in [(93,89.53),(98,94.74),(119,117.43),(121,117.43),
                  (123.28,123.27),(123.32,123.27),(126,123.27),
                  (139.88,139.87),(139.92,139.87),(141,139.87)]:
    current=frame(output,at);expected=frame(references[start],at)
    for box in [(0,0,1920,170),(0,900,1920,1080)]:
        assert ImageChops.difference(current.crop(box),expected.crop(box)).getbbox() is None,(at,box)
    checks.append(at)
    if at in (93,98,119,121,126,141):
        panel=Image.new('RGB',(1920,1200),'gray');draw=ImageDraw.Draw(panel)
        for i,(label,path) in enumerate([('Original',source),('v207',baseline),('v208',output)]):
            im=current if path==output else frame(path,at)
            panel.paste(im.crop((0,0,1920,170)),(0,25+i*400))
            panel.paste(im.crop((0,900,1920,1080)),(0,205+i*400))
            draw.text((20,5+i*400),f'{label} at {at//60}:{at%60:05.2f}',fill='white')
        panel.save(DEST/f'opening-{at}.png')
# Native views of the real reconstructed gradients supplement the exact
# source-literal paint correspondence above; reference geometry is unchanged.
for at in (109,130,133):
    panel=Image.new('RGB',(1920,1200),'gray');draw=ImageDraw.Draw(panel)
    for i,(label,path) in enumerate([('Original',source),('v207',baseline),('v208',output)]):
        im=frame(path,at)
        panel.paste(im.crop((0,0,1920,170)),(0,25+i*400))
        panel.paste(im.crop((0,900,1920,1080)),(0,205+i*400))
        draw.text((20,5+i*400),f'{label} gradient at {at//60}:{at%60:05.2f}',fill='white')
    panel.save(DEST/f'opening-{at}.png')
(DEST/'native-opening.json').write_text(json.dumps(dict(engine_sha256=sha(ROOT/'simplify_ass.py'),
    source_sha256=sha(source),output_sha256=sha(output),samples=checks,font_selection=fonts,
    references={str(p):sha(p) for p in references.values()},repeat_identical=True,
    lyric_content_timing_geometry_unchanged=True),indent=2)+'\n')
print('24 lyric cues retain content/timing/geometry; 10 exact native paint samples plus 3 gradient panels; full-file repeat identical')
