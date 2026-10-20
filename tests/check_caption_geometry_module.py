"""Caption geometry identity, borrowed measurements, uncertainty and installed use."""
import test_paths
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import get_type_hints
import subprocess
import pickle
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import caption_geometry as geometry
from check_windows_installer import load_installer, ROOT

NAMES = ('NUM', 'POS_RE', 'get_pos', 'set_pos', 'inline_layout_key', 'caption_bounds',
         'text_height', 'placement_key', 'text_layout_key', 'compatible_text_layout', 'rectangle_clip')


class Metric:
    """Deterministic measurement double; native checks cover real font ink."""
    available = True

    def __init__(self):
        self.face = SimpleNamespace(cmap={ord(c): ord(c) for c in 'AB '})
        self.calls = []

    def matching_face(self, *args):
        self.calls.append(('face', args))
        return self.face

    def ass_em_scale(self, face):
        return 1.

    def measure(self, face, text, kerning):
        self.calls.append(('measure', text))
        return 1024. * len(text)

    def line_ink_metrics(self, *args, **kwargs):
        return None


def event(**changes):
    return SimpleNamespace(text=r'{\pos(100,100)}A',
        state={'fn': 'Test', 'fs': 20., 'an': 5, 'bord': 2., **changes}, unit=1.,
        measurement=engine.DocumentMeasurementContext(script_wrap_mode=2))


def layout_event():
    raw = ('[Events]\n' + r'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,'
           r'{\pos(100,100)\fs100\fnArial}A' + '\n')
    return next(iter(engine._resolve_document_state(engine.parse_subtitle_document(raw)).events.values()))


def child(code, cwd, tools):
    code = 'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + code
    return subprocess.run([sys.executable, '-I', '-c', code], cwd=cwd,
                          capture_output=True, text=True)


