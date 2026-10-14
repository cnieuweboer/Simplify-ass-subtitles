"""Native exact-font checks for source-supported moving poses and boundary holds."""
import test_paths
from pathlib import Path
import contextlib,hashlib,io,json,runpy,subprocess,tempfile
from PIL import Image,ImageChops
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
    h=runpy.run_path(str(ROOT/'tests/check_frame_pose_selection.py'))
    boundary=runpy.run_path(str(ROOT/'tests/check_rotating_entrance_fades.py'))
checks=[]
def check(label,value):
    assert value,label;checks.append(label)
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
def convert(path,out):
    report=s.FontProcessingReport()
    with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(path,out,s.SimplifyConfig(),font_metrics=metric,font_report=report)
    check('all exact fonts available '+path.name,not report.missing_families)
def render(path,at,size,background):
    r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s={size[0]}x{size[1]}:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    return Image.frombytes('RGB',size,r.stdout)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    expected=directory/'expected.ass';expected.write_text(h['HEADER']+h['records']([(1,1.48,330,0)]))
    outputs=[]
    for i,specs in enumerate((h['SPECS'],h['split'])):
        source=directory/f'moving-{i}.ass';out=directory/f'moving-{i}.simple.ass'
        frames=[(a,b,x,min(alpha,110)) for a,b,x,alpha in specs]
        source.write_text(h['HEADER']+''.join(h['records'](frames,layer=layer,
            tags=r'\1c&HDDDDDD&\bord4\blur4' if layer==0 else '') for layer in range(2)))
        convert(source,out);outputs.append(out)
        twice=directory/f'twice-{i}.ass';convert(out,twice)
        check('moving caption stable on second run '+str(i),out.read_bytes()==twice.read_bytes())
    for background in ('gray','white'):
        for at in (.99,1.02,1.18,1.3,1.47,1.48):
            wanted=render(expected,at,(640,360),background)
            for out in outputs:
                check(f'{out.name} authored source pose/timing {background} {at}',
                    ImageChops.difference(wanted,render(out,at,(640,360),background)).getbbox() is None)
    # Existing entrance/exit ownership proofs must keep the authored upright
    # rest pose, rather than selecting a brighter transformed boundary glyph.
    for phase in ('entrance','exit'):
        source=directory/f'{phase}.ass';out=directory/f'{phase}.simple.ass'
        header=h['HEADER'].replace('640','1920').replace('360','1080').replace(',1,1,0,5,',',1,2,0,5,')
        source.write_text(boundary['fixture'](phase,40,'complete')[0].replace(boundary['HEADER'],header));convert(source,out)
        wanted=directory/f'{phase}.expected.ass'
        wanted.write_text(header+boundary['event']('abc',500,1.5,3.5))
        for at in (1.49,1.5,2.5,3.49,3.5):
            check(f'{phase} upright held geometry and boundaries {at}',ImageChops.difference(
                render(out,at,(1920,1080),'gray'),render(wanted,at,(1920,1080),'gray')).getbbox() is None)
(ROOT/'validation/frame-pose-render-checks.json').write_text(json.dumps(dict(version=s.__version__,
    checks_passed=len(checks),checks=checks,engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'native source pose render checks passed')
