"""Jitter module ownership, canonical records and pipeline/delivery handoffs."""
import test_paths
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import inspect
import io
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
from typing import get_type_hints
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import complete_line_jitter as jitter
from check_windows_installer import ROOT, load_installer
from complete_line_jitter_test_helpers import HEADER, jitter_inputs, jitter_text

RECORDS = ('JitterTextFamily', 'CompleteLineJitterResult')
FUNCTIONS = ('_index_complete_line_jitter', '_prove_complete_line_jitter',
             '_complete_line_jitter_families', '_complete_line_jitter_core_overlap',
             '_group_complete_line_jitter_stacks', '_render_complete_line_jitter',
             'flatten_complete_line_jitter')

COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import complete_line_jitter as j
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
for stacked, counts in ((False, (11, 0)), (True, (20, 1))):
    events, visible, styles = jitter_inputs(stacked=stacked, sentinel=True)
    before = deepcopy(([vars(e) for e in events], visible, styles))
    sources = {e.source_index:e for e in events}
    result = j.flatten_complete_line_jitter(events, visible, styles, source_events=sources)
    assert (result.frames, result.stacks) == counts
    assert len(result.events) == 2 and len(result.captions) == 1
    assert result.events[0] is result.captions[0] and result.events[-1] is events[-1]
    caption = result.captions[0]
    assert caption.start_s == 1. and caption.end_s == 1.48
    assert caption.state['1c'] == ('335577' if stacked else 'FFFFFF')
    assert caption.state['3c'] == '000000' and caption.state['bord'] == 1
    assert caption.measurement is events[0].measurement
    assert caption.row == 8 and caption.lyric and caption.evidence.frame_pose_intervals
    assert ([vars(e) for e in events], visible, styles) == before
    again = j.flatten_complete_line_jitter(result.events, visible, styles)
    assert again.frames == again.stacks == 0
    assert all(a is b for a,b in zip(again.events, result.events))
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as engine
assert engine.flatten_complete_line_jitter is j.flatten_complete_line_jitter
assert engine.CompleteLineJitterResult is j.CompleteLineJitterResult
assert Path(j.__file__).resolve() == Path(engine.__file__).resolve().parent/'_simplify_ass/complete_line_jitter.py'
import py_compile
py_compile.compile(j.__file__, doraise=True)
'''
COLD_CODE = Path(__file__).with_name('complete_line_jitter_test_helpers.py').read_text() + COLD_CHECKS


class CompleteLineJitterModuleChecks(unittest.TestCase):
    def test_canonical_aliases_resolved_annotations_and_historical_root_lookup(self):
        for name in RECORDS + FUNCTIONS:
            value = getattr(jitter, name)
            self.assertIs(getattr(engine, name), value)
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n' + name + '\n.').encode()), value)
            self.assertIs(pickle.loads(pickle.dumps(value)), value)
        self.assertIs(jitter.Event, engine.Event)
        signature = inspect.signature(jitter.flatten_complete_line_jitter)
        self.assertEqual(signature.parameters['max_piece_duration'].default, .16)
        self.assertIsNone(signature.parameters['source_events'].default)
        self.assertEqual(signature.parameters['source_events'].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_shallow_frozen_records_borrow_their_members(self):
        events, _, _ = jitter_inputs()
        family = jitter.JitterTextFamily(tuple(events), tuple(events), 1., 1.48, (960., 74.))
        captions = (events[0],)
        result = jitter.CompleteLineJitterResult(events, 11, 0, captions)
        self.assertIs(result.events, events)
        self.assertIs(result.captions, captions)
        self.assertIs(family.members[0], events[0])
        for record in (family, result):
            self.assertTrue(type(record).__dataclass_params__.frozen)
            name = fields(record)[0].name
            with self.assertRaises(FrozenInstanceError):
                setattr(record, name, getattr(record, name))
        result.events.append(events[0])
        self.assertEqual(len(events), 13)

    def test_caption_identity_paint_timing_flags_pose_support_and_input_immutability(self):
        for stacked, counts in ((False, (11, 0)), (True, (20, 1))):
            with self.subTest(stacked=stacked):
                events, visible, styles = jitter_inputs(stacked=stacked, sentinel=True)
                sources = {e.source_index:e for e in events}
                before = deepcopy(([vars(e) for e in events], visible, styles))
                original_states = [e.state for e in events]
                result = jitter.flatten_complete_line_jitter(events, visible, styles, source_events=sources)
                self.assertEqual((result.frames, result.stacks), counts)
                self.assertEqual(len(result.events), 2)
                caption = result.captions[0]
                self.assertIs(result.events[0], caption)
                self.assertIs(result.events[-1], events[-1])
                self.assertEqual(engine.OVERRIDE_RE.sub('', caption.text), 'A complete line')
                self.assertEqual((caption.start_s, caption.end_s, caption.source_index),
                                 (1., 1.48, min(e.source_index for e in events)))
                self.assertEqual((caption.row, caption.lyric), (8, True))
                self.assertEqual((caption.layer, caption.state['1c'], caption.state['3c'], caption.state['bord']),
                                 ('1' if stacked else '0', '335577' if stacked else 'FFFFFF', '000000', 1))
                self.assertIs(caption.measurement, events[0].measurement)
                self.assertTrue(caption.evidence.frame_pose_intervals)
                self.assertIn(engine.get_pos(caption.text), [engine.get_pos(e.text) for e in events[:-1]])
                self.assertEqual(([vars(e) for e in events], visible, styles), before)
                self.assertTrue(all(e.state is state for e,state in zip(events,original_states)))
                self.assertTrue(all(sources[e.source_index] is e for e in events))

    def test_original_source_refusals_do_not_accept_frozen_lookalikes(self):
        events, visible, styles = jitter_inputs()
        for change in (lambda e: replace(e, end_s=e.end_s+.01),
                       lambda e: engine.replace_event(e, text=e.text.replace('}', r'\t(\fs41)}', 1))):
            sources = {e.source_index:change(e) for e in events}
            result = jitter.flatten_complete_line_jitter(events, visible, styles, source_events=sources)
            self.assertEqual((result.frames, result.stacks, result.captions), (0, 0, ()))
            self.assertTrue(all(a is b for a,b in zip(result.events,events)))
        result = jitter.flatten_complete_line_jitter(events, visible, styles, source_events={})
        self.assertEqual((result.frames, result.stacks), (0, 0))

    def test_invocations_do_not_share_replacements_and_repeat_conversion_is_inert(self):
        events, visible, styles = jitter_inputs()
        a = jitter.flatten_complete_line_jitter(events, visible, styles)
        b = jitter.flatten_complete_line_jitter(events, visible, styles)
        self.assertEqual(a, b)
        self.assertIsNot(a.events, b.events)
        self.assertIsNot(a.captions[0], b.captions[0])
        again = jitter.flatten_complete_line_jitter(a.events, visible, styles)
        self.assertEqual((again.frames, again.stacks, again.captions), (0, 0, ()))
        self.assertIs(again.events[0], a.events[0])
        self.assertEqual(jitter.flatten_complete_line_jitter([], {}, {}),
                         jitter.CompleteLineJitterResult([], 0, 0, ()))

    def test_pipeline_passes_the_exact_accepted_caption_tuple_to_word_echo_proof(self):
        for stacked, counts in ((False, (11, 0)), (True, (20, 1))):
            with self.subTest(stacked=stacked):
                captured = []
                def capture(*args, **kwargs):
                    result = jitter.flatten_complete_line_jitter(*args, **kwargs)
                    captured.append(result)
                    return result
                with tempfile.TemporaryDirectory() as folder:
                    source = Path(folder)/'source.ass'; output = Path(folder)/'output.ass'
                    text = jitter_text()
                    if stacked:
                        text += jitter_text(layer=1, start=1.04, count=10, color='335577')
                    source.write_text(HEADER + text)
                    with patch.object(engine, 'flatten_complete_line_jitter', side_effect=capture), \
                            patch.object(engine, 'remove_owned_word_echoes', wraps=engine.remove_owned_word_echoes) as consumer, \
                            redirect_stdout(io.StringIO()):
                        stats = engine.simplify_ass(source, output, engine.SimplifyConfig(),
                                                    font_metrics=engine.FontMetrics([ROOT/'fonts']))
                    self.assertEqual(len(captured), 1)
                    result = captured[0]
                    self.assertIs(consumer.call_args.args[0], result.events)
                    self.assertIs(consumer.call_args.args[2], result.captions)
                    self.assertEqual((result.frames, result.stacks), counts)
                    self.assertEqual(stats['text_effect_sequences_frozen'], counts[0])
                    self.assertEqual(stats['stacked_text_copies_flattened'], counts[1])
                    self.assertEqual(len(engine.load_subtitle_events(output)[1]), 1)

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
            self.assertFalse((installed/'_simplify_ass/complete_line_jitter.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('complete_line_jitter*.pyc')))


if __name__ == '__main__':
    unittest.main()
