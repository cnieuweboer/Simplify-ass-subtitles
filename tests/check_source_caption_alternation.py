"""Complete source phases across fragmentations and the lyric-boundary handoff."""
import test_paths
from copy import deepcopy
from pathlib import Path
import contextlib, hashlib, json, tempfile
import subprocess, sys, typing
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from _simplify_ass import lyric_boundaries, text_effect_sequences as sequences
import simplify_ass as s

ROOT = Path(__file__).resolve().parents[1]
METRIC = s.FontMetrics([ROOT/'fonts'])
assert METRIC.matching_face('Volkhov',0,False), 'Exact Volkhov regular is required'
HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
TEXT = 'AB CD EF GH'
checks = []
def check(label, condition):
    assert condition,label
    checks.append(label)
def record(word,x=320,y=100,start=1,end=5,layer=0,tags=''):
    return f'Dialogue: {layer},{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{{\\pos({x:.8f},{y}){tags}}}{word}\n'
def parse(lines):
    events = s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(lines))).events
    for e in events.values():
        e.lyric = True; e.row = 1
    return events
STATE = next(iter(parse([record(TEXT)]).values())).state

def fragments(parts, text=TEXT, anchor=320):
    model = s.authored_glyph_positions(METRIC,STATE,text,anchor,1)
    assert ''.join(text.split()) == ''.join(''.join(parts).split())
    offset = 0; result = []
    for part in parts:
        local = s.authored_glyph_positions(METRIC,STATE,part,0,1)
        assert local
        result.append((part,model[offset][1]-local[0][1]))
        offset += len(local)
    return result

def family(early=(TEXT,),late=tuple(TEXT.replace(' ','')),handoff=1000,shift=0,
           gap=0,layers=(0,1),obstacle=None,late_text=TEXT,late_tags='',early_tags=''):
    lines = []
    for phase,parts,text in [(0,early,TEXT),(1,late,late_text)]:
        for layer in layers:
            for i,(part,x) in enumerate(fragments(parts,text=text)):
                visibility = (rf'\t({handoff},{handoff},\alpha&HFF&)' if phase==0 else
                              rf'\alpha&HFF&\t({handoff+gap},{handoff+gap},\alpha&H00&)')
                paint = r'\1c&H0000FF&\3c&H000000&' if phase==0 else rf'\1c&H{40+i*8:02X}C080&\3c&H{40+i*8:02X}8040&'
                lines.append(record(part,x+(shift if phase else 0),layer=layer,
                    tags=visibility+paint+(late_tags if phase else early_tags)))
    if obstacle is not None:lines.append(obstacle)
    return parse(lines)

def removal(events,metric=METRIC):
    saved = deepcopy(events)
    collected = s.collect_source_text_rows(events,set(events),font_metrics=metric)
    rows_before = deepcopy(collected.rows)
    result = s.remove_source_fragment_effects(list(collected.events.values()),collected.rows,
        collected.words,collected.positions,set(events),font_metrics=metric)
    check('source records remain unchanged',vars_snapshot(events)==vars_snapshot(saved))
    check('row proof remains borrowed',repr(collected.rows)==repr(rows_before))
    return collected,result

def vars_snapshot(events):
    return [deepcopy(vars(e)) for e in events.values()]

cases = [
    ('complete to glyphs',(TEXT,),tuple(TEXT.replace(' ',''))),
    ('two fragments to glyphs',('AB CD ','EF GH'),tuple(TEXT.replace(' ',''))),
    ('three fragments to glyphs',('AB ','CD EF ','GH'),tuple(TEXT.replace(' ',''))),
    ('complete to two fragments',(TEXT,),('AB CD ','EF GH')),
    ('two to three fragments',('AB CD ','EF GH'),('AB ','CD EF ','GH')),
    ('glyphs to complete',tuple(TEXT.replace(' ','')),(TEXT,)),
]
for name,early,late in cases:
    events = family(early,late)
    collected,result = removal(events)
    expected = len(early)*2
    check(name+' removes only earlier complete phase',result.removed_effects==expected and len(result.events)==2*len(late))
    check(name+' selects the longer phase',len(collected.rows)==1 and len(collected.rows[0].pieces)==len(late) and
          collected.rows[0].base.evidence.opaque_spans==((2.,5.),))
    check(name+' preserves selected paint exactly',all(e.fields() in [x.fields() for x in events.values()] for e in result.events))
    reversed_events = dict(reversed(list(events.items())))
    _,reversed_result = removal(reversed_events)
    check(name+' independent of enumeration',sorted(e.fields() for e in result.events)==sorted(e.fields() for e in reversed_result.events))

