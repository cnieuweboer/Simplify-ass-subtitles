import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare mask decisions, font calls/cache lifetime and input ownership with v123."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import ast
import contextlib
import importlib.util
import json
import math
import sys
import tempfile
import trace
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.recordingPen import DecomposingRecordingPen,RecordingPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.ttLib import TTFont
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current, historical_fade_timing=True)

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('masked_reference',
    ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
# Keep historical pass behavior while correcting its known hexadecimal suffix bug.
from outline_color_test_helpers import install_hex_parenthesis_reference_parser
install_hex_parenthesis_reference_parser(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing, Outline, Shadow
Style: Default,Mask Geometry Test,40,0,5,100,100,0,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
SHADOW=r'\fnTexture\1a&HFF&\3a&HFF&\4a&H00&\shad1\bord0'

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {key:snapshot(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return tuple(snapshot(item) for item in value)
    if isinstance(value,set):return frozenset(snapshot(item) for item in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def make_font(path):
    builder=FontBuilder(1000,isTTF=True)
    builder.setupGlyphOrder(['.notdef','space','A','B','C','i'])
    builder.setupCharacterMap({32:'space',65:'A',66:'B',67:'C',105:'i'})
    glyphs={}
    for glyph in ('.notdef','space','A','B','C','i'):
        pen=TTGlyphPen(None)
        if glyph!='space':
            pen.moveTo((0,0));pen.lineTo((400,0));pen.lineTo((400,700))
            if glyph=='C':pen.qCurveTo((200,950),(0,700))
            else:pen.lineTo((0,700))
            pen.closePath()
            if glyph in ('B','i'):
                pen.moveTo((100,200));pen.lineTo((100,500));pen.lineTo((300,500))
                pen.lineTo((300,200));pen.closePath()
        glyphs[glyph]=pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({g:(600,0) for g in glyphs})
    builder.setupHorizontalHeader(ascent=800,descent=-200)
    builder.setupNameTable(dict(familyName='Mask Geometry Test',styleName='Regular',
        uniqueFontIdentifier='MaskGeometryTest-Regular',fullName='Mask Geometry Test',
        psName='MaskGeometryTest-Regular'))
    builder.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
    builder.setupPost();builder.setupMaxp();builder.save(path)

def authored_mask(font_path,glyph='A',x=160,y=100,scale=1,shift=0,warp=0,
                  clip_scale=1,explicit_close=False,sx=100,sy=100):
    """Generate an authored screen outline directly from an independently opened font."""
    with TTFont(font_path) as font:
        glyphs=font.getGlyphSet();pen=DecomposingRecordingPen(glyphs)
        glyphs[font.getBestCmap()[ord(glyph)]].draw(pen)
        cubic=RecordingPen();pen.replay(Qu2CuPen(cubic,max_err=.01,all_cubic=True))
        advance=measurement_fonts(font['hmtx'])[font.getBestCmap()[ord(glyph)]][0]
        units=font['head'].unitsPerEm
        fs=40/units
        dx=x-.5*advance*fs*sx/100*scale+shift
        asc,desc=font['OS/2'].usWinAscent,font['OS/2'].usWinDescent
        dy=y+(asc-.5*(asc+desc))*fs*sy/100*scale
        parts=[];first=None;index=0
        for op,coords in cubic.value:
            if op=='closePath':
                if explicit_close:parts.append('l '+first)
                continue
            command={'moveTo':'m','lineTo':'l','curveTo':'b'}[op]
            values=[]
            for px,py in coords:
                values.extend(((dx+px*fs*sx/100*scale+(warp if index==1 else 0))*clip_scale,
                    (dy-py*fs*sy/100*scale)*clip_scale));index+=1
            numbers=' '.join(format(v,'.8f').rstrip('0').rstrip('.') for v in values)
            if op=='moveTo':first=numbers
            parts.append(command+' '+numbers)
        return ' '.join(parts)

class FontProxy:
    def __init__(self,font,calls,mode):self.font,self.calls,self.mode=font,calls,mode
    def __getitem__(self,key):return self.font[key]
    def getBestCmap(self):return self.font.getBestCmap()
    def getGlyphSet(self):
        glyphs=self.font.getGlyphSet()
        if self.mode=='draw_failure':
            class BrokenGlyph:
                def draw(self,pen):raise RuntimeError('unsupported outline')
            return {name:BrokenGlyph() for name in glyphs}
        return glyphs
    def close(self):self.calls.append(('close',));self.font.close()

class RecordingMetric:
    def __init__(self,engine,mode):
        self.engine,self.mode,self.calls=engine,mode,[]
        self.available=mode!='unavailable'
    def matching_face(self,name,bold,italic):
        self.calls.append(('face',name,bold,italic))
        if self.mode=='missing':return None
        face=self.engine.matching_face(name,bold,italic)
        if face is not None and self.mode=='absent_cmap':
            return SimpleNamespace(key=face.key,cmap={})
        return face
    def open_face(self,face):
        self.calls.append(('open',face.key))
        if self.mode=='open_failure':raise RuntimeError('corrupt font')
        return FontProxy(self.engine.open_face(face),self.calls,self.mode)

def event(text='A',x=160,y=100,start=1,end=5,layer=0,tags='',clip=None,**options):
    return dict(text=text,x=x,y=y,start=start,end=end,layer=layer,tags=tags,clip=clip,**options)

def inputs(module,descriptors,animation):
    lines=[]
    for d in descriptors:
        position='' if d.get('unpositioned') else r'\pos('+str(d['x'])+','+str(d['y'])+')'
        tags=r'\an5'+position+d['tags']
        if d['clip'] is not None:tags+=r'\clip('+d['clip']+')'
        if d.get('iclip') is not None:tags+=r'\iclip('+d['iclip']+')'
        kind=d.get('kind','Dialogue')
        lines.append(f"{kind}: {d['layer']},{module.format_time(d['start'])},"
            f"{module.format_time(d['end'])},Default,{d.get('name','')},0,0,0,,{{{tags}}}{d['text']}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values())
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    animated={e.source_index for e in events if e.kind=='Dialogue'} if animation else set()
    return events,visible,animated

tracer=trace.Trace(count=True,trace=False);checks=[]
with tempfile.TemporaryDirectory() as directory:
    font_path=Path(directory)/'MaskGeometryTest.ttf';make_font(font_path)
    mask=authored_mask(font_path)
    complex_mask=authored_mask(font_path,'B')
    def texture(outline,**options):
        descriptor=dict(text='X',tags=r'\fnTexture',layer=2,clip=outline)
        descriptor.update(options)
        return event(**descriptor)
    rectangle='m 140 80 l 175 80 175 115 140 115'
    multi='m 140 80 l 155 80 155 115 140 115 m 160 80 l 175 80 175 115 160 115'
    cases=[
        ('empty',[]),('plain_text',[event()]),
        ('same_text_copy',[event('ABCD'),event('ABCD',clip=rectangle,layer=2)]),
        ('same_text_other_name',[event('ABCD'),event('ABCD',clip=rectangle,layer=2,name='other')]),
        ('same_text_wrong_layout',[event('ABCD'),event('ABCD',clip=rectangle,layer=2,tags=r'\fs50')]),
        ('same_text_wrong_placement',[event('ABCD'),event('ABCD',clip=rectangle,layer=2,tags=r'\an7')]),
        ('exact_glyph',[event(),texture(mask)]),
        ('transparent_glyph',[event(tags=r'\1a&H80&'),texture(mask)]),
        ('explicit_close',[event(),texture(authored_mask(font_path,explicit_close=True))]),
        ('curved_glyph',[event('C'),texture(authored_mask(font_path,'C'))]),
        ('scaled_clip',[event(),texture('2,'+authored_mask(font_path,clip_scale=2))]),
        ('source_axis_scale',[event(tags=r'\fscx120\fscy90'),texture(authored_mask(font_path,sx=120,sy=90))]),
        ('hole_contours',[event('B'),texture(complex_mask)]),
        ('distorted_contour',[event(),texture(authored_mask(font_path,warp=.3))]),
        ('too_small_factor',[event(),texture(authored_mask(font_path,scale=.4))]),
        ('too_large_factor',[event(),texture(authored_mask(font_path,scale=1.6))]),
        ('anchor_too_far',[event(),texture(authored_mask(font_path,shift=6))]),
        ('loose_single',[event(),texture(authored_mask(font_path,shift=3))]),
        ('loose_two',[event(x=100),event(x=140),texture(authored_mask(font_path,x=100,shift=3)+' '+authored_mask(font_path,x=140,shift=3))]),
        ('loose_three',[event(x=100),event(x=140),event(x=180),texture(' '.join(authored_mask(font_path,x=x,shift=3) for x in (100,140,180)))]),
        ('partial_contour',[event(),texture(mask+' m 180 90 l 185 90 185 100 180 100')]),
        ('cached_same_glyph',[event(),event(x=200),texture(mask),texture(authored_mask(font_path,x=200))]),
        ('cached_two_glyphs',[event(),event('B',x=200),texture(mask),texture(authored_mask(font_path,'B',x=200))]),
        ('layer_priority',[event(layer=1),event(layer=3,tags=r'\1a&H80&'),texture(mask)]),
        ('ineligible_lifetime',[event(end=2),texture(mask)]),
        ('rotated_source',[event(tags=r'\frz20'),texture(mask)]),
        ('invalid_alignment',[event(tags=r'\an0'),texture(mask)]),
        ('empty_outline',[event(' '),texture(mask)]),
        ('unpositioned_mask',[event(),texture(mask,unpositioned=True)]),
        ('inline_mask',[event(),texture(mask,text=r'X{\fs50}X')]),
        ('inverse_mask',[event(),texture(mask,iclip=rectangle)]),
        ('rectangular_clip',[event(),texture('140,80,175,115')]),
        ('empty_mask',[event(),texture('m')]),
        ('odd_points',[event(),texture('m 140 80 l 175 80 175')]),
        ('wrong_move',[event(),texture('m 140 80 150 90 l 175 115')]),
        ('unsupported_command',[event(),texture('m 140 80 s 175 80 175 115')]),
        ('invalid_scale',[event(),texture('17,'+mask)]),
        ('zero_scale',[event(),texture('0,'+mask)]),
        ('uppercase_commands',[event(),texture(mask.upper())]),
        ('shadow_texture',[event('ABCD'),event('X',tags=SHADOW,clip=multi),event('Y',tags=SHADOW,clip=multi)]),
        ('shadow_single_string',[event('ABCD'),event('X',tags=SHADOW,clip=multi)]),
        ('shadow_single_contour',[event('ABCD'),event('X',tags=SHADOW,clip=rectangle),event('Y',tags=SHADOW,clip=rectangle)]),
        ('shadow_no_caption',[event('X',tags=SHADOW,clip=multi),event('Y',tags=SHADOW,clip=multi)]),
        ('shadow_shifted_caption',[event('ABCD',x=220),event('X',tags=SHADOW,clip=multi),event('Y',tags=SHADOW,clip=multi)]),
        ('shadow_inline_tracking',[event(r'AB{\fsp2}CD'),event('X',tags=SHADOW,clip=multi),event('Y',tags=SHADOW,clip=multi)]),
        # A rotated companion is eligible for the texture index but cannot
        # short-circuit the exact glyph proof as an identical-layout text copy.
        ('texture_companion',[event(),texture(mask),event('X',tags=r'\fnTexture\frz20',layer=2)]),
        ('companion_other_phase',[event(),texture(mask),event('X',tags=r'\fnTexture',layer=2,start=2,end=3)]),
        ('companion_other_paint',[event(),texture(mask),event('X',tags=r'\fnTexture\b1',layer=2)]),
        ('touching_shadow_phases',[event('ABCD',end=2.1)]+[
            event(c,start=start,end=end,tags=SHADOW,clip=multi) for start,end in ((1,2),(2,3),(4,5)) for c in ('X','Y')]),
    ]
    engines={module:(module.FontMetrics([Path(directory)]) if module is current else module.FontMetrics([Path(directory)])) for module in (previous,current)}
    for name,descriptors in cases:
        for animation in (False,True):
            for mode in ('none','real','unavailable','missing','absent_cmap','open_failure','draw_failure'):
                compared=[]
                for module in (previous,current):
                    events,visible,animated=inputs(module,descriptors,animation)
                    before=deepcopy(snapshot((events,visible,animated)))
                    metric=None if mode=='none' else RecordingMetric(engines[module],mode)
                    result=(tracer.runfunc(module.remove_masked_glyph_effects,events,visible,metric,animated)
                            if module is current else module.remove_masked_glyph_effects(events,visible,metric,animated))
                    assert before==snapshot((events,visible,animated)),(name,mode,'input mutation')
                    compared.append(snapshot((result,getattr(metric,'calls',[]))))
                assert compared[0]==compared[1],(name,animation,mode)
                calls=getattr(metric,'calls',[])
                checks.append(dict(case=name,animated=animation,mode=mode,removed=result[1],
                    opened=sum(c[0]=='open' for c in calls),closed=sum(c[0]=='close' for c in calls)))
    assert any(c['case']=='exact_glyph' and c['mode']=='real' and c['removed']==1 for c in checks)
    assert any(c['case']=='transparent_glyph' and c['mode']=='real' and c['removed']==1 for c in checks)
    assert any(c['case']=='texture_companion' and c['mode']=='real' and c['animated'] and c['removed']==2 for c in checks)
    assert any(c['case']=='touching_shadow_phases' and c['mode']=='none' and c['removed']==4 for c in checks)
    assert all(c['removed']==0 for c in checks if c['case']=='distorted_contour')
    assert all(c['opened']==1 and c['closed']==1 for c in checks if c['case']=='cached_same_glyph' and c['mode']=='real')
    assert all(c['opened']==1 and c['closed']==0 for c in checks if c['case']=='cached_same_glyph' and c['mode']=='open_failure')
    assert all(c['opened']==1 and c['closed']==1 and c['removed']==0 for c in checks if c['case']=='cached_same_glyph' and c['mode']=='draw_failure')

# Compare real target-pass inputs and edits during two complete focused conversions.
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.remove_masked_glyph_effects
        def wrapped(events,visible,metric=None,animated_sources=None):
            before=snapshot((events,visible,animated_sources))
            result=(tracer.runfunc(original,events,visible,metric,animated_sources)
                    if module is current else original(events,visible,metric,animated_sources))
            captured.append(snapshot((before,result,events,visible,animated_sources)))
            return result
        module.remove_masked_glyph_effects=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):
                    stats=module.simplify_ass(ROOT/'test-data'/fixture,output,
                        module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
                compared.append((snapshot(captured),output.read_bytes(),stats,font_test_report(metric).rows_joined))
        finally:module.remove_masked_glyph_effects=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))

audit=json.loads((ROOT/'validation/masked-extraction-blocks.json').read_text())
helpers={entry['helper'] for entry in audit}
executed={line for (filename,line),count in tracer.results().counts.items()
          if Path(filename).resolve()==Path(current.__file__).resolve() and count}
coverage={}
for node in ast.parse(Path(current.__file__).read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in helpers:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt)
            and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and
            isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),
            statement_lines=len(statements),executed_statement_lines=len(statements&executed),
            unexecuted_lines=sorted(statements-executed))
assert all(item['exercised'] for item in coverage.values()),coverage
report=dict(reference='v123',comparisons=len(checks),font_calls_and_closure_identical=True,
    focused_conversions=focused,helper_coverage=coverage,checks=checks)
(ROOT/'validation/masked-glyph-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'{len(checks)} masked-glyph comparisons; font calls and closure identical; 2 focused conversions; all 17 helpers exercised')
