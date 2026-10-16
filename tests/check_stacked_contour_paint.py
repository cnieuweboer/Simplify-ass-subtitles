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
# Representative paint belongs to a whole source-time palette, including
# outline-only steps and distinct inline fragmentations.
for inline in (False,True):
 sources=parse(stepped_fixture(inline=inline));before=deepcopy(sources)
 at=s._representative_source_palette_time(sources,1,4)
 sampled=[s._source_palette_at(e,at)[0] for e in sources]
 proof=s._stacked_source_contour_paint(context(sampled,sources),sampled[-1],sampled)
 check(str(inline)+' coherent longest source palette',proof is not None and
       (proof[1][0].fill,proof[1][0].outline)==('FFFFFF','DDD37F'))
 check(str(inline)+' full source timeline retained',sources==before and r'\t(1000,1000,' in sources[-1].text)
 if inline:
  check('inline gradient retained through source palette choice',proof[1][-1].outline=='88AA77')
# A no-op subdivision must not change the strongest palette.
sources=parse(stepped_fixture());first=s._representative_source_palette_time(sources,1,4)
sources=[s.replace_event(e,text=e.text.replace('AB',r'{\t(1600,1600,\3c&HDDD37F&)}AB')) if e.layer=='1' else e for e in sources]
at=s._representative_source_palette_time(sources,1,4)
check('no-op subdivision retains palette',s._source_palette_at(sources[-1],at)[0].state['1c']==s._source_palette_at(sources[-1],first)[0].state['1c'])
# Equal exposure uses source chronology, independent of no-op tag splitting.
text=HEADER+event(r'{\bord0\1c&H112233&\t(1000,1000,\1c&H445566&)}AB',2)
a=parse(text);b=parse(text.replace('AB',r'{\t(500,500,\1c&H112233&)}AB'))
selected=lambda es:s._source_palette_at(es[0],s._representative_source_palette_time(es,1,3))[0].state['1c']
check('equal-duration palette tie survives no-op splitting',selected(a)==selected(b)=='112233')
# Containing paint planes use source ownership, never fuzzy-equal timestamps.
for start_offset,end_offset in ((.01,0),(.04,0),(.05,0),(0,.04),(.04,.04)):
 sources=parse(HEADER+event(r'{\bord2\1c&H000000&\3c&HBBBBCC&}AB',1)+
               event(r'{\bord0\1c&HDDDDEE&}AB',2,start=1+start_offset,end=3-end_offset))
 before=deepcopy(sources);out,count=flatten(sources)
 check(f'{start_offset}/{end_offset} backing-owned single caption',count==1 and len(out)==1)
 check(f'{start_offset}/{end_offset} contour width and color retained',paints(out[0])[0][1]==('DDDDEE','BBBBCC',0,0,2.,2.))
 check(f'{start_offset}/{end_offset} exact containing interval',(out[0].start_s,out[0].end_s)==(1,3))
 check(f'{start_offset}/{end_offset} original lifetimes retained',sources==before)
 check(f'{start_offset}/{end_offset} repeat stable',[e.fields() for e in flatten(out)[0]]==[e.fields() for e in out])
for label,back,front,start,end,extra in [
 ('long independent phase',r'\bord2',r'\bord0',1.5,3,''),
 ('partial backing',r'\bord2',r'\bord0',.96,3,''),
 ('independent stroked foreground',r'\bord2',r'\bord1',1.04,3,''),
 ('translucent foreground',r'\bord2',r'\bord0\1a&H40&',1.04,3,''),
 ('blurred backing',r'\bord2\blur1',r'\bord0',1.04,3,''),
 ('different geometry',r'\bord2',r'\bord0\fs42',1.04,3,''),
 ('incomplete literal support',r'\bord2',r'\bord0',1.04,3,'CD'),
 ('intervening content',r'\bord2',r'\bord0',1.04,3,'foreign')]:
 text=HEADER+event('{'+back+r'\1c&H000000&\3c&HBBBBCC&}AB',0)+event('{'+front+r'\1c&HDDDDEE&}'+('CD' if extra=='CD' else 'AB'),2,start=start,end=end)
 if extra=='foreign':text+=event(r'{\bord0\1c&HFFFFFF&}XY',1)
 sources=parse(text);before=deepcopy(sources);out,count=flatten(sources)
 check(label+' cannot grant containing ownership',count==0 and len(out)==len(sources))
 check(label+' refusal leaves source untouched',sources==before)
