#!/usr/bin/env python3
"""Check final frame-echo application contracts against immutable v152."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import json
import sys
import simplify_ass as current

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('frame_application_reference',root/'test-data/simplify_ass-v152-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
cases = [
    ('empty',[],set(),{}),
    ('unchanged',[8,3,9],set(),{}),
    ('removed',[8,3,9],{3},{}),
    ('replacement also removed',[8,3,9],{3,9},{3:'caption'}),
    ('replacement without removal',[8,3,9],set(),{3:'caption'}),
    ('duplicate source identifiers',[3,8,3,9],{3,9},{3:'caption'}),
    ('unlisted removed identifier',[8,3,9],{3,99},{}),
    ('unlisted replacement identifier',[8,3,9],{3,99},{99:'caption'}),
]
checks = []
for name,ids,removed,replaced in cases:
    for reverse in (False,True):
        events = [SimpleNamespace(source_index=i,label=f'original-{j}') for j,i in enumerate(ids)]
        if reverse: events.reverse()
        replacements = {i:SimpleNamespace(source_index=i,label=label) for i,label in replaced.items()}
        before = [vars(e).copy() for e in events]
        results = []
        for module in (previous,current):
            def accept(context,frames):
                context.removed.update(removed)
                context.replacements.update(replacements)
            with patch.object(module,'_index_frame_echo_families',return_value={'family':{}}), patch.object(module,'_collapse_frame_echo_family',side_effect=accept):
                output,count = module.collapse_frame_text_echoes(events,.16)
            assert output is not events
            assert before==[vars(e) for e in events]
            results.append((output,count))
        assert results[0][1]==results[1][1],name
        assert len(results[0][0])==len(results[1][0]),name
        assert all(a is b for a,b in zip(results[0][0],results[1][0])),name
        checks.append(dict(case=name,reverse=reverse,removed_count=results[1][1],returned_events=len(results[1][0])))
(root/'validation/frame-echo-application-checks.json').write_text(json.dumps(dict(
    comparisons=len(checks),event_order_identity_and_counts_identical=True,checks=checks),indent=2)+'\n')
print(len(checks),'frame-echo application comparisons: order, identity, duplicates and source-set counts preserved')
