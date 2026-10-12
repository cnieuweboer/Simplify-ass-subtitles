#!/usr/bin/env python3
"""Compare explicit lyric/source/row updates with immutable v162 semantics."""
from collections.abc import Mapping
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch
import importlib.util
import ast
import json
import random
import sys
import tempfile

import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
from event_evidence_test_helpers import event_comparison_fields

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('authored_ownership_reference',ROOT/'test-data/simplify_ass-v162-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
# Normalize only the authorized hexadecimal suffix correction in the reference.
from outline_color_test_helpers import install_hex_parenthesis_reference_parser
install_hex_parenthesis_reference_parser(previous)
adapt_reference_font_api(previous)
# Apply only the independently tested v171 wrapping correction to this old
# renderer. Ownership, scaffold decisions and all source/row algorithms stay
# historical; compare their contracts without preserving the known q loss.
renderer = next(n for n in ast.parse(Path(previous.__file__).read_text()).body
                if isinstance(n,ast.FunctionDef) and n.name=='render_simplified_caption')
keys = next(n for n in ast.walk(renderer) if isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='keys' for t in n.targets))
assert isinstance(keys.value,ast.Tuple) and all(isinstance(n,ast.Constant) for n in keys.value.elts)
assert 'q' not in [n.value for n in keys.value.elts]
keys.value.elts.insert(3,ast.Constant('q'))
exec(compile(ast.fix_missing_locations(ast.Module(body=[renderer],type_ignores=[])),
             '<historical renderer with authored wrapping>','exec'),previous.__dict__)
checks = []
cases = 0

def check(name, condition):
    assert condition, name
    checks.append(name)

def snapshot(value):
    if isinstance(value,(previous.Event,current.Event)):
        return snapshot(event_comparison_fields(value))
    if isinstance(value,Mapping):
        return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return tuple(snapshot(v) for v in value)
    if isinstance(value,set):
        return frozenset(value)
    if hasattr(value,'__dict__'):
        return snapshot(vars(value))
    return value

@contextmanager
def borrowed_events(events):
    """Reject even same-value field assignments into a borrowed Event."""
    identities = {id(e) for e in events}
    setter = current.Event.__setattr__
    def assign(event,name,value):
        assert id(event) not in identities, ('borrowed event field write',name)
        setter(event,name,value)
    with patch.object(current.Event,'__setattr__',assign):
        yield

HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow, MarginL, MarginR, MarginV
Style: Default,Arial,40,2,2,0,20,20,20
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def lyric_inputs(module, *, cached, shared, invalid, reset, alias):
    def line(start,end,tags,word):
        return f'Dialogue: 0,{module.format_time(start)},{module.format_time(end)},Default,,0,0,0,,{{{tags}}}{word}\n'
    prefix = reset+r'\an2'
    text = line(1,4,prefix,'ABCDEFGH')
    for phase in ('in','out'):
        for i,char in enumerate('ABCDEFGH'):
            if invalid == 'incomplete' and phase == 'out' and i == 7:
                continue
            x,y = 820+40*i,1040+(10 if invalid == 'wrong y' else 0)
            movement = fr'\move({x-50},{y},{x},{y})' if phase == 'in' else fr'\move({x},{y},{x+50},{y})'
            text += line(.5 if phase=='in' else 4,1 if phase=='in' else 4.5,reset+r'\an5'+movement,char)
    if invalid == 'collision':
        text += line(2,3,prefix,'OTHERLINE')
    doc = module.parse_subtitle_document(HEADER+text)
    if cached:
        doc = module._resolve_document_state(doc)
    sources = doc.events
    events = list(sources.values())
    if not shared:
        events = [module.replace_event(e,text=module.simplify_visual_text(e.text,0,e.duration,e.defaults,e.styles,1)[0]) for e in events]
    # Preserve unrelated history/proof while installing a cache successor.
    for e in sources.values():
        e.evidence = module.EventEvidence(opaque_spans=((e.start_s,e.end_s),))
        if not cached:
            e.continuation = module.OverrideContinuation('stale',True)
    if alias:
        sources[999999] = sources[events[0].source_index]
    visible = {e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    return events,visible,sources

for cached in (False,True):
    for shared in (False,True):
        for invalid in ('none','incomplete','wrong y','collision'):
            for reset in ('',r'\r',r'\rDefault',r'\rMissing'):
                for alias in (False,True):
                    label = (cached,shared,invalid,reset,alias)
                    compared = []
                    for module in (previous,current):
                        events,visible,sources = lyric_inputs(module,cached=cached,shared=shared,invalid=invalid,reset=reset,alias=alias)
                        original_objects = dict(sources)
                        before = snapshot((events,visible,sources))
                        if module is current:
                            with borrowed_events([*events,*sources.values()]):
                                result = module.match_authored_lyric_rows(events,MappingProxyType(visible),MappingProxyType(sources))
                            check('matcher borrows input '+str(label),before == snapshot((events,visible,sources)))
                            removed,rows = result.removed_sources,result.row_additions
                            applied = {**sources,**result.source_updates}
                            for index,event in result.source_updates.items():
                                original = original_objects[index]
                                check('successor owns cache',event is not original and event.state is not original.state)
                                check('cache edit retains evidence/context/styles',event.evidence is original.evidence and event.measurement is original.measurement and event.defaults is original.defaults and event.styles is original.styles)
                                check('fresh complete continuation',event.continuation == module.evaluate_effective_state(original.text,original.defaults,original.styles).continuation)
                            check('resolved caches never copied',not result.source_updates if cached else bool(result.source_updates))
                            if alias:
                                check('all source aliases share successor',applied[999999] is applied[events[0].source_index])
                            # Applying a delta is explicitly caller-owned.
                            sources.update(result.source_updates)
                            check('applied source caches agree',snapshot(sources) == snapshot(applied))
                        else:
                            removed,rows = module.match_authored_lyric_rows(events,visible,sources)
                            applied = sources
                        compared.append(snapshot((removed,rows,applied)))
                    check('authored decision/cache/row parity '+str(label),compared[0] == compared[1])
                    cases += 1

# Reuse the established scaffold/paint/fragment cases without historical traces.
fixture = ROOT/'check_full_line_copy_stages.py'
f = {'__file__':str(fixture),'__name__':'full_line_ownership_fixtures'}
exec(compile(fixture.read_text().split('NAMES=')[0],str(fixture),'exec'),f)
metrics = {module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
for c in f['CASES']:
    for order in ('original','reverse','shuffle'):
        for mode in ('none','sources only','rows only','sources and rows'):
            compared = []
            for module in (previous,current):
                events = f['inputs'](module,c,order)
                visible = {e.source_index:module.OVERRIDE_RE.sub('',e.text) for e in events}
                sources = {e.source_index:e for e in events} if mode in ('sources only','sources and rows') else None
                collect = mode in ('rows only','sources and rows')
                # Existing rows stay independently owned by the caller.
                seed = [module.TextRow(events[0],[])]
                before = snapshot((events,visible,sources,seed))
                patches = []
                if c.get('preowned'):
                    full = next(e.source_index for e in events if module.OVERRIDE_RE.sub('',e.text).startswith('Colorful row'))
                    fragment = min(e.source_index for e in events if e.source_index != full)
                    owned = {'full':full,'fragment':fragment,'external':999999}[c['preowned']]
                    patches.append(patch.object(module,'match_nested_glyph_copies',return_value={owned}))
                if c.get('render_failure'):
                    patches.append(patch.object(module,'render_merged_caption',return_value=None))
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for item in patches:
                        stack.enter_context(item)
                    if module is current:
                        stack.enter_context(borrowed_events(events))
                        result = module.remove_letters_over_full_lines(events,MappingProxyType(visible),
                            MappingProxyType(sources) if sources is not None else None,
                            collect_rows=collect,font_metrics=metrics[module])
                        check('full-line inputs borrowed',before == snapshot((events,visible,sources,seed)))
                        out,count = result.events,result.removed_count
                        evidence = seed+result.row_additions if collect else None
                        applied = {**sources,**result.source_updates} if sources is not None else None
                        check('disabled row collection produces no additions',collect or not result.row_additions)
                        check('no source evaluation without both opt-ins',not result.source_updates if sources is None or not collect else True)
                        check('unchanged cached events retain identity',all(any(e is old for old in events) for e in out if e.source_index not in {r.base.source_index for r in result.row_additions}) if collect else True)
                    else:
                        evidence = seed if collect else None
                        out,count = module.remove_letters_over_full_lines(events,visible,sources,evidence,font_metrics=metrics[module])
                        applied = sources
                compared.append(snapshot((out,count,evidence,applied)))
            check('scaffold row/paint/source parity '+str((c['name'],order,mode)),compared[0] == compared[1])
            cases += 1

# Direct full-line callers may also share unresolved source objects. Preserve
# the old cache-visible output and source-map aliases using private successors.
for shared in (False,True):
    compared = []
    for module in (previous,current):
        events,visible,sources = lyric_inputs(module,cached=False,shared=shared,invalid='none',reset=r'\rDefault',alias=True)
        before = snapshot((events,visible,sources))
        if module is current:
            with borrowed_events([*events,*sources.values()]):
                result = module.remove_letters_over_full_lines(events,visible,sources,collect_rows=True)
            check('unresolved shared full-line inputs borrowed',before == snapshot((events,visible,sources)))
            out,count,rows = result.events,result.removed_count,result.row_additions
            applied = {**sources,**result.source_updates}
            check('shared retained caption uses source successor',not shared or out[0] is applied[out[0].source_index])
        else:
            rows = []
            out,count = module.remove_letters_over_full_lines(events,visible,sources,rows)
            applied = sources
        compared.append(snapshot((out,count,rows,applied)))
    check('unresolved full-line output and proof parity',compared[0] == compared[1])

# Exercise the pipeline owner directly, including a second timing map that
# aliases authored sources and one distinct event with the same source ID.
pipeline_compared = []
for module in (previous,current):
    events,visible,sources = lyric_inputs(module,cached=False,shared=False,invalid='none',reset=r'\rDefault',alias=False)
    source = module.parse_subtitle_document(HEADER+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in sources.values()))
    timing = dict(source.events)
    first = next(iter(source.events.values()))
    timing[999999] = first
    unrelated = replace(first,state={'fs':123})
    timing[999998] = unrelated
    prepared = module.PreparedSourceText(source.events,timing,[],0,0)
    frozen = module.FrozenTextEvents(events,[],[],visible,{},[],{'original':len(events),'dropped':0})
    captured = []
    real = module.remove_letters_over_full_lines
    def watched(*args,**kwargs):
        result = real(*args,**kwargs)
        captured.append(result)
        return result
    with patch.object(module,'remove_letters_over_full_lines',watched):
        out = module._consolidate_text_events(source,prepared,frozen,set(),module.SimplifyConfig(),None, font_report=font_test_report(None))
    if module is current:
        check('pipeline applies source delta with authored row proof',captured[0].row_additions and captured[0].source_updates and all(source.events[k] is v for k,v in captured[0].source_updates.items()))
        check('pipeline applies timing aliases',timing[999999] is source.events[first.source_index] and timing[999999] is not first)
        check('pipeline preserves distinct timing rewrite',timing[999998] is unrelated and timing[999998].state == {'fs':123})
        check('caller updates leave original source uncached',not first.state)
    pipeline_compared.append(snapshot((out,source.events,timing)))
check('pipeline cache/row application parity',pipeline_compared[0] == pipeline_compared[1])

# Failure after resolving sources must not leave borrowed caches half-installed.
events,visible,sources = lyric_inputs(current,cached=False,shared=True,invalid='none',reset='',alias=True)
before = snapshot((events,visible,sources))
with patch.object(current,'render_simplified_caption',side_effect=RuntimeError('injected row render failure')):
    try:
        current.remove_letters_over_full_lines(events,visible,sources,collect_rows=True)
    except RuntimeError as error:
        check('render exception propagated',str(error) == 'injected row render failure')
    else:
        raise AssertionError('row rendering not reached')
check('failed pass leaves source/event inputs unchanged',before == snapshot((events,visible,sources)))

# Later passes see caller-applied cache updates and row additions in complete
# conversions, including real Overlord timing/fade evidence and scaffold paint.
focused = []
for name in ('Full-line-scaffold-source.ass','Full-line-shadow-source.ass','Full-line-tracking-source.ass','Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared = []
    for module in (previous,current):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/'out.ass'
            with redirect_stdout(None):
                statistics = module.simplify_ass(ROOT/'test-data'/name,out,module.SimplifyConfig(),font_metrics=metrics[module], font_report=font_test_report(metrics[module]))
            assert statistics.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
            compared.append((out.read_bytes(),statistics))
    check('complete focused conversion '+name,compared[0] == compared[1])
    focused.append(name)

report = dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
    differential_cases=cases,focused_conversions=focused,borrowed_event_field_writes_rejected=True,
    source_aliases_and_complete_cache_history_preserved=True,scaffold_and_authored_rows_compared=True)
(ROOT/'validation/authored-lyric-ownership-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'authored lyric/source/row ownership checks passed;',cases,'cases; five focused conversions')
