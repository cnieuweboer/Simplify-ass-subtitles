"""Drawing geometry retains conservative proofs and caller-owned evidence."""
import test_paths
from copy import deepcopy
from dataclasses import replace
from typing import get_type_hints
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

import simplify_ass as engine
from _simplify_ass import drawing_geometry as geometry
from check_windows_installer import ROOT, load_installer

NAMES = ('coverage_geometry', 'polygon_covers_box', 'drawing_polygon',
         'fit_rectangular_contour', 'normalize_drawing_alignment',
         'flatten_rectangular_border', 'detach_drawing_edge_slivers',
         'simplify_drawing_contour')
RECTANGLE = 'm 0 0 l 100 0 100 50 0 50'
SUBDIVIDED = 'm 0 0 l 25 0 50 0 75 0 100 0 100 25 100 50 50 50 0 50 0 25'


def drawing(path=RECTANGLE, tags='', *, alignment=7):
    raw = '[Script Info]\n[Events]\n'
    raw += ('Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,'
            + rf'{{\pos(100,100)\an{alignment}\p1\bord0\shad0{tags}}}' + path + '\n')
    document = engine._resolve_document_state(engine.parse_subtitle_document(raw))
    return next(iter(document.events.values()))


COLD_CODE = r'''
from pathlib import Path
from copy import deepcopy
from _simplify_ass import drawing_geometry as g, subtitle_document as d
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
raw='[Script Info]\n[Events]\nDialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,'
raw+=r'{\pos(100,100)\an7\p1\bord0\shad0}m 0 0 l 100 0 100 50 0 50'+'\n'
event=next(iter(d._resolve_document_state(d.parse_subtitle_document(raw)).events.values()))
before=deepcopy(vars(event))
assert g.drawing_polygon(event)==[(0.,0.),(100.,0.),(100.,50.),(0.,50.)]
points,box,opaque=g.coverage_geometry(event)
assert box==(98.,98.,202.,152.) and opaque
assert g.polygon_covers_box(points,(110,110,190,140))
assert not g.polygon_covers_box(points,(100,110,190,140))
assert g.normalize_drawing_alignment(event) is event
assert vars(event)==before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as e
assert Path(g.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/drawing_geometry.py'
for name in ('coverage_geometry','polygon_covers_box','drawing_polygon',
             'fit_rectangular_contour','normalize_drawing_alignment',
             'flatten_rectangular_border','detach_drawing_edge_slivers','simplify_drawing_contour'):
 assert getattr(e,name) is getattr(g,name)
import py_compile
py_compile.compile(g.__file__,doraise=True)
'''


