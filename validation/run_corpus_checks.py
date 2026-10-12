"""Compare fresh v176/v177 conversions using the supplied nine-file corpus."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import simplify_ass as current


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    cases = json.loads((ROOT / 'test-data/corpus-manifest.json').read_text())
    if len(cases) != 9:
        raise ValueError('Expected the supplied nine-file corpus')
    reference = ROOT / 'test-data/simplify_ass-v176-reference.py'
    destination = ROOT / 'validation/migration-corpus/windows'
    destination.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['ASS_REGRESSION_FONT_BACKEND'] = 'windows'
    startup = str(ROOT / 'validation/backend_startup')
    env['PYTHONPATH'] = os.pathsep.join(
        [startup, *filter(None, env.get('PYTHONPATH', '').split(os.pathsep))])

    def convert(engine, source, output):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'validation/measure_one.py'),
             '--engine', str(engine), '--source', str(source),
             '--fonts', str(ROOT / 'fonts'), '--output', str(output)],
            cwd=ROOT, env=env, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return json.loads(output.with_suffix('.json').read_text())

    def compare(case):
        name = case['name']
        source = ROOT / case['source']
        if digest(source) != case['sha256']:
            raise ValueError('Source checksum mismatch: ' + name)
        before_path = destination / (name + '-v176.ass')
        after_path = destination / (name + '-v177.ass')
        before = convert(reference, source, before_path)
        after = convert(ROOT / 'simplify_ass.py', source, after_path)
        if name.startswith('Attack'):
            old_events = current.load_subtitle_events(before_path)[1]
            new_events = current.load_subtitle_events(after_path)[1]
            unrelated = lambda events: [e.fields() for e in events if e.style != 'OP-R']
            assert unrelated(old_events) == unrelated(new_events), 'Unrelated events changed'
            romanized = [e for e in new_events if e.style == 'OP-R']
            assert len(romanized) == 21, 'Expected 21 complete opening lines'
            focused = current.load_subtitle_events(ROOT / 'outputs/opening-probe.ass')[1]
            assert [e.fields() for e in romanized] == [
                e.fields() for e in focused if e.style == 'OP-R']
            assert (before['statistics']['output'], after['statistics']['output']) == (3491, 354)
        else:
            assert before_path.read_bytes() == after_path.read_bytes(), name
            assert before['statistics'] == after['statistics'], name
        assert digest(source) == case['sha256'], 'Source modified'
        print(name, before['statistics']['output'], '->',
              after['statistics']['output'], flush=True)
        return dict(case=name, source_sha256=case['sha256'],
                    before=before['statistics'], after=after['statistics'],
                    baseline_sha256=before['output_sha256'],
                    output_sha256=after['output_sha256'])

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(compare, cases))
    report = dict(runtime_sha256=digest(ROOT / 'simplify_ass.py'),
                  reference_sha256=digest(reference), backend='windows',
                  baselines_regenerated=True, cases=results)
    (destination / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print('9 fresh Windows-font-backend corpus comparisons passed')


if __name__ == '__main__':
    main()
