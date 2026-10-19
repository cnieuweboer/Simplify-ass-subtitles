"""Scrolling proofs retain caller-owned data, strict limits and private delivery."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints
import pickle
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import scrolling_blocks as blocks
from check_windows_installer import ROOT, load_installer

NAMES = ('ScrollingBlockMatch', 'collect_scrolling_tracks', 'scroll_track_crosses_canvas', '_scrolling_pose_is_translational', '_profile_scrolling_track', '_scrolling_profile_position', '_scrolling_profiles_are_coherent', '_scrolling_profiles_are_distinct', '_match_scrolling_block', 'drop_overloaded_scrolling_blocks')

class Metric:
 available=True
 def __init__(self):self.calls=[];self.face=SimpleNamespace(cmap={ord(c):ord(c) for c in 'OneTwoThree'})
 def matching_face(self,*args):self.calls.append(args);return self.face
 def ass_em_scale(self,face):return 1.
 def measure(self,face,text,kerning):return 512.*len(text)
 def line_ink_metrics(self,*args,**kwargs):return None

COLD_CODE = r'''
import sys
from copy import deepcopy
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import pickle
from _simplify_ass import scrolling_blocks as b, subtitle_document as d
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
class Metric:
 available=True
 def __init__(self):self.calls=[];self.face=SimpleNamespace(cmap={ord(c):ord(c) for c in 'OneTwoThree'})
 def matching_face(self,*args):self.calls.append(args);return self.face
 def ass_em_scale(self,face):return 1.
 def measure(self,face,text,kerning):return 512.*len(text)
 def line_ink_metrics(self,*args,**kwargs):return None
raw='[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n[Events]\n'
for i in range(40):
 for text,y in [('One',300),('Two',550),('Three',800)]:
  raw+=f'Dialogue: 0,{d.format_time(1+i*.05)},{d.format_time(1+(i+1)*.05)},Default,,0,0,0,,'+'{'+rf'\fnTest\fs40\an5\bord0\shad0\pos(400,{y+900*i/39:.6f})'+'}'+text+'\n'
events=list(d._resolve_document_state(d.parse_subtitle_document(raw)).events.values());before=[deepcopy(vars(e)) for e in events]
metric=Metric();tracks=b.collect_scrolling_tracks(events,1920,1080)
assert len(tracks)==3 and all(len(t)==40 for t in tracks)
out,report=b.drop_overloaded_scrolling_blocks(events,1920,1080,metric,concurrency_limit=0)
assert len(out)==120 and all(a is c for a,c in zip(out,events))
assert len(report)==1 and report[0]['action']=='retained' and report[0]['peak_concurrent']==3
removed,reports=b.drop_overloaded_scrolling_blocks(events,1920,1080,metric,concurrency_limit=2)
assert removed==[] and reports[0]['action']=='removed' and metric.calls
assert b.drop_overloaded_scrolling_blocks(events,1920,1080,None,concurrency_limit=2)==(events,[])
assert [vars(e) for e in events]==before
indices=[1,2,3];match=b.ScrollingBlockMatch(indices,1.,2.)
assert match.indices is indices
try:match.start=0.
except FrozenInstanceError:pass
else:raise AssertionError('Mutable match record')
assert pickle.loads(pickle.dumps(match))==match
class Unreadable:
 def __iter__(self):raise AssertionError('Consumed input before rejecting negative limit')
try:b.drop_overloaded_scrolling_blocks(Unreadable(),0,0,None,concurrency_limit=-1)
except ValueError:pass
else:raise AssertionError('Negative limit admitted')
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as engine
for name in ['ScrollingBlockMatch', 'collect_scrolling_tracks', 'scroll_track_crosses_canvas', '_scrolling_pose_is_translational', '_profile_scrolling_track', '_scrolling_profile_position', '_scrolling_profiles_are_coherent', '_scrolling_profiles_are_distinct', '_match_scrolling_block', 'drop_overloaded_scrolling_blocks']:assert getattr(engine,name) is getattr(b,name)
assert pickle.loads(b'csimplify_ass\nScrollingBlockMatch\n.') is b.ScrollingBlockMatch

from pathlib import Path
import py_compile
assert Path(b.__file__).resolve()==Path(engine.__file__).resolve().parent/'_simplify_ass/scrolling_blocks.py'
py_compile.compile(b.__file__,doraise=True)
'''


def scrolling_events():
    raw='[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n[Events]\n'
    for i in range(40):
     for text,y in [('One',300),('Two',550),('Three',800)]:
      raw+=f'Dialogue: 0,{engine.format_time(1+i*.05)},{engine.format_time(1+(i+1)*.05)},Default,,0,0,0,,'+'{'+rf'\fnTest\fs40\an5\bord0\shad0\pos(400,{y+900*i/39:.6f})'+'}'+text+'\n'
    return list(engine._resolve_document_state(engine.parse_subtitle_document(raw)).events.values())


class ScrollingBlocksModuleChecks(unittest.TestCase):
    def test_direct_aliases_annotations_and_old_root_pickle_lookup(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(blocks, name))
            get_type_hints(getattr(blocks, name))
        self.assertIs(blocks.Event, engine.Event)
        self.assertIs(blocks.FontMetrics, engine.FontMetrics)
        self.assertIs(pickle.loads(b'csimplify_ass\nScrollingBlockMatch\n.'), blocks.ScrollingBlockMatch)
        self.assertEqual(blocks.drop_overloaded_scrolling_blocks.__kwdefaults__, {'concurrency_limit': 32})

    def test_match_record_is_shallow_frozen_and_contains_profile_indices(self):
        indices = [1, 3, 8]
        match = blocks.ScrollingBlockMatch(indices, 1., 2.)
        self.assertIs(match.indices, indices)
        with self.assertRaises(FrozenInstanceError):
            match.start = 0.
        indices.append(9)
        self.assertEqual(match.indices, [1, 3, 8, 9])
        self.assertEqual(pickle.loads(pickle.dumps(match)), match)

    def test_strict_cap_zero_reporting_and_borrowed_inputs(self):
        events = scrolling_events(); before = deepcopy(events)
        metric = Metric()
        for limit, removed in ((0, False), (3, False), (2, True), (32, False)):
            out, report = blocks.drop_overloaded_scrolling_blocks(events, 1920, 1080, metric, concurrency_limit=limit)
            self.assertEqual(len(out), 0 if removed else 120)
            if not removed:
                self.assertIsNot(out, events)
                self.assertTrue(all(a is b for a, b in zip(events, out)))
            self.assertEqual(len(report), 1)
            self.assertEqual(report[0]['peak_concurrent'], 3)
            self.assertEqual(report[0]['concurrency_limit'], limit)
            self.assertEqual(report[0]['action'], 'removed' if removed else 'retained')
            self.assertEqual([t['text'] for t in report[0]['tracks']], ['One', 'Two', 'Three'])
        self.assertTrue(metric.calls)
        self.assertEqual(events, before)

    def test_three_spatial_voters_and_known_measured_edge_required(self):
        events = scrolling_events()
        tracks = blocks.collect_scrolling_tracks(events, 1920, 1080)
        self.assertEqual([len(t) for t in tracks], [40, 40, 40])
        self.assertEqual(blocks.drop_overloaded_scrolling_blocks(events, 1920, 1080, None, concurrency_limit=2), (events, []))
        two = [e for e in events if engine.OVERRIDE_RE.sub('', e.text) != 'Three']
        self.assertEqual(blocks.drop_overloaded_scrolling_blocks(two, 1920, 1080, Metric(), concurrency_limit=1), (two, []))

    def test_unrelated_captions_do_not_inflate_block_concurrency(self):
        events = scrolling_events()
        unrelated = [replace(events[0], source_index=10000+i, start_s=1., end_s=3.,
                             text=r'{\pos(100,100)}Independent') for i in range(40)]
        out, report = blocks.drop_overloaded_scrolling_blocks(events + unrelated, 1920, 1080, Metric(), concurrency_limit=3)
        self.assertEqual(report[0]['peak_concurrent'], 3)
        self.assertEqual(report[0]['action'], 'retained')
        self.assertTrue(all(a is b for a, b in zip(out, events + unrelated)))
        out, report = blocks.drop_overloaded_scrolling_blocks(events + unrelated, 1920, 1080, Metric(), concurrency_limit=2)
        self.assertEqual(out, unrelated)
        self.assertTrue(all(a is b for a, b in zip(out, unrelated)))
        # No confirmed-profile/removal buffers survive into the next call.
        self.assertEqual(blocks.drop_overloaded_scrolling_blocks(unrelated, 1920, 1080, Metric(), concurrency_limit=1), (unrelated, []))

    def test_negative_limit_rejected_before_reading_inputs(self):
        class Unreadable:
            def __iter__(self):
                raise AssertionError('Consumed invalid input')
        with self.assertRaises(ValueError):
            blocks.drop_overloaded_scrolling_blocks(Unreadable(), 0, 0, None, concurrency_limit=-1)

    def test_cold_source_and_installed_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            owner = load_installer(); target = root/'installed tools with spaces'
            _, installed = owner.install(ROOT, target, individual_launchers=False)
            for tools in (ROOT, installed):
                child = subprocess.run([sys.executable, '-I', '-c',
                    'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + COLD_CODE],
                    cwd=unrelated, capture_output=True, text=True)
                self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
            user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((installed/'_simplify_ass/scrolling_blocks.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('scrolling_blocks*.pyc')))


if __name__ == '__main__':
    unittest.main()
