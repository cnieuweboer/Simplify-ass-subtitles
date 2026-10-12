#!/usr/bin/env python3
"""Exercise measurement-dependent strip and unpositioned lyric proofs."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from copy import deepcopy
import importlib.util,json,random,sys
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current)
from event_evidence_test_helpers import event_comparison_fields
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('measurement_effect_reference',ROOT/'test-data/simplify_ass-v156-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
def snapshot(value):
 if type(value).__name__=='Event':return snapshot(event_comparison_fields(value))
 if isinstance(value,dict):return {k:snapshot(v) for k,v in value.items()}
 if isinstance(value,(tuple,list)):return tuple(snapshot(v) for v in value)
 if isinstance(value,set):return frozenset(value)
 if hasattr(value,'__dict__'):return snapshot(vars(value))
 return value

# Reuse the existing authored strip scenarios and builder, without its older
# implementation-call trace assertions. Those traces necessarily change when
# context moves out of dictionaries and becomes an explicit renderer argument.
fixture=ROOT/'tests'/'check_sliced_text_stages.py'
namespace={'__file__':str(fixture),'__name__':'measurement_strip_fixtures'}
prefix=fixture.read_text().split('SPY_NAMES=')[0]
prefix=prefix.replace("e.defaults.update(d.get('defaults_changes',{}))", """updates=dict(d.get('defaults_changes',{}))
        if hasattr(e,'measurement') and '_canvas' in updates:
            e.measurement=module.dataclass_replace(e.measurement,canvas=updates.pop('_canvas'))
        e.defaults.update(updates)""")
exec(compile(prefix,str(fixture),'exec'),namespace)
for case in namespace['CASES']:
 for order in ('original','reverse','shuffle'):
  outcomes=[]
  for module in (previous,current):
   events,_=namespace['parse'](module,case)
   if order=='reverse':events.reverse()
   elif order=='shuffle':random.Random(157).shuffle(events)
   before=deepcopy(snapshot(events));out,n=module.collapse_sliced_text_sequences(events)
   check(case['name']+order+module.__version__+' borrowed events',before==snapshot(events))
   outcomes.append((snapshot(out),n,out is events,[any(e is source for source in events) for e in out]))
   if 'expected' in case:check(case['name']+order+module.__version__+' decision',n==case['expected'])
  check(case['name']+order+' strip output parity',outcomes[0]==outcomes[1])

HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow, MarginL, MarginR, MarginV
Style: Default,Arial,40,2,2,0,20,20,20
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def line(module,start,end,tags,text):
 return f'Dialogue: 0,{module.format_time(start)},{module.format_time(end)},Default,,0,0,0,,{{{tags}}}{text}\n'
for resolution in ('complete','none','onlyx'):
 for alignment in (1,2,3,4,5,6,7,8,9):
  for invalid in ('none','wrong y','incomplete exit','collision'):
   outcomes=[]
   for module in (previous,current):
    header=HEADER
    if resolution=='none':header=header.replace('PlayResX: 1920\nPlayResY: 1080\n','')
    if resolution=='onlyx':header=header.replace('PlayResY: 1080\n','')
    height=40
    y=1080-20-height/2 if alignment<=3 else 540 if alignment<=6 else 20+height/2
    x0=20 if (alignment-1)%3==0 else 1620 if (alignment-1)%3==2 else 820
    text=line(module,1,4,fr'\an{alignment}','ABCDEFGH')
    for phase in ('in','out'):
     for i,char in enumerate('ABCDEFGH'):
      if invalid=='incomplete exit' and phase=='out' and i==7:continue
      x=x0+40*i;ey=y+(10 if invalid=='wrong y' else 0)
      move=fr'\move({x-50},{ey},{x},{ey})' if phase=='in' else fr'\move({x},{ey},{x+50},{ey})'
      text+=line(module,.5 if phase=='in' else 4,1 if phase=='in' else 4.5,r'\an5'+move,char)
    if invalid=='collision':text+=line(module,2,3,fr'\an{alignment}','OTHERLINE')
    source_doc=module._resolve_document_state(module.parse_subtitle_document(header+text))
    sources=source_doc.events
    events=list(sources.values())
    # Freezing preserves glyph positions while original endpoints supply proof.
    events=[module.replace_event(e,text=module.simplify_visual_text(e.text,0,e.duration,e.defaults,e.styles,1)[0])
            if r'\move' in e.text else e for e in events]
    visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
    result=module.match_authored_lyric_rows(events,visible,sources)
    outcomes.append(snapshot((result.removed_sources,result.row_additions) if hasattr(result,'source_updates') else result))
   check(f'authored lyric {resolution} alignment {alignment} {invalid}',outcomes[0]==outcomes[1])
   if resolution=='complete' and invalid=='none':check('authored acceptance '+str(alignment),len(outcomes[-1][0])==16)

# Font-positioned staggered rows use the same explicit viewport and margin placement.
metrics={m:m.FontMetrics([ROOT/'fonts']) for m in (previous,current)}
for resolution in ('complete','none'):
 for collision in (False,True):
  outcomes=[]
  for module in (previous,current):
   header=HEADER if resolution=='complete' else HEADER.replace('PlayResX: 1920\nPlayResY: 1080\n','')
   text=line(module,1,4,r'\an5','ABCDEFGH')
   fonts=measurement_fonts(metrics[module]) if module is current else metrics[module]
   fit=fonts.matching_face('Arial',0,False);factor=fonts.ass_em_scale(fit)
   advances=[fonts.measure(fit,char,False)*40/1024*factor for char in 'ABCDEFGH']
   start=960-sum(advances)/2
   for i,char in enumerate('ABCDEFGH'):
    x=start+sum(advances[:i])+advances[i]/2
    text+=line(module,.98,4.02,fr'\an5\pos({x},540)',char)
   if collision:text+=line(module,2,3,r'\an5','OTHERLINE')
   doc=module._resolve_document_state(module.parse_subtitle_document(header+text))
   events=list(doc.events.values());visible={e.source_index:module.simplify_text(e.text,visible_only=True)[1] for e in events}
   outcomes.append(module.match_staggered_full_line_copies(events,visible,metrics[module]))
  check(f'staggered {resolution} collision {collision}',outcomes[0]==outcomes[1])
  if resolution=='complete' and not collision:check('staggered acceptance',len(outcomes[-1])==8)
report=dict(version=current.__version__,checks_passed=len(checks),strip_scenarios=len(namespace['CASES']),
            authored_lyric_scenarios=108,staggered_scenarios=4)
(ROOT/'validation/measurement-effects-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'measurement effect checks passed')
