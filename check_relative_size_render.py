"""Verify font-size geometry against actual FFmpeg/libass rendering."""
from pathlib import Path
import json
import runpy
import subprocess
import tempfile

from PIL import Image

root = Path(__file__).resolve().parent
data = runpy.run_path(str(root / 'check_relative_font_size.py'))
s, header = data['s'], data['header']
styles = s.parse_styles(header.splitlines())
default = styles['Default']
fonts = (root / 'fonts').resolve()
results = []

with tempfile.TemporaryDirectory() as temporary:
    temporary = Path(temporary)

    def render(ass, png, at):
        vf = (f"settb=1/1000,setpts=PTS+{at}/TB,"
              f"subtitles=filename='{ass.resolve()}':fontsdir='{fonts}'")
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=black:s=640x360:r=1',
                        '-vf', vf, '-frames:v', '1', '-y', str(png)],
                       check=True, capture_output=True)
        return Image.open(png).convert('RGB')

    # Compare the full converted fixture against its original, cue by cue.
    source = root / 'validation' / 'relative-size-source.ass'
    fixed = root / 'validation' / 'relative-size-v104.ass'
    for i in range(len(data['static_cases']) + 1):
        at = 2 + 4*i
        before_path, after_path = temporary / 'before.png', temporary / 'after.png'
        before, after = render(source, before_path, at), render(fixed, after_path, at)
        assert before.tobytes() == after.tobytes(), ('static', i)
        results.append({'type': 'static', 'case': i, 'pixel_identical': True})
        if i == 0:
            before.save(root / 'validation' / 'relative-size-source.png')
            after.save(root / 'validation' / 'relative-size-fixed.png')

    # Mid-animation snapshots verify ordered interpolation independently of
    # the script's static representative-pose selection.
    for i, (changes, _, _) in enumerate(data['transform_cases']):
        if any(name != 'fs' and name != 'r' for name, _ in changes):
            continue
        transforms = [(100, 1100, 1, changes)]
        state = s.sample_transform_state(default, transforms, 600, styles, default).formatting
        animated = ''.join('\\' + name + value for name, value in changes)
        for label, tags in [('source', r'\t(100,1100,' + animated + ')'),
                            ('snapshot', s.render_tag('fs', state['fs']))]:
            (temporary / f'{label}.ass').write_text(
                header + 'Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,'
                + r'{\pos(320,180)' + tags + '}Relative size\n')
        before = render(temporary / 'source.ass', temporary / 'before.png', 1.6)
        after = render(temporary / 'snapshot.ass', temporary / 'after.png', 1.6)
        assert before.tobytes() == after.tobytes(), ('transform', i, state['fs'])
        results.append({'type': 'transform_midpoint', 'case': i, 'pixel_identical': True})

(root / 'validation' / 'relative-size-render-check.json').write_text(
    json.dumps({'version': s.__version__, 'checks': len(results), 'results': results}, indent=2) + '\n')
print(len(results), 'pixel-identical libass render comparisons passed')
