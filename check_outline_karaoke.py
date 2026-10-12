"""Bounded strip-outline completion proof, ownership and libass timing checks."""
from pathlib import Path
from dataclasses import replace
from copy import deepcopy
from types import MappingProxyType
import ast,contextlib,importlib.util,json,subprocess,sys,tempfile
from PIL import Image,ImageDraw
import simplify_ass as s
from executable_ast_audit import executable_ast
ROOT=Path(__file__).resolve().parent
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
fixture=ROOT/'test-data/Sword-S01E02-ending-sweep-source.ass'
document=s._resolve_document_state(s.read_subtitle_document(fixture))
events=list(document.events.values())
metric=s.FontMetrics([ROOT/'fonts'])
visible={e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events}
context=s.StackedTextContext({},[],{},set(),set(),MappingProxyType(document.events),metric)
groups={}
for e in events:groups.setdefault((s.get_pos(e.text),visible[e.source_index]),[]).append(e)
profiles=[]
for (pos,word),group in sorted(groups.items()):
    if pos[1]!=82.2:continue
    chosen=next(e for e in group if e.layer=='1')
    evidence=s._collect_outline_strip_evidence(chosen,group,context)
    profile=s._profile_outline_strip_sweep(chosen,evidence,context)
    check('complete syllable profile '+word+str(pos),profile is not None)
    profiles.append(profile)
check('existing ordered sweep accepts full row',s._prove_ordered_karaoke_completion_sweep(profiles))
check('reversed times normalized locally',profiles[2].begin==profiles[2].end)
check('completed destination red',all(int(p.final['3c'][4:],16)>int(p.final['3c'][:2],16)*2 for p in profiles))
check('reversed row remains a one-way sweep',s._prove_ordered_karaoke_completion_sweep(profiles[::-1]))
check('mixed order rejected',not s._prove_ordered_karaoke_completion_sweep([profiles[1],profiles[0]]+profiles[2:]))
check('simultaneous changes rejected',not s._prove_ordered_karaoke_completion_sweep([replace(p,begin=1,end=2) for p in profiles]))
check('no completed hold rejected',not s._prove_ordered_karaoke_completion_sweep([replace(p,completed=False) for p in profiles]))
check('competing palette rejected',not s._prove_ordered_karaoke_completion_sweep([replace(profiles[0],after=('foreign',))]+profiles[1:]))
first=next(group for (pos,word),group in groups.items() if pos==(680.07,82.2))
chosen=next(e for e in first if e.layer=='1')
evidence=s._collect_outline_strip_evidence(chosen,first,context)
source,rect,state=evidence.strips[0]

def reject_transition(name,old,new):
    event=replace(source,text=source.text.replace(old,new))
    check(name,s._profile_outline_strip_transition(event,state) is None)
reject_transition('changing font cannot supply paint',r'\blur15',r'\fs80')
reject_transition('changing alpha cannot supply paint',r'\blur15',r'\3a&HFF&')
reject_transition('a second color change is a reversal',r'\t(81.6,240,',r'\t(81.6,240,\3c&HA100FD&')
reject_transition('unrestored expanded border rejected',r'\bord4.2)',r'\bord12)')
reject_transition('negative acceleration rejected','(80,81.6,','(80,81.6,-1,')
reject_transition('nonfinite timing rejected','(80,81.6,','(nan,81.6,')
reject_transition('negative reversed endpoint remains rejected','(80,81.6,','(80,-1,')
reject_transition('activation after cue rejected','(80,81.6,','(9000,9001,')
reject_transition('unsupported nested transform rejected',r'\blur15',r'\t(0,1,\3c&H000000&)')
reject_transition('later static paint override rejected',r'\t(81.6,240,\blur1.5\bord4.2)',r'\3c&H1300FE&')
check('legacy scroll effects rejected',s._profile_outline_strip_transition(replace(source,effect='Scroll up;0;1080;10'),state) is None)
check('unknown effect annotation is inert',s._profile_outline_strip_transition(replace(source,effect='annotation'),state) is not None)
check('independent geometry pulse may finish beyond cue',s._profile_outline_strip_transition(replace(source,text=source.text.replace('(81.6,240,','(81.6,6000,')),state) is not None)
reject_transition('color transition beyond cue rejected','(80,81.6,','(80,6000,')
for label,change in [('unsynchronized strips',source.text.replace('(80,81.6,','(90,91.6,')),
                     ('inconsistent fade',source.text.replace(r'\fad(200,250)',r'\fad(200,500)'))]:
    altered=replace(source,text=change)
    ev=replace(evidence,strips=((altered,rect,state),)+evidence.strips[1:])
    check(label,s._profile_outline_strip_sweep(chosen,ev,context) is None)
