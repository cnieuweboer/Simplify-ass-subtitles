"""Caption outline budget, native footprints and original inline extent handoff."""
import test_paths
from pathlib import Path
from copy import deepcopy
import contextlib, hashlib, io, json, subprocess, tempfile
from PIL import Image, ImageChops
import simplify_ass as s

ROOT = Path(__file__).resolve().parents[1]
metric = s.FontMetrics([ROOT/'fonts'])
assert metric.matching_face('Volkhov', 0, False), 'Exact Volkhov Regular required'
HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
checks = []
def check(label, value):
    assert value, label
    checks.append(label)
def event(body):
    return 'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,'+body+'\n'
def resolve(body):
    return next(iter(s._resolve_document_state(s.parse_subtitle_document(HEADER+event(body))).events.values()))
def render(path, background='gray'):
    result = subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
        f'color=c={background}:s=640x360:r=1','-vf',
        f'settb=1/1000,setpts=PTS+2000,ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
        capture_output=True,check=True)
    return Image.frombytes('RGB',(640,360),result.stdout)

with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    for i,(x,y,alpha) in enumerate([(0,0,0),(.5,1.5,0),(2,2,0),(3.75,3.75,0),
            (6,6,0),(12,12,0),(.75,6,96),(6,.75,160)]):
        source = resolve(r'{\pos(320,100)\1c&HC6DDEA&\3c&H446688&'+
            f'\\xbord{x}\\ybord{y}\\3a&H{alpha:02X}&'+'}Soft caption')
        before = deepcopy(source)
        proof = s._source_caption_paint(source.state,[source.state])
        body = s.render_simplified_caption(source.state,'Soft caption',source_paint=proof)
        output = s.replace_event(source,text=body)
        widths = tuple(output.state.get(k,output.state['bord']) for k in ('xbord','ybord'))
        check(f'{i} per-axis budget',widths==(min(2,x),min(2,y)))
        check(f'{i} source immutable',source==before)
        check(f'{i} color and independent alpha retained',not max(x,y) or
            (output.state['3c']=='446688' and output.state['3a']==alpha))
        expected = resolve(r'{\pos(320,100)\1c&HC6DDEA&\3c&H446688&'+
            f'\\xbord{min(2,x)}\\ybord{min(2,y)}\\3a&H{alpha:02X}&'+'}Soft caption')
        a,b = directory/'actual.ass',directory/'expected.ass'
        a.write_text(HEADER+event(body));b.write_text(HEADER+event(expected.text))
        box = s.caption_bounds(output,metric)
        for background in ('black','gray','white'):
            frame = render(a,background)
            check(f'{i} {background} native capped paint',ImageChops.difference(frame,render(b,background)).getbbox() is None)
            pixels = ImageChops.difference(frame,Image.new('RGB',frame.size,frame.getpixel((0,0)))).getbbox()
            check(f'{i} {background} emitted footprint contained',box[0]<=pixels[0] and box[1]<=pixels[1] and
                box[2]>=pixels[2] and box[3]>=pixels[3])
        check(f'{i} selected paint stable',s.render_simplified_caption(output.state,'Soft caption',
            source_paint=s._source_caption_paint(output.state,[output.state]))==body)

    # Original paint extents must survive removing inline tags for measurement.
    # The final span is deliberately borderless: its state is not the whole line.
    for label,tags in [('wide',r'\xbord30\ybord20'),
            ('offset shadow',r'\xshad-30\yshad20'),('soft edge',r'\blur12\be2')]:
        source = resolve(r'{\pos(320,100)}A{'+tags+r'}B{\bord0\xbord0\ybord0\shad0\xshad0\yshad0\blur0\be0}C')
        before = deepcopy(source)
        context = s._prepare_shared_interval_context([source],{source.source_index:'ABC'},metric)
        box = s._shared_interval_bounds(context,source)
        ordinary = s.caption_bounds(resolve(r'{\pos(320,100)}ABC'),metric)
        check(label+' inline extent survives final narrow span',box[0]<ordinary[0] and box[2]>ordinary[2])
        check(label+' bounds cache source immutable',source==before and s._shared_interval_bounds(context,source)==box)
        a = directory/'inline.ass';a.write_text(HEADER+event(source.text));frame = render(a)
        pixels = ImageChops.difference(frame,Image.new('RGB',frame.size,frame.getpixel((0,0)))).getbbox()
        check(label+' native original footprint contained',box[0]<=pixels[0] and box[1]<=pixels[1] and box[2]>=pixels[2] and box[3]>=pixels[3])

    # A panel can contain the capped caption while failing to contain its source
    # stroke. Do not use selected output widths as proof of source redundancy.
    thick = resolve(r'{\pos(320,100)\bord12}Soft caption')
    capped = s.replace_event(thick,text=s.render_simplified_caption(thick.state,'Soft caption',
        source_paint=s._source_caption_paint(thick.state,[thick.state])))
    small,large = s.caption_bounds(capped,metric),s.caption_bounds(thick,metric)
    panel = [(small[0]-1,small[1]-1),(small[2]+1,small[1]-1),
        (small[2]+1,small[3]+1),(small[0]-1,small[3]+1)]
    check('coverage uses current footprint',s.polygon_covers_box(panel,small) and not s.polygon_covers_box(panel,large))
    source,out = directory/'ordinary.ass',directory/'ordinary.simple.ass'
    source.write_text(HEADER+event(thick.text))
    report = s.FontProcessingReport()
    with contextlib.redirect_stdout(io.StringIO()):
        s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=metric,font_report=report)
    check('ordinary static caption not globally capped',s.load_subtitle_events(out)[1][0].state['bord']==12)
    check('ordinary exact fonts',not report.missing_families)

(ROOT/'validation/outline-policy-checks.json').write_text(json.dumps(dict(version=s.__version__,
    engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'outline policy and native geometry checks passed')
