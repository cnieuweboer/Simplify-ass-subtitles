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
            lower_tags='', shadow=False, fontsize=40):
    def row(layer,tags,text,style='Default',actor='owner',end=4):
        return f'Dialogue: {layer},0:00:01.00,{s.format_time(end)},{style},{actor},0,0,0,,{{{tags}}}{text}\n'
    rectangle=rf'\an7\pos(100,100)\p1\bord0\shad0{lower_tags}'
    upper=rf'\an7\pos({upper_pos[0]},{upper_pos[1]})\p1\bord0\shad0{upper_tags}'
    small=r'\pos(120,180)'+(r'\1a&HFE&\4a&H00&\4c&H123456&\xshad-.01' if shadow else '')
    doc=s._resolve_document_state(s.parse_subtitle_document(HEADER.replace('Volkhov,40,',f'Volkhov,{fontsize},')+
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

# Selection ownership is separate from general caption/support associations.
base,evs=fixture(shadow=True)
proof=s._caption_panel_ownership(base.kept,base.associated,metrics)
base=s.dataclass_replace(base,ownership=proof)
before=deepcopy(base)
out=s.settle_caption_backdrop_layers(base,evs,metrics)
small=next(e for e in out.events if s.OVERRIDE_RE.sub('',e.text)=='Small')
relation=next(r for r in out.ownership if r.caption is small)
check('removed fill retains original panel ownership evidence',relation.panel is base.kept[0] and relation.panel not in out.kept)
check('ownership follows the promoted caption successor',relation.caption.layer=='2')
check('proof lists and input relationships remain borrowed',[vars(r.panel) for r in base.ownership]==[vars(r.panel) for r in before.ownership] and base.ownership==before.ownership)
check('explicit ownership gives stable final layers',
      [e.fields() for e in s.settle_caption_backdrop_layers(out,out.events,metrics).events]==[e.fields() for e in out.events])
base,evs=fixture()
base=s.dataclass_replace(base,ownership=[])
out=s.settle_caption_backdrop_layers(base,evs,metrics)
check('mere reassociation cannot create a background owner',out.events==evs and out.kept==base.kept and out.ownership==[])
base,evs=fixture(upper_path='m 0 0 l 400 0 400 150 0 150')
base=s.dataclass_replace(base,ownership=s._caption_panel_ownership(base.kept,base.associated,metrics))
for repeat in range(3):
    out=s.settle_caption_backdrop_layers(base,evs,metrics)
    check('independent card preserves original ownership '+str(repeat),out.events[-1].layer=='0' and
          next(r for r in out.ownership if r.caption is out.events[-1]).panel is base.ownership[0].panel)
    base,evs=out,out.events
for name,kwargs,expected in [
    ('same footprint different paint',dict(upper_tags=r'\1c&H123456&'), '2'),
    ('subpixel panel offset',dict(upper_pos=(101,100)), '2'),
    ('rounding bound panel offset',dict(upper_pos=(102,100)), '2'),
    ('independent shifted card',dict(upper_pos=(103,100)), '0'),
    ('different polygon enclosing ink',dict(upper_path='m 0 0 l 300 0 320 150 0 150'), '0'),
]:
    base,evs=fixture(**kwargs)
    base=s.dataclass_replace(base,ownership=s._caption_panel_ownership(base.kept,base.associated,metrics))
    out=s.settle_caption_backdrop_layers(base,evs,metrics)
    check(name+': footprint ownership determines visibility',out.events[-1].layer==expected)
base,evs=fixture()
# A simplified rectangle cannot prove ink outside its original source contour.
invalid=s.dataclass_replace(base.kept[0],evidence=s.EventEvidence(((100,100),(140,100),(140,130),(100,130))))
box=s.caption_bounds(base.events[-1],metrics);points=s.coverage_geometry(invalid)[0]
check('original contour bounds shared by support and final proof',not s.caption_panel_contains(invalid,points,base.events[-1],box))
check('original contour excludes enclosing ownership',not s._caption_panel_ownership([invalid],{invalid.source_index:[base.events[-1]]},metrics))
# Retention needs positive overlap, while promotion needs the complete lifetime.
base,evs=fixture(upper_end=2)
proof=s._caption_panel_ownership(base.kept,base.associated,metrics)
check('partial support can own only its occupied interval',any(r.panel is base.kept[1] for r in proof))
out=s.settle_caption_backdrop_layers(s.dataclass_replace(base,ownership=proof),evs,metrics)
check('partial support ownership does not authorize full-lifetime promotion',out.events[-1].layer=='0')

for name,options in [('lower blur',dict(lower_tags=r'\blur6')),('upper blur',dict(upper_tags=r'\blur6')),
                     ('lower edge blur',dict(lower_tags=r'\be1')),('upper edge blur',dict(upper_tags=r'\be1'))]:
    base,evs=fixture(**options)
    out=s.settle_caption_backdrop_layers(base,evs,metrics)
    check(name+': unsupported fill coverage preserves both panels',len(out.kept)==2)
for size in (24,40,48):
    base,evs=fixture(fontsize=size)
    out=s.settle_caption_backdrop_layers(base,evs,metrics)
    check('font size '+str(size)+': measured ownership generalizes',out.events[-1].layer=='2')
base,evs=fixture(upper_path='m 0 0 l 300 0 320 150 0 150')
low=s.replace_event(base.kept[0],text=base.kept[1].text)
base=s.dataclass_replace(base,events=[low,*base.events[1:]],kept=[low,base.kept[1]])
out=s.settle_caption_backdrop_layers(base,base.events,metrics)
check('identical nonrectangular footprint retains caption ownership',out.events[-1].layer=='2')
check('nonrectangular fill not removed by rectangular coverage proof',len(out.kept)==2)

# A same-layer card painted AFTER text is an intentional mask. Reassociation
# used to let that card acquire the text on the next final-layer invocation.
base,evs=fixture(upper_layer=0,upper_path='m 0 0 l 400 0 400 150 0 150')
ordered=[evs[0],evs[-1],evs[1],evs[2]]
base=s.dataclass_replace(base,events=ordered,ownership=s._caption_panel_ownership(base.kept,base.associated,metrics))
original_owner=base.kept[0]
for repeat in range(3):
    out=s.settle_caption_backdrop_layers(base,ordered,metrics)
    small=next(e for e in out.events if s.OVERRIDE_RE.sub('',e.text)=='Small')
    check('later same-layer card keeps text masked '+str(repeat),small.layer=='0')
    check('later same-layer card never adopts the text '+str(repeat),
          next(r for r in out.ownership if r.caption is small).panel is original_owner)
    base,ordered=out,out.events
spec187=importlib.util.spec_from_file_location('caption_owner_v187',ROOT/'tests/references/simplify_ass_v187.py')
reference187=importlib.util.module_from_spec(spec187);sys.modules[spec187.name]=reference187;spec187.loader.exec_module(reference187)
oldbase=reference187.CaptionSupportResult([evs[0],evs[-1],evs[1],evs[2]],
    [evs[0],evs[1]],[],{evs[0].source_index:[evs[-1]],evs[1].source_index:[evs[2]]},set(),{'drawing_duplicates_removed':0})
first=reference187.settle_caption_backdrop_layers(oldbase,oldbase.events,metrics)
second=reference187.settle_caption_backdrop_layers(first,first.events,metrics)
check('v187 reproduction: reassociation exposes independent masked text',
      next(e for e in first.events if s.OVERRIDE_RE.sub('',e.text)=='Small').layer=='0' and
      next(e for e in second.events if s.OVERRIDE_RE.sub('',e.text)=='Small').layer=='1')

spec=importlib.util.spec_from_file_location('caption_layer_v182',ROOT/'tests/references/simplify_ass_v182.py')
reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)
reference_metrics=reference.FontMetrics([ROOT/'fonts'])
for name,at,style,text in [('Sword-S01E03',121.3,'ZahuSigns','(Cat Beastmen Style)'),
                           ('Sword-S01E02-track5',933,'LightSigns','VIT  180MAG616')]:
    source=ROOT/'test-data/corpus'/(name+'.original.ass');source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    paths=[DEST/(name+f'.pass{i}.ass') for i in (1,2,3)]
    current=source
    captured_supports=[]
    rebuild=s._rebuild_caption_supports
    def capture_supports(*args,**kwargs):
        result=rebuild(*args,**kwargs);captured_supports.append(result);return result
    for path in paths:
        report=s.FontProcessingReport()
        with contextlib.redirect_stdout(io.StringIO()),patch.object(s,'_rebuild_caption_supports',capture_supports):
            s.simplify_ass(current,path,s.SimplifyConfig(),font_metrics=metrics,font_report=report)
        check(name+': all required fonts available '+path.name,not report.missing_families)
        current=path
    check(name+': production carries enclosing ownership before final paint',all(r.ownership is not None and r.ownership for r in captured_supports))
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
    # v198 preserves authored contours, so old rendered pixels are no longer
    # the paint specification. Keep the old caption as a placement/layer oracle.
    from event_evidence_test_helpers import contour_independent_contract as contract
    old_caption=next(e for e in s.load_subtitle_events(oracle)[1]
                     if e.style==style and s.OVERRIDE_RE.sub('',e.text)==text)
    check(name+': readable historical caption geometry retained',
          contract(old_caption.fields())==contract(captions[0].fields()))
    # Prove the intended caption actually contributes ink above its panel.
    document=s.parse_subtitle_document(paths[0].read_text());events=s.load_subtitle_events(paths[0])[1]
    masked=DEST/(name+'.without-caption.ass')
    masked.write_text(s.render_subtitle_document(document,[e for e in events
        if not (e.style==style and s.OVERRIDE_RE.sub('',e.text)==text)]))
    check(name+': current caption visibly contributes above backdrop',
          ImageChops.difference(frames[0],render(masked)).getbbox() is not None)
    frames[0].save(DEST/(name+'.fixed.png'))

def definitions(path):
    return {node.name:node for node in executable_ast(ast.parse(path.read_text())).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
# Keep the historical v183 scope audit bounded; live behavior checks above use current code.
old,new=definitions(ROOT/'tests/references/simplify_ass_v182.py'),definitions(ROOT/'tests/references/simplify_ass_v183.py')
check('only final-layer helper added',new.keys()-old.keys()=={'settle_caption_backdrop_layers'} and not old.keys()-new.keys())
check('only final pipeline wiring changed',{name for name in old if ast.dump(old[name])!=ast.dump(new[name])}=={'simplify_ass'})
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'caption/backdrop layer checks passed; both Sword signs visible and layers stable in one run')
