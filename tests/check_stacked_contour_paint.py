"""Opaque ordered contour ownership preserves authored gradients without neutral repair."""
import test_paths
from stacked_contour_cases import *
from copy import deepcopy
import contextlib,hashlib,io,json,tempfile
checks=[]
def check(label,value):
    assert value,label;checks.append(label)
for inline in (False,True):
 for same_layer in (False,True):
  for split in (False,True):
   for width in (.75,2,5):
    name=f'{inline}/{same_layer}/{split}/{width}'
    events=parse(fixture(inline=inline,same_layer=same_layer,split=split,width=width));before=deepcopy(events)
    proof=s._stacked_source_contour_paint(context(events),events[-1],events)
    check(name+' ordered paint proved',proof is not None)
    output,count=flatten(events)
    check(name+' one complete caption',count==2 and len(output)==1)
    expected=[(f[0],(f[1][0],b[1][1],0,0,min(2,width),min(2,width))) for f,b in zip(paints(events[-1]),paints(events[1]))]
    check(name+' corresponding fill and contour gradient',paints(output[0])==expected)
    check(name+' interval and pose',(output[0].start_s,output[0].end_s,output[0].state['pos'])==(1,3,(320,100)))
    again,_=flatten(output)
    check(name+' stack repeat stable',[e.fields() for e in again]==[e.fields() for e in output])
    check(name+' source immutable',events==before)
# Rotation/skew do not make same-plane contour ownership ambiguous.
for layout in [r'\pos(320,100)\frz12',r'\pos(320,100)\fax.2\fry8\org(310,95)']:
 events=parse(fixture(layout=layout));out,count=flatten(events)
 check(layout+' transformed same-plane paint',count==2 and [p[1][1] for p in paints(out[0])]==[p[1][1] for p in paints(events[1])])
# A borderless intervening fill is occluded, but its source blur cannot be
# silently skipped simply because an earlier freeze removed that blur.
base=parse(fixture());middle=parse(HEADER+event(r'{\bord0\1c&H112233&}AB{\1c&H334455&} CD',1))[0]
middle.source_index=99
base[-1]=s.dataclass_replace(base[-1],layer='3');middle=s.dataclass_replace(middle,layer='2')
events=base[:-1]+[middle,base[-1]]
check('occluded borderless copy may be skipped',s._stacked_source_contour_paint(context(events),events[-1],events) is not None)
blurred=s.replace_event(middle,text=middle.text.replace(r'\bord0',r'\bord0\blur3'))
check('source blur on skipped copy blocks proof',s._stacked_source_contour_paint(context(events,base[:-1]+[blurred,base[-1]]),events[-1],events) is None)
for name,changes in [('translucent inner',dict(inner_extra=r'\3a&H40&')),('blurred inner',dict(inner_extra=r'\blur1')),
 ('shadowed inner',dict(inner_extra=r'\shad1')),('masked inner',dict(inner_extra=r'\clip(0,0,640,360)')),
 ('animated inner',dict(inner_extra=r'\t(0,1000,\3c&HFFFFFF&)')),
 ('translucent foreground',dict(front_extra=r'\1a&H40&')),('blurred foreground',dict(front_extra=r'\blur1')),
 ('authored foreground stroke',dict(front_extra=r'\bord1'))]:
 events=parse(fixture(**changes));before=deepcopy(events)
 check(name+' cannot claim immediate opaque contour',s._stacked_source_contour_paint(context(events),events[-1],events) is None)
 check(name+' immutable refusal',events==before)
events=parse(fixture());missing=context(events);missing.source_events.pop(events[1].source_index)
check('missing original stays uncertain',s._stacked_source_contour_paint(missing,events[-1],events) is None)
# Equivalent literals under a reused ID cannot inherit unrelated source paint.
source=deepcopy(events);source[1]=s.replace_event(source[1],text=source[1].text.replace('AB','XY'))
check('different source literal stays uncertain',s._stacked_source_contour_paint(context(events,source),events[-1],events) is None)
for tag in ('clip','iclip'):
 source=parse(fixture(front_extra='\\'+tag+'(0,0,640,360)'))
 check(tag+' removed from foreground cannot manufacture source proof',s._stacked_source_contour_paint(context(events,source),events[-1],events) is None)
