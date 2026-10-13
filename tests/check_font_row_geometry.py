"""Row geometry parity, explicit diagnostics, batch lifetime and bounded rewiring."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from io import StringIO
import ast, contextlib, hashlib, importlib.util, inspect, json, random, sys, tempfile
from font_geometry_test_helpers import historical_static_phase_policy
import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields
from font_geometry_audit import normalized_row_algorithm, normalized_font_caller
from font_geometry_test_helpers import ROW_NAMES

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('font_rows_reference',ROOT/'test-data/simplify_ass-v165-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
# Normalize only the authorized hexadecimal suffix correction in the reference.
from outline_color_test_helpers import install_hex_parenthesis_reference_parser
install_hex_parenthesis_reference_parser(previous)
checks=[];cases=0
def check(label,value):
    assert value,label
    checks.append(label)

HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Italic, Alignment, ScaleX, ScaleY, Spacing
Style: Default,Arial,40,0,0,5,100,100,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def row(module,fragments,positions,*,family='Arial',fs=40,alignment=5,tracking=0,angle=0,duration=2):
    records=[]
    for text,x in zip(fragments,positions):
        tags=rf'\fn{family}\fs{fs}\an{alignment}\fsp{tracking}\frz{angle}\pos({x},100)'
        records.append(f'Dialogue: 0,0:00:01.00,{module.format_time(1+duration)},Default,,0,0,0,,{{{tags}}}{text}\n')
    document=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(records)))
    return list(document.events.values())

fonts=current.FontMetrics([ROOT/'fonts']);owner=previous.FontSpacing(metrics=fonts)
report=current.FontProcessingReport();matcher=current.FontOutlineMatcher(fonts)
check('no combined service or forwarding facade',not hasattr(current,'FontSpacing') and
    not any(hasattr(fonts,name) for name in (*ROW_NAMES,'missing','merged','outline_matcher')))
check('report collections are independently owned',current.FontProcessingReport().missing_families is not report.missing_families)

# Compare every return value and borrowed event/formatting object, including
# rejection paths, spacing ambiguities, scaling, tracking and missing faces.
rng=random.Random(166)
for i in range(180):
    fragments=rng.choice([list('abcd'),['ab','cd','ef','gh'],list('a b c'),['a','b','c'],['é','a','b','c']])
    options=dict(family=rng.choice(['Arial','Arial','Missing Row Font','  Missing Row Font  ']),
        fs=rng.choice([20,40,60]),alignment=rng.choice([0,1,2,4,5,6,7,9]),
        tracking=rng.choice([0,0,1,2]),angle=rng.choice([0,0,0,.1]),duration=rng.choice([.2,2]))
    positions=[100+18*j+rng.choice([0,0,.1,-.1,2]) for j in range(len(fragments))]
    events=row(current,fragments,positions,**options)
    before=deepcopy([event_comparison_fields(e) for e in events]);state=events[0].state
    max_error=rng.choice([None,.1,.2])
    arguments={
        'recover':((events,fragments),dict(max_size_error=max_error,allow_internal_spaces=bool(i%2))),
        'recover_tracked':((events,fragments),{}),
        'fragment_anchor':((state,positions,fragments,''.join(fragments),1),dict(allow_tracking=bool(i%2),separate_glyphs=bool(i%3),exact_size=bool(i%5),max_size_error=max_error)),
        'authored_glyph_positions':((state,''.join(fragments),100,1),{}),
        'matches_authored_glyph_positions':((state,positions,''.join(fragments),100,1),{}),
        'fit_fullwidth_run':((events,fragments),{}),
    }
    for old,new in ROW_NAMES.items():
        owner.missing.clear();local=current.FontProcessingReport();args,kwargs=arguments[old]
        expected=getattr(owner,old)(*args,**kwargs)
        if old in {'recover','recover_tracked','fit_fullwidth_run'}:kwargs={**kwargs,'font_report':local}
        actual=getattr(current,new)(fonts,*args,**kwargs)
        check('complete row algorithm decision '+str((i,old)),actual==expected)
        check('selective missing-font evidence '+str((i,old)),local.missing_families==owner.missing)
        check('geometry probes never count accepted joins',local.rows_joined==0)
        check('borrowed formatting/events unchanged',before==[event_comparison_fields(e) for e in events])
        cases+=1

missing=row(current,list('abcd'),[100,120,140,160],family='  Missing Exact  ')
local=current.FontProcessingReport()
current.recover_font_row(fonts,missing[:3],list('abc'),font_report=local)
check('pre-font row rejection stays silent',not local.missing_families)
current.recover_font_row(fonts,missing,list('abcd'),font_report=local)
check('row recovery preserves trimmed diagnostic name',local.missing_families=={'Missing Exact'})
local=current.FontProcessingReport()
for probe in (current.fit_fragment_anchor,current.authored_glyph_positions,current.matches_authored_glyph_positions):
    args=(missing[0].state,[100,120,140,160],list('abcd'),'abcd',1) if probe is current.fit_fragment_anchor else (
        missing[0].state,'abcd',100,1) if probe is current.authored_glyph_positions else (missing[0].state,[100,120,140,160],'abcd',100,1)
    probe(fonts,*args)
fonts.matching_face('Missing Measurement',0,False)
check('measurement and anchor probes do not broaden reporting',not local.missing_families)
context=current.VectorTextFitContext(fonts,0,{},font_report=local)
current._measure_vector_text_outline(((None,[ (missing[0],None,{**missing[0].state,'fn':'  Missing Exact  '}) ])),'abcd',context)
check('vector diagnostic preserves untrimmed family',local.missing_families=={'  Missing Exact  '})

# Full conversions preserve row counters, selective diagnostics, file bytes
# and statistics, including already-completed work before a write failure.
conversion_cases=[]
with tempfile.TemporaryDirectory() as directory, patch.object(
        current,'derive_staggered_fade_cores',lambda events,rows,sources: rows), patch.object(
        current,'synchronize_faded_cue_handoffs',lambda context,pairs,proven: {}), historical_static_phase_policy(current):
    # This release-equivalence audit retains pre-v180 fade timing. Real
    # staggered timing is covered by check_staggered_fade_cores instead.
    # Final v185 phase joins are independently checked by the unmodified
    # complete pipeline in check_late_static_phases_render.
    folder=Path(directory)
    synthetic=folder/'missing-fonts.ass'
    synthetic.write_text(HEADER+''.join(
        f'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{{\\fnMissing Batch\\pos({100+20*i},100)}}{c}\n'
        for i,c in enumerate('abcd')))
    inputs=[ROOT/'test-data'/name for name in (
        'Overlord-22m06-source.ass','Vector-text-inferred-source.ass','Vector-text-fragments-source.ass')]+[synthetic]
    batch=current.FontProcessingReport();old_batch=previous.FontSpacing(metrics=fonts)
    for repeat in range(2):
        for source in inputs:
            new_output=folder/'current.ass';old_output=folder/'reference.ass'
            with contextlib.redirect_stdout(None):
                actual=current.simplify_ass(source,new_output,current.SimplifyConfig(),font_metrics=fonts,font_report=batch,outline_matcher=matcher)
                expected=previous.simplify_ass(source,old_output,previous.SimplifyConfig(),font_spacing=old_batch)
            assert actual.pop('shadow_lettering_normalized',0)==0  # These row fixtures are outside the new normalization.
            check('complete focused subtitle unchanged',actual==expected and new_output.read_bytes()==old_output.read_bytes())
            check('batch accepted joins unchanged',batch.rows_joined==old_batch.merged)
            check('batch selective missing fonts unchanged',batch.missing_families==old_batch.missing)
            conversion_cases.append(source.name)
    check('batch actually records accepted joins',batch.rows_joined>0)
    check('batch actually discovers missing faces','Missing Batch' in batch.missing_families)
    cache_ids={key:id(value) for key,value in matcher._profiles.items()}
    source=inputs[1]
    with contextlib.redirect_stdout(None):
        current.simplify_ass(source,folder/'repeat.ass',current.SimplifyConfig(),font_metrics=fonts,font_report=batch,outline_matcher=matcher)
    check('batch matcher profile identities reused',all(id(matcher._profiles[key])==value for key,value in cache_ids.items()))
    check('batch matcher actually populated',bool(cache_ids))
    fresh=current.FontProcessingReport();old_fresh=previous.FontSpacing(metrics=fonts)
    with contextlib.redirect_stdout(None):
        current.simplify_ass(inputs[0],folder/'fresh.ass',current.SimplifyConfig(),font_metrics=fonts,font_report=fresh,outline_matcher=matcher)
        previous.simplify_ass(inputs[0],folder/'fresh-old.ass',previous.SimplifyConfig(),font_spacing=old_fresh)
    check('fresh report reuses fonts without inheriting another run',fresh.rows_joined==old_fresh.merged and fresh.missing_families==old_fresh.missing and 'Missing Batch' not in fresh.missing_families)
    for module,kwargs in ((current,dict(font_metrics=fonts,font_report=fresh,outline_matcher=matcher)),(previous,dict(font_spacing=old_fresh))):
        with patch.object(module,'write_subtitle_document',side_effect=OSError('intentional late failure')),contextlib.redirect_stdout(None):
            try:module.simplify_ass(inputs[0],folder/'failed.ass',module.SimplifyConfig(),**kwargs)
            except OSError:pass
            else:raise AssertionError('write failure was swallowed')
    check('late failures retain completed counters/evidence',fresh.rows_joined==old_fresh.merged and fresh.missing_families==old_fresh.missing)
    late_missing=current.FontProcessingReport()
    with patch.object(current,'write_subtitle_document',side_effect=OSError('late missing-font failure')),contextlib.redirect_stdout(None):
        try:current.simplify_ass(synthetic,folder/'missing-failed.ass',current.SimplifyConfig(),font_metrics=fonts,font_report=late_missing,outline_matcher=matcher)
        except OSError:pass
    check('failed conversion retains discovered missing fonts',late_missing.missing_families=={'Missing Batch'})
    # The caller may intentionally discard reporting without changing output.
    with contextlib.redirect_stdout(None):
        current.simplify_ass(inputs[0],folder/'unreported.ass',current.SimplifyConfig(),font_metrics=fonts)
    check('omitted report does not change output', (folder/'unreported.ass').read_bytes()==(folder/'fresh.ass').read_bytes())
    try:current.simplify_ass(inputs[0],folder/'mismatch.ass',current.SimplifyConfig(),font_metrics=fonts,outline_matcher=current.FontOutlineMatcher(current.FontMetrics()))
    except ValueError:check('mismatched matcher owner rejected',True)
    else:raise AssertionError('mixed font catalogs accepted')

    # Exercise real CLI ownership across successful and failing batch tracks.
    cli_sources=[]
    for index,source in enumerate((inputs[0],synthetic)):
        target=folder/f'cli-{index}.ass';target.write_bytes(source.read_bytes());cli_sources.append(target)
    expected_cli=previous.FontSpacing([ROOT/'fonts',folder/'fonts'])
    for source in cli_sources:
        with contextlib.redirect_stdout(None):previous.simplify_ass(source,folder/'cli-reference.ass',previous.SimplifyConfig(),font_spacing=expected_cli)
    out=StringIO();err=StringIO()
    with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
        with patch.object(sys,'argv',['simplify_ass.py']+[str(p) for p in cli_sources]+['--fonts-dir',str(ROOT/'fonts')]):result=current.main()
    check('CLI batch succeeds',result==0)
    check('CLI row count owns batch accumulation',f'Rows joined using font measurements: {expected_cli.merged}' in out.getvalue())
    check('CLI missing-font output unchanged','Exact fonts unavailable (kept positions): '+', '.join(sorted(expected_cli.missing)) in out.getvalue())
    real_write=current.write_subtitle_document
    def fail_one(output,*args,**kwargs):
        if output.stem.startswith('cli-1'):raise OSError('intentional batch failure')
        return real_write(output,*args,**kwargs)
    out=StringIO();err=StringIO()
    with patch.object(current,'write_subtitle_document',fail_one),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
        with patch.object(sys,'argv',['simplify_ass.py']+[str(p) for p in cli_sources]+['--fonts-dir',str(ROOT/'fonts')]):result=current.main()
    check('CLI reports failed batch track',result==1 and 'Failed files: 1/2' in err.getvalue())
    check('CLI retains failed-track diagnostics','Exact fonts unavailable (kept positions): '+', '.join(sorted(expected_cli.missing)) in out.getvalue())
    check('CLI retains completed row count',f'Rows joined using font measurements: {expected_cli.merged}' in out.getvalue())

from executable_ast_audit import executable_ast
# Source audit proves numeric methods unchanged and limits all remaining
# modifications to dependency wiring, reporting ownership and public guards.
def definitions(path):return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a=definitions(ROOT/'test-data/simplify_ass-v165-reference.py');b=definitions(ROOT/'test-data/simplify_ass-v173-reference.py')
for old,new in ROW_NAMES.items():
    reference=deepcopy(next(n for n in a['FontSpacing'].body if isinstance(n,ast.FunctionDef) and n.name==old))
    if isinstance(reference.body[0],ast.Expr) and isinstance(reference.body[0].value,ast.Constant):reference.body[0].value.value=inspect.cleandoc(reference.body[0].value.value)
    check('row numeric algorithm AST unchanged '+old,ast.dump(reference,include_attributes=False)==ast.dump(normalized_row_algorithm(b[new]),include_attributes=False))
# The v173 portable ink method has an independent bounded audit/regression.
backend=deepcopy(b['FontMetrics'])
ink=next(n for n in a['FontMetrics'].body if isinstance(n,ast.FunctionDef) and n.name=='line_ink_metrics')
backend.body=[deepcopy(ink) if isinstance(n,ast.FunctionDef) and n.name=='line_ink_metrics' else n for n in backend.body]
check('shared font backend AST unchanged outside portable ink',ast.dump(a['FontMetrics'],include_attributes=False)==ast.dump(backend,include_attributes=False))
b['FontMetrics']=backend
check('matcher and profile lifetime AST unchanged',ast.dump(a['FontOutlineMatcher'],include_attributes=False)==ast.dump(b['FontOutlineMatcher'],include_attributes=False))
check('only declared abstractions added',set(b)-set(a)=={'FontProcessingReport','TextPhaseRowsResult','SharedIntervalRowsResult',*ROW_NAMES.values(), '_representative_static_strip_outline', '_static_outline_ink_bounds', 'OutlineStripEvidence', '_collect_outline_strip_evidence', '_average_outline_strip_color', '_profile_outline_strip_transition', '_profile_outline_strip_sweep'})
# The final visibility contracts are independently audited against v166.
# Preserve extraction-policy checks against that immutable stage for the
# functions subsequently changed by the explicit visibility/document review.
contracts={'TranslatedPhaseContext','SharedIntervalContext','SubtitleDocument',
    'merge_shared_interval_rows','_prepare_shared_interval_context',
    '_merge_shared_interval_rows_once','_collect_translated_motion_profiles',
    '_prepare_translated_phases','_apply_translated_cue_proposals',
    'collapse_translated_phase_rows','_index_fragment_phase_rows',
    '_apply_fragment_phase_rows','collapse_fragment_phase_rows',
    'parse_subtitle_document','_finalize_text_layout'}
font_stage=definitions(ROOT/'test-data/simplify_ass-v166-reference.py')
# Preserve extraction assertions for the subsequently changed paint/parser
# contracts; check_static_strip_outline.py independently audits current code.
paint_contracts={'render_simplified_caption', 'apply_override', '_prepare_stacked_text_copies', '_flatten_stacked_text_group', '_render_stacked_text_caption', 'flatten_stacked_text_copies', '_consolidate_text_events', 'StackedTextContext', 'normalize_karaoke_completion_paint'}
paint_stage=definitions(ROOT/'test-data/simplify_ass-v168-reference.py')
changed=[name for name in a if name not in b or ast.dump(a[name],include_attributes=False)!=ast.dump(b[name],include_attributes=False)]
# Later token reuse is independently audited by check_outline_parsing_reuse.py.
parsing_stage=definitions(ROOT/'test-data/simplify_ass-v171-reference.py')
for name in {'evaluate_effective_state','parse_effect_transform'}:b[name]=parsing_stage[name]
for name,node in a.items():
    if name=='FontSpacing':continue
    reference=normalized_font_caller(node,reference=True)
    actual=normalized_font_caller(paint_stage[name] if name in paint_contracts else font_stage[name] if name in contracts else b[name],reference=False)
    check('caller policy AST unchanged '+name,ast.dump(reference,include_attributes=False)==ast.dump(actual,include_attributes=False))
check('no production combined-service references','FontSpacing' not in (ROOT/'simplify_ass.py').read_text())
check('no implicit geometry/cache/report owner',not any(isinstance(n,ast.Attribute) and n.attr in {'merged','missing','recover','recover_tracked','fragment_anchor','authored_glyph_positions','matches_authored_glyph_positions','fit_fullwidth_run'} for n in ast.walk(ast.parse((ROOT/'simplify_ass.py').read_text()))))
audit=dict(version=current.__version__,reference_version=previous.__version__,changed_definitions=changed,
    new_definitions=sorted(set(b)-set(a)),removed_definitions=sorted(set(a)-set(b)),
    row_algorithms_unchanged=True,font_metrics_unchanged_except_portable_ink=True,outline_matcher_unchanged=True,
    other_existing_definitions_unchanged=True,visibility_contract_followup=sorted(contracts),static_outline_followup=sorted(paint_contracts),report_commit_sites=4,selective_missing_font_sites=3)
(ROOT/'validation/structure-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
result=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),
    geometry_cases=cases,focused_conversions=conversion_cases,checks=checks)
(ROOT/'validation/font-row-geometry-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(len(checks),'font row geometry/reporting checks passed;',cases,'algorithm cases; batch, fresh-run and failure contracts verified')
