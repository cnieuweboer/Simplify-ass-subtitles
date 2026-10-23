"""Shared static phase proofs and the row/support ownership boundaries."""
import test_paths
from event_evidence_test_helpers import without_inactive_color_phase_reporting
from event_evidence_test_helpers import contour_independent_contract as contract
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import contextlib,hashlib,importlib.util,io,json,sys
import simplify_ass as s
from lyric_layer_fixtures import HEADER,event

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

# Trace the actual current-policy handoff. Earlier copy cleanup can legitimately
# change the input relative to v185; the merger must preserve the roles it is
# given, and the consumer must receive exactly its adopted output.
source=ROOT/'test-data/Overlord-22m06-source.ass';digest=hashlib.sha256(source.read_bytes()).hexdigest()
def signature(e):return (e.fields(),e.row,e.lyric,e.source_index,e.state,e.evidence.original_contour_points,e.evidence.opaque_spans)
phase_output=[];captured=[];trace=[]
original=s.merge_shared_interval_rows
real_merge=s.merge_static_timed_copies
def capture(events,visible,owner,animated_sources,**kwargs):
 check('shared-interval consumer receives adopted phase events',
       len(events)==len(phase_output) and all(a is b for a,b in zip(events,phase_output)))
 captured.append(([signature(e) for e in events],dict(visible),set(animated_sources)))
 return original(events,visible,owner,animated_sources,**kwargs)
def track(events,styles,**kwargs):
 before=deepcopy([signature(e) for e in events])
 result=real_merge(events,styles,**kwargs)
 check('phase merger borrows actual caller inputs',before==[signature(e) for e in events])
 check('actual phase removal count matches retained slots',len(events)-len(result[0])==result[1])
 for caption in result[0]:
  source=next(e for e in events if e.source_index==caption.source_index)
  check('actual phase merger retains source row roles',(caption.row,caption.lyric)==(source.row,source.lyric))
 if not kwargs.get('text_only',False):phase_output[:]=result[0]
 trace.append(dict(text_only=kwargs.get('text_only',False),pending=kwargs.get('row_sources') is not None,removed=result[1]))
 return result
output=DEST/(s.__version__+'.ass');report=s.FontProcessingReport()
with patch.object(s,'merge_shared_interval_rows',capture),patch.object(s,'merge_static_timed_copies',track),contextlib.redirect_stdout(io.StringIO()):
 stats=s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metrics,font_report=report)
check('actual conversion has exact fonts available',not report.missing_families)
check('actual shared-interval handoff observed',len(captured)==1)
check('both actual callers share one implementation',len(trace)==2 and
      trace[0]['pending'] and not trace[0]['text_only'] and
      trace[1]['text_only'] and not trace[1]['pending'])
check('actual phase removals are reported',stats['static_merged']==sum(c['removed'] for c in trace))
check('source preserved',hashlib.sha256(source.read_bytes()).hexdigest()==digest)
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks),caller_trace=trace,
 runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'static phase handoff checks passed; source roles preserved; both stages share one merger')
