"""Bounded dither palettes, gradient protection and unchanged real song paint."""
import test_paths
from pathlib import Path
from copy import deepcopy
import ast
import hashlib
import json
import tempfile
import subprocess
from unittest.mock import patch
from PIL import Image, ImageChops
import simplify_ass as s
from executable_ast_audit import executable_ast

ROOT = Path(__file__).resolve().parents[1]
checks = []


def check(name, value):
    assert value, name
    checks.append(name)


HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Outline, Shadow, Alignment
Style: Default,Arial,24,&H00FFFFFF,&H00101010,2,0,5
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def event(text, start=1, end=3, style='Default', effect=''):
    source = HEADER + f'Dialogue: 0,{s.format_time(start)},{s.format_time(end)},{style},,0,0,0,{effect},{text}\n'
    return next(iter(s._resolve_document_state(s.parse_subtitle_document(source)).events.values()))


def colors(event, channel):
    obj = s.static_object_key(event, event.styles, allow_unpositioned=True)
    return [dict(sig.formatting)[f'{channel}c'] for sig, draw, text in obj[-1]
            if not draw and text.strip()]


es = [event('Caption',1,3), event(r'{\c&HFDFDFD&\3c&H121212&}Caption',4,6), event('Caption',7,9)]
before = deepcopy(es)
out, count = s.normalize_near_text_colors(es)
check('two-level caption fill/outline noise normalized', count == 1 and
      all(set(colors(e,1)) == {'FFFFFF'} and set(colors(e,3)) == {'101010'} for e in out))
check('redundant leading color overrides removed', out[1].text == 'Caption')
check('borrowed events and styles preserved', [vars(e) for e in es] == [vars(e) for e in before])
check('all event fields except text retained', all(a.fields()[:-1] == b.fields()[:-1] for a,b in zip(es,out)))
check('second normalization byte-idempotent', s.normalize_near_text_colors(out) == (out, 0))

for delta, accepted in [(1, True), (2, True), (3, False)]:
    color = f'{255-delta:02X}' * 3
    es = [event('dominant', 1, 3), event('{\\1c&H'+color+'&}variant', 4, 5)]
    result, n = s.normalize_near_text_colors(es)
    check('full palette bound '+str(delta), bool(n) == accepted)
    if accepted:
        check('literal, timing and layer preserved '+str(delta),
              all(a.fields()[:-1] == b.fields()[:-1] and
                  s.OVERRIDE_RE.sub('', a.text) == s.OVERRIDE_RE.sub('', b.text)
                  for a, b in zip(es, result)))
        reverse, _ = s.normalize_near_text_colors(list(reversed(es)))
        check('input order independent '+str(delta), [e.text for e in result] ==
              [e.text for e in reversed(reverse)])

for name, es in [
    ('bounded neighbor chain does not accumulate', [event('{\\c&H'+f'{c:02X}'*3+'&}X') for c in (10,12,14,16)]),
    ('large intentional gradient', [event(r'A{\c&HDEC7F6&}B{\c&HA9FFC8&}C')]),
    ('wide outline gradient', [event(r'A{\3c&H202020&}B{\3c&H303030&}C')]),
    ('gradient split over events', [event(r'{\c&HE2C3FA&}A'), event(r'{\c&HA9FFC8&}B')]),
]:
    result, n = s.normalize_near_text_colors(es)
    check('preserve '+name, n == 0 and all(a is b for a, b in zip(es, result)))

