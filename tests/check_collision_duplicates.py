"""Regression checks for unpositioned text and renderer collision placement."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile
import pickle
import subprocess
from copy import deepcopy
from typing import get_type_hints

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simplify_ass as s
from _simplify_ass import text_copy_reduction as copies
from check_windows_installer import load_installer
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(s)

root = Path(__file__).resolve().parents[1]
header = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def event(text='YES', *, layer=0, kind='Dialogue', start='0:00:01.00',
          end='0:00:04.00'):
    return f'{kind}: {layer},{start},{end},Default,,0,0,0,,{text}\n'

checks = 0
with tempfile.TemporaryDirectory() as temporary:
    source = Path(temporary) / 'input.ass'
    output = Path(temporary) / 'output.ass'

    def load(raw):
        source.write_text(header + raw)
        return s.load_subtitle_events(source)[1]

    # Equal records without positions are distinct collision-managed rows.
    for raw in [event() * 2,
                event(r'{\an2}YES') * 2,
                event(r'{\org(320,180)}YES') * 2,
                event() + event('Other caption') + event()]:
        events = load(raw)
        visible = {e.source_index: s.simplify_text(e.text, visible_only=True)[1]
                   for e in events}
        kept, removed = s.deduplicate_layers(events, visible)
        assert removed == 0 and [e.fields() for e in kept] == [e.fields() for e in events]
        checks += 1

        # The complete pipeline must keep both rows too, at either level.
        for level in (1, 2):
            with contextlib.redirect_stdout(io.StringIO()):
                stats = s.simplify_ass(source, output, s.SimplifyConfig(level=level),
                                       font_metrics=None, font_report=font_test_report(None))
            converted = s.load_subtitle_events(output)[1]
            assert stats['output'] == len(events)
            assert sum(s.simplify_text(e.text, visible_only=True)[1] == 'YES'
                       for e in converted) == 2
            checks += 1

    # Explicitly positioned opaque duplicates can still be removed.
    events = load(event(r'{\pos(320,180)}YES') * 2)
    kept, removed = s.deduplicate_layers(events, {e.source_index: 'YES' for e in events})
    assert len(kept) == 1 and removed == 1
    checks += 1
    with contextlib.redirect_stdout(io.StringIO()):
        stats = s.simplify_ass(source, output, s.SimplifyConfig(), font_metrics=None, font_report=font_test_report(None))
    assert stats['output'] == 1
    checks += 1

    # Drawings are not collision-managed text; retain their previous dedup rule.
    events = load(event(r'{\p1}m 0 0 l 100 0 100 50 0 50') * 2)
    kept, removed = s.deduplicate_layers(events, {})
    assert len(kept) == 1 and removed == 1
    checks += 1

    # Comments are preserved, and separate layers retain their existing handling.
    events = load(event(kind='Comment') * 2)
    kept, removed = s.deduplicate_layers(events, {})
    assert len(kept) == 2 and removed == 0
    checks += 1
    events = load(event(layer=0) + event(layer=1))
    kept, removed = s.deduplicate_layers(events, {e.source_index: 'YES' for e in events})
    assert len(kept) == 2 and removed == 0
    checks += 1

NAMES=('event_identity_for_dedup','has_translucent_paint','deduplicate_layers',
       'reduce_static_sign_copies','select_static_sign_paint','_near_containing_text_copy',
       'remove_late_complete_copies','remove_redundant_text_copies')
for name in NAMES:
    assert getattr(s,name) is getattr(copies,name)
    get_type_hints(getattr(copies,name))
    assert pickle.loads(('csimplify_ass\n'+name+'\n.').encode()) is getattr(copies,name)
    checks+=1
assert copies.Event is s.Event and copies.static_object_key is s.static_object_key
checks+=1
def resolved(rows):
    return list(s._resolve_document_state(s.parse_subtitle_document(header+''.join(rows))).events.values())

events=resolved([event(r'{\pos(100,100)\q2}YES')]*2)
before=deepcopy([vars(e) for e in events]);visible={e.source_index:'YES' for e in events}
for entry in (copies.deduplicate_layers,copies.reduce_static_sign_copies):
    for _ in range(2):
        kept,count=entry(events,visible)
        assert count==1 and len(kept)==1 and kept[0] is events[0]
        assert [vars(e) for e in events]==before
        assert visible=={e.source_index:'YES' for e in events}
        checks+=1
for entry in (copies.remove_redundant_text_copies,copies.remove_late_complete_copies):
    kept,count=entry(events)
    assert count==1 and kept[0] is events[0] and entry(kept)==(kept,0)
    assert [vars(e) for e in events]==before
    checks+=1

# Early paint selection and strict final redundancy keep their distinct contracts.
events=resolved([event(r'{\pos(100,100)\q2}YES'),
                 event(r'{\pos(101,100)\q2\1c&H123456&}YES',layer=1)])
visible={e.source_index:'YES' for e in events};before=deepcopy([vars(e) for e in events])
assert copies.remove_late_complete_copies(events)==(events,0)
assert copies.select_static_sign_paint(events,visible)==([events[1]],1)
assert [vars(e) for e in events]==before
checks+=1
for e in events:e.lyric=True
assert copies.reduce_static_sign_copies(events,visible)==(events,0)
checks+=1
events=resolved([event(r'{\pos('+str(x)+r',100)\q2}YES') for x in (100,102,104)])
visible={e.source_index:'YES' for e in events}
for entry in (copies.select_static_sign_paint,copies.reduce_static_sign_copies):
    assert entry(events,visible)==([events[0],events[2]],1)
    checks+=1
assert copies.remove_late_complete_copies(events)==([events[0],events[2]],1)
checks+=1

COLD_CODE=r'''
from pathlib import Path
from typing import get_type_hints
from copy import deepcopy
from _simplify_ass import text_copy_reduction as c, subtitle_document as d
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
for name in ('event_identity_for_dedup','has_translucent_paint','deduplicate_layers','reduce_static_sign_copies','select_static_sign_paint','_near_containing_text_copy','remove_late_complete_copies','remove_redundant_text_copies'):
 get_type_hints(getattr(c,name))
raw='[Events]\n'+(r'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\pos(100,100)\q2\alpha&H00&}YES'+'\n')*2
events=list(d._resolve_document_state(d.parse_subtitle_document(raw)).events.values())
before=deepcopy([vars(e) for e in events]);visible={e.source_index:'YES' for e in events}
assert c.deduplicate_layers(events,visible)==([events[0]],1)
assert c.reduce_static_sign_copies(events,visible)==([events[0]],1)
assert c.remove_late_complete_copies(events)==([events[0]],1)
assert [vars(e) for e in events]==before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as e
assert Path(c.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/text_copy_reduction.py'
for name in ('event_identity_for_dedup','has_translucent_paint','deduplicate_layers','reduce_static_sign_copies','select_static_sign_paint','_near_containing_text_copy','remove_late_complete_copies','remove_redundant_text_copies'):
 assert getattr(c,name) is getattr(e,name)
import py_compile
py_compile.compile(c.__file__,doraise=True)
'''
with tempfile.TemporaryDirectory() as folder:
    parent=Path(folder);unrelated=parent/'unrelated';unrelated.mkdir()
    installer=load_installer();target=parent/'installed tools with spaces'
    with contextlib.redirect_stdout(io.StringIO()):
        _,installed=installer.install(root,target,individual_launchers=False)
    for tools in (root,installed):
        child=subprocess.run([sys.executable,'-I','-c',
            'import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+COLD_CODE],
            cwd=unrelated,capture_output=True,text=True)
        assert child.returncode==0,child.stdout+child.stderr
        checks+=1
    user=installed/'_simplify_ass/user.py';user.write_text('# user\n')
    with contextlib.redirect_stdout(io.StringIO()):installer.remove(target)
    assert user.read_text()=='# user\n'
    assert not (installed/'_simplify_ass/text_copy_reduction.py').exists()
    assert not any((installed/'_simplify_ass').rglob('text_copy_reduction*.pyc'))
    checks+=1

result = {'checks': checks, 'version': s.__version__,
          'unpositioned_rows_retained': True,
          'positioned_duplicates_still_reduced': True,
          'drawing_deduplication_unchanged': True}
(root / 'validation' / 'collision-checks.json').write_text(json.dumps(result, indent=2) + '\n')
print(checks, 'collision-duplicate checks passed')
