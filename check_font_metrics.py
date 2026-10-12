"""Exact-font parity, backend fallbacks, cache ownership and bounded extraction."""
from pathlib import Path
from io import BytesIO
from dataclasses import FrozenInstanceError
from unittest.mock import patch
import ast,builtins,contextlib,hashlib,importlib.util,json,sys,tempfile
from PIL import ImageFont,features
from fontTools.ttLib import TTFont,TTCollection
import simplify_ass as current
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('font_metrics_reference',ROOT/'test-data/simplify_ass-v163-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
checks=[]
def check(label,condition):
 assert condition,label
 checks.append(label)
# Reuse synthetic-font builders without executing the other check suite.
ns={'__file__':str(ROOT/'check_font_selection.py'),'__name__':'font_metrics_builders'}
exec(compile((ROOT/'check_font_selection.py').read_text().split('with tempfile.TemporaryDirectory()')[0],str(ROOT/'check_font_selection.py'),'exec'),ns)
# Variable instances serialize a fresh head.modified timestamp. Freeze the
# test clock so old/new byte parity does not depend on crossing a second.
with patch('fontTools.ttLib.tables._h_e_a_d.timestampNow',return_value=3800000000), tempfile.TemporaryDirectory() as directory:
 folder=Path(directory)
 ns['master'](folder/'one.ttf','Priority Font',400)
 later=folder/'later';later.mkdir();ns['master'](later/'two.ttf','Priority Font',700)
 ns['variable'](folder/'masters','Metrics Variant')
 ns['master'](folder/'regular.ttf','Metrics Collection')
 ns['master'](folder/'bold.ttf','Metrics Collection',700,subfamily='Bold')
 collection=TTCollection();collection.fonts=[TTFont(folder/'regular.ttf'),TTFont(folder/'bold.ttf')]
 collection.save(folder/'collection.ttc');collection.close()
 (folder/'regular.ttf').unlink();(folder/'bold.ttf').unlink()
 (folder/'invalid.ttf').write_text('invalid font')
 initial={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
 old=previous.FontSpacing([folder,later,ROOT/'fonts']);fonts=current.FontMetrics([folder,later,ROOT/'fonts'])
 spacing=current.FontOutlineMatcher(fonts);second=current.FontOutlineMatcher(fonts)
 report=current.FontProcessingReport();other_report=current.FontProcessingReport()
 check('explicit shared owner',spacing.metrics is fonts and second.metrics is fonts)
 check('reconstruction owners keep independent profile and report state',spacing._profiles is not second._profiles and report.missing_families is not other_report.missing_families)
 check('measurement owner has no reconstruction/report state',not any(hasattr(fonts,k) for k in ('merged','missing','outline_profiles','recover')))
 check('row owner has no forwarded measurement methods',not hasattr(current,'FontSpacing') and not any(hasattr(fonts,k) for k in ('recover','fragment_anchor')))
 check('row owner has no backend caches',not any(hasattr(spacing,k) for k in ('loaded','font_bytes','faces','cmaps','_loaded')))
 faces=[]
 for family in ('Priority Font','Metrics Variant','Metrics Collection','00243','No Such Font'):
  for bold in (0,1,-1,550,700):
   for italic in (False,True):
    face=fonts.matching_face(family,bold,italic);reference=old.matching_face(family,bold,italic)
    check(f'face parity {family,bold,italic}',(None if face is None else vars(face))==(None if reference is None else vars(reference)))
    if face is None:continue
    faces.append((face,reference))
    check(f'bytes/index parity {family,bold,italic}',fonts.face_data(face)==old.face_data(reference))
    check('same instance bytes reused',fonts.face_data(face)[0] is fonts.face_data(face)[0])
    check('line scale parity',fonts.ass_em_scale(face)==old.ass_em_scale(reference))
    check('outline parity',fonts.cubic_outline(face,'Ai')==old.cubic_outline(reference,'Ai'))
    check('outline cache identity',fonts.cubic_outline(face,'Ai') is fonts.cubic_outline(face,'Ai'))
    for char in ('A','i','\u2603'):
     check('fragment inspection parity',fonts.fragmented_glyph(face,char)==old.fragmented_glyph(reference,char))
    for text in ('','A','Ai','A A','AAA'):
     if any(ord(c) not in face.cmap for c in text):continue
     for kern in (False,True):
      for liga in (False,True):
       check('shaped advance parity',fonts.measure(face,text,kern,ligatures=liga)==old.measure(reference,text,kern,ligatures=liga))
 # Early ink call must not load a new backend font.
 fresh=current.FontMetrics([folder]);f=fresh.matching_face('Metrics Variant',0,False)
 check('unmeasured ink stays unknown',fresh.line_ink_metrics(f,['Ai']) is None and not fresh._loaded)
 header=ns['header'].replace('Arial','Metrics Variant')
 for mode in (('raqm','basic') if features.check_feature('raqm') else ('basic',)):
  original=ImageFont.truetype
  def basic(*args,**kwargs):return original(*args,**{**kwargs,'layout_engine':ImageFont.Layout.BASIC})
  with patch.object(ImageFont,'truetype',basic) if mode=='basic' else contextlib.nullcontext():
   backend=current.FontMetrics([folder]);prior=previous.FontSpacing([folder])
   if mode=='basic' and not backend.capabilities.harfbuzz:
    face=backend.matching_face('Metrics Variant',0,False)
    for engine in (backend,prior):
     try:engine.measure(face,'Ai')
     except ValueError as exc:check('missing shaping backend preserves error',str(exc)=='Font measurement needs RAQM or uharfbuzz')
     else:raise AssertionError('unsupported backend unexpectedly measured')
   for tags in ('',r'\b-1',r'\i1',r'\fsp2',r'\frz20',r'\fax.2',r'\frx3',r'\q2',r'\q0',r'\an7',r'\an1',r'\fscx80\fscy130',r'\1a&HFF&\4a&H00&\bord0\shad10'):
    for body in ('Ai',r'Ai\N A',r'Ai\nAi',r'Ai\N\NAi'):
     raw=header+f'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{{\\pos(500,200){tags}}}{body}\n'
     e=next(iter(current._resolve_document_state(current.parse_subtitle_document(raw)).events.values()))
     oe=next(iter(previous._resolve_document_state(previous.parse_subtitle_document(raw)).events.values()))
     for adjacency in (False,True):
      # The portable ink refinement is covered separately; retain the old
      # fallback contract when comparing to the v163 ownership baseline.
      with patch.object(backend,'line_ink_metrics',return_value=None) if mode=='basic' else contextlib.nullcontext():
       check('caption bounds/ink parity',current.caption_bounds(e,backend,adjacency=adjacency)==previous.caption_bounds(oe,prior,adjacency=adjacency))
   face=backend.matching_face('Metrics Variant',0,False)
   if mode!='basic' or backend.capabilities.harfbuzz:backend.measure(face,'Ai')
   ink=backend.line_ink_metrics(face,['Ai','',' ','A'])
   if mode=='basic' and not backend.capabilities.harfbuzz:check('unavailable shaping retains line-box fallback',ink is None and not backend._line_ascent_ratios)
   elif mode=='basic':check('direct HarfBuzz refines ink and preserves blank lines',ink is not None and ink.boxes[1:3]==(None,None))
   elif backend.capabilities.raqm:
    check('blank-line ink slots preserved',ink.boxes[1:3]==(None,None))
    check('immutable ink result',isinstance(ink.boxes,tuple))
    try:ink.ascent_ratio=0
    except FrozenInstanceError:check('frozen ink record',True)
    else:raise AssertionError('mutable ink record')
 # Separate row owners reuse identical backend font/instance caches.
 backend_ids={k:id(v) for k,v in fonts._loaded.items()};instance_ids={k:id(v) for k,v in fonts._instance_bytes.items()}
 face=fonts.matching_face('Metrics Variant',0,False)
 state={**current.DEFAULT_STATE,'fn':'Metrics Variant','fs':40,'an':5}
 for owner in (spacing,second):check('row consumers use shared backend',current.authored_glyph_positions(owner.metrics,state,'Ai',500,1) is not None)
 check('backend cache objects retained',all(id(fonts._loaded[k])==v for k,v in backend_ids.items()))
 check('variable instance cache objects retained',all(id(fonts._instance_bytes[k])==v for k,v in instance_ids.items()))
 check('no written or modified font files',initial=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()})
# Deterministic direct-HarfBuzz contract test, independent of installed backends.
# Exercise flags, face index, scale, cache reuse and rejection paths, rather
# than claiming a real HarfBuzz/RAQM pixel comparison.
from types import SimpleNamespace
class FakeHarfBuzz:
    calls=[]
    @staticmethod
    def Face(data,index):
        FakeHarfBuzz.calls.append(('face',hashlib.sha256(data).hexdigest(),index))
        return SimpleNamespace(upem=1000)
    @staticmethod
    def Font(face):return SimpleNamespace(scale=None,get_glyph_extents=lambda gid:SimpleNamespace(x_bearing=-64,y_bearing=6400,width=3200,height=-6400))
    @staticmethod
    def ot_font_set_funcs(font):pass
    class Buffer:
        def add_str(self,text):self.text=text
        def guess_segment_properties(self):self.direction='rtl' if self.text=='rtl' else 'ltr'
    @staticmethod
    def shape(font,buffer,flags):
        FakeHarfBuzz.calls.append(('shape',font.scale,buffer.text,dict(flags)))
        buffer.glyph_infos=[SimpleNamespace(codepoint=0 if buffer.text=='missing' else 1)]
        buffer.glyph_positions=[SimpleNamespace(x_advance=6400+64*len(buffer.text),y_advance=1 if buffer.text=='vertical' else 0,x_offset=0,y_offset=0)]
with patch.dict(sys.modules,{'uharfbuzz':FakeHarfBuzz}):
    hb_current=current.FontMetrics([ROOT/'fonts']);hb_prior=previous.FontSpacing([ROOT/'fonts'])
original=ImageFont.truetype
def basic_font(*args,**kwargs):return original(*args,**{**kwargs,'layout_engine':ImageFont.Layout.BASIC})
with patch.object(ImageFont,'truetype',basic_font):
    calls=[]
    for engine in (hb_prior,hb_current):
        FakeHarfBuzz.calls=[]
        face=engine.matching_face('Arial',0,False)
        results=[]
        for text in ('A','Ai','A A','rtl','missing','vertical'):
            for kern in (False,True):
                for liga in (False,True):
                    try:out=engine.measure(face,text,kern,ligatures=liga)
                    except ValueError as exc:out=('error',str(exc))
                    results.append(out)
        calls.append((results,FakeHarfBuzz.calls))
    check('direct HarfBuzz results and backend calls preserved',calls[0]==calls[1])
    check('direct HarfBuzz face/font reused',sum(c[0]=='face' for c in calls[1][1])==1)
    check('direct HarfBuzz refines baseline-relative ink',hb_current.line_ink_metrics(face,['A']).boxes==((-1,-100,101,0),))
    check('direct HarfBuzz flags and scale explicit',all(c[1]==(65536,65536) for c in calls[1][1] if c[0]=='shape'))

# Dependencies and capability status remain defined even on the early return.
real_import=builtins.__import__
for blocked in ('PIL','fontTools.ttLib'):
 def limited(name,*args,**kwargs):
  if name==blocked:raise ImportError('test missing dependency')
  return real_import(name,*args,**kwargs)
 with patch('builtins.__import__',limited):
  disabled=current.FontMetrics();owner=disabled
  check('unavailable dependencies have explicit capabilities',disabled.capabilities==current.FontCapabilities() and not disabled.available and not owner.available)
  check('unavailable early ink result',disabled.line_ink_metrics(current.FontFace('unused',0,frozenset()),['A']) is None)
for raqm in (False,True):
 def no_hb(name,*args,**kwargs):
  if name=='uharfbuzz':raise ImportError('test missing portable backend')
  return real_import(name,*args,**kwargs)
 with patch('builtins.__import__',no_hb),patch.object(features,'check_feature',return_value=raqm):
  check('capabilities distinguish optional backends',current.FontMetrics().capabilities==current.FontCapabilities(True,raqm,False))
from executable_ast_audit import executable_ast
# Structural audit: moved numerical algorithms differ only in ownership paths.
def parse(path):return executable_ast(ast.parse(path.read_text()))
def members(tree):return {n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a=members(parse(ROOT/'test-data/simplify_ass-v163-reference.py'));b=members(parse(ROOT/'test-data/simplify_ass-v173-reference.py'))
old_methods={n.name:n for n in a['FontSpacing'].body if isinstance(n,ast.FunctionDef)}
new_methods={n.name:n for n in b['FontMetrics'].body if isinstance(n,ast.FunctionDef)}
matcher_methods={n.name:n for n in b['FontOutlineMatcher'].body if isinstance(n,ast.FunctionDef)}
from font_geometry_audit import normalized_row_algorithm
from font_geometry_test_helpers import ROW_NAMES
row_methods={old:normalized_row_algorithm(b[new]) for old,new in ROW_NAMES.items()}
class Normalize(ast.NodeTransformer):
 def visit_Name(self,n):
  if n.id=='FontMetrics':n.id='FontSpacing'
  return n
 def visit_Attribute(self,n):
  n=self.generic_visit(n)
  if n.attr=='metrics' and isinstance(n.value,ast.Name) and n.value.id=='self':return n.value
  private={'_imagefont':'ImageFont','_profiles':'outline_profiles'}
  if n.attr in private:n.attr=private[n.attr]
  elif n.attr.startswith('_') and n.attr[1:] in {'faces','cmaps','loaded','font_bytes','variable_axes','variable_slants','instance_bytes','glyph_fragments','cubic_outlines','ass_em_scales','harfbuzz','shaping_fonts'}:n.attr=n.attr[1:]
  return n
for name,node in old_methods.items():
 if name=='__init__':continue
 import copy
 target=new_methods.get(name,row_methods.get(name,matcher_methods.get(name)))
 if name in ROW_NAMES:
  node=copy.deepcopy(node)
  if isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant):node.body[0].value.value=__import__('inspect').cleandoc(node.body[0].value.value)
 check('unchanged algorithm '+name,ast.dump(node,include_attributes=False)==ast.dump(Normalize().visit(copy.deepcopy(target)),include_attributes=False))
allowed={'MaskedGlyphContext','FontSpacing','remove_fragmented_font_decorations','_prepare_masked_glyphs','remove_masked_glyph_effects','match_staggered_full_line_copies','_shared_interval_bounds','infer_vector_text_cues','_measure_vector_text_outline','_consolidate_text_events','main','caption_bounds','_match_scrolling_block','_limit_scrolling_text','_rebuild_caption_supports','_reconstruct_caption_backdrops','_summarize_caption_supports','simplify_ass'}
changed=[name for name,node in a.items() if name not in b or ast.dump(node,include_attributes=False)!=ast.dump(b[name],include_attributes=False)]
check('row service removed', 'FontSpacing' not in b)
new_definitions=sorted(set(b)-set(a))
check('measurement and matcher abstractions',set(new_definitions)=={'FontCapabilities','FontLineInkMetrics','FontMetrics','FontOutlineMatcher','FontProcessingReport','TextPhaseRowsResult','SharedIntervalRowsResult',*ROW_NAMES.values(), '_representative_static_strip_outline', '_static_outline_ink_bounds', 'OutlineStripEvidence', '_collect_outline_strip_evidence', '_average_outline_strip_color', '_profile_outline_strip_transition', '_profile_outline_strip_sweep'})
# No backend/cache access leaks outside its owner.
private={'_loaded','_imagefont','_harfbuzz','_font_bytes','_faces','_cmaps','_line_ascent_ratios','_instance_bytes','_shaping_fonts','_variable_axes','_variable_slants','_ass_em_scales','_glyph_fragments','_cubic_outlines'}
for name,node in b.items():
 if name=='FontMetrics':continue
 check('no font backend cache leak '+name,not any(isinstance(n,ast.Attribute) and n.attr in private for n in ast.walk(node)))
audit=dict(version=current.__version__,changed_definitions=changed,new_definitions=new_definitions,numerical_algorithms_unchanged=True,backend_caches_only_in_font_owner=True)
(ROOT/'validation/font-metrics-structure-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),checks=checks)
(ROOT/'validation/font-metrics-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'font measurement ownership/parity checks passed')
