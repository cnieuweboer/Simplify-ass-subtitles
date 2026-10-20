"""Frame-exit echoes preserve source proof, paint, ordering and cache ownership."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
import pickle
import random
import subprocess
import sys
import tempfile
from typing import get_type_hints
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import frame_echoes as echoes
from check_windows_installer import ROOT, load_installer
from frame_echo_test_helpers import add_tags, echo_events, moving_sources
from _simplify_ass.event_operations import replace_event

RECORDS = ('FrameEchoContext', 'FrameEchoFamily', 'FrameEchoFrame', 'FrameEchoHold', 'FrameEchoPaintProfile')
FUNCTIONS = ('_index_frame_echo_families', '_frame_echo_follows_motion', '_replace_frame_echo',
             '_recorded_frame_echo_motion', '_frame_echo_is_exit', '_frame_echo_candidates',
             '_isolated_frame_echo_times', '_blocked_frame_echo_times', '_prepare_frame_echo_family',
             '_profile_frame_echo', '_match_flattened_frame_echo', '_advance_flattened_frame_echo',
             '_frame_echo_paint_profile', '_match_stacked_frame_echo', '_collapse_frame_echo_family',
             'collapse_frame_text_echoes')

# Embed the fixture builder so installed children cannot import repository tests.
COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import frame_echoes as b
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
for flat, expected in ((False, 5), (True, 2)):
    events = echo_events(flat)
    before = deepcopy([vars(e) for e in events])
    output, count = b.collapse_frame_text_echoes(events, .16)
    assert count == expected and output is not events
    caption = output[-1]
    assert get_pos(caption.text) == (500., 100.) and caption.row == 8 and caption.lyric
    assert caption.state['1c'] == 'FFFFFF' and caption.layer == ('5' if flat else '0')
    assert [vars(e) for e in events] == before
long = echo_events(True, duration=.4)
assert b.collapse_frame_text_echoes(long, .16) == (long, 0)
originals = moving_sources(long, endpoint=450)
before = deepcopy({key: vars(value) for key, value in originals.items()})
assert b.collapse_frame_text_echoes(long, .16, source_events=originals)[1] == 2
assert {key: vars(value) for key, value in originals.items()} == before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as engine
assert engine.collapse_frame_text_echoes is b.collapse_frame_text_echoes
assert engine.FrameEchoContext is b.FrameEchoContext
assert Path(b.__file__).resolve() == Path(engine.__file__).resolve().parent/'_simplify_ass/frame_echoes.py'
import py_compile
py_compile.compile(b.__file__, doraise=True)
'''
COLD_CODE = Path(__file__).with_name('frame_echo_test_helpers.py').read_text() + COLD_CHECKS


def snapshot(events):
    return deepcopy([vars(event) for event in events])


def replacements(output, originals):
    return [event for event in output if not any(event is source for source in originals)]


class FrameEchoModuleChecks(unittest.TestCase):
    def test_canonical_aliases_annotations_and_historical_root_lookup(self):
        for name in RECORDS + FUNCTIONS:
            value = getattr(echoes, name)
            self.assertIs(getattr(engine, name), value)
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n' + name + '\n.').encode()), value)
            self.assertIs(pickle.loads(pickle.dumps(value)), value)
        self.assertIs(echoes.Event, engine.Event)
        self.assertEqual(echoes.collapse_frame_text_echoes.__kwdefaults__, {'source_events': None})

    def test_all_five_records_are_shallow_frozen_and_borrow_their_members(self):
        events = echo_events(); originals = moving_sources(events)
        frames = next(iter(echoes._index_frame_echo_families(events).values()))
        cache = {}; removed = set(); replacement_map = {}; omit = {'pos'}
        context = echoes.FrameEchoContext(.16, originals, omit, removed, replacement_map)
        family = echoes.FrameEchoFamily(frames, cache)
        members = frames[(1., 2.)]
        frame = echoes._profile_frame_echo((1., 2.), members, {(1., 2.)}, set())
        hold = echoes.FrameEchoHold(2., (500., 100.), members[-1])
        paint = echoes._frame_echo_paint_profile(context, frame)
        self.assertIs(context.source_events, originals)
        self.assertIs(context.omit, omit)
        self.assertIs(context.removed, removed)
        self.assertIs(context.replacements, replacement_map)
        self.assertIs(family.frames, frames)
        self.assertIs(family.moving_frames, cache)
        self.assertIs(frame.members, members)
        self.assertIs(hold.anchor, members[-1])
        self.assertTrue(all(any(event is original for original in members) for event in paint.stack))
        for record in (context, family, frame, hold, paint):
            with self.assertRaises(FrozenInstanceError):
                setattr(record, fields(record)[0].name, None)
            self.assertEqual(pickle.loads(pickle.dumps(record)), record)
        removed.add(7); cache[(2., 2.05)] = False
        self.assertEqual(context.removed, {7})
        self.assertIs(family.moving_frames[(2., 2.05)], False)

    def test_both_paths_and_chains_retain_anchor_paint_pose_timing_and_flags(self):
        for flat, per_frame in ((False, 5), (True, 2)):
            events = echo_events(flat, frames=3); before = snapshot(events)
            output, count = echoes.collapse_frame_text_echoes(events, .16)
            self.assertEqual(count, per_frame*3)
            self.assertEqual(len(output), len(events)-count)
            self.assertIsNot(output, events)
            captions = replacements(output, events)
            self.assertEqual(len(captions), 3)
            for caption in captions:
                sources = [e for e in events if (e.start_s, e.end_s) == (caption.start_s, caption.end_s)]
                self.assertEqual(echoes.get_pos(caption.text), (500., 100.))
                self.assertEqual(caption.state['1c'], 'FFFFFF')
                self.assertEqual(caption.state['3c'], '000000')
                self.assertEqual(caption.state.get('1a', 0), 0)
                self.assertGreater(caption.state['bord'], 0)
                self.assertLessEqual(caption.state['bord'], 2)
                self.assertEqual(caption.layer, '5' if flat else '0')
                self.assertEqual(caption.source_index, min(e.source_index for e in sources))
                self.assertEqual((caption.row, caption.lyric), (8, True))
                self.assertIs(caption.measurement, sources[0].measurement)
            self.assertEqual(snapshot(events), before)

    def test_application_preserves_supplied_list_order_and_retained_identity(self):
        for flat, count in ((False, 5), (True, 2)):
            for order in ('original', 'reverse', 'shuffle'):
                events = echo_events(flat)
                if order == 'reverse': events.reverse()
                if order == 'shuffle': random.Random(233).shuffle(events)
                before = snapshot(events)
                output, removed = echoes.collapse_frame_text_echoes(events, .16)
                self.assertEqual(removed, count)
                chosen = min(e.source_index for e in events if e.start_s == 2.)
                expected = [e.source_index for e in events if e.start_s < 2. or e.source_index == chosen]
                self.assertEqual([e.source_index for e in output], expected)
                for event in output:
                    if event.start_s < 2.: self.assertTrue(any(event is source for source in events))
                self.assertEqual(snapshot(events), before)

    def test_long_frames_require_original_motion_and_compatible_source_lifetimes(self):
        for flat, expected in ((False, 5), (True, 2)):
            events = echo_events(flat, duration=.4)
            for originals in (None, {}):
                self.assertEqual(echoes.collapse_frame_text_echoes(events, .16, source_events=originals), (events, 0))
            originals = moving_sources(events, endpoint=450)
            before = deepcopy({key: vars(value) for key, value in originals.items()})
            self.assertEqual(echoes.collapse_frame_text_echoes(events, .16, source_events=originals)[1], expected)
            self.assertEqual({key: vars(value) for key, value in originals.items()}, before)
            self.assertEqual(echoes.collapse_frame_text_echoes(events, .16, source_events=moving_sources(events, endpoint=451)), (events, 0))
            for variant in ('missing', 'late-start', 'early-end', 'reverse', 'inline'):
                changed = dict(originals); key = next(iter(changed)); source = changed[key]
                if variant == 'missing': del changed[key]
                if variant == 'late-start': changed[key] = replace(source, start_s=2.01)
                if variant == 'early-end': changed[key] = replace(source, end_s=2.39)
                if variant == 'reverse': changed[key] = replace_event(source, text=r'{\move(100,100,0,100)}Hello')
                if variant == 'inline': changed[key] = replace_event(source, text=source.text + r'{\fnOther}X')
                with self.subTest(flat=flat, variant=variant):
                    self.assertEqual(echoes.collapse_frame_text_echoes(events, .16, source_events=changed), (events, 0))

    def test_nonuniform_paint_layout_and_incomplete_offset_stacks_are_retained(self):
        for flat in (False, True):
            for tags in (r'\1c&H123456&', r'\fs20', r'\clip(0,0,100,100)'):
                events = echo_events(flat)
                index = next(i for i, e in enumerate(events) if e.start_s == 2.)
                events[index] = add_tags(events[index], tags)
                before = snapshot(events)
                self.assertEqual(echoes.collapse_frame_text_echoes(events, .16), (events, 0))
                self.assertEqual(snapshot(events), before)
            events = echo_events(flat, offsets=2)
            self.assertEqual(echoes.collapse_frame_text_echoes(events, .16), (events, 0))
        for variant in ('missing', 'duplicate'):
            events = echo_events()
            if variant == 'missing': events.pop()
            else: events.append(replace(events[-1], source_index=10000))
            self.assertEqual(echoes.collapse_frame_text_echoes(events, .16), (events, 0))

    def test_flattened_holds_reject_overlap_and_persistent_label_ambiguity(self):
        events = echo_events(True)
        overlap = replace_event(events[0], source_index=10000, start='0:00:01.50', start_s=1.5,
                                end='0:00:02.03', end_s=2.03, text=r'{\pos(800,100)\fs40}Hello')
        ambiguous = events + [overlap]
        self.assertEqual(echoes.collapse_frame_text_echoes(ambiguous, .16), (ambiguous, 0))
        persistent = [replace(e, source_index=10000+i, start='0:00:02.05', start_s=2.05,
                              end='0:00:04.00', end_s=4.) for i, e in enumerate(events) if e.start_s == 2.]
        ambiguous = events + persistent
        self.assertEqual(echoes.collapse_frame_text_echoes(ambiguous, .16), (ambiguous, 0))
        gap = [replace(e, start_s=e.start_s+.001, end_s=e.end_s+.001) if e.start_s == 2. else e for e in events]
        self.assertEqual(echoes.collapse_frame_text_echoes(gap, .16), (gap, 0))

    def test_exit_contour_animation_does_not_replace_the_preceding_paint(self):
        events = [add_tags(e, r'\bord8') if e.start_s == 2. else e for e in echo_events()]
        output, removed = echoes.collapse_frame_text_echoes(events, .16)
        self.assertEqual(removed, 5)
        caption = replacements(output, events)[0]
        self.assertEqual(caption.state['1c'], 'FFFFFF')
        self.assertEqual(caption.state['3c'], '000000')
        self.assertLessEqual(caption.state['bord'], 2)
        self.assertEqual(caption.state.get('1a', 0), 0)

    def test_positive_and_negative_motion_cache_entries_are_family_local(self):
        events = echo_events(True, duration=.4); originals = moving_sources(events)
        frames = next(iter(echoes._index_frame_echo_families(events).values()))
        family = echoes.FrameEchoFamily(frames, {})
        context = echoes.FrameEchoContext(.16, originals, set(), set(), {})
        with patch.object(echoes, 'event_override_tokens', wraps=echoes.event_override_tokens) as read:
            self.assertTrue(echoes._recorded_frame_echo_motion(context, family, (2., 2.4)))
            calls = read.call_count; self.assertEqual(calls, 3)
            self.assertTrue(echoes._recorded_frame_echo_motion(context, family, (2., 2.4)))
            self.assertEqual(read.call_count, calls)
        invalid = moving_sources(events, endpoint=451)
        family = echoes.FrameEchoFamily(frames, {})
        context = echoes.FrameEchoContext(.16, invalid, set(), set(), {})
        with patch.object(echoes, 'event_override_tokens', wraps=echoes.event_override_tokens) as read:
            self.assertFalse(echoes._recorded_frame_echo_motion(context, family, (2., 2.4)))
            calls = read.call_count; self.assertGreater(calls, 0)
            self.assertFalse(echoes._recorded_frame_echo_motion(context, family, (2., 2.4)))
            self.assertEqual(read.call_count, calls)
        self.assertTrue(echoes._recorded_frame_echo_motion(
            echoes.FrameEchoContext(.16, originals, set(), set(), {}), echoes.FrameEchoFamily(frames, {}), (2., 2.4)))

    def test_repeated_invocations_keep_retained_objects_without_sharing_replacements(self):
        events = echo_events(True); before = snapshot(events)
        first, count = echoes.collapse_frame_text_echoes(events, .16)
        second, again = echoes.collapse_frame_text_echoes(events, .16)
        self.assertEqual(count, again)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIs(first[0], events[0])
        self.assertIs(second[0], events[0])
        self.assertIsNot(replacements(first, events)[0], replacements(second, events)[0])
        self.assertEqual(snapshot(events), before)
        output, count = echoes.collapse_frame_text_echoes([], .16)
        self.assertEqual((output, count), ([], 0))

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
            self.assertFalse((installed/'_simplify_ass/frame_echoes.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('frame_echoes*.pyc')))


if __name__ == '__main__':
    unittest.main()
