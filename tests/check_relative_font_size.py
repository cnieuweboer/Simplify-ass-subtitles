"""Regression checks for signed ASS sizes, inline spans and transforms."""
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
Style: Large,Arial,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

static_cases = [
    (r'\fs+2', 48), (r'\fs-2', 32), (r'\fs+0', 40),
    (r'\fs-0', 40), (r'\fs+0.5', 42), (r'\fs-.5', 38),
    (r'\fs50\fs-2', 40), (r'\fs+2\fs+2', 57.6),
    (r'\fs-2\fs-2', 25.6), (r'\fs+2\fs-2', 38.4),
    (r'\fs+2\fs', 40), (r'\fs+2\fs0', 40),
    (r'\fs50\fs-10', 40), (r'\fs50\fs-12', 40),
    (r'\rLarge\fs+2', 72), (r'\rLarge\fs-2', 48),
    (r'\rLarge\fs50\fs-10', 60),
    (r'\rLarge\fs+2\r\fs-2', 32),
    (r'\fs+2\rLarge\fs+2', 72),
    (r'\rUnknown\fs+2', 48), (r'\fs24', 24),
    # Early entrance size transforms should freeze to their settled size.
    (r'\t(0,100,\fs+2)', 48),
    (r'\fs50\t(0,100,\fs-2)', 40),
    (r'\rLarge\t(0,100,\fs+2)', 72),
    (r'\t(0,100,\fs+2\fs+2)', 57.6),
]

checks = 0
with tempfile.TemporaryDirectory() as temporary:
    source = Path(temporary) / 'input.ass'
    output = Path(temporary) / 'output.ass'
    source.write_text(header)
    styles = s.parse_styles(header.splitlines())
    default = styles['Default']

    def check_size(actual, expected):
        global checks
        assert math.isclose(actual, expected, abs_tol=1e-8), (actual, expected)
        checks += 1

    for tags, expected in static_cases:
        if r'\t(' not in tags:
            check_size(s.effective_state('{' + tags + '}Size', default, styles)['fs'], expected)
        result = s.freeze_block(tags, 3, default, default, styles, 0)
        frozen, state = result.text, result.selection.state
        check_size(state['fs'], expected)
        check_size(s.effective_state('{' + frozen + '}Size', default, styles)['fs'], expected)
        assert not any(name == 'fs' and value.startswith(('+', '-'))
                       for name, value in s.tokenize_override(frozen))
        checks += 1

    # Size changes carry from one visible span into the following span.
    text = r'{\fs+2}A{\fs-2}B{\rLarge\fs+2}C{\r\fs+2}D'
    simplified, visible, _ = s.simplify_visual_text(text, 0, 3, default, styles, level=1)
    assert visible == 'ABCD'
    expected_inline = r'{\fs48}A{\fs38.4}B{\rLarge\fs72}C{\r\fs48}D'
    assert simplified == expected_inline, simplified
    checks += 1

    # Expected midpoint/end values follow libass's per-tag interpolation.
    # In particular, fallback to the style size happens after interpolation.
    transform_cases = [
        ([('fs', '+2')], 44, 48),
        ([('fs', '-2')], 36, 32),
        ([('fs', '+2'), ('fs', '+2')], 48.4, 57.6),
        ([('fs', '60'), ('fs', '+2')], 55, 72),
        ([('fs', '+2'), ('fs', '60')], 52, 60),
        ([('fs', '60'), ('fs', '80')], 65, 80),
        ([('fs', '-10')], 20, 40),
        ([('fs', '-20')], 40, 40),
        ([('fs', '0')], 20, 40),
        ([('fs', '')], 40, 40),
        ([('fs', '+2'), ('fs', '')], 40, 40),
        ([('r', 'Large'), ('fs', '+2')], 66, 72),
        ([('fs', '+2'), ('r', 'Large')], 60, 60),
        ([('fs', '+2'), ('1c', '&H0000FF&')], 44, 48),
    ]
    for changes, midpoint, end in transform_cases:
        transforms = [(100, 1100, 1, changes)]
        times = [0, 100, 600, 1100, 1500]
        evaluations = list(s.sample_transform_states(default, transforms, times, styles, default))
        sampled = [evaluation.formatting for evaluation in evaluations]
        for at, evaluation in zip(times, evaluations):
            assert evaluation == s.sample_transform_state(default, transforms, at, styles, default)
            checks += 1
        check_size(sampled[0]['fs'], 40)
        check_size(sampled[2]['fs'], midpoint)
        check_size(sampled[3]['fs'], end)
        check_size(sampled[4]['fs'], end)
        if ('1c', '&H0000FF&') in changes:
            assert sampled[2]['1c'] == '8080FF'
            checks += 1
    transforms = [(0, 1000, 1, [('fs', '+2')]),
                  (500, 1500, 1, [('fs', '-2')])]
    check_size(s.sample_transform_state(default, transforms, 1000, styles, default).formatting['fs'], 43.2)
    check_size(s.sample_transform_state(default, transforms, 1500, styles, default).formatting['fs'], 38.4)
    check_size(s.sample_transform_state(default, [(0, 1000, 2, [('fs', '+2')])],
                                       500, styles, default).formatting['fs'], 42)
    large = styles['Large'].copy()
    check_size(s.sample_transform_state(large, [(0, 1000, 1, [('fs', '-10')])],
        1000, styles, default,continuation=s.OverrideContinuation('Large')).formatting['fs'], 60)

    # End-to-end conversion at both levels, with nonoverlapping captions.
    events = []
    for i, (tags, _) in enumerate(static_cases):
        events.append(f'Dialogue: 0,{s.format_time(1+4*i)},{s.format_time(4+4*i)},'
                      f'Default,,0,0,0,,{{\\pos(320,180){tags}}}Relative size\n')
    events.append(f'Dialogue: 0,{s.format_time(1+4*len(events))},'
                  f'{s.format_time(4+4*len(events))},Default,,0,0,0,,{{\\pos(320,180)}}{text}\n')
    source.write_text(header + ''.join(events))
    (root / 'validation' / 'relative-size-source.ass').write_text(source.read_text())
    for level in (1, 2):
        with contextlib.redirect_stdout(io.StringIO()):
            s.simplify_ass(source, output, s.SimplifyConfig(level=level), font_metrics=None, font_report=font_test_report(None))
        output_lines, converted, _, _ = s.load_subtitle_events(output)
        output_styles = s.parse_styles(output_lines)
        assert len(converted) == len(events)
        checks += 1
        for converted_event, (_, expected) in zip(converted, static_cases):
            check_size(s.effective_state(converted_event.text, output_styles['Default'],
                                         output_styles)['fs'], expected)
        assert converted[-1].text.endswith(expected_inline)
        checks += 1
        if level == 1:
            (root / 'validation' / 'relative-size-v104.ass').write_bytes(output.read_bytes())

result = {'checks': checks, 'version': s.__version__,
          'static_cases': len(static_cases), 'transform_cases': len(transform_cases)}
(root / 'validation' / 'relative-size-checks.json').write_text(json.dumps(result, indent=2) + '\n')
print(checks, 'relative-font-size checks passed')
