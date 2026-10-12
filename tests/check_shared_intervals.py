import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import tempfile,json,sys,collections
import simplify_ass as s
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(s)
ROOT=Path(__file__).resolve().parents[1]
metric=s.FontMetrics([ROOT/'fonts'])
fixture=ROOT/'test-data/Overlord-22m06-source.ass'
header=fixture.read_text(encoding='utf-8-sig').split('Dialogue:',1)[0]
checks=[]
def ok(name,condition):
 assert condition,name
 checks.append(name)
def event(c,x,start,end,extra='',layer='0'):
 return f'Dialogue: {layer},{s.format_time(start)},{s.format_time(end)},ED-R,,0,0,0,,'+r'{\an5\pos('+f'{x},78'+')'+extra+'}'+c+'\n'
def load(parts):
 with tempfile.TemporaryDirectory() as temp:
  p=Path(temp)/'input.ass';p.write_text(header+''.join(parts));events=s.load_subtitle_events(p)[1]
 visible={e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in events}
 return events,visible
letters=[('i',488),('t',505),('s',525),('u',552)]
def merge(parts,metric_override=metric,animated=True):
 before,visible=load(parts);result=s.merge_shared_interval_rows(before,visible,metric_override,{e.source_index for e in before} if animated else set(), font_report=font_test_report(metric_override))
 after,rows,tails=result.events,result.rows_joined,result.tails_retained
 visible.update(result.visibility_updates)
 return before,after,rows,tails
# Compare multiplicities at every original/new boundary and midpoint. This
# catches lost tails, extended letters, duplicate painting and handoff holes.
def glyphs(events,at):
 counter=collections.Counter()
 for e in events:
  if e.kind=='Dialogue' and e.start_s<=at<e.end_s:counter.update(c for c in s.simplify_text(e.text,visible_only=True)[1] if not c.isspace())
 return counter
def coverage(before,after,label):
 times=sorted({t for e in before+after for t in (e.start_s,e.end_s)})
 for at in times+[(a+b)/2 for a,b in zip(times,times[1:])]:ok(label+' coverage '+str(at),glyphs(before,at)==glyphs(after,at))
 ok(label+' unique IDs',len({e.source_index for e in after})==len(after))
for mode in ('shared_start','shared_end'):
 parts=[event(c,x,1 if mode=='shared_start' else 1+.2*i,2+.2*i if mode=='shared_start' else 3) for i,(c,x) in enumerate(letters)]
 a,b,rows,tails=merge(parts)
 ok(mode+' reconstructs once',rows==1 and tails==3)
 coverage(a,b,mode)
 ok(mode+' lower core concurrency',sum(e.start_s<=1.8<e.end_s for e in b)==1)
 expected = [c for c,x in letters][1:] if mode=='shared_start' else [c for c,x in letters][:-1]
 ok(mode+' source order retained for tails',[s.simplify_text(e.text,visible_only=True)[1] for e in b if len(s.simplify_text(e.text,visible_only=True)[1])==1]==expected)
# Different colours must remain on the corresponding letters; other paint
# (outline axes, alpha, shadow) must survive without normalizing to defaults.
colors=['0000FF','00FF00','FF0000','ABCDEF']
extra=r'\xbord1.25\ybord2.5\3a&H40&\xshad3\yshad4'
parts=[event(c,x,1,2+.2*i,extra+r'\1c&H'+colors[i]+'&') for i,(c,x) in enumerate(letters)]
a,b,rows,tails=merge(parts);ok('paint row reconstructs',rows==1);coverage(a,b,'paint')
row=next(e for e in b if len(s.simplify_text(e.text,visible_only=True)[1])>1)
state=row.defaults.copy();painted=[];continuation=s.OverrideContinuation()
for part in s.re.split(r'(\{[^}]*\})',row.text):
 if part.startswith('{'):
  for tag,value in s.tokenize_override(part[1:-1]):continuation=s.apply_override(state,tag,value,row.styles,row.defaults,continuation)
 else:
  for c in part:
   if not c.isspace():painted.append((c,state['1c'],state.get('xbord'),state.get('ybord'),state.get('3a'),state.get('xshad'),state.get('yshad')))
ok('span paint stays attached to each letter',painted==[(c,col,1.25,2.5,64,3,4) for (c,x),col in zip(letters,colors)])
# Conservative fallback cases.
base=[event(c,x,1,2+.2*i) for i,(c,x) in enumerate(letters)]
for name,parts,font,animated in [
 ('missing exact fonts',base,None,True),
 ('unproven animation',base,metric,False),
 ('translucent fill',[event(c,x,1,2+.2*i,r'\1a&H80&') for i,(c,x) in enumerate(letters)],metric,True),
 ('duplicate anchors',[event(c,488 if i==1 else x,1,2+.2*i) for i,(c,x) in enumerate(letters)],metric,True),
 ('short core',[event(c,x,1,1.03+.2*i) for i,(c,x) in enumerate(letters)],metric,True),
 ('different sizes',[event(c,x,1,2+.2*i,r'\fs65' if i==1 else '') for i,(c,x) in enumerate(letters)],metric,True),
 ('clipped text',[event(c,x,1,2+.2*i,r'\clip(400,40,600,100)') for i,(c,x) in enumerate(letters)],metric,True),
 ('inline formatting',[event(c,x,1,2+.2*i)+'' for i,(c,x) in enumerate(letters[:3])]+[event('u{\\1c&HFF0000&}x',552,1,2.6)],metric,True),
]:
 a,b,rows,tails=merge(parts,font,animated);ok(name+' leaves input intact',rows==0 and [e.fields() for e in a]==[e.fields() for e in b])