class DrawingGeometryModuleChecks(unittest.TestCase):
    def test_canonical_aliases_types_defaults_and_old_root_lookup(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(geometry, name))
            get_type_hints(getattr(geometry, name))
            self.assertIs(pickle.loads(pickle.dumps(getattr(geometry, name))),
                          getattr(geometry, name))
        self.assertIs(geometry.Event, engine.Event)
        self.assertIs(geometry.geometry_key, engine.geometry_key)
        self.assertIs(pickle.loads(b'csimplify_ass\ncoverage_geometry\n.'),
                      geometry.coverage_geometry)
        self.assertEqual(geometry.drawing_polygon(drawing()),
                         [(0., 0.), (100., 0.), (100., 50.), (0., 50.)])

    def test_bounds_include_scale_stroke_shadow_and_hidden_channels(self):
        event = drawing(tags=r'\p2\bord2\xshad-3\yshad4\3a&HFF&\4a&HFF&')
        before = deepcopy(vars(event))
        points, bounds, opaque = geometry.coverage_geometry(event)
        self.assertEqual(points, [(100., 100.), (150., 100.), (150., 125.), (100., 125.)])
        self.assertEqual(bounds, (93., 96., 154., 133.))
        self.assertTrue(opaque)
        self.assertIsNone(geometry.coverage_geometry(event, scaled_borders=False))
        self.assertEqual(vars(event), before)
        for changes in ({'layer': 'bad'}, {'state': {**event.state, 'frz': 10}},
                        {'state': {**event.state, 'fscx': 0}}):
            self.assertIsNone(geometry.coverage_geometry(replace(event, **changes)))

    def test_curves_unknown_paths_and_coverage_boundaries_stay_distinct(self):
        event = drawing(); points, _, _ = geometry.coverage_geometry(event)
        self.assertTrue(geometry.polygon_covers_box(points, (110, 110, 190, 140)))
        self.assertFalse(geometry.polygon_covers_box(points, (100, 110, 190, 140)))
        curve = drawing('m 0 0 b 20 0 100 20 100 50 l 0 50')
        self.assertIsNone(geometry.drawing_polygon(curve))
        self.assertFalse(geometry.coverage_geometry(curve)[2])
        for path in ('m 0 0 l nan 3 5 4',
                     RECTANGLE + ' m 20 20 l 30 20 30 30',
                     'm 0 0 s 10 0 100 50 0 50'):
            with self.subTest(path=path):
                self.assertIsNone(geometry.drawing_polygon(drawing(path)))
                self.assertIsNone(geometry.coverage_geometry(drawing(path)))

    def test_alignment_and_border_successors_preserve_scene_footprint_and_inputs(self):
        centered = drawing(alignment=5)
        before = deepcopy(vars(centered))
        out = geometry.normalize_drawing_alignment(centered)
        self.assertEqual(out.state['an'], 7)
        self.assertEqual(geometry.get_pos(out.text), (50., 75.))
        self.assertEqual(geometry.coverage_geometry(out)[0],
                         [(50., 75.), (150., 75.), (150., 125.), (50., 125.)])
        self.assertEqual(out.fields()[:-1], centered.fields()[:-1])
        self.assertIs(out.styles, centered.styles)
        self.assertIs(out.measurement, centered.measurement)
        self.assertEqual(vars(centered), before)
        bordered = drawing(tags=r'\bord2\1c&HFFFFFF&\3c&HFFFFFF&')
        bordered = replace(bordered, evidence=engine.EventEvidence(
            original_contour_points=((0., 0.),), opaque_spans=((1., 4.),)))
        before = deepcopy(vars(bordered)); flat = geometry.flatten_rectangular_border(bordered)
        self.assertNotEqual(flat.text, bordered.text)
        self.assertEqual(geometry.coverage_geometry(flat)[1], geometry.coverage_geometry(bordered)[1])
        self.assertIsNone(flat.evidence.original_contour_points)
        self.assertIsNone(flat.evidence.opaque_spans)
        self.assertEqual(vars(bordered), before)
        self.assertIs(geometry.flatten_rectangular_border(bordered, scaled_borders=False), bordered)
        rotated = drawing(tags=r'\frz10', alignment=5)
        self.assertIs(geometry.normalize_drawing_alignment(rotated), rotated)

    def test_sliver_proof_keeps_interior_overlap_and_independent_artwork(self):
        source = drawing(RECTANGLE + ' m 50 0 l 50.2 -0.2 50.4 0')
        before = deepcopy(vars(source)); out, count = geometry.detach_drawing_edge_slivers(source)
        self.assertEqual(count, 1)
        self.assertEqual(geometry.drawing_polygon(out), geometry.drawing_polygon(drawing()))
        self.assertEqual(out.source_index, source.source_index)
        self.assertEqual(out.fields()[:-1], source.fields()[:-1])
        self.assertEqual(vars(source), before)
        for extra in (' m 50 0 l 50.2 0.2 50.4 0',
                      ' m 150 0 l 150.2 -0.2 150.4 0',
                      ' m 50 0 l 60 -10 70 0'):
            source = drawing(RECTANGLE + extra)
            out, count = geometry.detach_drawing_edge_slivers(source)
            self.assertEqual(count, 0)
            self.assertIs(out, source)

    def test_reduction_returns_original_scene_contour_without_installing_evidence(self):
        source = drawing(SUBDIVIDED); before = deepcopy(vars(source))
        self.assertIsNone(geometry.drawing_polygon(source))
        raw, original = geometry.simplify_drawing_contour(source)
        self.assertEqual(original, geometry.coverage_geometry(source)[0])
        successor = geometry.replace_event(source, text=engine.OVERRIDE_RE.match(source.text).group() + raw)
        self.assertLessEqual(len(geometry.drawing_polygon(successor)), 8)
        self.assertEqual(geometry.coverage_geometry(successor)[1], geometry.coverage_geometry(source)[1])
        self.assertIsNone(source.evidence.original_contour_points)
        self.assertIsNone(successor.evidence.original_contour_points)
        self.assertEqual(vars(source), before)

    def test_supporting_producer_retains_original_contour_and_count_ownership(self):
        source = drawing(SUBDIVIDED); before = deepcopy(vars(source))
        out, counts = engine.reduce_supporting_drawings([source])
        self.assertEqual(len(out), 1)
        self.assertEqual(counts['drawing_contours_simplified'], 1)
        self.assertEqual(counts['drawing_candidates'], 1)
        self.assertEqual(out[0].evidence.original_contour_points,
                         tuple(geometry.coverage_geometry(source)[0]))
        self.assertEqual(vars(source), before)
        # A later pass invocation must not inherit the preceding contour map.
        ordinary = drawing(); again, counts = engine.reduce_supporting_drawings([ordinary])
        self.assertEqual(counts['drawing_contours_simplified'], 0)
        self.assertIsNone(again[0].evidence.original_contour_points)

    def test_cold_installed_geometry_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            owner = load_installer(); target = root/'installed tools with spaces'
            _, installed = owner.install(ROOT, target, individual_launchers=False)
            for tools in (ROOT, installed):
                result = subprocess.run([sys.executable, '-I', '-c',
                    'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + COLD_CODE],
                    cwd=unrelated, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((installed/'_simplify_ass/drawing_geometry.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('drawing_geometry*.pyc')))


if __name__ == '__main__':
    unittest.main()