for name,kwargs in [
    ('unmeasured font',dict(metric=None)),
    ('different geometry',dict(shift=3)),
    ('visibility gap',dict(gap=20)),
    ('visibility overlap',dict(gap=-20)),
    ('only one paint plane',dict(layers=(0,))),
    ('incomplete literal',dict(late=tuple('ABCDEFG'),late_text='AB CD EF G')),
    ('clipped fragment',dict(late_tags=r'\clip(0,0,640,360)')),
    ('moving fragment',dict(late_tags=r'\move(300,100,320,100)')),
    ('different paragraph geometry',dict(late_tags=r'\q1')),
    ('intervening overlapping ink',dict(obstacle=record('FOREIGN',layer=1))),
    ('intervening unmeasurable ink',dict(obstacle=record('FOREIGN',layer=1,tags=r'\fnUnknownFamily'))),
]:
    metric=kwargs.pop('metric',METRIC)
    _,result=removal(family(**kwargs),metric)
    check(name+' retains uncertain phase',result.removed_effects==0)

_,result=removal(family(obstacle=record('FOREIGN',layer=1,y=280)))
check('distant independent caption remains eligible',result.removed_effects==2 and
      any(s.OVERRIDE_RE.sub('',e.text)=='FOREIGN' for e in result.events))
_,result=removal(family(handoff=3000))
check('longer whole-line paint wins over many glyphs',result.removed_effects==16 and len(result.events)==2 and
      all(s.OVERRIDE_RE.sub('',e.text)==TEXT for e in result.events))
_,result=removal(family(handoff=2000))
check('equal exposure prefers earlier phase without fragment votes',result.removed_effects==16 and len(result.events)==2)

# A hidden fill does not hide a separately authored stroke or shadow.
for label,change in [('outline independent',lambda text:text.replace('alpha&H','1a&H')),
                     ('shadow independent',lambda text:text.replace('alpha&H','1a&H').replace('\\pos','\\shad2\\pos'))]:
    events=family()
    events={i:s.replace_event(e,text=change(e.text)) for i,e in events.items()}
    _,result=removal(events)
    check(label+' cannot borrow fill visibility',result.removed_effects==0)

# Splitting a single lyric's sampled effect into more frames must not invent
# a cue change, and a subsequent real lyric boundary must remain protected.
for split in (1,2,5):
    lines=[]
    for cue,word in enumerate(('AB','CB')):
        for frame in range(split):
            start=1+cue*2+2*frame/split;end=1+cue*2+2*(frame+1)/split
            lines.extend(record(c,200+30*i,start=start,end=end,
                tags=rf'\\1c&H{40+frame:02X}C080&') for i,c in enumerate(word))
    events=list(parse(lines).values());words={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events}
    index=s._index_lyric_boundaries(events,words)
    out,_=s.coalesce_lyric_phases(events,words,lyric_boundaries=index)
    out,_=s.merge_frame_animation(out,words,merge_near_static=True,lyric_boundaries=index)
    out,_=s.flatten_text_effect_sequences(out,words,events[0].styles,set(words),lyric_boundaries=index)
    bs=[(e.start_s,e.end_s) for e in out if words[e.source_index]=='B']
    check(f'{split} source frames retain real cue boundary',bs==[(1,3),(3,5)])

# A changing subset is not a complete lyric handoff while other letters hold.
events=list(parse([record('A',200,start=1,end=3),record('C',200,start=3,end=5),
                   record('B',230,start=1,end=3),record('B',230,start=3,end=5),
                   record('D',260,start=1,end=5)]).values())
words={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events}
index=s._index_lyric_boundaries(events,words);saved_index=deepcopy(index)
check('staggered subset is not a complete caption boundary',not index.caption_handoffs)
out,_=s.coalesce_lyric_phases(events,words,lyric_boundaries=index)
out,_=s.merge_frame_animation(out,words,merge_near_static=True,lyric_boundaries=index)
out,_=s.flatten_text_effect_sequences(out,words,events[0].styles,set(words),lyric_boundaries=index)
check('valid held letter phases remain mergeable',[(e.start_s,e.end_s) for e in out if words[e.source_index]=='B']==[(1,5)])
check('boundary proof borrowed without edits',index==saved_index)

# Paint layers are planes of one caption lane, not separate lyric timelines.
# A held letter on another layer also disproves a complete handoff.
layered=[s.replace_event(e,layer='3') if words[e.source_index]=='D' else e for e in events]
layered_index=s._index_lyric_boundaries(layered,words)
check('ongoing text across paint layers prevents a false handoff',not layered_index.caption_handoffs)
# Changing only the segmentation of the same complete caption is not a cue
# change: another held plane supplies unchanged whole-caption context.
changed=parse([record('AB',215,start=1,end=3),record('A',200,start=3,end=5),
               record('B',230,start=3,end=5),record('AB',215,start=1,end=5,layer=2)])
