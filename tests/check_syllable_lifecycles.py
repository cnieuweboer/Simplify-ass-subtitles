"""Source-owned letter/syllable lifecycles, paint evidence and atomic refusal."""
import test_paths
from pathlib import Path
from copy import deepcopy
from collections import Counter
import contextlib,hashlib,io,json,tempfile
import simplify_ass as s
import syllable_lifecycle_cases as h
ROOT=h.ROOT;owner=h.metric();checks=[]
def check(label,value):
    assert value,label;checks.append(label)
def run(text):
    parsed=h.parse(text);before=deepcopy(parsed)
    result=s.reconstruct_glyph_lifecycles(parsed,owner)
    check('borrowed source and caches immutable '+str(len(checks)),parsed==before and
          [(e.fields(),e.state,e.defaults,e.styles,e.evidence,e.continuation) for e in parsed.values()]==
          [(e.fields(),e.state,e.defaults,e.styles,e.evidence,e.continuation) for e in before.values()])
    return result,parsed
def emit(parsed):
    return h.HEADER+''.join(e.kind+': '+','.join(e.fields())+'\n' for e in parsed.values())
def variant(label,change):
    parsed=h.parse(h.fixture());change(parsed)
    result,source=run(emit(parsed))
    check('atomic preservation '+label,result.removed_count==0 and result.events==list(source.values()))
for edges in (False,True):
    for effect in ('','fx','arbitrary annotation'):
        for split in (False,True):
            result,parsed=run(h.fixture(edges=edges,effect=effect,split_tags=split))
            label=f'{edges} {effect!r} split={split}'
            check('one complete source owner '+label,len(result.rows)==1 and len(result.events)==1 and result.removed_count==len(parsed)-1)
            e=result.events[0]
            check('literal and layout '+label,s.OVERRIDE_RE.sub('',e.text)==h.LITERAL and abs(s.get_pos(e.text)[0]-960)<.01 and s.get_pos(e.text)[1]==120)
            check('held paint and thin authored contour '+label,e.state['1c']=='D8DFE1' and e.state['3c']=='001122' and e.state['bord']==1)
            check('source cue and fade exposure '+label,e.start_s==1 and abs(e.end_s-(4.1 if edges else 4))<.001 and result.rows[0].phase_core[0]>=1)
            check('no animation or sweep remains '+label,not any(k in e.text for k in ('\\t(','\\fad(')) and e.state.get('blur',0)==0 and e.state.get('1a',0)==0)
# ASS effects which actually move text cannot supply stationary evidence.
for effect in ('Banner;20;0;0','Scroll up;0;1080;20',' Scroll Down ;0;1080;20'):
    result,parsed=run(h.fixture(effect=effect))
    check('preserve scrolling '+effect,result.removed_count==0)
for scale in (115,160,240):
    result,_=run(h.fixture(scale=scale))
    check('pulse magnitude is not a show-specific signature '+str(scale),len(result.rows)==1)
result,_=run(h.fixture(start=8,x=1100,y=220))
check('translated cue and geometry',len(result.rows)==1 and result.events[0].start_s==8 and abs(s.get_pos(result.events[0].text)[0]-1100)<.01)
def pulses(parsed):return [e for e in parsed.values() if e.layer=='3']
def remove_interior(parsed):
    e=next(e for e in parsed.values() if e.layer=='1' and s.OVERRIDE_RE.sub('',e.text)=='c' and '\\fad(0,' in e.text)
    del parsed[e.source_index]
variant('missing interior return',remove_interior)
def duplicate(parsed):
    e=pulses(parsed)[1];index=max(parsed)+1;parsed[index]=s.dataclass_replace(e,source_index=index)
variant('competing whole syllable',duplicate)
def shift(parsed):
    e=pulses(parsed)[1];x,y=s.get_pos(e.text);parsed[e.source_index]=s.replace_event(e,text=s.set_pos(e.text,(x+12,y)))
variant('shifted syllable',shift)
def mutate_pulse(parsed,old,new):
    e=pulses(parsed)[1];parsed[e.source_index]=s.replace_event(e,text=e.text.replace(old,new))
variant('growing rather than returning',lambda p:mutate_pulse(p,'\\fscx100','\\fscx180'))
variant('nonfading independent word',lambda p:mutate_pulse(p,'\\alpha&ff&','\\alpha&H10&'))
variant('moving replacement',lambda p:mutate_pulse(p,'\\an5','\\an5\\move(800,120,1000,120)'))
variant('clipped replacement',lambda p:mutate_pulse(p,'\\an5','\\an5\\clip(0,0,1920,1080)'))
variant('unsupported target',lambda p:mutate_pulse(p,'\\fscx100','\\fscx100\\frz30'))
variant('incorrect syllable literal',lambda p:mutate_pulse(p,'calm','clam'))
def competing_paint(parsed):
    e=next(e for e in parsed.values() if e.layer=='1' and s.OVERRIDE_RE.sub('',e.text)=='c' and '\\fad(0,' in e.text)
    parsed[e.source_index]=s.replace_event(e,text=e.text.replace('D8DFE1','99AAFF'))
variant('ambiguous missing terminal paint',competing_paint)
def interleave(parsed,style='Default',x=960):
    e=next(iter(h.parse(h.HEADER+h.record(2,1.5,3.5,fr'{{\pos({x},120)}}Independent',style=style)).values()))
    index=max(parsed)+1;parsed[index]=s.dataclass_replace(e,source_index=index)
variant('intervening same-family content',interleave)
variant('intervening foreign-style content',lambda p:interleave(p,'Other'))
def expanding_interloper(parsed):
    interleave(parsed,'Other',1600)
    index=max(parsed);e=parsed[index]
    parsed[index]=s.replace_event(e,text=e.text.replace('}',r'\t(0,1000,\fscx500)}',1))
