"""Shared effect proofs preserve strict timing and borrowed source evidence."""
import test_paths
from copy import deepcopy
import inspect
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
from typing import get_type_hints
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import effect_validation as validation
from check_windows_installer import ROOT, load_installer

NAMES = ('parse_effect_transform', 'parse_effect_move')
PAYLOAD = r'\alpha&H80&'
CHANGES = [('alpha', '&H80&')]

COLD_CODE = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import effect_validation as v, event_operations as o, subtitle_document as d
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
allowed = {'alpha'}
changes = [('alpha', '&H80&')]
before = deepcopy((allowed, changes))
assert v.parse_effect_transform(r'(\alpha&H80&)', 1, allowed) == (0, 1000, changes)
assert v.parse_effect_transform(r'(0,1000,2,\alpha&H80&)', 1, allowed, parsed_changes=changes)[2] is changes
assert (allowed, changes) == before
assert v.parse_effect_transform(r'(500,500,\alpha&H80&)', 1, allowed) is None
assert v.parse_effect_transform(r'(500,500,\alpha&H80&)', 1, allowed, allow_instant=True)[:2] == (500, 500)
assert v.parse_effect_transform(r'(0,1051,\alpha&H80&)', 1, allowed) is None
assert v.parse_effect_transform(r'(0,1051,\alpha&H80&)', 1, allowed, allow_after_end=True) is not None
assert v.parse_effect_move('(1,2,3,4)', 1) == [1., 2., 3., 4.]
assert v.parse_effect_move('(1,2,3,4,0,1040)', 1) is None
assert v.parse_effect_move('(1,2,3,4,0,1040)', 1, endpoint_slack=50)[-1] == 1040.
duration = 2.4 - 2.0
assert v.parse_effect_move('(0,0,60,0,0,400)', duration)[-1] == 400
assert v.parse_effect_move('(0,0,60,0,0,450)', duration, endpoint_slack=50)[-1] == 450
assert v.parse_effect_transform(r'(0,450,\alpha&H80&)', duration, allowed)[:2] == (0, 450)
assert v.parse_effect_move('(0,0,60,0,0,400.00001)', duration) is None
assert v.parse_effect_transform(r'(0,450.00001,\alpha&H80&)', duration, allowed) is None
raw = '[Events]\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,'
raw += r'{\rOther\fnTest}A{\t(0,1000,\alpha&H80&)}B{\fn}' + '\n'
event = next(iter(d.parse_subtitle_document(raw).events.values()))
before = deepcopy(vars(event))
expected = [('r', 'Other'), ('fn', 'Test'), ('t', r'(0,1000,\alpha&H80&)'), ('fn', '')]
tokens = o.event_override_tokens(event)
assert tokens == expected and vars(event) == before
tokens.clear()
assert o.event_override_tokens(event) == expected and vars(event) == before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as engine
assert engine.parse_effect_transform is v.parse_effect_transform
assert engine.parse_effect_move is v.parse_effect_move
assert engine.event_override_tokens is o.event_override_tokens
assert Path(v.__file__).resolve() == Path(engine.__file__).resolve().parent/'_simplify_ass/effect_validation.py'
import py_compile
py_compile.compile(v.__file__, doraise=True)
py_compile.compile(o.__file__, doraise=True)
'''


class EffectValidationModuleChecks(unittest.TestCase):
    def test_canonical_aliases_annotations_defaults_and_old_root_lookup(self):
        for name in NAMES:
            function = getattr(validation, name)
            self.assertIs(function, getattr(engine, name))
            get_type_hints(function)
            self.assertIs(pickle.loads(('csimplify_ass\n' + name + '\n.').encode()), function)
            self.assertIs(pickle.loads(pickle.dumps(function)), function)
        signature = inspect.signature(validation.parse_effect_transform)
        for name, default in (('allow_instant', False), ('allow_after_end', False), ('parsed_changes', None)):
            self.assertIs(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(signature.parameters[name].default, default)
        self.assertEqual(inspect.signature(validation.parse_effect_move).parameters['endpoint_slack'].default, 0)

    def test_four_transform_forms_retain_timing_and_raw_changes(self):
        for arguments, interval in (('', (0, 2000)), ('2,', (0, 2000)),
                                    ('100,1800,', (100, 1800)), ('100,1800,2,', (100, 1800))):
            with self.subTest(arguments=arguments):
                self.assertEqual(validation.parse_effect_transform('(' + arguments + PAYLOAD + ')', 2, {'alpha'}),
                                 (*interval, CHANGES))

    def test_transform_refusals_preserve_allowed_tags_and_finite_forward_timing(self):
        cases = [r'(0,1000,\bord2)', r'(nan,1000,\alpha&H80&)',
                 r'(0,inf,\alpha&H80&)', r'(1000,0,\alpha&H80&)',
                 r'(-1,1000,\alpha&H80&)', r'(0,1000,0,\alpha&H80&)',
                 r'(-2,\alpha&H80&)', r'(0,1000,2,3,\alpha&H80&)',
                 r'(bad,\alpha&H80&)', '(0,1000)']
        for value in cases:
            with self.subTest(value=value):
                self.assertIsNone(validation.parse_effect_transform(value, 1, {'alpha'}))

    def test_transform_endpoint_rounding_and_opt_ins_are_independent(self):
        self.assertIsNotNone(validation.parse_effect_transform('(0,1050,' + PAYLOAD + ')', 1, {'alpha'}))
        beyond = '(0,1050.01,' + PAYLOAD + ')'
        self.assertIsNone(validation.parse_effect_transform(beyond, 1, {'alpha'}))
        self.assertIsNotNone(validation.parse_effect_transform(beyond, 1, {'alpha'}, allow_after_end=True))
        instant = '(500,500,' + PAYLOAD + ')'
        self.assertIsNone(validation.parse_effect_transform(instant, 1, {'alpha'}))
        self.assertIsNotNone(validation.parse_effect_transform(instant, 1, {'alpha'}, allow_instant=True))
        self.assertIsNone(validation.parse_effect_transform(instant, 1, {'alpha'}, allow_after_end=True))
        self.assertIsNone(validation.parse_effect_transform('(-1,2000,' + PAYLOAD + ')', 1, {'alpha'}, allow_after_end=True))

    def test_supplied_changes_are_borrowed_without_retokenizing_or_caching(self):
        changes = [('alpha', '&H80&'), ('alpha', '&H20&')]
        allowed = {'alpha'}; before = deepcopy((changes, allowed))
        value = '(0,1000,' + PAYLOAD + ')'
        with patch.object(validation, 'tokenize_override', side_effect=AssertionError('Reparsed borrowed payload')):
            self.assertIs(validation.parse_effect_transform(value, 1, allowed, parsed_changes=changes)[2], changes)
            self.assertIsNone(validation.parse_effect_transform(value, 1, set(), parsed_changes=changes))
        self.assertEqual((changes, allowed), before)
        first = validation.parse_effect_transform(value, 1, allowed)[2]
        first.clear()
        self.assertEqual(validation.parse_effect_transform(value, 1, allowed)[2], CHANGES)

    def test_move_coordinates_and_caller_slack_are_not_normalized(self):
        self.assertEqual(validation.parse_effect_move('(-1,2,3.5,-4)', 1), [-1., 2., 3.5, -4.])
        self.assertEqual(validation.parse_effect_move('(1,2,3,4,0,1000)', 1), [1., 2., 3., 4., 0., 1000.])
        rounded = '(1,2,3,4,0,1050)'
        self.assertIsNone(validation.parse_effect_move(rounded, 1))
        self.assertIsNotNone(validation.parse_effect_move(rounded, 1, endpoint_slack=50))
        self.assertIsNone(validation.parse_effect_move('(1,2,3,4,0,1050.01)', 1, endpoint_slack=50))
        first = validation.parse_effect_move('(1,2,3,4)', 1)
        first[0] = 99
        self.assertEqual(validation.parse_effect_move('(1,2,3,4)', 1), [1., 2., 3., 4.])

    def test_move_refuses_nonfinite_coordinates_and_invalid_timing(self):
        for value in ('(0,0,nan,2)', '(inf,0,1,2)', '(0,0,1)', '(0,0,1,2,3)',
                      '(0,0,1,2,10,0)', '(0,0,1,2,0,0)', '(0,0,1,2,-1,1000)', '(bad,0,1,2)'):
            with self.subTest(value=value):
                self.assertIsNone(validation.parse_effect_move(value, 1))

    def test_subtracted_cue_times_accept_exact_endpoints_without_retiming(self):
        for start, end in ((2., 2.4), (1320.2, 1320.6), (7200.2, 7200.6),
                           (86400.2, 86400.6)):
            duration = end - start
            with self.subTest(start=start, end=end):
                self.assertEqual(validation.parse_effect_move('(0,0,60,0,0,400)', duration),
                                 [0., 0., 60., 0., 0., 400.])
                self.assertEqual(validation.parse_effect_move('(0,0,60,0,0,450)', duration,
                                                             endpoint_slack=50),
                                 [0., 0., 60., 0., 0., 450.])
                changes = list(CHANGES)
                parsed = validation.parse_effect_transform('(0,450,' + PAYLOAD + ')', duration,
                                                           {'alpha'}, parsed_changes=changes)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed[:2], (0., 450.))
                self.assertIs(parsed[2], changes)

    def test_rounding_allowance_rejects_actual_overruns_without_relative_tolerance(self):
        for duration, milliseconds in ((2.4-2., 400.), (86400., 86400000.)):
            for overrun in (.00001, .01, 1.):
                with self.subTest(duration=duration, overrun=overrun):
                    end = milliseconds + overrun
                    self.assertIsNone(validation.parse_effect_move(f'(0,0,60,0,0,{end:.8f})', duration))
                    end += 50
                    self.assertIsNone(validation.parse_effect_move(f'(0,0,60,0,0,{end:.8f})', duration,
                                                                  endpoint_slack=50))
                    self.assertIsNone(validation.parse_effect_transform(
                        f'(0,{end:.8f},' + PAYLOAD + ')', duration, {'alpha'}))
        self.assertIsNone(validation.parse_effect_move('(0,0,60,0,-0.0000001,400)', 2.4-2.))
        self.assertIsNone(validation.parse_effect_move('(0,0,60,0,400,400)', 2.4-2.))
        self.assertIsNone(validation.parse_effect_transform(
            '(-0.0000001,400,' + PAYLOAD + ')', 2.4-2., {'alpha'}))

    def test_cold_source_and_installed_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            owner = load_installer(); target = root/'installed tools with spaces'
            _, installed = owner.install(ROOT, target, individual_launchers=False)
            for tools in (ROOT, installed):
                child = subprocess.run([sys.executable, '-I', '-c',
                    'import sys\nsys.path.insert(0,' + repr(str(tools)) + ')\n' + COLD_CODE],
                    cwd=unrelated, capture_output=True, text=True)
                self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
            user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
            owner.remove(target)
            self.assertEqual(user.read_text(), '# user\n')
            for name in ('effect_validation', 'event_operations'):
                self.assertFalse((installed/'_simplify_ass'/f'{name}.py').exists())
                self.assertFalse(any((installed/'_simplify_ass').rglob(f'{name}*.pyc')))


if __name__ == '__main__':
    unittest.main()
