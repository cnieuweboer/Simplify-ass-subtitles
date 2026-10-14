"""Shared static phase proofs and the row/support ownership boundaries."""
import test_paths
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import contextlib,hashlib,importlib.util,io,json,sys
import simplify_ass as s
from event_evidence_test_helpers import freeze_caption_policy_for_legacy_comparison
freeze_caption_policy_for_legacy_comparison(s)
from lyric_layer_fixtures import HEADER,event
from font_geometry_test_helpers import historical_final_tag_policy

ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'validation/static-phase-handoff';DEST.mkdir(exist_ok=True)
checks=[];metrics=s.FontMetrics([ROOT/'fonts'])
assert metrics.matching_face('Volkhov',0,False) is not None,'Missing Volkhov regular'
def check(name,condition):
 assert condition,name
 checks.append(name)
def parse(rows):return list(s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(rows))).events.values())
def merge(es,**kwargs):return s.merge_static_timed_copies(es,es[0].styles if es else {},font_metrics=metrics,**kwargs)
for spelling in ('same','o',r'a{\1c&H123456&}b'):
 es=parse([event(spelling,100,0,(1,2)),event('Peer',100,0,(1,2)),event(spelling,100,0,(2,4))])
 es[0].row=es[2].row=4;es[0].lyric=es[2].lyric=True
 before=deepcopy(es);sources={es[0].source_index,es[2].source_index};sources_before=sources.copy()
 check(spelling+': pending row slots retained',merge(es,row_sources=sources)==(es,0))
 out,n=merge(es,text_only=True)
 check(spelling+': expired peer no longer blocks finished phases',n==1 and out[0].start_s==1 and out[0].end_s==4)
 check(spelling+': source/cache/context/evidence preserved',out[0].source_index==es[0].source_index and
       out[0].state is es[0].state and out[0].continuation is es[0].continuation and
       out[0].evidence is es[0].evidence and out[0].measurement is es[0].measurement)
 check(spelling+': inputs unchanged',[vars(e) for e in es]==[vars(e) for e in before] and sources==sources_before)
 es[0].lyric=es[2].lyric=False
 check(spelling+': irrelevant row labels do not disable improved early proof',merge(es,row_sources=set())[1]==1)
 for e in es:e.source_index=17
 check(spelling+': overlapping active peer blocks despite colliding IDs',
       merge([es[0],s.replace_event(es[1],end='0:00:04.00',end_s=4),es[2]],text_only=True)[1]==0)

for mode in ('same row','different row','different eligibility','lyric and animated equivalence'):
 es=parse([event('o',100,0,(1,2)),event('o',100,0,(2,4))]);es[0].row=es[1].row=3
 sources={es[0].source_index,es[1].source_index}
 if mode=='different row':es[1].row=5
 if mode=='different eligibility':sources={es[1].source_index}
 if mode=='lyric and animated equivalence':es[1].lyric=True;sources={es[0].source_index}
 expected=0 if mode in ('different row','different eligibility') else 1
 out,n=merge(es,row_sources=sources)
 check(mode+': preserve actual consumer roles',n==expected)
 if n:
  check(mode+': merged survivor remains row eligible',out[0].row==3 and (out[0].lyric or out[0].source_index in sources))
 check(mode+': final invocation can settle redundant phases',merge(es,text_only=True)[1]==1)
 check(mode+': pending proof reaches fixed point',merge(out,row_sources=sources)==(out,0))

# Numeric layer spellings must not conceal a real same-layer foreground.
for layer in ('00','+0','-0','unknown'):
 es=parse([event('same',100,0,(1,2)),event('Foreground',100,layer,(1,4),r'\1c&H0000FF&'),event('same',100,0,(2,4))])
 check('numeric layer alias '+layer+': foreground remains above original slot',merge(es,text_only=True)==(es,0))
 check('numeric layer alias '+layer+': same protection at text stage',merge(es,row_sources=set())==(es,0))

for layer in ('00','+0','-0'):
 es=parse([event('same',100,0,(1,2)),event('same',100,layer,(2,4))])
 check('equivalent numeric layer phases '+layer+': semantic match',merge(es)[1]==1)
es=parse([event('same',100,'unknown',t) for t in ((1,2),(2,4))])
check('unknown candidate layer cannot authorize a merge',merge(es)==(es,0))

