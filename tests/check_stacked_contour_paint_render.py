"""Native rendering uses authored inner contours, including low-contrast gradients."""
import test_paths
from stacked_contour_cases import *
import contextlib,hashlib,io,json,subprocess,tempfile
from PIL import Image,ImageChops
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
checks=[]
def check(label,value):
    assert value,label;checks.append(label)
def frame(path,at,bg):
    p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={bg}:s=640x360:r=1',
      '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
      '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    return Image.frombytes('RGB',(640,360),p.stdout)
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder)
 for number,changes in enumerate([{},dict(inline=False),dict(dark=True),dict(same_layer=True,split=True),dict(width=.75),
      dict(layout=r'\pos(320,100)\frz12'),dict(layout=r'\pos(320,100)\fax.2\fry8\org(310,95)')]):
    source=folder/'source.ass';out=folder/'current.ass';expected=folder/'expected.ass';source.write_text(fixture(**changes));events=parse(source.read_text())
    # Independent authored single-caption reference, with the selected fill
    # and corresponding inner stroke; outer glow is intentionally simplified.
    body=r'{\bord'+str(min(2,changes.get('width',2)))+r'\1c&HDDDDEE&\3c&HBBBBCC&}AB'
    if changes.get('inline',True):body+=r'{\1c&H99DDCC&\3c&H88CCBB&} CD'
    if changes.get('dark'):
      for old,new in [('DDDDEE','000000'),('99DDCC','BBDDCC'),('BBBBCC','889966'),('88CCBB','223311')]:body=body.replace(old,new)
    expected.write_text(HEADER+event(body,0,layout=changes.get('layout',r'\pos(320,100)')))
    report=s.FontProcessingReport()
    with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=metric,font_report=report)
    check(str(number)+' exact fonts',not report.missing_families)
    for background in ('black','gray','white'):
      for at in (.99,1.5,3):
        check(f'{number} {background} authored native contour and timing {at}',
            ImageChops.difference(frame(out,at,background),frame(expected,at,background)).getbbox() is None)
(ROOT/'validation/stacked-contour-render-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'native ordered contour checks passed')
