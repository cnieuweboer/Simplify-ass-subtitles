"""Interpreter imports, canonical bindings, ownership and installed isolation."""
import test_paths
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
import os
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import ass_overrides as parser
from override_module_test_helpers import patch_interpreter_bindings
from check_windows_installer import load_installer, ROOT


class OverrideModuleChecks(unittest.TestCase):
    def child(self, code, directory, tools):
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONPYCACHEPREFIX', None)
        result = subprocess.run([sys.executable, '-c',
            'import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+code],
            cwd=directory, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return result

    def test_public_names_alias_the_actual_records_functions_and_constants(self):
        for name in ('OverrideContinuation','OverrideEvaluation','tokenize_override',
                     'resolve_event_style','parse_styles','apply_font_size','apply_override',
                     'evaluate_effective_state','effective_state','OVERRIDE_RE','TAG_NAMES',
                     'TAG_RE','NUMBER','DEFAULT_STATE','STYLE_TAGS'):
            self.assertIs(getattr(engine, name), getattr(parser, name), name)
        history = parser.OverrideContinuation()
        result = parser.OverrideEvaluation({}, history)
        for obj, name in [(history, 'reset_style'), (result, 'formatting')]:
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, name, None)
        result.formatting['fs'] = 30
        self.assertEqual(result.formatting['fs'], 30)  # Frozen binding, owned dict.

    def test_standalone_interpreter_import_needs_only_the_standard_library(self):
        with tempfile.TemporaryDirectory() as folder:
            self.child("from _simplify_ass import ass_overrides as p\n"
                "assert 'simplify_ass' not in sys.modules\n"
                "assert '_simplify_ass.font_metrics' not in sys.modules\n"
                "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n"
                "assert p.effective_state(r'{\\fs30}')['fs']==30\n", folder, ROOT)

    def test_recognized_syntax_and_output_policy_have_separate_contracts(self):
        self.assertTrue(engine.SAFE_SIMPLE_TAGS <= set(parser.TAG_NAMES))
        self.assertFalse(hasattr(parser, 'SAFE_SIMPLE_TAGS'))
        for name in parser.TAG_NAMES:
            self.assertEqual(parser.tokenize_override('\\'+name.upper()+'123'), [(name, '123')])
        self.assertEqual([name for name, _ in parser.tokenize_override(
            r'\fscx120\fs20\frz5\fr6\iclip(0,0,2,2)\clip(1,1,3,3)')],
            ['fscx','fs','frz','fr','iclip','clip'])
        self.assertTrue({'t','move','fade','alpha','kf'} <= set(parser.TAG_NAMES)-engine.SAFE_SIMPLE_TAGS)

    def test_supplied_tokens_and_history_preserve_borrowed_input_ownership(self):
        default = {**parser.DEFAULT_STATE, 'fs': 24}
        styles = MappingProxyType({'Default': MappingProxyType(default),
            'Other': MappingProxyType({**default, 'fs': 40})})
        text = r'{\rOther\fs+2}A{\an0\r\an7\fs+1}B'
        expected = parser.evaluate_effective_state(text, default, styles)
        tokens = tuple(t for b in parser.OVERRIDE_RE.findall(text) for t in parser.tokenize_override(b))
        with patch_interpreter_bindings(engine, 'tokenize_override', side_effect=AssertionError('reparsed')):
            actual = engine.evaluate_effective_state(text, default, styles, tokens=iter(tokens))
        self.assertEqual(actual, expected)
        self.assertEqual(default['fs'], 24)
        self.assertIsNot(actual.formatting, default)
        self.assertEqual(actual.continuation.alignment_set, True)
        self.assertEqual(actual.continuation.reset_style, '')

    def test_call_instrumentation_observes_both_bindings_and_deduplicates_owner(self):
        with patch_interpreter_bindings(engine, 'tokenize_override', wraps=engine.tokenize_override) as observed:
            engine.tokenize_override(r'\fs20')
            engine.evaluate_effective_state(r'{\\fs30}')
        self.assertEqual(observed.call_count, 2)
        with patch_interpreter_bindings(parser, 'tokenize_override', wraps=parser.tokenize_override) as observed:
            parser.evaluate_effective_state(r'{\\fs30}')
        self.assertEqual(observed.call_count, 1)

    def test_installed_engine_uses_its_interpreter_and_uninstalls_owned_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = load_installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            unrelated = root/'unrelated working directory'; unrelated.mkdir()
            self.child("from pathlib import Path\nimport simplify_ass as s\n"
                "from _simplify_ass import ass_overrides as p\n"
                "assert s.apply_override is p.apply_override\n"
                "assert s.OverrideContinuation is p.OverrideContinuation\n"
                "assert Path(p.__file__).resolve()==Path(s.__file__).resolve().parent/'_simplify_ass/ass_overrides.py'\n"
                "assert s.effective_state(r'{\\fs30\\r\\fs+2}')['fs']==24\n", unrelated, tools)
            source = unrelated/'input.ass'
            source.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n'
                '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,Outline,Alignment\n'
                'Style: Default,Arial,20,&H00FFFFFF,&H00000000,2,2\n[Events]\n'
                'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
                'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\fs+2}Hello\n')
            env = os.environ.copy(); env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, str(tools/'simplify_ass.py'), str(source), '--no-font-spacing'],
                                    cwd=unrelated, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            events = engine.load_subtitle_events(source.with_name('input.simple.ass'))[1]
            self.assertEqual(len(events), 1)
            self.assertEqual(engine.OVERRIDE_RE.sub('', events[0].text), 'Hello')
            self.assertEqual((events[0].start_s, events[0].end_s), (1, 3))
            self.assertTrue(list((tools/'_simplify_ass/__pycache__').glob('ass_overrides.*.pyc')))
            keep = tools/'keep.txt'; keep.write_text('user')
            owner.remove(target)
            self.assertFalse((tools/'_simplify_ass').exists())
            self.assertEqual(keep.read_text(), 'user')


if __name__ == '__main__':
    unittest.main()
