#!/usr/bin/env python3
"""Compare copy clustering, caption selection and applied visibility with immutable v165."""
import test_paths
from event_evidence_test_helpers import without_inactive_color_phase_reporting  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import contour_independent_contract as contract
from contextlib import contextmanager,redirect_stdout
from pathlib import Path
import importlib.util,inspect,json,random,sys,tempfile
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current, historical_fade_timing=True)
from event_evidence_test_helpers import event_comparison_fields
from full_copy_contract_helpers import accepted_copy_clusters, assert_copy_family_coverage, copy_paint_comparison_fields

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('full_copies_reference',ROOT/'test-data/simplify_ass-v165-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
# Keep historical pass behavior while correcting its known hexadecimal suffix bug.
from outline_color_test_helpers import install_hex_parenthesis_reference_parser
install_hex_parenthesis_reference_parser(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
Style: Other,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def snapshot(value):
    if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value
BASE=[dict(word='ABCD',start=1,end=4),dict(word='AB CD',start=1.1,end=4.1)]
CASES=[]
def case(name,records):CASES.append((name,records))
case('empty',[]);case('single',BASE[:1]);case('spaced caption',BASE)
case('case and spacing',[dict(word='ab cd'),dict(word='ABCD'),dict(word='Ab  Cd')])
case('shadow paints',[dict(word='ABCD',tags=r'\1c&H221133&\bord1'),dict(word='AB CD',tags=r'\3c&HAA55CC&\bord4')])
case('effect preference',[dict(word='ABCD',effect='effect'),dict(word='ABCD')])
case('zero duration',[dict(word='ABCD',start=1,end=1),*BASE])
case('boundary overlap',[dict(word='ABCD',start=1,end=4),dict(word='AB CD',start=1.6,end=4.6)])
case('insufficient overlap',[dict(word='ABCD',start=1,end=4),dict(word='AB CD',start=1.61,end=4.61)])
case('nested copies',[dict(word='ABCD',start=1,end=8),dict(word='AB CD',start=3,end=4)])
case('same-time independent positions',[dict(word='ABCD',x=100),dict(word='AB CD',x=200)])
case('same-time independent rows',[dict(word='ABCD',row=0),dict(word='AB CD',row=1)])
case('ordinary text preserved',[dict(word='ABCD',lyric=False),dict(word='AB CD',lyric=False)])
case('comment copy',[dict(word='ABCD'),dict(word='AB CD',kind='Comment')])
case('different styles',[dict(word='ABCD'),dict(word='AB CD',style='Other')])
case('different actors',[dict(word='ABCD'),dict(word='AB CD',actor='other')])
case('different margins',[dict(word='ABCD'),dict(word='AB CD',margin='12')])
case('unpositioned copies',[dict(word='ABCD',x=None),dict(word='AB CD',x=None)])
case('unpositioned separate rows',[dict(word='ABCD',x=None,row=0),dict(word='AB CD',x=None,row=1)])
case('independent lyric',[*BASE,dict(word='OTHER')])
case('separate repeated cues',[*BASE,*[{**r,'start':r['start']+5,'end':r['end']+5} for r in BASE]])
case('crossing clusters',[dict(word='ABCD',start=1,end=4),dict(word='AB CD',start=1.5,end=4.5),
    dict(word='A B C D',start=2,end=5),dict(word='ABCD',start=2.5,end=5.5)])
rng=random.Random(156)
for n in range(50):
    records=[]
    for i in range(rng.randint(2,9)):
        start=rng.choice([1,1.2,1.5,2,4]);end=start+rng.choice([1,2,3,4])
        records.append(dict(word=rng.choice(['ABCD','AB CD','A B C D','abcd','OTHER']),
            start=start,end=end,x=rng.choice([100,100,200]),row=rng.choice([0,0,1]),
            effect=rng.choice(['','','fx']),tags=rng.choice(['',r'\bord4',r'\1c&H123456&'])))
    case('random clusters '+str(n),records)

def inputs(module,records,order,map_mode):
    lines=[]
    for d in records:
        pos='' if d.get('x',100) is None else r'\pos('+str(d.get('x',100))+',100)'
        lines.append(f"{d.get('kind','Dialogue')}: 0,{module.format_time(d.get('start',1))},{module.format_time(d.get('end',4))},{d.get('style','Default')},{d.get('actor','')},{d.get('margin','0')},0,0,{d.get('effect','')},{{{pos}{d.get('tags','')}}}{d['word']}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values())
    for e,d in zip(events,records):e.lyric=d.get('lyric',True);e.row=d.get('row',0)
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    if map_mode=='missing_all':visible={}
    elif map_mode=='missing_one' and events:visible.pop(events[0].source_index)
    elif map_mode=='wrong_one' and events:visible[events[0].source_index]='mismatch'
    visible[999999]='historical source'
    if order=='reverse':events.reverse()
    elif order=='shuffle':random.Random(156).shuffle(events)
    return events,visible

@contextmanager
def recording(module,calls):
    owner=inspect.getmodule(module.collapse_full_lyric_copies)
    originals={name:getattr(owner,name) for name in ('select_static_state',)}
    def wrap(name,original):
        def call(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            calls.append((name,before,snapshot(result)));return result
        return call
    for name,original in originals.items():setattr(owner,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(owner,name,original)

checks=[]
for name,records in CASES:
    for order in ('original','reverse','shuffle'):
        for map_mode in ('complete','missing_one','missing_all','wrong_one'):
            compared=[]
            for module in (previous,current):
                events,visible=inputs(module,records,order,map_mode)
                before=snapshot((events,visible));calls=[]
                with accepted_copy_clusters(module) as clusters,recording(module,calls):result=module.collapse_full_lyric_copies(events,visible)
                if hasattr(result,"visibility_updates"):
                    assert before==snapshot((events,visible)),(name,'borrowed inputs changed')
                    out,count=result.events,result.removed_count
                    applied={**visible,**result.visibility_updates}
                else:out,count=result;applied=visible
                if module is current:assert_copy_family_coverage(events,out,clusters)
                compared.append((snapshot(([copy_paint_comparison_fields(e) for e in out],count)),snapshot(applied),calls,
                    tuple(any(e is old for old in events) for e in out)))
            assert contract(compared[0]) == contract(compared[1]),(name,order,map_mode)
            checks.append(dict(case=name,order=order,map_mode=map_mode))

focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        original=module.collapse_full_lyric_copies;captured=[]
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            if hasattr(result,"visibility_updates"):
                assert before==snapshot((args,kwargs)),fixture
                semantic=(result.events,result.removed_count)
                after=snapshot(((args[0],{**args[1],**result.visibility_updates}),kwargs))
            else:semantic=result;after=snapshot((args,kwargs))
            captured.append((before,snapshot(semantic),after));return result
        module.collapse_full_lyric_copies=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                out=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,out,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                stats=without_inactive_color_phase_reporting(stats)
                assert stats.pop('shadow_lettering_normalized', 0)==0  # This fixture must remain unaffected by final paint normalization.
                compared.append((captured,out.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.collapse_full_lyric_copies=original
    assert contract(compared[0]) == contract(compared[1]),fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),contour_independent_contract_identical=True))

(ROOT/'validation/full-lyric-visibility-checks.json').write_text(json.dumps(dict(
    version=current.__version__,reference_version=previous.__version__,comparisons=len(checks),
    scenarios=len(CASES),contour_independent_visibility_and_selection_identical=True,
    input_ownership_and_event_identity_preserved=True,focused_conversions=focused,checks=checks),indent=2)+'\n')
print(len(checks),'full-lyric comparisons across',len(CASES),'scenarios; two focused conversions passed')
