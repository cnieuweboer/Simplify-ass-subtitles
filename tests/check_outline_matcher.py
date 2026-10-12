"""Decoder decision parity, bounded search, profile ownership and vector integration."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import ast,contextlib,importlib.util,json,math,sys,tempfile
import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields
from font_geometry_test_helpers import font_test_report, adapt_reference_font_api
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('outline_matcher_reference',ROOT/'test-data/simplify_ass-v164-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
checks=[];search_cases=0;integration_cases=0

def check(label,condition):
 assert condition,label
 checks.append(label)
def snapshot(value):
 if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
 if isinstance(value,float) and not math.isfinite(value):return repr(value)
 if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
 if isinstance(value,(tuple,list)):return tuple(snapshot(v) for v in value)
 if isinstance(value,(set,frozenset)):return frozenset(snapshot(v) for v in value)
 return value

class RecordedFonts:
 """Small deterministic font interface for exact search-boundary checks."""
 def __init__(self,*,nominal=1.,fragmented=(),unsupported=(),space=5.12,em=100,fail_measure=False):
  self.nominal,self.fragmented,self.unsupported,self.space,self.em=nominal,set(fragmented),set(unsupported),space,em
  self.fail_measure=fail_measure;self.calls=[]
 def ass_em_scale(self,face):self.calls.append(('scale',face.key));return self.nominal
 def fragmented_glyph(self,face,char):self.calls.append(('fragmented',face.key,char));return char in self.fragmented
 def cubic_outline(self,face,char):
  self.calls.append(('outline',face.key,char));return None if char in self.unsupported else ((char,),self.em)
 def measure(self,face,text):
  self.calls.append(('measure',face.key,text))
  if self.fail_measure and text!=' ':raise ValueError('unsupported measurement')
  return self.space if text==' ' else 10.24

def pair(font_options=None):
 old_fonts=RecordedFonts(**(font_options or {}));new_fonts=RecordedFonts(**(font_options or {}))
 old=previous.FontSpacing.__new__(previous.FontSpacing);old.metrics=old_fonts;old.outline_profiles={}
 new=current.FontOutlineMatcher(new_fonts)
 return (old,old_fonts,old.outline_profiles),(new,new_fonts,new._profiles)
def face(chars='A',coordinates=()):return current.FontFace('exact-font',0,frozenset(map(ord,' '+chars)),coordinates)

def search_case(label,*,chars='A',path=(0.,),fs=100.,unit=1.,alphabet=(),font_options=None,fit=None,expected=None,compare_expected=True):
 global search_cases
 results=[]
 for module,(matcher,fonts,cache) in zip((previous,current),pair(font_options)):
  observed=[]
  def fitted(model,actual,**kwargs):
   observed.append((model,actual,kwargs))
   if fit is not None:return fit(model,actual,**kwargs)
   return None if not actual else (1.,actual[0],0.,0.)
  f=face(chars);before=snapshot((path,alphabet,vars(f)))
  with patch.object(module,'fit_cubic_points',fitted):
   result=matcher.decode_cubic_outline(f,path,fs,unit,set(alphabet))
  check(label+' borrowed proof unchanged',before==snapshot((path,alphabet,vars(f))))
  results.append((result,snapshot(fonts.calls),snapshot(cache),snapshot(observed)))
 check(label+' complete decoder parity',results[0]==results[1])
 if compare_expected:check(label+' expected decision',results[1][0]==expected)
 search_cases+=1
 return results[1]

search_case('single complete glyph',expected='A')
search_case('exact unbroken advances',path=(0.,1.,2.),expected='AAA')
for spaces in range(5):
 search_case('measured space count '+str(spaces),path=(0.,1.+spaces*.5),expected=('A'+' '*spaces+'A') if spaces<=3 else None)
search_case('negative interglyph gap',path=(0.,.4))
search_case('inexact interglyph gap',path=(0.,31.),font_options={'space':1024.})
for nominal in (None,0.,1.,2.):
 for fs in (0.,-1.,float('inf'),float('nan'),50.,100.):
  search_case('size preconditions '+repr((nominal,fs)),fs=fs,font_options={'nominal':nominal},compare_expected=False)
for scale in (.7999,.8,1.,1.2,1.2001):
 for error in (0.,3.9999,4.,4.0001):
  for unit in (.5,5.):
   search_case('scale/error bounds '+repr((scale,error,unit)),unit=unit,
    fit=lambda m,p,s=scale,e=error,**kw:(s,0.,0.,e),compare_expected=False)
search_case('unknown scale keeps profiles absent',font_options={'nominal':None})
search_case('no supported contours',font_options={'unsupported':['A']})
search_case('fragmented glyph exclusion',font_options={'fragmented':['A']})
search_case('only nonfragmented candidate',chars='AB',font_options={'fragmented':['A']},expected='B')
search_case('unsupported glyph exclusion',chars='AB',font_options={'unsupported':['A']},expected='B')
search_case('two equally fitting letters reject',chars='AB')
search_case('no positive measured space',font_options={'space':0.})
search_case('empty path retains historical completion',path=(),expected='')
search_case('alphabet admits literal nonASCII',chars='é',alphabet={'é'},expected='é')
search_case('nonASCII absent from alphabet stays unsearched',chars='é')
search_case('alphabet whitespace excluded',chars='A\t',alphabet={'A',' ','\t'},expected='A')
search_case('unsupported paths reject',fit=lambda m,p,**kw:None)
# Scale/baseline snapshots must be carried to subsequent fit calls unchanged.
r=search_case('continued fit snapshots',path=(0.,1.),fit=lambda m,p,**kw:(1.,p[0],17.,0.),expected='AA')
check('continued scale/baseline passed',r[3][1][2]=={'scale':1.,'y_offset':17.})
# Root + 4095 glyph nodes reaches exactly the retained examined-node bound.
r=search_case('examined node bound accepts 4096',path=tuple(map(float,range(4095))),expected='A'*4095)
check('examined-bound fitted nodes',len(r[3])==4095)
r=search_case('examined node bound rejects 4097',path=tuple(map(float,range(4096))))
check('examined overflow remains bounded',len(r[3])==4096)
for candidates in (32,33,34):
 # The candidate order and pending-option limit are observed, not relaxed.
 chars=''.join(map(chr,range(33,33+candidates)))
 r=search_case('pending option bound '+str(candidates),chars=chars)
 check('pending queue has bounded profile fit count',len(r[3])==candidates)

# Reuse cache through changed authored geometry, alphabet order and repeated runs.
for module,(matcher,fonts,cache) in zip((previous,current),pair()):
 f=face('ABé')
 with patch.object(module,'fit_cubic_points',return_value=None):
  matcher.decode_cubic_outline(f,(0.,),100.,1.,{'A','B'})
  initial_keys=set(cache);profile=next(iter(cache.values()));before=len([c for c in fonts.calls if c[0] in ('outline','fragmented')])
  matcher.decode_cubic_outline(f,(99.,),90.,2.,{'B','A',' '})
  check('same normalized alphabet reuses profile object',set(cache)==initial_keys and next(iter(cache.values())) is profile)
  check('source geometry never rebuilds profiles',len([c for c in fonts.calls if c[0] in ('outline','fragmented')])==before)
  matcher.decode_cubic_outline(f,(0.,),100.,1.,{'é'})
  check('new nonASCII alphabet has separate key',len(cache)==2)
  matcher.decode_cubic_outline(face('ABé',(('wght',700.),)),(0.,),100.,1.,{'é'})
  check('requested variable coordinates distinguish profile key',len(cache)==3)
for module,(matcher,fonts,cache) in zip((previous,current),pair({'unsupported':['A']})):
 f=face()
 matcher.decode_cubic_outline(f,(0.,),100.,1.,set());before=list(fonts.calls)
 matcher.decode_cubic_outline(f,(1.,),100.,1.,set())
 check('negative profile cache reused',list(cache.values())==[[]] and fonts.calls==before+[('scale',f.key)])
for module,(matcher,fonts,cache) in zip((previous,current),pair({'fail_measure':True})):
 for attempt in range(2):
  try:matcher.decode_cubic_outline(face(),(0.,),100.,1.,set())
  except ValueError as exc:check('measurement error propagation',str(exc)=='unsupported measurement')
  else:raise AssertionError('measurement error hidden')
  check('partial profile not installed',not cache)
 check('failed profile retries source measurement',len([c for c in fonts.calls if c[0]=='outline'])==2)

# Actual face outlines: whole/partial runs, shared size/position and alphabets.
fonts=current.FontMetrics([ROOT/'fonts']);old=previous.FontSpacing(metrics=fonts)
matcher=current.FontOutlineMatcher(fonts);sibling=current.FontOutlineMatcher(fonts)
check('shared exact metrics owner',matcher.metrics is fonts and sibling.metrics is fonts)
check('row service no longer owns decoder/profile dictionary',not hasattr(current,'FontSpacing') and not hasattr(fonts,'decode_cubic_outline'))
check('measurement owner still has no interpretation cache',not hasattr(fonts,'outline_profiles') and not hasattr(fonts,'_profiles'))
face_real=fonts.matching_face('Arial',0,False)
for text in ('a','abc','abc de','Hello','iiii','AV'):
 outline=fonts.cubic_outline(face_real,text)
 if outline is None:continue
 for fs in (20.,40.):
  factor=fonts.ass_em_scale(face_real)*fs/outline[1]
  for scale in (.8,1.,1.2):
   for x,y in ((0.,0.),(125.,-37.)):
    path=[];axis=0
    for value in outline[0]:
     if isinstance(value,str):path.append(value)
     else:path.append(value*factor*scale+(x if axis%2==0 else y));axis+=1
    path=tuple(path)
    for clip in (None,-2):
     actual=path if clip is None else path[:clip]
     result=matcher.decode_cubic_outline(face_real,actual,fs,1.,set(text))
     expected=old.decode_cubic_outline(face_real,actual,fs,1.,set(text))
     check('real exact-font contour parity',result==expected)
check('same exact outline cache borrowed',fonts.cubic_outline(face_real,'abc') is fonts.cubic_outline(face_real,'abc'))
check('sibling matcher owns separate profiles',sibling._profiles is not matcher._profiles)
# Event-specific cache isolation and inferred cue integration, using prior fixtures.
fpath=ROOT/'tests'/'check_vector_text_stages.py';fixtures={'__file__':str(fpath),'__name__':'outline_vector_fixtures'}
exec(compile(fpath.read_text().split('class RecordingMetric:')[0],str(fpath),'exec'),fixtures)
adapt_reference_font_api(previous)
engines={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
shared_matcher=current.FontOutlineMatcher(engines[current])
for case in fixtures['CASES']:
 for order in ('original','reverse','shuffle'):
  outputs=[]
  for module in (previous,current):
   parsed=fixtures['inputs'](module,case,order);before=snapshot(parsed);borrowed=dict(parsed)
   result=module.recover_vector_text_cues(parsed,engines[module],0.,font_report=font_test_report(engines[module]),outline_matcher=shared_matcher if module is current else None)
   check('vector source input evidence preserved',snapshot(parsed)==before and all(parsed[k] is v for k,v in borrowed.items()))
   outputs.append((snapshot(result),result[0] is parsed,font_test_report(engines[module]).rows_joined,sorted(font_test_report(engines[module]).missing_families)))
  check('complete vector cue decision/evidence parity '+case['name']+order,outputs[0]==outputs[1]);integration_cases+=1
  if case['name']=='drawing evidence infers missing cue':check('inferred cue remains recovered',outputs[-1][0][1]==1)
# Profile cache remains attached to the service, rather than recreated per file.
owner=engines[current];identity=id(shared_matcher);profile_ids={k:id(v) for k,v in shared_matcher._profiles.items()}
for _ in range(2):
 module=current;parsed=fixtures['inputs'](module,fixtures['CASES'][-2],'original')
 module.recover_vector_text_cues(parsed,owner,0.,font_report=font_test_report(owner),outline_matcher=shared_matcher)
 check('repeated conversions keep matcher identity',id(shared_matcher)==identity)
 check('repeated conversions retain cached profile identities',all(id(shared_matcher._profiles[k])==v for k,v in profile_ids.items()))
check('profiles contain no Event evidence',all(all(not hasattr(v,'source_index') for v in p) for profiles in shared_matcher._profiles.values() for p in profiles))

# Focused conversions traverse full pipeline and keep event source-fit results local.
conversions=[]
with tempfile.TemporaryDirectory() as directory:
 for name in ('Vector-text-inferred-source.ass','Vector-text-fragments-source.ass'):
  compared=[]
  for module in (previous,current):
   target=Path(directory)/(module.__version__+'-'+name)
   with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/name,target,module.SimplifyConfig(),font_metrics=engines[module],font_report=font_test_report(engines[module]),outline_matcher=shared_matcher if module is current else None)
   assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
   compared.append((target.read_bytes(),stats,font_test_report(engines[module]).rows_joined,sorted(font_test_report(engines[module]).missing_families)))
  check('focused conversion '+name,compared[0]==compared[1]);conversions.append(name)

from executable_ast_audit import executable_ast
# Bound the source change; the numerical method moves without edits.
def definitions(path):return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a=definitions(ROOT/'test-data/simplify_ass-v164-reference.py');b=definitions(ROOT/'simplify_ass.py')
old_decoder=next(n for n in a['FontSpacing'].body if isinstance(n,ast.FunctionDef) and n.name=='decode_cubic_outline')
new_decoder=next(n for n in b['FontOutlineMatcher'].body if isinstance(n,ast.FunctionDef) and n.name=='decode_cubic_outline')
class Normalize(ast.NodeTransformer):
 def visit_Attribute(self,n):
  n=self.generic_visit(n)
  if n.attr=='_profiles':n.attr='outline_profiles'
  return n
check('decoder algorithm AST unchanged',ast.dump(old_decoder,include_attributes=False)==ast.dump(Normalize().visit(deepcopy(new_decoder)),include_attributes=False))
# Portable ink has its own v173 method audit and real-backend regression.
backend=deepcopy(b['FontMetrics'])
ink=next(n for n in a['FontMetrics'].body if isinstance(n,ast.FunctionDef) and n.name=='line_ink_metrics')
backend.body=[deepcopy(ink) if isinstance(n,ast.FunctionDef) and n.name=='line_ink_metrics' else n for n in backend.body]
check('font backend unchanged outside portable ink',ast.dump(a['FontMetrics'],include_attributes=False)==ast.dump(backend,include_attributes=False))
check('ownership resolution unchanged',ast.dump(a['_apply_vector_text_ownership'],include_attributes=False)==ast.dump(b['_apply_vector_text_ownership'],include_attributes=False))
report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),search_cases=search_cases,vector_integration_cases=integration_cases,focused_conversions=conversions,checks=checks)
(ROOT/'validation/outline-matcher-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'outline matcher checks passed;',search_cases,'search cases;',integration_cases,'vector integration cases; two focused conversions')
