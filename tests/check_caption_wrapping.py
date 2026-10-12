"""Authored wrapping survives caption reconstruction and source-fade matching."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
import ast, contextlib, hashlib, importlib.util, json, subprocess, sys, tempfile
import simplify_ass as s
from executable_ast_audit import executable_ast

ROOT=Path(__file__).resolve().parents[1]
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)

for q in range(4):
    state={**s.DEFAULT_STATE,'q':q,'pos':(320,100)}
    before=deepcopy(state)
    for script_wrap in range(4):
        text=s.render_simplified_caption(state,'A long caption',measurement=s.DocumentMeasurementContext((640,180),script_wrap))
        check(f'explicit q{q} overrides script wrap {script_wrap}',s.effective_state(text)['q']==q)
    check(f'borrowed q{q} state unchanged',state==before)
for script_wrap in (None,0,1,2,3):
    text=s.render_simplified_caption(s.DEFAULT_STATE,'Caption',measurement=s.DocumentMeasurementContext((640,180),script_wrap))
    check(f'absent override stays absent for script wrap {script_wrap}','q' not in s.effective_state(text))
state=s.effective_state(r'{\q2\q1}Caption')
check('last effective authored wrapping retained',s.effective_state(s.render_simplified_caption(state,'Caption'))['q']==1)
state=s.effective_state(r'{\q2\r}Caption')
check('event-level wrapping survives style reset',s.effective_state(s.render_simplified_caption(state,'Caption'))['q']==2)

# Independent libass evidence: a narrow viewport makes q2 visibly differ
# from automatic wrapping; compare each mode with a manually authored cue.
header='''[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 360
WrapStyle: 0
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,32,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,20,20,20,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory);pixels={}
    for q in range(4):
        literal='One long caption needs several words to wrap'
        state={**s.DEFAULT_STATE,'fn':'Arial','fs':32,'an':5,'q':q,'pos':(160,180),'b':0,'i':0}
        bodies={'authored':fr'{{\q{q}\an5\pos(160,180)}}'+literal,
                'simplified':s.render_simplified_caption(state,literal)}
        rendered={}
        for label,body in bodies.items():
            path=directory/(label+str(q)+'.ass')
            path.write_text(header+'Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,'+body+'\n')
            vf=f"subtitles=filename='{path}':fontsdir='{ROOT/'fonts'}'"
            rendered[label]=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=320x360:r=1',
                '-vf',vf,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-threads','1','pipe:1'],capture_output=True,check=True).stdout
        check(f'libass authored and rebuilt q{q} pixels match',rendered['authored']==rendered['simplified'])
        pixels[q]=rendered['simplified']
    check('render fixture exposes actual wrapping differences',pixels[0]!=pixels[2])

spec=importlib.util.spec_from_file_location('wrapping_reference',ROOT/'test-data/simplify_ass-v170-reference.py')
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
fixture=ROOT/'test-data/Sword-S01E02-ending-handoff-source.ass'
document=s._resolve_document_state(s.read_subtitle_document(fixture))
sources=[e for e in document.events.values() if e.kind=='Dialogue' and e.layer=='1']
check('real source has 40ms overlapping fade intervals',len(sources)==2 and round(sources[0].end_s-sources[1].start_s,2)==.04)
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory);outputs={};statistics={};calls=[]
    trim=s.trim_faded_cue_overlaps
    def recorded(events,rows,source_events,**kwargs):
        before=deepcopy((events,rows,source_events))
        result=trim(events,rows,source_events,**kwargs)
        check('overlap pass borrows events rows and source caches',before==(events,rows,source_events))
        calls.append(result[1]);return result
    s.trim_faded_cue_overlaps=recorded
    try:
        for label,module in [('v170',old),('current',s)]:
            path=directory/(label+'.ass')
            with contextlib.redirect_stdout(None):
                statistics[label]=module.simplify_ass(fixture,path,module.SimplifyConfig(),font_metrics=module.FontMetrics([ROOT/'fonts']))
            outputs[label]=list(module._resolve_document_state(module.read_subtitle_document(path)).events.values())
    finally:
        s.trim_faded_cue_overlaps=trim
    a=outputs['v170'];b=outputs['current']
    check('old release reproduces overlap',len(a)==2 and a[0].end_s>a[1].start_s)
    check('same two captions retained',len(b)==2)
    check('existing source fade check fixes handoff',calls==[1])
    check('shared midpoint preserves both source cores',b[0].end==b[1].start=='0:22:31.93' and sources[0].end_s-.2<=b[0].end_s<=sources[1].start_s+.15)
    check('outer exposure unchanged',a[0].start==b[0].start and a[1].end==b[1].end)
    check('q2 and red outline survive final serialization',all(e.state.get('q')==2 and e.state['3c']=='260AC6' for e in b))
    check('text placement font and paint unchanged',all(s.OVERRIDE_RE.sub('',x.text)==s.OVERRIDE_RE.sub('',y.text) and {k:v for k,v in x.state.items() if k!='q'}=={k:v for k,v in y.state.items() if k!='q'} for x,y in zip(a,b)))
    # A layout mismatch must still prevent trimming: do not relax the proof.
    incompatible=[replace(e,state={**e.state,'q':1}) for e in b]
    incompatible=[replace(e,start=a[i].start,end=a[i].end,start_s=a[i].start_s,end_s=a[i].end_s) for i,e in enumerate(incompatible)]
    rejected,n=s.trim_faded_cue_overlaps(incompatible,[],document.events)
    check('genuine wrapping mismatch still rejected',n==0 and rejected==incompatible)

def definitions(path):
    return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a=definitions(ROOT/'test-data/simplify_ass-v170-reference.py');b=definitions(ROOT/'test-data/simplify_ass-v171-reference.py')
changed={k for k in a if ast.dump(a[k])!=ast.dump(b[k])}
check('only existing renderer changed',changed=={'render_simplified_caption'} and a.keys()==b.keys())
report=dict(version=s.__version__,runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),checks_passed=len(checks),checks=checks,changed_definitions=sorted(changed),pixel_identical_comparisons=4)
(ROOT/'validation/caption-wrapping-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'{len(checks)} caption wrapping and real-source handoff checks passed')