changed_words={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in changed.values()}
check('held caption plane protects segmentation handoff',
      not s._index_lyric_boundaries(list(changed.values()),changed_words).caption_handoffs)

# Complete caption jitter and word-to-letter changes preserve the same
# literal caption, even when every source record changes at the boundary.
for label,records in [
    ('complete-row jitter',[record(c,200+30*i+shift,start=a,end=b)
        for a,b,shift in [(1,3,0),(3,5,.5)] for i,c in enumerate('ABCD')]),
    ('word-to-glyph handoff',[record('AB',215,start=1,end=3),record('CD',275,start=1,end=3)]+
        [record(c,200+30*i,start=3,end=5) for i,c in enumerate('ABCD')]),
]:
    same=list(parse(records).values());same_words={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in same}
    check(label+' is not a new lyric',not s._index_lyric_boundaries(same,same_words).caption_handoffs)

# Full pipeline: a last letter shared with a different following caption must
# not grow the reconstructed row's lifetime. Both are exact-font positioned rows.
next_text = 'IJ KL MN OH'
old_positions = s.authored_glyph_positions(METRIC,STATE,TEXT,320,1)
next_positions = s.authored_glyph_positions(METRIC,STATE,next_text,320,1)
next_anchor = 320+old_positions[-1][1]-next_positions[-1][1]
events=family()
lines=[record(part,x,start=5,end=9,layer=layer,tags=r'\t(0,0,\alpha&H00&)\1c&H60C080&\3c&H608040&')
       for layer in (0,1) for part,x in fragments(tuple(next_text.replace(' ','')),next_text,next_anchor)]
source=HEADER+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events.values())+''.join(lines)
for source_variant in (source, ''.join(line for line in source.splitlines(keepends=True) if not line.startswith('Dialogue: 1,0:00:05.00,'))):
    with tempfile.TemporaryDirectory() as directory:
        source_path=Path(directory)/'source.ass';output=Path(directory)/'output.ass';repeat=Path(directory)/'repeat.ass'
        source_path.write_text(source_variant)
        before=source_path.read_bytes();report=s.FontProcessingReport()
        with contextlib.redirect_stdout(None):
            stats=s.simplify_ass(source_path,output,s.SimplifyConfig(),font_metrics=METRIC,font_report=report)
            s.simplify_ass(output,repeat,s.SimplifyConfig(),font_metrics=METRIC,font_report=report)
        check('pipeline uses exact fonts',not report.missing_families)
        check('pipeline preserves original',source_path.read_bytes()==before)
        out=[e for e in s.load_subtitle_events(output)[1] if e.kind=='Dialogue']
        check('pipeline reconstructs both complete paint phases and next caption',len(out)==3 and [s.OVERRIDE_RE.sub('',e.text) for e in out]==[TEXT,TEXT,next_text])
        check('pipeline retains lyric handoff',[(e.start_s,e.end_s) for e in out]==[(1,2),(2,5),(5,9)])
        check('pipeline retains gradient',len({span[0].formatting for span in s.static_object_key(out[1],out[1].styles)[-1]})>1)
        check('pipeline repeat stable',output.read_bytes()==repeat.read_bytes())

# The same surrounding-row evidence is used in glyph coalescing and sequence
# merging, including standalone callers and both exact/scale recursion routes.
for same_caption in [False,True]:
    for overlap in [0,.08]:
        second='AB' if same_caption else 'CB'
        events=list(parse([record(c,200+30*i,start=a,end=b,tags=r'\1c&H40C080&')
                           for word,a,b in [('AB',1,3), (second,3-overlap,5)] for i,c in enumerate(word)]).values())
        words={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events}
        before=deepcopy(events);index=s._index_lyric_boundaries(events,words)
        joined,_=s.coalesce_lyric_phases(events,words,lyric_boundaries=index)
        for mode in [False,True]:
            contexts=[]
            prepare=sequences._prepare_text_effect_sequence_pass
            def observe(inputs,context):
                contexts.append(context)
                return prepare(inputs,context)
            with patch.object(sequences,'_prepare_text_effect_sequence_pass',side_effect=observe), \
                    patch.object(sequences,'_index_lyric_boundaries',side_effect=AssertionError('supplied proof must survive')):
                out,count=s.flatten_text_effect_sequences(joined,words,events[0].styles,set(words),mode,
                    source_events={e.source_index:e for e in events},lyric_boundaries=index)
            check('all recursive routes borrow the original boundary proof',
                  len(contexts)==(3 if mode else 1) and
                  all(context.lyric_boundaries is index for context in contexts))
            repeated=[e for e in out if words[e.source_index]=='B']
            check(f'boundary same={same_caption} overlap={overlap} mode={mode}',
                  len(repeated)==(1 if same_caption else 2) and
                  (same_caption or [(e.start_s,e.end_s) for e in repeated]==[(1,3),(3-overlap,5)]))
        check('boundary passes preserve inputs',vars_snapshot({i:e for i,e in enumerate(events)})==vars_snapshot({i:e for i,e in enumerate(before)}))

