#!/usr/bin/env python3
"""Verify final visibility contracts against v166, including pending rounds."""
import test_paths  # Resolve the repository for direct test execution.
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import MappingProxyType, ModuleType
from unittest.mock import patch
import ast, contextlib, importlib.util, json, sys
import simplify_ass as s
from font_geometry_test_helpers import install_row_test_doubles, row_test_call
from event_evidence_test_helpers import event_comparison_fields

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('visibility_v166',ROOT/'test-data/simplify_ass-v166-reference.py')
old = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = old
spec.loader.exec_module(old)
install_row_test_doubles(s)
install_row_test_doubles(old)
checks = []

def check(name,condition):
    assert condition,name
    checks.append(name)

def snapshot(value):
    if type(value).__name__ == 'Event':return snapshot(event_comparison_fields(value))
    if isinstance(value,dict):return {key:snapshot(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return tuple(snapshot(item) for item in value)
    if isinstance(value,set):return frozenset(snapshot(item) for item in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def fixture_definitions(filename,stop):
    """Reuse established fixture builders without executing their test loops."""
    path = ROOT/'tests'/filename
    module = ModuleType('fixtures_'+path.stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    source = path.read_text().split(stop,1)[0]
    exec(compile(source,str(path),'exec'),vars(module))
    return module

translated = fixture_definitions('check_translated_phases.py','tracer = trace.Trace')
fragment = fixture_definitions('check_fragment_phase_stages.py','CASES=[]')
shared = fixture_definitions('check_shared_intervals.py',"for mode in ('shared_start'")
fonts = {module:module.FontMetrics([ROOT/'fonts']) for module in (s,old)}

class LookupOnly(Mapping):
    """Reject traversal/copying of the borrowed visibility history."""
    def __init__(self,values):self.values = values
    def __getitem__(self,key):return self.values[key]
    def __len__(self):return len(self.values)
    def __iter__(self):raise AssertionError('borrowed visibility traversed')

def phase_inputs(module,kind,accepted=True):
    if kind=='translated':
        descriptors = translated.entrances+translated.held+[translated.cue()]
        if not accepted:descriptors = translated.held
        return translated.inputs(module,descriptors)
    events = fragment.parse(module,fragment.sequence() if accepted else [])
    return events,{e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}

def metric(module,kind,mode):
    if mode=='none':return None
    if kind=='translated':return translated.ControlledMetric(mode)
    return fonts[module]

for kind in ('translated','fragment'):
    name = 'collapse_'+kind+'_phase_rows'
    for accepted in (True,False):
        for mode in ('none','unavailable','fit','reject_anchor') if kind=='translated' else ('none','fit'):
            expected_events,expected_visible = phase_inputs(old,kind,accepted)
            events,visible = phase_inputs(s,kind,accepted)
            visible[999999] = expected_visible[999999] = 'retained history'
            before = deepcopy(snapshot((events,visible)))
            current_report,old_report = s.FontProcessingReport(),old.FontProcessingReport()
            expected = getattr(old,name)(expected_events,expected_visible,metric(old,kind,mode),font_report=old_report)
            result = getattr(s,name)(events,visible,metric(s,kind,mode),font_report=current_report)
            label = str((kind,accepted,mode))
            check(label+' explicit result',isinstance(result,s.TextPhaseRowsResult))
            check(label+' borrowed events/map unchanged',snapshot((events,visible))==before)
            check(label+' outputs/count/rows unchanged',snapshot((result.events,result.removed_count,result.rows))==snapshot(expected))
            check(label+' selective reporting unchanged',snapshot(current_report)==snapshot(old_report))
            check(label+' sparse delta',999999 not in result.visibility_updates and set(result.visibility_updates)<=set(visible))
            check(label+' caller application matches old writes',{**visible,**result.visibility_updates}==expected_visible)
            check(label+' early-return identity preserved',(result.events is events)==(expected[0] is expected_events))
            for borrowed in (MappingProxyType(visible),LookupOnly(visible)):
                again = getattr(s,name)(events,borrowed,metric(s,kind,mode))
                check(label+' readonly/lookup-only accepted',snapshot(again)==snapshot(result))
                check(label+' independently owned delta',again.visibility_updates is not result.visibility_updates)
            try:result.rows = []
            except FrozenInstanceError:check(label+' immutable result binding',True)
            else:raise AssertionError('mutable result binding')
            if result.rows:
                check(label+' accepted proof present',all(row.pieces for row in result.rows))
                visible.update(result.visibility_updates)
                saved = visible.copy()
                result.visibility_updates.clear()
                check(label+' application has no mutable alias',visible==saved)

# Compare every translated admission/fallback fixture with the last release.
for name,descriptors in translated.cases:
    for mode in ('none','unavailable','reject_positions','reject_anchor','fit','real'):
        expected_events,expected_visible = translated.inputs(old,descriptors)
        events,visible = translated.inputs(s,descriptors)
        before = deepcopy(snapshot((events,visible)))
        a = fonts[old] if mode=='real' else metric(old,'translated',mode)
        b = fonts[s] if mode=='real' else metric(s,'translated',mode)
        old_report,current_report = old.FontProcessingReport(),s.FontProcessingReport()
        expected = old.collapse_translated_phase_rows(expected_events,expected_visible,a,font_report=old_report)
        result = s.collapse_translated_phase_rows(events,visible,b,font_report=current_report)
        check(name+mode+' translated decisions/evidence preserved',snapshot(expected)==snapshot((result.events,result.removed_count,result.rows)))
        check(name+mode+' translated inputs unchanged',before==snapshot((events,visible)))
        check(name+mode+' translated writes/report preserved',{**visible,**result.visibility_updates}==expected_visible and snapshot(current_report)==snapshot(old_report))

# Fragment chains retain geometry, timing cores, ownership and rejection rules.
for phases in (1,2,6):
    for direction in (1,-1):
        for missing in (False,True):
            descriptors = fragment.sequence(phases=phases,direction=direction)
            if missing:descriptors.pop(0)
            expected_events = fragment.parse(old,descriptors)
            events = fragment.parse(s,descriptors)
            old_visible = {e.source_index:old.simplify_text(e.text,visible_only=True)[1] for e in expected_events}
            visible = {e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in events}
            before = deepcopy(snapshot((events,visible)))
            expected = old.collapse_fragment_phase_rows(expected_events,old_visible,fonts[old])
            result = s.collapse_fragment_phase_rows(events,LookupOnly(visible),fonts[s])
            check('fragment chain '+str((phases,direction,missing)),snapshot(expected)==snapshot((result.events,result.removed_count,result.rows)) and before==snapshot((events,visible)) and {**visible,**result.visibility_updates}==old_visible)

for count in (4,8):
    seed = shared.load([shared.event('i',488,1,2)])[0][0]
    text = ('itsu'*2)[:count]
    positions = s.authored_glyph_positions(fonts[s],seed.state,text,550,seed.unit)
    check('shared exact positions available',positions is not None)
    parts = [shared.event(char,x,1,2+.2*i) for i,(char,x) in enumerate(positions)]
    events,visible = shared.load(parts)
    visible[999999] = 'retained history'
    original = deepcopy(snapshot((events,visible)))
    expected_events = list(old._resolve_document_state(old.parse_subtitle_document(shared.header+''.join(parts))).events.values())
    old_visible = {e.source_index:old.simplify_text(e.text,visible_only=True)[1] for e in expected_events}
    old_visible[999999] = 'retained history'
    old_report,current_report = old.FontProcessingReport(),s.FontProcessingReport()
    expected = old.merge_shared_interval_rows(expected_events,old_visible,fonts[old],set(old_visible),font_report=old_report)
    round_reads = []
    once = s._merge_shared_interval_rows_once
    def tracked_round(batch,pending,*args,**kwargs):
        round_reads.append({e.source_index:pending.get(e.source_index) for e in batch})
        return once(batch,pending,*args,**kwargs)
    with patch.object(s,'_merge_shared_interval_rows_once',tracked_round):
        result = s.merge_shared_interval_rows(events,LookupOnly(visible),fonts[s],set(visible),font_report=current_report)
    check('shared explicit result',isinstance(result,s.SharedIntervalRowsResult))
    check('shared accepted rows/tails',result.rows_joined>0 and result.tails_retained>0)
    check('shared inputs unchanged',snapshot((events,visible))==original)
    check('shared outputs/counts unchanged',snapshot((result.events,result.rows_joined,result.tails_retained))==snapshot(expected))
    check('shared writes/report unchanged',{**visible,**result.visibility_updates}==old_visible and snapshot(current_report)==snapshot(old_report))
    check('later round reads generated visibility',len(round_reads)>1 and any(key not in visible and value for key,value in round_reads[1].items()))
    check('shared sparse generated-ID delta',set(result.visibility_updates).isdisjoint(visible))
    again = s.merge_shared_interval_rows(events,MappingProxyType(visible),fonts[s],set(visible))
    check('shared readonly map accepted',snapshot(again)==snapshot(result) and again.visibility_updates is not result.visibility_updates)
    try:result.events = []
    except FrozenInstanceError:check('shared immutable result binding',True)
    else:raise AssertionError('mutable result binding')
    no_font = s.merge_shared_interval_rows(events,LookupOnly(visible),None,set(visible))
    check('shared unavailable early identity',no_font.events is events and not no_font.visibility_updates and no_font.rows_joined==no_font.tails_retained==0)

# A failure after committing a private caption cannot leak shared-map writes.
for kind,helper in [('translated','_apply_translated_cue_proposals'),('fragment','_apply_fragment_phase_rows'),('shared','_apply_shared_interval_proposal')]:
    if kind=='shared':events,visible = shared.load(parts)
    else:events,visible = phase_inputs(s,kind)
    before = deepcopy(snapshot((events,visible)))
    original_helper = getattr(s,helper)
    committed = []
    def fail_after_commit(*args,**kwargs):
        result = original_helper(*args,**kwargs)
        if kind!='shared':assert result.rows,'failure must follow a real accepted row'
        committed.append(True)
        raise RuntimeError('intentional failure after private acceptance')
    with patch.object(s,helper,fail_after_commit):
        try:
            if kind=='shared':s.merge_shared_interval_rows(events,visible,fonts[s],set(visible))
            else:getattr(s,'collapse_'+kind+'_phase_rows')(events,visible,metric(s,kind,'fit'))
        except RuntimeError:check(kind+' failure after acceptance reached',bool(committed))
        else:raise AssertionError('failure hook not reached')
    check(kind+' failure leaves caller state unchanged',snapshot((events,visible))==before)

# The document still serializes original records after dropping the unused buffer.
for ending in ('\n','\r\n','\r',''):
    raw = translated.HEADER.replace('\n',ending or '\n')
    document = s.parse_subtitle_document(raw)
    previous = old.parse_subtitle_document(raw)
    check('document raw field removed','raw' not in {f.name for f in fields(document)})
    check('document serialization unchanged',s.render_subtitle_document(document,list(document.events.values()))==old.render_subtitle_document(previous,list(previous.events.values())))

from executable_ast_audit import executable_ast
def definitions(path):
    return {node.name:node for node in executable_ast(ast.parse(path.read_text())).body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef))}

baseline = definitions(Path(old.__file__))
# v174 final paint normalization has a separate complete source audit.
current = definitions(ROOT/'test-data/simplify_ass-v173-reference.py')
# This later paint/parser fix has its own complete v168 source audit.
# Keep the v167 visibility extraction audit on its immutable closing stage.
paint_followup = {'render_simplified_caption', 'apply_override', '_prepare_stacked_text_copies', '_flatten_stacked_text_group', '_render_stacked_text_caption', 'flatten_stacked_text_copies', '_consolidate_text_events', 'StackedTextContext', 'normalize_karaoke_completion_paint'}
closing_stage = definitions(ROOT/'test-data/simplify_ass-v168-reference.py')
for name in paint_followup:current[name] = closing_stage[name]
for name in {'_static_outline_ink_bounds', '_representative_static_strip_outline', 'OutlineStripEvidence', '_collect_outline_strip_evidence', '_average_outline_strip_color', '_profile_outline_strip_transition', '_profile_outline_strip_sweep'}:current.pop(name)
# v172 token reuse has its own complete audit; retain the closing-stage proof.
parsing_stage = definitions(ROOT/'test-data/simplify_ass-v171-reference.py')
for name in {'evaluate_effective_state','parse_effect_transform'}:current[name] = parsing_stage[name]
# v173 portable ink has its own method audit; retain this extraction baseline.
current['FontMetrics']=definitions(ROOT/'test-data/simplify_ass-v172-reference.py')['FontMetrics']
allowed = {'TranslatedPhaseContext','SharedIntervalContext','SubtitleDocument',
    'merge_shared_interval_rows','_prepare_shared_interval_context',
    '_merge_shared_interval_rows_once','_collect_translated_motion_profiles',
    '_prepare_translated_phases','_apply_translated_cue_proposals',
    'collapse_translated_phase_rows','_index_fragment_phase_rows',
    '_apply_fragment_phase_rows','collapse_fragment_phase_rows',
    'parse_subtitle_document','_finalize_text_layout'}
changed = {name for name in baseline if name in current and
    ast.dump(baseline[name],include_attributes=False)!=ast.dump(current[name],include_attributes=False)}
check('only declared results added',set(current)-set(baseline)=={'TextPhaseRowsResult','SharedIntervalRowsResult'})
check('no prior functions/classes removed',not set(baseline)-set(current))
check('bounded contract changes only',changed==allowed)
for name in set(baseline)-allowed:
    check('unrelated definition unchanged '+name,ast.dump(baseline[name],include_attributes=False)==ast.dump(current[name],include_attributes=False))
audit = dict(version=s.__version__,reference_version=old.__version__,
    changed_definitions=sorted(changed),new_definitions=sorted(set(current)-set(baseline)),
    removed_definitions=[],other_existing_definitions_unchanged=True,
    separately_audited_paint_followup=sorted(paint_followup))
(ROOT/'validation/final-visibility-structure-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
(ROOT/'validation/final-visibility-ownership-checks.json').write_text(json.dumps(dict(
    version=s.__version__,reference_version=old.__version__,checks_passed=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'final visibility ownership checks passed')
