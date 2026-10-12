#!/usr/bin/env python3
"""Prove sustained layout priority and conservative touching-phase recovery."""
from pathlib import Path
import tempfile,json,math
import simplify_ass as s
ROOT=Path(__file__).resolve().parent
header=(ROOT/'test-data/Overlord-22m06-source.ass').read_text(encoding='utf-8-sig').split('Dialogue:',1)[0]
checks=[]
def ok(name,value):
    assert value,name
    checks.append(name)
def near(a,b):return abs(a-b)<1e-5
def freeze(tags,duration=1,enabled=True):
    return s.freeze_block(tags,duration,s.DEFAULT_STATE,s.DEFAULT_STATE,{},0,prefer_upright=enabled).selection
def event(tags,start=1,end=1.37,word='k',name='',layer='4'):
    return f'Dialogue: {layer},{s.format_time(start)},{s.format_time(end)},ED-R,{name},0,0,0,,{{{tags}}}{word}\n'
def load(parts):
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'source.ass';path.write_text(header+''.join(parts))
        return s.load_subtitle_events(path)[1]
def early(events):
    result=[]
    for e in events:
        body,word,drawing=s.simplify_visual_text(e.text,0,e.duration,e.defaults,e.styles,1,upright_crossings=False)
        result.append(s.replace_event(e,text=body))
    return result
motion=r'\move(100,50,100,100,0,100)\frz0\t(0,100,\frz20)\t(100,1000,\frz40)'
selected=freeze(motion)
st=selected.state
ok('own position hold wins over first upright instant',st['pos']==(100.,100.) and st['frz']==0)
ok('position hold is recorded separately from orientation',dict(selected.pose.sustained_geometry)['pos']==(100.,100.))
size=r'\pos(100,100)\fs20\fscx100\fscy100\frz0\t(0,100,\fs60\fscx120\fscy130\frz20)\t(100,1000,\frz40)'
selected=freeze(size)
st=selected.state
ok('held font size wins',st['fs']==60)
ok('held scales remain paired',st['fscx']==120 and st['fscy']==130)
ok('held sizing does not prevent upright orientation',st['frz']==0)
colored=motion+r'\t(200,300,\1c&H0000FF&)\t(400,500,\1c&H00FF00&)\t(600,700,\1c&HFF0000&)'
selected=freeze(colored)
st=selected.state
ok('colour subdivisions accumulate one position hold',st['pos']==(100.,100.))
ok('legacy non-upright freezing remains unchanged',freeze(motion,enabled=False).state['frz']!=0)
# With no sustained position, use the coherent actual upright pose as fallback.
fallback=r'\move(100,50,100,100,0,1000)\frz0\t(0,1000,\frz40)'
selected=freeze(fallback)
st=selected.state
ok('no positional hold retains crossing fallback',st['pos']==(100.,50.) and st['frz']==0)
ok('moving path does not acquire a held position', 'pos' not in dict(selected.pose.sustained_geometry or ()))
# Two equally long stationary poses do not prove one preferred position.
tied=s.select_static_state({**s.DEFAULT_STATE,'pos':(100.,50.)},[(500,500,1,[('pos','(100,100)')])],{0,500,1000},{},s.DEFAULT_STATE,prefer_upright=True)
ok('equal holds remain ambiguous','pos' not in dict(tied.pose.sustained_geometry or ()))
short=freeze(motion,.2)
ok('short constant sizing is not called sustained',short.pose.sustained_geometry is None)
hidden=freeze(r'\pos(100,50)\1a&HFF&\3a&HFF&\4a&H00&\shad0\frz0\t(0,1000,\frz40)')
ok('unused opaque shadow does not prove visible geometry',hidden.pose.sustained_geometry is None)
# Geometry priority applies when the upright detector actually resolves a pose.
# Decorative glyphs without a usable upright pose retain their existing freeze.
particle=(r'\pos(100,50)\fscx20\fscy20\t(0,150,\fscx100\fscy100)'
          r'\t(2660,2810,\fscx20\fscy20)\frz47\frx-77\fry274'
          r'\t(0,350,\frx0\fry0)\t(350,2460,\frz35)'
          r'\t(2460,2810,\frz47\frx-77\fry274)')
