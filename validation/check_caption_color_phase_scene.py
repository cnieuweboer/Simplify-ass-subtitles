"""Native/current-source phase and next-cue checks after the v209 corpus runner."""
from pathlib import Path
import contextlib,hashlib,json,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/caption-color-phase-corpus';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((DEST/'summary.json').read_text());engine=sha(ROOT/'simplify_ass.py')
assert summary['engine_sha256']==engine
case=next(c for c in summary['cases'] if c['case']=='DemonSlayer-S04E02')
source=Path(case['current']['source']);current=Path(case['current']['output']);baseline=Path(case['baseline']['output'])
assert sha(current)==case['current']['output_sha256'] and sha(source)==case['current']['source_sha256']
old=s.load_subtitle_events(baseline)[1];new=s.load_subtitle_events(current)[1]
paint_tags=set(s.CAPTION_PAINT_TAGS)|{'alpha','c'}
styles={'OP - Romaji','OP - ENG','ED - Romaji','ED - ENG'}
plain=lambda e:s.OVERRIDE_RE.sub('',e.text)
covered=set()
for e in old:
 if e.kind!='Dialogue' or e.style not in styles:continue
 parts=sorted([n for n in new if n.kind=='Dialogue' and n.style==e.style and plain(n)==plain(e) and
               n.start_s>=e.start_s-1e-6 and n.end_s<=e.end_s+1e-6],key=lambda n:n.start_s)
 assert parts and parts[0].start==e.start and parts[-1].end==e.end
 assert all(a.end==b.start for a,b in zip(parts,parts[1:]))
 assert all(s.static_text_paint_geometry(p,paint_tags)[0]==s.static_text_paint_geometry(e,paint_tags)[0] for p in parts)
 covered.update(id(p) for p in parts)
assert covered=={id(e) for e in new if e.kind=='Dialogue' and e.style in styles}
for style in ('OP - Romaji','OP - ENG'):
 for start,ends in [(94.74,[97.37,100.71]),(117.43,[120.01,123.27]),(144.92,[146.09,148.22,150.01,151.59])]:
  parts=[e for e in new if e.style==style and start-1e-6<=e.start_s<ends[-1]-1e-6]
  assert len(parts)==len(ends) and [e.end for e in parts]==[s.format_time(t) for t in ends]
  if start==117.43:
   assert [{(st[0]['1c'],st[0]['3c']) for f,st in s._literal_paint_ranges([e])} for e in parts]==[
       {('92DDFC','2594FC')},{('FFFFFF','DDD37F')}]
ending=[e for e in new if e.style=='ED - ENG' and 1319<=e.start_s<1329]
assert [(e.start,e.end) for e in ending]==[(s.format_time(a),s.format_time(b)) for a,b in [(1319.01,1321.58),(1321.58,1324.26),(1324.26,1329.43)]]
assert [plain(e) for e in ending]==["It's chaos, falling in love in times like these"]*2+['No matter how many times sorrow overcomes the world']
assert len({st[0]['1c'] for f,st in s._literal_paint_ranges([ending[1]])})>2
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Mikadan',0,False) and metric.matching_face('Planewalker',-1,False)
repeat=DEST/'DemonSlayer-S04E02.again.ass';report=s.FontProcessingReport()
with (DEST/'repeat.log').open('w') as log,contextlib.redirect_stdout(log):
 s.simplify_ass(current,repeat,s.SimplifyConfig(),font_metrics=metric,font_report=report)
assert not report.missing_families and repeat.read_bytes()==current.read_bytes()
# Independent plain-caption references retain v208 placement and authored
# source colors, without source effects or dependence on v209 serialized tags.
document=s.parse_subtitle_document(baseline.read_text(encoding='utf-8-sig'));header=[];in_events=False
for line in document.lines:
 if line.strip().startswith('['):
  if in_events:break
  in_events=line.strip().casefold()=='[events]'
 if not line.startswith(('Dialogue:','Comment:')):header.append(line.rstrip('\n'))
header='\n'.join(header)+'\n'
def reference(start,fill,outline,style_set):
 records=[]
 for e in old:
  if e.style not in style_set or abs(e.start_s-start)>1e-6:continue
  body=s.OVERRIDE_RE.sub(lambda m:'{'+''.join('\\'+k+v for k,v in s.tokenize_override(m[1]) if k not in paint_tags)+'}',e.text)
  body=rf'{{\1c&H{fill}&\3c&H{outline}&\1a&H00&\3a&H00&\bord2\xbord2\ybord2\shad0\xshad0\yshad0\blur0\be0}}'+body
  records.append(s.replace_event(e,text=body))
 p=DEST/f'reference-{start}-{fill}-{outline}.ass';p.write_text(header+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in records));return p
refs={(94.74,0):reference(94.74,'FFFFFF','0F919A',styles),
      (94.74,1):reference(94.74,'FFFFFF','DDD37F',styles),
      (117.43,0):reference(117.43,'92DDFC','2594FC',styles),
      (117.43,1):reference(117.43,'FFFFFF','DDD37F',styles),
      (1319.01,0):reference(1319.01,'0E004C','100CC1',{'ED - ENG'})}
fonts=[];samples=[]
def frame(path,at,family):
 p=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1','-vf',
   f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
   '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 selected=[line for line in p.stderr.decode().splitlines() if 'fontselect:' in line and family in line]
 assert selected,(path,at,family);fonts.extend(selected)
 return Image.frombytes('RGB',(1920,1080),p.stdout)
for start,at,phase in [(94.74,97.36,0),(94.74,97.37,1),(117.43,120.00,0),(117.43,120.01,1)]:
 a=frame(current,at,'Mikadan');b=frame(refs[start,phase],at,'Mikadan')
 for box in [(0,0,1920,170),(0,900,1920,1080)]:assert ImageChops.difference(a.crop(box),b.crop(box)).getbbox() is None,(at,box)
 samples.append(at)
for at in (1320,1321.57,1321.58,1323,1324.25,1324.26,1326):
 expected=refs[1319.01,0] if at<1321.58 else baseline
 a=frame(current,at,'Planewalker');b=frame(expected,at,'Planewalker')
 box=(0,900,1920,1070);assert ImageChops.difference(a.crop(box),b.crop(box)).getbbox() is None,at;samples.append(at)
for at in (97.36,97.37,120,120.01,145.5,147,149,150.5,1320,1323):
 family='Mikadan' if at<160 else 'Planewalker'
 panel=Image.new('RGB',(1920,1200),'gray');draw=ImageDraw.Draw(panel)
 for i,(label,path) in enumerate([('Original',source),('v208',baseline),('v209',current)]):
  im=frame(path,at,family);panel.paste(im.crop((0,0,1920,170)),(0,25+i*400));panel.paste(im.crop((0,900,1920,1080)),(0,205+i*400))
  draw.text((20,5+i*400),f'{label} at {at//60}:{at%60:05.2f}',fill='white')
 panel.save(DEST/f'phase-{at}.png')
assert engine==sha(ROOT/'simplify_ass.py')
(DEST/'native-phases.json').write_text(json.dumps(dict(engine_sha256=engine,output_sha256=sha(current),source_sha256=sha(source),
    harness_sha256=sha(Path(__file__)),references={str(p):sha(p) for p in refs.values()},samples=samples,font_selection=fonts,
    repeat_identical=True,content_geometry_and_next_cue_preserved=True),indent=2)+'\n')
print('Real source phases: exact opening/ending boundaries, unchanged text/geometry, 11 native reference samples, full-file repeat identical')
