"""Native one-conversion source-fade handoffs, using independent v210 references.

Requires the private v210/v211 comparison produced by the parameterized
run_caption_glow_phase_corpus.py runner; media and fonts remain private.
"""
from pathlib import Path
import contextlib,hashlib,json,os,subprocess,sys
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
D=ROOT/'validation/caption-fade-phase-corpus';A=ROOT/'validation/faded-color-phase-investigation'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((D/'summary.json').read_text());engine=sha(ROOT/'simplify_ass.py')
assert summary['engine_sha256']==engine
BASE=A/'simplify_ass_v210.py';assert sha(BASE)==summary['baseline_sha256']
case=next(c for c in summary['cases'] if c['case']=='Kill-la-Kill-S01E20')
source=Path(case['current']['source']);current=Path(case['current']['output']);old=Path(case['baseline']['output'])
assert sha(source)==case['current']['source_sha256'] and sha(current)==case['current']['output_sha256']
fonts=source.parent.parent/'fonts';metric=s.FontMetrics([fonts]);assert metric.matching_face('Fontastique',-1,False)
original=s.load_subtitle_events(source)[1];new=s.load_subtitle_events(current)[1];before=s.load_subtitle_events(old)[1]
stats=case['current']['statistics'];assert stats['color_phase_changes_removed']==136 and stats['color_phase_captions_limited']==16
assert case['baseline']['statistics']['color_phase_changes_removed']==128
start,end=150.79,154.38;styles={'KLKOP2 #2 R','KLKOP2 #2 T','KLKOP2 #2 RGB','KLKOP2 #2 TGB'}
target=lambda e:e.kind=='Dialogue' and e.style in styles and e.start_s>=start-1e-6 and e.end_s<=end+1e-6
assert [e.fields() for e in before if not target(e)]==[e.fields() for e in new if not target(e)]
selected=[e for e in new if target(e)];assert len(selected)==4
assert all(e.start_s==start and e.end_s==end for e in selected)
document=s.read_subtitle_document(source)
unlimited=D/'Kill-la-Kill-S01E20.unlimited.ass';report=s.FontProcessingReport()
with (D/'unlimited.log').open('w') as log,contextlib.redirect_stdout(log):
    unrestricted=s.SimplifyConfig(color_phase_min_hold=0,color_phase_change_interval=0)
    unlimited_stats=s.simplify_ass(source,unlimited,unrestricted,font_metrics=metric,font_report=report)
assert not report.missing_families and unlimited_stats['color_phase_changes_preserved']==136
all_phases=s.load_subtitle_events(unlimited)[1];sharp=[e for e in all_phases if target(e)];assert len(sharp)==20
for style in styles:
    actual=[e for e in sharp if e.style==style];authored=[e for e in original if target(e) and e.style==style]
    assert [(e.start,e.end) for e in actual]==[(e.start,e.end) for e in authored]
    assert all(s.OVERRIDE_RE.sub('',a.text)==s.OVERRIDE_RE.sub('',b.text) for a,b in zip(actual,authored))

def no_fade(e):
    text=s.OVERRIDE_RE.sub(lambda m:'{'+''.join('\\'+k+v for k,v in s.tokenize_override(m[1]) if k!='fad')+'}',e.text)
    if e.style in {'KLKOP2 #2 R','KLKOP2 #2 T'}:text=r'{\bord2\xbord2\ybord2}'+text
    return s.replace_event(e,text=text)

# All phases are held to the authored handoff clocks, explicitly applying the
# already established foreground cap. v210 supplies independent serialization.
held=[]
for main in [e for e in selected if e.layer=='2']:
    appearance=next(e for e in original if target(e) and e.style==main.style and e.state['1c']==main.state['1c'])
    at=(appearance.start_s+appearance.end_s)/2
    backstyle=main.style.replace(' R',' RGB').replace(' T',' TGB')
    back=next(e for e in original if target(e) and e.style==backstyle and e.start_s<=at<e.end_s)
    for e in (appearance,back):held.append(s.replace_event(no_fade(e),start=main.start,end=main.end,start_s=start,end_s=end))
