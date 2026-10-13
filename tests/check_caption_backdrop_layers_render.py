"""Final panel layering, protected decorations and the two real Sword signs."""
import test_paths
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import ast,contextlib,hashlib,importlib.util,io,json,subprocess,sys
import simplify_ass as s
from PIL import Image,ImageChops,ImageDraw
from executable_ast_audit import executable_ast

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'validation/caption-backdrop-layers';DEST.mkdir(exist_ok=True)
metrics=s.FontMetrics([ROOT/'fonts'])
assert metrics.matching_face('Volkhov',0,False) is not None, 'Missing Volkhov regular'
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)

HEADER=r'''[Script Info]
PlayResX: 640
PlayResY: 360
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,7,0,0
Style: Other,Volkhov,40,7,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def fixture(*, upper_tags='', upper_end=4, upper_style='Default', upper_actor='owner',
            upper_layer=1,
            upper_path='m 0 0 l 300 0 300 150 0 150', upper_pos=(100,100), low_width=300,
            lower_tags='', shadow=False):
    def row(layer,tags,text,style='Default',actor='owner',end=4):
        return f'Dialogue: {layer},0:00:01.00,{s.format_time(end)},{style},{actor},0,0,0,,{{{tags}}}{text}\n'
    rectangle=rf'\an7\pos(100,100)\p1\bord0\shad0{lower_tags}'
    upper=rf'\an7\pos({upper_pos[0]},{upper_pos[1]})\p1\bord0\shad0{upper_tags}'
    small=r'\pos(120,180)'+(r'\1a&HFE&\4a&H00&\4c&H123456&\xshad-.01' if shadow else '')
    doc=s._resolve_document_state(s.parse_subtitle_document(HEADER+
        row(0,rectangle,f'm 0 0 l {low_width} 0 {low_width} 150 0 150')+
        row(upper_layer,upper,upper_path,upper_style,upper_actor,upper_end)+
        row(2,r'\pos(120,120)','Top')+row(0,small,'Small')))
    low,high,top,small=list(doc.events.values())
    supports=s.CaptionSupportResult([low,high,top,small],[low,high],[],
                                   {low.source_index:[small],high.source_index:[top]},set(),
                                   {'drawing_duplicates_removed':0})
    events,_=s.normalize_shadow_lettering(supports.events)
    return supports,events

supports,events=fixture(shadow=True);before=deepcopy((supports,events))
result=s.settle_caption_backdrop_layers(supports,events,metrics)
small=next(e for e in result.events if s.OVERRIDE_RE.sub('',e.text)=='Small')
check('late shadow foreground sits above upper panel in one call',small.layer=='2')
check('hidden lower rectangle omitted',len(result.kept)==1 and len(result.events)==3)
check('existing drawing counter records hidden duplicate',result.counts['drawing_duplicates_removed']==1)
check('paint text timing and anchor preserved',small.fields()[1:]==events[-1].fields()[1:] and small.state is events[-1].state)
check('borrowed support records and caches unchanged',
      [vars(e) for e in supports.events]==[vars(e) for e in before[0].events] and
      supports.counts==before[0].counts and supports.associated==before[0].associated)
again=s.settle_caption_backdrop_layers(result,result.events,metrics)
check('final layer proof is idempotent',[e.fields() for e in again.events]==[e.fields() for e in result.events] and again.counts==result.counts)
check('missing metrics keeps existing layers',s.settle_caption_backdrop_layers(supports,events,None).events==events)
with patch.object(metrics,'available',False):
    check('unavailable metrics keeps existing layers',s.settle_caption_backdrop_layers(supports,events,metrics).events==events)
with patch.object(metrics,'matching_face',return_value=None):
    check('unresolved exact font authorizes no promotion',s.settle_caption_backdrop_layers(supports,events,metrics).events==events)
base,evs=fixture()
symbol=s.replace_event(evs[-1],text=r'{\pos(120,180)}^')
out=s.settle_caption_backdrop_layers(base,[*evs[:-1],symbol],metrics)
check('punctuation-only custom-font artwork keeps its layer',out.events[-1].layer==symbol.layer)

for name,options in [
    ('translucent upper',dict(upper_tags=r'\1a&H80&')),
    ('clipped upper',dict(upper_tags=r'\clip(110,110,390,240)')),
    ('inverse-clipped upper',dict(upper_tags=r'\iclip(110,110,390,240)')),
    ('rotated upper',dict(upper_tags=r'\frz20')),
    ('moving upper',dict(upper_tags=r'\move(100,100,110,100)')),
    ('partial lifetime',dict(upper_end=2)),
    ('different style',dict(upper_style='Other')),
    ('different actor',dict(upper_actor='other')),
    ('adjacent arrow',dict(upper_path='m 0 0 l 20 10 0 20',upper_pos=(500,100))),
    ('foreground decoration',dict(upper_layer=3)),
    ('fullscreen',dict(upper_path='m 0 0 l 640 0 640 360 0 360',upper_pos=(0,0))),
]:
    base,evs=fixture(**options);out=s.settle_caption_backdrop_layers(base,evs,metrics)
    small=next(e for e in out.events if s.OVERRIDE_RE.sub('',e.text)=='Small')
    check(name+': guarded shape does not raise caption over itself',int(small.layer)<=1)
    check(name+': lower support retained',len(out.kept)==2)

for name,options in [
    ('partially exposed lower',dict(low_width=350)),
    ('lower stroke',dict(lower_tags=r'\bord2')),
    ('lower shadow',dict(lower_tags=r'\xshad3')),
]:
    base,evs=fixture(**options);out=s.settle_caption_backdrop_layers(base,evs,metrics)
    check(name+': visible lower geometry retained',len(out.kept)==2)
    check(name+': different overlaid card does not expose masked text' if name=='partially exposed lower' else name+': same-panel promotion retained',
          out.events[-1].layer==('0' if name=='partially exposed lower' else '2'))

base,evs=fixture(upper_path='m 0 0 l 400 0 400 150 0 150')
out=s.settle_caption_backdrop_layers(base,evs,metrics)
check('different overlaid panel remains a mask even with full glyph containment',out.events[-1].layer=='0')
again=s.settle_caption_backdrop_layers(out,out.events,metrics)
check('masked caption does not acquire a new panel owner on another call',again.events[-1].layer=='0')

spec=importlib.util.spec_from_file_location('caption_layer_v182',ROOT/'tests/references/simplify_ass_v182.py')
reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)
reference_metrics=reference.FontMetrics([ROOT/'fonts'])
for name,at,style,text in [('Sword-S01E03',121.3,'ZahuSigns','(Cat Beastmen Style)'),
                           ('Sword-S01E02-track5',933,'LightSigns','VIT  180MAG616')]:
    source=ROOT/'test-data/corpus'/(name+'.original.ass');source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    paths=[DEST/(name+f'.pass{i}.ass') for i in (1,2,3)]
    current=source
    for path in paths:
        report=s.FontProcessingReport()
        with contextlib.redirect_stdout(io.StringIO()):
            s.simplify_ass(current,path,s.SimplifyConfig(),font_metrics=metrics,font_report=report)
        check(name+': all required fonts available '+path.name,not report.missing_families)
        current=path
    captions=[]
    for path in paths:
        es=s.load_subtitle_events(path)[1]
        matches=[e for e in es if e.style==style and s.OVERRIDE_RE.sub('',e.text)==text]
        check(name+': retained one intended caption '+path.name,len(matches)==1)
        captions.append(matches[0])
    check(name+': stable layer 2 from first conversion',all(e.layer=='2' for e in captions))
    check(name+': caption paint text geometry and timing stable',
          all(e.start==captions[0].start and e.end==captions[0].end and
              e.state==captions[0].state for e in captions))
    check(name+': source preserved',hashlib.sha256(source.read_bytes()).hexdigest()==source_hash)
    def render(path):
        run=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1',
            '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
            '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
        return Image.frombytes('RGB',(1920,1080),run.stdout)
    frames=[render(path) for path in paths]
    check(name+': first second third renders identical',all(ImageChops.difference(frames[0],f).getbbox() is None for f in frames[1:]))
    # Reproduce the verified old third-pass rendering from immutable code,
    # without requiring an ignored generated file in a fresh checkout.
    old_source=source
    for number in (1,2,3):
        oracle=DEST/(name+f'.v182-pass{number}.ass')
        report=reference.FontProcessingReport()
        with contextlib.redirect_stdout(io.StringIO()):
            reference.simplify_ass(old_source,oracle,reference.SimplifyConfig(),
                                  font_metrics=reference_metrics,font_report=report)
        check(name+': oracle fonts complete '+str(number),not report.missing_families)
        old_source=oracle
    check(name+': first rendering matches verified readable v182 third pass',ImageChops.difference(frames[0],render(oracle)).getbbox() is None)
    frames[0].save(DEST/(name+'.fixed.png'))

def definitions(path):
    return {node.name:node for node in executable_ast(ast.parse(path.read_text())).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
old,new=definitions(ROOT/'tests/references/simplify_ass_v182.py'),definitions(ROOT/'simplify_ass.py')
check('only final-layer helper added',new.keys()-old.keys()=={'settle_caption_backdrop_layers'} and not old.keys()-new.keys())
check('only final pipeline wiring changed',{name for name in old if ast.dump(old[name])!=ast.dump(new[name])}=={'simplify_ass'})
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'caption/backdrop layer checks passed; both Sword signs visible and layers stable in one run')
