"""Complete staggered source fades and the AoT translation overlap regression."""
import test_paths
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
from unittest.mock import patch
import simplify_ass as s
from executable_ast_audit import executable_ast

ROOT = Path(__file__).resolve().parents[1]
checks = []


def check(name, value):
    assert value, name
    checks.append(name)


HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def fixture(second=4, dx=0):
    lines = []
    for base, word in [(1, 'ABC'), (second, 'DEF')]:
        for i, char in enumerate(word):
            lines.append('Dialogue: 0,'+s.format_time(base+.1*i)+','+
                s.format_time(base+3.2+.1*i)+',Default,,0,0,0,,{\\pos('+
                str(100+20*i+(dx if base == second else 0))+',80)\\fad(300,300)}'+char+'\n')
    doc = s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(lines)))
    source = list(doc.events.values())
    rows, captions = [], []
    for cue, word in enumerate(('ABC', 'DEF')):
        originals = source[3*cue:3*cue+3]
        pieces = [s.replace_event(e, text=s.OVERRIDE_RE.sub(
            lambda m: '{'+m[0][1:-1].replace(r'\fad(300,300)', '')+'}', e.text)) for e in originals]
        end = max(e.end_s for e in originals)
        caption = s.replace_event(pieces[0], text='{\\pos('+str(120+(dx if cue else 0))+',80)}'+word,
                                  end=s.format_time(end), end_s=end)
        captions.append(caption)
        rows.append(s.TextRow(caption, [(e,char,s.get_pos(e.text)) for e,char in zip(pieces,word)]))
    return captions, rows, doc.events


captions, rows, sources = fixture()
before = deepcopy((captions, rows, sources))
derived = s.derive_staggered_fade_cores(captions, rows, sources)
check('staggered fully readable intersection computed',
      all(abs(a-b) < 1e-9 for a,b in zip(derived[0].phase_core, (1.5,3.9))))
check('incoming staggered intersection computed', derived[1].phase_core == (4.5,6.9))
check('only independent row successors receive cores', all(a is not b for a,b in zip(rows,derived)))
check('borrowed captions rows sources unmodified',
      [vars(e) for e in captions] == [vars(e) for e in before[0]] and
      [vars(r) for r in rows] == [vars(r) for r in before[1]] and
      {k:vars(e) for k,e in sources.items()} == {k:vars(e) for k,e in before[2].items()})
check('derivation idempotent', all(a is b for a,b in zip(
      derived, s.derive_staggered_fade_cores(captions, derived, sources))))
out, n = s.trim_faded_cue_overlaps(captions, derived, sources)
check('existing filter trims staggered fade overlap', n == 1 and out[0].end_s == out[1].start_s == 4.2)
check('text placement paint and event count preserved', len(out) == len(captions) and
      all(a.text == b.text and a.fields()[3:] == b.fields()[3:] for a,b in zip(captions,out)))
check('stable cores and exposure outside collision retained',
      out[0].start_s == captions[0].start_s and out[1].end_s == captions[1].end_s and
      all(e.start_s <= r.phase_core[0] < r.phase_core[1] <= e.end_s for e,r in zip(out,derived)))
check('handoff byte-idempotent', s.trim_faded_cue_overlaps(out, derived, sources)[1] == 0)

for delta, accepted in [(.005,True),(.008,False)]:
    piece,word,anchor = rows[0].pieces[1]
    rounded = replace(rows[0],pieces=[rows[0].pieces[0],
        (piece,word,(anchor[0]+delta,anchor[1])),rows[0].pieces[2]])
    result = s.derive_staggered_fade_cores(captions,[rounded,rows[1]],sources)
    check('anchor rounding tolerance '+str(delta),
          (result[0].phase_core is not None) == accepted)

for label, change in [
    ('missing source', lambda d,k: d.pop(k)),
    ('wrong literal', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text[:-1]+'Q')})),
    ('wrong font', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\fnAbsentFont}'))})),
    ('wrong anchor', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('120,80','121,80'))})),
    ('clip', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\clip(0,0,10,10)}'))})),
    ('transform', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\t(0,100,\c&HFFFFFF&)}'))})),
    ('move', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\move(120,80,121,80)}'))})),
    ('shear', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\fax0.2}'))})),
    ('drawing', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\p1}'))})),
    ('inline state change', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text+r'{\alpha&HFF&}')})),
    ('karaoke', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\k20}'))})),
    ('missing fade', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace(r'\fad(300,300)',''))})),
    ('malformed fade', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('300,300','nan,300'))})),
    ('repeated fade', lambda d,k: d.update({k:s.replace_event(d[k],text=d[k].text.replace('}',r'\fad(300,300)}'))})),
    ('scrolling effect', lambda d,k: d.update({k:s.replace_event(d[k],effect='Banner;0;0;10')})),
    ('comment source', lambda d,k: d.update({k:s.replace_event(d[k],kind='Comment')})),
    ('nonfinite time', lambda d,k: d.update({k:replace(d[k],start_s=float('nan'))})),
]:
    data = dict(sources)
    change(data,rows[0].pieces[1][0].source_index)
    result = s.derive_staggered_fade_cores(captions, rows, data)
    check('reject '+label, result[0] is rows[0] and result[0].phase_core is None)

