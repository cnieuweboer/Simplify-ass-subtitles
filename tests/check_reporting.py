"""Exercise real Python CLI warning output, JSON and threshold pass-through."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import sys,subprocess,tempfile,json,io
here=Path(__file__).resolve().parents[1]
code_dir=here
sys.path.insert(0,str(code_dir))
import simplify_ass as s
checks=0
assert s.text_drop_warnings({})==[];checks+=1
assert s.text_drop_warnings({'scrolling_events_dropped':0})==[];checks+=1
sample={'scrolling_events_dropped':1320,'scrolling_concurrency_limit':32,
        'scrolling_blocks_dropped':1,'scrolling_peak_after_reduction':33}
w=s.text_drop_warnings(sample)[0]
assert w['code']=='scrolling_text_dropped' and w['events']==1320 and w['concurrency_limit']==32;checks+=1
plain=io.StringIO();s.print_text_drop_warning(w,'example.mkv - track 4',plain)
assert 'Dropped 1320 events' in plain.getvalue() and '\x1b' not in plain.getvalue();checks+=1
class TTY(io.StringIO):
 def isatty(self): return True
if sys.platform!='win32':
 color=TTY();s.print_text_drop_warning(w,'example.mkv - track 4',color)
 assert '\x1b[1;31m' in color.getvalue() and '\x1b[0m' in color.getvalue();checks+=1
header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sign,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp)/'crowded.ass'; data=header
 for row in range(33):
  for i in range(40):
   y=300+row*60-700*i/39;at=1+i*.05
   data+=f'Dialogue: 0,{s.format_time(at)},{s.format_time(at+.05)},Sign,,0,0,0,,{{\\an5\\pos(400,{y:g})\\org(400,{y:g})}}Row {row}\n'
 p.write_text(data);script=code_dir/'simplify_ass.py'
 for limit,expected in ((32,1320),(33,0),(0,0)):
  report=Path(temp)/f'stats-{limit}.json'
  r=subprocess.run([sys.executable,str(script),str(p),'--fonts-dir',str(code_dir/'fonts'),
                   '--scroll-concurrency-limit',str(limit),'--stats-json',str(report)],capture_output=True,text=True)
  assert r.returncode==0,r.stderr;checks+=1
  entry=json.loads(report.read_text())['tracks'][0]
  assert entry['stats']['scrolling_events_dropped']==expected;checks+=1
  if expected:
   assert entry['warnings'][0]['events']==expected and entry['warnings'][0]['concurrency_limit']==limit;checks+=1
   assert f'Dropped {expected} events due to exceeding concurrent event limit {limit}' in r.stderr;checks+=1
   assert '\x1b' not in r.stderr;checks+=1
  else:
   assert entry['warnings']==[] and 'WARNING:' not in r.stderr;checks+=1
 r=subprocess.run([sys.executable,str(script),str(p),'--scroll-concurrency-limit','-1'],capture_output=True,text=True)
 assert r.returncode==2 and 'must be nonnegative' in r.stderr;checks+=1
print(checks,'Python reporting checks passed')
(here/'validation/reporting-checks.json').write_text(json.dumps({'version':s.__version__,'python_reporting_checks':checks,'powershell_harness':'check_reporting.ps1; executed separately'},indent=2)+'\n')
