"""Generate plausible lyric-copy experiments; compare complete on/off pipelines.

This is a policy investigation, not a claim that the current matcher is correct.
Oracle violations are reported separately from harness assertions. Run through
run_backend_check.py so conversions use the usual Windows font backend.
"""
from pathlib import Path
from unittest.mock import patch
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import simplify_ass as s
from PIL import Image, ImageChops, ImageDraw

DEST = ROOT / 'validation/lyric-layer-niche' / s.__version__
DEST.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'tests'))
from lyric_layer_fixtures import FONT, OTHER_FONT, TEXT, HEADER, make_case as build_case
metrics = s.FontMetrics([ROOT / 'fonts'])
required = [(FONT, 0, False), (OTHER_FONT, -1, False)]
for family, bold, italic in required:
    assert metrics.matching_face(family, bold, italic) is not None, ('Missing exact font', family, bold, italic)


def make_case(name, **options):
    return build_case(name, metrics, DEST, **options)


cases = [make_case('letters-offset-' + str(offset), offset=offset) for offset in (.1, .5, 1, 2, 4, 12)]
cases += [make_case('words', pieces='words'), make_case('syllables', pieces='syllables'),
          make_case('ordinary-full-line', ordinary=True),
          make_case('equal-timing', fragment_time=(1, 4)),
          make_case('one-centisecond-inset', fragment_time=(1.01, 3.99)),
          make_case('fragment-entrance', fragment_time=(.9, 3.9)),
          make_case('fragment-exit', fragment_time=(1.1, 4.1)),
          make_case('fragment-both-ends', fragment_time=(.9, 4.1))]
for percent, interval in [(79, (2.05, 7.05)), (80, (2, 7)), (81, (1.95, 6.95))]:
    cases.append(make_case('overlap-' + str(percent), full_time=(1, 6), fragment_time=interval,
                           oracle='preserve readable fragment-only exposure'))
cases += [make_case('independent-displaced-row', shift=120, oracle='preserve separate positioned text'),
          make_case('independent-size', size=52, oracle='preserve differently sized text'),
          make_case('independent-font', font=OTHER_FONT, oracle='preserve different font'),
          make_case('independent-case', fragment_text='THE SKY SHINES', oracle='preserve authored capitalization'),
          make_case('independent-spacing', fragment_text='Theskyshines', oracle='preserve authored spacing')]

original = s.collapse_matching_lyric_layers


def describe(path):
    document = s._resolve_document_state(s.parse_subtitle_document(path.read_text()))
    return [dict(text=s.OVERRIDE_RE.sub('', e.text), start=e.start_s, end=e.end_s,
                 layer=e.layer, position=s.get_pos(e.text), font=e.state.get('fn'),
                 size=e.state.get('fs'), alignment=e.state.get('an'), fill=e.state.get('1c'), outline=e.state.get('3c'),
                 fields=e.fields()) for e in document.events.values() if e.kind == 'Dialogue']


def convert(source, output, enabled):
    original_bytes = source.read_bytes()
    calls = []
    def instrument(events, visible, font_metrics=None):
        result, removed = original(events, visible, font_metrics)
        live = {e.source_index for e in result}
        calls.append(dict(would_remove=removed,
                          removed_text=[visible.get(e.source_index) for e in events if e.source_index not in live],
                          input_lyric_events=sum(e.lyric for e in events)))
        return (result, removed) if enabled else (events, 0)
    report = s.FontProcessingReport()
    with patch.object(s, 'collapse_matching_lyric_layers', instrument), contextlib.redirect_stdout(io.StringIO()):
        stats = s.simplify_ass(source, output, s.SimplifyConfig(), font_metrics=metrics, font_report=report)
    assert not report.missing_families, sorted(report.missing_families)
    assert len(calls) == 1
    assert source.read_bytes() == original_bytes, 'Input was modified'
    return dict(statistics=stats, probe=calls[0], events=describe(output))


def oracle_checks(case, events):
    """Expectations from the authored fixture, independent of filter outputs."""
    anchor = [e for e in events if e['text'] == TEXT and e['position'] == (100.0, 100.0)
              and e['alignment'] == 7 and e['font'] == FONT and e['size'] == 40
              and e['fill'] == 'FFFFFF' and e['outline'] == '403020']
    checks = {'authored_caption_text_paint_geometry_retained': bool(anchor)}
    name, settings = case['name'], case['settings']
    if name == 'independent-displaced-row':
        checks['independent_text_retained'] = any(e['position'][0] > 300 for e in events)
    elif name == 'independent-size':
        checks['independent_text_retained'] = any(e['size'] == 52 for e in events)
    elif name == 'independent-font':
        checks['independent_text_retained'] = any(e['font'] == OTHER_FONT for e in events)
    elif name in ('independent-case', 'independent-spacing'):
        checks['independent_text_retained'] = any(e['text'] == settings['fragment_text'] for e in events)
    else:
        # Every fragment is static, opaque and present throughout its authored
        # interval. Preserving its complete row's readable exposure is required.
        low = min(settings['full_time'][0], settings['fragment_time'][0])
        high = max(settings['full_time'][1], settings['fragment_time'][1])
        coverage = sorted((e['start'], e['end']) for e in events if e['text'] == TEXT)
        cursor = low
        for start, end in coverage:
            if start <= cursor + 1e-9:cursor = max(cursor, end)
        checks['readable_row_exposure_retained'] = cursor >= high - 1e-9
    return checks