selected=freeze(particle,2.81)
st=selected.state
legacy=freeze(particle,2.81,enabled=False).state
ok('unresolved rotated decoration keeps its existing size',st['fscx']==legacy['fscx'] and st['fscy']==legacy['fscy'])
ok('unresolved rotation does not acquire protected geometry',selected.pose.sustained_geometry is None)
selected=s.freeze_block(size,1,s.DEFAULT_STATE,s.DEFAULT_STATE,{},0,prefer_upright=True,upright_crossings=False).selection
st=selected.state
ok('deferred detector does not alter earlier frozen geometry',selected.pose.sustained_geometry is None)
# A touching source hold fixes the incomplete 380 ms/370 ms bounce.
bounce=r'\an5\bord1.5\1c&H123456&\3c&H172639&\move(1175,68,1175,78,0,380)\t(0,126.66666666667,0.7,\frz-4)\t(126.66666666667,380,\frz0\fsp0)'
hold=r'\an5\pos(1175,78)\bord1.5\1c&HABCDEF&\frz0\fsp0\fad(0,120)'
parts=[event(bounce),event(hold,1.37,3.87,layer='3')]
a=load(parts);src={e.source_index:e for e in a};before=early(a);after=s.prefer_surviving_upright_poses(before,src)
ok('touching hold restores y78',s.get_pos(after[0].text)==(1175.,78.))
ok('stationary successor stays unchanged',after[1].fields()==before[1].fields())
ok('recovered geometry keeps current colour',after[0].state['1c']==before[0].state['1c'])
ok('recovery keeps times',[(e.start,e.end) for e in before]==[(e.start,e.end) for e in after])
ok('recovery keeps source layers',[e.layer for e in before]==[e.layer for e in after])
ok('recovery is idempotent',[e.fields() for e in after]==[e.fields() for e in s.prefer_surviving_upright_poses(after,src)])
# Endpoint sizing can be recovered by the same evidence, not by a zero-angle start.
zoom=bounce.replace(r'\move(1175,68,1175,78,0,380)',r'\pos(1175,78)\fs20\t(0,380,\fs66)')
a=load([event(zoom),event(hold,1.37,3.87,layer='3')]);after=s.prefer_surviving_upright_poses(early(a),{e.source_index:e for e in a})
ok('adjacent hold restores endpoint font size',after[0].state['fs']==66)
# Reject evidence that is weak, unrelated, animated, invisible or ambiguous.
for label,parts in [
    ('non-touching',[event(bounce),event(hold,1.50,4,layer='3')]),
    ('different letter',[event(bounce),event(hold,1.37,3.87,word='a',layer='3')]),
    ('different actor',[event(bounce),event(hold,1.37,3.87,name='other',layer='3')]),
    ('different position',[event(bounce),event(hold.replace('1175,78','1201,78'),1.37,3.87,layer='3')]),
    ('different font',[event(bounce),event(hold+r'\fnArial',1.37,3.87,layer='3')]),
    ('short hold',[event(bounce),event(hold,1.37,1.87,layer='3')]),
    ('moving hold',[event(bounce),event(hold+r'\move(1175,78,1175,100)',1.37,3.87,layer='3')]),
    ('hidden hold',[event(bounce),event(hold+r'\1a&HFF&\3a&HFF&\4a&HFF&',1.37,3.87,layer='3')]),
    ('fade-hidden hold',[event(bounce),event(hold+r'\t(0,100,\1a&HFF&)',1.37,3.87,layer='3')]),
    ('fully faded hold',[event(bounce),event(hold.replace('fad(0,120)','fad(0,2400)'),1.37,3.87,layer='3')]),
    ('clipped hold',[event(bounce),event(hold+r'\clip(0,0,10,10)',1.37,3.87,layer='3')]),
    ('clipped transition',[event(bounce+r'\clip(0,0,10,10)'),event(hold,1.37,3.87,layer='3')]),
    ('two conflicting holds',[event(bounce),event(hold,1.37,3.87,layer='3'),event(hold.replace('1175,78','1175,77.5'),1.37,4,layer='3')]),
]:
    a=load(parts);proof=s.adjacent_sustained_geometry({e.source_index:e for e in a},[a[0]])
    ok(label+' cannot supply geometry',not proof)
# Previous holds can support an exit; genuine holds inside a cue have priority.
a=load([event(hold.replace('1175,78','1175,68'),0,1,layer='3'),event(bounce)])
proof=s.adjacent_sustained_geometry({e.source_index:e for e in a},[a[1]])
ok('previous sustained pose supports exit',proof[a[1].source_index]['pos']==(1175.,68.))
longmotion=bounce.replace('0,380','0,100').replace('126.66666666667','33.33333333333').replace('380,','2000,')
a=load([event(hold.replace('1175,78','1175,68'),0,5,layer='3'),event(longmotion,5,7)])
after=s.prefer_surviving_upright_poses(early(a),{e.source_index:e for e in a})
ok('own hold outranks adjacent starting pose',s.get_pos(after[1].text)==(1175.,78.))
# Actual regression fixture, not synthetic coordinates alone.
original=s.load_subtitle_events(ROOT/'test-data/Overlord-22m06-source.ass')[1]
phase=[e for e in original if e.kind=='Dialogue' and e.style=='ED-R' and abs(e.start_s-1325.85)<.001 and s.simplify_text(e.text,visible_only=True)[1] in ('k','a')]
after=s.prefer_surviving_upright_poses(early(phase),{e.source_index:e for e in original})
for e in after:
    word=s.simplify_text(e.text,visible_only=True)[1]
    ok('actual '+word+' y78 '+str(e.source_index),near(s.get_pos(e.text)[1],78))
    ok('actual '+word+' upright '+str(e.source_index),s.unrotated_text_state(e.state))
(ROOT/'validation/upright-priority-checks.json').write_text(json.dumps({'version':s.__version__,'checks_passed':len(checks),'checks':checks},indent=2)+'\n')
print(len(checks),'upright-priority checks passed')
