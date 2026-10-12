#!/usr/bin/env python3
"""Convert six real-world fixtures and report changes against saved v107 outputs.

Baseline differences are review signals, not automatic correctness failures.
The supplied simplified files have unknown provenance and are comparisons only.
"""
from pathlib import Path
import argparse
import collections
import contextlib
import hashlib
import importlib.util
import json
import platform
import sys
import time


ROOT = Path('/workspace/scratch/47f8a23c7b66/expanded-tests-v107')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_engine(path):
    spec = importlib.util.spec_from_file_location('tested_simplifier', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def top_intervals(engine, events):
    boundaries = collections.Counter()
    for event in events:
        if event.kind != 'Dialogue':
            continue
        start, end = engine.parse_time(event.start), engine.parse_time(event.end)
        if start < end:
            boundaries[start] += 1
            boundaries[end] -= 1
    times = sorted(boundaries)
    active = 0
    intervals = []
    for start, end in zip(times, times[1:]):
        active += boundaries[start]
        if active:
            intervals.append((active, start, end))
    selected = []
    for active, start, end in sorted(intervals, key=lambda x: (-x[0], x[1])):
        at = (start + end) / 2
        if any(abs(at - item['sample_seconds']) < 1 for item in selected):
            continue
        peers = [e for e in events if e.kind == 'Dialogue' and
                 engine.parse_time(e.start) <= at < engine.parse_time(e.end)]
        selected.append({'active_events': active,
                         'start': engine.format_time(start),
                         'end': engine.format_time(end),
                         'sample_seconds': round(at, 6),
                         'styles': dict(collections.Counter(e.style for e in peers))})
        if len(selected) == 5:
            break
    return selected


def summarize(engine, path):
    lines, events, *_ = engine.load_subtitle_events(path)
    dialogue = [e for e in events if e.kind == 'Dialogue']
    tags = collections.Counter()
    for event in dialogue:
        names = {name for block in engine.OVERRIDE_RE.findall(event.text)
                 for name, _ in engine.tokenize_override(block)}
        tags.update(names)
    return {'bytes': path.stat().st_size,
            'sha256': digest(path),
            'dialogue_events': len(dialogue),
            'comment_events': sum(e.kind == 'Comment' for e in events),
            'peak_concurrent': engine.peak_concurrent_events(events),
            'drawing_events': sum(bool(e.state.get('p', 0)) for e in dialogue),
            'short_events': sum(0 < e.end_s - e.start_s <= .160001 for e in dialogue),
            'styles': dict(collections.Counter(e.style for e in dialogue)),
            'events_with_tags': dict(sorted(tags.items())),
            'top_concurrency_intervals': top_intervals(engine, events)}, events


def compare(reference, current, limit=10):
    old = collections.Counter(tuple(e.fields()) for e in reference)
    new = collections.Counter(tuple(e.fields()) for e in current)
    added, removed = new - old, old - new
    return {'event_fields_identical': old == new,
            'event_order_identical': [e.fields() for e in reference] == [e.fields() for e in current],
            'added_records': sum(added.values()), 'removed_records': sum(removed.values()),
            'added_examples': [{'fields': list(k), 'count': v} for k, v in list(added.items())[:limit]],
            'removed_examples': [{'fields': list(k), 'count': v} for k, v in list(removed.items())[:limit]]}


def run_case(args, case):
    source = ROOT / case['source']
    if digest(source) != case['source_sha256']:
        raise ValueError(f"Input fixture changed: {case['id']}")
    baseline = ROOT / case.get('baseline_output', 'missing')
    if case.get('baseline_sha256') and digest(baseline) != case['baseline_sha256']:
        raise ValueError(f"Saved baseline changed: {case['id']}")
    output = args.output_dir / (case['id'] + '.ass')
    protected = [source, ROOT / 'baseline-v107' / output.name]
    if case.get('supplied_comparison'):
        protected.append(ROOT / case['supplied_comparison'])
    # Baselines are immutable review records; new runs belong elsewhere.
    if any(output.resolve() == p.resolve() or
           output.exists() and p.exists() and output.samefile(p) for p in protected):
        raise ValueError('Choose an output directory separate from fixtures and baselines')
    engine = load_engine(args.script)
    metric = engine.FontMetrics(args.fonts_dir)
    fonts = metric
    font_report = engine.FontProcessingReport()
    outline_matcher = engine.FontOutlineMatcher(fonts)
    source_summary, source_events = summarize(engine, source)
    requested = {(str(e.state.get('fn', '')), bool(e.state.get('b', 0)), bool(e.state.get('i', 0)))
                 for e in source_events if e.kind == 'Dialogue' and not e.state.get('p', 0)}
    unavailable = [{'family': name, 'bold': bold, 'italic': italic}
                   for name, bold, italic in sorted(requested)
                   if fonts.matching_face(name, bold, italic) is None]
    started = time.perf_counter()
    with (args.output_dir / (case['id'] + '.log')).open('w', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            stats = engine.simplify_ass(source, output, engine.SimplifyConfig(), font_metrics=metric, font_report=font_report, outline_matcher=outline_matcher)
    seconds = round(time.perf_counter() - started, 3)
    if digest(source) != case['source_sha256']:
        raise AssertionError('Converter changed the source fixture')
    current_summary, current = summarize(engine, output)
    if stats['output'] != current_summary['dialogue_events']:
        raise AssertionError('Output count differs from the serialized file')
    if stats['max_concurrent_out'] != current_summary['peak_concurrent']:
        raise AssertionError('Peak count differs from the serialized file')
    if not engine.has_generated_marker(output):
        raise AssertionError('Output lacks its generated marker')
    if any(e.kind == 'Dialogue' and engine.parse_time(e.end) <= engine.parse_time(e.start)
           for e in current):
        raise AssertionError('Output contains a nonpositive Dialogue duration')
    try:
        from PIL import features
        raqm = bool(features.check_feature('raqm'))
    except ImportError:
        raqm = False
    report = {'case': case['id'], 'engine_version': engine.__version__,
              'engine_sha256': digest(args.script), 'python_version': platform.python_version(),
              'conversion_seconds': seconds, 'source': source_summary,
              'current': current_summary, 'statistics': stats,
              'text_drop_warnings': engine.text_drop_warnings(stats),
              'font_measurement_available': metric.available, 'raqm': raqm,
              'harfbuzz_available': fonts.capabilities.harfbuzz,
              'unavailable_requested_faces': unavailable,
              'missing_during_conversion': sorted(font_report.missing_families),
              'used_faces': [{'filename': Path(path).name, 'index': index, 'sha256': digest(Path(path))}
                             for path, index in sorted(fonts._cmaps) if fonts._cmaps[(path, index)] is not None]}
    for key, path in [('supplied_comparison', ROOT / case.get('supplied_comparison', 'missing')),
                      ('baseline_comparison', ROOT / 'baseline-v107' / output.name)]:
        if path.is_file():
            if key == 'supplied_comparison' and digest(path) != case['supplied_comparison_sha256']:
                raise AssertionError('Supplied comparison changed')
            summary, reference = summarize(engine, path)
            report[key] = {'summary': summary, **compare(reference, current),
                           'bytes_identical': path.read_bytes() == output.read_bytes()}
    (args.output_dir / (case['id'] + '.json')).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"{case['id']}: {source_summary['dialogue_events']} -> {current_summary['dialogue_events']} "
          f"events; peak {source_summary['peak_concurrent']} -> {current_summary['peak_concurrent']}; "
          f"{seconds}s", flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--script', type=Path, default=ROOT / 'engine' / 'simplify_ass.py')
    ap.add_argument('--case', action='append', default=[], help='case ID; repeat to select several')
    ap.add_argument('--fonts-dir', type=Path, action='append', default=[])
    ap.add_argument('--output-dir', type=Path, default=ROOT / 'runs' / 'latest')
    args = ap.parse_args()
    args.script = args.script.resolve()
    args.output_dir = args.output_dir.resolve()
    args.fonts_dir = args.fonts_dir or [ROOT / 'fonts']
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    known = {case['id'] for case in manifest['cases']}
    if set(args.case) - known:
        ap.error('Unknown case IDs: ' + ', '.join(sorted(set(args.case) - known)))
    if args.output_dir in {ROOT / 'inputs', ROOT / 'supplied-comparisons', ROOT / 'baseline-v107'}:
        ap.error('Choose a directory separate from fixtures and baselines')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for case in manifest['cases']:
        if not args.case or case['id'] in args.case:
            results.append(run_case(args, case))
    (args.output_dir / 'summary.json').write_text(json.dumps({
        'cases': [{'case': r['case'], 'source_events': r['source']['dialogue_events'],
                   'output_events': r['current']['dialogue_events'],
                   'source_peak': r['source']['peak_concurrent'],
                   'output_peak': r['current']['peak_concurrent'],
                   'text_drop_warnings': r['text_drop_warnings'],
                   'baseline_changed': not r.get('baseline_comparison', {}).get('event_fields_identical', True)}
                  for r in results]}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