for name, text, channel in [
    ('alternating inline fill', r'A{\c&HFDFDFD&}B{\c&HFFFFFF&}C', 1),
    ('tiny ordered fill ramp', r'A{\c&HFEFEFE&}B{\c&HFDFDFD&}C', 1),
    ('two-color fill ramp', r'A{\c&HFDFDFD&}B', 1),
    ('tiny ordered outline ramp', r'A{\3c&H111111&}B{\3c&H121212&}C', 3),
]:
    original = event(text)
    snapshot = deepcopy(original)
    result, n = s.normalize_near_text_colors([original])
    check('normalize '+name, n == 1 and len(set(colors(result[0], channel))) == 1)
    check('preserve text timing and formatting '+name,
          s.OVERRIDE_RE.sub('', result[0].text) == s.OVERRIDE_RE.sub('', text) and
          result[0].fields()[:-1] == original.fields()[:-1] and vars(original) == vars(snapshot))
    check('inline normalization idempotent '+name,
          s.normalize_near_text_colors(result) == (result, 0))

es = [event(r'A{\c&HFDFDFD&}B{\c&HFFFFFF&}C'), event(r'{\c&H000000&}Different paint')]
result, n = s.normalize_near_text_colors(es)
check('wide complete style palette vetoes tiny inline variation', n == 0 and result == es)

for tag in (r'\t(0,100,\c&HFDFDFD&)', r'\k20', r'\fad(100,0)', r'\move(1,1,2,2)'):
    es = [event('ABC'), event('{'+tag+r'\c&HFDFDFD&}X')]
    result, n = s.normalize_near_text_colors(es)
    check('animated family veto '+tag, n == 0 and result == es)

e = event(r'{\c&HFDFDFD&}A{\rDefault\i1\c&HFDFDFD&}B')
es = [event('Long representative caption'), e]
out, n = s.normalize_near_text_colors(es)
check('reset and italic formatting retained', n == 1 and r'\rDefault\i1' in out[1].text
      and out[1].state['i'] == 1 and set(colors(out[1],1)) == {'FFFFFF'})
e = event(r'{\alpha&H80&\c&HFDFDFD&}Caption')
out, n = s.normalize_near_text_colors([event('Long representative caption'),e])
check('alpha untouched', n == 1 and out[1].state['1a'] == 128)
e = event(r'{\1a&HFF&\c&HFDFDFD&}Caption')
out, n = s.normalize_near_text_colors([event('Long representative caption'),e])
check('invisible fill not normalized', n == 0 and out[1] is e)

# Real v177 outputs contain both complete song lines and retained gradients.
for name, styles in [('Attack-on-Titan-S02E01-track3', {'OP-R','OP-E','ED-R'}),
                     ('DemonSlayer-S04E02', {'ED - ENG','ED - Romaji'})]:
    path = ROOT/'validation/migration-corpus/windows'/(name+'-v177.ass')
    if not path.is_file():
        # These verified baseline outputs are also supplied in the snapshot.
        path = ROOT/'outputs'/('Attack-on-Titan-S02E01-track3-v177.ass' if
                              name.startswith('Attack') else 'DemonSlayer-S04E02.ass')
    es = [e for e in s.load_subtitle_events(path)[1] if e.style in styles]
    check('real fixture contains selected lyrics '+name, bool(es))
    result, n = s.normalize_near_text_colors(es)
    check('real lyric paint byte-identical '+name, n == 0 and
          [e.fields() for e in result] == [e.fields() for e in es])
    if name.startswith('Demon'):
        check('real gradient fixture has many intentional steps',
              len({c for e in es for c in colors(e, 1)}) > 30)

