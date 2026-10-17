"""Sampling module isolation, input/result ownership and interpreter composition."""
import test_paths
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import get_type_hints
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import transform_sampling as sampler
from override_module_test_helpers import patch_interpreter_bindings

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('font_size_transform_needs_replay', 'transform_weight', 'interpolate_transform_value',
         '_commit_transform_continuation', 'sample_transform_state', 'sample_transform_states')


class TransformSamplingModuleChecks(unittest.TestCase):
    def test_direct_aliases_and_existing_interpreter_records(self):
        for name in NAMES:
            function = getattr(sampler, name)
            self.assertIs(getattr(engine, name), function)
            get_type_hints(function)
        self.assertIs(sampler.OverrideContinuation, engine.OverrideContinuation)
        self.assertIs(sampler.OverrideEvaluation, engine.OverrideEvaluation)
        self.assertFalse(hasattr(sampler, 'Event'))
        self.assertFalse(hasattr(sampler, 'FontMetrics'))

    def test_independent_import_and_annotation_resolution(self):
        with tempfile.TemporaryDirectory() as folder:
            code = ('import sys\nfrom typing import get_type_hints\n'
                'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
                'from _simplify_ass import transform_sampling as s\n'
                "assert 'simplify_ass' not in sys.modules\n"
                "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n"
                'for name in ' + repr(NAMES) + ': get_type_hints(getattr(s,name))\n')
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=folder,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_borrowed_seeds_and_independent_result_buffers(self):
        base = {**engine.DEFAULT_STATE, 'fs': 20, 'bord': 0}
        default = base.copy(); styles = {'Other': {**base, 'fs': 40}}
        transforms = [(0, 1000, 1, [('r', 'Other'), ('fs', '+2'), ('an', '7')])]
        seed = engine.OverrideContinuation('', False)
        before = deepcopy((base, default, styles, transforms))
        args = (MappingProxyType(base), transforms, 500,
                MappingProxyType({k: MappingProxyType(v) for k, v in styles.items()}),
                MappingProxyType(default))
        left = sampler.sample_transform_state(*args, continuation=seed)
        right = sampler.sample_transform_state(*args, continuation=seed)
        self.assertEqual(left, right)
        self.assertEqual((base, default, styles, transforms), before)
        self.assertEqual(seed, engine.OverrideContinuation('', False))
        self.assertEqual(left.continuation.reset_style, 'Other')
        self.assertTrue(left.continuation.alignment_set)
        left.formatting['fs'] = 999
        self.assertNotEqual(right.formatting['fs'], 999)
        self.assertIsNot(left.formatting, base)

    def test_ordered_sampling_is_lazy_with_owned_per_sample_buffers(self):
        consumed = []
        def times():
            for at in [0, 500, 500, 1000]:
                consumed.append(at)
                yield at
        base = {'fs': 20}
        stream = sampler.sample_transform_states(base, [(0, 1000, 1, [('fs', '40')])], times(), {}, base)
        self.assertEqual(consumed, [])
        first = next(stream)
        self.assertEqual(consumed, [0, 500, 500, 1000])
        rest = list(stream)
        self.assertEqual([first.formatting['fs'], *(v.formatting['fs'] for v in rest)], [20, 30, 30, 40])
        first.formatting['fs'] = 999
        rest[0].formatting['fs'] = 888
        self.assertEqual([v.formatting['fs'] for v in rest[1:]], [30, 40])
        self.assertEqual(base, {'fs': 20})

    def test_optimized_and_fallback_paths_keep_the_same_interpreter_owner(self):
        base = {'bord': 0}
        changes = [(0, 100, 1, [('bord', '2')])]
        with patch_interpreter_bindings(engine, 'apply_override', wraps=engine.apply_override) as apply:
            optimized = list(engine.sample_transform_states(base, changes, [0, 50, 100], {}, base))
        self.assertEqual([v.formatting['bord'] for v in optimized], [0, 1, 2])
        self.assertEqual(apply.call_count, 1)
        with patch.object(sampler, 'sample_transform_state', wraps=sampler.sample_transform_state) as single:
            replayed = list(engine.sample_transform_states(base, changes, [100, 0, 50], {}, base))
        self.assertEqual([v.formatting['bord'] for v in replayed], [2, 0, 1])
        self.assertEqual(single.call_count, 3)

    def test_relative_size_replay_uses_the_existing_size_interpreter(self):
        base = {**engine.DEFAULT_STATE, 'fs': 20}
        changes = [(0, 100, 1, [('fs', '+2')])]
        with patch_interpreter_bindings(engine, 'apply_font_size', wraps=engine.apply_font_size) as size:
            result = list(engine.sample_transform_states(base, changes, [0, 100], {}, base))
        self.assertEqual([v.formatting['fs'] for v in result], [20, 24])
        self.assertEqual(size.call_count, 2)
        self.assertEqual(base['fs'], 20)

    def test_interpolation_populates_only_its_explicit_decoding_cache(self):
        cache = {}
        self.assertEqual(sampler.interpolate_transform_value('1c', '000000', 'FFFFFF', .5, cache), '808080')
        self.assertEqual(cache, {'000000': (0, 0, 0), 'FFFFFF': (255, 255, 255)})
        snapshot = deepcopy(cache)
        self.assertEqual(sampler.interpolate_transform_value('1c', 'FFFFFF', '000000', .5), '808080')
        self.assertEqual(cache, snapshot)


if __name__ == '__main__':
    unittest.main()
