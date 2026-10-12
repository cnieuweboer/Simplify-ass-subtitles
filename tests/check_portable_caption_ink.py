"""Portable shaped ink, unknown bounds and the real Skill Bank backdrop."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import ast, contextlib, copy, hashlib, importlib.util, json, sys, tempfile
import uharfbuzz  # Required: this regression must never skip the real backend.
from PIL import ImageFont
import simplify_ass as s
from executable_ast_audit import executable_ast

ROOT = Path(__file__).resolve().parents[1]
checks = []
def check(label, condition):
    assert condition, label
    checks.append(label)

spec = importlib.util.spec_from_file_location('portable_ink_reference',ROOT/'test-data/simplify_ass-v172-reference.py')
old = importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
fixture = ROOT/'test-data/Sword-S01E01-skill-bank-source.ass'
source = s.load_subtitle_events(fixture)[1]
before = copy.deepcopy(source)
title = next(e for e in source if not e.state.get('p') and 'Skill Bank' in e.text)
title = s.replace_event(title,text=s.simplify_visual_text(title.text,0,title.duration,title.defaults,title.styles,1)[0])
original = ImageFont.truetype
def basic(*args,**kwargs):
    return original(*args,**{**kwargs,'layout_engine':ImageFont.Layout.BASIC})

# Deterministic shaped offsets and extents; these are font measurements, never
# guessed placements or a relaxed panel-containment test.
with patch.object(ImageFont,'truetype',basic):
    metrics = s.FontMetrics([ROOT/'fonts'])
    face = metrics.matching_face('Nyala',0,False)
    check('unmeasured face stays unknown',metrics.line_ink_metrics(face,['AB']) is None)
    data,index = metrics.face_data(face)
    metrics._loaded[face.key] = basic(__import__('io').BytesIO(data),1024,index=index)
    class Buffer:
        def add_str(self,text):self.text=text
        def guess_segment_properties(self):self.direction='rtl' if self.text=='rtl' else 'ltr'
    def shape(font,buffer,flags):
        check('ink shaping retains kerning flag',flags=={'kern':False})
        buffer.glyph_infos=[SimpleNamespace(codepoint=0 if buffer.text=='missing' else 1),SimpleNamespace(codepoint=2)]
        buffer.glyph_positions=[SimpleNamespace(x_advance=640,y_advance=0,x_offset=32,y_offset=64),
                                SimpleNamespace(x_advance=640,y_advance=1 if buffer.text=='vertical' else 0,x_offset=-64,y_offset=-32)]
    metrics._harfbuzz=SimpleNamespace(Buffer=Buffer,shape=shape)
    glyphs={1:SimpleNamespace(x_bearing=-64,y_bearing=640,width=320,height=-512),
            2:SimpleNamespace(x_bearing=0,y_bearing=512,width=640,height=-640)}
    metrics._shaping_fonts[face.key]=SimpleNamespace(get_glyph_extents=glyphs.get)
    ink=metrics.line_ink_metrics(face,['AB','',' '])
    check('offsets advances y direction and outward rounding',ink.boxes==((-1,-11,20,3),None,None))
    check('ascent uses exact ASS face',0<ink.ascent_ratio<1)
    for text in ('rtl','missing','vertical'):
        check('unsupported ink remains unknown '+text,metrics.line_ink_metrics(face,[text]) is None)
    glyphs[2]=None
    check('missing glyph extents stay unknown',metrics.line_ink_metrics(face,['AB']) is None)
    glyphs.update({gid:SimpleNamespace(x_bearing=0,y_bearing=0,width=0,height=0) for gid in (1,2)})
    check('no ink cannot prove support',metrics.line_ink_metrics(face,['AB']) is None)
    metrics._harfbuzz=None
    check('missing shaping backend stays unknown',metrics.line_ink_metrics(face,['AB']) is None)

real_backend=True
with patch.object(ImageFont,'truetype',basic):
    current=s.FontMetrics([ROOT/'fonts']);prior=old.FontMetrics([ROOT/'fonts'])
    old_box=old.caption_bounds(title,prior);new_box=s.caption_bounds(title,current)
    check('actual portable path has ink',new_box is not None and new_box!=old_box)
    check('v172 reproduces missing backdrop',not old.reconstruct_composite_backdrops(source,[title],prior))
    rebuilt=s.reconstruct_composite_backdrops(source,[title],current)
    check('portable path rebuilds one backdrop',len(rebuilt)==1)
    check('bounds exclude separator',s.drawing_polygon(rebuilt[0])==[(232.0,273.0),(1219.01,273.0),(1219.01,474.0),(232.0,474.0)])
    check('opaque representative tan fill',rebuilt[0].state['1c']=='96AAAF' and rebuilt[0].state['1a']==0)
    check('strict containment still required',len(s.select_caption_supports(rebuilt,[title],current)[0])==1)
    face=current.matching_face('Nyala',0,False)
    for text in ('Skill Bank ','AV','office','A\u0301','é', ' A '):
        for kerning in (False,True):
            advance=current.measure(face,text,kerning)
            ink=current.line_ink_metrics(face,[text],kerning=kerning)
            check('real shaped ink '+repr((text,kerning)),ink is not None and ink.boxes[0][0]<ink.boxes[0][2] and ink.boxes[0][1]<ink.boxes[0][3])
            check('ink preserves advance '+repr((text,kerning)),current.measure(face,text,kerning)==advance)
    with tempfile.TemporaryDirectory() as directory:
        output=Path(directory)/'portable.ass'
        with contextlib.redirect_stdout(None):
            stats=s.simplify_ass(fixture,output,s.SimplifyConfig(),font_metrics=current)
        events=s.load_subtitle_events(output)[1]
        check('full pipeline retains Skill Bank backdrop',any(e.kind=='Dialogue' and e.layer=='0' and e.state.get('p') and e.state.get('1c')=='96AAAF' and e.start_s<=257<e.end_s for e in events))
        check('composite report records recovered support',stats['composite_backdrops_built']==1)
if s.FontMetrics().capabilities.raqm:
    raqm=s.FontMetrics([ROOT/'fonts'])
    check('RAQM still reconstructs backdrop',len(s.reconstruct_composite_backdrops(source,[title],raqm))==1)
    # Compare actual portable extents to raster-backed bounds on TTF/CFF,
    # spacing, ligatures, combining marks, accents and both kerning modes.
    with patch.object(ImageFont,'truetype',basic):
        portable=s.FontMetrics([ROOT/'fonts'])
        for family in ('Nyala','Arial','Gandhi Sans'):
            face=portable.matching_face(family,False,False)
            raster=s.FontMetrics([ROOT/'fonts'])
            data,index=raster.face_data(face)
            raster._loaded[face.key]=original(__import__('io').BytesIO(data),1024,index=index,layout_engine=ImageFont.Layout.RAQM)
            for text in ('Skill Bank ','AV','office','A\u0301','é',' A '):
                for kern in (False,True):
                    portable.measure(face,text,kern)
                    hb_box=portable.line_ink_metrics(face,[text],kerning=kern).boxes[0]
                    raster_box=raster.line_ink_metrics(face,[text],kerning=kern).boxes[0]
                    check('actual shaped/raster bounds '+repr((family,text,kern)),max(abs(x-y) for x,y in zip(hb_box,raster_box))<=2)
check('source events preserved',source==before and all(vars(a)==vars(b) for a,b in zip(source,before)))

# This fix changes exactly one backend method; drawing admission, containment,
# font selection, advances and text reduction are unchanged from v172.
def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a=definitions(ROOT/'test-data/simplify_ass-v172-reference.py');b=definitions(ROOT/'test-data/simplify_ass-v173-reference.py')
check('only font owner changed',a.keys()==b.keys() and {k for k in a if ast.dump(a[k])!=ast.dump(b[k])}=={'FontMetrics'})
am={n.name:n for n in a['FontMetrics'].body if isinstance(n,ast.FunctionDef)}
bm={n.name:n for n in b['FontMetrics'].body if isinstance(n,ast.FunctionDef)}
check('only ink measurement method changed',am.keys()==bm.keys() and {k for k in am if ast.dump(am[k])!=ast.dump(bm[k])}=={'line_ink_metrics'})
report=dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),real_harfbuzz_verified=real_backend,checks=checks)
(ROOT/'validation/portable-caption-ink-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'portable caption ink checks passed; real HarfBuzz:',real_backend)