variants = [
    ('virtual row', replace(rows[0],virtual=True)),
    ('missing piece', replace(rows[0],pieces=rows[0].pieces[:-1])),
    ('duplicate piece', replace(rows[0],pieces=rows[0].pieces+[rows[0].pieces[0]])),
    ('stale base text', replace(rows[0],base=s.replace_event(rows[0].base,text=rows[0].base.text+'Q'))),
    ('missing anchor', replace(rows[0],pieces=[rows[0].pieces[0],
        (rows[0].pieces[1][0],rows[0].pieces[1][1],None),rows[0].pieces[2]])),
]
for label, row in variants:
    result = s.derive_staggered_fade_cores(captions, [row,rows[1]], sources)
    check('reject '+label, result[0] is row and result[0].phase_core is None)
result = s.derive_staggered_fade_cores(captions, [rows[0],rows[0],rows[1]], sources)
check('competing provenance rejected', result[0] is rows[0] and result[1] is rows[0])
existing = replace(rows[0],phase_core=(1.6,3.8))
check('stronger existing proof retained',
      s.derive_staggered_fade_cores(captions,[existing,rows[1]],{})[0] is existing)
for label, second, dx in [('overlapping stable cores',3.3,0),('independent horizontal placement',4,300)]:
    caps, rs, src = fixture(second,dx)
    ds = s.derive_staggered_fade_cores(caps,rs,src)
    result, n = s.trim_faded_cue_overlaps(caps,ds,src)
    check('preserve '+label, n == 0 and [e.fields() for e in result] == [e.fields() for e in caps])

# Current and frozen engines use the same exact fonts and actual source bytes.
spec = importlib.util.spec_from_file_location('staggered_reference',ROOT/'tests/references/simplify_ass_v179.py')
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)
source = ROOT/'test-data/Attack-on-Titan-S02E01-opening-source.ass'
digest = hashlib.sha256(source.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()), patch.object(
        s,'synchronize_faded_cue_handoffs',lambda context,pairs,proven: {}), patch.object(
        s,'merge_late_static_phases',lambda events,font_metrics:(events,0)):
    results = []
    statistics = []
    for engine in (reference,s):
        path = Path(folder)/(engine.__version__+'.ass')
        metrics = engine.FontMetrics([ROOT/'fonts'])
        statistics.append(engine.simplify_ass(source,path,engine.SimplifyConfig(),font_metrics=metrics))
        results.append((path,s.load_subtitle_events(path)[1]))
    prior, current = results[0][1],results[1][1]
    old_eng = sorted([e for e in prior if e.style=='OP-E'],key=lambda e:e.start_s)
    new_eng = sorted([e for e in current if e.style=='OP-E'],key=lambda e:e.start_s)
    check('real fixture reproduces twenty English overlaps',len(old_eng)==21 and
          sum(a.end_s>b.start_s for a,b in zip(old_eng,old_eng[1:]))==20)
    check('real English lines have twenty clean handoffs',len(new_eng)==21 and
          all(a.end_s==b.start_s for a,b in zip(new_eng,new_eng[1:])))
    check('real timing only shortens affected English lines',all(
        a.start_s<=b.start_s<b.end_s<=a.end_s and a.fields()[3:]==b.fields()[3:]
        for a,b in zip(old_eng,new_eng)))
    check('other rows including romanized lyrics unchanged',
          [e.fields() for e in prior if e.style!='OP-E']==[e.fields() for e in current if e.style!='OP-E'])
    check('only overlap and concurrency statistics change',
          {k:v for k,v in statistics[0].items() if k not in {'cue_overlaps_trimmed','max_concurrent_out'}}==
          {k:v for k,v in statistics[1].items() if k not in {'cue_overlaps_trimmed','max_concurrent_out'}})
    check('intro peak concurrency drops from three to two',
          (statistics[0]['max_concurrent_out'],statistics[1]['max_concurrent_out'])==(3,2))
    check('twenty additional handoffs reported',statistics[1]['cue_overlaps_trimmed']==statistics[0]['cue_overlaps_trimmed']+20)
    again = Path(folder)/'again.ass'
    s.simplify_ass(results[1][0],again,s.SimplifyConfig(),font_metrics=s.FontMetrics([ROOT/'fonts']))
    check('real conversion byte-idempotent',again.read_bytes()==results[1][0].read_bytes())
