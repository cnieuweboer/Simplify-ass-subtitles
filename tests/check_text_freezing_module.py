"""Text-freezing identity, borrowed evidence, serialization and installed use."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import get_type_hints
from unittest.mock import patch
import pickle
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import text_freezing as freezing
from check_windows_installer import load_installer, ROOT

NAMES = ('FrozenBlock', 'SAFE_SIMPLE_TAGS', 'safe_override', 'simplify_text',
         '_freeze_inputs', 'freeze_block', 'simplify_visual_text')


def child(code, cwd, tools):
    code = 'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + code
    return subprocess.run([sys.executable, '-I', '-c', code], cwd=cwd,
                          capture_output=True, text=True)


class TextFreezingModuleChecks(unittest.TestCase):
    def test_canonical_aliases_annotations_defaults_and_whitelist(self):
        for name in NAMES:
            self.assertIs(getattr(engine, name), getattr(freezing, name))
            if callable(getattr(freezing, name)):
                get_type_hints(getattr(freezing, name))
        self.assertIs(get_type_hints(freezing.FrozenBlock)['selection'], engine.StaticStateSelection)
        self.assertEqual([f.name for f in fields(freezing.FrozenBlock)], ['text', 'selection'])
        for name in ('freeze_block', '_freeze_inputs'):
            self.assertIs(type(getattr(freezing, name).__kwdefaults__['continuation']),
                          engine.OverrideContinuation)
        self.assertIs(freezing.select_static_state, engine.select_static_state)
        self.assertIs(freezing.render_tag, engine.render_tag)
        self.assertIs(freezing.DEFAULT_STATE, engine.DEFAULT_STATE)
        self.assertIsInstance(freezing.SAFE_SIMPLE_TAGS, set)

    def test_cold_processing_without_engine_or_optional_backends(self):
        code = r'''
from _simplify_ass import text_freezing as f
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
state={**f.DEFAULT_STATE,'fs':40,'pos':(10.,20.)}
result=f.freeze_block(r'\blur8\be4',1.,state,state,{},2.)
assert type(result) is f.FrozenBlock and result.selection.state['blur']==2.
assert r'\blur2' in result.text
assert f.simplify_text(r'A\NB',visible_only=True)==('', 'A B')
assert 'simplify_ass' not in sys.modules
'''
        with tempfile.TemporaryDirectory() as folder:
            result = child(code, folder, ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_borrowed_seeds_and_preclamp_snapshot_handoff(self):
        base = {**engine.DEFAULT_STATE, 'fs': 40, 'pos': (10., 20.)}
        styles = {'Other': {**base, 'fs': 50}}
        opaque = [(-100., 0.)]; seed = {'seed': True}; settled = [seed]
        before = deepcopy((base, styles, opaque, settled))
        result = freezing.freeze_block(r'\blur8\be4', 1., base, base, styles, 2., opaque, settled)
        self.assertEqual((base, styles, opaque, settled), before)
        self.assertIsNot(result.selection.state, base)
        self.assertIs(result.selection.settled_states[0], seed)
        self.assertEqual(result.selection.state['blur'], 2.)
        self.assertEqual(result.selection.settled_states[-1]['blur'], 8.)
        disabled = freezing.freeze_block('', 1., base, base, styles, 0.)
        self.assertIsNone(disabled.selection.opaque_spans)
        self.assertIsNone(disabled.selection.settled_states)

    def test_frozen_bindings_keep_selection_identity_and_pickle_lookup(self):
        base = {**engine.DEFAULT_STATE, 'fs': 40}
        selection = engine.select_static_state(base, [], {0., 1000.}, {}, base)
        result = freezing.FrozenBlock('', selection)
        self.assertIs(result.selection, selection)
        with self.assertRaises(FrozenInstanceError):
            result.text = 'replacement'
        result.selection.state['fs'] = 50
        self.assertEqual(base['fs'], 50)  # Existing selector early-return sharing.
        self.assertIs(pickle.loads(b'csimplify_ass\nFrozenBlock\n.'), freezing.FrozenBlock)
        restored = pickle.loads(pickle.dumps(result))
        self.assertIs(type(restored), freezing.FrozenBlock)
        self.assertIs(type(restored.selection), engine.StaticStateSelection)
        self.assertEqual(restored, result)

    def test_visible_only_path_bypasses_freezing(self):
        with patch.object(freezing, 'freeze_block', side_effect=AssertionError('unexpected freeze')):
            text, visible = freezing.simplify_text(r'{\p1}m 0 0 l 1 1{\p0}Words\Nhere', visible_only=True)
        self.assertEqual((text, visible), ('', 'Words here'))

    def test_drawing_accounting_and_safe_header_route(self):
        text = r'{\p1}m 0 0 l 1 1{\p0}Words'
        full, visible, count = freezing.simplify_visual_text(text, 0., level=2)
        self.assertIn('m 0 0 l 1 1', full)
        self.assertEqual(visible, 'Words')
        self.assertEqual(count, len('m 0 0 l 1 1'))
        simple, visible, count = freezing.simplify_visual_text(text, 0., level=1)
        self.assertNotIn('m 0 0 l 1 1', simple)
        self.assertEqual((visible, count), ('Words', 0))
        safe = freezing.safe_override(r'\p1\pbo2\bord3')
        self.assertNotIn(r'\p', safe)
        self.assertIn(r'\bord3', safe)

    def test_installed_freezing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = load_installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            unrelated = root/'unrelated'; unrelated.mkdir()
            code = r'''
from pathlib import Path
import py_compile
import simplify_ass as e
from _simplify_ass import text_freezing as f
assert Path(f.__file__).resolve()==Path(e.__file__).resolve().parent/'_simplify_ass/text_freezing.py'
for name in NAMES: assert getattr(e,name) is getattr(f,name)
assert type(f.freeze_block.__kwdefaults__['continuation']) is e.OverrideContinuation
state={**f.DEFAULT_STATE,'fs':40}
result=e.freeze_block(r'\blur8\be4',1.,state,state,{},2.,prior_settled_states=())
assert type(result) is f.FrozenBlock and type(result.selection) is e.StaticStateSelection
assert result.selection.state['blur']==2. and result.selection.settled_states[0]['blur']==8.
assert r'\blur2' in result.text
assert e.simplify_text(r'A\NB',visible_only=True)==('', 'A B')
py_compile.compile(f.__file__,doraise=True)
'''.replace('NAMES', repr(NAMES))
            result = child(code, unrelated, tools)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            user = tools/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            self.assertFalse((tools/'_simplify_ass/text_freezing.py').exists())
            self.assertFalse(any((tools/'_simplify_ass').rglob('text_freezing*.pyc')))


if __name__ == '__main__':
    unittest.main()
