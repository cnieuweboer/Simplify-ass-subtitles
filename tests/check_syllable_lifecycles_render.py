"""Native exact-font replacement phases and shorthand alpha continuation."""
import test_paths
from pathlib import Path
import contextlib,hashlib,io,json,re,subprocess,tempfile
from PIL import Image,ImageChops,ImageDraw
import simplify_ass as s
import syllable_lifecycle_cases as h
ROOT=h.ROOT;owner=h.metric();checks=[]
DEST=ROOT/'validation/syllable-lifecycle-renders';DEST.mkdir(exist_ok=True)
def check(label,value):
    assert value,label;checks.append(label)
def render(path,at,background='gray'):
    r=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i',f'color=c={background}:s=1920x1080:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={h.FONT_DIR}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    log=r.stderr.decode()
    if 'fontselect:' in log:
        assert re.search(r'fontselect: \(Century Gothic, 400, 0\) ->.*CenturyGothic',log),log
    return Image.frombytes('RGB',(1920,1080),r.stdout)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for edges in (False,True):
        src=directory/f'case-{edges}.ass';out=directory/f'out-{edges}.ass';expected=directory/f'expected-{edges}.ass'
        src.write_text(h.fixture(edges=edges))
        with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(src,out,s.SimplifyConfig(),font_metrics=owner)
        expected.write_text(h.HEADER+h.record(1,1,4.1 if edges else 4,
            r'{\an5\pos(960,120)\bord1\shad0\1c&HD8DFE1&\3c&H001122&}'+h.LITERAL,effect=''))
        for background in ('black','gray','white'):
            for at in (.99,1.05,1.45,2.45,3.95,4.05,4.11):
                check(f'independent static caption {edges} {background} {at}',ImageChops.difference(
                    render(out,at,background),render(expected,at,background)).getbbox() is None)
        canonical=directory/f'canonical-{edges}.ass';canonical.write_text(src.read_text().replace('&ff&','&HFF&'))
        for at in (1.45,1.85,2.05,3.95,4.05):
            for background in ('black','gray','white'):
                check(f'native shorthand transform alpha {edges} {background} {at}',ImageChops.difference(
                    render(src,at,background),render(canonical,at,background)).getbbox() is None)
    current=DEST/'episode.ass';report=s.FontProcessingReport()
    with contextlib.redirect_stdout(io.StringIO()):s.simplify_ass(h.SOURCE,current,s.SimplifyConfig(),font_metrics=owner,font_report=report)
    check('real embedded fonts',not report.missing_families)
    # The same complete output row must remain pixel-identical while the
    # source swaps from letters to syllables and back. Translation is outside
    # this crop; it remains independently timed at the bottom of the frame.
    for name,times in [('first',(1332.4,1332.65,1333.2,1338.9)),('immediate',(1360.4,1360.6,1361.15))]:
        for background in ('black','gray','white'):
            reference=None;rows=[]
            for at in times:
                source=render(h.SOURCE,at,background).crop((300,0,1650,160))
                actual=render(current,at,background).crop((300,0,1650,160))
                if reference is None:reference=actual
                check(f'real complete static hold {name} {background} {at}',ImageChops.difference(reference,actual).getbbox() is None)
                check(f'real visible caption {name} {background} {at}',ImageChops.difference(actual,Image.new('RGB',actual.size,actual.getpixel((0,0)))).getbbox() is not None)
                row=Image.new('RGB',(1350,350),'#dddddd');row.paste(source,(0,20));row.paste(actual,(0,190))
                draw=ImageDraw.Draw(row);draw.text((5,2),f'{at:.2f} source',fill='black');draw.text((5,172),'v205',fill='black');rows.append(row)
            panel=Image.new('RGB',(1350,350*len(rows)))
            for i,row in enumerate(rows):panel.paste(row,(0,350*i))
            panel.save(DEST/f'{name}-{background}.png')
(ROOT/'validation/syllable-lifecycle-render-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,
    engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'native syllable lifecycle checks passed')
