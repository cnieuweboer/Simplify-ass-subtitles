"""Render a same-layer independent-card handoff against immutable v187."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/caption-ownership-render';DEST.mkdir(exist_ok=True)
HEADER=r'''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Alignment, Outline, Shadow
Style: Default,Volkhov,40,&H00FFFFFF&,7,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
SOURCE=HEADER+r'''Dialogue: 0,0:00:01.00,0:00:04.00,Default,owner,0,0,0,,{\an7\pos(100,100)\p1\bord0\shad0\1c&H303030&}m 0 0 l 300 0 300 150 0 150
Dialogue: 0,0:00:01.00,0:00:04.00,Default,owner,0,0,0,,{\pos(120,180)}Small
Dialogue: 0,0:00:01.00,0:00:04.00,Default,owner,0,0,0,,{\an7\pos(100,100)\p1\bord0\shad0\1c&H303030&}m 0 0 l 400 0 400 150 0 150
Dialogue: 2,0:00:01.00,0:00:04.00,Default,owner,0,0,0,,{\pos(120,120)}Top
'''
metric=s.FontMetrics([ROOT/'fonts'])
assert metric.matching_face('Volkhov',0,False) is not None,'Missing required Volkhov regular; stop'
spec=importlib.util.spec_from_file_location('render_owner_v187',ROOT/'tests/references/simplify_ass_v187.py')
reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)
frames={}
def render(events,label):
 path=DEST/(label+'.ass');path.write_text(HEADER+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events))
 result=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=640x360:r=1',
  '-vf',f'settb=1/1000,setpts=PTS+2000,ass=filename={path}:fontsdir={ROOT/"fonts"}',
  '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 frame=Image.frombytes('RGB',(640,360),result.stdout);frame.save(DEST/(label+'.png'));frames[label]=frame
for engine,label in ((reference,'v187'),(s,'v188')):
 es=list(engine._resolve_document_state(engine.parse_subtitle_document(SOURCE)).events.values())
 low,small,high,top=es
 support=engine.CaptionSupportResult(es,[low,high],[],{low.source_index:[small],high.source_index:[top]},set(),{'drawing_duplicates_removed':0})
 if engine is s:
  support=s.dataclass_replace(support,ownership=s._caption_panel_ownership(support.kept,support.associated,metric))
 for number in (1,2,3):
  support=engine.settle_caption_backdrop_layers(support,support.events,metric)
  render(support.events,f'{label}-{number}')
assert ImageChops.difference(frames['v187-1'],frames['v188-1']).getbbox() is None
assert all(ImageChops.difference(frames['v188-1'],frames['v188-'+str(n)]).getbbox() is None for n in (2,3))
difference=ImageChops.difference(frames['v187-1'],frames['v187-2']).getbbox()
assert difference is not None,'v187 must visibly reproduce unintended text exposure'
assert ImageChops.difference(frames['v188-1'],frames['v187-2']).getbbox()==difference
(DEST/'summary.json').write_text(json.dumps(dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),
 reference_sha256=hashlib.sha256((ROOT/'tests/references/simplify_ass_v187.py').read_bytes()).hexdigest(),
 first_render_unchanged=True,current_second_third_pixel_identical=True,v187_unintended_exposure_box=difference),indent=2)+'\n')
print('Caption ownership render: first result unchanged; v188 second/third stable; v187 repeated proof visibly exposes text',difference)
