#!/usr/bin/env python3
"""Regression checks for source-backed staggered fade handoffs."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import tempfile,json
import subprocess,sys,typing
from copy import deepcopy
from dataclasses import FrozenInstanceError
from _simplify_ass import cue_fades, text_freezing
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
HEADER=(ROOT/'test-data/Overlord-opening-fades-source.ass').read_text(encoding='utf-8-sig').split('Dialogue:',1)[0]
checks=[]
def ok(name,value):
    assert value,name
    checks.append(name)
def load(lines):
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp)/'source.ass';p.write_text(HEADER+''.join(lines))
        return s.load_subtitle_events(p)[1]
def lines(*, moved=False, overlap=False, paint=False, repeated=False):
    result=[]
    for cue,word in enumerate(('abcd','wxyz')):
        for i,c in enumerate(word):
            start=(1+i*.2) if cue==0 else (3.4 if overlap else 3.9)
            end=4 if cue==0 else 4.6+i*.6
            x=200+i*35+(800 if moved and cue else 0)
            tags=rf'\an5\pos({x},80)\fad(0,300)' if cue==0 else rf'\an5\pos({x},80)\fad(200,0)'
            if paint:tags+=r'\t(100,200,\1c&H334455&\blur2)'
            if repeated and cue:tags+=r'\fad(30,0)'
            result.append(f'Dialogue: 1,{s.format_time(start)},{s.format_time(end)},OP-R,,0,0,0,,{{{tags}}}{c}\n')
    return result
def fixed(source):
    return [s.replace_event(e,text=s.render_simplified_caption(e.state,s.OVERRIDE_RE.sub('',e.text))) for e in source]
def handoff(source,events=None,rows=None):
    events=events or fixed(source);rows=rows or []
    families=s.collect_faded_cue_families(events,rows,{e.source_index:e for e in source})
    out,n=s.trim_faded_cue_overlaps(events,rows,{e.source_index:e for e in source},cue_families=families)
    return out,n,families,events
source=load(lines());out,n,families,before=handoff(source)
ok('staggered starts and ends recover two cue families',len(families)==2)
ok('existing overlap policy gives one handoff',n==1)
boundary=out[0].end_s
ok('all outgoing fragments end at one boundary',all(e.end_s==boundary for e in out[:4]))
ok('all incoming fragments start at that boundary',all(e.start_s==boundary for e in out[4:]))
ok('boundary stays inside original collision',3.9<=boundary<=4)
ok('boundary preserves the outgoing protected core',boundary>=3.7)
ok('boundary preserves incoming protected core',boundary<=4.1)
ok('every fragment keeps literal text and paint',[e.text for e in out]==[e.text for e in before])
ok('layers and source order stay intact',[(e.layer,e.source_index) for e in out]==[(e.layer,e.source_index) for e in before])
ok('no fragment lifetime expands',all(b.start_s<=e.start_s<e.end_s<=b.end_s for e,b in zip(out,before)))
again,n2=s.trim_faded_cue_overlaps(out,[],{e.source_index:e for e in source},cue_families=s.collect_faded_cue_families(out,[],{e.source_index:e for e in source}))
ok('handoff is idempotent',n2==0 and [e.fields() for e in again]==[e.fields() for e in out])
for label,variant in [('overlapping stable cores',lines(overlap=True)),('independent horizontal placement',lines(moved=True))]:
    out,n,_,before=handoff(load(variant));ok(label+' retains timing',n==0 and [e.fields() for e in out]==[e.fields() for e in before])
source=load(lines(paint=True));out,n,_,before=handoff(source)
ok('color-only transforms retain usable source fades',n==1)
ok('selected transformed paint stays unchanged',[e.text for e in out]==[e.text for e in before])
source=load(lines(repeated=True));out,n,families,before=handoff(source)
ok('repeated fades protect every possible stable frame',n==1 and out[4].start_s<=3.93)
# Complete source correspondence is required, even for just one missing glyph.
source=load(lines());events=fixed(source)
for label,mutate in [
    ('missing source',lambda data:data.pop(events[1].source_index)),
    ('source text mismatch',lambda data:data.update({events[1].source_index:s.replace_event(data[events[1].source_index],text=data[events[1].source_index].text[:-1]+'q')})),
    ('source position mismatch',lambda data:data.update({events[1].source_index:s.replace_event(data[events[1].source_index],text=data[events[1].source_index].text.replace('235,80','236,80'))})),
    ('alpha animation',lambda data:data.update({events[1].source_index:s.replace_event(data[events[1].source_index],text=data[events[1].source_index].text.replace('}b',r'\t(100,200,\1a&HFF&)}b'))})),
    ('font scaling animation',lambda data:data.update({events[1].source_index:s.replace_event(data[events[1].source_index],text=data[events[1].source_index].text.replace('}b',r'\t(100,200,\fscx150)}b'))})),
    ('clipped source',lambda data:data.update({events[1].source_index:s.replace_event(data[events[1].source_index],text=data[events[1].source_index].text.replace('}b',r'\clip(0,0,10,10)}b'))})),
    ('unsupported fade',lambda data:data.update({events[1].source_index:s.replace_event(data[events[1].source_index],text=data[events[1].source_index].text.replace(r'\fad(0,300)',r'\fade(0,0,255,0,0,100,200)'))})),
    ('malformed fade',lambda data:data.update({events[1].source_index:s.replace_event(data[events[1].source_index],text=data[events[1].source_index].text.replace(r'\fad(0,300)',r'\fad(abc0,300)'))})),
]:
    data={e.source_index:e for e in source};mutate(data)
    f=s.collect_faded_cue_families(events,[],data)
    out,n=s.trim_faded_cue_overlaps(events,[],data,cue_families=f)
    ok(label+' rejects incomplete family',n==0 and [e.fields() for e in out]==[e.fields() for e in events])
# A whole reconstructed row retains each source glyph's identity and fade.
source=load(lines());source=[s.replace_event(e,start='0:00:01.00',start_s=1,end='0:00:04.00',end_s=4) if i<4 else s.replace_event(e,end='0:00:06.90',end_s=6.9) for i,e in enumerate(source)]
fragments=fixed(source);captions=[];rows=[]
for cue,word in enumerate(('abcd','wxyz')):
    pieces=fragments[cue*4:cue*4+4]
    base=s.replace_event(pieces[0],text=s.render_simplified_caption(pieces[0].state,word,pos=(250,80)))
    captions.append(base);rows.append(s.TextRow(base,[(e,s.OVERRIDE_RE.sub('',e.text),s.get_pos(e.text)) for e in pieces]))
out,n,families,before=handoff(source,captions,rows)
ok('assembled row uses complete fragment provenance',n==1 and out[0].end_s==out[1].start_s)
ok('assembled text and formatting are untouched',[e.text for e in out]==[e.text for e in before])
families=[s.CueFadeFamily(tuple(captions[:1]),(1.1,3.913),(200,305)),
          s.CueFadeFamily(tuple(captions[1:]),(3.917,6.6),(200,305))]
out,n=s.trim_faded_cue_overlaps(captions,[],{},cue_families=families)
ok('no representable safe centisecond retains original timing',n==0 and [e.fields() for e in out]==[e.fields() for e in captions])
families[1]=s.CueFadeFamily(tuple(captions[1:]),(3.922,6.6),(200,305))
out,n=s.trim_faded_cue_overlaps(captions,[],{},cue_families=families)
ok('quantized boundary stays inside the protected gap',n==1 and out[0].end_s==out[1].start_s==3.92)
out,n,_,before=handoff(source,captions,rows+[rows[0]])
ok('competing row provenance cannot authorize trimming',n==0)
# Actual Overlord source phases include oscillating rotation and repeated fad.
original=s.load_subtitle_events(ROOT/'test-data/Overlord-opening-fades-source.ass')[1]
normalized=s.normalize_animated_rotations({e.source_index:e for e in original})
current=[]
for e in normalized.values():
    body,word,drawing=s.simplify_visual_text(e.text,0,e.duration,e.defaults,e.styles,1,upright_crossings=False)
    current.append(s.replace_event(e,text=body))
f=s.collect_faded_cue_families(current,[],normalized)
out,n=s.trim_faded_cue_overlaps(current,[],normalized,cue_families=f)
ok('actual opening phases produce both lane handoffs',n==2)
for style in ('OP-R','OP-E'):
    prior=[e for e in out if e.style==style and e.start_s<128.5]
    following=[e for e in out if e.style==style and e.end_s>129 and e.start_s>128]
    ok('actual '+style+' has a clean boundary',max(e.end_s for e in prior)==min(e.start_s for e in following))
ok('actual fragment lifetimes only shrink',all(b.start_s<=e.start_s<e.end_s<=b.end_s for e,b in zip(out,current)))

# The extracted owner retains the public engine names and borrowed records.
for name in (
    'FadedCueContext','FadedCueEvidence','CueFadeFamily','shadow_lyric_fade_core',
    'text_cue_lane','derive_staggered_fade_cores','collect_faded_cue_families',
    '_faded_cue_slot','_apply_faded_cue_families','_find_faded_cue_collisions',
    '_parse_faded_source_evidence','_collect_faded_cue_evidence',
    '_prove_faded_source_core','_prove_faded_cue_core','_select_readable_core_handoff',
    '_select_faded_cue_handoff','synchronize_faded_cue_handoffs',
    '_trim_owned_cue_backing','trim_faded_cue_overlaps',
):
    value=getattr(cue_fades,name)
    ok(name+' has a direct engine alias',getattr(s,name) is value)
    typing.get_type_hints(value)
ok('shared text normalization has one owner',
   s.without_inert_spacing_tail is cue_fades.without_inert_spacing_tail is
   text_freezing.without_inert_spacing_tail)

provenance={};groups={};proofs={};slots={};shadows=set()
context=s.FadedCueContext(provenance,groups,proofs)
evidence=s.FadedCueEvidence(slots,shadows)
members=tuple(current);core=(1.,2.);extent=(200.,300.)
family=s.CueFadeFamily(members,core,extent)
ok('context borrows caller containers',context.provenance is provenance and
   context.groups is groups and context.family_proofs is proofs)
ok('boundary evidence borrows caller containers',
   evidence.phase_slots is slots and evidence.shadow_phases is shadows)
ok('family borrows its immutable payloads',family.members is members and
   family.core is core and family.xspan is extent)
for record,field in ((context,'groups'),(evidence,'phase_slots'),(family,'core')):
    try:
        setattr(record,field,None)
    except FrozenInstanceError:
        ok(type(record).__name__+' retains frozen bindings',True)
    else:
        raise AssertionError(type(record).__name__+' must remain frozen')

# Normalizing a non-painted tail must not normalize a live inline change.
seed=current[0]
for label,text,accepted in (
    ('trailing tracking reset',r'{\fsp4}word{\fsp0}',True),
    ('several trailing tracking resets',r'{\fsp4}word{\fsp1}{\fsp0}',True),
    ('live inline tracking',r'wo{\fsp4}rd',False),
    ('another trailing tag',r'word{\fsp0\bord2}',False),
    ('invalid tracking',r'word{\fspnan}',False),
    ('overflowing tracking',r'word{\fsp1e999}',False),
    ('no visible literal',r'{\fsp4}{\fsp0}',False),
    ('ordinary caption',r'word',False),
):
    event=s.replace_event(seed,text=text)
    before=deepcopy(vars(event))
    result=s.without_inert_spacing_tail(event)
    ok(label+' keeps the expected identity', (result is not event)==accepted)
    ok(label+' leaves source caches and evidence unchanged',vars(event)==before)
    if accepted:
        ok(label+' keeps the painted tracking',result.text==r'{\fsp4}word' and
           result.state['fsp']==4 and event.state['fsp']==0)

source=load(lines());events=fixed(source);source_map={e.source_index:e for e in source}
borrowed=deepcopy((events,source_map))
families=s.collect_faded_cue_families(events,[],source_map)
out,n=s.trim_faded_cue_overlaps(events,[],source_map,cue_families=families)
ok('family discovery and trimming preserve every borrowed source',
   [vars(e) for e in events]==[vars(e) for e in borrowed[0]] and
   {k:vars(e) for k,e in source_map.items()}=={k:vars(e) for k,e in borrowed[1].items()})
isolated=events[:4]
unchanged,n=s.trim_faded_cue_overlaps(isolated,[],source_map)
ok('no collision returns the original list and no handoffs',unchanged is isolated and n==0)

with tempfile.TemporaryDirectory() as folder:
    code=f'''import sys
sys.path.insert(0,{str(ROOT)!r})
from _simplify_ass import cue_fades, text_freezing
assert cue_fades.without_inert_spacing_tail is text_freezing.without_inert_spacing_tail
assert not any(n.split('.')[0] in {{'simplify_ass','PIL','fontTools','uharfbuzz'}} for n in sys.modules)
'''
    probe=subprocess.run([sys.executable,'-I','-c',code],cwd=folder,
                         capture_output=True,text=True)
    ok('independent import needs no engine or optional font backends',probe.returncode==0)
    assert not probe.stderr,probe.stderr
(ROOT/'validation/cue-family-checks.json').write_text(json.dumps({'version':s.__version__,'checks_passed':len(checks),'checks':checks},indent=2)+'\n')
print(len(checks),'cue-family checks passed')
