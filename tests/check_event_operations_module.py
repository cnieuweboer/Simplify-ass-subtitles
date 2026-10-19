"""Event operations preserve cache, continuation and source-proof ownership."""
import test_paths
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import get_type_hints
import subprocess
import pickle
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import event_operations as operations
from check_windows_installer import load_installer, ROOT

NAMES = ('event_evaluation', 'replace_event', '_frame_pose_key', 'state_key')


def source():
    raw = ('[Script Info]\n[Events]\n'
           r'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\pos(100,100)\fs40}A' + '\n')
    doc = engine._resolve_document_state(engine.parse_subtitle_document(raw))
    event = next(iter(doc.events.values()))
    proof = engine.EventEvidence(original_contour_points=((1., 2.), (3., 4.)),
        opaque_spans=((1., 2.),), frame_pose_intervals=((1., 2., (0., 0., 255.)),))
    return replace(event, evidence=proof)


def child(code, cwd, tools):
    return subprocess.run([sys.executable, '-I', '-c',
        'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + code],
        cwd=cwd, capture_output=True, text=True)


class EventOperationsModuleChecks(unittest.TestCase):
    def test_canonical_aliases_and_types(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(operations, name))
            get_type_hints(getattr(operations, name))
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()), getattr(operations, name))
        self.assertIs(operations.Event, engine.Event)
        self.assertIs(operations.EventEvidence, engine.EventEvidence)
        self.assertIs(get_type_hints(operations.replace_event)['return'], engine.Event)
        self.assertIs(get_type_hints(operations.event_evaluation)['return'], engine.OverrideEvaluation)

    def test_resolved_read_borrows_and_unresolved_read_does_not_cache(self):
        event = source(); before = deepcopy(vars(event))
        result = operations.event_evaluation(event)
        self.assertIs(result.formatting, event.state)
        self.assertIs(result.continuation, event.continuation)
        empty = replace(event, state={}, continuation=engine.OverrideContinuation('Unknown', True))
        fresh = operations.event_evaluation(empty)
        self.assertEqual(fresh.formatting, event.state)
        self.assertEqual(fresh.continuation, event.continuation)
        self.assertIsNot(fresh.formatting, empty.state)
        self.assertEqual(empty.state, {})
        self.assertEqual(empty.continuation, engine.OverrideContinuation('Unknown', True))
        self.assertEqual(vars(event), before)

    def test_text_and_style_edits_own_complete_parse(self):
        event = source(); stale = engine.OverrideContinuation('Unknown', True)
        changed = operations.replace_event(event, text=event.text.replace('A', 'B'),
            state={'fs': 999}, continuation=stale)
        expected = engine.evaluate_effective_state(changed.text, changed.defaults, changed.styles)
        self.assertEqual(changed.state, expected.formatting)
        self.assertEqual(changed.continuation, expected.continuation)
        self.assertEqual(changed.evidence, engine.EventEvidence())
        styles = {**event.styles, 'Other': {**event.defaults, 'fs': 25., '1c': '123456'}}
        styled = operations.replace_event(replace(event, styles=styles), style='Other', text='B')
        self.assertIs(styled.defaults, styles['Other'])
        self.assertEqual(styled.state['fs'], 25.)
        self.assertEqual(styled.state['1c'], '123456')

    def test_explicit_cache_and_history_contract(self):
        event = source(); state = {**event.state, '1c': 'ABCDEF'}
        changed = operations.replace_event(event, state=state)
        self.assertIs(changed.state, state)
        self.assertIs(changed.continuation, event.continuation)
        history = engine.OverrideContinuation('Other', True)
        self.assertIs(operations.replace_event(event, state=state, continuation=history).continuation, history)
        cleared = operations.replace_event(event, state={}, continuation=history)
        self.assertEqual(cleared.continuation, engine.OverrideContinuation())

    def test_timing_edits_borrow_without_inventing_exposure(self):
        event = source(); before = deepcopy(vars(event))
        later = operations.replace_event(event, end='0:00:04.00', end_s=4., layer='2')
        self.assertIsNot(later, event)
        for name in ('state', 'defaults', 'styles', 'continuation', 'evidence', 'measurement'):
            self.assertIs(getattr(later, name), getattr(event, name))
        self.assertEqual(later.evidence.frame_pose_intervals, ((1., 2., (0., 0., 255.)),))
        self.assertEqual(vars(event), before)

    def test_paint_retains_only_pose_and_explicit_evidence_is_authoritative(self):
        event = source(); before = deepcopy(vars(event))
        repaint = operations.replace_event(event, text=event.text.replace('}', r'\1c&HABCDEF&}', 1))
        self.assertIsNone(repaint.evidence.original_contour_points)
        self.assertIsNone(repaint.evidence.opaque_spans)
        self.assertEqual(repaint.evidence.frame_pose_intervals, event.evidence.frame_pose_intervals)
        explicit = operations.replace_event(event, text='Other', evidence=event.evidence)
        self.assertIs(explicit.evidence, event.evidence)
        self.assertEqual(vars(event), before)

    def test_layout_and_context_changes_expire_pose_support(self):
        event = source()
        for changes in ({'text': 'B'}, {'state': {**event.state, 'pos': (200., 100.)}},
                        {'margin_l': '5'}, {'unit': 2.},
                        {'measurement': replace(event.measurement, script_wrap_mode=2)}):
            with self.subTest(changes=changes):
                self.assertIsNone(operations.replace_event(event, **changes).evidence.frame_pose_intervals)
        near = replace(event, state={**event.state, 'pos': (100.000001, 100.)})
        self.assertEqual(operations._frame_pose_key(event), operations._frame_pose_key(near))
        inline = operations.replace_event(event, text=event.text + r'{\fs20}B')
        plain = operations.replace_event(event, text=event.text + 'B')
        self.assertNotEqual(operations._frame_pose_key(inline), operations._frame_pose_key(plain))

    def test_state_key_reads_resolved_cache_without_mutating_or_parsing(self):
        event = source()
        state = {'number': 1.123456789, 'clip': ('m', 1.123456789, 2.),
                 'name': 'A', '_scratch': 'private'}
        event = replace(event, state=state); before = deepcopy(vars(event)); omit = {'name'}
        self.assertEqual(operations.state_key(event, omit),
                         (('clip', ('m', 1.123457, 2.)), ('number', 1.123457)))
        self.assertEqual(omit, {'name'})
        self.assertEqual(operations.state_key(event, set()), operations.state_key(event))
        self.assertEqual(vars(event), before)
        empty = replace(event, state={})
        self.assertEqual(operations.state_key(empty), ())
        self.assertEqual(empty.state, {})
        first = replace(event, state={'fs': .0000012345})
        second = replace(first, state={'fs': .0000014321})
        self.assertEqual(operations.state_key(first), operations.state_key(second))
        self.assertNotEqual(operations._frame_pose_key(first), operations._frame_pose_key(second))

    def test_cold_and_installed_operation_and_owned_uninstall(self):
        code = r'''
from pathlib import Path
from dataclasses import replace
from _simplify_ass import event_operations as o
from _simplify_ass import subtitle_document as d
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
raw='[Events]\n'+r'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\fs40}A'+'\n'
event=next(iter(d._resolve_document_state(d.parse_subtitle_document(raw)).events.values()))
read=o.event_evaluation(event)
assert read.formatting is event.state and read.continuation is event.continuation
edited=o.replace_event(event,text=r'{\fs20}B')
assert edited.state['fs']==20. and event.state['fs']==40.
assert o.replace_event(event,state={}).continuation==o.OverrideContinuation()
assert dict(o.state_key(event))['fs']==40.
assert 'fs' not in dict(o.state_key(event,{'fs'}))
assert o.state_key(replace(event,state={}))==()
assert 'simplify_ass' not in sys.modules
import simplify_ass as e
assert Path(o.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/event_operations.py'
for name in ('event_evaluation','replace_event','_frame_pose_key','state_key'):assert getattr(e,name) is getattr(o,name)
import py_compile
py_compile.compile(o.__file__,doraise=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            result = child(code, unrelated, ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            owner = load_installer()
            _, tools = owner.install(ROOT, root/'installed tools with spaces', individual_launchers=False)
            result = child(code, unrelated, tools)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            user = tools/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(root/'installed tools with spaces')
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((tools/'_simplify_ass/event_operations.py').exists())
            self.assertFalse(any((tools/'_simplify_ass').rglob('event_operations*.pyc')))


if __name__ == '__main__':
    unittest.main()
