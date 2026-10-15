"""Native samples of the real complete-caption/gradient alternation and handoff.

Requires the restored Demon Slayer corpus, v206 diagnostic evidence and a fresh
run_source_alternation_corpus.py result. Generated media remain private assets.
"""
from pathlib import Path
import hashlib,json,subprocess,sys
from collections import Counter
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import simplify_ass as s
DEST=ROOT/'validation/source-alternation-corpus'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((DEST/'summary.json').read_text())
assert summary['engine_sha256']==sha(ROOT/'simplify_ass.py')
case=next(c for c in summary['cases'] if c['case']=='DemonSlayer-S04E02')
source=Path(case['current']['source']);output=Path(case['current']['output']);baseline=Path(case['baseline']['output'])
assert sha(source)==case['current']['source_sha256'] and sha(output)==case['current']['output_sha256']
assert sha(baseline)==case['baseline']['output_sha256']
events=s.load_subtitle_events(output)[1]
english=[e for e in events if e.kind=='Dialogue' and e.style=='ED - ENG' and 1319<e.start_s<1325]
assert len(english)==2
assert [(e.start_s,e.end_s) for e in english]==[(1319.01,1324.26),(1324.26,1329.43)]
assert [s.OVERRIDE_RE.sub('',e.text) for e in english]==[
    "It's chaos, falling in love in times like these",
    'No matter how many times sorrow overcomes the world']
spans=s.static_object_key(english[0],english[0].styles)[-1]
assert len({dict(sig.formatting)['1c'] for sig,draw,literal in spans})>2
assert len({dict(sig.formatting)['3c'] for sig,draw,literal in spans})>2
reference=ROOT/'validation/demon-phase-diagnosis/selected-gradient-with-boundary.ass'
proof=json.loads((ROOT/'validation/demon-phase-diagnosis/native-summary.json').read_text())
assert sha(reference)==proof['output_sha256']
frames={};fonts=[];samples=[1320,1321.57,1321.58,1323,1324.25,1324.26,1326,1329.43]
def render(path,at,box=(0,900,1920,1070),family="Planewalker",face="Planewalker-Bold",require_font=True):
    result=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    selection=[line for line in result.stderr.decode().splitlines() if 'fontselect:' in line and family in line]
    assert (selection or not require_font) and all(face in line for line in selection)
    fonts.extend(selection)
    return Image.frombytes('RGB',(1920,1080),result.stdout).crop(box)
for at in samples:
    frames[at]=render(output,at)
    assert ImageChops.difference(frames[at],render(reference,at)).getbbox() is None,(at,'proved phase/reference handoff')
    if at in (1320,1323,1326):
        panel=Image.new('RGB',(1920,630),'gray');draw=ImageDraw.Draw(panel)
        for i,(label,path) in enumerate([('Original',source),('v206',baseline),('v207',output)]):
            panel.paste(render(path,at),(0,35+i*210));draw.text((20,12+i*210),f'{label} at {at//60}:{at%60:05.2f}',fill='white')
        panel.save(DEST/f'native-{at}.png')
for at in samples[:5]:assert ImageChops.difference(frames[1320],frames[at]).getbbox() is None,at
assert ImageChops.difference(frames[1324.26],frames[1326]).getbbox() is None
# Inspect the only other corpus output change: a short whole-word phase
# replaces two letter events, using the established row geometry tolerance.
other=next(c for c in summary['cases'] if c['case']=='Overlord-S04E02')
old_path=Path(other['baseline']['output']);new_path=Path(other['current']['output'])
assert sha(old_path)==other['baseline']['output_sha256'] and sha(new_path)==other['current']['output_sha256']
old=s.load_subtitle_events(old_path)[1];new=s.load_subtitle_events(new_path)[1]
records=lambda es:Counter(tuple(e.fields()) for e in es)
removed=list((records(old)-records(new)).elements());added=list((records(new)-records(old)).elements())
assert len(removed)==2 and len(added)==1
old_letters=sorted([e for e in old if tuple(e.fields()) in removed],key=lambda e:s.get_pos(e.text)[0])
word=next(e for e in new if tuple(e.fields()) in added)
assert ''.join(s.OVERRIDE_RE.sub('',e.text) for e in old_letters)==s.OVERRIDE_RE.sub('',word.text)=='If'
assert all((e.start_s,e.end_s)==(word.start_s,word.end_s)==(1306.08,1306.16) for e in old_letters)
assert all(s.state_key(e,{'pos'})==s.state_key(word,{'pos'}) for e in old_letters)
metric=s.FontMetrics([ROOT/'fonts'])
expected=s.authored_glyph_positions(metric,word.state,'If',s.get_pos(word.text)[0],word.unit)
assert expected is not None
anchor_errors=[abs(s.get_pos(e.text)[0]-x) for e,(c,x) in zip(old_letters,expected)]
assert max(anchor_errors)<=1.5*word.unit
other_samples=[1306.07,1306.08,1306.12,1306.159,1306.16]
for at in other_samples:
    before=render(old_path,at,(0,0,1920,150),'Clearface SSi','ClearfaceSSiBold',require_font=1306.08<=at<1306.16)
    after=render(new_path,at,(0,0,1920,150),'Clearface SSi','ClearfaceSSiBold',require_font=1306.08<=at<1306.16)
    difference=ImageChops.difference(before,after).getbbox()
    if at<1306.08 or at>=1306.16:assert difference is None
    elif difference is not None:
        assert 670<=difference[0]<=difference[2]<=725 and difference[3]<=120,difference
    if at==1306.12:
        panel=Image.new('RGB',(1920,400),'gray');draw=ImageDraw.Draw(panel)
        for i,(label,im) in enumerate([('v206 separate letters',before),('v207 complete word',after)]):
            panel.paste(im,(0,35+i*200));draw.text((20,12+i*200),label,fill='white')
        panel.save(DEST/'native-overlord-If.png')
other_proof=dict(source_sha256=other['current']['source_sha256'],output_sha256=sha(new_path),
    samples=other_samples,word='If',interval=[1306.08,1306.16],anchor_errors=anchor_errors,
    paint_preserved=True,other_pixels_unchanged=True)
repeat=DEST/'DemonSlayer-S04E02.repeat.ass';report=s.FontProcessingReport()
s.simplify_ass(output,repeat,s.SimplifyConfig(),font_metrics=s.FontMetrics([ROOT/'fonts']),font_report=report)
assert not report.missing_families and output.read_bytes()==repeat.read_bytes()
assert summary['engine_sha256']==sha(ROOT/'simplify_ass.py') and sha(source)==case['current']['source_sha256']
(DEST/'native-summary.json').write_text(json.dumps(dict(engine_sha256=summary['engine_sha256'],
    harness_sha256=sha(Path(__file__)),source_sha256=sha(source),output_sha256=sha(output),
    reference_sha256=sha(reference),samples=samples,font_selection=fonts,static_across_handoff=True,
    next_caption_complete_and_unobscured=True,repeat_byte_identical=True,overlord_word_phase=other_proof),indent=2)+'\n')
print('13 real native samples verified: gradient phase/handoff and the short Overlord word; Demon Slayer repeat is byte stable.')
