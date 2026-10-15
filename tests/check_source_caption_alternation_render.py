"""Native rendering of representative phase paint and the next lyric handoff."""
import test_paths
import check_source_caption_alternation as cases
from pathlib import Path
import contextlib, hashlib, json, subprocess, tempfile
from PIL import Image,ImageChops
import simplify_ass as s
ROOT=cases.ROOT
checks=[]
def check(label,value):
    assert value,label
    checks.append(label)
def frame(path,at,background):
    result=subprocess.run(['ffmpeg','-v','verbose','-f','lavfi','-i',f'color=c={background}:s=640x360:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    if 1<=at<9:
        check('native renderer selects exact Volkhov',any('fontselect:' in line and 'Volkhov' in line
            for line in result.stderr.decode().splitlines()))
    return Image.frombytes('RGB',(640,360),result.stdout)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory);source=directory/'source.ass';output=directory/'output.ass'
    expected=directory/'authored.ass';repeat=directory/'repeat.ass'
    source.write_text(cases.source)
    body='';index=0
    for c in cases.TEXT:
        if c.isspace():body+=c
        else:
            body+=rf'{{\1c&H{40+index*8:02X}C080&\3c&H{40+index*8:02X}8040&}}'+c
            index+=1
    expected.write_text(cases.HEADER+cases.record(body)+cases.record(cases.next_text,x=cases.next_anchor,
        start=5,end=9,tags=r'\1c&H60C080&\3c&H608040&'))
    report=s.FontProcessingReport()
    with contextlib.redirect_stdout(None):
        s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=cases.METRIC,font_report=report)
        s.simplify_ass(output,repeat,s.SimplifyConfig(),font_metrics=cases.METRIC,font_report=report)
    check('native integration exact fonts',not report.missing_families)
    check('native integration repeat byte stable',output.read_bytes()==repeat.read_bytes())
    for bg in ('black','gray','white'):
        for at in (.99,1,1.5,2,3,4.99,5,5.01,7,9):
            actual=frame(output,at,bg);authored=frame(expected,at,bg)
            check(f'{bg} {at} intended gradient, timing and next caption',
                  ImageChops.difference(actual,authored).getbbox() is None)
(ROOT/'validation/source-caption-alternation-render-checks.json').write_text(json.dumps(dict(
    version=s.__version__,engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),
    checks=len(checks),cases=checks),indent=2)+'\n')
print(len(checks),'native source phase and lyric handoff checks passed')
