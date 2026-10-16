"""Native matched-glow references for the private Kill la Kill phase fixture.

Run run_caption_glow_phase_corpus.py first. Each reference holds one real source
appearance and is simplified by hash-bound v209, independently of v210's proof.
"""
from pathlib import Path
import contextlib,hashlib,json,os,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
D=ROOT/'validation/caption-glow-phase-corpus';A=ROOT/'validation/kill-color-phase-investigation'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((D/'summary.json').read_text());engine=sha(ROOT/'simplify_ass.py')
assert summary['engine_sha256']==engine
case=next(c for c in summary['cases'] if c['case']=='Kill-la-Kill-S01E20')
source=Path(case['current']['source']);current=Path(case['current']['output']);old=Path(case['baseline']['output'])
assert sha(source)==case['current']['source_sha256'] and sha(current)==case['current']['output_sha256']
assert sha(A/'simplify_ass_v209.py')==summary['baseline_sha256']
original=s.load_subtitle_events(source)[1];new=s.load_subtitle_events(current)[1];before=s.load_subtitle_events(old)[1]
limits=case['current']['statistics']['color_phase_limits']
assert limits==case['baseline']['statistics']['color_phase_limits'] and len(limits)==14
font_folder=A/'fonts';metric=s.FontMetrics([font_folder]);assert metric.matching_face('Fontastique',-1,False)
document=s.read_subtitle_document(source);samples=[];font_selection=[];references={}
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
plain=lambda e:s.OVERRIDE_RE.sub('',e.text)

def frame(path,at):
    p=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1','-vf',
        f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={font_folder}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    selected=[line for line in p.stderr.decode().splitlines() if 'fontselect:' in line]
    assert any('Fontastique' in line or 'fontastique' in line for line in selected),selected
    font_selection.extend(selected)
    return Image.frombytes('RGB',(1920,1080),p.stdout)

for first in limits[::2]:
    rows=[c for c in limits if abs(c['start']-first['start'])<1e-6]
    assert len(rows)==2;reference_events=[];actual_events=[]
    for cue in rows:
        main=[e for e in new if e.style==cue['style'] and plain(e)==cue['text'] and abs(e.start_s-cue['start'])<1e-6]
        assert len(main)==1;main=main[0]
        prior=[e for e in before if e.style==main.style and e.start==main.start and e.end==main.end]
        assert len(prior)==1 and main.fields()==prior[0].fields()
        backstyle=cue['style'].replace(' R',' RGB').replace(' T',' TGB')
        back=[e for e in new if e.style==backstyle and plain(e)==cue['text'] and abs(e.start_s-cue['start'])<1e-6]
        assert len(back)==1 and (back[0].start,back[0].end)==(main.start,main.end)
        assert back[0].state['3c']==main.state['1c'] and back[0].state['3a']==63
        actual_events.extend([main,back[0]])
        appearance=next(e for e in original if e.style==main.style and plain(e)==cue['text'] and
                        e.start_s>=cue['start']-1e-6 and e.end_s<=cue['end']+1e-6 and e.state['1c']==main.state['1c'])
        at=(appearance.start_s+appearance.end_s)/2
        backing=next(e for e in original if e.style==backstyle and plain(e)==cue['text'] and e.start_s<=at<e.end_s)
        # v209 already reconstructs these foregrounds with the two-unit cap.
        # A static held source alone does not enter that reconstruction route.
        appearance=s.replace_event(appearance,text=r'{\bord2\xbord2\ybord2}'+appearance.text)
        for e in (appearance,backing):reference_events.append(s.replace_event(e,start=main.start,end=main.end,start_s=main.start_s,end_s=main.end_s))
    stem=f'held-{first["start"]:.2f}';ref_source=D/(stem+'.source.ass');ref_output=D/(stem+'.ass');actual=D/(stem+'.actual.ass')
    s.write_subtitle_document(ref_source,document,reference_events);s.write_subtitle_document(actual,document,actual_events)
    with (D/(stem+'.driver.log')).open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(A/'simplify_ass_v209.py'),
            '--source',str(ref_source),'--fonts',str(font_folder),'--output',str(ref_output)],
            env=env,cwd=ROOT,stdout=log,stderr=log,check=True)
    references[str(ref_output)]=sha(ref_output)
    times=[first['start']+.01,first['start']+.32,first['start']+.34,(first['start']+first['end'])/2,first['end']-.01]
    held=None
    for at in times:
        a=frame(actual,at);b=frame(ref_output,at)
        assert ImageChops.difference(a,b).getbbox() is None,(first['text'],at)
        if held is not None:assert ImageChops.difference(a,held).getbbox() is None
        held=a;samples.append(dict(caption=first['text'],at=at))