with tempfile.TemporaryDirectory() as folder:
    def render(event, name):
        path = Path(folder)/(name+'.ass')
        path.write_text(HEADER+'Dialogue: '+','.join(event.fields())+'\n')
        result = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
            'color=c=gray:s=640x360:r=1', '-vf',
            f'format=rgb24,setpts=PTS+2/TB,ass=filename={path}:fontsdir={ROOT/"fonts"}',
            '-frames:v', '1', '-threads', '1', '-f', 'rawvideo', '-pix_fmt',
            'rgb24', 'pipe:1'], capture_output=True, check=True)
        return Image.frombytes('RGB', (640,360), result.stdout)
    noisy = event(r'{\c&HFDFDFD&\3c&H121212&}ABC')
    normalized = s.normalize_near_text_colors([event('Long representative caption'),noisy])[0][1]
    difference = ImageChops.difference(render(noisy, 'noise'), render(normalized, 'normalized'))
    check('rendered dither change bounded by two RGB levels '+str(difference.getextrema()),
          0 < max(hi for lo, hi in difference.getextrema()) <= 2)
    inline = event(r'A{\c&HFDFDFD&\3c&H121212&}B{\c&HFFFFFF&\3c&H101010&}C')
    normalized, n = s.normalize_near_text_colors([inline])
    check('inline fill and outline reduced to inherited colors', n == 1 and normalized[0].text == 'ABC')
    original_frame = render(inline, 'inline')
    normalized_frame = render(normalized[0], 'inline-normalized')
    difference = ImageChops.difference(original_frame, normalized_frame)
    check('inline run merging permits outline-compositing changes',
          max(hi for lo, hi in difference.getextrema()) > 2)
    check('normalized inline render equals uniform-caption render',
          ImageChops.difference(normalized_frame, render(event('ABC'), 'uniform')).getbbox() is None)
    gradient = event(r'A{\c&HDEC7F6&}B{\c&HA9FFC8&}C')
    retained = s.normalize_near_text_colors([gradient])[0][0]
    check('rendered intentional gradient pixel-identical',
          ImageChops.difference(render(gradient, 'gradient'), render(retained, 'retained')).getbbox() is None)

with tempfile.TemporaryDirectory() as folder:
    source = Path(folder)/'source.ass'
    output = Path(folder)/'output.ass'
    again = Path(folder)/'again.ass'
    source.write_text(HEADER + 'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Long representative caption\nDialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,{\\c&HFDFDFD&}Caption\n')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    stats = s.simplify_ass(source, output, s.SimplifyConfig())
    check('pipeline reports a normalized event', stats['text_colors_normalized'] == 1)
    check('pipeline source untouched', hashlib.sha256(source.read_bytes()).hexdigest() == digest)
    s.simplify_ass(output, again, s.SimplifyConfig())
    check('pipeline output byte-idempotent', output.read_bytes() == again.read_bytes())
    with patch.object(s, 'normalize_near_text_colors', wraps=s.normalize_near_text_colors) as normalize:
        s.simplify_ass(source, Path(folder)/'legacy.ass', s.SimplifyConfig(level=2))
        check('legacy path does not invoke new pass', normalize.call_count == 0)
    source.write_text(HEADER + 'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,A{\\c&HFDFDFD&}B{\\c&HFFFFFF&}C\n')
    source_bytes = source.read_bytes()
    stats = s.simplify_ass(source, output, s.SimplifyConfig())
    actual = s.load_subtitle_events(output)[1]
    check('full pipeline normalizes retained inline colors',
          stats['text_colors_normalized'] == 1 and len(actual) == 1 and
          s.OVERRIDE_RE.sub('', actual[0].text) == 'ABC' and
          set(colors(actual[0], 1)) == {'FFFFFF'})
    check('inline pipeline keeps source bytes', source.read_bytes() == source_bytes)
    s.simplify_ass(output, again, s.SimplifyConfig())
    check('inline pipeline byte-idempotent', output.read_bytes() == again.read_bytes())

def definitions(path):
    return {n.name: n for n in executable_ast(ast.parse(path.read_text())).body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
a = definitions(ROOT/'tests/references/simplify_ass_v177.py')
b = definitions(ROOT/'simplify_ass.py')
check('only one production helper added', set(b)-set(a) == {'normalize_near_text_colors'} and not set(a)-set(b))
check('integration confined to final pipeline', {k for k in a if ast.dump(a[k]) != ast.dump(b[k])} == {'simplify_ass'})
(ROOT/'validation/color-normalization-checks.json').write_text(json.dumps(dict(
    version=s.__version__, runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest(),
    checks_passed=len(checks), checks=checks), indent=2)+'\n')
print(len(checks), 'color normalization checks passed')
