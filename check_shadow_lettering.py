"""Final shadow lettering admission, exact paint transfer and real-source checks."""
from pathlib import Path
from unittest.mock import patch
import ast, contextlib, copy, hashlib, importlib.util, io, json, subprocess, sys, tempfile
from PIL import Image, ImageChops
import simplify_ass as s
from executable_ast_audit import executable_ast

ROOT=Path(__file__).resolve().parent
checks=[]
def check(name, condition):
    assert condition, name
    checks.append(name)

fixture=ROOT/'test-data/Sword-S01E01-progressive-skills-source.ass'
header=fixture.read_text(encoding='utf-8-sig').split('Dialogue:',1)[0]
def event(tags='', body='Label', *, style='LightSigns', effect=''):
    text=header+f'Dialogue: 2,0:00:01.00,0:00:03.00,{style},actor,0,0,0,{effect},'+tags+body+'\n'
    return next(iter(s._resolve_document_state(s.parse_subtitle_document(text)).events.values()))

base=r'{\pos(100,200)\fnNyala\fs120\1a&HFE&\4c&H123456&\xshad-.01}'
e=event(base);before=copy.deepcopy(e)
result,count=s.normalize_shadow_lettering([e]);out=result[0]
check('one faint shadow label converted',count==1 and out is not e)
check('borrowed source/cache unmodified',vars(e)==vars(before))
check('literal and event identity preserved',s.OVERRIDE_RE.sub('',out.text)=='Label' and out.fields()[:-1]==e.fields()[:-1])
check('actual shadow position retained',out.state['pos']==(99.99,200))
check('BGR shadow colour transferred exactly',out.state['1c']=='123456')
check('opaque shadow supplies opaque primary',out.state['1a']==0)
check('both shadow axes and alpha disabled',out.state['shad']==out.state['xshad']==out.state['yshad']==0 and out.state['4a']==255)
check('font and geometry preserved',all(out.state.get(k)==e.state.get(k) for k in ('fn','fs','b','i','an','fscx','fscy','fsp','q','bord')))
check('normalization is idempotent',s.normalize_shadow_lettering(result)==(result,0))
for tags,position,alpha in [
    (r'\shad.02',(100.02,200.02),0),
    (r'\shad2\xshad.01\yshad-.02',(100.01,199.98),0),
    (r'\xshad2\yshad2\shad.01',(100.01,200.01),0),
    (r'\alpha&HFF&\1a&HFE&\4a&H80&\xshad.01',(100.01,200),128),
    (r'\1a&HFF&\4a&H00&\yshad-.03',(99.99,199.97),0),
]:
    e=event(base[:-1]+tags+'}');r,n=s.normalize_shadow_lettering([e])
    check('ordered offsets/alpha '+tags,n==1 and r[0].state['pos']==position and r[0].state['1a']==alpha)
    check('explicit shadow clear '+tags,all(r[0].state[k]==0 for k in ('shad','xshad','yshad')) and r[0].state['4a']==255)
# Inherited paint and a reset still resolve through the existing style parser.
e=event(r'{\pos(100,200)\shad.01\1a&HFE&\4a&H40&\4c&HABCDEF&}')
r,n=s.normalize_shadow_lettering([e]);check('inherited geometry and partial shadow opacity',n==1 and r[0].state['1a']==64 and r[0].state['1c']=='ABCDEF')
original_header=header
style_line=next(line for line in header.splitlines() if line.startswith('Style: LightSigns,'))
fields=style_line.split(',');fields[3]='&HFEFFFFFF';fields[6]='&H40ABCDEF';fields[17]='0.01'
header=header.replace(style_line,','.join(fields))
e=event(r'{\pos(100,200)}');header=original_header
r,n=s.normalize_shadow_lettering([e])
check('style-inherited paint and offsets transferred',n==1 and r[0].state['1c']=='ABCDEF' and r[0].state['1a']==64 and r[0].state['pos']==(100.01,200.01))
e=event(base[:-1]+r'\pos(999,999)}');r,n=s.normalize_shadow_lettering([e])
check('first position latch preserved',n==1 and r[0].state['pos']==(99.99,200))
e=event(r'{\pos(100,200)\alpha&HFF&}{\rLightSigns\1a&HFE&\4c&H123456&\xshad.01}')
r,n=s.normalize_shadow_lettering([e]);check('paint replacement follows resets',n==1 and r[0].state['1c']=='123456' and r[0].state['1a']==0)
for offset,expected in [('.05',1),('.050001',0)]:
    e=event(base.replace('-.01',offset));r,n=s.normalize_shadow_lettering([e])
    check('scaled near-coincident boundary '+offset,n==expected)
