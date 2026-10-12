import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare complete Overlord conversions and fade-pass contracts with immutable v164."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import sys
import tempfile

import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current, historical_fade_timing=True)
from event_evidence_test_helpers import event_comparison_fields

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('faded_conversion_reference',
    ROOT/'test-data/simplify_ass-v165-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
# Keep historical pass behavior while correcting its known hexadecimal suffix bug.
from outline_color_test_helpers import install_hex_parenthesis_reference_parser
install_hex_parenthesis_reference_parser(previous)

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

results = []
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared = []
    for module in (previous,current):
        captured = []
        original = module.trim_faded_cue_overlaps
        def wrapped(*args,**kwargs):
            before = snapshot((args,kwargs))
            result = original(*args,**kwargs)
            assert before==snapshot((args,kwargs)),(fixture,'pass input mutation')
            captured.append((before,snapshot(result)))
            return result
        module.trim_faded_cue_overlaps = wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/'output.ass'
                metric = module.FontMetrics([ROOT/'fonts'])
                log = io.StringIO()
                with contextlib.redirect_stdout(log):
                    stats = module.simplify_ass(ROOT/'test-data'/fixture,output,
                        module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
                compared.append((captured,output.read_bytes(),stats,log.getvalue(),
                    font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:
            module.trim_faded_cue_overlaps = original
    assert compared[0]==compared[1],fixture
    assert captured,fixture
    results.append(dict(fixture=fixture,target_calls=len(captured),
        handoffs=[result[1] for before,result in captured],
        pass_inputs_and_results_identical=True,output_bytes_identical=True,
        statistics_logs_and_font_counters_identical=True))
report = dict(version=current.__version__,reference_version=previous.__version__,
    focused_conversions=len(results),results=results)
(ROOT/'validation/faded-cue-conversion-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print('Two focused conversions: fade-pass inputs/results, output bytes, statistics, logs and font counters match v164')
