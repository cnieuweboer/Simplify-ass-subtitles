#!/usr/bin/env python3
"""Check contour history ownership, replacement rules and normalization clearing."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
import ast
import json
import simplify_ass as s

ROOT = Path(__file__).resolve().parent
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

HEADER = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Sign,Arial,40,7,0,0
Style: Other,Arial,45,7,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
raw = HEADER + r'Dialogue: 0,0:00:01.00,0:00:04.00,Sign,,0,0,0,,{\an7\pos(100,100)\p1\bord0\shad0}m 0 0 l 400 0 400 100 0 100'+'\n'
doc = s._resolve_document_state(s.parse_subtitle_document(raw))
event = next(iter(doc.events.values()))
points = [[100,100],[500,100],[500,200],[100,200]]
evidence = s.EventEvidence(points)
points[0][0] = -999
points.append([0,0])
check('input point containers cannot change stored contour',
      evidence.original_contour_points == ((100,100),(500,100),(500,200),(100,200)))
try:
    evidence.original_contour_points = ()
except FrozenInstanceError:
    check('evidence record is frozen', True)
else:
    raise AssertionError('evidence record is mutable')
try:
    evidence.original_contour_points[0][0] = -1
except TypeError:
    check('nested point tuples are immutable', True)
else:
    raise AssertionError('point coordinates are mutable')
check('empty contour is distinct from absent evidence', s.EventEvidence(()).original_contour_points == ())

event.evidence = evidence
before = deepcopy(vars(event))
check('formatting state contains no contour evidence', '_original_contour_points' not in event.state)
plain = s.replace_event(event,evidence=s.EventEvidence())
check('event evidence does not change state grouping', s.state_key(plain) == s.state_key(event))
check('event evidence does not change ASS fields', plain.fields() == event.fields())
check('event comparison remains formatting-independent', plain == event)

paint = event.text.replace(r'\bord0',r'\1a&H80&\bord0')
automatic = s.replace_event(event,text=paint)
check('unproven text replacement clears contour', automatic.evidence.original_contour_points is None)
explicit = s.replace_event(event,text=paint,evidence=evidence)
check('proven paint edit retains the immutable record', explicit.evidence is evidence)
check('paint replacement synchronizes effective formatting', explicit.state['1a'] == 128)
check('paint replacement has independent resolved state', explicit.state is not event.state)
check('paint replacement does not move evidence into state', '_original_contour_points' not in explicit.state)
for name,change in [
    ('drawing path',dict(text=event.text.replace('400','300'))),
    ('position',dict(text=event.text.replace('(100,100)','(200,100)'))),
    ('style',dict(style='Other')),
    ('explicit state',dict(state={**event.state,'fscx':50})),
    ('defaults',dict(defaults=dict(event.defaults))),
    ('styles',dict(styles=dict(event.styles))),
    ('left margin',dict(margin_l='10')),
    ('right margin',dict(margin_r='10')),
    ('vertical margin',dict(margin_v='10')),
    ('unit',dict(unit=2)),
]:
    check(name+' replacement clears unsupported contour history',
          s.replace_event(event,**change).evidence.original_contour_points is None)
for name,change in [
    ('timing',dict(start='0:00:02.00',start_s=2)),
    ('layer',dict(layer='1')),
    ('effect cleanup',dict(effect='')),
    ('local output index',dict(source_index=99)),
]:
    changed=s.replace_event(event,**change)
    check(name+' retains immutable historical contour',changed.evidence is evidence)
check('caller can explicitly clear history for a timing replacement',
      s.replace_event(event,end='0:00:05.00',end_s=5,evidence=s.EventEvidence()).evidence.original_contour_points is None)
check('all replacements leave the source event unchanged',vars(event)==before)

rendered=s.render_subtitle_document(doc,[event])
check('evidence does not enter serialized ASS',rendered==s.render_subtitle_document(doc,[plain]))
normalized=s._normalize_text_result(doc,s.TextProcessingResult([event],{}))
check('render/reparse boundary clears typed evidence',
      all(e.evidence.original_contour_points is None for e in normalized.events.values()))
check('normalization does not change source history', event.evidence is evidence and vars(event)==before)

# Isolate the final texture-removal boundary: an admitted support must still
# cover the text in BOTH its rendered fill and its recorded original contour.
source_doc=s._resolve_document_state(s.parse_subtitle_document(raw +
    r'Dialogue: 2,0:00:01.00,0:00:04.00,Sign,,0,0,0,,{\pos(300,150)}texture'+'\n'+
    r'Dialogue: 2,0:00:01.00,0:00:04.00,Sign,,0,0,0,,{\pos(300,150)}Hello'+'\n'))
source_panel,texture,caption=list(source_doc.events.values())
cutout=((100,100),(500,100),(500,200),(320,200),(320,130),(280,130),(280,200),(100,200))
for name,contour,removed in [('no history',None,True),
                             ('complete original fill',evidence.original_contour_points,True),
                             ('original cutout',cutout,False),('empty original contour',(),False)]:
    panel=s.replace_event(source_panel,evidence=s.EventEvidence(contour))
    source_before=deepcopy(vars(panel))
    with patch.object(s,'reduce_supporting_drawings',return_value=([panel],{'drawing_strips_collapsed':0})), \
         patch.object(s,'reconstruct_composite_backdrops',return_value=[]), \
         patch.object(s,'select_caption_supports',return_value=([panel],{panel.source_index:[caption]})), \
         patch.object(s,'retain_unmeasured_backdrops',return_value=[]), \
         patch.object(s,'is_font_texture',side_effect=lambda e,metric:e.source_index==texture.source_index), \
         patch.object(s,'caption_bounds',return_value=(290,140,310,160)):
        result=s._rebuild_caption_supports([panel],source_doc.lines,[texture,caption],
            source_doc.lines,{},s.SimplifyConfig(),None)
    check(name+' final texture removal respects original contour',
          (texture.source_index in result.removed_textures)==removed)
    check(name+' support boundary does not mutate borrowed evidence',vars(panel)==source_before)

tree=ast.parse((ROOT/'simplify_ass.py').read_text())
check('legacy contour dictionary key absent from production',
      not any(isinstance(n,ast.Constant) and n.value=='_original_contour_points' for n in ast.walk(tree)))
check('unused composite metadata absent from production',
      not any(isinstance(n,ast.Constant) and n.value=='_composite_backdrop_bounds' for n in ast.walk(tree)))
(ROOT/'validation/event-evidence-checks.json').write_text(json.dumps(dict(
    version=s.__version__,checks=checks,count=len(checks)),indent=2)+'\n')
print(len(checks),'event-evidence ownership checks passed')
