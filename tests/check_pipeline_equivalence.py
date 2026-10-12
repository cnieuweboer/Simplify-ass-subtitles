#!/usr/bin/env python3
"""Compare document boundaries and both modes with immutable v166."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import contextlib
import hashlib
import importlib.util
from io import StringIO
import json
import sys
import tempfile

import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
from event_evidence_test_helpers import event_comparison_fields

ROOT = Path(__file__).resolve().parents[1]
baseline_path = ROOT/'test-data/simplify_ass-v166-reference.py'
spec = importlib.util.spec_from_file_location('previous_pipeline',baseline_path)
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
adapt_reference_font_api(previous)

header = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def event(text, start='0:00:01.00', end='0:00:04.00', layer='0', style='Default'):
    return f'Dialogue: {layer},{start},{end},{style},,0,0,0,,{text}\n'

cases = {
    'empty_file':'',
    'no_events_section':header.split('[Events]',1)[0],
    'script_info_only':'[Script Info]\nScriptType: v4.00+\n',
    'empty_events':header,
    'comment_only':header+'Comment: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Authored cue\n',
    'unpositioned_copies':header+event('Two rows')*2,
    'relative_size_and_reset':header+event(r'{\pos(100,100)\fs+2}A{\r\fs-2}B'),
    'transparent_copies':header+event(r'{\pos(100,100)\1a&H80&}Fade')*2,
    'undefined_style':header+event(r'{\fnArial\fs40\pos(100,100)}A',style='Missing'),
    'backdrop_and_text':header+event(r'{\an7\pos(100,100)\p1\c&H112233&}m 0 0 l 400 0 400 100 0 100')+
        event(r'{\an7\pos(120,120)}Backdrop',layer='2'),
    'invalid_and_touching_intervals':header+event('Invisible',end='0:00:00.00')+
        event(r'{\pos(100,100)}A',end='0:00:02.00')+
        event(r'{\pos(100,100)}A',start='0:00:02.00'),
    'inline_fonts_and_comments':header+event(r'{\fnArial\pos(100,100)}A{\fn00243}i')+
        'Comment: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\fnUnused Font}Comment\n',
    'literal_unicode_line_separator':header+event('A\u2028B\u2029C'),
    'non_event_section_after_events':header+event('Text')+'[Fonts]\nfontname: fake\n',
    'no_final_newline':(header+event(r'{\pos(100,100)}Text')).rstrip('\n'),
    'explicit_blank_positions':header+''.join(event(r'{\pos('+str(x)+',100)}'+text)
        for x,text in [(100,'A'),(125,''),(150,'i'),(175,'A'),(200,'i')]),
    'ssa_actor_and_marked_fields':header.replace(
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
        'Format: Marked, Start, End, Style, Actor, MarginL, MarginR, MarginV, Effect, Text')+
        event('Text').replace('Dialogue: 0,','Dialogue: Marked=0,'),
    'empty_file_with_newlines':'\n\n\n',
    'multiple_terminal_newlines':header+event('Text')+'\n\n\n',
    'terminal_newlines_without_events':header+'\n\n',
    'carriage_returns':(header+event('Text')+'\n').replace('\n','\r'),
    'crlf_records':(header+event('Text')+'\n').replace('\n','\r\n'),
    'mixed_record_separators':header.replace('\n','\r\n')+event('Text').replace('\n','\r'),
    'invalid_resolution':header.replace('PlayResY: 1080','PlayResY: NaN')+event('Text'),
    'nonpositive_resolution':header.replace('PlayResY: 1080','PlayResY: 0')+event('Text'),
    'duplicate_resolution':header.replace('PlayResY: 1080','PlayResY: broken\nPlayResY: 1080')+event('Text'),
    'invalid_wrap_after_valid':header.replace('WrapStyle: 2','WrapStyle: 2\nWrapStyle: broken\nWrapStyle: 9')+
        event(r'{\pos(100,100)}A\NB'),
    'wrap_reset_and_unknown_style':header+event(r'{\q1\fs+2}A{\rMissing\q3}B',style='Missing'),
    'interstitial_event_metadata':header+event('One')+'; authored note\n\n'+event('Two'),
    'relocated_generated_marker':header+event('Text')+'; Simplified by simplify_ass.py\n',
    'marker_only_at_end':header.split('[Events]',1)[0].rstrip('\n')+'\n; Simplified by simplify_ass.py',
    'multiple_event_formats':header+event('First')+
        'Format: Marked, Start, End, Style, Actor, MarginL, MarginR, MarginV, Effect, Text\n'+
        event('Second').replace('Dialogue: 0,','Dialogue: Marked=0,'),
    'commas_and_literals':header+event('A, B, C\u2028D\u2029E'),
    'empty_events_before_following_section':header+'[Fonts]\nfontname: unused\n\n',
    'bom_exposed_by_legacy_marker_removal':'; static vector support prototype old\n\ufeff'+header+event('Text'),
    'casefolded_script_metadata':header.replace('[Script Info]','[\u017fcript Info]').replace(
        'WrapStyle:','Wrap\u017ftyle:')+event('Text'),
}

checks = []
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    # Font catalogs stay shared across inputs, as in a real CLI batch.
    metrics = {module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
    for name,text in cases.items():
        source = folder/(name+'.ass');source.write_text(text,encoding='utf-8')
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        readers = []
        for module in (previous,current):
            lines,events,fields,indices = module.load_subtitle_events(source)
            readers.append((lines,[event_comparison_fields(e) for e in events],fields,indices))
        assert readers[0] == readers[1],(name,'reader')
        for level in (1,2):
            for measured in (False,True):
                results = []
                for module in (previous,current):
                    output = folder/(name+'.'+module.__version__+str(level)+str(measured)+'.ass')
                    console = StringIO()
                    with contextlib.redirect_stdout(console):
                        stats = module.simplify_ass(source,output,module.SimplifyConfig(level=level),
                            font_metrics=metrics[module] if measured else None, font_report=font_test_report(metrics[module] if measured else None))
                    assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
                    results.append((output.read_bytes(),stats,console.getvalue()))
                assert results[0] == results[1],(name,level,measured)
                assert hashlib.sha256(source.read_bytes()).hexdigest()==original,name
                checks.append({'case':name,'level':level,'font_measurement':measured,
                    'output_statistics_and_diagnostics_identical':True,'source_unchanged':True})
report = {'version':current.__version__,'reference_version':previous.__version__,
    'comparisons_passed':len(checks),'reader_comparisons_passed':len(cases),'comparisons':checks}
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation/pipeline-equivalence.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'pipeline equivalence comparisons passed')
