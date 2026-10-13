"""Strict final copy policy and the actual lyric reconstruction pipeline."""
import test_paths
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import ast, contextlib, hashlib, io, json, runpy, subprocess
from PIL import Image, ImageChops
import simplify_ass as s
from lyric_layer_fixtures import HEADER, TEXT, event
from executable_ast_audit import executable_ast

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'validation/late-complete-copies';DEST.mkdir(exist_ok=True)
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def parsed(rows):
    return list(s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(rows))).events.values())
def pair(tags='', *, literal=TEXT, x=101, first_tags='', intervals=((1,4),(1,4)), layer=0):
    return parsed([event(TEXT,100,0,intervals[0],first_tags),event(literal,x,layer,intervals[1],tags)])

a=pair();a[0].lyric=a[1].lyric=True;before=deepcopy(a)
out,n=s.remove_late_complete_copies(a)
check('complete lyric copies reduced without clearing flags',n==1 and out==[a[0]] and out[0] is a[0] and out[0].lyric)
check('borrowed records styles and caches unchanged',[vars(e) for e in a]==[vars(e) for e in before])
check('helper idempotent',s.remove_late_complete_copies(out)==(out,0))
for name,rows,expected in [
    ('same inline gradient', [event(r'The {\1c&H00FFFF&}sky shines',x,0,(1,4)) for x in (100,101)],1),
    ('explicit automatic wrapping', [event(TEXT,x,0,(1,4),r'\q1') for x in (100,101)],0),
    ('identical wrapped anchor', [event(TEXT,100,0,(1,4),r'\q1')]*2,1),
    ('small span bounds large final span', [event(r'The {\fs400}sky shines',x,0,(1,4)) for x in (100,104)],0)]:
    es=parsed(rows);out,count=s.remove_late_complete_copies(es)
    check(name,count==expected)
    check(name+': idempotent',s.remove_late_complete_copies(out)==(out,0))
for name,options in [
    ('fill',{'tags':r'\1c&HFEFFFF&'}),('outline',{'tags':r'\3c&H413020&'}),
    ('shadow color',{'tags':r'\4c&H123456&'}),('partial alpha',{'first_tags':r'\alpha&H80&','tags':r'\alpha&H80&'}),
    ('partial inline alpha',{'literal':r'The {\1a&H80&}sky shines'}),
    ('earlier inline paint',{'literal':r'{\1c&H123456&}The {\1c&HFFFFFF&}sky shines'}),
    ('inline gradient',{'literal':r'The {\1c&H00FFFF&}sky shines'}),
    ('bold',{'tags':r'\b1'}),('italic',{'tags':r'\i1'}),('underline',{'tags':r'\u1'}),
    ('size',{'tags':r'\fs40.01'}),('scale',{'tags':r'\fscx100.01'}),('spacing',{'tags':r'\fsp.01'}),
    ('rotation',{'tags':r'\frz.01'}),('origin',{'tags':r'\org(100,100)'}),('border',{'tags':r'\bord2.01'}),
    ('blur',{'tags':r'\blur.1'}),('shadow',{'tags':r'\shad.1'}),('font',{'tags':r'\fnOther'}),
    ('wrap',{'tags':r'\q1'}),('clip',{'tags':r'\clip(0,0,200,200)'}),
    ('identical clip',{'tags':r'\clip(0,0,200,200)','first_tags':r'\clip(0,0,200,200)'}),
    ('animated',{'tags':r'\t(\frz10)'}),('fade',{'tags':r'\fad(100,100)'}),
    ('different layer',{'layer':1}),('independent anchor',{'x':104}),
    ('case',{'literal':TEXT.upper()}),('spacing text',{'literal':'Theskyshines'}),
    ('incomplete text',{'literal':'The sky'}),('one centisecond not covered',{'intervals':((1,4),(.99,3.99))}),
    ('overlap only',{'intervals':((1,4),(3,6))}),('disjoint cues',{'intervals':((1,2),(3,4))})]:
    es=pair(**options);result,count=s.remove_late_complete_copies(es)
    check(name+' retained',count==0 and result==es)
for name,edit in [('margin',lambda e:setattr(e,'margin_l','1')),('actor',lambda e:setattr(e,'name','other')),
                 ('measurement',lambda e:setattr(e,'measurement',s.DocumentMeasurementContext((1280,720),2)))]:
    es=pair();edit(es[1]);check(name+' retained',s.remove_late_complete_copies(es)==(es,0))
