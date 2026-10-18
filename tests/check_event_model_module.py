"""Canonical event-record classes, factories, ownership and installed behavior."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
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
from _simplify_ass import event_model as model
from check_windows_installer import load_installer, ROOT

NAMES = ('Event', 'EventEvidence', 'DocumentMeasurementContext')
HEADER = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n'
    '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,Outline,Alignment\n'
    'Style: Default,Arial,20,&H00FFFFFF,&H00000000,2,2\n[Events]\n'
    'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
    'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\n')


def event():
    return engine.Event('Dialogue', '0', '0:00:01.00', '0:00:03.00', 'Default', '',
                        '0', '0', '0', '', 'Hello', 1., 3., 1)


class EventModelModuleChecks(unittest.TestCase):
    def test_engine_aliases_and_annotations_use_the_canonical_classes(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(model, name))
            get_type_hints(getattr(model, name))
        self.assertEqual(get_type_hints(engine.fit_fullwidth_run)['ordered'], list[model.Event])
        self.assertEqual(get_type_hints(engine.select_static_state)['paint_events'], Iterable[model.Event] | None)
        self.assertEqual(get_type_hints(engine.SubtitleDocument)['events'], dict[int, model.Event])

    def test_factories_and_constructed_defaults_use_canonical_records(self):
        factories = {f.name: f.default_factory for f in fields(model.Event)}
        self.assertIs(factories['evidence'], model.EventEvidence)
        self.assertIs(factories['measurement'], model.DocumentMeasurementContext)
        self.assertIs(factories['continuation'], engine.OverrideContinuation)
        document_field = next(f for f in fields(engine.SubtitleDocument) if f.name == 'measurement')
        self.assertIs(document_field.default_factory, model.DocumentMeasurementContext)
        default = inspect.signature(engine.render_simplified_caption).parameters['measurement'].default
        self.assertIs(type(default), model.DocumentMeasurementContext)

    def test_independent_model_import_needs_no_engine_or_optional_backend(self):
        code = ('import sys\nfrom typing import get_type_hints\n'
            'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
            'from _simplify_ass import event_model as m\n'
            "assert 'simplify_ass' not in sys.modules\n"
            "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n"
            'for name in ' + repr(NAMES) + ': get_type_hints(getattr(m,name))\n')
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=folder,
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_construction_has_fresh_buffers_and_preserves_fields_and_equality(self):
        left, right = event(), event()
        self.assertEqual(left, right)
        self.assertEqual(left.duration, 2)
        self.assertEqual(left.fields(), ['0', '0:00:01.00', '0:00:03.00', 'Default', '', '0', '0', '0', '', 'Hello'])
        output = left.fields(); output[-1] = 'changed'
        self.assertEqual(left.text, 'Hello')
        for name in ('state', 'defaults', 'styles'):
            self.assertIsNot(getattr(left, name), getattr(right, name))
        left.state['fs'] = 99; left.evidence = model.EventEvidence(((1, 2),))
        self.assertEqual(left, right)
        self.assertFalse(model.Event.__dataclass_params__.frozen)

    def test_evidence_and_context_keep_their_existing_frozen_contracts(self):
        points = [[1, 2]]; spans = [[1, 3]]; alpha = [0, 20, 30]
        evidence = model.EventEvidence(points, spans, [(1, 3, alpha)])
        points[0][0] = 999; spans[0][0] = 999; alpha[0] = 999
        self.assertEqual(evidence.original_contour_points, ((1, 2),))
        self.assertEqual(evidence.opaque_spans, ((1, 3),))
        self.assertEqual(evidence.frame_pose_intervals, ((1, 3, (0, 20, 30)),))
        self.assertIsNone(model.EventEvidence().opaque_spans)
        self.assertEqual(model.EventEvidence(opaque_spans=()).opaque_spans, ())
        with self.assertRaises(FrozenInstanceError):
            evidence.opaque_spans = ()
        context = model.DocumentMeasurementContext((640, 360), 2)
        with self.assertRaises(FrozenInstanceError):
            context.canvas = None

    def test_copy_and_replace_preserve_existing_borrowing(self):
        source = event(); source.state['fs'] = 20
        successor = replace(source, end_s=4)
        self.assertIs(type(successor), model.Event)
        self.assertEqual(successor.duration, 3)
        for name in ('state', 'defaults', 'styles', 'evidence', 'measurement', 'continuation'):
            self.assertIs(getattr(source, name), getattr(successor, name))
        independent = deepcopy(source)
        self.assertIs(type(independent), model.Event)
        self.assertEqual(independent, source)
        self.assertIsNot(independent.state, source.state)

    def test_parsing_and_replacement_keep_cache_and_evidence_policy_in_the_engine(self):
        document = engine._resolve_document_state(engine.parse_subtitle_document(HEADER))
        source = next(iter(document.events.values()))
        self.assertIs(type(source), model.Event)
        self.assertIs(type(document.measurement), model.DocumentMeasurementContext)
        source.evidence = model.EventEvidence(opaque_spans=((1, 3),))
        unchanged = deepcopy(source)
        timed = engine.replace_event(source, end='0:00:04.00', end_s=4.)
        self.assertIs(timed.state, source.state)
        self.assertIs(timed.evidence, source.evidence)
        painted = engine.replace_event(source, text=r'{\fs30}Hello')
        self.assertIs(type(painted), model.Event)
        self.assertEqual(painted.state['fs'], 30)
        self.assertIsNot(painted.state, source.state)
        self.assertIsNone(painted.evidence.opaque_spans)
        self.assertEqual(vars(source), vars(unchanged))

    def test_pickle_roundtrip_and_legacy_engine_class_lookup(self):
        for name in NAMES:
            legacy = ('csimplify_ass\n' + name + '\n.').encode()
            self.assertIs(pickle.loads(legacy), getattr(model, name))
        source = event(); source.evidence = model.EventEvidence(opaque_spans=((1, 3),))
        result = pickle.loads(pickle.dumps(source))
        self.assertIs(type(result), model.Event)
        self.assertIs(type(result.evidence), model.EventEvidence)
        self.assertIs(type(result.measurement), model.DocumentMeasurementContext)
        self.assertEqual(vars(result), vars(source))

    def test_installed_classes_document_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = load_installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            unrelated = root/'unrelated'; unrelated.mkdir()
            source = unrelated/'input.ass'; source.write_text(HEADER)
            code = ('import sys\nfrom pathlib import Path\nfrom dataclasses import replace,fields\n'
                'sys.path.insert(0,' + repr(str(tools)) + ')\nimport simplify_ass as s\n'
                'from _simplify_ass import event_model as m\n'
                "assert Path(m.__file__).resolve()==Path(s.__file__).resolve().parent/'_simplify_ass/event_model.py'\n"
                'for name in ' + repr(NAMES) + ': assert getattr(s,name) is getattr(m,name)\n'
                'document=s._resolve_document_state(s.read_subtitle_document(Path(' + repr(str(source)) + ')))\n'
                'original=next(iter(document.events.values()))\n'
                'assert type(original) is m.Event and type(document.measurement) is m.DocumentMeasurementContext\n'
                'assert type(original.evidence) is m.EventEvidence\n'
                'assert type(replace(original,end_s=4)) is m.Event\n'
                'assert next(f for f in fields(s.SubtitleDocument) if f.name=="measurement").default_factory is m.DocumentMeasurementContext\n')
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=unrelated,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            env = os.environ.copy(); env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, str(tools/'simplify_ass.py'), str(source), '--no-font-spacing'],
                                    cwd=unrelated, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = engine.load_subtitle_events(source.with_name('input.simple.ass'))[1]
            self.assertEqual(len(output), 1)
            self.assertEqual(engine.OVERRIDE_RE.sub('', output[0].text), 'Hello')
            self.assertEqual((output[0].start_s, output[0].end_s), (1, 3))
            self.assertTrue(list((tools/'_simplify_ass/__pycache__').glob('event_model.*.pyc')))
            keep = tools/'keep.txt'; keep.write_text('user')
            owner.remove(target)
            self.assertFalse((tools/'_simplify_ass').exists())
            self.assertEqual(keep.read_text(), 'user')


if __name__ == '__main__':
    unittest.main()