foreground=replace(chosen,text=chosen.text.replace(r'\q2',r'\q2\t(0,100,\c&HFF0000&)'))
sources={**document.events,chosen.source_index:foreground}
check('animated foreground rejected',s._profile_outline_strip_sweep(chosen,evidence,replace(context,source_events=sources)) is None)
check('incomplete strip partition rejected',s._collect_outline_strip_evidence(chosen,[e for e in first if e is not first[40]],context) is None)
check('duplicate strip overlap rejected',s._collect_outline_strip_evidence(chosen,first+[first[40]],context) is None)

before=deepcopy(events)
output,count=s.flatten_stacked_text_copies(events,MappingProxyType(visible),set(document.events),source_events=MappingProxyType(document.events),font_metrics=metric)
top=[e for e in output if s.get_pos(e.text)[1]==82.2]
check('all 11 reduced syllables share completed outline',len(top)==11 and {e.state['3c'] for e in top}=={'2409CF'})
check('input events and maps remain borrowed',events==before)
# An unproved syllable must not leave its neighbors colored independently.
bad_source=replace(source,text=source.text.replace('(80,81.6,','(90,91.6,'))
bad_sources=MappingProxyType({**document.events,source.source_index:bad_source})
bad_output,_=s.flatten_stacked_text_copies(events,MappingProxyType(visible),set(document.events),source_events=bad_sources,font_metrics=metric)
check('one failed family refuses color for the whole row',
      {e.state['3c'] for e in bad_output if s.get_pos(e.text)[1]==82.2}=={'000000'})
reordered,_=s.flatten_stacked_text_copies(list(reversed(events)),MappingProxyType(visible),set(document.events),source_events=context.source_events,font_metrics=metric)
check('event order does not change the completion decision',[e.fields() for e in reordered]==[e.fields() for e in output])

check('pass-local evidence does not leak into formatting',all(not any(k.startswith('_') for k in e.state) for e in output))
row_profiles={e.source_index:p for e,p in zip(sorted(top,key=lambda e:s.get_pos(e.text)[0]),profiles)}
check('missing profile refuses the whole row',s.normalize_karaoke_completion_paint(top,visible,document.events,outline_profiles={k:v for i,(k,v) in enumerate(row_profiles.items()) if i})==top)
check('empty profile map leaves unrelated rows unchanged',s.normalize_karaoke_completion_paint(top,visible,document.events,outline_profiles={})==top)