for name,rows in [
    ('single glyph',[event('o',100,0,(1,4)),event('o',101,0,(1,4))]),
    ('drawing',[event('m 0 0 l 10 0 10 10',100,0,(1,4),r'\p1'),event('m 0 0 l 10 0 10 10',101,0,(1,4),r'\p1')]),
    ('unpositioned',[event(TEXT,100,0,(1,4)).replace(r'\pos(100.000000,100)','')]*2),
    ('interleaved text',[event(TEXT,100,0,(1,4)),event('Foreground',100,0,(1,4)),event(TEXT,101,0,(1,4))]),
    ('interleaved drawing',[event(TEXT,100,0,(1,4)),event('m 0 0 l 50 0 50 50',100,0,(2,3),r'\p1'),event(TEXT,101,0,(1,4))])]:
    es=parsed(rows);check(name+' retained',s.remove_late_complete_copies(es)==(es,0))
es=parsed([event(TEXT,100,0,(1,4)),event('Inactive',100,0,(4,5)),event(TEXT,101,0,(1,4))])
check('inactive peer does not block',s.remove_late_complete_copies(es)[1]==1)
es=parsed([event(TEXT,x,0,(1,4)) for x in (100,102,104)])
out,n=s.remove_late_complete_copies(es)
check('no cumulative offset chain',n==1 and out==[es[0],es[2]])
es=pair(intervals=((1,4),(1.05,3.95)))
check('nested coverage retains original hold timing',s.remove_late_complete_copies(es)==([es[0]],1))

# The existing 22 exact-font fixtures exercise assign_layout and every lyric proof.
# Compare to the real pipeline with only this new final pass disabled.
with contextlib.redirect_stdout(io.StringIO()):
    experiment=runpy.run_path(str(ROOT/'validation/investigate_lyric_layer_niche.py'))
metrics=experiment['metrics'];reductions=0
def render(path, at):
    run=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=640x360:r=1',
        '-vf',f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}',
        '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
    return Image.frombytes('RGB',(640,360),run.stdout)
for case in experiment['cases']:
    baseline=DEST/(case['name']+'.without-late.ass');output=DEST/(case['name']+'.ass');again=DEST/(case['name']+'.again.ass')
    original_hash=hashlib.sha256(case['source'].read_bytes()).hexdigest()
    with contextlib.redirect_stdout(io.StringIO()):
        with patch.object(s,'remove_late_complete_copies',lambda events:(events,0)):
            old_stats=s.simplify_ass(case['source'],baseline,s.SimplifyConfig(),font_metrics=metrics)
        stats=s.simplify_ass(case['source'],output,s.SimplifyConfig(),font_metrics=metrics)
        s.simplify_ass(output,again,s.SimplifyConfig(),font_metrics=metrics)
    old=s.load_subtitle_events(baseline)[1];new=s.load_subtitle_events(output)[1]
    expected,count=s.remove_late_complete_copies(old);reductions+=bool(count)
    check(case['name']+': only final redundant copies removed',[e.fields() for e in new]==[e.fields() for e in expected])
    if count:
        oracle=DEST/(case['name']+'.old-second.ass')
        with contextlib.redirect_stdout(io.StringIO()), patch.object(s,'remove_late_complete_copies',lambda events:(events,0)):
            s.simplify_ass(baseline,oracle,s.SimplifyConfig(),font_metrics=metrics)
        cover=next(e for e in new if s.OVERRIDE_RE.sub('',e.text)==TEXT)
        for at in (cover.start_s+.01,(cover.start_s+cover.end_s)/2,cover.end_s-.01):
            check(case['name']+f': rendered hold matches old second pass at {at:.2f}',
                  ImageChops.difference(render(output,at),render(oracle,at)).getbbox() is None)
    check(case['name']+': counted in existing duplicate filter',stats['deduped']==old_stats['deduped']+count)
    check(case['name']+': count reflects final output',stats['output']==sum(e.kind=='Dialogue' for e in new))
    check(case['name']+': second conversion cannot remove another complete copy',len(new)==len(s.load_subtitle_events(again)[1]))
    check(case['name']+': source preserved',hashlib.sha256(case['source'].read_bytes()).hexdigest()==original_hash)
check('all 18 known leftovers cleaned in first conversion',reductions==18)
def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
old,new=definitions(ROOT/'tests/references/simplify_ass_v183.py'),definitions(ROOT/'simplify_ass.py')
check('only new late-copy helper added',new.keys()-old.keys()=={'remove_late_complete_copies'} and not old.keys()-new.keys())
check('only final pipeline modified',{name for name in old if ast.dump(old[name])!=ast.dump(new[name])}=={'simplify_ass'})
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks),fixtures_reduced=reductions),indent=2)+'\n')
print(len(checks),'late complete-copy checks passed;',reductions,'fixtures settle in one conversion')
