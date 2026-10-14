"""Native span RGBA survives reconstruction, fading-phase joins and compaction."""
import test_paths
from pathlib import Path
import contextlib,hashlib,io,json,runpy,subprocess,tempfile
from PIL import Image,ImageChops
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):h=runpy.run_path(str(ROOT/'tests/check_inline_paint_ownership.py'))
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
checks=[]
def check(label,value):
    assert value,label;checks.append(label)
def render(path,at,background):
    p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={background}:s=640x360:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    return Image.frombytes('RGB',(640,360),p.stdout)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for i,(name,body) in enumerate(h['CASES']):
        source=directory/f'{i}.ass';out=directory/f'{i}.simple.ass';expected=directory/f'{i}.expected.ass'
        source.write_text(h['HEADER']+h['fixture'](body));expected.write_text(h['HEADER']+h['event'](body,1,2.08))
        report=s.FontProcessingReport()
        with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=metric,font_report=report)
        check(name+' exact fonts',not report.missing_families)
        for background in ('black','gray','white'):
            for at in (.99,1.5,2.05,2.08):
                check(f'{name} {background} native authored span paint and timing {at}',
                    ImageChops.difference(render(out,at,background),render(expected,at,background)).getbbox() is None)
    # An invisible spacer keeps its typographic advance without becoming a
    # visible letter or losing useful moving-frame reduction.
    body=r'A{\alpha&HFF&}B{\alpha&H00&}C';source=directory/'spacer.ass';out=directory/'spacer.simple.ass';expected=directory/'spacer.expected.ass'
    source.write_text(h['HEADER']+''.join(h['event'](body,1+i*.04,1+(i+1)*.04).replace('320,100',f'{320+i*.02},100') for i in range(5)))
    expected.write_text(h['HEADER']+h['event'](body,1,1.2))
    with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=metric)
    events=s.load_subtitle_events(out)[1]
    check('invisible spacer moving sequence reduced once',len(events)==1 and events[0].state['pos']==(320.04,100))
    # Use the independently authored selected source position for exact pixels.
    expected.write_text(expected.read_text().replace('320,100','320.04,100'))
    for background in ('gray','white'):
        check('invisible spacing glyph native advance '+background,ImageChops.difference(
            render(out,1.1,background),render(expected,1.1,background)).getbbox() is None)
(ROOT/'validation/inline-paint-render-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,
    engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'native whole-span paint checks passed')
