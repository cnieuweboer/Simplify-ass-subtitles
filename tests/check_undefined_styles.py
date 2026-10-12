"""Regression checks for event-style fallback and explicit override retention."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import contextlib
import io
import json
import math
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simplify_ass as s
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(s)

root = Path(__file__).resolve().parents[1]
header = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: Large,Arial,60,&H0000FFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: Sign,Arial,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: sign,Arial,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

default_line = next(line for line in header.splitlines() if line.startswith('Style: Default,'))

def with_default(**fields):
    names = ('Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,'
             'Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,'
             'Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding').split(',')
    values = dict(zip(names, default_line.removeprefix('Style: ').split(',')))
    values.update({k: str(v) for k, v in fields.items()})
    return header.replace(default_line, 'Style: ' + ','.join(values[n] for n in names))

def event(text, style='Missing', count=1):
    return (f'Dialogue: 0,0:00:01.00,0:00:04.00,{style},,0,0,0,,{text}\n') * count

# The last entry in each tuple is a field which must retain its explicit value.
cases = [
    ('reviewed-reset', header, 'Missing', r'{\pos(320,180)\fs20}Reset {\r}default size', 1, None),
    ('explicit-size', header, 'Missing', r'{\pos(320,180)\fs20}Size', 1, ('fs', 20)),
    ('redundant-size', header, 'Missing', r'{\pos(320,180)\fs40}Size', 1, ('fs', 40)),
    ('relative-size', header, 'Missing', r'{\pos(320,180)\fs+2}Size', 1, ('fs', 48)),
    ('explicit-font', with_default(Fontname='Times New Roman'), 'Missing', r'{\pos(320,180)\fnArial}Font', 1, ('fn', 'Arial')),
    ('explicit-colour', with_default(PrimaryColour='&H000000FF'), 'Missing', r'{\pos(320,180)\1c&HFFFFFF&}Colour', 1, ('1c', 'FFFFFF')),
    ('explicit-bold', with_default(Bold=-1), 'Missing', r'{\pos(320,180)\b0}Weight', 1, ('b', 0)),
    ('explicit-outline', with_default(Outline=4), 'Missing', r'{\pos(320,180)\bord0}Outline', 1, ('bord', 0)),
    ('explicit-shadow', with_default(Shadow=3), 'Missing', r'{\pos(320,180)\shad0}Shadow', 1, ('shad', 0)),
    ('explicit-scale', with_default(ScaleX=80), 'Missing', r'{\pos(320,180)\fscx100}Scale', 1, ('fscx', 100)),
    ('explicit-spacing', with_default(Spacing=3), 'Missing', r'{\pos(320,180)\fsp0}Spacing', 1, ('fsp', 0)),
    ('explicit-alignment', with_default(Alignment=8), 'Missing', r'{\an2\fs20}Alignment', 1, ('an', 2)),
    ('explicit-alpha', with_default(PrimaryColour='&H80FFFFFF'), 'Missing', r'{\pos(320,180)\1a&H00&}Alpha', 1, ('1a', 0)),
    ('transparent-copies', with_default(PrimaryColour='&H80FFFFFF'), 'Missing', r'{\pos(320,180)\fs20}Copies', 2, ('fs', 20)),
    ('missing-reset-known-event', header, 'Large', r'{\pos(320,180)\fs20}Small {\rMissing}large', 1, ('fs', 60)),
    ('missing-reset-missing-event', header, 'Missing', r'{\pos(320,180)\rLarge}Large {\rMissing}default', 1, ('fs', 40)),
    ('strict-reset-case', header, 'Large', r'{\pos(320,180)\rdefault}Large', 1, ('fs', 60)),
    ('strict-reset-star', header, 'Sign', r'{\pos(320,180)\r*Large}Sign', 1, ('fs', 50)),
    ('explicit-default-reset', header, 'Large', r'{\pos(320,180)\rDefault}Default', 1, ('fs', 40)),
    ('case-sensitive-sign', header, 'sign', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
    ('missing-case-variant', header, 'SIGN', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
    ('event-star-alias', header, '**Sign', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
    ('style-star-definition', header.replace('Style: Sign,', 'Style: **Sign,'), 'Sign', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
    ('default-star-definition', header.replace('Style: Default,', 'Style: **Default,'), 'Missing', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
    ('empty-event-style', header, '', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
    ('lower-event-default', header, 'default', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
    ('implicit-default', header.replace(default_line + '\n', ''), 'Missing', r'{\pos(320,180)\fs20}Size {\r}implicit', 1, ('fs', 18)),
    ('implicit-relative-size', header.replace(default_line + '\n', ''), 'Missing', r'{\pos(320,180)\fs+2}Size', 1, ('fs', 21.6)),
    ('lowercase-style-not-default', header.replace('Style: Default,', 'Style: default,'), 'Missing', r'{\pos(320,180)\fs20}Small', 1, ('fs', 20)),
]

checks = 0
with tempfile.TemporaryDirectory() as temporary:
    source, output = Path(temporary) / 'input.ass', Path(temporary) / 'output.ass'
    styles = s.parse_styles(header.splitlines())
    for name, fs in [('Missing', 40), ('Sign', 50), ('sign', 30), ('SIGN', 40),
                     ('*Sign', 50), ('**Sign', 50), ('', 40), ('default', 40)]:
        assert s.resolve_event_style(styles, name)['fs'] == fs
        checks += 1
    assert s.effective_state('Size', styles=styles)['fs'] == 40
    assert s.effective_state('Size', default={'fs': 25}, styles=styles)['fs'] == 25
    checks += 2
    simplified, _, _ = s.simplify_visual_text(r'{\fs20}Small', 0, styles=styles)
    assert simplified == r'{\fs20}Small'
    checks += 1

    # Style changes must synchronize both cached state and inherited defaults.
    source.write_text(header + event(r'{\pos(320,180)}Size', 'Large'))
    original = s.load_subtitle_events(source)[1][0]
    changed = s.replace_event(original, style='Missing')
    assert changed.defaults is original.styles['Default']
    assert changed.state['fs'] == changed.defaults['fs'] == 40
    changed = s.replace_event(changed, text=r'{\pos(320,180)\fs20}Size')
    compacted = s.compact_static_overrides([changed], 0)[0]
    assert compacted.state['fs'] == 20 and r'\fs20' in compacted.text
    checks += 1

    # The static-object matcher must compare actual inherited font/paint.
    source.write_text(header + event(r'{\pos(320,180)}Size'))
    e = s.load_subtitle_events(source)[1][0]
    key = s.static_object_key(e, e.styles)
    signature = dict(key[-1][0][0].formatting)
    assert signature['fs'] == e.defaults['fs'] == e.state['fs'] == 40
    checks += 1

    for i, (label, script, style, text, count, expected) in enumerate(cases):
        source.write_text(script + event(text, style, count))
        (root / 'validation' / f'undefined-source-{i}.ass').write_bytes(source.read_bytes())
        parsed = s.load_subtitle_events(source)[1]
        selected = s.resolve_event_style(parsed[0].styles, style)
        assert parsed[0].defaults == selected
        checks += 1
        for level in (1, 2):
            with contextlib.redirect_stdout(io.StringIO()):
                stats = s.simplify_ass(source, output, s.SimplifyConfig(level=level), font_metrics=None, font_report=font_test_report(None))
            converted = s.load_subtitle_events(output)[1]
            assert len(converted) == stats['output'] == count, (label, level, len(converted))
            assert converted[0].style == style
            checks += 1
            if expected:
                field, value = expected
                actual = converted[0].state[field]
                assert actual == value or isinstance(actual, (int, float)) and math.isclose(actual, value), (label, level, actual, value)
                checks += 1
            (root / 'validation' / f'undefined-level{level}-{i}.ass').write_bytes(output.read_bytes())

result = {'checks': checks, 'version': s.__version__, 'pipeline_cases_at_both_levels': len(cases)}
(root / 'validation' / 'undefined-style-checks.json').write_text(json.dumps(result, indent=2) + '\n')
print(checks, 'undefined-style checks passed')
