import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare source-fragment phases, matching, particle guards and foreground updates with v152."""
from pathlib import Path
from copy import deepcopy
from collections.abc import Iterator
import ast,contextlib,importlib.util,json,math,random,sys,tempfile,trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source_fragment_reference',ROOT/'test-data/simplify_ass-v152-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
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
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,Iterator):return ('iterator',type(value).__name__)
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if hasattr(value,'matching_face') and hasattr(value,'available'):return ('font_metrics',value.available,font_test_report(value).rows_joined,tuple(sorted(font_test_report(value).missing_families)))
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def event(word,x=100,y=100,start=1,end=5,layer=0,tags='',**options):
    return dict(word=word,x=x,y=y,start=start,end=end,layer=layer,tags=tags,**options)
def source_row(words=('ab','cd','ef','gh'),step=30,layers=(0,1),**options):
    return [event(word,100+i*step,layer=layer,owner=0,paint=paint,piece=paint==0,**options) for paint,layer in enumerate(layers) for i,word in enumerate(words)]
def dense(copies=3,words=('ab','cd','ef','gh'),**options):
    return source_row(words)+[event(word,100+i*30,start=1.1+j*.2,end=1.2+j*.2,tags=r'\t(0,100,\1a&HFF&)',animated=True,**options) for j in range(copies) for i,word in enumerate(words)]
def highlight(word='abcd',x=115,**options):return source_row()+[event(word,x,start=1.1,end=1.3,layer=2,tags=r'\t(0,100,\1a&HFF&)',animated=True,**options)]
def change(records,predicate=lambda i,d:d.get('animated',False),**options):
    result=deepcopy(records)
    for i,d in enumerate(result):
        if predicate(i,d):d.update(options)
    return result
BASE=dense();CASES=[]
def case(name,records=None,expected=None,confirmed=None,**options):CASES.append(dict(name=name,records=BASE if records is None else records,expected=expected,confirmed=confirmed,**options))
case('dense anchored family',expected=16,confirmed=True)
case('ordinary layered source row',source_row(),0,False)
case('no source rows',no_rows=True,expected=0)
case('empty input',[],0,no_rows=True)
case('short source row',dense(words=('a','b','c','d')),0,False)
case('single paint layer',source_row(layers=(0,))+BASE[8:],0,False)
case('incomplete dense family',dense(2),0,False)
case('only two distinct anchored fragments',source_row()+[d for d in BASE[8:] if d['word'] in ('ab','cd')],0,False)
case('single nested complete fragment',highlight(),1,False)
case('single nested glyph fragment',highlight('ab',100),1,False)
case('nested cached match',highlight()+[deepcopy(highlight()[-1])],2,False)
case('nested same layer',change(highlight(),layer=1),0,False)
case('nested nonnumeric layer',change(highlight(),layer='bad'),0,False)
case('nested negative layer',change(highlight(),layer=-1),0,False)
case('nested nearly full duration',change(highlight(),start=1,end=4.99),0,False)
case('nested extends past base',change(highlight(),end=5.1),0,False)
case('nested starts before base',change(highlight(),start=.99),0,False)
case('nested too far horizontally',change(highlight(),x=120),0,False)
case('nested too far vertically',change(highlight(),y=103),0,False)
case('nested fragment with spaces',highlight('ab cd',115),1,False)
case('nested unknown fragment',highlight('zzzz',115),0,False)
case('nested static copy',change(highlight(),animated=False),0,False)
case('nested moving layout transform',change(highlight(),tags=r'\t(0,100,\fs50)'),0,False)
case('nested scale-only transform',change(highlight(),tags=r'\t(0,100,\fscx50)'),1,False)
case('nested fully hidden fill',change(highlight(),tags=r'\1a&H80&'),0,False)
case('nested origin tag',change(highlight(),tags=r'\org(115,100)'),0,False)
case('nested move tag',change(highlight(),tags=r'\move(115,100,115,100)'),0,False)
case('nested inline layout',change(highlight(),word=r'ab{\fs40}cd'),0,False)
case('nested different font',change(highlight(),tags=r'\fnOtherFont'),0,False)
case('nested different spacing',change(highlight(),tags=r'\fsp1'),0,False)
case('nested clipped',change(highlight(),tags=r'\clip(0,0,1000,1000)'),0,False)
case('repeated nearby fragments are ambiguous',source_row(words=('ab','ab','ab','ab'),step=5)+[event('ab',102.5,start=1.1,end=1.3,layer=2,animated=True)],0,False)
case('large fragment gap cannot match syllable',source_row(step=200)+[event('abcd',200,start=1.1,end=1.3,layer=2,animated=True)],0,False)
case('unresolved candidate states',change(BASE,unresolved=True),16,True)
case('font names match without case sensitivity',change(BASE,tags=r'\fnARIAL'),16,True)
case('accepted font-size tolerance',change(BASE,tags=r'\fs42'),16,True)
case('font size outside tolerance',change(BASE,tags=r'\fs42.01'),0,False)
for name,tags in (('drawing',r'\p1'),('clip',r'\clip(0,0,1000,1000)'),('inverse clip',r'\iclip(0,0,1000,1000)'),('font mismatch',r'\fnOtherFont'),('bold mismatch',r'\b1'),('italic mismatch',r'\i1'),('alignment mismatch',r'\an7')):
    case(name,change(BASE,tags=tags),0,False)
case('distant anchors',change(BASE,x=500),0,False)
case('distant vertical anchors',change(BASE,y=111),0,False)
case('candidate source family mismatch',change(BASE,name='other'),0,False)
case('candidate style mismatch',change(BASE,style='Other'),0,False)
case('candidate margin mismatch',change(BASE,margin_l=10),0,False)
case('missing candidate word',change(BASE,missing_word=True),0,False)
case('missing candidate position',change(BASE,missing_position=True),0,False)
case('candidate before row',change(BASE,start=.99,end=1.2),0,False)
case('candidate beyond delayed window',change(BASE,start=6.01,end=6.2),0,False)
case('delayed opaque lyric retained',change(BASE,start=5.1,end=5.2),0,False)
case('delayed actual fades',change(BASE,start=5.1,end=5.2,tags=r'\alpha&H80&\t(0,100,\1a&HFF&)'),16,True)
case('delayed transparency alone insufficient',change(BASE,start=5.1,end=5.2,tags=r'\alpha&H80&'),0,False)
case('delayed static copy retained',change(BASE,start=5.1,end=5.2,tags=r'\alpha&H80&\t(0,100,\1a&HFF&)',animated=False),0,False)
later=[event('ab',100,start=5,end=8,owner=1,paint=0,piece=True)]
case('later stable row owns repeated delayed fragment',change(BASE,start=5.1,end=5.2,tags=r'\alpha&H80&\t(0,100,\1a&HFF&)')+later,13,True,protected_word='ab')
case('later distant row does not take ownership',change(BASE,start=5.1,end=5.2,tags=r'\alpha&H80&\t(0,100,\1a&HFF&)')+change(later,lambda i,d:True,x=200),16,True)
origin=[{**d,'y':145,'tags':rf"\alpha&H80&\org({d['x']},2000)\fscx80"} if d.get('animated') else d for d in BASE]
case('rising shrinking distant-origin copies',origin,16,True)
case('distant-origin copy still needs transparency',change(origin,tags=r'\org(100,2000)\fscx80'),0,False)
case('distant-origin wrong horizontal center',change(origin,tags=r'\alpha&H80&\org(500,2000)\fscx80'),0,False)
case('distant-origin must be far away',change(origin,tags=r'\alpha&H80&\org(100,200)\fscx80'),0,False)
case('distant-origin cannot grow',[{**d,'tags':d['tags'].replace('fscx80','fscx120')} for d in origin],0,False)
case('distant-origin copy beyond vertical bound',change(origin,y=181),0,False)
# Alternating visibility is a separate whole-cue proof, independent of dense-particle confirmation.
phases=source_row(layers=(0,1,2,3));phases=[{**d,'spans':((1.,3.),) if d['paint']<2 else ((3.,5.),)} for d in phases]
case('complete alternating layered phases',phases,8,False)
case('phase gap',[{**d,'spans':((3.01,5.),)} if d['paint']>=2 else d for d in phases],0,False)
case('phase overlap',[{**d,'spans':((2.99,5.),)} if d['paint']>=2 else d for d in phases],0,False)
case('incomplete phase tail',[{**d,'spans':((3.,4.99),)} if d['paint']>=2 else d for d in phases],0,False)
case('single alternate phase',[{**d,'spans':((1.,3.),)} for d in source_row()],0,False)
case('phase needs two layers',phases[:12],0,False)
case('empty alternate spans',[{**d,'spans':()} if d['paint']>=2 else d for d in phases],0,False)
case('multispan phase cover',[{**d,'spans':((1.,2.),(3.,4.)) if d['paint']<2 else ((2.,3.),(4.,5.))} for d in phases],8,False)
case('initial row confirmation preserved',source_row(),0,True,seeded_confirmation=True)
case('duplicate row evidence',duplicate_row=True,expected=16,confirmed=True)
case('duplicate source identity',BASE+[deepcopy(BASE[8])],16,True,duplicate_source=True)
case('row with no anchors',empty_anchors=True,expected=0,confirmed=False)
case('all candidates animated foreground fallback',animate_all=True,expected=16,confirmed=True)

def inputs(module,c,order,animation):
    records=c['records'];lines=[]
    for d in records:
        text='{'+f"\\pos({d['x']},{d['y']})"+d['tags']+'}'+d['word']
        lines.append(f"Dialogue: {d['layer']},{module.format_time(d['start'])},{module.format_time(d['end'])},{d.get('style','Default')},{d.get('name','')},{d.get('margin_l',0)},0,0,,{text}\n")
    doc=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)));events=list(doc.events.values())
    if c.get('duplicate_source') and events:events[-1].source_index=events[8].source_index
    words={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events};positions={e.source_index:module.get_pos(e.text) for e in events}
    for e,d in zip(events,records):
        if 'spans' in d:
            e.evidence=module.EventEvidence(opaque_spans=d['spans'])
        if d.get('unresolved'):e.state={}
        if d.get('missing_word'):words.pop(e.source_index,None)
        if d.get('missing_position'):positions[e.source_index]=None
    rows=[]
    for owner in sorted({d['owner'] for d in records if 'owner' in d}):
        paint={};pieces=[];anchors={}
        for e,d in zip(events,records):
            if d.get('owner')!=owner:continue
            paint.setdefault(d['paint'],[]).append(e)
            if d.get('piece'):
                word=words[e.source_index];pos=positions[e.source_index];pieces.append((e,word,pos));anchors.setdefault(word,[]).append(pos)
        row=module.TextRow(pieces[0][0],pieces,list(paint.values()),{} if c.get('empty_anchors') else anchors)
        if c.get('seeded_confirmation'):row.confirmed=True;row.foreground=[pieces[0][0]]
        rows.append(row)
    if c.get('duplicate_row'):rows.append(module.TextRow(rows[0].base,rows[0].pieces.copy(),rows[0].paint_rows.copy(),deepcopy(rows[0].source_anchors)))
    if c.get('no_rows'):rows=[]
    animated={e.source_index for e,d in zip(events,records) if d.get('animated') or c.get('animate_all')}
    if animation=='none':animated=None
    if animation=='empty':animated=set()
    if order=='reversed':events.reverse();rows.reverse()
    if order=='shuffled':random.Random(129).shuffle(events);random.Random(129).shuffle(rows)
    return events,rows,words,positions,animated
SPY_NAMES=('match_translucent_glyph_particles','match_repeated_glyph_flashes','text_height',
    'index_fragment_spans','matching_fragment_spans','text_layout_key','effective_state',
    'inline_layout_key','tokenize_override','collapse_backed_glyph_pulses','collapse_sliced_text_sequences')
@contextlib.contextmanager
def recording(module,calls):
    originals={name:getattr(module,name) for name in SPY_NAMES}
    def wrap(name,original):
        def run(*args,**kwargs):
            calls.append((name,snapshot((args,kwargs))));return original(*args,**kwargs)
        return run
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix],ignoremods=['check_source_fragment_stages']);checks=[]
metrics={module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
unavailable={module:module.FontMetrics([]) for module in (previous,current)}
for metric in unavailable.values():metric.available=False
for i,c in enumerate(CASES):
    if i%20==0:print(i,'source-fragment scenarios compared',flush=True)
    for order in ('original','reversed','shuffled'):
        for animation in ('authored','none','empty'):
            for font_mode in ('available','none','unavailable'):
                compared=[]
                for module in (previous,current):
                    events,rows,words,positions,animated=inputs(module,c,order,animation);calls=[]
                    borrowed_ids={id(e) for e in events if e.state};input_before=snapshot((events,rows));map_before=snapshot((words,positions,animated));containers=[(id(r.pieces),id(r.paint_rows),id(r.source_anchors)) for r in rows]
                    metric=metrics[module] if font_mode=='available' else unavailable[module] if font_mode=='unavailable' else None
                    with recording(module,calls):
                        args=(events,rows,words,positions,animated);kwargs=dict(font_metrics=metric)
                        result=tracer.runfunc(module.remove_source_fragment_effects,*args,**kwargs) if module is current and order=='original' and animation=='authored' and font_mode=='none' else module.remove_source_fragment_effects(*args,**kwargs)
                    if module is current:
                        out,count,updated=result.events,result.removed_effects,result.rows
                        assert input_before==snapshot((events,rows)),(c['name'],'borrowed evidence changed')
                        assert updated is not rows and all(a is not b for a,b in zip(updated,rows))
                        for a,b in zip(updated,rows):
                            assert a.pieces is not b.pieces and a.paint_rows is not b.paint_rows
                            assert all(x is not y for x,y in zip(a.paint_rows,b.paint_rows))
                            assert a.source_anchors is not b.source_anchors and a.foreground is not b.foreground
                            assert all(a.source_anchors[k] is not b.source_anchors[k] for k in b.source_anchors)
                        rows=updated
                    else:out,count=result
                    assert map_before==snapshot((words,positions,animated)),(c['name'],'caller maps/set changed')
                    if module is previous:assert containers==[(id(r.pieces),id(r.paint_rows),id(r.source_anchors)) for r in rows],(c['name'],'row containers replaced')
                    assert all(any(e.source_index==original.source_index and e.text==original.text for original in events) for r in rows for e in r.foreground),(c['name'],'foreground provenance')
                    if animation=='authored':
                        if c['expected'] is not None:assert count==c['expected'],(c['name'],'expected count',count,c['expected'])
                        if c['confirmed'] is not None and rows:assert rows[0 if order=='original' else next(j for j,r in enumerate(rows) if len(r.pieces)>=4)].confirmed==c['confirmed'],(c['name'],'foreground confirmation')
                        if c.get('protected_word'):
                            protected=[e.source_index for e in events if e.source_index in (animated or set()) and words.get(e.source_index)==c['protected_word']]
                            assert all(k in {e.source_index for e in out} for k in protected),(c['name'],'later-row precedence')
                    compared.append((snapshot((out,count,rows)),snapshot((words,positions,animated)),calls,
                        [e.source_index for e in out if id(e) in borrowed_ids],
                        [[e.source_index for e in r.foreground] for r in rows],snapshot(metric)))
                assert compared[0]==compared[1],(c['name'],order,animation,font_mode,'v152 equivalence')
                checks.append(dict(case=c['name'],order=order,animation=animation,font_metrics=font_mode))
focused=[]
for fixture in ('Overlord-22m06-source.ass','Overlord-opening-fades-source.ass'):
    compared=[]
    for module in (previous,current):
        captured=[];original=module.remove_source_fragment_effects
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            if module is current:
                assert before==snapshot((args,kwargs)),fixture
                semantic=(result.events,result.removed_effects,result.rows)
            else:semantic=(*result,args[1])
            captured.append((before,snapshot(semantic)));return result
        module.remove_source_fragment_effects=wrapped
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(None):stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((captured,output.read_bytes(),stats,font_test_report(metric).rows_joined,sorted(font_test_report(metric).missing_families)))
        finally:module.remove_source_fragment_effects=original
    assert compared[0]==compared[1],fixture
    focused.append(dict(fixture=fixture,target_calls=len(captured),identical=True))
audit=json.loads((ROOT/'validation/source-fragment-extraction-audit.json').read_text());filename=Path(current.__file__).resolve()
executed={line for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==filename and count};coverage={}
for node in ast.parse(filename.read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in audit['helpers']:
        statements={n.lineno for n in ast.walk(node) if isinstance(n,ast.stmt) and not isinstance(n,ast.FunctionDef) and not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))}
        coverage[node.name]=dict(exercised=bool(set(range(node.lineno,node.end_lineno+1))&executed),statement_lines=len(statements),executed_statement_lines=len(statements&executed),unexecuted_lines=sorted(statements-executed))
assert len(coverage)==12 and all(v['exercised'] for v in coverage.values()),coverage
(ROOT/'validation/source-fragment-checks.json').write_text(json.dumps(dict(reference_version=previous.__version__,version=current.__version__,scenarios=len(CASES),comparisons=len(checks),caller_maps_and_animation_set_unchanged=True,events_counts_and_returned_row_updates_identical=True,borrowed_events_and_rows_unchanged=True,nested_row_containers_independent=True,helper_call_order_identical=True,resolved_event_identity_preserved=True,foreground_source_provenance_preserved=True,focused_conversions=focused,helper_coverage=coverage,checks=checks),indent=2)+'\n')
print(len(checks),'source-fragment comparisons across',len(CASES),'scenarios; 2 focused conversions; all 12 helpers exercised')
