"""Native stroke reconstruction and interleaved foreground order."""
import test_paths
import check_near_stacked_backings as cases
from pathlib import Path
import subprocess
import tempfile
from PIL import Image,ImageChops
import simplify_ass as s

def frame(path,at,bg):
    result=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={bg}:s=1920x1080:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={cases.ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    return Image.frombytes('RGB',(1920,1080),result.stdout)

checks=0
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for peer,back,front in [(None,'',''),(None,r'\frz20',r'\frz20.01'),('interleaved','','')]:
        text=cases.fixture(back,front,peer=peer);events=cases.parse(text)
        doc=s.parse_subtitle_document(text);out,n=cases.flatten(events);assert n==1
        actual=directory/'actual.ass';expected=directory/'expected.ass'
        actual.write_text(s.render_subtitle_document(doc,out,final_newline=True))
        body=cases.HEADER
        if peer:body+=cases.row(r'\pos(960,500)\bord0\1c&H0000FF&','XXXXXXXXXXXXXXXXXXXX',0)
        body+=cases.row(r'\pos(960.015,500)\bord2\1c&H272627&\3c&HEAE9E7&'+front,layer=1 if peer else 0)
        expected.write_text(body)
        for bg in ('black','gray','white'):
            for at in (.99,1.5,2):
                assert ImageChops.difference(frame(actual,at,bg),frame(expected,at,bg)).getbbox() is None,(peer,front,bg,at)
                checks+=1
print(checks,'native near-backing contour/order/timing checks passed')