# Actual source order chooses the inner plane, independent of list traversal.
ordered=parse(fixture(same_layer=True));reverse=list(reversed(ordered))
check('reversed input retains source paint order',paints(flatten(ordered)[0][0])==paints(flatten(reverse)[0][0]))
# Opacity animation belongs to the existing freezer. Matching source legs can
# still prove constant paint, including instant reveals and disappearing tails.
for name,tags in [('reveal',r'\alpha&HFF&\t(500,500,\alpha&H00&)'),
                  ('exit',r'\t(1000,1000,\alpha&HFF&)'),
                  ('fade',r'\alpha&HFF&\t(0,500,\alpha&H00&)'),
                  ('implicit times',r'\t(\alpha&HFF&)'),
                  ('acceleration',r'\t(0,1000,2,\alpha&HFF&)')]:
 current=parse(fixture());sources=parse(fixture(front_extra=tags,inner_extra=tags))
 proof=s._stacked_source_contour_paint(context(current,sources),current[-1],current)
 check(name+' shared source opacity retains authored paint',proof is not None and proof[1][0].outline=='BBBBCC')
 sources[1]=s.replace_event(sources[1],text=sources[1].text.replace(tags,r'\t(100,1200,\alpha&HFF&)'))
 check(name+' differing source opacity stays uncertain',s._stacked_source_contour_paint(context(current,sources),current[-1],current) is None)
current=parse(fixture());sources=parse(fixture(front_extra=r'\t(0,1000,\1a&HFF&)',inner_extra=r'\t(0,1000,\1a&HFF&)'))
check('independent fill and contour opacity stays uncertain',s._stacked_source_contour_paint(context(current,sources),current[-1],current) is None)
for changes in [dict(front_extra=r'\t(0,500,\alpha&H00&)'),dict(inner_extra=r'\t(\1a&H00&\3a&H00&)')]:
 sources=parse(fixture(**changes))
 check('irrelevant no-op opacity does not obstruct paint ownership '+str(changes),
       s._stacked_source_contour_paint(context(current,sources),current[-1],current) is not None)
for later in (r'\rDefault\bord0',r'\alpha&H00&',r'\1a&H00&',r'\3a&H00&'):
 sources=parse(fixture(front_extra=r'\t(0,1000,\alpha&HFF&)',inner_extra=r'\t(0,1000,\alpha&HFF&)'))
 sources[-1]=s.replace_event(sources[-1],text=sources[-1].text.replace('AB','A{'+later+'}B'))
 check('later span opacity/reset cannot borrow a header progression '+later,
       s._stacked_source_contour_paint(context(current,sources),current[-1],current) is None)
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder)
 for inline,dark in [(False,False),(True,False),(True,True)]:
  a,b,c=(folder/name for name in ('source.ass','simple.ass','again.ass'))
  a.write_text(fixture(inline=inline,dark=dark));original=a.read_bytes();report=s.FontProcessingReport()
  with contextlib.redirect_stdout(io.StringIO()):
   s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric,font_report=report)
   s.simplify_ass(b,c,s.SimplifyConfig(),font_metrics=metric)
  out=s.load_subtitle_events(b)[1];source=parse(a.read_text())
  check(str(inline)+' pipeline exact fonts',not report.missing_families)
  check(str(inline)+' pipeline complete static caption',len(out)==1 and len(paints(out[0]))==len(paints(source[-1])))
  check(str(inline)+' pipeline authored contour',[p[1][1] for p in paints(out[0])]==[p[1][1] for p in paints(source[1])])
  check(str(inline)+' pipeline repeat stable',b.read_bytes()==c.read_bytes())
  check(str(inline)+' pipeline source unchanged',a.read_bytes()==original)
(ROOT/'validation/stacked-contour-paint-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'ordered contour paint checks passed')
