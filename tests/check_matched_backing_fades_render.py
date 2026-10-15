"""Native unit fades keep readable paint, projection, scrolling and cue boundaries."""
import test_paths
from pathlib import Path
import contextlib,hashlib,io,json,runpy,subprocess,tempfile
from PIL import Image,ImageChops
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):h=runpy.run_path(str(ROOT/'tests/check_matched_backing_fades.py'))
metric=s.FontMetrics([ROOT/'fonts']);face=metric.matching_face('Volkhov',0,False);assert face
FONT=Path(face.path).parent
checks=[]
def check(label,value):
    assert value,label;checks.append(label)
def render(path,at,background):
    r=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i',f'color=c={background}:s=640x360:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={FONT}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    if 1<=at<1.38:check('native exact Volkhov selected','fontselect: (Volkhov,' in r.stderr.decode() and 'Volkhov' in r.stderr.decode().split('fontselect: (Volkhov,')[-1])
    return Image.frombytes('RGB',(640,360),r.stdout)
def expected(projective,gradient):
    rows=[]
    for i,(start,end,alpha) in enumerate(h['PHASES']):
        x,y=220+20*i,110+15*i
        layout=f'\\an5\\pos({x},{y})'
        if projective:layout+=f'\\frz8\\frx1\\fry-4\\fax-.2\\org({x-7},{y})'
        body='{'+layout+f'\\alpha&H{alpha:02X}&'+r'\bord2\1c&HCD8050&\3c&HEEEEEE&}AB '
        if gradient:body+=r'{\1c&HBC7040&\3c&HDDEEFF&}'
        rows.append(h['row'](body+'CD',start,end,0))
    return h['HEADER']+''.join(rows)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for projective,gradient in [(False,False),(False,True),(True,True)]:
        source=directory/'source.ass';output=directory/'simple.ass';reference=directory/'expected.ass'
        source.write_text(h['fixture'](projective=projective,gradient=gradient));reference.write_text(expected(projective,gradient))
        report=s.FontProcessingReport()
        with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metric,font_report=report)
        check('exact pipeline fonts',not report.missing_families)
        for background in ('black','gray','white'):
            for at in (.99,1.,1.05,1.1,1.25,1.3,1.34,1.37,1.38):
                check(f'{projective}/{gradient} {background} native phase paint and geometry {at}',
                    ImageChops.difference(render(output,at,background),render(reference,at,background)).getbbox() is None)
(ROOT/'validation/matched-backing-fade-render-checks.json').write_text(json.dumps(dict(version=s.__version__,
    engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'native matched backing fade checks passed')
