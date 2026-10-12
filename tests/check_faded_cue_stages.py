import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Compare fade evidence, protected cores and complete timing results with v154."""
from pathlib import Path
from copy import deepcopy
import ast,contextlib,importlib.util,json,math,random,sys,trace
import simplify_ass as current
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('faded_cue_reference',ROOT/'test-data/simplify_ass-v154-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing, Outline, Shadow
Style: Default,Arial,40,0,5,100,100,0,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return tuple(snapshot(v) for v in value)
    if isinstance(value,set):return frozenset(snapshot(v) for v in value)
    if hasattr(value,'__dict__'):return snapshot(vars(value))
    return value

def cue(c,start,end,word=None,**options):
    return {**dict(cue=c,start=start,end=end,word=word or ('ABCD' if c==0 else 'WXYZ'),x=300,y=100),**options}

def pair():return [cue(0,1,4),cue(1,3.8,7)]

def change(records,predicate,**changes):
    records=deepcopy(records)
    for i,d in enumerate(records):
        if predicate(i,d):d.update(changes)
    return records

CASES=[]
def case(label,records=None,**options):CASES.append(dict(label=label,records=records or pair(),**options))
case('ordinary complete fades',expected=1)
case('source fragments reconstruct whole rows',records=[cue(c,a,b,word=letter,x=300+30*i) for c,a,b,word in [(0,1,4,'AB'),(1,3.8,7,'WX')] for i,letter in enumerate(word)],rows='assembled',expected=1)
for label,records in [
 ('touching cues',[cue(0,1,4),cue(1,4,7)]),('separated cues',[cue(0,1,4),cue(1,4.1,7)]),
 ('same start',[cue(0,1,4),cue(1,1,7)]),('same end',[cue(0,1,7),cue(1,3.8,7)]),
 ('nested cues',[cue(0,1,7),cue(1,3.8,6)]),('triple collision',[cue(0,1,4),cue(1,3.8,7),cue(2,3.9,8)]),
 ('earlier active cue',[cue(2,.5,5),*pair()]),
 ('independent horizontal anchors',change(pair(),lambda i,d:i==1,x=800)),
 ('different vertical lanes',change(pair(),lambda i,d:i==1,y=200)),
 ('different actor',change(pair(),lambda i,d:i==1,name='other')),
 ('different margins',change(pair(),lambda i,d:i==1,margin_l='5')),
 ('comment retained cue',change(pair(),lambda i,d:i==1,kind='Comment')),
 ('unpositioned retained cue',change(pair(),lambda i,d:i==1,unpositioned=True)),
 ('translucent retained cue',change(pair(),lambda i,d:i==1,kept_tags=r'\1a&H80&')),
 ('rotated retained cue',change(pair(),lambda i,d:i==1,kept_tags=r'\frz10')),
]:case(label,records,expected=0)
case('two handoffs update both middle edges',[cue(0,1,4),cue(1,3.8,7),cue(2,6.8,10)],expected=2)
for effect in ['Banner;20;0;10','Scroll up;0;100;20',' scroll DOWN ;0;100;20']:
    case('retained '+effect,change(pair(),lambda i,d:i==0,effect=effect),expected=0)
    case('source '+effect,change(pair(),lambda i,d:i==0,source_effect=effect),expected=0)
for fad in [r'\fad(0,400)',r'\fad(200,0)',r'\fad(-1,400)',r'\fad(nan,400)',r'\fad(200,inf)',
            r'\fad(abc,400)',r'\fad(200)',r'\fad(200,400,600)',r'\fad(200,400)\fad(200,400)',r'\fade(0,0,255,0,0,100,200)','']:
    case('incomplete or malformed '+fad,change(pair(),lambda i,d:i==0,fade=fad),expected=0)
for tags in [r'\t(0,200,\1c&H334455&)',r'\move(300,100,310,100)',r'\clip(0,0,100,100)',
             r'\iclip(0,0,100,100)',r'\org(300,100)',r'\k20',r'\kf20',r'\ko20',r'\kt20',
             r'\1a&H80&',r'\frz10']:
    case('unsupported source '+tags,change(pair(),lambda i,d:i==0,source_tags=tags),expected=0)
for field,value in [('source_word','ABCE'),('source_x',301),('source_tags',r'\fs41'),('source_tags',r'\fnOther')]:
    case('source identity mismatch '+field+str(value),change(pair(),lambda i,d:i==0,**{field:value}),expected=0)
case('missing source',missing_source={0},expected=0)
case('extra unaccounted source identity',extra_source=True,expected=0)
case('duplicate retained identity',[cue(0,1,4),cue(0,1,4),cue(1,3.8,7)],expected=0)
case('outer whitespace preserved',change(pair(),lambda i,d:True,word='  ABCD  '),expected=1)
case('internal spaces preserved',change(pair(),lambda i,d:True,word='AB CD'),expected=1)
case('literal font spans',change(pair(),lambda i,d:True,word=r'A{\fnOther}BCD'),expected=1)
case('inert spacing tail',change(pair(),lambda i,d:True,word=r'ABCD{\fsp25}'),expected=1)
for word in [r'AB\NCD',r'AB\nCD','    ']:case('unusable literal '+repr(word),change(pair(),lambda i,d:True,word=word),expected=0)
for rows,expected in [('single',1),('duplicate',0),('stale',0),('virtual',1),('phase',1),('invalid_phase',0),('boundary_phase',0),('stale_phase',0)]:
    case('row provenance '+rows,rows=rows,expected=expected)
case('family proof priority over invalid row cores',rows='invalid_phase',families='manual',expected=1)
case('complete manually proved families',families='manual',missing_source={0,1},expected=1)
case('incomplete family membership',families='missing',missing_source={0,1},expected=0)
case('separately painted group prevents family absorption',[cue(0,1,4),cue(0,1,4,word='OTHER'),cue(1,3.8,7)],families='outsider',missing_source={0,1,2},expected=0)
case('overlapping protected family cores',families='overlap',expected=0)
case('disjoint family x spans',families='disjoint',expected=0)
case('touching family x spans',families='touching',expected=1)
case('no representable centisecond',families='subcentisecond',expected=0)
case('one safe centisecond',families='one_centisecond',expected=1,boundary=3.92)
case('family gap before collision',families='before_collision',expected=0)
case('family gap after collision',families='after_collision',expected=0)
case('unrelated sources are filtered',unrelated_sources=200,expected=1)
# Staggered shadow revelations may have different endpoints but one per glyph.
SHADOW=r'\1a&HFF&\3a&HFF&\4a&HFF&\shad2\t(0,{},\4a&H00&)'
shadow=[cue(c,a,b,word=letter,x=300+30*i,source_tags=SHADOW.format(200+50*i),fade=r'\fad(0,400)')
        for c,a,b,word in [(0,1,4,'AB'),(1,3.8,7,'WX')] for i,letter in enumerate(word)]
case('staggered shadow full-row cores',shadow,rows='assembled',expected=1)
case('ambiguous shadow glyph core',shadow,rows='assembled',ambiguous_shadow=True,expected=0)
case('shadow rejection does not fall through',change(shadow,lambda i,d:i==0,word=r'A\NB'),rows='assembled',expected=0)
case('ordinary differing entrance endpoints',change([cue(c,a,b,word=letter,x=300+30*i,fade=rf'\fad({200+50*i},400)') for c,a,b,word in [(0,1,4,'AB'),(1,3.8,7,'WX')] for i,letter in enumerate(word)],lambda i,d:False),rows='assembled',expected=0)
# Common handoffs may already lie outside individual fragment intervals.
case('staggered family fragments never extend',[cue(0,1,4,word='A'),cue(0,1.5,3.85,word='B',x=330),cue(1,3.8,7,word='W'),cue(1,4.1,7,word='X',x=330)],families='manual',expected=1)
case('source family collection',families='collect',expected=1)

def line(module,d,source):
    x=d.get('source_x',d['x']) if source else d['x']
    pos='' if d.get('unpositioned') and not source else rf'\pos({x},{d["y"]})'
    tags=r'\an5'+pos+(d.get('source_tags','') if source else d.get('kept_tags',''))
    if source:tags+=d.get('fade',r'\fad(200,400)' if d['cue']==0 else r'\fad(400,200)')
    word=d.get('source_word',d['word']) if source else d['word']
    effect=d.get('source_effect',d.get('effect','')) if source else d.get('effect','')
    return f"{d.get('kind','Dialogue')}: 0,{module.format_time(d['start'])},{module.format_time(d['end'])},Default,{d.get('name','')},{d.get('margin_l','0')},0,0,{effect},{{{tags}}}{word}\n"

def parse(module,lines):
    return list(module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines))).events.values())

def inputs(module,c,order):
    records=c['records'];events=parse(module,[line(module,d,False) for d in records]);sources=parse(module,[line(module,d,True) for d in records])
    groups={}
    for e,d in zip(events,records):groups.setdefault(d['cue'],[]).append(e)
    rows=[];mode=c.get('rows')
    if mode=='assembled':
        events=[]
        for group in groups.values():
            base=module.replace_event(group[0],text=module.render_simplified_caption(group[0].state,''.join(module.OVERRIDE_RE.sub('',e.text) for e in group),pos=(300,100)))
            rows.append(module.TextRow(base,[(e,module.OVERRIDE_RE.sub('',e.text),module.get_pos(e.text)) for e in group]));events.append(base)
    elif mode:
        for e in events:
            row=module.TextRow(e,[(e,module.OVERRIDE_RE.sub('',e.text),module.get_pos(e.text))])
            if 'phase' in mode:
                row.phase_core=(e.start_s+.25,e.end_s-.25)
                if mode=='invalid_phase':row.phase_core=(e.start_s-.01,e.end_s-.25)
                if mode=='boundary_phase':row.phase_core=(e.start_s,e.end_s-.25)
            if mode in ('stale','stale_phase'):row.base=module.replace_event(e,text=e.text+'!')
            if mode=='virtual':row.virtual=True
            rows.append(row)
        if mode=='duplicate':rows.append(rows[0])
    source_map={e.source_index:e for i,e in enumerate(sources) if i not in c.get('missing_source',set())}
    if c.get('extra_source'):
        extra=module.replace_event(sources[0],source_index=10001,text=sources[0].text+'!');source_map[extra.source_index]=extra
    if c.get('ambiguous_shadow'):
        extra=module.replace_event(sources[0],source_index=10002,text=sources[0].text.replace('0,200','0,300'));source_map[extra.source_index]=extra
    for i in range(c.get('unrelated_sources',0)):
        extra=module.replace_event(sources[0],source_index=20000+i,name='unrelated',text=r'{\fad(200,400)\t(0,200,\fs60)}EXTRA');source_map[extra.source_index]=extra
    families=None;family_mode=c.get('families')
    if family_mode=='collect':families=module.collect_faded_cue_families(events,rows,source_map)
    elif family_mode:
        families=[]
        for i,group in groups.items():
            start,end=min(e.start_s for e in group),max(e.end_s for e in group)
            core=(start+.2,end-.4) if i==0 else (start+.4,end-.2)
            xspan=(300,330)
            if family_mode=='overlap':core=(start+.05,end-.05)
            if family_mode in ('subcentisecond','one_centisecond'):core=(1.1,3.913) if i==0 else (3.917 if family_mode=='subcentisecond' else 3.922,6.6)
            if family_mode=='before_collision':core=(1.1,3.3) if i==0 else (3.4,6.6)
            if family_mode=='after_collision':core=(1.1,4.1) if i==0 else (4.2,6.6)
            if family_mode=='disjoint' and i:xspan=(800,830)
            if family_mode=='touching' and i:xspan=(330,360)
            members=tuple(group[:1]) if family_mode=='outsider' else tuple(group)
            if family_mode=='missing' and i==0:members=(*members,module.replace_event(group[0],source_index=99999))
            families.append(module.CueFadeFamily(members,core,xspan))
    if order=='reverse':events.reverse();rows.reverse();source_map=dict(reversed(list(source_map.items())))
    elif order=='shuffle':
        rng=random.Random(941);rng.shuffle(events);rng.shuffle(rows);items=list(source_map.items());rng.shuffle(items);source_map=dict(items)
    return events,rows,source_map,families

SPY_NAMES=('shadow_lyric_fade_core','event_override_tokens','effective_state','literal_font_spans','without_inert_spacing_tail','text_cue_lane','format_time','get_pos','opaque_text_effect_state','unrotated_text_state','replace_event','_select_faded_cue_handoff','_prove_faded_source_core')
@contextlib.contextmanager
def recording(module,calls):
    originals={name:getattr(module,name) for name in SPY_NAMES}
    def wrap(name,original):
        def call(*args,**kwargs):
            result=original(*args,**kwargs);calls.append((name,snapshot((args,kwargs)),snapshot(result)));return result
        return call
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)

tracer=trace.Trace(count=True,trace=False)
results=[]
for c in CASES:
    for order in ('original','reverse','shuffle'):
        records=[]
        for module in (previous,current):
            events,rows,sources,families=inputs(module,c,order);before=snapshot((events,rows,sources,families));calls=[]
            with recording(module,calls):
                if module is current:out,n=tracer.runfunc(module.trim_faded_cue_overlaps,events,rows,sources,cue_families=families)
                else:out,n=module.trim_faded_cue_overlaps(events,rows,sources,cue_families=families)
            assert snapshot((events,rows,sources,families))==before,(c['label'],order,'input ownership')
            assert n==c['expected'],(c['label'],order,'unexpected baseline handoffs',n)
            for a,b in zip(events,out):
                assert a.start_s<=b.start_s<b.end_s<=a.end_s,(c['label'],'fragment lifetime')
                assert a.text==b.text and a.source_index==b.source_index
            if 'boundary' in c:assert all((e.end_s if e.end_s<5 else e.start_s)==c['boundary'] for e in out)
            again,n2=module.trim_faded_cue_overlaps(out,rows,sources)
            if n:assert n2==0 and snapshot(again)==snapshot(out),(c['label'],'idempotence after trimming')
            records.append((snapshot(out),n,out is events,calls,tuple(a is b for a,b in zip(events,out)),snapshot(again),n2))
        assert records[0]==records[1],(c['label'],order,'v154 parity')
        results.append({'case':c['label'],'order':order,'handoffs':records[0][1]})
source=current.__file__;tree=ast.parse(Path(source).read_text());audit=json.loads((ROOT/'validation/faded-cue-consolidation-audit.json').read_text())
coverage={name:sum(count for (file,line),count in tracer.results().counts.items() if Path(file).resolve()==Path(source).resolve() and node.lineno<=line<=node.end_lineno) for name in {*audit['helpers'],'trim_faded_cue_overlaps'} for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name}
assert len(coverage)==10 and all(coverage.values()),coverage
(ROOT/'validation/faded-cue-stage-checks.json').write_text(json.dumps({'version':current.__version__,'reference_version':previous.__version__,'scenarios':len(CASES),'comparisons':len(results),'exact_source_validation_calls':True,'input_ownership_and_return_identity':True,'idempotence_after_trimming':True,'all_fragments_only_shrink':True,'helper_coverage':coverage,'results':results},indent=2)+'\n')
print(len(results),'fade-overlap comparisons passed across',len(CASES),'scenarios; all',len(coverage),'helpers exercised')
