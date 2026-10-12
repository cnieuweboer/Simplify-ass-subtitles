"""Trace repeated conversions and verify their event/timing/render consequences."""
from pathlib import Path
from unittest.mock import patch
import collections
import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import simplify_ass as s
from PIL import Image, ImageChops, ImageDraw

DEST = ROOT / 'validation/second-pass-investigation' / s.__version__
DEST.mkdir(parents=True, exist_ok=True)
metrics = s.FontMetrics([ROOT / 'fonts'])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
runtime_hash = sha(ROOT / 'simplify_ass.py')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--corpus-only', action='store_true')
args = parser.parse_args()
STAGES = ['reduce_static_sign_copies', 'flatten_stacked_text_copies', 'coalesce_lyric_phases',
          'deduplicate_layers', 'collapse_matching_lyric_layers', 'collapse_full_lyric_copies',
          'merge_frame_animation', 'flatten_text_effect_sequences', 'remove_letters_over_full_lines',
          'reconstruct_text_rows', 'remove_covered_fragment_effects', 'trim_faded_cue_overlaps',
          'merge_static_timed_copies', 'normalize_near_text_colors', 'compact_static_overrides',
          'reduce_supporting_drawings', 'select_caption_supports', '_rebuild_caption_supports',
          '_restore_caption_paint', 'restore_masked_caption_foregrounds']


def event_list(value):
    if isinstance(value, dict):value = list(value.values())
    if isinstance(value, list) and all(isinstance(e, s.Event) for e in value):return value
    if hasattr(value, 'events'):return event_list(value.events)
    if isinstance(value, tuple) and value:return event_list(value[0])
    return None


def describe(e):
    return dict(fields=e.fields(), lyric=e.lyric, row=e.row, source_index=e.source_index,
                text=s.OVERRIDE_RE.sub('', e.text), start=e.start_s, end=e.end_s,
                position=s.get_pos(e.text), state=dict(e.state))


def convert(source, output, *, bypass_sign=False, pretend_non_lyric=False):
    before_hash = sha(source);stages = []
    def instrument(name, original):
        def wrapped(*args, **kwargs):
            input_index = 1 if name in ('_restore_caption_paint', 'restore_masked_caption_foregrounds') else 0
            before = event_list(args[input_index]) if args else None
            snapshot = [describe(e) for e in before] if before is not None else None
            if name == 'reduce_static_sign_copies' and bypass_sign:
                result = (args[0], 0)
            elif name == 'reduce_static_sign_copies' and pretend_non_lyric:
                # Diagnostic only: the pass sees cleared flags on private
                # successors; survivors keep their original flags/objects.
                copies = [s.dataclass_replace(e, lyric=False) for e in args[0]]
                selected, n = original(copies, *args[1:], **kwargs)
                ids = {e.source_index for e in selected}
                result = ([e for e in args[0] if e.source_index in ids], n)
            else:result = original(*args, **kwargs)
            after = event_list(result)
            if before is not None and after is not None:
                old_fields = [e['fields'] for e in snapshot]
                new_fields = [e.fields() for e in after]
                if old_fields != new_fields or name == 'reduce_static_sign_copies':
                    stages.append(dict(name=name, input_count=len(before), output_count=len(after),
                                       before=snapshot, after=[describe(e) for e in after]))
            return result
        return wrapped
    report = s.FontProcessingReport()
    with contextlib.ExitStack() as stack, contextlib.redirect_stdout(io.StringIO()):
        for name in STAGES:
            stack.enter_context(patch.object(s, name, instrument(name, getattr(s, name))))
        stats = s.simplify_ass(source, output, s.SimplifyConfig(), font_metrics=metrics, font_report=report)
    assert not report.missing_families, ('Missing exact fonts; stop', sorted(report.missing_families))
    assert sha(source) == before_hash
    events = s.load_subtitle_events(output)[1]
    return dict(statistics=stats, stages=stages, output_sha256=sha(output), events=[describe(e) for e in events])


def render(path, at, destination, size='640x360'):
    vf = (f'settb=1/1000,setpts=PTS+{round(at*1000)},'
          f'ass=filename={path}:fontsdir={ROOT / "fonts"}')
    run = subprocess.run(['ffmpeg', '-v', 'info', '-f', 'lavfi', '-i',
                          f'color=c=gray:s={size}:r=1', '-vf', vf, '-frames:v', '1',
                          '-threads', '1', '-y', str(destination)], capture_output=True, text=True, check=True)
    return Image.open(destination).convert('RGB'), [line for line in run.stderr.splitlines() if 'fontselect:' in line]


def compare_events(first, second):
    # Renderer fields, rather than reparsed source IDs, identify surviving events.
    old = collections.Counter(tuple(e['fields']) for e in first)
    new = collections.Counter(tuple(e['fields']) for e in second)
    return dict(removed=[list(k) for k in (old-new).elements()],
                added=[list(k) for k in (new-old).elements()],
                event_counts=[len(first), len(second)])


def semantic_key(e):
    return tuple(e['fields'][:-1]), e['text'], json.dumps(e['state'], sort_keys=True)


