"""Frame-pose policy preserves source exposure and borrowed event ownership."""
import test_paths
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import get_type_hints
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import event_operations, frame_pose as policy
from check_windows_installer import load_installer, ROOT

NAMES = ('_frame_paint_alphas', '_frame_pose_intervals', '_visible_pose_support',
         '_preserve_frame_pose_support', '_representative_frame_pose')
SPECS = ((1., 1.2, 100, 64), (1.2, 1.3, 110, 0), (1.3, 1.4, 120, 0))


def events(specs=SPECS):
    rows = ['[Script Info]\nWrapStyle: 2\n[Events]\n']
    for start, end, x, alpha in specs:
        rows.append(f'Dialogue: 0,{engine.format_time(start)},{engine.format_time(end)},Default,,0,0,0,,'
                    + rf'{{\pos({x},100)\bord0\shad0\alpha&H{alpha:02X}&}}A' + '\n')
    doc = engine._resolve_document_state(engine.parse_subtitle_document(''.join(rows)))
    return list(doc.events.values())


def capture(items):
    return [replace(e, evidence=engine.EventEvidence(frame_pose_intervals=policy._frame_pose_intervals(e)))
            for e in items]


def child(code, cwd, tools):
    return subprocess.run([sys.executable, '-I', '-c',
        'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + code],
        cwd=cwd, capture_output=True, text=True)


class FramePoseModuleChecks(unittest.TestCase):
    def test_canonical_aliases_types_and_validity_key(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(policy, name))
            get_type_hints(getattr(policy, name))
        self.assertIs(policy.Event, engine.Event)
        self.assertIs(policy._frame_pose_key, event_operations._frame_pose_key)
        self.assertIs(engine._frame_pose_key, event_operations._frame_pose_key)
        self.assertIs(get_type_hints(policy._preserve_frame_pose_support)['return'], engine.Event)

    def test_alphas_use_actual_visible_channels(self):
        event = events()[0]; before = deepcopy(vars(event))
        self.assertEqual(policy._frame_paint_alphas(event), (64, 255, 255))
        outline = replace(event, state={**event.state, '1a': 255, 'bord': 2., '3a': 80})
        self.assertEqual(policy._frame_paint_alphas(outline), (255, 80, 255))
        shadow = replace(event, state={**event.state, '1a': 255, 'xshad': -2., '4a': 100})
        self.assertEqual(policy._frame_paint_alphas(shadow), (255, 255, 100))
        self.assertEqual(vars(event), before)

    def test_support_capture_clipping_rounding_and_empty_evidence(self):
        event = events()[0]; before = deepcopy(vars(event))
        self.assertEqual(policy._frame_pose_intervals(event), ((1., 1.2, (64, 255, 255)),))
        held = capture([event])[0]
        extended = replace(held, end_s=3.)
        self.assertEqual(policy._frame_pose_intervals(extended), held.evidence.frame_pose_intervals)
        trimmed = replace(extended, start_s=1.1000004)
        self.assertEqual(policy._frame_pose_intervals(trimmed), ((1.1, 1.2, (64, 255, 255)),))
        gone = replace(held, start_s=2.)
        self.assertEqual(policy._frame_pose_intervals(gone), ())
        empty = replace(event, evidence=engine.EventEvidence(frame_pose_intervals=()))
        self.assertEqual(policy._frame_pose_intervals(empty), ())
        self.assertEqual(vars(event), before)

    def test_maximum_opacity_support_preserves_gaps_and_inputs(self):
        intervals = [(0., 2., (0, 255, 255)), (0., 2., (0, 255, 255)),
                     (1., 3., (128, 255, 255)), (4., 5., (0, 255, 255))]
        before = deepcopy(intervals)
        self.assertEqual(policy._visible_pose_support(iter(intervals), 0),
                         [(0., 2., 255), (2., 3., 127), (4., 5., 255)])
        self.assertEqual(policy._visible_pose_support(intervals, 1), [])
        self.assertEqual(intervals, before)

    def test_selection_borrows_candidates_and_ignores_copies_and_splitting(self):
        items = capture(events()); before = [deepcopy(vars(e)) for e in items]
        chosen, intervals = policy._representative_frame_pose(items)
        self.assertIs(chosen, items[0])
        self.assertEqual(intervals, items[0].evidence.frame_pose_intervals)
        copies = [*items, *[replace(items[1], source_index=99+i) for i in range(20)]]
        self.assertIs(policy._representative_frame_pose(copies)[0], items[0])
        self.assertIs(policy._representative_frame_pose(list(reversed(items)))[0], items[0])
        split = capture(events(((1., 1.1, 100, 64), (1.1, 1.2, 100, 64), *SPECS[1:])))
        self.assertEqual(policy._representative_frame_pose(split)[0].state['pos'], (100., 100.))
        self.assertEqual([vars(e) for e in items], before)

    def test_handoff_preserves_successor_proofs_and_rejects_other_geometry(self):
        items = capture(events()); source = items[0]
        successor = replace(source, end_s=3., evidence=engine.EventEvidence(opaque_spans=((9., 10.),)))
        before = [deepcopy(vars(e)) for e in [*items, successor]]
        kept = policy._preserve_frame_pose_support(source, successor, iter([source, source, items[1]]))
        self.assertIsNot(kept, successor)
        self.assertEqual(kept.evidence.frame_pose_intervals, source.evidence.frame_pose_intervals)
        self.assertEqual(kept.evidence.opaque_spans, ((9., 10.),))
        for name in ('state', 'defaults', 'styles', 'measurement', 'continuation'):
            self.assertIs(getattr(kept, name), getattr(successor, name))
        for moved in (replace(successor, text=successor.text+'!'),
                      replace(successor, measurement=replace(successor.measurement, script_wrap_mode=0))):
            self.assertIs(policy._preserve_frame_pose_support(source, moved), moved)
        self.assertEqual([vars(e) for e in [*items, successor]], before)

    def test_paint_selection_remains_independent_of_source_pose(self):
        items = capture(events()); before = [deepcopy(vars(e)) for e in items]
        self.assertIs(engine._frame_sequence_paint_owner(items), items[1])
        self.assertIs(policy._representative_frame_pose(items)[0], items[0])
        repainted = [event_operations.replace_event(e, text=e.text.replace('}', r'\alpha&H00&}', 1))
                     for e in items]
        self.assertIs(policy._representative_frame_pose(repainted)[0], repainted[0])
        self.assertEqual([e.evidence.frame_pose_intervals for e in repainted],
                         [e.evidence.frame_pose_intervals for e in items])
        self.assertEqual([vars(e) for e in items], before)

    def test_cold_and_installed_policy_and_owned_uninstall(self):
        code = r'''
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from _simplify_ass import frame_pose as p, event_operations as o, subtitle_document as d
from _simplify_ass.event_model import EventEvidence
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
assert p._frame_pose_key is o._frame_pose_key
raw='[Events]\n'+r'Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\pos(100,100)\bord0\shad0}A'+'\n'
event=next(iter(d._resolve_document_state(d.parse_subtitle_document(raw)).events.values()))
event=replace(event,evidence=EventEvidence(frame_pose_intervals=p._frame_pose_intervals(event)))
before=deepcopy(vars(event))
chosen,intervals=p._representative_frame_pose([event,event])
assert chosen is event and intervals==((1.,2.,(0,255,255)),)
expanded=replace(event,end_s=4.,evidence=EventEvidence(opaque_spans=((9.,10.),)))
kept=p._preserve_frame_pose_support(event,expanded,[event,event])
assert kept.evidence.opaque_spans==((9.,10.),) and p._frame_pose_intervals(kept)==intervals
assert kept.state is expanded.state and kept.continuation is expanded.continuation
assert p._visible_pose_support([*intervals,*intervals],0)==[(1.,2.,255)]
assert vars(event)==before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as e
assert Path(p.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/frame_pose.py'
for name in ('_frame_paint_alphas','_frame_pose_intervals','_visible_pose_support','_preserve_frame_pose_support','_representative_frame_pose'):assert getattr(e,name) is getattr(p,name)
assert e._frame_pose_key is o._frame_pose_key
import py_compile
py_compile.compile(p.__file__,doraise=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            result = child(code, unrelated, ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            owner = load_installer(); target = root/'installed tools with spaces'
            _, tools = owner.install(ROOT, target, individual_launchers=False)
            result = child(code, unrelated, tools)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            user = tools/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((tools/'_simplify_ass/frame_pose.py').exists())
            self.assertFalse(any((tools/'_simplify_ass').rglob('frame_pose*.pyc')))


if __name__ == '__main__':
    unittest.main()
