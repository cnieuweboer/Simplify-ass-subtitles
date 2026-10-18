"""Caption-rendering module identity, borrowed evidence and installed use."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import get_type_hints
import pickle
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import caption_rendering as rendering
from check_windows_installer import load_installer, ROOT

NAMES = ('SourceCaptionPaint', 'MAX_PROVED_CAPTION_BORDER', 'render_tag',
         '_source_caption_paint', 'render_simplified_caption')


class CaptionRenderingModuleChecks(unittest.TestCase):
    def test_aliases_annotations_and_defaults_are_canonical(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(rendering, name))
        for name in ('SourceCaptionPaint', 'render_tag', '_source_caption_paint',
                     'render_simplified_caption'):
            get_type_hints(getattr(rendering, name))
        self.assertIs(rendering.DEFAULT_STATE, engine.DEFAULT_STATE)
        self.assertIs(rendering.DocumentMeasurementContext, engine.DocumentMeasurementContext)
        self.assertIs(type(rendering.render_simplified_caption.__kwdefaults__['measurement']),
                      engine.DocumentMeasurementContext)
        for name in ('BackingFadePhase', 'MatchedBackingFade'):
            self.assertEqual(get_type_hints(getattr(engine, name))['paint'],
                             tuple[rendering.SourceCaptionPaint, ...])
        self.assertEqual(get_type_hints(engine.CaptionPaintTimeline)['phases'],
                         tuple[tuple[float, float, tuple[rendering.SourceCaptionPaint, ...]], ...])

    def test_cold_import_and_rendering_without_engine_or_optional_backends(self):
        code = ('import sys\nfrom typing import get_type_hints\n'
            'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
            'from _simplify_ass import caption_rendering as r\n'
            "assert 'simplify_ass' not in sys.modules\n"
            "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n"
            "state={'1c':'EEEEEE','3c':'DDDDDD','bord':1.5}\n"
            'paint=r._source_caption_paint(state,[state])\n'
            "assert paint==r.SourceCaptionPaint('EEEEEE','DDDDDD',0,(1.5,1.5))\n"
            "text=r.render_simplified_caption(state,'Caption',source_paint=paint)\n"
            "assert r'\\3c&HDDDDDD&' in text and text.endswith('}Caption')\n"
            "assert 'simplify_ass' not in sys.modules\n")
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=folder,
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_paint_record_retains_frozen_shape_and_pickle_lookup(self):
        paint = rendering.SourceCaptionPaint('AABBCC', 'DDEEFF', 47)
        self.assertEqual([f.name for f in fields(paint)],
                         ['fill', 'outline', 'outline_alpha', 'border'])
        self.assertEqual(paint.border, (2., 2.))
        with self.assertRaises(FrozenInstanceError):
            paint.fill = 'FFFFFF'
        self.assertIs(pickle.loads(b'csimplify_ass\nSourceCaptionPaint\n.'),
                      rendering.SourceCaptionPaint)
        restored = pickle.loads(pickle.dumps(paint))
        self.assertIs(type(restored), rendering.SourceCaptionPaint)
        self.assertEqual(restored, paint)

    def test_source_resolution_borrows_inputs_and_keeps_contour_policy(self):
        state = {**engine.DEFAULT_STATE, '1c': 'EEEEEE', '3c': 'DDDDDD', 'bord': 5.}
        for label, changes, expected in (
            ('capped low contrast', {}, rendering.SourceCaptionPaint('EEEEEE', 'DDDDDD', 0)),
            ('independent alpha', {'3a': 96}, rendering.SourceCaptionPaint('EEEEEE', 'DDDDDD', 96)),
            ('coupled fade', {'1a': 96, '3a': 96}, rendering.SourceCaptionPaint('EEEEEE', 'DDDDDD', 0)),
            ('borderless', {'bord': 0., 'shad': 0.}, rendering.SourceCaptionPaint('EEEEEE', '000000', 0, (0., 0.))),
            ('uncertain clip', {'clip': (0., 0., 10., 10.)}, None),
        ):
            with self.subTest(label=label):
                selected = {**state, **changes}; sources = [dict(selected)]
                before = deepcopy((selected, sources))
                paint = rendering._source_caption_paint(selected, iter(sources))
                self.assertEqual(paint, expected)
                if paint is not None:
                    rendering.render_simplified_caption(selected, 'Caption', iter(sources), source_paint=paint)
                self.assertEqual((selected, sources), before)

    def test_shadow_transfer_discards_foreground_paint_without_mutation(self):
        state = {'pos': (320., -1000.), 'fs': 20., 'yshad': 1200., 'xshad': 0.,
                 '1c': 'EEEEEE', '4c': '112233', '4a': 0}
        before = deepcopy(state)
        paint = rendering.SourceCaptionPaint('EEEEEE', 'DDDDDD', 0, (0., 0.))
        text = rendering.render_simplified_caption(state, 'Caption', source_paint=paint,
            measurement=engine.DocumentMeasurementContext(canvas=(640., 360.)))
        self.assertIn(r'\pos(320,200)', text)
        self.assertIn(r'\1c&H112233&', text)
        self.assertIn(r'\bord2', text)
        self.assertEqual(state, before)

    def test_tag_serialization_stays_independent_of_caption_policy(self):
        self.assertEqual(rendering.render_tag('pos', (1., 2.)), r'\pos(1,2)')
        self.assertEqual(rendering.render_tag('3a', 47), r'\3a&H2F&')
        self.assertEqual(rendering.render_tag('1c', 'AABBCC'), r'\1c&HAABBCC&')
        self.assertEqual(rendering.render_tag('bord', 5.), r'\bord5')

    def test_installed_rendering_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = load_installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            unrelated = root/'unrelated'; unrelated.mkdir()
            code = ('import sys,py_compile\nfrom pathlib import Path\n'
                'sys.path.insert(0,' + repr(str(tools)) + ')\nimport simplify_ass as e\n'
                'from _simplify_ass import caption_rendering as r\n'
                "assert Path(r.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/caption_rendering.py'\n"
                'for name in ' + repr(NAMES) + ': assert getattr(e,name) is getattr(r,name)\n'
                "state={'1c':'EEEEEE','3c':'DDDDDD','bord':1.5}\n"
                'paint=r._source_caption_paint(state,[state])\n'
                "text=e.render_simplified_caption(state,'Caption',source_paint=paint)\n"
                "assert r'\\3c&HDDDDDD&' in text and r'\\bord1.5' in text\n"
                "assert type(r.render_simplified_caption.__kwdefaults__['measurement']) is e.DocumentMeasurementContext\n"
                'py_compile.compile(r.__file__,doraise=True)\n')
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=unrelated,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            user = tools/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((tools/'_simplify_ass/caption_rendering.py').exists())
            self.assertFalse(any((tools/'_simplify_ass').rglob('caption_rendering*.pyc')))


if __name__ == '__main__':
    unittest.main()