e=s.dataclass_replace(event(base),unit=.1);r,n=s.normalize_shadow_lettering([e])
check('offset threshold follows document unit',n==0 and r[0] is e)
for label,tags,body,effect in [
    ('visible foreground',r'\1a&H00&','Label',''),
    ('foreground beyond faint cutoff',r'\1a&HFD&','Label',''),
    ('no shadow paint',r'\4a&HFF&','Label',''),
    ('shadow too faint',r'\4a&HFE&','Label',''),
    ('no actual offset',r'\shad0','Label',''),
    ('ordinary distant shadow',r'\xshad2','Label',''),
    ('outline width',r'\bord1','Label',''),
    ('axis outline width',r'\bord0\xbord1','Label',''),
    ('box style',r'\rSystem','Label',''),
    ('blur',r'\blur1','Label',''),
    ('edge blur',r'\be1','Label',''),
    ('rotation',r'\frz10','Label',''),
    ('shear',r'\fax.1','Label',''),
    ('vertical font',r'\fn@Nyala','Label',''),
    ('clip',r'\clip(0,0,500,500)','Label',''),
    ('inverse clip',r'\iclip(0,0,500,500)','Label',''),
    ('drawing',r'\p1','m 0 0 l 10 0 10 10 0 10',''),
    ('transform',r'\t(0,100,\xshad.02)','Label',''),
    ('move',r'\move(100,200,200,200)','Label',''),
    ('fade',r'\fad(100,0)','Label',''),
    ('karaoke',r'\k20','Label',''),
    ('inline paint','',r'A{\4c&HFFFFFF&}B',''),
    ('inline reset','',r'A{\rLightSigns}B',''),
    ('effect','', 'Label','Banner;0;0;10'),
]:
    e=event(base[:-1]+tags+'}',body,effect=effect)
    r,n=s.normalize_shadow_lettering([e]);check('reject '+label,n==0 and r[0] is e)
for key,value in [('pos',(float('nan'),200)),('xshad',float('inf'))]:
    # Nonfinite authored geometry must fail admission.
    if key=='pos':e=event(base.replace('(100,200)','(nan,200)'))
    else:e=event(base.replace('-.01','inf'))
    r,n=s.normalize_shadow_lettering([e]);check('reject nonfinite authored '+key,n==0 and r[0] is e)

spec=importlib.util.spec_from_file_location('shadow_lettering_reference',ROOT/'test-data/simplify_ass-v173-reference.py')
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
    folder=Path(directory);outputs=[];stats=[];paths=[]
    for engine in (old,s):
        output=folder/(engine.__version__+'.ass')
        stats.append(engine.simplify_ass(fixture,output,engine.SimplifyConfig(),font_metrics=engine.FontMetrics([ROOT/'fonts'])))
        outputs.append(s.load_subtitle_events(output)[1])
        paths.append(output)
    check('real scene converts eight shadow labels',stats[1]['shadow_lettering_normalized']==8)
    check('existing conversion statistics identical',{k:v for k,v in stats[1].items() if k!='shadow_lettering_normalized'}==stats[0])
    check('all text/events/timing/layers retained',len(outputs[0])==len(outputs[1]) and all(a.fields()[:-1]==b.fields()[:-1] and s.OVERRIDE_RE.sub('',a.text)==s.OVERRIDE_RE.sub('',b.text) for a,b in zip(*outputs)))
    check('all eight rectangle events byte identical',[e.text for e in outputs[0] if e.state.get('p')]==[e.text for e in outputs[1] if e.state.get('p')])
    for a,b in zip(*outputs):
        if a.text!=b.text:
            check('real caption transfers actual paint '+s.OVERRIDE_RE.sub('',a.text),b.state['1c']==a.state['4c'] and b.state['1a']==a.state['4a'] and b.state['4a']==255)
    def render(path):
        result=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=1920x1080:r=1',
            '-vf',f'setpts=PTS+239/TB,ass=filename={path}:fontsdir={ROOT/"fonts"}',
            '-frames:v','1','-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True)
        return Image.frombytes('RGB',(1920,1080),result.stdout)
    difference=ImageChops.difference(render(paths[0]),render(paths[1]))
    check('real 3:59 frame differs by at most one colour level',max(hi for lo,hi in difference.getextrema())<=1)
    # Keep this normalization after support reconstruction and outside legacy mode.
    real=s.normalize_shadow_lettering
    with patch.object(s,'normalize_shadow_lettering',wraps=real) as normalize:
        s.simplify_ass(fixture,folder/'legacy.ass',s.SimplifyConfig(level=2))
        check('legacy path unchanged',normalize.call_count==0)

def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a=definitions(ROOT/'test-data/simplify_ass-v173-reference.py');b=definitions(ROOT/'test-data/simplify_ass-v174-reference.py')
check('only one normalization function added',set(b)-set(a)=={'normalize_shadow_lettering'} and not set(a)-set(b))
check('only existing entry point changed',{k for k in a if ast.dump(a[k])!=ast.dump(b[k])}=={'simplify_ass'})
calls=[n.func.id for n in ast.walk(b['simplify_ass']) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
check('normalization follows support reconstruction',calls.index('_reconstruct_caption_backdrops')<calls.index('normalize_shadow_lettering')<calls.index('write_subtitle_document'))
report=dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks,new_definitions=['normalize_shadow_lettering'],changed_definitions=['simplify_ass'])
(ROOT/'validation/shadow-lettering-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'shadow lettering checks passed; actual progressive scene: eight labels normalized')
