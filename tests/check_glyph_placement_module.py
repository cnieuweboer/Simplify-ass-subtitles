"""Glyph-placement import, borrowing and shared-model contracts."""
import test_paths
from pathlib import Path
from types import MappingProxyType
from typing import get_type_hints
from unittest.mock import patch
import copy
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import glyph_placement as placement

NAMES = ('fit_fragment_anchor', 'authored_glyph_positions', 'matches_authored_glyph_positions')
ROOT = Path(__file__).resolve().parents[1]


class UniformMetrics:
    """Recorded independent-glyph advances, without optional font packages."""
    available = True
    def matching_face(self, *args):
        return type('Face', (), {'cmap': {ord(c): c for c in 'AB '}})()
    def ass_em_scale(self, face):
        return 1.
    def measure(self, face, text, kerning=False):
        return 512 * len(text)


class GlyphPlacementModuleChecks(unittest.TestCase):
    def test_engine_exports_are_direct_aliases_with_resolvable_annotations(self):
        for name in NAMES:
            function = getattr(placement, name)
            self.assertIs(getattr(engine, name), function)
            self.assertIs(get_type_hints(function)['metrics'], engine.FontMetrics)
        self.assertFalse(hasattr(placement, 'Event'))
        self.assertFalse(hasattr(placement, 'FontProcessingReport'))

    def test_independent_import_without_engine_or_optional_backends(self):
        with tempfile.TemporaryDirectory() as folder:
            code = ('import sys\nfrom typing import get_type_hints\n'
                'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
                'from _simplify_ass import glyph_placement as p\n'
                "assert 'simplify_ass' not in sys.modules\n"
                "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n"
                'for name in ' + repr(NAMES) + ': get_type_hints(getattr(p,name))\n')
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=folder,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_positions_and_fragment_fit_borrow_their_inputs(self):
        state = {'fn': 'Recorded', 'fs': 20, 'an': 5, 'fsp': 2, 'fscx': 100}
        xs = [94., 106.]; fragments = ['A', 'B']
        original = copy.deepcopy((state, xs, fragments))
        borrowed = MappingProxyType(state)
        metrics = UniformMetrics()
        expected = [('A', 94.), ('B', 106.)]
        self.assertEqual(placement.authored_glyph_positions(metrics, borrowed, 'AB', 100, .01), expected)
        self.assertTrue(placement.matches_authored_glyph_positions(metrics, borrowed, xs, 'AB', 100, .01))
        self.assertEqual(placement.fit_fragment_anchor(metrics, borrowed, xs, fragments, 'AB', .01,
            allow_tracking=True, exact_size=True), 100.)
        self.assertEqual(placement.authored_glyph_positions(metrics, borrowed, 'A B', 100, .01),
                         [('A', 88.), ('B', 112.)])
        self.assertEqual((state, xs, fragments), original)
        first = placement.authored_glyph_positions(metrics, borrowed, 'AB', 100, .01)
        first.clear()
        self.assertEqual(placement.authored_glyph_positions(metrics, borrowed, 'AB', 100, .01), expected)

    def test_boolean_proof_uses_the_defining_modules_position_model(self):
        with patch.object(placement, 'authored_glyph_positions',
                          wraps=placement.authored_glyph_positions) as model:
            self.assertTrue(engine.matches_authored_glyph_positions(
                UniformMetrics(), {'fn': 'Recorded', 'fs': 20, 'an': 5}, [95, 105], 'AB', 100, .01))
        self.assertEqual(model.call_count, 1)

    def test_rejections_remain_silent_and_preserve_borrowed_state(self):
        metrics = UniformMetrics(); metrics.available = False
        state = {'fn': 'Unavailable', 'fs': 20}; before = state.copy()
        self.assertIsNone(placement.authored_glyph_positions(metrics, state, 'AB', 100, .01))
        self.assertFalse(placement.matches_authored_glyph_positions(metrics, state, [95, 105], 'AB', 100, .01))
        self.assertIsNone(placement.fit_fragment_anchor(metrics, state, [95, 105], ['A', 'B'], 'AB', .01))
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
