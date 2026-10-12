"""Check that copy removal preserves partial-alpha compositing evidence."""
from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simplify_ass as s
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(s)

root = Path(__file__).resolve().parent
header = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: Partial,Arial,40,&H80FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: PartialOutline,Arial,40,&HFFFFFFFF,&H00FFFFFF,&H80FFFFFF,&HFF000000,0,0,0,0,100,100,0,0,1,4,0,2,20,20,20,1
Style: PartialShadow,Arial,40,&HFFFFFFFF,&H00FFFFFF,&HFFFFFFFF,&H80FFFFFF,0,0,0,0,100,100,0,0,1,0,6,2,20,20,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def event(text, style='Default', layer=0, start=1, end=4, kind='Dialogue'):
    return (f'{kind}: {layer},{s.format_time(start)},{s.format_time(end)},'
            f'{style},,0,0,0,,{text}\n')

partial_cases = [
    (r'{\pos(320,180)\alpha&H80&}YES', 'Default'),
    (r'{\pos(320,180)\1a&H80&}YES', 'Default'),
    (r'{\pos(320,180)\alpha&HC0&}YES', 'Default'),
    (r'{\pos(320,180)\alpha&H01&}YES', 'Default'),
    (r'{\pos(320,180)\alpha&HFE&}YES', 'Default'),
    (r'{\pos(320,180)\3a&H80&\bord4}YES', 'Default'),
    (r'{\pos(320,180)\4a&H80&\shad6}YES', 'Default'),
    (r'{\pos(320,180)\2a&H80&}YES', 'Default'),
    (r'{\pos(320,180)}YES', 'Partial'),
    (r'{\pos(320,180)}YES', 'PartialOutline'),
    (r'{\pos(320,180)}YES', 'PartialShadow'),
    (r'{\pos(320,180)\alpha&H80&}YES{\alpha&H00&} OK', 'Default'),
    (r'{\pos(320,180)\rPartial}YES{\rDefault} OK', 'Default'),
    (r'{\pos(320,180)\1a&HFF&\3a&H80&\bord4}YES{\3a&H00&} OK', 'Default'),
    (r'{\pos(320,180)\p1\alpha&H80&}m 0 0 l 100 0 100 50 0 50', 'Default'),
]

# Full conversions which should retain source paint exactly. Complete opaque
# foreground stacks may still undergo the existing standard simplification reconstruction.
pipeline_cases = [partial_cases[i] for i in (0, 1, 2, 4, 8, 9, 11, 12, 13)]

checks = 0
with tempfile.TemporaryDirectory() as temporary:
    source, output = Path(temporary) / 'input.ass', Path(temporary) / 'output.ass'

    def load(raw):
        source.write_text(header + raw)
        return s.load_subtitle_events(source)[1]

    for text, style in partial_cases:
        events = load(event(text, style) * 2)
        assert all(s.has_translucent_paint(e) for e in events)
        checks += 1
        visible = {e.source_index: 'YES' for e in events}
        kept, removed = s.deduplicate_layers(events, visible)
        assert removed == 0 and [e.fields() for e in kept] == [e.fields() for e in events]
        checks += 1
        kept, removed = s.reduce_static_sign_copies(events, visible)
        assert removed == 0 and [e.fields() for e in kept] == [e.fields() for e in events]
        checks += 1

    # Dynamic opacity is unsafe until the separate freezing pass resolves it.
    for tags in (r'\t(0,1000,\alpha&H80&)', r'\fad(500,500)',
                 r'\fade(0,128,0,0,500,1000,1500)', r'\kf30'):
        events = load(event(r'{\pos(320,180)' + tags + '}YES') * 2)
        assert s.deduplicate_layers(events, {})[1] == 0
        checks += 1

    # Alpha changes with no following payload do not describe painted spans.
    # Fully hidden channels and ordinary opaque copies remain deduplicatable.
    for text in (r'{\pos(320,180)}YES',
                 r'{\pos(320,180)}YES{\alpha&H80&}',
                 r'{\pos(320,180)\3a&HFF&\4a&HFF&}YES',
                 r'{\pos(320,180)\alpha&HFF&}YES',
                 r'{\pos(320,180)\alpha&H80&\alpha&H00&}YES'):
        events = load(event(text) * 2)
        assert not any(s.has_translucent_paint(e) for e in events)
        assert s.deduplicate_layers(events, {})[1] == 1
        checks += 1

    # Near-positioned copies and full-lifetime covers can also accumulate paint.
    text = r'{\pos(320,180)\alpha&H80&}YES'
    for raw in (event(text) * 3,
                event(text) + event(text.replace('320', '321')),
                event(text, start=1, end=5) + event(text, start=2, end=4),
                event(text, layer=0) + event(text, layer=1)):
        events = load(raw)
        visible = {e.source_index: 'YES' for e in events}
        assert s.reduce_static_sign_copies(events, visible)[1] == 0
        assert s.deduplicate_layers(events, visible)[1] == 0
        checks += 1

    # An opaque paint copy is not grounds to discard a translucent neighbour.
    events = load(event(text) + event(r'{\pos(320,180)}YES'))
    assert s.reduce_static_sign_copies(events, {e.source_index: 'YES' for e in events})[1] == 0
    checks += 1
    # Preserve the established simplification of nearby opaque copies.
    events = load(event(r'{\pos(320,180)}YES') + event(r'{\pos(321,180)}YES'))
    assert s.reduce_static_sign_copies(events, {e.source_index: 'YES' for e in events})[1] == 1
    checks += 1

    for i, (text, style) in enumerate(pipeline_cases):
        source.write_text(header + event(text, style) * 2)
        (root / 'validation' / f'translucent-source-{i}.ass').write_bytes(source.read_bytes())
        for level in (1, 2):
            with contextlib.redirect_stdout(io.StringIO()):
                stats = s.simplify_ass(source, output, s.SimplifyConfig(level=level), font_metrics=None, font_report=font_test_report(None))
            converted = s.load_subtitle_events(output)[1]
            assert len(converted) == stats['output'] == 2, (i, level, len(converted))
            assert stats['deduped'] == 0
            checks += 1
            (root / 'validation' / f'translucent-level{level}-{i}.ass').write_bytes(output.read_bytes())

result = {'checks': checks, 'version': s.__version__, 'direct_partial_cases': len(partial_cases),
          'pipeline_cases_at_both_levels': len(pipeline_cases)}
(root / 'validation' / 'translucent-checks.json').write_text(json.dumps(result, indent=2) + '\n')
print(checks, 'translucent-duplicate checks passed')
