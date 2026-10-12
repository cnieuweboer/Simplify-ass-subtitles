"""Complete source letter lifecycles, exact-font ownership and atomic fallback."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
import ast,contextlib,hashlib,io,json,random,tempfile
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
def parse(text):
 d=s._resolve_document_state(s.parse_subtitle_document(HEADER+text));return {e.source_index:e for e in d.events.values()}
def row(*,literal='A full line',start=1,y=120,x=960,stagger=.03,pulses=5,piece=.04,jitter=.5,colors=None,alpha=0,extra='',layer_offset=0):
 seed=next(iter(parse(f'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{{\\pos({x},{y})}}'+literal+'\n').values()))
 glyphs=s.authored_glyph_positions(metric,seed.state,literal,x,2)
 assert glyphs is not None
 face=metric.matching_face('Arial',0,False);factor=metric.ass_em_scale(face);out=[]
 for i,(char,gx) in enumerate(glyphs):
  width=metric.measure(face,char,False)*40/1024*factor
  a=start+i*stagger;b=a+.7;c=b+pulses*piece;d=c+1.3
  fill=colors[i%len(colors)] if colors else 'FFFFFF'
  for layer in [layer_offset,layer_offset+1]:
   paint='001122' if layer==layer_offset else fill;bord=2 if layer==layer_offset else 0
   def event(a,b,tags):
    out.append(f'Dialogue: {layer},{s.format_time(a)},{s.format_time(b)},Default,,0,0,0,,{{'+tags+extra+'}'+char+'\n')
   base=fr'\an5\pos({gx},{y})\bord{bord}\1c&H{paint}&\3c&H001122&\alpha&H{alpha:02X}&'
   event(a,b,base+r'\fad(200,0)')
   for j in range(pulses):
    dx=[0,jitter,-jitter,jitter*.5][j%4];dy=-dx
    pulse='555555' if j%2 else 'AAAAAA'
    event(b+j*piece,b+(j+1)*piece,fr'\an7\pos({gx-width/2+dx},{y-20+dy})\bord{bord}\1c&H{pulse}&\3c&H001122&\alpha&H{alpha:02X}&')
   event(c,d,base+r'\fad(0,200)')
 return ''.join(out)
def snapshot(parsed):return [(k,e.fields(),deepcopy(e.state),deepcopy(e.defaults),deepcopy(e.styles),e.evidence,e.continuation) for k,e in parsed.items()]
def run(text,*,metric_owner=metric,change=None):
 parsed=parse(text)
 if change:parsed=change(parsed)
 before=snapshot(parsed)
 result=s.reconstruct_glyph_lifecycles(parsed,metric_owner)
 check('borrowed source/cache unchanged '+str(len(checks)),snapshot(parsed)==before)
 return result,parsed
r,p=run(row());check('complete staggered explicit-frame line',len(r.rows)==1 and len(r.events)==1 and r.visibility_updates[r.events[0].source_index]=='A full line')
check('every source phase atomically consumed',r.removed_count==len(p)-1)
e=r.events[0];check('font placement fill outline retained',e.state['fn']=='Arial' and e.state['fs']==40 and abs(s.get_pos(e.text)[0]-960)<.01 and s.get_pos(e.text)[1]==120 and e.state['1c']=='FFFFFF' and e.state['3c']=='001122')
check('simple static opaque paint',e.state['1a']==0 and e.state['bord']==2 and e.state['shad']==0 and not any(t in e.text for t in [r'\fad(',r'\t(',r'\move(']))
check('common readable core retained',r.rows[0].phase_core[1]-r.rows[0].phase_core[0]>.32)
check('direct pass idempotent',s.reconstruct_glyph_lifecycles({e.source_index:e},metric).removed_count==0)
for label,text in [
 ('faint-only layers',row(alpha=128)),('clip',row(extra=r'\clip(0,0,1920,1080)')),
 ('rotation',row(extra=r'\frz10')),('shear',row(extra=r'\fax.1')),('tracking',row(extra=r'\fsp2')),
 ('mirrored scale',row(extra=r'\fscx-100')),('layout transform',row(extra=r'\t(\fs42)')),
 ('reset',row(extra=r'\r')),('two-sided fades',row().replace(r'\fad(200,0)',r'\fad(200,200)')),
 ('missing exit',row().replace(r'\fad(0,200)',r'\fad(0,0)')),
 ('long frames',row(piece=.17)),('moving phase',row(extra=r'\move(10,120,960,120)')),
 ('excess jitter',row(jitter=2.40001)),('insufficient complete core',row(stagger=.3)),
 ]:
 r,p=run(text);check('preserve '+label,r.removed_count==0 and r.events==list(p.values()))
r,p=run(row(),metric_owner=None);check('missing metric preserves input',r.removed_count==0)
missing=s.FontMetrics([ROOT/'fonts']);missing.matching_face=lambda *args:None
r,p=run(row(),metric_owner=missing);check('missing exact font preserves input',r.removed_count==0)
r,p=run(row(alpha=87));check('readable translucent layer becomes opaque',len(r.rows)==1 and r.events[0].state['1a']==0)
r,p=run(row(pulses=1));check('short single pulse supported with complete fading lifecycle',len(r.rows)==1)
# A lost frame or extra matching frame must reject the entire line.
def missing_frame(p):
 target=next(e for e in p.values() if e.layer=='1' and r'\an7' in e.text)
 return {k:e for k,e in p.items() if k!=target.source_index}
r,p=run(row(),change=missing_frame);check('missing phase cannot produce truncated line',r.removed_count==0)
def duplicate_frame(p):
 e=next(e for e in p.values() if e.layer=='1' and r'\an7' in e.text);k=max(p)+1;return {**p,k:replace(e,source_index=k)}
r,p=run(row(),change=duplicate_frame);check('competing frame rejects atomic line',r.removed_count==0)
def wrong_font(p):
 target=next(e for e in p.values() if e.layer=='1' and r'\fad(0,200)' in e.text)
 return {k:s.replace_event(e,text=e.text.replace('}',r'\fnUnavailableExactFont}',1)) if k==target.source_index else e for k,e in p.items()}
r,p=run(row(),change=wrong_font);check('unowned font phase blocks partial reconstruction',r.removed_count==0)
def moving_glyph(p):
 target=next(e for e in p.values() if e.layer=='1' and r'\fad(0,200)' in e.text)
 return {k:s.replace_event(e,text=s.re.sub(r'\\pos\([^)]*\)',r'\\move(0,120,1920,120)',e.text)) if k==target.source_index else e for k,e in p.items()}
r,p=run(row(),change=moving_glyph);check('unpositioned movement blocks incomplete row',r.removed_count==0)
def shifted_exit(p):
 target=next(e for e in p.values() if e.layer=='1' and r'\fad(0,200)' in e.text)
 return {k:s.replace_event(e,text=s.POS_RE.sub(lambda _:s.render_tag('pos',(s.get_pos(e.text)[0]+.041,120)),e.text,count=1)) if k==target.source_index else e for k,e in p.items()}
r,p=run(row(),change=shifted_exit);check('exit must return to authored held anchor',r.removed_count==0)
for jitter,accepted in [(2.4,True),(2.40001,False)]:
 r,_=run(row(jitter=jitter));check('fixed anchor boundary '+str(jitter),bool(r.rows)==accepted)
for piece,accepted in [(.16,True),(.17,False)]:
 r,_=run(row(piece=piece));check('short frame boundary '+str(piece),bool(r.rows)==accepted)
r,p=run(row(literal='same same')+row(literal='same same',start=4.4));check('repeated words and disconnected cues',len(r.rows)==2 and r.rows[0].base.end_s<r.rows[1].base.start_s)
r,p=run(row()+row(start=4.4,y=220));check('separate row placements',len(r.rows)==2)
r,p=run(row()+row(y=220,layer_offset=2));check('simultaneous different rows stay separate',len(r.rows)==2)
colors=['102030','406080','90B0D0'];r,p=run(row(colors=colors));check('genuine sustained per-letter colors retained',[e.state['1c'] for e,word,pos in r.rows[0].pieces]==[colors[i%3] for i in range(len(r.rows[0].pieces))] and r.events[0].text.count(r'\1c&')>2)
r,p=run(row()+row(start=4.4),change=lambda p:{k:replace(e,state={}) for k,e in reversed(list(p.items()))});check('unresolved cache and arbitrary source order supported',len(r.rows)==2)
# Whole source opening: source text derives from measured glyph positions.
fixture=ROOT/'test-data/Attack-on-Titan-S02E01-opening-source.ass';original=fixture.read_bytes();parsed=s.read_subtitle_document(fixture).events
result=s.reconstruct_glyph_lifecycles(parsed,metric)
check('21 complete romaji cue owners',len(result.rows)==21)
check('all 12783 romaji phases replaced atomically',result.removed_count==12762 and not any(e.style=='OP-R' and len(s.OVERRIDE_RE.sub('',e.text))==1 for e in result.events))
check('repeated refrain recovered twice',[s.OVERRIDE_RE.sub('',e.text) for e in result.events].count('sasageyo! sasageyo! shinzou wo sasageyo!')==2)
check('all accepted colors are sustained actual foreground/contour',all(row.base.state['1c']=='FFFFFF' and row.base.state['3c']=='101010' for row in result.rows))
check('source-only pass preserves other languages and drawing events',[e.fields() for e in result.events if e.style!='OP-R']==[e.fields() for e in parsed.values() if e.style!='OP-R'])
with tempfile.TemporaryDirectory() as directory:
 output=Path(directory)/'opening.ass';twice=Path(directory)/'twice.ass'
 with contextlib.redirect_stdout(io.StringIO()):
  stats=s.simplify_ass(fixture,output,s.SimplifyConfig(),font_metrics=metric)
  again=s.simplify_ass(output,twice,s.SimplifyConfig(),font_metrics=metric)
 actual=[e for e in s.load_subtitle_events(output)[1] if e.style=='OP-R'];expected=[row.base for row in result.rows]
 check('actual opening pipeline emits 21 static complete romaji lines',len(actual)==21 and stats['covered_fragments']==12762)
 check('actual pipeline preserves font placement paint and text',[(s.OVERRIDE_RE.sub('',e.text),e.state['fn'],e.state['fs'],s.get_pos(e.text),e.state['1c'],e.state['3c']) for e in actual]==[(s.OVERRIDE_RE.sub('',e.text),e.state['fn'],e.state['fs'],s.get_pos(e.text),e.state['1c'],e.state['3c']) for e in expected])
 check('actual source cores protected after handoffs',all(e.start_s<=row.phase_core[0]+1e-6 and e.end_s>=row.phase_core[1]-1e-6 for e,row in zip(actual,result.rows)))
 check('actual adjacent static romaji lines have no overlap',all(a.end_s<=b.start_s for a,b in zip(actual,actual[1:])))
 check('actual opening pipeline byte-idempotent',output.read_bytes()==twice.read_bytes() and again['covered_fragments']==0)
 check('source bytes untouched',fixture.read_bytes()==original)
def definitions(p):return {n.name:n for n in executable_ast(ast.parse(p.read_text())).body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
a,b=definitions(ROOT/'test-data/simplify_ass-v176-reference.py'),definitions(ROOT/'simplify_ass.py')
check('only focused lifecycle proof definitions added',set(b)-set(a)=={'GlyphPhaseLife','_index_glyph_phase_slots','_prove_glyph_phase_lives','reconstruct_glyph_lifecycles'} and not set(a)-set(b))
check('existing changes confined to source preparation and proof adoption',{k for k in a if ast.dump(a[k])!=ast.dump(b[k])}=={'_prepare_source_text','_consolidate_text_events'})
report=dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks,romaji_lines=21,source_phases=12783)
(ROOT/'validation/glyph-lifecycle-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(len(checks),'glyph lifecycle checks passed; 21 complete opening lines')
