"""Static selection boundary, canonical results, borrowed evidence and delivery."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Iterable, get_type_hints
import inspect
import os
import pickle
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import static_selection as selection
from _simplify_ass import transform_sampling as sampler
from check_windows_installer import load_installer, ROOT
from override_module_test_helpers import patch_interpreter_bindings

RECORDS = ('StaticStateContext', 'StaticStateEvidence', 'StaticStateSamples',
           'StaticPoseEvidence', 'StaticStateSelection')
FUNCTIONS = ('select_static_state', 'unrotated_text_state', 'upright_text_state',
    'upright_transform_pose', '_prepare_static_state_evidence',
    '_static_state_geometry_is_settled', '_vote_static_state_holds',
    '_record_static_opaque_span', '_sample_static_state_intervals',
    '_choose_static_state_geometry', '_static_state_has_rotation',
    '_apply_static_upright_fallback', '_protect_sustained_static_geometry',
    '_static_state_colour_spans', '_vote_static_state_colours',
    '_apply_static_state_colour_vote')


class StaticSelectionModuleChecks(unittest.TestCase):
    def test_canonical_aliases_annotations_and_result_factories(self):
        for name in (*RECORDS, *FUNCTIONS):
            self.assertIs(getattr(engine, name), getattr(selection, name))
            get_type_hints(getattr(selection, name))
        self.assertIs(selection.Event, engine.Event)
        self.assertIs(selection.OverrideContinuation, engine.OverrideContinuation)
        self.assertIs(selection.sample_transform_states, sampler.sample_transform_states)
        self.assertEqual(get_type_hints(selection.select_static_state)['paint_events'],
                         Iterable[engine.Event] | None)
        self.assertIs(get_type_hints(engine.FrozenBlock)['selection'], selection.StaticStateSelection)
        factories = {f.name: f.default_factory for f in fields(selection.StaticStateSelection)}
        self.assertIs(factories['pose'], selection.StaticPoseEvidence)
        self.assertIs(factories['continuation'], engine.OverrideContinuation)

    def test_independent_import_without_engine_or_optional_backends(self):
        code = ('import sys\nfrom typing import get_type_hints\n'
            'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
            'from _simplify_ass import static_selection as s\n'
            "assert 'simplify_ass' not in sys.modules\n"
            "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n"
            'for name in ' + repr((*RECORDS, *FUNCTIONS)) + ': get_type_hints(getattr(s,name))\n'
            'base={"1a":0}\nresult=s.select_static_state(base,[],{0.,1000.},{},base)\n'
            'assert result.state is base\n')
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=folder,
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unchanged_selection_borrows_base_and_preserves_seed_ownership(self):
        base = {**engine.DEFAULT_STATE, 'pos': (10., 20.)}
        seed = {'seed': True}; settled = [seed]; opaque = [(-100., 0.)]
        before = deepcopy((base, settled, opaque))
        pose = selection.StaticPoseEvidence(True, (('pos', (10., 20.)),))
        continuation = engine.OverrideContinuation('Other', True)
        result = selection.select_static_state(base, [], {0., 1000.}, {}, base,
            prior_opaque_spans=opaque, prior_settled_states=settled,
            prior_pose=pose, continuation=continuation)
        self.assertIs(result.state, base)
        self.assertIs(result.pose, pose)
        self.assertIs(result.continuation, continuation)
        self.assertEqual((base, settled, opaque), before)
        self.assertIs(result.settled_states[0], seed)
        self.assertIsNot(result.settled_states[1], base)
        self.assertEqual(result.settled_states[1], base)
        self.assertEqual(result.opaque_spans, ((-100., 0.), (0., 1000.)))
        absent = selection.select_static_state(base, [], set(), {}, base)
        empty = selection.select_static_state(base, [], set(), {}, base,
            prior_opaque_spans=(), prior_settled_states=())
        self.assertIsNone(absent.opaque_spans)
        self.assertIsNone(absent.settled_states)
        self.assertEqual((empty.opaque_spans, empty.settled_states), ((), ()))

    def test_sampled_results_own_changed_buffers_and_keep_continuation(self):
        base = {**engine.DEFAULT_STATE, 'fs': 20, 'pos': (10., 20.)}
        default = base.copy(); styles = {'Other': {**base, 'fs': 40}}
        transforms = [(0., 1000., 1., [('r', 'Other'), ('fs', '+2')])]
        seed = {'seed': True}; settled = [seed]; opaque = [(-100., 0.)]
        before = deepcopy((base, default, styles, transforms, settled, opaque))
        def choose():
            return selection.select_static_state(base, transforms, {0., 1000.}, styles, default,
                prior_opaque_spans=opaque, prior_settled_states=settled,
                continuation=engine.OverrideContinuation('', False))
        left, right = choose(), choose()
        self.assertEqual(left, right)
        self.assertIsNot(left.state, base)
        self.assertIsNot(left.state, right.state)
        self.assertEqual(left.continuation.reset_style, 'Other')
        self.assertIs(left.settled_states[0], seed)
        self.assertEqual((base, default, styles, transforms, settled, opaque), before)
        left.state['fs'] = 999
        self.assertNotEqual(right.state['fs'], 999)

    def test_frozen_records_keep_shallow_buffers_and_tuple_protected_pose(self):
        point = [10., 20.]; source = [('pos', point)]
        pose = selection.StaticPoseEvidence(True, source)
        point[0] = 999; source.clear()
        self.assertEqual(pose.sustained_geometry, (('pos', (10., 20.)),))
        for name in RECORDS:
            self.assertTrue(getattr(selection, name).__dataclass_params__.frozen)
        result = selection.StaticStateSelection({}, None, None, pose)
        with self.assertRaises(FrozenInstanceError):
            result.state = {}
        result.state['fs'] = 20
        self.assertEqual(result.state, {'fs': 20})

    def test_interpreter_observation_covers_actual_consumers_and_restores_bindings(self):
        original = engine.apply_override
        owners = [engine, selection, sampler, inspect.getmodule(original)]
        with patch_interpreter_bindings(engine, 'apply_override', wraps=original) as watched:
            for owner in owners:
                self.assertIs(owner.apply_override, watched)
            base = {**engine.DEFAULT_STATE, 'pos': (10., 20.)}
            selected = engine.select_static_state(base,
                [(0., 100., 1., [('fs', '40')])], {0., 100.}, {}, base,
                prefer_upright=True)
            self.assertGreater(watched.call_count, 0)
            self.assertIs(type(selected), selection.StaticStateSelection)
        for owner in owners:
            self.assertIs(owner.apply_override, original)

    def test_pickle_roundtrip_and_legacy_engine_record_lookup(self):
        for name in RECORDS:
            self.assertIs(pickle.loads(('csimplify_ass\n' + name + '\n.').encode()),
                          getattr(selection, name))
        original = selection.StaticStateSelection({'fs': 20}, (), ({'fs': 20},),
            selection.StaticPoseEvidence(True, (('pos', (10., 20.)),)),
            engine.OverrideContinuation('Other', True))
        result = pickle.loads(pickle.dumps(original))
        self.assertEqual(result, original)
        self.assertIs(type(result), selection.StaticStateSelection)
        self.assertIs(type(result.pose), selection.StaticPoseEvidence)

    def test_installed_selector_freezing_cli_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = load_installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            unrelated = root/'unrelated'; unrelated.mkdir()
            code = ('import sys\nfrom pathlib import Path\nfrom dataclasses import fields\n'
                'sys.path.insert(0,' + repr(str(tools)) + ')\nimport simplify_ass as e\n'
                'from _simplify_ass import static_selection as s\n'
                "assert Path(s.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/static_selection.py'\n"
                'for name in ' + repr((*RECORDS, *FUNCTIONS)) + ': assert getattr(e,name) is getattr(s,name)\n'
                'assert next(f for f in fields(s.StaticStateSelection) if f.name=="pose").default_factory is s.StaticPoseEvidence\n'
                'base={**e.DEFAULT_STATE,"pos":(10.,20.)}\n'
                'assert s.select_static_state(base,[],{0.,1000.},{},base).state is base\n'
                r'block=e.freeze_block(r"\t(0,1000,\fs40)",1.,base,base,{},0.)' + '\n'
                'assert type(block.selection) is s.StaticStateSelection\n'
                'assert type(block.selection.pose) is s.StaticPoseEvidence\n')
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=unrelated,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = unrelated/'input.ass'
            source.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n'
                '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,Alignment\nStyle: Default,Arial,20,2\n'
                '[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
                r'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\t(0,1000,\fs40)}Hello' + '\n')
            env = os.environ.copy(); env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, str(tools/'simplify_ass.py'), str(source), '--no-font-spacing'],
                                    cwd=unrelated, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = engine.load_subtitle_events(source.with_name('input.simple.ass'))[1]
            self.assertEqual(len(output), 1)
            self.assertEqual(engine.OVERRIDE_RE.sub('', output[0].text), 'Hello')
            self.assertEqual((output[0].start_s, output[0].end_s), (1, 3))
            self.assertNotIn(r'\t(', output[0].text)
            self.assertTrue(list((tools/'_simplify_ass/__pycache__').glob('static_selection.*.pyc')))
            keep = tools/'keep.txt'; keep.write_text('user')
            owner.remove(target)
            self.assertFalse((tools/'_simplify_ass').exists())
            self.assertEqual(keep.read_text(), 'user')


if __name__ == '__main__':
    unittest.main()
