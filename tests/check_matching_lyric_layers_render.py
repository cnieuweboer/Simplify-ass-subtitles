"""Assert complete-pipeline lyric-copy oracles and matching safety contracts."""
import test_paths
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import contextlib
import ast
import importlib.util
import io
import json
import runpy
import sys
import simplify_ass as s
from lyric_layer_fixtures import make_case

ROOT = Path(__file__).resolve().parents[1]
checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)


data = runpy.run_path(str(ROOT / 'validation/investigate_lyric_layer_niche.py'))
records = data['records']
check('all authored fixtures completed', len(records) == 22)
for case in records:
    name = case['name']
    for oracle, passed in case['results']['on']['oracle_checks'].items():
        check(name + ': ' + oracle, passed)
    expected = (0 if name.startswith('independent-') or name in
                ('ordinary-full-line', 'equal-timing', 'overlap-79') else
                3 if name == 'words' else 4 if name == 'syllables' else 12)
    check(name + ': intended removals', case['results']['on']['statistics']['overlap_removed'] == expected)
    if name.startswith('independent-'):
        check(name + ': disabling safe filter leaves same output', not case['output_changed'])

# Capture a real pass input, after normal preparation, rather than assigning
# synthetic lyric flags. Then exercise proof guards and borrowed ownership.
fixture = make_case('guard-input', data['metrics'], data['DEST'])
captured = []
original = s.collapse_matching_lyric_layers


def capture(events, visible, font_metrics=None):
    captured.append(deepcopy((events, visible)))
    return original(events, visible, font_metrics)


with patch.object(s, 'collapse_matching_lyric_layers', capture), contextlib.redirect_stdout(io.StringIO()):
    s.simplify_ass(fixture['source'], data['DEST'] / 'guard-output.ass', s.SimplifyConfig(),
                   font_metrics=data['metrics'])
events, visible = captured[0]
before = deepcopy((events, visible))
out, removed = original(events, visible, data['metrics'])
check('real captured input reduces complete row', removed == 12)
check('target pass idempotent on its own output', original(out, visible, data['metrics'])[1] == 0)
check('source events caches continuations and visibility unmodified',
      [vars(e) for e in events] == [vars(e) for e in before[0]] and visible == before[1])
check('missing metrics conservatively retains all', original(events, visible) == (events, 0))
with patch.object(data['metrics'], 'available', False):
    check('unavailable metrics conservatively retains all',
          original(events, visible, data['metrics']) == (events, 0))
reversed_out, n = original(list(reversed(events)), visible, data['metrics'])
check('input order does not change retained captions or count', n == removed and
      sorted(e.fields() for e in reversed_out) == sorted(e.fields() for e in out))

fragment = next(e for e in events if len(visible[e.source_index]) == 1)
for label, tags in [
    ('different fill', r'\1c&H00FF00&'),
    ('different outline', r'\3c&HFF0000&'),
    ('partial alpha', r'\1a&H80&'),
    ('inline formatting', ''),
    ('clip', r'\clip(0,0,640,360)'),
    ('shear', r'\fax0.3'),
    ('rotation', r'\frz12'),
    ('live fade', r'\fad(100,100)'),
    ('live movement', r'\move(100,100,110,100)'),
    ('live transform', r'\t(0,100,\fs45)'),
]:
    altered = (fragment.text + r'{\1c&H00FF00&}X' if label == 'inline formatting' else
               fragment.text.replace('}', tags + '}', 1))
    replacement = s.replace_event(fragment, text=altered)
    modified = [replacement if e is fragment else e for e in events]
    output, n = original(modified, visible, data['metrics'])
    check(label + ': entire incomplete/unsupported phase retained', n == 0 and output == modified)

for label, replacement in [
    ('nonfinite time', s.dataclass_replace(fragment, start_s=float('nan'))),
    ('nonfinite position', s.dataclass_replace(fragment, text=r'{\pos(1e999,100)}T')),
    ('missing glyph', None),
]:
    modified = [replacement if e is fragment else e for e in events if e is not fragment or replacement is not None]
    output, n = original(modified, visible, data['metrics'])
    check(label + ': no partial deletion', n == 0)

for key, value in [('fs', float('nan')), ('fscx', float('inf')),
                   ('fscy', -100), ('an', 10), ('fax', .3)]:
    replacement = s.dataclass_replace(fragment, state=dict(fragment.state, **{key:value}))
    modified = [replacement if e is fragment else e for e in events]
    check('invalid cached ' + key + ': no removal or crash', original(modified, visible, data['metrics'])[1] == 0)
with patch.object(data['metrics'], 'matching_face', return_value=None):
    check('unresolved exact font retains complete group', original(events, visible, data['metrics'])[1] == 0)

# Two independently proven fragment phases must accumulate their entrance/exit,
# rather than the later extension overwriting the first one's timing.
lines = [e for e in events if len(visible[e.source_index]) > 1]
pieces = [e for e in events if len(visible[e.source_index]) == 1]
phases, phase_visible = list(lines), dict(visible)
for offset, (start, end) in enumerate(((.9, 3.9), (1.1, 4.1))):
    for e in pieces:
        identifier = e.source_index + 1000*(offset+1)
        phases.append(s.replace_event(e, start=s.format_time(start), end=s.format_time(end),
                                     start_s=start, end_s=end, source_index=identifier))
        phase_visible[identifier] = visible[e.source_index]
output, n = original(phases, phase_visible, data['metrics'])
check('multiple proofs accumulate readable exposure', n == 24 and
      any(e.start_s == .9 and e.end_s == 4.1 for e in output))

# A frozen pre-fix engine documents the five failures without modifying its
# behavior. Full fixture outputs above are independently checked against oracles.
spec = importlib.util.spec_from_file_location('lyric_layers_v181', ROOT / 'tests/references/simplify_ass_v181.py')
reference = importlib.util.module_from_spec(spec);sys.modules[spec.name] = reference;spec.loader.exec_module(reference)
check('pre-fix captured positive proof reaches old filter', reference.collapse_matching_lyric_layers(events, visible)[1] == 12)
from executable_ast_audit import executable_ast
def definitions(path):
    return {node.name: node for node in executable_ast(ast.parse(path.read_text())).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
old = definitions(ROOT / 'tests/references/simplify_ass_v181.py')
new = definitions(ROOT / 'simplify_ass.py')
check('no unrelated runtime definitions added or removed', old.keys() == new.keys())
check('runtime changes limited to matching pass and font dependency wiring',
      {name for name in old if ast.dump(old[name]) != ast.dump(new[name])} ==
      {'collapse_matching_lyric_layers', '_consolidate_text_events'})

report = dict(version=s.__version__, checks=len(checks), completed=22,
              global_second_pass_changes={mode: sum(not c['results'][mode]['byte_idempotent'] for c in records)
                                          for mode in ('on', 'off')})
(ROOT / 'validation/matching-lyric-layer-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(len(checks), 'matching lyric layer checks passed; separate pipeline second-pass issue remains recorded')
