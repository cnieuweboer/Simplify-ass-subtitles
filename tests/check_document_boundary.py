#!/usr/bin/env python3
"""Verify decoding compatibility, normalization and document state ownership."""
import test_paths
from event_evidence_test_helpers import without_inactive_color_phase_reporting  # Resolve the repository for direct test execution.
from pathlib import Path
from dataclasses import replace
import contextlib
from copy import deepcopy
import hashlib
import importlib.util
from io import StringIO
import json
import sys
import tempfile
from unittest.mock import patch

import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('document_reference',
    ROOT/'test-data/simplify_ass-v152-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
checks = []

def check(name,condition):
    assert condition,name
    checks.append(name)

def event_snapshot(event):
    fields = event_comparison_fields(event)
    return (event.fields(),event.kind,event.start_s,event.end_s,event.source_index,
            fields['state'],fields['defaults'],fields['styles'],event.unit,event.row,event.lyric)

def reader_snapshot(result):
    lines,events,fields,indices = result
    return (lines,[event_snapshot(e) for e in events],fields,indices)

header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
WrapStyle: 2
ScaledBorderAndShadow: yes
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
content = header+r'Dialogue: 2,0:00:01.00,0:00:04.00,Missing,Actor,10,20,30,,{\fnArial\fs+2\q1\1c&H123456&}Café{\r\fs-2}i'+ '\n'
encodings = [('utf8','utf-8',None),('utf8_bom','utf-8-sig',None),
    ('utf16_bom','utf-16',None),('utf32_bom','utf-32',None),
    ('utf16_le','utf-16-le','utf-16-le'),('utf16_be','utf-16-be','utf-16-be'),
    ('cp1252','cp1252','cp1252')]

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    for name,encoding,override in encodings:
        source = folder/(name+'.ass')
        source.write_bytes(content.replace('\n','\r\n').encode(encoding))
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        check(name+' reader parity',reader_snapshot(previous.load_subtitle_events(source,override)) ==
              reader_snapshot(current.load_subtitle_events(source,override)))
        for level in (1,2):
            results = []
            for module in (previous,current):
                output = folder/(name+module.__version__+str(level)+'.ass')
                console = StringIO()
                with contextlib.redirect_stdout(console):
                    stats = module.simplify_ass(source,output,
                        module.SimplifyConfig(level=level,encoding=override))
                stats=without_inactive_color_phase_reporting(stats)
                assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
                results.append((output.read_bytes(),stats,console.getvalue()))
            check(name+f' mode {level} conversion parity',results[0]==results[1])
        check(name+' source unchanged',digest==hashlib.sha256(source.read_bytes()).hexdigest())

    # Private proof metadata can disagree with the serialized ASS. The ASS
    # formatting must govern the backdrop boundary, as with the old disk pass.
    source = folder/'boundary.ass'
    source.write_text(content,encoding='utf-8')
    document = current.read_subtitle_document(source)
    original = current._resolve_document_state(document)
    original_snapshot = deepcopy([event_snapshot(e) for e in original.events.values()])
    prepared = current._prepare_text_document(document,source)
    event = next(iter(prepared.events.values()))
    private_state = {'fs':999,'_opaque_spans':[(0,99)],'_sustained_geometry':{'pos':(9,9)},
                     '_original_contour_points':[(1,2)],'_layout_proof':True}
    changed_styles = {name:{**state,'_temporary_proof':True} for name,state in event.styles.items()}
    changed = replace(event,source_index=999,row=42,lyric=True,state=private_state,
                      styles=changed_styles,defaults={'fs':999})
    result = current.TextProcessingResult([changed],{'original':1})
    normalized = current._normalize_text_result(prepared,result)
    temporary = folder/'disk-boundary.ass'
    current.write_subtitle_document(temporary,prepared,result.events)
    expected = previous.load_subtitle_events(temporary)
    actual = (normalized.lines,list(normalized.events.values()),normalized.fields,
              list(normalized.events))
    check('normalization matches previous disk reader',reader_snapshot(actual)==reader_snapshot(expected))
    normalized_event = next(iter(normalized.events.values()))
    check('line index is regenerated',normalized_event.source_index==expected[3][0] and
          normalized_event.source_index!=999)
    check('row and lyric flags reset',normalized_event.row==0 and not normalized_event.lyric)
    check('proof metadata is discarded',not (private_state.keys()-{'fs'}) & normalized_event.state.keys())
    check('serialized formatting wins',normalized_event.state['fs']!=999)
    check('wrap measurement restored',normalized_event.measurement.script_wrap_mode==2)
    check('source evidence unchanged',original_snapshot==[event_snapshot(e) for e in original.events.values()])
    original_event = next(iter(original.events.values()))
    check('independent source and caption styles',original.styles is not normalized.styles and
          original_event.defaults is not normalized_event.defaults)
    normalized_event.state['_mutated_after_boundary'] = True
    normalized_event.styles['Default']['fs'] = 5000
    check('caption mutations stay isolated',original_snapshot==[event_snapshot(e) for e in original.events.values()])
    check('text result flags stay local',changed.lyric and changed.row==42 and changed.source_index==999)
    check('text result counters stay intact',result.statistics=={'original':1})

    # Real conversion must read the input once and write only the final output.
    # Disallow temporary directories to catch a regression to the old ASS pass.
    output = folder/'supported.ass'
    read_calls,write_calls = [],[]
    read = current.read_subtitle
    write = Path.write_text
    def tracked_read(path,encoding=None):
        read_calls.append(path)
        return read(path,encoding)
    def tracked_write(path,*args,**kwargs):
        write_calls.append(path)
        return write(path,*args,**kwargs)
    with patch.object(current,'read_subtitle',tracked_read), \
         patch.object(Path,'write_text',tracked_write), \
         patch.object(tempfile,'TemporaryDirectory',side_effect=AssertionError('Unexpected ASS disk roundtrip')), \
         contextlib.redirect_stdout(StringIO()):
        stats = current.simplify_ass(source,output,current.SimplifyConfig())
    check('one source read',read_calls==[source])
    check('only final output written',write_calls==[output])
    check('final subtitle and count agree',stats['output']==len(current.load_subtitle_events(output)[1]))

report = {'version':current.__version__,'reference_version':previous.__version__,
          'checks_passed':len(checks),'checks':checks}
(ROOT/'validation/document-boundary-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'document boundary checks passed')