variant('animated foreign content with a disjoint initial box',expanding_interloper)
parsed=h.parse(h.fixture());interleave(parsed,'Other',1700)
result,_=run(emit(parsed));check('disjoint intervening content preserved',len(result.rows)==1 and any('Independent' in e.text for e in result.events))
parsed=h.parse(h.fixture());interleave(parsed,'Other',1700)
index=max(parsed);peer=parsed[index]
parsed[index]=s.replace_event(peer,text=peer.text.replace('}',r'\t(0,1000,\fscx120)}',1))
result,_=run(emit(parsed))
check('provably disjoint animated content preserved',len(result.rows)==1 and
      any('Independent' in e.text and r'\t(' in e.text for e in result.events))
# Complete endpoint evidence retains intentional spatial paint changes.
parsed=h.parse(h.fixture(edges=False))
for index,e in list(parsed.items()):
    if e.layer=='1' and '\\fad(0,' in e.text:
        color='114477' if s.OVERRIDE_RE.sub('',e.text) in 'Scl' else 'CCAA77'
        parsed[index]=s.replace_event(e,text=e.text.replace('D8DFE1',color))
result,_=run(emit(parsed))
check('complete endpoint gradients remain intentional',len(result.rows)==1 and
      {e.state['1c'] for e,word,pos in result.rows[0].pieces}=={'114477','CCAA77'})
# A phase may touch within the existing centisecond source tolerance; this
# does not relax the interval to the separate fifty millisecond fade policy.
for delta,accepted in ((.01,True),(.02,False)):
    parsed=h.parse(h.fixture());e=pulses(parsed)[1]
    parsed[e.source_index]=s.replace_event(e,start=s.format_time(e.start_s+delta),start_s=e.start_s+delta)
    result,_=run(emit(parsed))
    check('replacement source timing tolerance '+str(delta),bool(result.rows)==accepted)
# Optional fitted scale must preserve source advance geometry within the
# existing five percent admission, rather than erasing the final font check.
parsed=h.parse(h.fixture());reversed_input=dict(reversed(list(parsed.items())))
a=s.reconstruct_glyph_lifecycles(parsed,owner);b=s.reconstruct_glyph_lifecycles(reversed_input,owner)
check('input iteration order does not choose ownership',[e.fields() for e in a.events]==[e.fields() for e in b.events])
check('no metric preserves source',s.reconstruct_glyph_lifecycles(parsed,None).removed_count==0)
# Shorthand hex is shared parser behavior, including branch-local transforms.
for tag in ('alpha','1a','3a','1c','3c'):
    for value in ('&ff&','&FF&','&Hff&','ff'):
        check('hex spelling '+tag+value,s.effective_state('{\\'+tag+value+'}',s.DEFAULT_STATE,{})==s.effective_state('{\\'+tag+'&HFF&}',s.DEFAULT_STATE,{}))
check('unrecognized hex trailing garbage remains ignored',s.effective_state(r'{\alpha&ff&junk}',s.DEFAULT_STATE,{})['1a']==0)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    for edges in (False,True):
        source=directory/f'case-{edges}.ass';out=source.with_suffix('.simple.ass');twice=source.with_suffix('.twice.ass')
        source.write_text(h.fixture(edges=edges));original=source.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            s.simplify_ass(source,out,s.SimplifyConfig(),font_metrics=owner)
            s.simplify_ass(out,twice,s.SimplifyConfig(),font_metrics=owner)
        events=s.load_subtitle_events(out)[1]
        check('synthetic pipeline literal and multiplicity '+str(edges),len(events)==1 and s.OVERRIDE_RE.sub('',events[0].text)==h.LITERAL)
        check('synthetic repeat conversion stable '+str(edges),out.read_bytes()==twice.read_bytes())
        check('synthetic source unchanged '+str(edges),source.read_bytes()==original)
    original=h.SOURCE.read_bytes();parsed=s.read_subtitle_document(h.SOURCE).events
    source_result=s.reconstruct_glyph_lifecycles(parsed,owner)
    rows=[row for row in source_result.rows if row.base.style=='ED - Romaji']
    check('real ending owns sixteen complete source captions',len(rows)==16)
    check('all real ending planes consumed',not any(e.style=='ED - Romaji' and e not in [r.base for r in rows] for e in source_result.events))
    out=directory/'episode.ass';twice=directory/'again.ass';report=s.FontProcessingReport()
    with contextlib.redirect_stdout(io.StringIO()):
        stats=s.simplify_ass(h.SOURCE,out,s.SimplifyConfig(),font_metrics=owner,font_report=report)
        s.simplify_ass(out,twice,s.SimplifyConfig(),font_metrics=owner)
    actual=[e for e in s.load_subtitle_events(out)[1] if e.style=='ED - Romaji']
    check('real pipeline sixteen complete lines',len(actual)==16 and [s.OVERRIDE_RE.sub('',e.text) for e in actual]==[s.OVERRIDE_RE.sub('',r.base.text) for r in rows])
    check('real exact fonts',not report.missing_families)
    check('real representative paint',all(e.state['1c']=='E1DFD8' and e.state['3c']=='000000' and e.state['bord']==1 for e in actual))
    check('real readable cores retained',all(e.start_s<=r.phase_core[0]+.011 and e.end_s>=r.phase_core[1]-.011 for e,r in zip(actual,rows)))
    check('real same-row handoffs settled',all(a.end_s<=b.start_s for a,b in zip(actual,actual[1:])))
    check('real repeated output stable',out.read_bytes()==twice.read_bytes())
    check('real source unchanged',h.SOURCE.read_bytes()==original)
(ROOT/'validation/syllable-lifecycle-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,
    engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'syllable lifecycle checks passed; sixteen real ending captions')
