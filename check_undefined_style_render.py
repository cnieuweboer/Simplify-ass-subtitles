"""Verify fallback-style formatting against actual FFmpeg/libass renders."""
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import runpy
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent
data = runpy.run_path(str(root / 'check_undefined_styles.py'))
fonts = (root / 'fonts').resolve()
results = []

with tempfile.TemporaryDirectory() as temporary:
    temporary = Path(temporary)

    def render(ass, png):
        vf = (f"settb=1/1000,setpts=PTS+2/TB,"
              f"subtitles=filename='{ass.resolve()}':fontsdir='{fonts}'")
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=black:s=640x360:r=1',
                        '-vf', vf, '-frames:v', '1', '-y', str(png)],
                       check=True, capture_output=True)
        return Image.open(png).convert('RGB')

    for i, case in enumerate(data['cases']):
        source = root / 'validation' / f'undefined-source-{i}.ass'
        before = render(source, temporary / 'source.png')
        for level in (1, 2):
            fixed = root / 'validation' / f'undefined-level{level}-{i}.ass'
            after = render(fixed, temporary / 'fixed.png')
            assert before.tobytes() == after.tobytes(), (case[0], level)
            results.append({'case': case[0], 'level': level, 'pixel_identical': True})
            if i == 0 and level == 1:
                before.save(root / 'validation' / 'undefined-style-source.png')
                after.save(root / 'validation' / 'undefined-style-fixed.png')

    baseline = root / 'test-data' / 'simplify_ass-v105-reference.py'
    widths = {}
    if baseline.is_file():
        spec = importlib.util.spec_from_file_location('undefined_baseline105', baseline)
        old = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = old
        spec.loader.exec_module(old)
        source = root / 'validation' / 'undefined-source-0.ass'
        old_output = root / 'validation' / 'undefined-style-v105.ass'
        with contextlib.redirect_stdout(io.StringIO()):
            old.simplify_ass(source, old_output, old.SimplifyConfig(), font_spacing=None)
        old_image = render(old_output, root / 'validation' / 'undefined-style-v105.png')
        source_image = Image.open(root / 'validation' / 'undefined-style-source.png').convert('RGB')
        fixed_image = Image.open(root / 'validation' / 'undefined-style-fixed.png').convert('RGB')
        montage = Image.new('RGB', (640*3, 390))
        draw = ImageDraw.Draw(montage)
        for i, (label, im) in enumerate([('Source', source_image), ('v105', old_image), ('v106', fixed_image)]):
            bounds = im.getbbox()
            widths[label] = bounds[2]-bounds[0]
            montage.paste(im, (i*640, 30))
            draw.text((i*640+12, 10), label, fill='white')
        assert widths['Source'] == widths['v106'] != widths['v105']
        montage.save(root / 'validation' / 'undefined-style-comparison.png')

(root / 'validation' / 'undefined-style-render-check.json').write_text(
    json.dumps({'version': data['s'].__version__, 'checks': len(results),
                'results': results, 'reviewed_fixture_widths': widths}, indent=2) + '\n')
print(len(results), 'pixel-identical undefined-style render comparisons passed')
if widths:
    print('Reviewed fixture widths:', widths)