env=os.environ.copy();env['ASS_REGRESSION_FONT_BACKEND']='windows';env['PYTHONPATH']=str(ROOT/'validation/backend_startup')
references={}
for label,events in [('held',held),('sharp',[no_fade(e) for e in original if target(e)])]:
    path=D/(label+'.source.ass');s.write_subtitle_document(path,document,events)
    with (D/(label+'.reference.log')).open('w') as log:
        subprocess.run([sys.executable,str(BASE),str(path),'--fonts-dir',str(fonts),
            '--color-phase-min-hold','0','--color-phase-change-interval','0','--suffix','.reference'],
            cwd=ROOT,env=env,stdout=log,stderr=log,check=True)
    reference=path.with_name(path.stem+'.reference.ass');references[label]=reference
isolated={}
for label,events in [('original',[e for e in original if target(e)]),('v210',[e for e in before if target(e)]),
                     ('held',selected),('sharp',sharp)]:
    path=D/(label+'.actual.ass');s.write_subtitle_document(path,document,events);isolated[label]=path
font_selection=[]
def frame(path,at):
    p=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1','-vf',
        f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={fonts}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    selected_fonts=[line for line in p.stderr.decode().splitlines() if 'fontselect:' in line]
    if start<=at<end:assert any('Fontastique' in line or 'fontastique' in line for line in selected_fonts),selected_fonts
    font_selection.extend(selected_fonts);return Image.frombytes('RGB',(1920,1080),p.stdout)
times=(150.78,150.79,151.0,151.539,151.54,152.169,152.17,152.749,152.75,153.169,153.17,153.8,154.379,154.38)
for label in ('held','sharp'):
    for at in times:assert ImageChops.difference(frame(isolated[label],at),frame(references[label],at)).getbbox() is None,(label,at)
for at in (151.0,151.5,151.54,152.7,153.8):
    panel=Image.new('RGB',(1920,1440),'gray');draw=ImageDraw.Draw(panel)
    for i,(label,path) in enumerate(isolated.items()):
        im=frame(path,at);panel.paste(im.crop((0,0,1920,160)),(0,i*360+20));panel.paste(im.crop((0,920,1920,1080)),(0,i*360+180))
        draw.text((10,i*360+2),f'{label} at {s.format_time(at)}',fill='white')
    panel.save(D/f'fade-{at:.2f}.png')
def records(path):
    return [(e.fields()[:9],s.static_object_key(e,e.styles,allow_unpositioned=True)) for e in s.load_subtitle_events(path)[1]]
for path,config in [(current,s.SimplifyConfig()),(unlimited,unrestricted)]:
    repeat=path.with_name(path.stem+'.again.ass');report=s.FontProcessingReport()
    with (D/(path.stem+'.repeat.log')).open('w') as log,contextlib.redirect_stdout(log):
        repeated=s.simplify_ass(path,repeat,config,font_metrics=metric,font_report=report)
    assert not report.missing_families and records(path)==records(repeat)
    assert repeated['color_phase_changes_removed']==0
assert engine==sha(ROOT/'simplify_ass.py')
(D/'native-fades.json').write_text(json.dumps(dict(engine_sha256=engine,harness_sha256=sha(Path(__file__)),
    source_sha256=sha(source),output_sha256=sha(current),unlimited_sha256=sha(unlimited),native_samples=28,
    references={k:dict(path=str(v),sha256=sha(v)) for k,v in references.items()},times=times,font_selection=font_selection,
    unrelated_records_unchanged=True,default_and_unlimited_full_file_repeat_stable=True),indent=2)+'\n')
print('28 native held/sharp boundary samples; full-file repeat stable with default and disabled limits; unrelated records identical')
