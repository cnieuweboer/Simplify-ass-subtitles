"""Source-owned fade/jitter words: exact geometry, atomicity and safe fallbacks."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
import ast,hashlib,json,tempfile,contextlib,io
from executable_ast_audit import executable_ast
import simplify_ass as s
ROOT=Path(__file__).resolve().parent
metric=s.FontMetrics([ROOT/'fonts']);checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,Arial,40,&H00FFFFFF,&H00000000,0,0,5,0,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def line(literal='A word here',start=1,length=50,x=960,y=74):
 return ''.join(f'Dialogue: 0,{s.format_time(start+i*.04)},{s.format_time(start+(i+1)*.04)},Default,,0,0,0,,{{\\pos({x+[0,.7,-.4,.6][i%4]},{y})}}{literal}\n' for i in range(length))
def parse(text):
 d=s._resolve_document_state(s.parse_subtitle_document(HEADER+text));es=list(d.events.values());return es,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in es},d.styles
base,v,styles=parse(line());proof=s.flatten_complete_line_jitter(base,v,styles);parent=proof.captions[0];anchor=s._owned_word_echo_anchors(parent,'A word here','word',metric)[0]
def echoes(*,word='word',x=anchor,y=74,start=1.2,n=14,step=.04,copies=3,extra='',alpha=None,jitter=True):
 return ''.join(f'Dialogue: 3,{s.format_time(start+i*step)},{s.format_time(start+(i+1)*step)},Default,,0,0,0,,{{\\pos({x+([0,.4,-.4,.3][i%4] if jitter else 0)+c*.05},{y})\\bord0\\blur2\\alpha&H{(round(17+223*i/max(1,n-1)) if alpha is None else alpha):02X}&{extra}}}{word}\n' for i in range(n) for c in range(copies))
def run(echo,parents=None,owner=metric,source_change=None):
 es,v,styles=parse(line()+echo);sources={e.source_index:e for e in es};j=s.flatten_complete_line_jitter(es,v,styles,source_events=sources)
 if source_change:
  sources={k:source_change(e) if e.layer=='3' else e for k,e in sources.items()}
 before=deepcopy(j.events)
 r=s.remove_owned_word_echoes(j.events,v,j.captions if parents is None else parents,sources,owner)
 check('borrowed input unchanged '+str(len(checks)),j.events==before)
 return r,j,v
r,j,v=run(echoes());check('three copies of fourteen fade frames removed',r.removed_effects==42 and r.events==j.events[:1])
check('parent unchanged',r.events[0]==j.captions[0])
check('already reduced pass idempotent',s.remove_owned_word_echoes(r.events,v,j.captions,{},metric).removed_effects==0)
for label,echo,kwargs in [
 ('no accepted parent',echoes(),{'parents':()}),('missing metric',echoes(),{'owner':None}),
 ('unrelated word',echoes(word='other'),{}),('different case',echoes(word='Word'),{}),
 ('wrong font',echoes(extra=r'\fnUnknownExactFont'),{}),('different alignment',echoes(extra=r'\an7'),{}),
 ('clip',echoes(extra=r'\clip(0,0,1920,1080)'),{}),('rotation',echoes(extra=r'\frz1'),{}),
 ('original animation',echoes(extra=r'\t(\fs42)'),{}),('inline gradient',echoes(word=r'wo{\1c&H123456&}rd'),{}),
 ('long event',echoes(n=3,step=.17),{}),('two frames',echoes(n=2,copies=5),{}),
 ('too few samples',echoes(n=7,copies=1),{}),('sequence outside parent',echoes(n=90),{}),
 ('static opaque overlay',echoes(alpha=0,jitter=False),{}),('static translucent overlay',echoes(alpha=180,jitter=False),{}),
 ('bright jitter without fade',echoes(alpha=87),{}),('distant word',echoes(x=anchor+10),{}),
 ('other row',echoes(y=84),{}),('echo before cue',echoes(start=.98),{}),('echo after cue',echoes(start=3.01),{}),
 ('changed source timing',echoes(),{'source_change':lambda e:replace(e,end_s=e.end_s+.01)}),
 ('missing source',echoes(),{'source_change':lambda e:replace(e,text=e.text.replace('word','different'))}),
 ]:
 r,_,_=run(echo,**kwargs);check('preserve '+label,r.removed_effects==0)
for n,copies,accepted in [(3,3,True),(8,1,True),(7,1,False)]:
 r,_,_=run(echoes(n=n,copies=copies));check('minimum frame/sample boundary '+str((n,copies)),bool(r.removed_effects)==accepted)
for duration,accepted in [(.16,True),(.17,False)]:
 r,_,_=run(echoes(n=3,step=duration));check('frame duration boundary '+str(duration),bool(r.removed_effects)==accepted)
r,_,_=run(echoes(alpha=180));check('faint jitter family without fade',r.removed_effects==42)
r,_,_=run(echoes(jitter=False));check('fade family without jitter',r.removed_effects==42)
# Unit=2.4px; test fixed ownership position with no jitter.
for dx,accepted in [(2.4,True),(2.40001,False)]:
 r,_,_=run(echoes(x=anchor+dx,jitter=False,copies=1));check('anchor tolerance '+str(dx),bool(r.removed_effects)==accepted)
# Entire-family range, rather than pairwise drift, is bounded.
for extent,accepted in [(2.4,True),(2.40001,False)]:
 es,_,_=parse(echoes(x=anchor-extent/2,jitter=False,copies=1))
 family=[s.replace_event(e,text=e.text.replace(f'\\pos({anchor-extent/2},',f'\\pos({anchor+extent/2},')) if i%2 else e for i,e in enumerate(es)]
 check('family extent boundary '+str(extent),s._prove_word_echo_family(family)==accepted)
# Faint tail after the cue is owned; an early readable tail is retained.
r,j,_=run(echoes(start=2.7));check('bounded faint tail removed without extending parent',r.removed_effects==42 and r.events[0].end_s==3)
r,_,_=run(echoes(start=2.9));check('readable tail outside cue retained',r.removed_effects==0)
# Same-word positions inside a repeated literal and competing full captions.
es,v,styles=parse(line('word and word'));j=s.flatten_complete_line_jitter(es,v,styles);xs=s._owned_word_echo_anchors(j.captions[0],'word and word','word',metric)
check('repeated word has distinct anchors',len(xs)==2 and xs[1]>xs[0]+10)
es,v,styles=parse(line('word and word')+echoes(x=xs[1]));j=s.flatten_complete_line_jitter(es,v,styles);r=s.remove_owned_word_echoes(j.events,v,j.captions,{e.source_index:e for e in es},metric);check('second word occurrence uniquely removed',r.removed_effects==42)
r,_,_=run(echoes(),parents=(parent,parent));check('competing owners retain entire family',r.removed_effects==0)
# Real episode: exact family is bundled, source events are all original frames.
es=s.load_subtitle_events(ROOT/'test-data/Attack-on-Titan-S02E01-ending-source.ass')[1];v={e.source_index:s.OVERRIDE_RE.sub('',e.text) if not e.state.get('p') else '' for e in es};sources={e.source_index:e for e in es};j=s.flatten_complete_line_jitter(es,v,es[0].styles,source_events=sources)
r=s.remove_owned_word_echoes(j.events,v,j.captions,sources,metric)
check('real ending has 24 accepted owners',len(j.captions)==24)
check('real ending removes source-owned word echoes',r.removed_effects>3500)
check('all complete captions remain identical',all(e in r.events for e in j.captions))
unresolved={k:replace(e,state={}) for k,e in sources.items()}
before=deepcopy(unresolved)
check('unresolved production source formatting yields identical removal',
      s.remove_owned_word_echoes(j.events,v,j.captions,unresolved,metric).removed_effects==r.removed_effects)
check('borrowed unresolved source cache remains empty',unresolved==before)
missing=s.FontMetrics([]);missing.matching_face=lambda *a:None
check('missing exact font preserves every original echo',s.remove_owned_word_echoes(j.events,v,j.captions,sources,missing).removed_effects==0)
with tempfile.TemporaryDirectory() as directory:
 output=Path(directory)/'ending.ass';twice=Path(directory)/'twice.ass'
 fixture=ROOT/'test-data/Attack-on-Titan-S02E01-ending-source.ass'
 digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
 with contextlib.redirect_stdout(io.StringIO()):
  stats=s.simplify_ass(fixture,output,s.SimplifyConfig(),font_metrics=metric)
  again=s.simplify_ass(output,twice,s.SimplifyConfig(),font_metrics=metric)
 actual=s.load_subtitle_events(output)[1]
 check('actual ending pipeline emits 24 lines and removes 4413 echoes',stats['output']==24 and stats['covered_fragments']==4413)
 model=lambda es:sorted((s.OVERRIDE_RE.sub('',e.text),e.start_s,e.end_s,e.state['fn'],e.state['fs'],s.get_pos(e.text),e.state['1c'],e.state['3c']) for e in es)
 check('actual pipeline preserves all accepted parent geometry paint and timing',model(actual)==model(j.captions))
 check('actual pipeline output is byte-idempotent',output.read_bytes()==twice.read_bytes() and again['covered_fragments']==0)
 check('actual pipeline leaves source unchanged',hashlib.sha256(fixture.read_bytes()).hexdigest()==digest)
# Scope audit of this release; historical stage-1 audit remains frozen at v175.
def defs(p):return {n.name:n for n in executable_ast(ast.parse(p.read_text())).body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
a,b=defs(ROOT/'test-data/simplify_ass-v175-reference.py'),defs(ROOT/'test-data/simplify_ass-v176-reference.py')
check('focused proof definitions only',set(b)-set(a)=={'CompleteLineJitterResult','_word_echo_layout','_word_echo_families','_prove_word_echo_family','_owned_word_echo_anchors','remove_owned_word_echoes'} and not set(a)-set(b))
check('existing changes limited to owner return and consolidation',{k for k in a if ast.dump(a[k])!=ast.dump(b[k])}=={'flatten_complete_line_jitter','_consolidate_text_events'})
report=dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks,real_ending_removed=r.removed_effects)
(ROOT/'validation/word-echo-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(len(checks),'word-echo checks passed;',r.removed_effects,'real ending frames removed')