with tempfile.TemporaryDirectory() as temporary:
    temporary=Path(temporary)
    result=temporary/'v170.ass'
    with contextlib.redirect_stdout(None):s.simplify_ass(fixture,result,s.SimplifyConfig(),font_metrics=metric)
    doc=s._resolve_document_state(s.read_subtitle_document(result))
    rows=[e for e in doc.events.values() if e.kind=='Dialogue']
    check('focused cue preserves its 11 syllables and bottom caption',len(rows)==12)
    check('top completed outline retained',next(e for e in rows if s.get_pos(e.text)[1]==82.2).state['3c']=='2409CF')
    check('bottom static paint unchanged',next(e for e in rows if s.get_pos(e.text)[1]==994.2).state['3c']=='260AC6')
    check('all white foregrounds retained',all(e.state['1c']=='FFFFFF' for e in rows))
    spec=importlib.util.spec_from_file_location('outline_previous',ROOT/'test-data/simplify_ass-v169-reference.py')
    old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
    prior=temporary/'v169.ass'
    with contextlib.redirect_stdout(None):old.simplify_ass(fixture,prior,old.SimplifyConfig(),font_metrics=old.FontMetrics([ROOT/'fonts']))
    a=list(old.read_subtitle_document(prior).events.values());b=list(s.read_subtitle_document(result).events.values())
    check('caption count and all non-text fields unchanged',len(a)==len(b) and all(x.fields()[:-1]==y.fields()[:-1] for x,y in zip(a,b)))
    def render(path,at,size):
        vf=f"format=rgb24,settb=1/1000,setpts=PTS+{at}/TB,subtitles=filename='{path}':fontsdir='{ROOT/'fonts'}'"
        raw=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c=black:s={size[0]}x{size[1]}:r=1000',
            '-vf',vf,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-threads','1','pipe:1'],capture_output=True,check=True).stdout
        return Image.frombytes('RGB',size,raw)
    # Independent renderer evidence for the nonstandard timing encountered here.
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 180
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00A100FD,&H00000000,0,0,0,0,100,100,0,0,1,6,0,5,0,0,0,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
    paths={}
    for label,tags in [('reversed',r'\t(470,250,\3c&H1300FE&)'),('instant',r'\t(470,470,\3c&H1300FE&)'),('purple',''),('red',r'\3c&H1300FE&')]:
        path=temporary/(label+'.ass');path.write_text(header+'Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\pos(320,90)'+tags+'}Timing\n');paths[label]=path
    purple=render(paths['purple'],0,(640,180)).tobytes();red=render(paths['red'],0,(640,180)).tobytes()
    timing=[]
    for at in [0,.249,.25,.251,.469,.47,.471,.6,1]:
        actual=render(paths['reversed'],at,(640,180)).tobytes()
        check('libass reversed matches instant at '+str(at),actual==render(paths['instant'],at,(640,180)).tobytes())
        check('libass correct activation side at '+str(at),actual==(purple if at<=.47 else red))
        timing.append(dict(at=at,instant_equivalent=True,completed=at>.47))
    montage=Image.new('RGB',(1920,510),(24,24,24));draw=ImageDraw.Draw(montage)
    for i,(label,path) in enumerate((('Original after the color sweep',fixture),('v169 black outline',prior),('v170 completed red outline',result))):
        picture=render(path,1340,(1920,1080)).crop((0,0,1920,150))
        draw.text((12,i*170+3),label,fill='white');montage.paste(picture,(0,i*170+20))
        if i==2:check('rendered top outline has red pixels',sum(r>60 and r>2*g and r>2*b for r,g,b in picture.getdata())>100)
    montage.save(ROOT/'validation/outline-karaoke-comparison.png')

def definitions(path):return {n.name:n for n in executable_ast(ast.parse(path.read_text())).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a=definitions(ROOT/'test-data/simplify_ass-v169-reference.py');b=definitions(ROOT/'test-data/simplify_ass-v170-reference.py')
changed={k for k in a if ast.dump(a[k])!=ast.dump(b[k])}
added=set(b)-set(a)
check('bounded production definition changes',changed=={'_representative_static_strip_outline','_render_stacked_text_caption','_flatten_stacked_text_group','flatten_stacked_text_copies','normalize_karaoke_completion_paint'} and added=={'OutlineStripEvidence','_collect_outline_strip_evidence','_average_outline_strip_color','_profile_outline_strip_transition','_profile_outline_strip_sweep'} and not set(a)-set(b))
(ROOT/'validation/outline-karaoke-checks.json').write_text(json.dumps(dict(version=s.__version__,checks_passed=len(checks),checks=checks,libass_timing=timing,changed_definitions=sorted(changed),new_definitions=sorted(added)),indent=2)+'\n')
print(len(checks),'outline karaoke checks passed; 9 pixel-identical reversed/instant comparisons; completed red outline rendered')
