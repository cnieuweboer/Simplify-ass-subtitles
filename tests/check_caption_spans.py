#!/usr/bin/env python3
"""Check character paint, literal spacing, and border/shadow span resets."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import json
import tempfile
import simplify_ass as s

ROOT = Path(__file__).resolve().parents[1]
header = (ROOT/'test-data/Overlord-22m06-source.ass').read_text(
    encoding='utf-8-sig').split('Dialogue:',1)[0]
checks = []

def ok(name,condition):
    assert condition,name
    checks.append(name)

def load(tags):
    lines = [f'Dialogue: 0,0:00:01.00,0:00:03.00,ED-R,,0,0,0,,{{\\an5\\pos({100+30*i},78){tag}}}{c}'
             for i,(tag,c) in enumerate(zip(tags,'abcd'))]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'input.ass'
        path.write_text(header+'\n'.join(lines)+'\n',encoding='utf-8')
        return s.load_subtitle_events(path)[1]

def glyph_states(body,event):
    state = event.defaults.copy()
    continuation = s.OverrideContinuation()
    glyphs = []
    for part in s.re.split(r'(\{[^}]*\})',body):
        if part.startswith('{'):
            for tag,value in s.tokenize_override(part[1:-1]):
                continuation = s.apply_override(state,tag,value,event.styles,event.defaults,continuation)
        else:
            glyphs.extend((char,state.copy()) for char in part if not char.isspace())
    return glyphs

def paint(state):
    keys = ('1c','2c','3c','4c','1a','2a','3a','4a','blur','be')
    return (tuple(state.get(k,s.DEFAULT_STATE.get(k,0)) for k in keys),
            tuple(state.get(k,state[k[1:]]) for k in ('xbord','ybord','xshad','yshad')))

def render(events,text=' ab  c d ',**policy):
    return s.render_merged_caption(events,list('abcd'),text,an=5,pos=(160,78),
                                   fscx=105,fscy=110,fsp=1.25,**policy)

# A base override clears axis overrides. The next fragment must restore its
# axes even when they match the preceding fragment's explicit axis values.
common = (r'\1c&H112233&\2c&H234567&\3c&H765432&\4c&H456789&'
          r'\1a&H10&\2a&H20&\3a&H30&\4a&H40&\blur1\be2')
tags = [common+r'\bord2\xbord6\ybord7\shad2\xshad-3\yshad4',
        common+r'\bord3\xbord6\ybord7\shad3\xshad-3\yshad4',
        r'\1c&HABCDEF&\3a&H60&\bord4\shad5',
        common+r'\bord2\xbord6\ybord7\shad2\xshad-3\yshad4']
events = load(tags)
body = render(events,animated=False,preserve_paint=True)
ok('exact paint row renders',body is not None)
ok('recovered whitespace remains literal',s.OVERRIDE_RE.sub('',body)==' ab  c d ')
glyphs = glyph_states(body,events[0])
ok('no missing or repeated letters',''.join(c for c,state in glyphs)=='abcd')
for (char,state),source in zip(glyphs,events):
    ok(char+' keeps all color, alpha, border and shadow channels',paint(state)==paint(source.state))
    ok(char+' keeps recovered placement and scale',state['pos']==(160.,78.) and
       state['an']==5 and state['fscx']==105 and state['fscy']==110)
    ok(char+' keeps tracking and disables wrapping',state['fsp']==1.25 and state['q']==2)
ok('unmatched recovered characters reject exact spans',
   render(events,text='abXd',animated=False,preserve_paint=True) is None)

# Animated rows retain their established simplified paint/decorations policy.
events = load([r'\1c&H112233&\b1',r'\1c&HABCDEF&\i1',
               r'\1c&H224466&\u1',r'\1c&HFFFFFF&\s1'])
body = render(events,animated=True)
ok('animated recovered whitespace remains literal',s.OVERRIDE_RE.sub('',body)==' ab  c d ')
for (char,state),source in zip(glyph_states(body,events[0]),events):
    expected = s.effective_state(s.render_simplified_caption(source.state,char,source_paint=s._source_caption_paint(source.state,[source.state])),source.defaults,source.styles)
    ok(char+' keeps simplified color and decorations',all(state[k]==expected[k]
       for k in ('b','i','u','s','1c','3c','3a','bord')))
ok('unmatched recovered characters reject animated spans',
   render(events,text='abXd',animated=True) is None)

# Equal-paint static rows use only the shared header and literal text.
events = load([r'\1c&H123456&']*4)
body = render(events,animated=False)
ok('equal paint static row has no redundant span blocks',len(s.OVERRIDE_RE.findall(body))==1)
ok('equal paint static row preserves literal spaces',s.OVERRIDE_RE.sub('',body)==' ab  c d ')
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation/caption-span-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(f'{len(checks)} caption-span checks passed')