# Font, emphasis and size variations exercise the same spatial proof.
for family,bold,italic,size,tags in [
 ('Volkhov',0,False,24,r'\fs24'),('Volkhov',-1,True,48,r'\fs48\b1\i1'),
 ('FOT-MatisseMinori Pro-En B',-1,False,40,r'\fnFOT-MatisseMinori Pro-En B\b1')]:
 assert metrics.matching_face(family,bold,italic) is not None,('Missing required exact font',family,bold,italic)
 es=parse([event('same',100,0,(1,2),tags),event('Other',500,0,(1,4),tags),event('same',100,0,(2,4),tags)])
 check('font/style variation '+str((family,size))+': shared proof joins disjoint phases',
       merge(es,row_sources=set())[1]==merge(es,text_only=True)[1]==1)
 check('font/style variation '+str((family,size))+': stable on repeat',merge(merge(es)[0])[1]==0)

# Generalize ordering beyond the original single-font/show fixture.
for x in (400,500):
 for first,second in (((1,2),(2,4)),((2,4),(1,2))):
  es=parse([event('same',100,0,first),event('Other',x,0,(1,4)),event('same',100,0,second)])
  check('disjoint peer '+str((x,first))+': early/final share spatial proof',
        merge(es,row_sources=set())[1]==merge(es,text_only=True)[1]==1)
  check('unknown metrics preserve order '+str((x,first)),s.merge_static_timed_copies(es,es[0].styles)[1]==0)

drawings=parse([event('m 0 0 l 10 0 10 10',100,0,t,r'\p1') for t in ((1,2),(2,4))])
check('text/vector owner can join static drawings',merge(drawings)[1]==1)
check('final support owner retains drawing identities',merge(drawings,text_only=True)==(drawings,0))
check('drawing evidence remains historical rather than extended',merge(drawings)[0][0].evidence is drawings[0].evidence)

# Trace actual callers and what the shared-interval consumer receives. Compare
# its complete input against immutable v185, not only the final output count.
spec=importlib.util.spec_from_file_location('handoff_v185',ROOT/'tests/references/simplify_ass_v185.py')
reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)
source=ROOT/'test-data/Overlord-22m06-source.ass';digest=hashlib.sha256(source.read_bytes()).hexdigest()
recorded=[]
def signature(e):return (e.fields(),e.row,e.lyric,e.source_index,e.state,e.evidence.original_contour_points,e.evidence.opaque_spans)
for engine in (reference,s):
 captured=[];original=engine.merge_shared_interval_rows
 def capture(events,visible,owner,animated_sources,**kwargs):
  captured.append(([signature(e) for e in events],dict(visible),set(animated_sources)))
  return original(events,visible,owner,animated_sources,**kwargs)
 trace=[];real_merge=engine.merge_static_timed_copies
 def track(events,styles,**kwargs):
  result=real_merge(events,styles,**kwargs)
  if engine is s:trace.append(dict(text_only=kwargs.get('text_only',False),pending=kwargs.get('row_sources') is not None,removed=result[1]))
  return result
 output=DEST/(engine.__version__+'.ass');report=engine.FontProcessingReport()
 with patch.object(engine,'merge_shared_interval_rows',capture),patch.object(engine,'merge_static_timed_copies',track),contextlib.redirect_stdout(io.StringIO()),historical_final_tag_policy(engine):
  stats=engine.simplify_ass(source,output,engine.SimplifyConfig(),font_metrics=engine.FontMetrics([ROOT/'fonts']),font_report=report)
 check(engine.__version__+': exact fonts available',not report.missing_families)
 recorded.append((captured,output.read_bytes(),stats))
 if engine is s:current_trace=trace
check('actual consumer receives same source roles visibility and intervals',recorded[0][0]==recorded[1][0])
check('focused source output and counters unchanged',recorded[0][1:]==recorded[1][1:])
check('both actual callers share one implementation',len(current_trace)==2 and
      current_trace[0]['pending'] and not current_trace[0]['text_only'] and
      current_trace[1]['text_only'] and not current_trace[1]['pending'])
check('source preserved',hashlib.sha256(source.read_bytes()).hexdigest()==digest)
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks),caller_trace=current_trace,
 runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'static phase handoff checks passed; source roles preserved; both stages share one merger')
