"""Static identity and ordered merging retain parser, stage and evidence contracts."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import get_type_hints
from unittest.mock import patch
import pickle
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import static_objects as objects
from check_windows_installer import load_installer, ROOT

NAMES = ('StaticSpanSignature', 'geometry_key', 'static_object_key',
         '_merge_static_phase_round', 'merge_static_timed_copies')
PREFIX = r'{\pos(100,100)\q2\bord0\shad0}'


def events(rows=None):
    rows = rows if rows is not None else [('A', 1., 2., '0'), ('A', 2., 3., '0')]
    text = '[Script Info]\nWrapStyle: 2\n[Events]\n'
    for literal, start, end, layer in rows:
        text += (f'Dialogue: {layer},{engine.format_time(start)},{engine.format_time(end)},Default,,0,0,0,,'
                 + PREFIX + literal + '\n')
    return list(engine._resolve_document_state(engine.parse_subtitle_document(text)).events.values())


def key(event):
    return objects.static_object_key(event, event.styles)


def merge(items, **kwargs):
    return objects.merge_static_timed_copies(items, items[0].styles if items else {}, **kwargs)


def child(code, cwd, tools):
    return subprocess.run([sys.executable, '-I', '-c',
        'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + code],
        cwd=cwd, capture_output=True, text=True)


class StaticObjectsModuleChecks(unittest.TestCase):
    def test_canonical_aliases_frozen_signature_and_pickle_lookup(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(objects, name))
            get_type_hints(getattr(objects, name))
        self.assertIs(objects.Event, engine.Event)
        self.assertIs(objects.FontMetrics, engine.FontMetrics)
        self.assertIs(objects.OverrideContinuation, engine.OverrideContinuation)
        signature = key(events()[0])[-1][0][0]
        self.assertIs(type(signature), engine.StaticSpanSignature)
        with self.assertRaises(FrozenInstanceError):
            signature.formatting = ()
        self.assertEqual(pickle.loads(pickle.dumps(signature)), signature)
        self.assertIs(pickle.loads(b'csimplify_ass\nStaticSpanSignature\n.'), objects.StaticSpanSignature)
        self.assertEqual(objects.StaticSpanSignature.__module__, objects.__name__)

    def test_span_and_vector_identity_preserve_history_paint_and_inputs(self):
        source = events()[0]; before = deepcopy(vars(source))
        reset = engine.replace_event(source, text=source.text.replace('{', r'{\r', 1))
        self.assertEqual(source.state, reset.state)
        self.assertNotEqual(key(source), key(reset))
        whole = engine.replace_event(source, text=PREFIX+'AB')
        split = engine.replace_event(source, text=PREFIX+'A{}B')
        self.assertEqual(key(whole), key(split))
        gradient = engine.replace_event(source, text=PREFIX+r'A{\1c&H123456&}B')
        self.assertNotEqual(key(whole), key(gradient))
        self.assertEqual(len(key(gradient)[-1]), 2)
        self.assertEqual(objects.geometry_key(r'{\pos(3,4)}M 0.0 +0 L 10.00 2'),
                         ('m', 0., 0., 'l', 10., 2.))
        drawing = engine.replace_event(source, text=PREFIX+r'{\p1}M 0.0 +0 L 10.00 2')
        equivalent = engine.replace_event(source, text=PREFIX+r'{\p1}m 0 0 l 10 2')
        self.assertEqual(key(drawing), key(equivalent))
        self.assertEqual(vars(source), before)

    def test_static_admission_keeps_live_effects_and_collision_placement_out(self):
        source = events()[0]
        for tag in (r'\t(\fs50)', r'\move(1,2,3,4)', r'\fad(100,100)', r'\kf20'):
            with self.subTest(tag=tag):
                self.assertIsNone(key(engine.replace_event(source, text=PREFIX+'{'+tag+'}A')))
        for changes in ({'kind': 'Comment'}, {'effect': 'Scroll up;1;2;3'}, {'end_s': 1.}):
            self.assertIsNone(key(replace(source, **changes)))
        unpositioned = engine.replace_event(source, text='A')
        self.assertIsNone(key(unpositioned))
        self.assertIsNotNone(objects.static_object_key(unpositioned, unpositioned.styles,
                                                      allow_unpositioned=True))

    def test_join_borrows_caches_and_hands_off_only_actual_source_support(self):
        items = [replace(e, evidence=engine.EventEvidence(
            original_contour_points=((1., 2.), (3., 4.)), opaque_spans=((e.start_s, e.end_s),),
            frame_pose_intervals=engine._frame_pose_intervals(e))) for e in events()]
        before = [deepcopy(vars(e)) for e in items]
        out, count = merge(items)
        self.assertEqual((count, len(out), out[0].start_s, out[0].end_s), (1, 1, 1., 3.))
        for name in ('state', 'defaults', 'styles', 'measurement', 'continuation'):
            self.assertIs(getattr(out[0], name), getattr(items[0], name))
        self.assertEqual(out[0].evidence.opaque_spans, ((1., 2.),))
        self.assertEqual(out[0].evidence.original_contour_points, items[0].evidence.original_contour_points)
        self.assertEqual(out[0].evidence.frame_pose_intervals,
                         tuple(e.evidence.frame_pose_intervals[0] for e in items))
        self.assertEqual(merge(out), (out, 0))
        self.assertEqual([vars(e) for e in items], before)

    def test_gap_overlap_and_paint_changes_remain_distinct(self):
        source = events()
        variants = [engine.replace_event(source[1], start=engine.format_time(2.01), start_s=2.01),
                    engine.replace_event(source[1], start=engine.format_time(1.99), start_s=1.99),
                    engine.replace_event(source[1], text=PREFIX+r'{\1c&HFEFFFF&}A')]
        for second in variants:
            with self.subTest(second=second.text, start=second.start):
                out, count = merge([source[0], second])
                self.assertEqual(count, 0)
                self.assertEqual([vars(e) for e in out], [vars(e) for e in (source[0], second)])
        copies = [*source, replace(source[1], source_index=99)]
        self.assertEqual(merge(copies), (copies, 0))
        gradient = events([(r'A{\1c&H123456&}B', 1., 2., '0'),
                           (r'A{\1c&H123456&}B', 2., 3., '0')])
        out, count = merge(gradient)
        self.assertEqual(count, 1)
        self.assertEqual(out[0].text, gradient[0].text)

    def test_actual_slots_and_pending_row_roles_are_preserved(self):
        first, last = events()
        peer = engine.replace_event(first, text=PREFIX+'Peer', source_index=99)
        ordered = [first, peer, last]; before = [deepcopy(vars(e)) for e in ordered]
        finished, count = merge(ordered, text_only=True)
        self.assertEqual(count, 1)
        self.assertEqual(vars(finished[1]), vars(peer))
        pending = [replace(first, row=3, lyric=True), peer, replace(last, row=3, lyric=True)]
        roles = {first.source_index, last.source_index}; roles_before = roles.copy()
        self.assertEqual(merge(pending, row_sources=roles), (pending, 0))
        self.assertEqual(roles, roles_before)
        different_row = [replace(first, row=3, lyric=True), replace(last, row=4, lyric=True)]
        self.assertEqual(merge(different_row, row_sources=roles), (different_row, 0))
        live = engine.replace_event(peer, start=last.start, start_s=last.start_s,
                                    end=last.end, end_s=last.end_s)
        colliding = [replace(e, source_index=7) for e in (first, live, last)]
        self.assertEqual(merge(colliding, text_only=True), (colliding, 0))
        self.assertEqual([vars(e) for e in ordered], before)

    def test_numeric_layer_aliases_and_malformed_peers_keep_ordering_rules(self):
        for layer in ('00', '+0', '-0'):
            items = events([('A', 1., 2., '0'), ('A', 2., 3., layer)])
            self.assertEqual(merge(items)[1], 1)
        first, last = events()
        peer = engine.replace_event(first, text=PREFIX+'Peer', layer='bad',
                                    start=last.start, start_s=last.start_s,
                                    end=last.end, end_s=last.end_s)
        self.assertEqual(merge([first, peer, last], text_only=True), ([first, peer, last], 0))

    def test_bounds_use_borrowed_metrics_and_no_persistent_round_cache(self):
        first, last = events()
        peer = engine.replace_event(first, text=PREFIX.replace('100,100', '500,100')+'Peer',
                                    start=last.start, start_s=last.start_s,
                                    end=last.end, end_s=last.end_s, source_index=99)
        items = [first, peer, last]; before = [deepcopy(vars(e)) for e in items]
        owner = object(); seen = []
        def bounds(event, metric):
            seen.append(metric)
            x, y = objects.get_pos(event.text)
            return x-10., y-10., x+10., y+10.
        with patch.object(objects, 'caption_bounds', bounds):
            out, count = objects._merge_static_phase_round(items, first.styles, owner,
                                                           text_only=True, row_sources=None)
        self.assertEqual(count, 1)
        self.assertTrue(seen)
        self.assertTrue(all(metric is owner for metric in seen))
        with patch.object(objects, 'caption_bounds', return_value=None):
            self.assertEqual(objects._merge_static_phase_round(items, first.styles, owner,
                             text_only=True, row_sources=None), (items, 0))
        self.assertEqual([vars(e) for e in items], before)

    def test_cold_installed_processing_pickle_and_owned_uninstall(self):
        code = r'''
from pathlib import Path
from copy import deepcopy
from dataclasses import FrozenInstanceError
import pickle
from _simplify_ass import static_objects as o, subtitle_document as d
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
raw='[Script Info]\nWrapStyle: 2\n[Events]\n'
for start,end in [('01.00','02.00'),('02.00','03.00')]:
 raw+=f'Dialogue: 0,0:00:{start},0:00:{end},Default,,0,0,0,,'+r'{\pos(100,100)\q2\bord0\shad0}A'+'\n'
items=list(d._resolve_document_state(d.parse_subtitle_document(raw)).events.values())
before=[deepcopy(vars(e)) for e in items]
signature=o.static_object_key(items[0],items[0].styles)[-1][0][0]
try:signature.formatting=()
except FrozenInstanceError:pass
else:raise AssertionError('Mutable static signature')
assert pickle.loads(pickle.dumps(signature))==signature
assert o.geometry_key('M 0.0 +0 L 10.00 2')==('m',0.,0.,'l',10.,2.)
out,n=o.merge_static_timed_copies(items,items[0].styles)
assert n==1 and len(out)==1 and out[0].start_s==1. and out[0].end_s==3.
assert out[0].state is items[0].state and out[0].continuation is items[0].continuation
assert o.merge_static_timed_copies(out,items[0].styles)==(out,0)
assert [vars(e) for e in items]==before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as e
assert Path(o.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/static_objects.py'
for name in ('StaticSpanSignature','geometry_key','static_object_key','_merge_static_phase_round','merge_static_timed_copies'):assert getattr(e,name) is getattr(o,name)
assert pickle.loads(b'csimplify_ass\nStaticSpanSignature\n.') is o.StaticSpanSignature
assert o.StaticSpanSignature.__module__==o.__name__
import py_compile
py_compile.compile(o.__file__,doraise=True)
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
            self.assertFalse((tools/'_simplify_ass/static_objects.py').exists())
            self.assertFalse(any((tools/'_simplify_ass').rglob('static_objects*.pyc')))


if __name__ == '__main__':
    unittest.main()
