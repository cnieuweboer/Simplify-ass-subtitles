#!/usr/bin/env python3
"""Check explicit protected-core ownership and adoption by timing consumers."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
import json
import simplify_ass as s
from event_evidence_test_helpers import event_comparison_fields

ROOT=Path(__file__).resolve().parent
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)

HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
SHADOW=r'\1a&HFF&\3a&HFF&\4a&H00&\shad2'

def fixture(*,cues=(),fade=r'\fad(200,300)',existing=None,virtual=False):
    lines=[]
    for word,start,end in [('ABCD',1.,4.),('WXYZ',3.8,7.)]:
        for i,char in enumerate(word):
            text=r'{\an5\pos('+str(100+20*i)+',100)}'+char
            lines.append(f'Dialogue: 0,{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{text}\n')
    for start,end in cues:
        lines.append(f'Comment: 0,{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,ABCD\n')
    doc=s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(lines)))
    originals=list(doc.events.values());events=[];rows=[]
    for offset,word in [(0,'ABCD'),(4,'WXYZ')]:
        glyphs=originals[offset:offset+4]
        base=s.replace_event(glyphs[0],text=s.render_simplified_caption(glyphs[0].state,word,pos=(130,100)))
        rows.append(s.TextRow(base,[(e,c,s.get_pos(e.text)) for e,c in zip(glyphs,word)],
            [list(glyphs)],{word:[(130.,100.)]},[glyphs[0]],True,virtual,existing))
        events.append(base)
    events+=originals[8:]
    visible={e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in events}
    sources={e.source_index:s.replace_event(e,text=e.text.replace('}',SHADOW+fade+'}',1))
             for e in originals[:8]}
    animated=set(sources)
    return events,visible,rows,animated,sources

def snapshot(args):
    events,visible,rows,animated,sources=args
    return deepcopy(([event_comparison_fields(e) for e in events],dict(visible),
        [vars(r) for r in rows],animated,{k:event_comparison_fields(e) for k,e in sources.items()}))

for name,options,expected in [
    ('shared fade',{},[(1.2,3.7),(4.,6.7)]),
    ('authored cue',dict(cues=[(1.4,3.6)]),[(1.4,3.6),(4.,6.7)]),
    ('ambiguous cue',dict(cues=[(1.4,3.6),(1.5,3.5)]),[None,(4.,6.7)]),
    ('present out-of-range cue',dict(cues=[(.9,4.1)]),[None,(4.,6.7)]),
    ('existing proof',dict(existing=(1.3,3.6)),[(1.3,3.6),(1.3,3.6)]),
    ('virtual evidence',dict(virtual=True),[None,None]),
    ('invalid fade',dict(fade=r'\fad(invalid,300)'),[None,None]),
]:
    args=fixture(**options);before=snapshot(args);result=s.remove_covered_fragment_effects(*args)
    check(name+' borrowed inputs unchanged',snapshot(args)==before)
    check(name+' cores explicit',isinstance(result,s.CoveredFragmentRemoval) and
          [r.phase_core for r in result.rows]==expected)
    check(name+' proof independent of removal count',result.removed_effects==0)
    check(name+' unchanged events retain identity',all(a is b for a,b in zip(args[0],result.events)))
    check(name+' rows independently owned',all(old is not new and old.base is new.base and
        old.pieces is not new.pieces and old.paint_rows is not new.paint_rows and
        old.paint_rows[0] is not new.paint_rows[0] and old.source_anchors is not new.source_anchors and
        old.source_anchors[next(iter(old.source_anchors))] is not new.source_anchors[next(iter(new.source_anchors))] and
        old.foreground is not new.foreground for old,new in zip(args[2],result.rows)))
    for row in result.rows:
        row.pieces.clear();row.paint_rows[0].clear();row.source_anchors[next(iter(row.source_anchors))].clear()
        row.foreground.clear();row.phase_core=(0.,0.)
    check(name+' nested successor edits isolated',snapshot(args)==before)

args=fixture();rows=args[2]
duplicate=s.dataclass_replace(rows[0],pieces=list(rows[0].pieces))
rows.insert(0,duplicate)
result=s.remove_covered_fragment_effects(*args)
check('duplicate source index protects selected model only',
    [r.phase_core for r in result.rows]==[None,(1.2,3.7),(4.,6.7)])
check('duplicate source index leaves originals intact',all(r.phase_core is None for r in rows))

args=fixture();args[2].insert(0,args[2][0]);result=s.remove_covered_fragment_effects(*args)
check('repeated row reference receives same selected proof',
    [r.phase_core for r in result.rows]==[(1.2,3.7),(1.2,3.7),(4.,6.7)])
check('repeated references have independent successor containers',
    result.rows[0] is not result.rows[1] and result.rows[0].pieces is not result.rows[1].pieces)

args=fixture();args=(args[0],MappingProxyType(args[1]),args[2],frozenset(args[3]),MappingProxyType(args[4]))
before=snapshot(args);result=s.remove_covered_fragment_effects(*args)
check('read-only maps and animated set accepted',snapshot(args)==before and result.rows[0].phase_core==(1.2,3.7))
try:result.rows=[]
except FrozenInstanceError:check('result bindings immutable',True)
else:raise AssertionError('result bindings should be immutable')

# Remove source fallback so a successful handoff must consume returned cores.
args=fixture();result=s.remove_covered_fragment_effects(*args)
before=snapshot(args)
returned_before=snapshot((result.events,args[1],result.rows,args[3],args[4]))
families=s.collect_faded_cue_families(result.events,result.rows,{})
trimmed,count=s.trim_faded_cue_overlaps(result.events,result.rows,{},cue_families=families)
check('adopted phase cores prove handoff',count==1 and trimmed[0].end_s==trimmed[1].start_s==3.9)
check('handoff preserves both protected cores',trimmed[0].end_s>=result.rows[0].phase_core[1] and
    trimmed[1].start_s<=result.rows[1].phase_core[0])
untrimmed,count=s.trim_faded_cue_overlaps(result.events,args[2],{})
check('unadopted original evidence cannot prove handoff',count==0 and
    all(a is b for a,b in zip(untrimmed,result.events)))
check('timing consumers leave borrowed evidence unchanged',snapshot(args)==before and
    snapshot((result.events,args[1],result.rows,args[3],args[4]))==returned_before)
check('trimmed events leave row bases and fragments historical',
    result.rows[0].base.end_s==4. and result.rows[1].base.start_s==3.8 and
    all(piece.end_s==4. for piece,word,pos in result.rows[0].pieces))

args=fixture();before=snapshot(args);original=s._remove_covered_shadow_fragments
def fail(*unused):raise RuntimeError('injected removal failure after timing proof')
s._remove_covered_shadow_fragments=fail
try:s.remove_covered_fragment_effects(*args)
except RuntimeError as error:check('failure exercised after selection',str(error).startswith('injected'))
else:raise AssertionError('expected injected failure')
finally:s._remove_covered_shadow_fragments=original
check('failed pass leaves caller evidence unchanged',snapshot(args)==before)

(ROOT/'validation/covered-fragment-ownership-checks.json').write_text(json.dumps(
    dict(version=s.__version__,count=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'covered-fragment ownership checks passed')
