"""One-centisecond source endpoint rounding reaches the complete sweep proof."""
import test_paths
from pathlib import Path
from copy import deepcopy
import json
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
BEFORE='112233';AFTER='445566';checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
def fixture(endpoint,offset,guard):
 records=[];held=[]
 for i,word in enumerate(('Sun','moon','stars')):
  x=100+i*100;begin=2+i*.2;end=begin+.2
  first=1+offset if endpoint=='start' else 1
  last=5+offset if endpoint=='end' else 5
  phases=[(first,begin,rf'\1c&H{BEFORE}&'),
          (begin,end,rf'\1c&H{BEFORE}&\t(0,200,\1c&H{AFTER}&)'),
          (end,last,rf'\1c&H{AFTER}&')]
  if guard=='gap':phases[2]=(end+.02,last,phases[2][2])
  if guard=='cycle':phases[1]=(begin,end,phases[1][2]+rf'\t(100,200,\1c&H{BEFORE}&)')
  if guard=='different palette' and i==1:phases=[(a,b,t.replace(AFTER,'778899')) for a,b,t in phases]
  if guard=='duplicate phase' and i==1:phases.append(phases[1])
  if guard=='missing transition' and i==1:phases.pop(1)
  for a,b,tags in phases:records.append((word,x,a,b,tags))
  held.append((word,x,1,5,rf'\1c&H{BEFORE}&'))
 def parse(items):
  lines=[f'Dialogue: 0,{s.format_time(a)},{s.format_time(b)},Default,,0,0,0,,{{\\pos({x},100){tags}}}{word}\n' for word,x,a,b,tags in items]
  events=list(s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(lines))).events.values())
  # Real files use centiseconds; direct endpoints also exercise both sides of
  # the numerical 11 ms bound without binary-float equality ambiguity.
  return [s.dataclass_replace(e,start_s=a,end_s=b) for e,(_,_,a,b,_) in zip(events,items)]
 sources={e.source_index:e for e in parse(records)}
 events=[s.dataclass_replace(e,source_index=e.source_index+10000) for e in parse(held)]
 visible={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events}
 return events,visible,sources
for endpoint in ('start','end'):
 for offset in (-.04,-.012,-.0111,-.0109,-.01,0,.01,.0109,.0111,.012,.04):
  for guard in ('complete','gap','cycle','different palette','duplicate phase','missing transition'):
   events,visible,sources=fixture(endpoint,offset,guard)
   for reverse in (False,True):
    if reverse:events=list(reversed(events));sources=dict(reversed(list(sources.items())))
    before=deepcopy((events,visible,sources));out=s.normalize_karaoke_completion_paint(events,visible,sources)
    label=f'{endpoint} {offset*1000:g} ms {guard} reverse={reverse}'
    expected=guard=='complete' and abs(offset)<=.011
    check(label+': destination or original paint',all(e.state['1c']==(AFTER if expected else BEFORE) for e in out))
    check(label+': count literal geometry timing ownership',len(out)==len(events) and all(
     (s.OVERRIDE_RE.sub('',a.text),a.start,a.end,a.start_s,a.end_s,a.source_index,s.text_layout_key(a),s.get_pos(a.text))==
     (s.OVERRIDE_RE.sub('',b.text),b.start,b.end,b.start_s,b.end_s,b.source_index,s.text_layout_key(b),s.get_pos(b.text))
     for a,b in zip(events,out)))
    check(label+': borrowed inputs unchanged',before==(events,visible,sources))
    if expected:
     again=s.normalize_karaoke_completion_paint(out,visible,sources)
     check(label+': repeat paint stable',[e.state for e in again]==[e.state for e in out])
(ROOT/'validation/karaoke-completion-bound-checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'karaoke completion bound checks passed')