records = []
def save():
    (DEST / ('corpus-trace.json' if args.corpus_only else 'summary.json')).write_text(json.dumps(dict(version=s.__version__,runtime_sha256=runtime_hash,
                                                     cases=records), indent=2) + '\n')


synthetic = json.loads((ROOT / 'validation/lyric-layer-niche' / s.__version__ / 'summary.json').read_text())
assert synthetic['engine_sha256'] == runtime_hash
for case in ([] if args.corpus_only else synthetic['cases']):
    name = case['name'];source = ROOT / 'validation/lyric-layer-niche' / s.__version__ / (name + '.source.ass')
    assert sha(source) == case['source_sha256']
    paths = {label: DEST / (name + '.' + label + '.ass') for label in ('first','second','third','second-no-sign','first-cleared-flags')}
    first = convert(source, paths['first']);second = convert(paths['first'], paths['second']);third = convert(paths['second'], paths['third'])
    assert paths['first'].read_bytes() == (source.parent / (name + '.on.ass')).read_bytes()
    difference = compare_events(first['events'], second['events'])
    old_semantics=collections.Counter(map(semantic_key,first['events']))
    new_semantics=collections.Counter(map(semantic_key,second['events']))
    assert not new_semantics-old_semantics, (name,'surviving caption semantics changed')
    assert sum((old_semantics-new_semantics).values()) in (0,1), (name,'unexpected semantic removals')
    record = dict(name=name, category='synthetic', source_sha256=sha(source), difference=difference,
                  first=first, second=second, third_stable=paths['second'].read_bytes()==paths['third'].read_bytes(), renders=[])
    if paths['first'].read_bytes() != paths['second'].read_bytes():
        no_sign = convert(paths['first'], paths['second-no-sign'], bypass_sign=True)
        cleared = convert(source, paths['first-cleared-flags'], pretend_non_lyric=True)
        record['without_static_sign_reduction_matches_first'] = paths['second-no-sign'].read_bytes()==paths['first'].read_bytes()
        record['cleared_flags_first_matches_second'] = paths['first-cleared-flags'].read_bytes()==paths['second'].read_bytes()
        record['diagnostic_no_sign'] = no_sign
        record['diagnostic_cleared_flags'] = cleared
        record['without_static_sign_reduction_preserves_semantics'] = (
            collections.Counter(map(semantic_key, first['events'])) ==
            collections.Counter(map(semantic_key, no_sign['events'])))
        assert record['without_static_sign_reduction_preserves_semantics'], (name,'removal not isolated to sign filter')
        intervals = (case['settings']['full_time'], case['settings']['fragment_time'])
        endpoints = sorted({t for pair in intervals for t in pair})
        times = sorted({round((a+b)/2,3) for a,b in zip(endpoints,endpoints[1:]) if a<b})
        for at in times:
            images, fonts = {}, {}
            for label in ('first','second'):
                images[label], fonts[label] = render(paths[label], at, DEST / f'{name}.{at}.{label}.png')
            diff = ImageChops.difference(images['first'],images['second']);pixels=diff.tobytes()
            record['renders'].append(dict(time=at,pixel_identical=diff.getbbox() is None,
                                          changed_pixels=sum(bool(r or g or b) for r,g,b in zip(pixels[::3],pixels[1::3],pixels[2::3])),
                                          font_selections=fonts))
            board=Image.new('RGB',(1280,390),'#202020');draw=ImageDraw.Draw(board)
            for x,label in [(0,'first'),(640,'second')]:
                draw.text((x+8,8),f'{name} / {at}s / {label}',fill='white');board.paste(images[label],(x,30))
            board.save(DEST / f'{name}.{at}.comparison.png')
    records.append(record);save()
    print(name,difference['event_counts'],'stable third:',record['third_stable'],flush=True)

manifest=json.loads((ROOT / 'test-data/corpus-manifest.json').read_text())
for case in manifest:
    name=case['name'];source=ROOT / 'validation/lyric-layer-corpus/windows' / (name+'-current.ass')
    meta=json.loads(source.with_suffix('.json').read_text())
    assert meta['engine_sha256']==runtime_hash and meta['output_sha256']==sha(source)
    assert meta['source_sha256']==case['sha256'] and meta['missing_families']==[]
    output=DEST/(name+'.second.ass');third_path=DEST/(name+'.third.ass')
    second=convert(source,output);third=convert(output,third_path)
    first_events=[describe(e) for e in s.load_subtitle_events(source)[1]]
    record=dict(name=name,category='corpus',difference=compare_events(first_events,second['events']),
                first_path=str(source),second=second,third=third,
                difference_second_third=compare_events(second['events'],third['events']),
                third_stable=output.read_bytes()==third_path.read_bytes(),
                semantic_identical=collections.Counter(map(semantic_key,first_events))==collections.Counter(map(semantic_key,second['events'])),
                byte_identical=source.read_bytes()==output.read_bytes())
    if not record['third_stable']:
        fourth_path=DEST/(name+'.fourth.ass')
        convert(third_path,fourth_path)
        record['fourth_stable']=third_path.read_bytes()==fourth_path.read_bytes()
    records.append(record);save()
    print(name,record['difference']['event_counts'],'same:',record['byte_identical'],'stable third:',record['third_stable'],flush=True)
print('Repeated conversions completed',flush=True)
