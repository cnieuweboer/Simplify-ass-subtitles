"""Regression checks for unpositioned text and renderer collision placement."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import contextlib
import io
import json
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
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def event(text='YES', *, layer=0, kind='Dialogue', start='0:00:01.00',
          end='0:00:04.00'):
    return f'{kind}: {layer},{start},{end},Default,,0,0,0,,{text}\n'

checks = 0
with tempfile.TemporaryDirectory() as temporary:
    source = Path(temporary) / 'input.ass'
    output = Path(temporary) / 'output.ass'

    def load(raw):
        source.write_text(header + raw)
        return s.load_subtitle_events(source)[1]

    # Equal records without positions are distinct collision-managed rows.
    for raw in [event() * 2,
                event(r'{\an2}YES') * 2,
                event(r'{\org(320,180)}YES') * 2,
                event() + event('Other caption') + event()]:
        events = load(raw)
        visible = {e.source_index: s.simplify_text(e.text, visible_only=True)[1]
                   for e in events}
        kept, removed = s.deduplicate_layers(events, visible)
        assert removed == 0 and [e.fields() for e in kept] == [e.fields() for e in events]
        checks += 1

        # The complete pipeline must keep both rows too, at either level.
        for level in (1, 2):
            with contextlib.redirect_stdout(io.StringIO()):
                stats = s.simplify_ass(source, output, s.SimplifyConfig(level=level),
                                       font_metrics=None, font_report=font_test_report(None))
            converted = s.load_subtitle_events(output)[1]
            assert stats['output'] == len(events)
            assert sum(s.simplify_text(e.text, visible_only=True)[1] == 'YES'
                       for e in converted) == 2
            checks += 1

    # Explicitly positioned opaque duplicates can still be removed.
    events = load(event(r'{\pos(320,180)}YES') * 2)
    kept, removed = s.deduplicate_layers(events, {e.source_index: 'YES' for e in events})
    assert len(kept) == 1 and removed == 1
    checks += 1
    with contextlib.redirect_stdout(io.StringIO()):
        stats = s.simplify_ass(source, output, s.SimplifyConfig(), font_metrics=None, font_report=font_test_report(None))
    assert stats['output'] == 1
    checks += 1

    # Drawings are not collision-managed text; retain their previous dedup rule.
    events = load(event(r'{\p1}m 0 0 l 100 0 100 50 0 50') * 2)
    kept, removed = s.deduplicate_layers(events, {})
    assert len(kept) == 1 and removed == 1
    checks += 1

    # Comments are preserved, and separate layers retain their existing handling.
    events = load(event(kind='Comment') * 2)
    kept, removed = s.deduplicate_layers(events, {})
    assert len(kept) == 2 and removed == 0
    checks += 1
    events = load(event(layer=0) + event(layer=1))
    kept, removed = s.deduplicate_layers(events, {e.source_index: 'YES' for e in events})
    assert len(kept) == 2 and removed == 0
    checks += 1

result = {'checks': checks, 'version': s.__version__,
          'unpositioned_rows_retained': True,
          'positioned_duplicates_still_reduced': True,
          'drawing_deduplication_unchanged': True}
(root / 'validation' / 'collision-checks.json').write_text(json.dumps(result, indent=2) + '\n')
print(checks, 'collision-duplicate checks passed')