for at in (90.35,90.70,91.35,94.20,119.50):
    panel=Image.new('RGB',(1920,1080),'gray');draw=ImageDraw.Draw(panel)
    for i,(label,path) in enumerate([('Original',source),('v209',old),('v210',current)]):
        im=frame(path,at);panel.paste(im.crop((0,0,1920,160)),(0,i*360+20));panel.paste(im.crop((0,920,1920,1080)),(0,i*360+180))
        draw.text((10,i*360+2),f'{label} at {s.format_time(at)}',fill='white')
    panel.save(D/f'phase-{at:.2f}.png')

repeat=D/'Kill-la-Kill-S01E20.again.ass';font_report=s.FontProcessingReport()
with (D/'repeat.log').open('w') as log,contextlib.redirect_stdout(log):
    repeat_stats=s.simplify_ass(current,repeat,s.SimplifyConfig(),font_metrics=metric,font_report=font_report)
assert not font_report.missing_families
# Full-file repeat exposes one separate source-fade family. Prove that v209
# already changes its foreground on repeat; keep that result explicit rather
# than claiming whole-file idempotence or weakening the matched-family checks.
old_repeat=D/'Kill-la-Kill-S01E20.v209.again.ass'
with (D/'v209-repeat.driver.log').open('w') as log:
    subprocess.run([sys.executable,str(ROOT/'validation/measure_one.py'),'--engine',str(A/'simplify_ass_v209.py'),
        '--source',str(old),'--fonts',str(font_folder),'--output',str(old_repeat)],
        env=env,cwd=ROOT,stdout=log,stderr=log,check=True)
historical=json.loads(old_repeat.with_suffix('.json').read_text())
assert historical['engine_sha256']==summary['baseline_sha256'] and not historical['missing_families']
known=historical['statistics']['color_phase_limits']
assert len(known)==2 and sum(c['changes_removed'] for c in known)==8
assert all(abs(c['start']-150.79)<1e-6 and abs(c['end']-154.38)<1e-6 for c in known)
assert repeat_stats['color_phase_limits']==known
def records(path):
    return [(e.fields()[:9],s.static_object_key(e,e.styles,allow_unpositioned=True))
        for e in s.load_subtitle_events(path)[1] if not any(
            e.style in {c['style'],c['style'].replace(' R',' RGB').replace(' T',' TGB')} and
            plain(e)==c['text'] and e.start_s>=c['start']-1e-6 and e.end_s<=c['end']+1e-6 for c in known)]
assert records(current)==records(repeat),'Matched or unrelated repeat paint, geometry, timing or compositing changed'
assert engine==sha(ROOT/'simplify_ass.py')
(D/'native-glows.json').write_text(json.dumps(dict(engine_sha256=engine,source_sha256=sha(source),output_sha256=sha(current),
    harness_sha256=sha(Path(__file__)),references=references,samples=samples,font_selection=font_selection,
    repeat_matched_families_and_other_content_stable=True,preexisting_source_fade_repeat_limits=known,
    foreground_records_unchanged=True,companion_planes=14),indent=2)+'\n')
print('35 native source-appearance references; 14 static matched glows; matched repeat paint/geometry/timing preserved')
print('Separate pre-existing fade handoff: 2 captions, 8 more switches recognized on repeat at 2:30.79–2:34.38')