# Module boundaries retain canonical engine aliases and shallow record contracts.
for owner,names in (
    (lyric_boundaries,('LyricBoundaryIndex','_index_lyric_boundaries','_crosses_lyric_boundary')),
    (sequences,('TextEffectSequenceContext','TextEffectSequenceGeometry','TextEffectSequenceProfile',
        'match_scale_trail','upright_text_holds','_prepare_text_effect_sequence_pass',
        '_group_text_effect_sequences','_index_text_effect_sequence_geometry',
        '_text_effect_sequence_neighbor','_cluster_text_effect_sequences','_prove_text_effect_sequence',
        '_select_text_effect_sequence_geometry','_select_text_effect_sequence_paint',
        '_construct_text_effect_sequence_caption','_flatten_text_effect_sequence_bucket',
        '_finish_text_effect_sequences','flatten_text_effect_sequences')),
):
    for name in names:
        value=getattr(owner,name)
        check(name+' retains a direct engine alias',getattr(s,name) is value)
        typing.get_type_hints(value)
check('sequence consumer uses the shared boundary owner',
      sequences.LyricBoundaryIndex is s.LyricBoundaryIndex and
      sequences._index_lyric_boundaries is s._index_lyric_boundaries and
      sequences._crosses_lyric_boundary is s._crosses_lyric_boundary)

starts={};ends={};touching=frozenset();handoffs=frozenset()
proof=s.LyricBoundaryIndex(starts,ends,touching,handoffs)
check('boundary record keeps shallow payload sharing',proof.starts is starts and proof.ends is ends and
      proof.touching is touching and proof.caption_handoffs is handoffs)
sources={e.source_index:e for e in events};animated=set(words);styles=events[0].styles
report=s.FontProcessingReport(missing_families={'prior finding'})
context=s.TextEffectSequenceContext(words,styles,animated,True,sources,METRIC,report,proof)
check('sequence context borrows all caller-owned inputs',context.visible_map is words and
      context.styles is styles and context.animated_sources is animated and context.source_events is sources and
      context.font_metrics is METRIC and context.font_report is report and context.lyric_boundaries is proof)
positions={};heights={};layouts={}
geometry=s.TextEffectSequenceGeometry(positions,heights,layouts)
check('geometry record keeps the producer-owned dictionaries',geometry.positions is positions and
      geometry.heights is heights and geometry.layouts is layouts)
visible=events[:1];profile=s.TextEffectSequenceProfile(events,visible,False,False,1,5)
check('sequence profile borrows its member lists',profile.members is events and profile.visible_candidates is visible)
for record_value,field in ((proof,'starts'),(context,'visible_map'),(geometry,'positions'),(profile,'members')):
    try:
        setattr(record_value,field,None)
    except FrozenInstanceError:
        check(type(record_value).__name__+' preserves frozen bindings',True)
    else:
        raise AssertionError(type(record_value).__name__+' must remain frozen')

with tempfile.TemporaryDirectory() as directory:
    code=f'''import sys
sys.path.insert(0,{str(ROOT)!r})
from _simplify_ass import lyric_boundaries, text_effect_sequences
assert text_effect_sequences.LyricBoundaryIndex is lyric_boundaries.LyricBoundaryIndex
assert not any(n.split('.')[0] in {{'simplify_ass','PIL','fontTools','uharfbuzz'}} for n in sys.modules)
'''
    result=subprocess.run([sys.executable,'-I','-c',code],cwd=directory,capture_output=True,text=True)
    check('independent importing needs no engine or optional font backends',result.returncode==0)
    assert not result.stderr,result.stderr

(ROOT/'validation/source-caption-alternation-checks.json').write_text(json.dumps(dict(
    version=s.__version__,engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),
    checks=len(checks),cases=checks),indent=2)+'\n')
print(len(checks),'source caption alternation and lyric-boundary checks passed')
