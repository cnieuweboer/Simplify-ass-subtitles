"""Exact Arial render: the retained caption stays static and preserves boundaries."""
from pathlib import Path
import contextlib,hashlib,io,json,runpy,subprocess,tempfile
from PIL import Image,ImageChops
import simplify_ass as s
ROOT=Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    helpers=runpy.run_path(str(ROOT/'check_complete_line_jitter.py'))
header,frames=helpers['HEADER'],helpers['frames']
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder);source=folder/'source.ass';output=folder/'out.ass'
    source.write_text(header+frames())
    with contextlib.redirect_stdout(io.StringIO()):stats=s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=s.FontMetrics([ROOT/'fonts']))
    twice=folder/'twice.ass'
    with contextlib.redirect_stdout(io.StringIO()):again=s.simplify_ass(output,twice,s.SimplifyConfig(),font_metrics=s.FontMetrics([ROOT/'fonts']))
    check('full conversion is idempotent',twice.read_bytes()==output.read_bytes() and again['text_effect_sequences_frozen']==0)
    es=[e for e in s.load_subtitle_events(output)[1] if e.kind=='Dialogue']
    check('full pipeline owns the frame sequence',len(es)==1 and stats['text_effect_sequences_frozen']==11)
    def render(path,at):
        p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1','-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}','-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
        return Image.frombytes('RGB',(1920,1080),p.stdout)
    hold=render(output,1.02)
    for at in (1.06,1.18,1.3,1.46):check('static rendered hold '+str(at),ImageChops.difference(hold,render(output,at)).getbbox() is None)
    before=render(output,.99);after=render(output,1.48)
    check('caption starts and ends at the source boundary',ImageChops.difference(before,after).getbbox() is None and ImageChops.difference(before,hold).getbbox() is not None)
    for at in (1.02,1.18,1.46):
        source_frame=render(source,at)
        before_box=ImageChops.difference(before,source_frame).getbbox();after_box=ImageChops.difference(before,hold).getbbox()
        check('same literal font footprint and bounded pose '+str(at),all(abs(a-b)<=4 for a,b in zip(before_box,after_box)))
report=dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks,exact_font='Arial (bundled arial.ttf)')
(ROOT/'validation/complete-line-jitter-render-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'exact-font jitter render checks passed')
