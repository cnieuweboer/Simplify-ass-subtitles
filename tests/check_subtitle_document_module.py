"""Document-module identity, ownership, serialized boundaries and installed I/O."""
import test_paths
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
from typing import get_type_hints
import codecs
import os
import pickle
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import subtitle_document as document
from check_windows_installer import load_installer, ROOT

FUNCTIONS = ('parse_time', 'format_time', 'peak_concurrent_events', 'parse_dialogue',
    'read_subtitle', 'script_resolution', 'parse_subtitle_document',
    'read_subtitle_document', '_resolve_document_state', 'mark_generated',
    'render_subtitle_document', 'write_subtitle_document', 'load_subtitle_events')
NAMES = ('SubtitleDocument', 'EVENT_FIELDS', 'GENERATED_MARKER', *FUNCTIONS)
HEADER = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n'
    'WrapStyle: 2\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,Alignment\n'
    'Style: Default,Arial,20,2\n[Events]\n'
    'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n')
LINE = 'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello'


class SubtitleDocumentModuleChecks(unittest.TestCase):
    def test_aliases_annotations_and_factory_use_canonical_records(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(document, name))
        for name in ('SubtitleDocument', *FUNCTIONS):
            get_type_hints(getattr(document, name))
        self.assertIs(document.Event, engine.Event)
        self.assertIs(document.DocumentMeasurementContext, engine.DocumentMeasurementContext)
        self.assertIs(get_type_hints(engine._prepare_text_document)['document'], document.SubtitleDocument)
        self.assertIs(get_type_hints(engine._normalize_text_result)['return'], document.SubtitleDocument)
        factory = next(f for f in fields(document.SubtitleDocument) if f.name == 'measurement').default_factory
        self.assertIs(factory, engine.DocumentMeasurementContext)
        fallback = document.parse_subtitle_document('[Script Info]\n[Events]\n' + LINE)
        self.assertIs(fallback.fields, document.EVENT_FIELDS)
        self.assertEqual(tuple(fallback.fields), tuple(engine.EVENT_FIELDS))

    def test_independent_import_and_processing_need_no_engine_or_optional_backend(self):
        code = ('import sys\nfrom typing import get_type_hints\n'
            'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
            'from _simplify_ass import subtitle_document as d\n'
            "assert 'simplify_ass' not in sys.modules\n"
            "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n"
            'for name in ' + repr(('SubtitleDocument', *FUNCTIONS)) + ': get_type_hints(getattr(d,name))\n'
            'parsed=d.parse_subtitle_document(' + repr(HEADER + LINE + '\n') + ')\n'
            'resolved=d._resolve_document_state(parsed)\n'
            'assert type(resolved) is d.SubtitleDocument\n'
            'assert not next(iter(parsed.events.values())).state\n'
            'assert next(iter(resolved.events.values())).state["fs"]==20\n'
            'assert d.render_subtitle_document(resolved,resolved.events.values()).endswith("Hello\\n")\n')
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=folder,
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_resolution_preserves_deliberate_sharing_and_isolates_source_caches(self):
        parsed = document.parse_subtitle_document(HEADER + LINE)
        source = next(iter(parsed.events.values()))
        source.evidence = engine.EventEvidence(opaque_spans=((1., 3.),))
        before = deepcopy(parsed)
        resolved = document._resolve_document_state(parsed)
        event = next(iter(resolved.events.values()))
        self.assertEqual(parsed, before)
        self.assertIsNot(resolved, parsed)
        self.assertIs(resolved.lines, parsed.lines)
        self.assertIs(resolved.fields, parsed.fields)
        self.assertIsNot(resolved.events, parsed.events)
        self.assertIsNot(event, source)
        self.assertIsNot(resolved.styles, parsed.styles)
        for name in parsed.styles:
            self.assertIsNot(resolved.styles[name], parsed.styles[name])
        self.assertIs(event.styles, resolved.styles)
        self.assertIs(event.defaults, resolved.styles['Default'])
        self.assertIs(event.evidence, source.evidence)
        self.assertIs(event.measurement, resolved.measurement)
        self.assertIsNone(parsed.measurement.script_wrap_mode)
        self.assertEqual(resolved.measurement.script_wrap_mode, 2)
        self.assertEqual(resolved.measurement.canvas, (640., 360.))
        self.assertFalse(source.state)
        event.state['fs'] = 999
        event.styles['Default']['fs'] = 500
        self.assertEqual(parsed, before)
        self.assertEqual(source.defaults['fs'], 20)

    def test_ssa_fields_metadata_comments_literal_separators_and_newlines(self):
        raw = ('[Script Info]\r\nTitle: retained\r\n[Events]\r\n'
            'Format: Marked,Start,End,Style,Actor,MarginL,MarginR,MarginV,Effect,Text\r\n'
            'Comment: Marked=0,0:00:00.00,0:00:01.00,Default,Note,0,0,0,,comment\r\n'
            'Dialogue: Marked=0,0:00:01.00,0:00:03.00,Default,Speaker,0,0,0,,A\u2028B\r\n'
            '[Other]\r\nKeep: metadata\r\n\r\n')
        parsed = document.parse_subtitle_document(raw); before = deepcopy(parsed)
        events = list(parsed.events.values())
        self.assertEqual([e.kind for e in events], ['Comment', 'Dialogue'])
        self.assertEqual(events[1].name, 'Speaker')
        self.assertEqual(events[1].text, 'A\u2028B')
        for index, event in parsed.events.items():
            self.assertEqual(event.source_index, index)
            self.assertTrue(parsed.lines[index].startswith(event.kind + ':'))
        output = document.render_subtitle_document(parsed, iter(events))
        self.assertNotIn('\r', output)
        self.assertIn('Title: retained\n', output)
        self.assertIn('Default,Speaker,0,0,0,,A\u2028B\n', output)
        self.assertTrue(output.endswith('[Other]\nKeep: metadata\n\n'))
        self.assertEqual(output.count(document.GENERATED_MARKER), 1)
        reparsed = document.parse_subtitle_document(output)
        self.assertEqual([e.fields() for e in reparsed.events.values()], [e.fields() for e in events])
        final = document.render_subtitle_document(parsed, events, final_newline=True)
        self.assertTrue(final.endswith('metadata\n'))
        self.assertFalse(final.endswith('\n\n'))
        self.assertEqual(parsed, before)

    def test_strict_decoding_errors_and_explicit_output_encoding(self):
        text = HEADER + LINE.replace('Hello', 'Café') + '\n'
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.ass'; output = Path(folder)/'output.ass'
            for encoding in ('utf-8-sig', 'utf-16', 'utf-32'):
                source.write_bytes(text.encode(encoding))
                self.assertEqual(document.read_subtitle(source), text)
            source.write_bytes(text.encode('cp1252'))
            with self.assertRaisesRegex(ValueError, 'cannot decode as utf-8-sig'):
                document.read_subtitle(source)
            self.assertEqual(document.read_subtitle(source, 'cp1252'), text)
            source.write_bytes(b'A\x00B')
            with self.assertRaisesRegex(ValueError, 'NUL characters'):
                document.read_subtitle(source)
            source.write_bytes(text.encode('utf-8'))
            before = source.read_bytes()
            parsed = document.read_subtitle_document(source)
            document.write_subtitle_document(output, parsed, parsed.events.values())
            self.assertTrue(output.read_bytes().startswith(codecs.BOM_UTF8))
            self.assertEqual(source.read_bytes(), before)
            self.assertIn('Café', document.read_subtitle(output))

    def test_concurrency_uses_serialized_half_open_intervals(self):
        first = document.parse_dialogue(LINE, 1)
        left = replace(first, end='0:00:02.00', start_s=0., end_s=100.)
        right = replace(first, start='0:00:02.00', source_index=2, start_s=0., end_s=100.)
        comment = replace(first, kind='Comment', source_index=3)
        reversed_time = replace(first, start='0:00:03.00', end='0:00:01.00', source_index=4)
        self.assertEqual(document.peak_concurrent_events(iter([left, right, comment, reversed_time])), 1)
        overlap = replace(first, start='0:00:01.50', end='0:00:02.50', source_index=5)
        self.assertEqual(document.peak_concurrent_events([left, right, overlap]), 2)
        self.assertEqual(document.peak_concurrent_events([left, right]), 1)

    def test_document_stays_mutable_and_pickle_lookup_uses_canonical_class(self):
        parsed = document.parse_subtitle_document(HEADER + LINE)
        self.assertFalse(document.SubtitleDocument.__dataclass_params__.frozen)
        parsed.peak = 5
        self.assertEqual(parsed.peak, 5)
        self.assertIs(pickle.loads(b'csimplify_ass\nSubtitleDocument\n.'), document.SubtitleDocument)
        restored = pickle.loads(pickle.dumps(parsed))
        self.assertEqual(restored, parsed)
        self.assertIs(type(restored), document.SubtitleDocument)
        self.assertIs(type(restored.measurement), engine.DocumentMeasurementContext)

    def test_installed_document_io_cli_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = load_installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            unrelated = root/'unrelated'; unrelated.mkdir()
            source = unrelated/'input.ass'; source.write_bytes((HEADER + LINE + '\n').encode('utf-16'))
            before = source.read_bytes()
            code = ('import sys\nfrom pathlib import Path\nfrom dataclasses import fields\n'
                'sys.path.insert(0,' + repr(str(tools)) + ')\nimport simplify_ass as e\n'
                'from _simplify_ass import subtitle_document as d\n'
                "assert Path(d.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/subtitle_document.py'\n"
                'for name in ' + repr(NAMES) + ': assert getattr(e,name) is getattr(d,name)\n'
                'assert next(f for f in fields(d.SubtitleDocument) if f.name=="measurement").default_factory is e.DocumentMeasurementContext\n'
                'original=d.read_subtitle_document(Path(' + repr(str(source)) + '))\n'
                'assert type(original) is d.SubtitleDocument\n'
                'resolved=d._resolve_document_state(original)\n'
                'assert not next(iter(original.events.values())).state\n'
                'assert next(iter(resolved.events.values())).state["fs"]==20\n'
                'assert resolved.measurement.script_wrap_mode==2\n'
                'd.write_subtitle_document(Path(' + repr(str(unrelated/'rendered.ass')) + '),resolved,resolved.events.values())\n')
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=unrelated,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            env = os.environ.copy(); env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, str(tools/'simplify_ass.py'), str(source), '--no-font-spacing'],
                                    cwd=unrelated, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = document.load_subtitle_events(source.with_name('input.simple.ass'))[1]
            self.assertEqual(len(output), 1)
            self.assertEqual(engine.OVERRIDE_RE.sub('', output[0].text), 'Hello')
            self.assertEqual((output[0].start_s, output[0].end_s), (1, 3))
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(list((tools/'_simplify_ass/__pycache__').glob('subtitle_document.*.pyc')))
            keep = tools/'keep.txt'; keep.write_text('user')
            owner.remove(target)
            self.assertFalse((tools/'_simplify_ass').exists())
            self.assertEqual(keep.read_text(), 'user')


if __name__ == '__main__':
    unittest.main()
