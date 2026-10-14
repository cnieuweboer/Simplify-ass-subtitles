#!/usr/bin/env python3
"""Verify borrowed reconstruction inputs, explicit deltas and final row timing."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
import contextlib,importlib.util,json,statistics,sys,tempfile
import simplify_ass as s
from event_evidence_test_helpers import freeze_caption_policy_for_legacy_comparison
freeze_caption_policy_for_legacy_comparison(s)
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(s, historical_fade_timing=True)
from event_evidence_test_helpers import event_comparison_fields

ROOT=Path(__file__).resolve().parents[1]
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def fixture(*,sweep=False,tails=False,confirmed=False,paint=False):
    lines=[]
    groups=(('ABCD',1.,4.1),('EFGH',3.8,6.1)) if tails else (('ABCD',1.,4.),)
    offsets=(.08,.02,0.,.10)
    for word,start,end in groups:
        for i,c in enumerate(word):
            offset=offsets[i] if tails else .1*i if sweep else 0
            tags=r'\pos('+str(100+24*i)+r',100)'
            if paint:tags+=r'\1c&H112233&'
            lines.append(f'Dialogue: 0,{s.format_time(start+offset)},{s.format_time(end+offset)},Default,,0,0,0,,{{{tags}}}{c}\n')
    if not sweep and not tails:
        lines.append('Comment: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,ABCD\n')
    doc=s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values())
    for e in events:e.lyric=e.kind=='Dialogue';e.row=1
    visible={e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in events}
    visible[999]='historical fragment'
    animated={e.source_index for e in events if e.lyric} if sweep else set()
    rows=[]
    if confirmed:
        pieces=[(e,visible[e.source_index],s.get_pos(e.text)) for e in events[:4]]
        base=events[0]
        base.evidence=s.EventEvidence(opaque_spans=((1.,4.),))
        rows=[s.TextRow(base,pieces,[events[:4]],{'A':[(100.,100.)]},
            [events[3]],True,True,(1.25,3.75))]
    return events,visible,{},animated,rows,{e.source_index:e for e in events}

class Metric:
    available=True
    def __init__(self):self.merged=0
    def recover(self,ordered,fragments):
        return ''.join(fragments),statistics.median(s.get_pos(e.text)[0] for e in ordered),100,100,5
    def recover_tracked(self,ordered,fragments):return (*self.recover(ordered,fragments),0)
    def fit_fullwidth_run(self,ordered,fragments):return None

def snapshot(args):
    events,visible,spaces,animated,rows,sources=args
    return deepcopy(([event_comparison_fields(e) for e in events],dict(visible),spaces,animated,
        [vars(r) for r in rows],{k:event_comparison_fields(e) for k,e in sources.items()}))
def run(args,metric=None,**options):
    events,visible,spaces,animated,rows,sources=args
    return s.reconstruct_text_rows(events,visible,spaces,metric,animated,
        source_rows=rows,source_events=sources,**options, font_report=font_test_report(metric))

for mode in ('normal','sweep','tails','static','source-only','source-static'):
    args=fixture(sweep=mode=='sweep',tails=mode=='tails',confirmed=mode.startswith('source'),paint=mode.startswith('source'))
    before=snapshot(args)
    options=dict(source_only=mode.startswith('source'),static_only=mode in ('static','source-static'))
    result=run(args,Metric(),**options)
    check(mode+' borrowed inputs unchanged',snapshot(args)==before)
    check(mode+' result bindings explicit',isinstance(result,s.RowReconstructionResult) and
        isinstance(result.events,list) and isinstance(result.rows,list) and isinstance(result.visibility_updates,dict))
    check(mode+' historical visibility retained',args[1][999]=='historical fragment' and 999 not in result.visibility_updates)
    check(mode+' no fragment deletion deltas',all(index in args[1] for index in result.visibility_updates))
    merged={**args[1],**result.visibility_updates}
    check(mode+' returned text agrees with applied visibility',all(
        merged[e.source_index]==s.simplify_text(e.text,visible_only=True)[1]
        for e in result.events if e.kind=='Dialogue'))
    check(mode+' row bases agree with output timing',all(row.virtual or any(
        e is row.base and e.start==s.format_time(e.start_s) and e.end==s.format_time(e.end_s)
        for e in result.events) for row in result.rows))
    check(mode+' output event evidence not implicit on source',all(
        source.start_s==old['start_s'] and source.end_s==old['end_s']
        for source,old in zip(args[0],before[0])))
    if mode=='normal':
        check('normal merge count explicit',result.merged_count==3 and result.duplicate_count==0)
        check('caller owns visibility application',args[1][result.events[0].source_index]=='A' and
            result.visibility_updates[result.events[0].source_index]=='ABCD')
        args[1].update(result.visibility_updates)
        result.visibility_updates.clear()
        check('applied visibility independent of result delta',args[1][result.events[0].source_index]=='ABCD')
    elif mode=='source-only':
        old,new=args[4][0],result.rows[0]
        check('source paint normalized into successor',new is not old and new.base is new.pieces[0][0])
        check('source paint preserves timing and history',new.phase_core==old.phase_core and new.virtual==old.virtual and
            new.base.start_s==old.base.start_s and new.base.end_s==old.base.end_s and
            new.foreground[0] is old.foreground[0])
        check('source paint row containers independent',new.pieces is not old.pieces and new.paint_rows is not old.paint_rows and
            new.paint_rows[0] is not old.paint_rows[0] and new.source_anchors is not old.source_anchors and
            new.source_anchors['A'] is not old.source_anchors['A'] and new.foreground is not old.foreground)
        check('source paint has no visibility update',result.visibility_updates=={} and result.merged_count==0)
        new.paint_rows[0].clear();new.source_anchors['A'].clear();new.foreground.clear();new.pieces.clear()
        check('source normalized nested edits isolate source evidence',snapshot(args)==before)
    elif mode=='tails':
        first=result.rows[0]
        check('tail trim returned consistently',first.base.end_s==3.8 and first.base.end==s.format_time(3.8) and
            result.events[0] is first.base)
        check('tail trim retains authored fragment intervals',max(e.end_s for e,_,_ in first.pieces)>first.base.end_s)
    elif mode=='source-static':
        check('source static early branch keeps resolved events',all(a is b for a,b in zip(result.events,args[0])) and result.rows==[])

args=fixture();args=(args[0],MappingProxyType(args[1]),*args[2:])
result=run(args)
check('read-only caller visibility accepted',result.merged_count==3 and result.visibility_updates)

# Shared-held-letter joins and ordinary joins both write through the same
# private overlay. Later consumers see pending text before caller application.
args=fixture();context,edits=s._prepare_row_reconstruction(args[0],args[1],args[2],None,args[3],args[5],static_only=False, font_report=font_test_report(None))
edits.visibility_updates[args[0][0].source_index]='pending caption'
check('pass-local overlay sees pending visibility',context.visible_map[args[0][0].source_index]=='pending caption')
check('pass-local overlay leaves borrowed map intact',args[1][args[0][0].source_index]=='A')

args=fixture();before=snapshot(args);original=s._trim_reconstructed_row_tails
def fail(*unused):raise RuntimeError('injected timing failure')
s._trim_reconstructed_row_tails=fail
try:run(args)
except RuntimeError:check('failure after merge leaves borrowed map and evidence intact',snapshot(args)==before)
else:raise AssertionError('expected injected failure')
finally:s._trim_reconstructed_row_tails=original
empty=s.reconstruct_text_rows([],{}, {},None,set(), font_report=font_test_report(None))
check('empty reconstruction explicit',empty.events==[] and empty.rows==[] and empty.visibility_updates=={} and empty.merged_count==0)
try:empty.merged_count=1
except FrozenInstanceError:check('result bindings immutable',True)
else:raise AssertionError('mutable result binding')

# Verify real caller boundaries and source-only paint normalization, then
# compare outputs/statistics against the current production reference.
spec=importlib.util.spec_from_file_location('reconstruction_reference',ROOT/'test-data/simplify_ass-v153-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
# Keep historical pass behavior while correcting its known hexadecimal suffix bug.
from outline_color_test_helpers import install_hex_parenthesis_reference_parser
install_hex_parenthesis_reference_parser(previous)
focused=[]
for fixture_name in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,s):
        calls=[];original=module.reconstruct_text_rows
        def wrapped(*args,**kwargs):
            result=original(*args,**kwargs)
            calls.append(dict(source_only=kwargs.get('source_only',False),static_only=kwargs.get('static_only',False)))
            return result
        module.reconstruct_text_rows=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture_name,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
                compared.append((output.read_bytes(),stats,calls,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.reconstruct_text_rows=original
    check(fixture_name+' caller conversion unchanged',compared[0]==compared[1])
    focused.append(dict(fixture=fixture_name,reconstruction_calls=calls,identical=True))

(ROOT/'validation/row-reconstruction-ownership-checks.json').write_text(json.dumps(
    dict(version=s.__version__,count=len(checks),checks=checks,focused_conversions=focused),indent=2)+'\n')
print(len(checks),'row-reconstruction ownership checks and 2 focused conversions passed')