class CaptionGeometryModuleChecks(unittest.TestCase):
    def test_rectangle_clip_reads_borrowed_source_coordinates_without_resolving(self):
        for value,expected in (('(0,0,1920,1080)',(0.,0.,1920.,1080.)),
                               ('( -2.5 , +.5, 3.25, 6 )',(-2.5,.5,3.25,6.)),
                               ('(3,0,2,9)',None),('(0,3,2,3)',None),
                               ('(m 0 0 l 2 0 2 9)',None),('(1,2,3)',None),
                               ('(1,2,3,4,5)',None),('(nan,0,2,9)',None),
                               ('(0,0,inf,9)',None),('(1,2,3,4)junk',None)):
            state = MappingProxyType({'clip':value})
            with self.subTest(value=value):
                self.assertEqual(geometry.rectangle_clip(SimpleNamespace(state=state)),expected)
                self.assertEqual(dict(state),{'clip':value})
        self.assertIsNone(geometry.rectangle_clip(SimpleNamespace(state=MappingProxyType({}))))
        self.assertIsNone(geometry.rectangle_clip(SimpleNamespace(state=MappingProxyType(
            {'clip':'(0,0,2,9)','iclip':None}))))

    def test_canonical_aliases_types_and_patterns(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(geometry, name))
            if callable(getattr(geometry, name)):
                get_type_hints(getattr(geometry, name))
                self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()), getattr(geometry, name))
        self.assertIs(geometry.Event, engine.Event)
        self.assertIs(geometry.FontMetrics, engine.FontMetrics)
        self.assertIs(geometry.OVERRIDE_RE, engine.OVERRIDE_RE)
        self.assertIs(geometry.DEFAULT_STATE, engine.DEFAULT_STATE)
        self.assertIs(get_type_hints(geometry.inline_layout_key)['e'], engine.Event)
        self.assertEqual(get_type_hints(geometry.caption_bounds)['metric'], engine.FontMetrics | None)

    def test_position_editing_preserves_first_match_and_distinct_precision(self):
        text = r'{\pos(10.5,-2)}A{\pos(99,4)}B'
        self.assertEqual(geometry.get_pos(text), (10.5, -2.))
        self.assertIs(geometry.set_pos(text, None), text)
        self.assertEqual(geometry.set_pos(text, (20.125, 4.)),
                         r'{\pos(20.12,4.00)}A{\pos(99,4)}B')
        self.assertEqual(geometry.set_pos('Text', (1., 2.)), r'{\pos(1.00,2.00)}Text')
        self.assertEqual(geometry.set_pos(r'{\an5}Text', (1., 2.)), r'{\pos(1.00,2.00)\an5}Text')
        self.assertIsNone(geometry.get_pos(r'{\pos(1e3,2)}Text'))
        precise = engine.POS_RE.sub(lambda _: r'\pos(12.123456789,4)', text, count=1)
        self.assertEqual(geometry.get_pos(precise), (12.123456789, 4.))

    def test_inline_guard_and_uncertain_bounds(self):
        ordinary = event(); inline = event(); inline.text = r'{\pos(100,100)}A{\bord0}B'
        self.assertEqual(geometry.inline_layout_key(ordinary), '')
        self.assertIs(geometry.inline_layout_key(inline), inline.text)
        self.assertIsNone(geometry.caption_bounds(inline, Metric()))
        self.assertIsNone(geometry.caption_bounds(ordinary, None))
        for changes in ({'p': 1}, {'clip': (0., 0., 50., 50.)}, {'frx': 20.}):
            self.assertIsNone(geometry.caption_bounds(event(**changes), Metric()))
        missing = Metric(); missing.face = None
        self.assertIsNone(geometry.caption_bounds(ordinary, missing))
        missing_glyph = Metric(); missing_glyph.face.cmap.clear()
        self.assertIsNone(geometry.caption_bounds(ordinary, missing_glyph))

    def test_borrowed_event_and_supplied_measurement_owner(self):
        source = event(); before = deepcopy(source); metric = Metric()
        box = geometry.caption_bounds(source, metric)
        self.assertLess(box[0], 100.)
        self.assertGreater(box[2], 100.)
        self.assertEqual(source, before)
        self.assertEqual(metric.calls, [('face', ('Test', 0, False)), ('measure', 'A')])

    def test_shadow_offsets_and_adjacency_keep_separate_contracts(self):
        metric = Metric(); source = event(**{'1a': 255, '4a': 0, 'bord': 0., 'xshad': 50., 'yshad': 20.})
        before = deepcopy(source); box = geometry.caption_bounds(source, metric)
        self.assertTrue(box[0] < 150. < box[2] and box[1] < 120. < box[3])
        self.assertEqual(source, before)
        projective = event(frx=2.); before = deepcopy(projective)
        self.assertIsNone(geometry.caption_bounds(projective, metric))
        self.assertIsNotNone(geometry.caption_bounds(projective, metric, adjacency=True))
        self.assertEqual(projective, before)

    def test_placement_inheritance_inline_guards_and_borrowed_inputs(self):
        source = layout_event()
        source = replace(source, state={**source.state, 'marginl': 17., 'marginr': 18.,
                                       'marginv': 19., 'clip': (0., 1., 20., 30.)})
        before = deepcopy(vars(source))
        self.assertEqual(geometry.placement_key(source)[:3],
                         ((17., 18., 19.), (0., 1., 20., 30.), None))
        self.assertEqual(geometry.placement_key(replace(source, margin_l='9', margin_r='-2'))[0],
                         (9., -2., 19.))
        inline = engine.replace_event(source, text=source.text+r'{\bord1}B')
        self.assertEqual(geometry.placement_key(inline)[-1], inline.text)
        self.assertEqual(vars(source), before)

    def test_exact_layout_and_tolerant_compatibility_keep_distinct_contracts(self):
        source = layout_event(); before = deepcopy(vars(source))
        compatible = replace(source, state={**source.state, 'fn': 'arial', 'fs': 105.})
        self.assertNotEqual(geometry.text_layout_key(source), geometry.text_layout_key(compatible))
        self.assertTrue(geometry.compatible_text_layout(source, compatible))
        self.assertFalse(geometry.compatible_text_layout(source,
            replace(compatible, state={**compatible.state, 'fs': 106.})))
        for field in ('frz', 'frx', 'fry', 'fax', 'fay', 'an'):
            changed = replace(source, state={**source.state, field: source.state.get(field, 0)+1})
            self.assertFalse(geometry.compatible_text_layout(source, changed))
        self.assertFalse(geometry.compatible_text_layout(source, replace(source, margin_l='10')))
        empty = replace(source, state={})
        self.assertEqual(dict(geometry.text_layout_key(empty))['fs'], engine.DEFAULT_STATE['fs'])
        self.assertEqual(empty.state, {})
        self.assertEqual(vars(source), before)

    def test_nominal_height_uses_supplied_cache_without_parsing_or_measurement(self):
        source = layout_event(); before = deepcopy(vars(source))
        self.assertEqual(geometry.text_height(source), 100.)
        self.assertEqual(geometry.text_height(replace(source, state={'fs': -40., 'fscy': 50.})), 20.)
        self.assertEqual(geometry.text_height(replace(source, unit=2., state={'fs': 0.})), 2.)
        empty = replace(source, state={})
        self.assertEqual(geometry.text_height(empty), 20.)
        self.assertEqual(empty.state, {})
        self.assertEqual(vars(source), before)

    def test_cold_processing_without_engine_or_optional_backends(self):
        code = r'''
from types import SimpleNamespace
from _simplify_ass import caption_geometry as g
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
assert g.get_pos(r'{\pos(10.5,-2)}A')==(10.5,-2.)
assert g.set_pos('A',(1.,2.))==r'{\pos(1.00,2.00)}A'
assert g.caption_bounds(SimpleNamespace(text='A',state={}),None) is None
source=SimpleNamespace(text='A',state={'fs':-40.,'fscy':50.,'marginl':17.},unit=1.,margin_l='0',margin_r='0',margin_v='0')
assert g.text_height(source)==20.
assert g.placement_key(source)[0]==(17.,0.,0.)
assert dict(g.text_layout_key(source))['fs']==-40.
assert g.compatible_text_layout(source,source)
assert 'simplify_ass' not in sys.modules
'''
        with tempfile.TemporaryDirectory() as folder:
            result = child(code, folder, ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_real_measurement_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = load_installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            fonts = tools/'fonts'; fonts.mkdir()
            builders = {'__file__': str(ROOT/'tests/check_font_selection.py'), '__name__': 'geometry_font_builders'}
            source = (ROOT/'tests/check_font_selection.py').read_text().split('with tempfile.TemporaryDirectory()')[0]
            exec(compile(source, str(ROOT/'tests/check_font_selection.py'), 'exec'), builders)
            builders['master'](fonts/'local.ttf', 'Caption Geometry Local')
            unrelated = root/'unrelated'; unrelated.mkdir()
            code = r'''
from pathlib import Path
from copy import deepcopy
import py_compile
import simplify_ass as e
from _simplify_ass import caption_geometry as g
assert Path(g.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/caption_geometry.py'
for name in NAMES: assert getattr(e,name) is getattr(g,name)
metrics=e.FontMetrics()
face=metrics.matching_face('Caption Geometry Local',0,False)
assert face is not None and Path(face.path).resolve()==Path(e.__file__).resolve().parent/'fonts/local.ttf'
header='[Script Info]\nPlayResX: 640\nPlayResY: 360\n[Events]\n'
body=r'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\fnCaption Geometry Local\fs40\an5\pos(320,100)}AA'
doc=e._resolve_document_state(e.parse_subtitle_document(header+body+'\n'))
event=next(iter(doc.events.values()));before=deepcopy(event)
box=e.caption_bounds(event,metrics)
assert box is not None and box[0]<320.<box[2] and event==before
assert g.get_pos(event.text)==(320.,100.)
assert g.text_height(event)==40.
assert g.placement_key(event)[0]==(event.state.get('marginl',0),event.state.get('marginr',0),event.state.get('marginv',0))
assert dict(g.text_layout_key(event))['fs']==40.
assert g.compatible_text_layout(event,event)
py_compile.compile(g.__file__,doraise=True)
'''.replace('NAMES', repr(NAMES))
            result = child(code, unrelated, tools)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            user = tools/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((tools/'_simplify_ass/caption_geometry.py').exists())
            self.assertFalse(any((tools/'_simplify_ass').rglob('caption_geometry*.pyc')))


if __name__ == '__main__':
    unittest.main()
