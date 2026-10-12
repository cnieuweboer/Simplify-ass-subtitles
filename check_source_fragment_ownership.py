#!/usr/bin/env python3
"""Check source-fragment evidence ownership through confirmation and reconstruction."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import json
import simplify_ass as s
from event_evidence_test_helpers import event_comparison_fields

ROOT = Path(__file__).resolve().parent
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def fixture(*, unresolved=False, dense=True, seeded=False):
    lines = []
    for layer in (0,1):
        for i,word in enumerate(('ab','cd','ef','gh')):
            lines.append(f'Dialogue: {layer},0:00:01.00,0:00:05.00,Default,,0,0,0,,'
                +r'{\pos('+str(100+i*30)+',100)}'+word+'\n')
    if dense:
        for copy in range(3):
            for i,word in enumerate(('ab','cd','ef','gh')):
                lines.append(f'Dialogue: 2,0:00:01.{10+copy*20:02},0:00:01.{20+copy*20:02},Default,,0,0,0,,'
                    +r'{\pos('+str(100+i*30)+r',100)\t(0,100,\1a&HFF&)}'+word+'\n')
    doc = s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(lines)))
    events = list(doc.events.values())
    pieces = [(e,word,s.get_pos(e.text)) for e,word in zip(events[:4],('ab','cd','ef','gh'))]
    row = s.TextRow(events[0],pieces,[events[:4],events[4:8]],
        {word:[pos] for e,word,pos in pieces},virtual=True,phase_core=(1.25,4.75))
    if seeded:
        row.foreground = [events[0]]
        row.confirmed = True
    events[0].evidence = s.EventEvidence(opaque_spans=((1.,5.),))
    if unresolved:
        for e in events:e.state = {}
    words = {e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in events}
    positions = {e.source_index:s.get_pos(e.text) for e in events}
    animated = {e.source_index for e in events[8:]}
    return events,[row],words,positions,animated

def snapshot(args):
    events,rows,words,positions,animated = args
    return deepcopy(([event_comparison_fields(e) for e in events],
        [vars(row) for row in rows],words,positions,animated))

for unresolved in (False,True):
    args = fixture(unresolved=unresolved)
    before = snapshot(args)
    result = s.remove_source_fragment_effects(*args)
    row,new = args[1][0],result.rows[0]
    label = 'unresolved' if unresolved else 'resolved'
    check(label+' input evidence unchanged',snapshot(args)==before)
    check(label+' named count and working output',result.removed_effects==16 and len(result.events)==4)
    check(label+' confirmation returned only',new.confirmed and not row.confirmed and not row.foreground)
    check(label+' independent row and outer collection',new is not row and result.rows is not args[1])
    check(label+' independent pieces',new.pieces is not row.pieces)
    check(label+' independent paint rows',new.paint_rows is not row.paint_rows and
        all(a is not b for a,b in zip(new.paint_rows,row.paint_rows)))
    check(label+' independent anchors',new.source_anchors is not row.source_anchors and
        all(new.source_anchors[k] is not row.source_anchors[k] for k in row.source_anchors))
    check(label+' independent foreground',new.foreground is not row.foreground)
    check(label+' historical proof preserved',new.phase_core==row.phase_core and new.virtual==row.virtual and
        new.base.evidence is row.base.evidence)
    check(label+' removed paints remain evidence',all(e.source_index in {p.source_index for p in args[0]}
        for e in new.foreground) and any(e.source_index not in {p.source_index for p in result.events}
        for e in new.foreground))
    if unresolved:
        check('unresolved source privately resolved',all(e.state for e in result.events) and
            all(not e.state for e in args[0]))
        check('unresolved aliases rebound consistently',new.base is new.pieces[0][0] and
            new.base is new.paint_rows[0][0] and new.base is result.events[0] and new.base is not row.base)
    else:
        check('resolved event identity preserved',all(a is b for a,b in zip(result.events,args[0][:4])))
        check('resolved source provenance retained',new.base is row.base and
            all(any(e is source for source in args[0]) for e in new.foreground))
    outcome = s.reconstruct_text_rows(result.events,args[2],{},None,args[4],
        source_rows=result.rows,source_only=True)
    check(label+' reconstruction preserves input evidence',snapshot(args)==before)
    check(label+' reconstruction receives confirmation',bool(outcome.rows) and outcome.rows[0].confirmed)
    check(label+' source timing preserved',all(e.start_s==1 and e.end_s==5 for e in outcome.events))
    new.source_anchors['ab'].append((999,999));new.paint_rows[0].clear();new.foreground.clear();new.pieces.clear()
    check(label+' successor containers writable independently',snapshot(args)==before)

args = fixture(dense=False,seeded=True)
before = snapshot(args)
result = s.remove_source_fragment_effects(*args)
check('prior confirmation retained',result.rows[0].confirmed and result.rows[0].foreground==args[1][0].foreground)
check('prior confirmation input unchanged',snapshot(args)==before)
check('no removal keeps resolved events',result.removed_effects==0 and all(a is b for a,b in zip(result.events,args[0])))
check('no removal owns row containers',result.rows[0] is not args[1][0] and result.rows[0].foreground is not args[1][0].foreground)

empty = s.remove_source_fragment_effects([],[],{},{},set())
check('empty result explicit',empty.events==[] and empty.rows==[] and empty.removed_effects==0)
try:
    empty.removed_effects=1
except FrozenInstanceError:
    check('result binding immutable',True)
else:raise AssertionError('mutable result binding')

# A failure during matching must not leave partial confirmation or resolved
# formatting on a caller's source snapshot.
args = fixture(unresolved=True)
before = snapshot(args)
original = s.collapse_backed_glyph_pulses
def fail(*unused):raise RuntimeError('injected matching failure')
s.collapse_backed_glyph_pulses=fail
try:
    s.remove_source_fragment_effects(*args)
except RuntimeError:
    check('failed pass leaves input evidence untouched',snapshot(args)==before)
else:raise AssertionError('expected injected failure')
finally:s.collapse_backed_glyph_pulses=original

(ROOT/'validation/source-fragment-ownership-checks.json').write_text(json.dumps(
    dict(version=s.__version__,count=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'source-fragment ownership checks passed')
