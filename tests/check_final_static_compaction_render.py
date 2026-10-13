"""Final serialization: literal formatting, history, immutable inputs and pixels."""
import test_paths
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import contextlib,hashlib,io,json,subprocess
from PIL import Image,ImageChops
import simplify_ass as s
from lyric_layer_fixtures import HEADER,event,TEXT
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'validation/final-static-compaction';DEST.mkdir(exist_ok=True)
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
def parsed(text,tags=''):
 return next(iter(s._resolve_document_state(s.parse_subtitle_document(HEADER+event(text,100,0,(1,4),tags))).events.values()))
CASES=[
 ('superseded adjacent paint',TEXT,r'\1a&HFE&}{\1a&H00&\4a&HFF&\shad0\xshad0\yshad0',True),
 ('style defaults',TEXT,r'\fs40\fscx100\fscy100\fsp0\blur0\be0',True),
 ('inline gradient',r'The {\1c&H123456&\fs40\fsp0}sky {\1c&HABCDEF&\fscx100}shines','',True),
 ('axis restoration',r'A{\xbord6\fs40}B{\bord2\fsp0}C','',True),
 ('shadow restoration',r'A{\xshad6\fs40}B{\shad0\fsp0}C','',True),
 ('named reset',r'A{\rLyric\fs40\fscx100}B{\r\fs40}C','',True),
 ('relative font size',r'A{\fs+5\fs+5\fsp0}B','',True),
 ('relative size precision',r'A{\fs+2\fs+3\fsp0}B','',False),
 ('unrotated origin',TEXT,r'\org(100,100)\fs40',True),
 ('rotated origin',TEXT,r'\org(100,100)\frz12\fs40',True),
 ('static drawing','m 0 0 l 50 0 50 50 0 50',r'\p1\fs40\fsp0',True),
 ('mixed drawing and text',r'm 0 0 l 50 0 50 50{\p0\fs40}Text',r'\p1\fsp0',True),
 ('bold italic face',TEXT,r'\b1\i1\fs40\fscx100',True),
 ('alpha shorthand must not expand',TEXT,r'\alpha&H80&',False),
 ('first alignment latch',r'A{\an9\fs40}B',r'\an7\fs40',False),
 ('invalid first alignment latch',r'A{\an9\fs40}B',r'\an0\fs40',False),
 ('high precision anchor',TEXT,r'\pos(100.123456789,100)\fs40',True),
 ('high precision layout',TEXT,r'\fs40.123456789\fsp0',False),
 ('animation',TEXT,r'\t(0,1000,\1c&H123456&)\fs40',False),
 ('move',TEXT,r'\move(100,100,200,100)\fs40',False),
 ('fade',TEXT,r'\fad(100,100)\fs40',False),
 ('karaoke',TEXT,r'\kf100\fs40',False),
 ('unknown tag',TEXT,r'\fe128\fs40',False),
 ('inline annotation',r'{authored note}The sky shines',r'\fs40',False),
]
# The event helper adds a first position; set_pos here preserves the authored
# precision case by replacing that first tag rather than adding a second one.
def render(es,label):
 path=DEST/(label+'.ass');path.write_text(HEADER+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in es))
 p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=gray:s=640x360:r=1',
  '-vf',f'settb=1/1000,setpts=PTS+2000,ass=filename={path}:fontsdir={ROOT/"fonts"}',
  '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
 return Image.frombytes('RGB',(640,360),p.stdout)
metric=s.FontMetrics([ROOT/'fonts'])
for bold,italic in ((0,False),(-1,True)):
 assert metric.matching_face('Volkhov',bold,italic) is not None,('Missing required Volkhov face',bold,italic)
rendered=0
for name,literal,tags,changes in CASES:
 e=parsed(literal,tags)
 if name=='high precision anchor':
  e=s.replace_event(e,text=e.text.replace(r'\pos(100.000000,100)',r'\pos(100.123456789,100)'))
  changes=False
 original=deepcopy(e);out=s.compact_static_overrides([e],0,final=True)[0]
 check(name+': intended spelling result',(out.text!=e.text)==changes)
 check(name+': no tag expansion',len(out.text)<=len(e.text))
 check(name+': stable final spelling',s.compact_static_overrides([out],0,final=True)[0].text==out.text)
 check(name+': literal text retained',s.OVERRIDE_RE.sub('',out.text)==s.OVERRIDE_RE.sub('',e.text))
 check(name+': event timing layer actor and margins retained',out.fields()[:-1]==e.fields()[:-1])
 check(name+': input/cache/catalog immutable',vars(e)==vars(original))
 if changes:
  check(name+': context source identity and proof retained',out.measurement is e.measurement and out.source_index==e.source_index and out.evidence is e.evidence)
  check(name+': formatting and continuation equivalent',s._finished_static_key(e)==s._finished_static_key(out))
  check(name+': pixel-identical',ImageChops.difference(render([e],name+'.before'),render([out],name+'.after')).getbbox() is None);rendered+=1
# Final mode must not clamp a finished blur even if a caller requests zero.
e=parsed(TEXT,r'\blur4\fs40');out=s.compact_static_overrides([e],0,final=True)[0]
check('finished blur retained',out.state.get('blur')==4)
check('finished blur not clamped',ImageChops.difference(render([e],'blur.before'),render([out],'blur.after')).getbbox() is None);rendered+=1
comment=s.dataclass_replace(parsed(TEXT,r'\fs40'),kind='Comment')
check('comment event retains identity',s.compact_static_overrides([comment],0,final=True)[0] is comment)
e=parsed(TEXT,r'\fs40');e=s.replace_event(e,text=e.text.replace(r'\pos(100.000000,100)',''))
check('collision-managed caption can compact without adding position',s.compact_static_overrides([e],0,final=True)[0].text==TEXT)
# Trace the finished records at the actual final pipeline handoff.
source=ROOT/'test-data/corpus/DemonSlayer-S04E02.original.ass';digest=hashlib.sha256(source.read_bytes()).hexdigest();captured=[];real=s.compact_static_overrides
output=DEST/'DemonSlayer.ass';report=s.FontProcessingReport()
def capture(es,max_blur,**kwargs):
 out=real(es,max_blur,**kwargs)
 if kwargs.get('final'):captured.append((list(es),out))
 return out
with patch.object(s,'compact_static_overrides',capture),contextlib.redirect_stdout(io.StringIO()):
 stats=s.simplify_ass(source,output,s.SimplifyConfig(),font_metrics=metric,font_report=report)
check('actual required fonts available',not report.missing_families)
check('one final serialization handoff',len(captured)==1)
before,after=captured[0]
check('actual late-generated headers compacted',sum(a.text!=b.text for a,b in zip(before,after))>0)
check('actual event multiplicity and order retained',len(before)==len(after) and all(a.fields()[:-1]==b.fields()[:-1] for a,b in zip(before,after)))
check('actual final spelling stable',all(a.text==b.text for a,b in zip(after,real(after,2,final=True))))
check('actual output count reflects same events',stats['output']==sum(e.kind=='Dialogue' for e in after))
check('source preserved',hashlib.sha256(source.read_bytes()).hexdigest()==digest)
(DEST/'checks.json').write_text(json.dumps(dict(version=s.__version__,checks=len(checks),render_pairs=rendered),indent=2)+'\n')
print(len(checks),'final static compaction checks passed;',rendered,'pixel-identical render pairs')
