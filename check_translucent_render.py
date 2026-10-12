"""Verify preserved paint accumulation with real FFmpeg/libass renders."""
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
data = runpy.run_path(str(root / 'check_translucent_duplicates.py'))
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

    for i in range(len(data['pipeline_cases'])):
        source = root / 'validation' / f'translucent-source-{i}.ass'
        before = render(source, temporary / 'source.png')
        for level in (1, 2):
            fixed = root / 'validation' / f'translucent-level{level}-{i}.ass'
            after = render(fixed, temporary / 'fixed.png')
            assert before.tobytes() == after.tobytes(), (i, level)
            results.append({'case': i, 'level': level, 'pixel_identical': True})
            if i == 0 and level == 1:
                before.save(root / 'validation' / 'translucent-source.png')
                after.save(root / 'validation' / 'translucent-fixed.png')

    # Optional adjacent baseline checkout reproduces the reported dimming.
    baseline = root / 'test-data' / 'simplify_ass-v104-reference.py'
    brightness = {}
    if baseline.is_file():
        spec = importlib.util.spec_from_file_location('translucent_baseline104', baseline)
        old = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = old
        spec.loader.exec_module(old)
        source = root / 'validation' / 'translucent-source-0.ass'
        old_output = root / 'validation' / 'translucent-v104.ass'
        with contextlib.redirect_stdout(io.StringIO()):
            old.simplify_ass(source, old_output, old.SimplifyConfig(), font_spacing=None)
        old_image = render(old_output, root / 'validation' / 'translucent-v104.png')
        source_image = Image.open(root / 'validation' / 'translucent-source.png').convert('RGB')
        fixed_image = Image.open(root / 'validation' / 'translucent-fixed.png').convert('RGB')
        for label, im in [('source', source_image), ('v104', old_image), ('v105', fixed_image)]:
            brightness[label] = max(channel[1] for channel in im.getextrema())
        assert brightness['source'] == brightness['v105'] > brightness['v104']
        montage = Image.new('RGB', (640*3, 390))
        draw = ImageDraw.Draw(montage)
        for i, (label, im) in enumerate([('Source', source_image), ('v104', old_image), ('v105', fixed_image)]):
            montage.paste(im, (i*640, 30))
            draw.text((i*640+12, 10), label, fill='white')
        montage.save(root / 'validation' / 'translucent-comparison.png')

(root / 'validation' / 'translucent-render-check.json').write_text(
    json.dumps({'version': data['s'].__version__, 'checks': len(results),
                'results': results, 'maximum_pixel_brightness': brightness}, indent=2) + '\n')
print(len(results), 'pixel-identical translucent render comparisons passed')
if brightness:
    print('Maximum brightness:', brightness)
