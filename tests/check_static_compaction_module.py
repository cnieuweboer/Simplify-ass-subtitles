"""Compaction keeps its two evidence boundaries after module delivery."""
import test_paths
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import get_type_hints
import pickle
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import static_compaction as compaction
from check_windows_installer import ROOT, load_installer
from lyric_layer_fixtures import HEADER, event

NAMES = ('_finished_static_key', '_join_finished_static_headers', 'compact_static_overrides')


def caption(text='Caption', tags=r'\fs40\fscx100\fsp0'):
    document = engine._resolve_document_state(
        engine.parse_subtitle_document(HEADER + event(text, 100, 3, (1, 4), tags)))
    return next(iter(document.events.values()))


class StaticCompactionModuleChecks(unittest.TestCase):
    def test_canonical_functions_types_and_old_root_lookup(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(compaction, name))
            get_type_hints(getattr(compaction, name))
            self.assertIs(pickle.loads(pickle.dumps(getattr(compaction, name))),
                          getattr(compaction, name))
        self.assertIs(compaction.Event, engine.Event)
        self.assertIs(compaction.StaticSpanSignature, engine.StaticSpanSignature)
        self.assertIs(compaction.OverrideContinuation, engine.OverrideContinuation)
        self.assertIs(pickle.loads(b'csimplify_ass\ncompact_static_overrides\n.'),
                      compaction.compact_static_overrides)

    def test_final_successor_borrows_document_and_preserves_proved_evidence(self):
        original = caption()
        original = replace(original, evidence=engine.EventEvidence(
            original_contour_points=((1., 2.), (3., 4.)), opaque_spans=((1., 4.),),
            frame_pose_intervals=engine._frame_pose_intervals(original)))
        before = deepcopy(vars(original))
        out = compaction.compact_static_overrides([original], 0, final=True)[0]
        self.assertLess(len(out.text), len(original.text))
        self.assertEqual(out.fields()[:-1], original.fields()[:-1])
        self.assertEqual(compaction._finished_static_key(out), compaction._finished_static_key(original))
        for name in ('styles', 'measurement', 'evidence'):
            self.assertIs(getattr(out, name), getattr(original, name))
        self.assertIsNot(out.state, original.state)
        self.assertEqual(vars(original), before)
        self.assertIs(compaction.compact_static_overrides([out], 0, final=True)[0], out)

    def test_early_serialization_does_not_extend_historical_contour_or_opacity(self):
        original = caption()
        support = engine._frame_pose_intervals(original)
        original = replace(original, evidence=engine.EventEvidence(
            original_contour_points=((1., 2.),), opaque_spans=((1., 4.),),
            frame_pose_intervals=support))
        before = deepcopy(vars(original))
        out = compaction.compact_static_overrides([original], 0)[0]
        self.assertNotEqual(out.text, original.text)
        self.assertIsNone(out.evidence.original_contour_points)
        self.assertIsNone(out.evidence.opaque_spans)
        self.assertEqual(out.evidence.frame_pose_intervals, support)
        self.assertIs(out.measurement, original.measurement)
        self.assertIs(out.styles, original.styles)
        self.assertEqual(vars(original), before)

    def test_origins_and_blur_keep_distinct_early_and_final_contracts(self):
        for rotation in (0, 12):
            original = caption(tags=rf'\fs40\org(80,90)\frz{rotation}\blur4')
            before = deepcopy(vars(original))
            early = compaction.compact_static_overrides([original], 0)[0]
            final = compaction.compact_static_overrides([original], 0, final=True)[0]
            self.assertEqual('org' in early.state, rotation != 0)
            self.assertIn('org', final.state)
            self.assertEqual(early.state.get('blur', 0), 0)
            self.assertEqual(final.state.get('blur'), 4)
            self.assertEqual(vars(original), before)

    def test_complete_spans_keep_gradient_drawing_reset_and_continuation(self):
        for literal in (r'A{\1c&H123456&\fs40}B{\1c&HABCDEF&\fsp0}C',
                        r'A{\rLyric\xbord6\fs40}B{\bord2\fsp0}C',
                        r'{\p1}m 0 0 l 50 0 50 50{\p0\fs40}Text',
                        r'A{\fs+2\fs+3\fsp0}B'):
            with self.subTest(literal=literal):
                original = caption(literal); before = deepcopy(vars(original))
                out = compaction.compact_static_overrides([original], 0, final=True)[0]
                self.assertEqual(compaction._finished_static_key(out),
                                 compaction._finished_static_key(original))
                self.assertEqual(engine.OVERRIDE_RE.sub('', out.text),
                                 engine.OVERRIDE_RE.sub('', original.text))
                self.assertEqual(out.fields()[:-1], original.fields()[:-1])
                self.assertEqual(vars(original), before)

    def test_unknown_syntax_live_effects_comments_and_list_order_remain_protected(self):
        items = [caption(tags=tag) for tag in (
            r'\t(0,1000,\1c&H123456&)\fs40', r'\fad(100,100)\fs40',
            r'\kf100\fs40', r'\fe128\fs40')]
        items += [caption(r'{authored note}Caption'), replace(caption(), kind='Comment')]
        before = [deepcopy(vars(e)) for e in items]
        out = compaction.compact_static_overrides(items, 0, final=True)
        self.assertIsNot(out, items)
        self.assertEqual(len(out), len(items))
        self.assertTrue(all(a is b for a, b in zip(items, out)))
        self.assertEqual([vars(e) for e in items], before)
        self.assertIsNone(compaction._join_finished_static_headers(r'{note}A'))
        self.assertEqual(compaction._join_finished_static_headers(r'{\bord2}{\shad0}A'),
                         r'{\bord2\shad0}A')

    def test_cold_installed_processing_and_owned_removal(self):
        code = r'''
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from _simplify_ass import static_compaction as c, subtitle_document as d, event_model as model
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
raw='[Script Info]\nWrapStyle: 2\n[Events]\n'
raw+='Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,'+r'{\pos(100,100)\blur0}{\shad0}Caption'+'\n'
original=next(iter(d._resolve_document_state(d.parse_subtitle_document(raw)).events.values()))
original=replace(original,evidence=model.EventEvidence(opaque_spans=((1.,4.),)))
before=deepcopy(vars(original))
final=c.compact_static_overrides([original],0,final=True)[0]
early=c.compact_static_overrides([original],0)[0]
assert len(final.text)<len(original.text) and early.text!=original.text
assert final.evidence is original.evidence and early.evidence.opaque_spans is None
assert c._finished_static_key(final)==c._finished_static_key(original)
assert c.compact_static_overrides([final],0,final=True)[0] is final
assert vars(original)==before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as e
assert Path(c.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/static_compaction.py'
for name in ('_finished_static_key','_join_finished_static_headers','compact_static_overrides'):
 assert getattr(e,name) is getattr(c,name)
import py_compile
py_compile.compile(c.__file__,doraise=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            owner = load_installer(); target = root/'installed tools with spaces'
            _, installed = owner.install(ROOT, target, individual_launchers=False)
            for tools in (ROOT, installed):
                result = subprocess.run([sys.executable, '-I', '-c',
                    'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + code],
                    cwd=unrelated, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((installed/'_simplify_ass/static_compaction.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('static_compaction*.pyc')))


if __name__ == '__main__':
    unittest.main()