# A confirmed dense row already owns completed fill. Its nearest stroke is
# resolved per literal fragment before row assembly, not pooled with glow.
for animated in (False,True):
 sources=[];pieces=[];paint_rows=[[],[],[]];foreground=[]
 for i,char in enumerate('ABCD'):
  layout=rf'\pos({250+i*45},100)'
  text=fixture(inline=False,layout=layout).replace('AB',char)
  if animated:text=text.replace(r'\3c&HBBBBCC&',rf'\3c&HBBBBCC&\t(500,500,\3c&H{["AABBCC","BBCCDD","CCDDEE","DDEEFF"][i]}&)')
  parsed=parse(text)
  for j,e in enumerate(parsed):
   e=s.dataclass_replace(e,source_index=i*10+j)
   paint_rows[j].append(e);sources.append(e)
   if j==2:foreground.append(e)
  pieces.append((paint_rows[-1][-1],char,(250+i*45,100)))
 row=s.TextRow(pieces[0][0],pieces,paint_rows=paint_rows,foreground=foreground,confirmed=True)
 before=deepcopy(row);result=s._normalize_source_row_paint([e for e,t,p in pieces],[row])
 check(str(animated)+' row uses sharp authored contours',all(e.state['3c']!='000000' and e.state['bord']==2 for e in result.events))
 check(str(animated)+' normalized row keeps original source evidence',row==before and result.rows[0].paint_rows==row.paint_rows and result.rows[0].foreground==row.foreground)
 if animated:check('row source gradient survives normalization',len({e.state['3c'] for e in result.events})==4)
# Missing terminal completed copy still consumes the existing dense-row fill
# proof; its black reveal plane must not leak into the reconstructed word.
source_rows=[[],[]];completed=[];pieces=[]
for i,char in enumerate('ABCD'):
 layout=rf'\pos({250+i*45},100)'
 for j,body in enumerate([r'{\bord2\3c&H88AACC&\1c&H000000&}'+char,r'{\bord0\1c&H000000&}'+char]):
  e=s.dataclass_replace(parse(HEADER+event(body,j+1,layout=layout))[0],source_index=100+i*10+j)
  source_rows[j].append(e)
 pieces.append((e,char,(250+i*45,100)))
 if i<3:completed.append(s.dataclass_replace(parse(HEADER+event(r'{\bord0\1c&HFFFFFF&}'+char,3,layout=layout))[0],source_index=105+i*10))
row=s.TextRow(pieces[0][0],pieces,paint_rows=source_rows,foreground=completed,confirmed=True)
result=s._normalize_source_row_paint([e for e,t,p in pieces],[row])
check('terminal reveal uses proved completed row fill',all(e.state['1c']=='FFFFFF' and e.state['3c']=='88AACC' for e in result.events))
# Terminal glyphs sometimes retain only their authored sharp plane; its stroke
# remains owned even though the completed fill comes from the proved row.
source_rows[1]=source_rows[1][:-1]
pieces[-1]=(source_rows[0][-1],'D',(385,100))
row=s.TextRow(pieces[0][0],pieces,paint_rows=source_rows,foreground=completed,confirmed=True)
result=s._normalize_source_row_paint([e for e,t,p in pieces],[row])
check('terminal sharp plane retains its own contour',all(e.state['1c']=='FFFFFF' and e.state['3c']=='88AACC' for e in result.events))

# Pipeline and repeat conversion cover paint ownership surviving all consumers.
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder)
 for inline in (False,True):
  a,b,c=(folder/name for name in ('steps.ass','simple.ass','again.ass'))
  a.write_text(stepped_fixture(inline=inline));before=a.read_bytes()
  with contextlib.redirect_stdout(io.StringIO()):
   s.simplify_ass(a,b,s.SimplifyConfig(),font_metrics=metric)
   s.simplify_ass(b,c,s.SimplifyConfig(),font_metrics=metric)
  output=s.load_subtitle_events(b)[1]
  check(str(inline)+' pipeline one coherent source appearance',len(output)==1 and paints(output[0])[0][1][:2]==('FFFFFF','DDD37F'))
  check(str(inline)+' pipeline stable representative paint',b.read_bytes()==c.read_bytes() and a.read_bytes()==before)
(ROOT/'validation/stacked-contour-paint-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,engine_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'ordered contour paint checks passed')
