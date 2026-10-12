"""Bounded explicit frame jitter, owned paint stacks, and negative evidence."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
import ast,hashlib,json
from executable_ast_audit import executable_ast
import simplify_ass as s
ROOT=Path(__file__).resolve().parent
checks=[]
def check(name,condition):
    assert condition,name
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
def frames(*,layer=0,start=1,alpha=0,color='FFFFFF',length=12,step=.04,
           positions=None,extra='',literal='A complete line',paint_changes=False):
    positions=positions or [0,.7,-.4,.6,-.3,.8,-.5,.5,-.4,.6,-.2,.4]
    return ''.join(f'Dialogue: {layer},{s.format_time(start+i*step)},{s.format_time(start+(i+1)*step)},Default,,0,0,0,,'+
        '{'+fr'\pos({960+positions[i%len(positions)]},{74+positions[i%len(positions)]})\1c&H{color}&\1a&H{alpha+i if paint_changes else alpha:02X}&'+extra+'}'+literal+'\n'
        for i in range(length))
def inputs(text):
    d=s._resolve_document_state(s.parse_subtitle_document(HEADER+text))
    es=list(d.events.values());v={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in es}
    return es,v,d.styles
def run(text,**kwargs):
    es,v,styles=inputs(text);before=deepcopy(es)
    proof=s.flatten_complete_line_jitter(es,v,styles,**kwargs)
    result=(proof.events,proof.frames,proof.stacks)
    check('borrowed events unchanged '+str(len(checks)),es==before)
    return result
text=frames();out,n,stack=run(text)
check('explicit frames freeze without animation tags',len(out)==1 and n==11 and stack==0)
e=out[0]
check('literal/font/placement/timing retained',s.OVERRIDE_RE.sub('',e.text)=='A complete line' and e.state['fn']=='Arial' and e.state['fs']==40 and e.start_s==1 and e.end_s==1.48 and abs(e.state['pos'][0]-960)<=.8)
check('simple opaque caption paint',e.state['1a']==0 and e.state['1c']=='FFFFFF' and e.state['3c']=='000000' and e.state['bord']==2 and e.state['shad']==0)
check('pass idempotent',s.flatten_complete_line_jitter(out,{e.source_index:'A complete line'},e.styles)==s.CompleteLineJitterResult(out,0,0,()))
for alpha in (0,87,127):
    out,n,_=run(frames(alpha=alpha));check('readable translucent core '+str(alpha),len(out)==1 and n==11 and out[0].state['1a']==0)
for label,txt in [
    ('faint core',frames(alpha=128)),
    ('fade-only word echo',frames(alpha=17,paint_changes=True,literal='word')),
    ('few frames',frames(length=7)),
    ('no jitter',frames(positions=[0])),
    ('monotonic travel within box',frames(positions=[i*.1 for i in range(12)])),
    ('long chained travel',frames(positions=[i*.3 for i in range(12)])),
    ('font change splits incomplete families',frames(length=6)+frames(start=1.24,length=6,extra=r'\fnOther')),
    ('rotation',frames(extra=r'\frz1')),
    ('clip',frames(extra=r'\clip(0,0,1920,1080)')),
    ('inline gradient',frames(literal=r'A{\1c&H123456&} complete line')),
    ('animation source',frames(extra=r'\t(\fs41)')),
]:
    es,_,_=inputs(txt);out,n,k=run(txt);check('reject '+label,n==k==0 and out==es)
# Entire family range, not frame-to-frame range, is the boundary.
for extent,accepted in [(2,True),(2.00001,False)]:
    out,n,_=run(frames(positions=[0,extent,0,extent]));check('whole-family extent '+str(extent),(n>0)==accepted)
for length,accepted in [(8,True),(7,False)]:
    out,n,_=run(frames(length=length));check('readable core duration '+str(length),(n>0)==accepted)
out,n,_=run(frames()+frames(start=1.49));check('real gap and repeated caption retained',len(out)==2 and n==22 and out[0].end_s==1.48 and out[1].start_s==1.49)
# Staggered overlay shares the sustained core, with a real compositing order.
text=frames(length=24,color='D5E5F0',extra=r'\blur4')+frames(layer=1,start=1.1,length=20,alpha=87,color='000000')
out,n,k=run(text);check('staggered paint layers have one caption',len(out)==1 and n==42 and k==1 and out[0].start_s==1 and out[0].end_s==1.96)
check('foreground color selected without averaging backing',out[0].state['1c']=='000000' and out[0].state['3c']=='FFFFFF' and out[0].layer=='1')
# Disconnected foreground holds can belong to a continuously readable backing.
text=frames(length=60)+frames(layer=1,start=1.08,length=25,color='000000')+frames(layer=1,start=2.28,length=26,color='000000')
out,n,k=run(text);check('continuous backing owns foreground interruption',len(out)==1 and k==2 and out[0].start_s==1 and out[0].end_s==3.4)
for label,tail in [
    ('different alignment',frames(layer=1,extra=r'\an7')),
    ('different font',frames(layer=1,extra=r'\fnOther')),
    ('distant position',frames(layer=1,positions=[10,10.7,9.6,10.6])),
    ('excess stagger',frames(layer=1,start=1.17,length=12)),
    ('same-layer compositing multiplicity',frames(layer=0)),
]:
    out,n,k=run(frames()+tail);check('no stack merge '+label,k==0)
# Source animation evidence cannot be mistaken for explicit static frames after freezing.
es,v,styles=inputs(frames());sources={e.source_index:replace(e,text=e.text.replace('}',r'\t(\1c&H000000&)}',1)) for e in es}
proof=s.flatten_complete_line_jitter(es,v,styles,source_events=sources)
out,n,k=proof.events,proof.frames,proof.stacks
check('original animation rejects frozen lookalike',n==k==0 and out==es)
for label,change in [('fragment',lambda e:s.replace_event(e,text=e.text.replace('A complete line','A'))),
                     ('altered timing',lambda e:s.replace_event(e,end_s=e.end_s+.01)),
                     ('original clip',lambda e:s.replace_event(e,text=e.text.replace('}',r'\clip(0,0,1920,1080)}',1)))]:
    sources={e.source_index:change(e) for e in es}
    proof=s.flatten_complete_line_jitter(es,v,styles,source_events=sources)
    out,n,k=proof.events,proof.frames,proof.stacks
    check('reject reconstructed source '+label,n==k==0 and out==es)
# No optional font backend is required for literal/anchor identity proof.
out,n,k=run(frames(extra=r'\fnUnavailableExactFont'));check('missing font does not block complete literal proof',n==11 and out[0].state['fn']=='UnavailableExactFont')
# One-frame timing and layout limits, plus actual-core coverage in a stack.
for step,accepted in [(.16,True),(.17,False)]:
    out,n,k=run(frames(step=step));check('maximum frame duration '+str(step),(n>0)==accepted)
for stagger,accepted in [(.16,True),(.17,False)]:
    out,n,k=run(frames(length=60)+frames(layer=1,start=1+stagger,length=56,color='000000'))
    check('stack endpoint allowance '+str(stagger),(k>0)==accepted)
# Every layer has to be complete; a short unrelated duplicate is retained.
out,n,k=run(frames(length=60)+frames(layer=1,start=1.8,length=12,color='000000'))
check('partial temporal overlay has no stack owner',len(out)==2 and k==0)
# All-layer gaps remain gaps even with a repeated foreground and backing.
chunk=frames(length=24)+frames(layer=1,start=1.1,length=20,color='000000')
out,n,k=run(chunk+frames(start=2.2,length=24)+frames(layer=1,start=2.3,length=20,color='000000'))
check('repeated stacks preserve their shared gap',len(out)==2 and k==2 and out[0].end_s==1.96 and out[1].start_s==2.2)
def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
a=definitions(ROOT/'test-data/simplify_ass-v174-reference.py');b=definitions(ROOT/'test-data/simplify_ass-v175-reference.py')
expected={'JitterTextFamily','flatten_complete_line_jitter','_render_complete_line_jitter',
          '_index_complete_line_jitter','_group_complete_line_jitter_stacks',
          '_complete_line_jitter_families','_complete_line_jitter_core_overlap','_prove_complete_line_jitter'}
check('only focused family proof and helpers added',set(b)-set(a)==expected and not set(a)-set(b))
check('only existing consolidation entry changed',{k for k in a if ast.dump(a[k])!=ast.dump(b[k])}=={'_consolidate_text_events'})
report=dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks)
(ROOT/'validation/complete-line-jitter-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'complete-line jitter checks passed')
