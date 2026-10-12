"""Verify static gradient outline recovery and narrowly tolerated color syntax."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch
import ast
import contextlib
import importlib.util
import json
import subprocess
import tempfile
from PIL import Image, ImageDraw
import simplify_ass as s
from executable_ast_audit import executable_ast

ROOT = Path(__file__).resolve().parents[1]
checks = []
def check(name, value):
    assert value, name
    checks.append(name)

# The correction accepts one parenthesis only after a complete delimited hex.
for tag in ('c','1c','2c','3c','4c','alpha','1a','2a','3a','4a'):
    for value in ('&H1300FE&)', '&h1300fe&)', '&H1300FE& )'):
        actual = s.evaluate_effective_state('{\\'+tag+value+'}')
        expected = s.evaluate_effective_state('{\\'+tag+'&H1300FE&}')
        check('complete color with parenthesis '+tag+value,actual == expected)
for value in ('&HGG&)', '&H123456&))','&H123456&)junk','&H123456)', '123456)', '&H123456&foo)'):
    state = {'3c':'112233'}
    c = s.OverrideContinuation('Unknown',True)
    check('other malformed colors stay rejected '+value,
          s.apply_override(state,'3c',value,{}, {},c) is c and state == {'3c':'112233'})
check('transform target uses canonical color parser',
      s.sample_transform_state({'3c':'112233'},[(0,100,1,[('3c','&H1300FE&)')])],100,{},s.DEFAULT_STATE).formatting['3c']=='1300FE')

fixture = ROOT/'test-data/Sword-S01E02-ending-outline-source.ass'
document = s._resolve_document_state(s.read_subtitle_document(fixture))
metric = s.FontMetrics([ROOT/'fonts'])
check('fixture exact face available',metric.matching_face('00243',True,False) is not None)
events = list(document.events.values())
bottom = [e for e in events if s.get_pos(e.text)[1] == 994.2]
top = [e for e in events if s.get_pos(e.text)[1] == 82.2]
chosen = next(e for e in bottom if e.layer=='1')
context = s.StackedTextContext({},[],{},set(),set(),MappingProxyType(document.events),metric)
before = deepcopy(events)
def representative_outline(chosen,group,context):
    return s._representative_static_strip_outline(chosen,s._collect_outline_strip_evidence(chosen,group,context))
representative = representative_outline(chosen,bottom,context)
check('complete static red gradient recovered',representative is not None and representative['3c']=='260AC6')
check('new formatting not chosen cache',representative is not chosen.state)
check('borrowed inputs unchanged',events == before and all(e.state==old.state for e,old in zip(events,before)))
check('input order independent',representative_outline(chosen,list(reversed(bottom)),context)==representative)
with patch.object(metric,'line_ink_metrics',return_value=None):
    check('does not require RAQM ink refinement',representative_outline(chosen,bottom,context)==representative)
top_chosen = next(e for e in top if e.layer=='1')
check('original karaoke transforms reject frozen gradients',representative_outline(top_chosen,top,context) is None)

def refuse(name, *, peers=None, foreground=None, sources=None, metrics=metric):
    ctx=replace(context,source_events=context.source_events if sources is None else sources,font_metrics=metrics)
    check(name,representative_outline(foreground or chosen,peers or bottom,ctx) is None)

strips=[e for e in bottom if e.layer=='0']
refuse('missing strip creates a hole',peers=[e for e in bottom if e is not strips[45]])
refuse('overlapping full copies are not a partition',peers=bottom+[strips[45]])
refuse('unknown font measurements',metrics=None)
missing=dict(document.events);missing.pop(strips[0].source_index);refuse('missing original source',sources=missing)
refuse('foreground already has authored outline',foreground=replace(chosen,state={**chosen.state,'bord':3}))
refuse('foreground clip cannot authorize expansion',foreground=replace(chosen,state={**chosen.state,'clip':'(0,0,1920,1080)'}))

def changed_source(name, **state_changes):
    sources=dict(document.events)
    source=strips[45]
    sources[source.source_index]=replace(source,state={**source.state,**state_changes})
    refuse(name,sources=sources)

changed_source('outline opacity must be uniform',**{'3a':21})
changed_source('invisible outline rejected',**{'3a':255})
changed_source('faint glow is not a dominant outline',**{'3a':200})
changed_source('visible clipped fills are not outline strips',**{'1a':0})
changed_source('outline width must be uniform',bord=5)
changed_source('different font layout rejected',fs=73)
changed_source('inverse clips rejected',iclip='(0,0,1920,1080)')
changed_source('nonfinite clip rejected',clip='(0,0,1e999,1080)')
changed_source('invalid color rejected',**{'3c':'garbage'})
sources=dict(document.events);original=strips[45]
sources[original.source_index]=replace(original,text=original.text.replace('\\q2','\\q2\\t(100,200,\\3c&H0000FF&)'))
refuse('original color animation remains rejected',sources=sources)
with patch.object(metric,'cubic_outline',return_value=None):
    refuse('unsupported contextual outline stays unknown')

# A different colored partition proves no red, style, line-count or strip-count rule.
sources=dict(document.events)
for e in strips:sources[e.source_index]=replace(e,state={**e.state,'3c':'FF0000'})
blue=representative_outline(chosen,bottom,replace(context,source_events=sources))
check('blue source paint retained',blue is not None and blue['3c']=='FF0000')
with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(None):
    output=Path(directory)/'result.ass'
    stats=s.simplify_ass(fixture,output,s.SimplifyConfig(),font_metrics=metric)
    result=s._resolve_document_state(s.read_subtitle_document(output))
    captions=[e for e in result.events.values() if e.kind=='Dialogue']
    check('focused conversion reduces to two captions',len(captions)==2)
    check('bottom conversion retains red outline',next(e for e in captions if s.get_pos(e.text)[1]==994.2).state['3c']=='260AC6')
    check('top remains existing neutral fallback',next(e for e in captions if s.get_pos(e.text)[1]==82.2).state['3c']=='000000')

    def render(path, at, size):
        vf=(f"format=rgb24,settb=1/1000,setpts=PTS+{at}/TB,"
            f"subtitles=filename='{path.resolve()}':fontsdir='{ROOT/'fonts'}'")
        result=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
            f'color=c=black:s={size[0]}x{size[1]}:r=1','-vf',vf,
            '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-threads','1','pipe:1'],
            capture_output=True,check=True)
        return Image.frombytes('RGB',size,result.stdout)

    # Validate tolerated syntax against libass independently of our parser.
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 180
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00790F73,&H0000FF00,0,0,0,0,100,100,0,0,1,6,5,5,0,0,0,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
    for tag in ('c','1c','2c','3c','4c','alpha','1a','2a','3a','4a'):
        value='&H80&' if tag.endswith('a') or tag=='alpha' else '&H1300FE&'
        pixels=[]
        for suffix in ('',')'):
            path=Path(directory)/'syntax.ass'
            path.write_text(header+'Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,'
                +r'{\pos(320,90)\kf200'+'\\'+tag+value+suffix+'}Outline\n')
            pixels.append(render(path,.5,(640,180)).tobytes())
        check('libass pixel-identical trailing parenthesis '+tag,pixels[0]==pixels[1])

    original=render(fixture,1338,(1920,1080)).crop((0,920,1920,1080))
    fixed=render(output,1338,(1920,1080)).crop((0,920,1920,1080))
    black=Path(directory)/'black.ass'
    black.write_text(output.read_text().replace(r'\3c&H260AC6&',r'\3c&H000000&'))
    prior=render(black,1338,(1920,1080)).crop((0,920,1920,1080))
    red_pixels=lambda image:sum(r>60 and r>2*g and r>2*b for r,g,b in image.getdata())
    check('source visibly has red outline',red_pixels(original)>100)
    check('simplified outline visibly red',red_pixels(fixed)>100)
    check('previous black outline has no red pixels',red_pixels(prior)==0)
    # Antialiased edge compositing can move a rounded channel by one unit.
    # The original opaque white interiors must remain white at the same pixels.
    cores=[i for i,rgb in enumerate(prior.getdata()) if rgb==(255,255,255)]
    check('opaque white glyph cores remain white',len(cores)>100 and
          all(min(fixed.getdata()[i])>=250 for i in cores))
    montage=Image.new('RGB',(1920,540),(24,24,24))
    draw=ImageDraw.Draw(montage)
    for i,(label,picture) in enumerate((('Original gradient',original),
            ('Previous black outline',prior),('v169 representative red outline',fixed))):
        draw.text((12,i*180+4),label,fill='white')
        montage.paste(picture,(0,i*180+20))
    montage.save(ROOT/'validation/static-outline-comparison.png')

# Separate current audit keeps historical extraction audits meaningful.
def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body
            if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
old=definitions(ROOT/'test-data/simplify_ass-v168-reference.py')
# Historical v169 production audit; v170 changes have their own complete audit.
new=definitions(ROOT/'test-data/simplify_ass-v169-reference.py')
allowed={'StackedTextContext','apply_override','_prepare_stacked_text_copies',
         '_render_stacked_text_caption','_flatten_stacked_text_group',
         'flatten_stacked_text_copies','_consolidate_text_events'}
added={'_representative_static_strip_outline','_static_outline_ink_bounds'}
changed={name for name in old if name in new and ast.dump(old[name])!=ast.dump(new[name])}
check('bounded production changes',changed==allowed and set(new)-set(old)==added and not set(old)-set(new))
report=dict(version=s.__version__,checks_passed=len(checks),checks=checks,
            changed_definitions=sorted(changed),new_definitions=sorted(added))
(ROOT/'validation/static-strip-outline-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'static outline/color-parser checks passed; 10 pixel-identical libass syntax comparisons; bottom red rendered; top animation rejected')
