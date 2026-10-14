"""Complete boundary glyph ownership with bounded source fade overruns."""
import test_paths
from pathlib import Path
from copy import deepcopy
import json,contextlib,io,tempfile
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
metric=s.FontMetrics([ROOT/'fonts']);assert metric.matching_face('Volkhov',0,False)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def event(word,x,start,end,tags=''):
 return f'Dialogue: 0,{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{{\\an5\\pos({x},100){tags}}}{word}\n'
seed=next(iter(s._resolve_document_state(s.parse_subtitle_document(HEADER+event('abc',500,1.5,3.5))).events.values()))
glyphs=s.authored_glyph_positions(metric,seed.state,'abc',500,1);assert glyphs
checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
def fixture(phase,overrun,guard):
 letters=glyphs[:-1] if guard=='missing glyph' else glyphs
 if guard=='duplicate glyph':letters=letters+letters[:1]
 text=HEADER
 for word,x in letters:
  if phase=='entrance':
   tags=rf'\frz30\fad({500+overrun},0)\t(0,500,\frz0)'
   if guard=='unsettled rotation':tags=tags.replace(r'\t(0,500,\frz0)',r'\t(0,500,\frz15)')
   if guard=='paint animation':tags=tags.replace(r'\frz0)',r'\frz0\1c&H112233&)')
   text+=event(word,x,1,1.5,tags)
  else:
   tags=rf'\an5\move({x},100,{x},120)\fad(0,{500+overrun})'
   text+=f'Dialogue: 0,0:00:03.50,0:00:04.00,Default,,0,0,0,,{{{tags}}}{word}\n'
 held_word='xyz' if guard=='wrong literal' else 'abc'
 held_x=600 if guard=='wrong anchor' else 500
 held_tags=r'\fnMissingFont' if guard=='missing font' else ''
 if guard=='competing parent':text+=event(held_word,held_x,1.5,3.5,held_tags)
 text+=event(held_word,held_x,1.5,3.5,held_tags)
 sources=s._resolve_document_state(s.parse_subtitle_document(text)).events
 return text,sources,list(sources.values()),{i:s.OVERRIDE_RE.sub('',e.text) for i,e in sources.items()}
for phase in ('entrance','exit'):
 for overrun in (0,10,40,50,51,60):
  for guard in ('complete','missing glyph','duplicate glyph','wrong literal','wrong anchor','missing font','competing parent'):
   text,sources,events,visible=fixture(phase,overrun,guard)
   before=deepcopy((events,visible,sources))
   removed=s.match_boundary_glyph_effects(events,visible,sources,metric)
   label=f'{phase} {overrun} ms {guard}'
   check(label+': ownership',len(removed)==(3 if overrun<=50 and guard=='complete' else 0))
   check(label+': borrowed inputs unchanged',before==(events,visible,sources))
   if removed:
    retained=[e for e in events if e.source_index not in removed]
    check(label+': full held literal and timing',len(retained)==1 and visible[retained[0].source_index]=='abc' and (retained[0].start_s,retained[0].end_s)==(1.5,3.5))
    check(label+': repeat stable',s.match_boundary_glyph_effects(retained,visible,sources,metric)==set())
for guard in ('unsettled rotation','paint animation'):
 _,sources,events,visible=fixture('entrance',40,guard)
 check(guard+': rejected',not s.match_boundary_glyph_effects(events,visible,sources,metric))
# Full conversions prove the change reaches normal source preparation, without
# deleting a retained word, altering its hold interval or requiring another run.
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory)
 for overrun in (40,50,51):
  text,_,_,_=fixture('entrance',overrun,'complete')
  path=root/f'source-{overrun}.ass';out=root/f'out-{overrun}.ass';again=root/f'again-{overrun}.ass';path.write_text(text)
  report=s.FontProcessingReport()
  with contextlib.redirect_stdout(io.StringIO()):
   s.simplify_ass(path,out,s.SimplifyConfig(),font_metrics=metric,font_report=report)
   s.simplify_ass(out,again,s.SimplifyConfig(),font_metrics=metric)
  events=s.load_subtitle_events(out)[1]
  check(f'pipeline {overrun}: exact fonts',not report.missing_families)
  if overrun<=50:
   check(f'pipeline {overrun}: only complete held word',len(events)==1 and s.OVERRIDE_RE.sub('',events[0].text)=='abc' and (events[0].start_s,events[0].end_s)==(1.5,3.5))
   check(f'pipeline {overrun}: byte repeat stable',out.read_bytes()==again.read_bytes())
  else:check('pipeline 51: glyph effects retained',len(events)>1)
  check(f'pipeline {overrun}: source bytes unchanged',path.read_text()==text)
(ROOT/'validation/rotating-entrance-fade-checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks)),indent=2)+'\n')
print(len(checks),'rotating entrance fade checks passed')