# An interleaved same-layer object blocks a row whose compositing order would
# change. Equivalent layer spellings refer to the same rendering layer.
parts=base[:1]+[event('X',515,1,3,layer='00').replace(',ED-R,,',',ED-R,other,')]+base[1:]
a,b,rows,tails=merge(parts);ok('interleaved object rejected',rows==0);coverage(a,b,'interleaved')
# Paint-only equal-time rows are useful too; no tails or visibility expansion.
parts=[event(c,x,1,2,extra+r'\1c&H'+colors[i]+'&') for i,(c,x) in enumerate(letters)]
a,b,rows,tails=merge(parts);ok('equal-time gradient joins',rows==1 and tails==0);coverage(a,b,'equal-time')

# Staggered phases need neither an identical start nor an identical end.
parts=[event(c,x,1+.2*i,3+.2*i) for i,(c,x) in enumerate(letters)]
a,b,rows,tails=merge(parts);ok('staggered sweep joins',rows==1 and tails==6);coverage(a,b,'staggered')
# Paint changes can include outline width and opacity; layout stays fixed.
parts=[event(c,x,1,2+.2*i,r'\bord'+str(i+1)+r'\3a&H'+f'{i*32:02X}'+'&') for i,(c,x) in enumerate(letters)]
a,b,rows,tails=merge(parts);ok('mixed borders join',rows==1);coverage(a,b,'borders')
# Layers may change only when no overlapping object lies between them.
parts=[event(c,x,1,2+.2*i,layer=str(i%2)) for i,(c,x) in enumerate(letters)]
a,b,rows,tails=merge(parts);ok('isolated mixed layers join',rows==1);coverage(a,b,'layers')
parts=parts[:1]+[event('X',515,1,3,layer='0').replace(',ED-R,,',',ED-R,other,')]+parts[1:]
a,b,rows,tails=merge(parts);ok('mixed layer occluder blocks join',rows==0);coverage(a,b,'occluder')
# A different vertical band must not invalidate an independent held row.
parts=base+[event('X',490,1.1,2.2).replace('490,78','490,68')]
a,b,rows,tails=merge(parts);ok('vertical bands stay separate',rows==1);coverage(a,b,'bands')
parts=[event(c,x,1,2+.2*i,r'\rBox') for i,(c,x) in enumerate(letters)]
# Style 3 boxes cannot become one continuous box merely by joining text.
a,visible=load(base)
a=[s.dataclass_replace(e,state={**e.state,'borderstyle':3}) for e in a]
result=s.merge_shared_interval_rows(a,visible,metric,{e.source_index for e in a}, font_report=font_test_report(metric))
b,rows,tails=result.events,result.rows_joined,result.tails_retained
visible.update(result.visibility_updates)
ok('opaque box style left intact',rows==0)


# Synthetic IDs from preceding passes must not stand in for file order.
parts=base[:1]+[event('X',515,1,3).replace(',ED-R,,',',ED-R,other,')]+base[1:]
a,visible=load(parts)
a=[s.dataclass_replace(e,source_index=(1000 if i==1 else i)) for i,e in enumerate(a)]
visible={e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in a}
result=s.merge_shared_interval_rows(a,visible,metric,{e.source_index for e in a}, font_report=font_test_report(metric))
b,rows,tails=result.events,result.rows_joined,result.tails_retained
visible.update(result.visibility_updates)
ok('file order wins over synthetic IDs',rows==0)


# An outside anchor can still paint into the candidate row. Exact font boxes
# must block it instead of relying only on proximity of anchor positions.
parts=base[:1]+[event('X'*20,760,1,3).replace(',ED-R,,',',ED-R,other,')]+base[1:]
a,b,rows,tails=merge(parts);ok('long interleaved text blocks join',rows==0);coverage(a,b,'long occluder')


# A row may move to a later source slot when that preserves every actual
# overlap relation. A disjoint first letter need not block the whole row.
parts=base[:1]+[event('X',575,1,3).replace(',ED-R,,',',ED-R,other,')]+base[1:]
a,b,rows,tails=merge(parts);ok('safe later source slot selected',rows==1);coverage(a,b,'later slot')
row_index=next(i for i,e in enumerate(b) if len(s.simplify_text(e.text,visible_only=True)[1])>1)
peer_index=next(i for i,e in enumerate(b) if e.name=='other')
ok('overlapping peer stays below row',peer_index<row_index)


# Two individually valid row placements must also remain valid together.
# The first row moves after X; the second must then move after that row to
# preserve the overlap order of the first row's i and the second row's u.
def named(part,name):return part.replace(',ED-R,,',',ED-R,'+name+',')
a_parts=[named(event(c,x,1,2+.2*i),'A') for i,(c,x) in enumerate(letters)]
b_parts=[named(event(c,x-86,1,2+.2*i),'B') for i,(c,x) in enumerate(letters)]
parts=[a_parts[0],named(event('X',552,1,3),'other'),b_parts[0],*a_parts[1:],*b_parts[1:]]
a,b,rows,tails=merge(parts)
ok('two row placements remain compatible',rows==2)
coverage(a,b,'joint placement')
row_order=[e.name for e in b if len(s.simplify_text(e.text,visible_only=True)[1])>1]
ok('joint placement preserves glyph draw order',row_order==['A','B'])

(ROOT/'validation/shared-interval-checks.json').write_text(json.dumps({'checks_passed':len(checks),'checks':checks},indent=2)+'\n')
print(len(checks),'shared-interval checks passed')