check('real source untouched',hashlib.sha256(source.read_bytes()).hexdigest()==digest)

# A second actual subtitle has the same staggered-fade overlap defect.
# Keep this v179 timing oracle isolated from v185 final phase joins; the new
# unmodified full conversion is checked by check_late_static_phases_render.
source = ROOT/'test-data/Overlord-22m06-source.ass'
digest = hashlib.sha256(source.read_bytes()).hexdigest()
protected = {}
original = s.derive_staggered_fade_cores
def capture_cores(events, rows, sources):
    successors = original(events,rows,sources)
    for before,after in zip(rows,successors):
        if before is not after:
            protected[(after.base.style,s.OVERRIDE_RE.sub('',after.base.text))] = after.phase_core
    return successors
with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()), patch.object(
        s,'synchronize_faded_cue_handoffs',lambda context,pairs,proven: {}), patch.object(
        s,'merge_late_static_phases',lambda events,font_metrics:(events,0)):
    paths,statistics = [],[]
    for engine in (reference,s):
        path = Path(folder)/(engine.__version__+'.ass')
        paths.append(path)
        if engine is s:
            s.derive_staggered_fade_cores = capture_cores
        try:
            statistics.append(engine.simplify_ass(source,path,engine.SimplifyConfig(),
                font_metrics=engine.FontMetrics([ROOT/'fonts'])))
        finally:
            s.derive_staggered_fade_cores = original
    old,new = [s.load_subtitle_events(path)[1] for path in paths]
    changes = [(a,b) for a,b in zip(old,new) if a.fields()!=b.fields()]
    check('Overlord only three caption timings shorten',len(old)==len(new) and len(changes)==3 and
          all(a.fields()[3:]==b.fields()[3:] and a.start_s<=b.start_s<b.end_s<=a.end_s
              for a,b in changes))
    check('Overlord fully readable source cores protected',all(
          key in protected and b.start_s<=protected[key][0]<protected[key][1]<=b.end_s
          for a,b in changes for key in [(b.style,s.OVERRIDE_RE.sub('',b.text))]))
    changed = sorted([b for a,b in changes],key=lambda e:e.start_s)
    check('Overlord two clean handoffs',all(a.end_s==b.start_s for a,b in zip(changed,changed[1:])))
    check('Overlord only additional trims reported',statistics[1]['cue_overlaps_trimmed']==
          statistics[0]['cue_overlaps_trimmed']+2 and
          {k:v for k,v in statistics[0].items() if k!='cue_overlaps_trimmed'}==
          {k:v for k,v in statistics[1].items() if k!='cue_overlaps_trimmed'})
    again = Path(folder)/'again.ass'
    s.simplify_ass(paths[1],again,s.SimplifyConfig(),font_metrics=s.FontMetrics([ROOT/'fonts']))
    repeated = s.load_subtitle_events(again)[1]
    check('Overlord repaired captions byte-idempotent',
          [e.fields() for e in new if e.style=='ED-E']==
          [e.fields() for e in repeated if e.style=='ED-E'])
    # v179 already combines additional unrelated romanized fragments on a
    # second pass. Preserve that behavior, rather than requiring a new global
    # idempotence policy as part of this timing correction.
    old_again = Path(folder)/'reference-again.ass'
    reference.simplify_ass(paths[0],old_again,reference.SimplifyConfig(),
                          font_metrics=reference.FontMetrics([ROOT/'fonts']))
    old_repeated = s.load_subtitle_events(old_again)[1]
    check('Overlord unrelated second-pass behavior matches v179',
          [e.fields() for e in old_repeated if e.style!='ED-E']==
          [e.fields() for e in repeated if e.style!='ED-E'])
check('Overlord source untouched',hashlib.sha256(source.read_bytes()).hexdigest()==digest)

def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body
            if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
a = definitions(ROOT/'tests/references/simplify_ass_v179.py')
b = definitions(ROOT/'tests/references/simplify_ass_v180.py')
check('only one timing helper added',set(b)-set(a)=={'derive_staggered_fade_cores'} and not set(a)-set(b))
check('integration confined to timing evidence adoption',
      {k for k in a if ast.dump(a[k])!=ast.dump(b[k])}=={'_consolidate_text_events'})
(ROOT/'validation/staggered-fade-core-checks.json').write_text(json.dumps(dict(
    version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),
    checks_passed=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'staggered fade-core checks passed; twenty real English overlaps removed')