render_fonts = DEST / 'render-fonts';render_fonts.mkdir(exist_ok=True)
for family, bold, italic in required:
    face = metrics.matching_face(family, bold, italic)
    destination = render_fonts / Path(face.path).name
    if not destination.exists():shutil.copy2(face.path, destination)


def render(path, at, destination):
    vf = (f'settb=1/1000,setpts=PTS+{round(at*1000)},'
          f'ass=filename={path}:fontsdir={render_fonts}')
    run = subprocess.run(['ffmpeg', '-v', 'info', '-f', 'lavfi', '-i',
                          'color=c=gray:s=640x360:r=1', '-vf', vf,
                          '-frames:v', '1', '-threads', '1', '-y', str(destination)],
                         capture_output=True, text=True, check=True)
    if any(e['start'] <= at < e['end'] for e in describe(path)):
        assert 'fontselect:' in run.stderr, 'No rendered text/font selection at ' + str(at)
    return Image.open(destination).convert('RGB'), [line for line in run.stderr.splitlines() if 'fontselect:' in line]


records = []
for case in cases:
    name = case['name'];paths = {mode: DEST / (name + '.' + mode + '.ass') for mode in ('on', 'off')}
    results = {}
    for mode, path in paths.items():
        results[mode] = convert(case['source'], path, mode == 'on')
        again = DEST / (name + '.' + mode + '.again.ass')
        second = convert(path, again, mode == 'on')
        results[mode]['byte_idempotent'] = path.read_bytes() == again.read_bytes()
        results[mode]['second_pass_events'] = second['events']
        results[mode]['oracle_checks'] = oracle_checks(case, results[mode]['events'])
        assert results[mode]['statistics']['overlap_removed'] == (results[mode]['probe']['would_remove'] if mode == 'on' else 0)
    assert case['source'].read_text().startswith(HEADER)
    assert results['on']['probe'] == results['off']['probe'], 'Instrumented runs disagree before target filter'
    changed = paths['on'].read_bytes() != paths['off'].read_bytes()
    record = dict(name=name, oracle=case['oracle'], settings=case['settings'],
                  source_sha256=hashlib.sha256(case['source'].read_bytes()).hexdigest(),
                  output_changed=changed, results=results, renders=[])
    # Always render one redundant-copy case and the ordinary control; render
    # every branch difference during hold and any fragment-only exposure.
    if changed or name in ('letters-offset-1', 'ordinary-full-line') or name.startswith('independent-'):
        full = case['settings']['full_time'];frag = case['settings']['fragment_time']
        times = {round((max(full[0], frag[0]) + min(full[1], frag[1])) / 2, 3)}
        if full[0] != frag[0]:times.add(round((full[0] + frag[0]) / 2, 3))
        if full[1] != frag[1]:times.add(round((full[1] + frag[1]) / 2, 3))
        for at in sorted(times):
            images, fonts = {}, {}
            for mode, path in dict(source=case['source'], **paths).items():
                images[mode], fonts[mode] = render(path, at, DEST / f'{name}.{at}.{mode}.png')
            difference = ImageChops.difference(images['on'], images['off'])
            pixels = difference.tobytes()
            record['renders'].append(dict(time=at, on_off_pixel_identical=difference.getbbox() is None,
                                          changed_pixels=sum(bool(r or g or b) for r,g,b in zip(pixels[::3],pixels[1::3],pixels[2::3])),
                                          font_selections=fonts))
            board = Image.new('RGB', (640 * 3, 390), '#202020');draw = ImageDraw.Draw(board)
            for column, mode in enumerate(('source', 'on', 'off')):
                draw.text((column * 640 + 8, 8), f'{name} / {at}s / {mode}', fill='white')
                board.paste(images[mode], (column * 640, 30))
            board.save(DEST / f'{name}.{at}.comparison.png')
    records.append(record)
    summary = dict(version=s.__version__, backend='Windows BASIC with real HarfBuzz; FFmpeg/libass renders on Linux',
                   fonts=[dict(family=f, bold=b, italic=i, path=str(metrics.matching_face(f,b,i).path),
                               sha256=hashlib.sha256(Path(metrics.matching_face(f,b,i).path).read_bytes()).hexdigest()) for f,b,i in required],
                   engine_sha256=hashlib.sha256((ROOT / 'simplify_ass.py').read_bytes()).hexdigest(),
                   completed=len(records), cases=records)
    (DEST / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(name, 'removed=', results['on']['statistics']['overlap_removed'], 'changed=', changed,
          'counts=', len(results['on']['events']), len(results['off']['events']), flush=True)
print(len(records), 'complete-pipeline lyric niche experiments completed; inspect policy findings separately')
