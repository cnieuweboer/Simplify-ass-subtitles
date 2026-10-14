"""Check bounded subtitle processes, ordered reporting, and child cleanup."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("simplify_subtitles", ROOT / "simplify_subtitles.py")
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)

ENGINE = r'''import json,sys,time,os
from pathlib import Path
stats=Path(sys.argv[sys.argv.index('--stats-json')+1])
sources=[Path(p) for p in sys.argv[sys.argv.index('--')+1:]]
records=[]
for source in sources:
    number=int(source.stem.split('-')[1])
    start=time.monotonic_ns()
    source.with_suffix('.started').touch()
    mode=source.read_text()
    if mode=='parallel':
        deadline=time.monotonic()+5
        # Force completion out of track order and require overlapping workers.
        if number==0:
            while not source.with_name('track-1.finished').exists():
                if time.monotonic()>deadline: raise RuntimeError('No overlapping worker')
                time.sleep(.01)
        elif number==1:
            while not source.with_name('track-0.started').exists():
                if time.monotonic()>deadline: raise RuntimeError('No overlapping worker')
                time.sleep(.01)
    elif mode=='fail':
        print('ERROR: deliberate failure',flush=True)
        raise SystemExit(2)
    elif mode=='wait':
        time.sleep(30)
    output=source.with_name(source.stem+'.simple'+source.suffix)
    output.write_text('Converted '+str(number))
    records.append({'input':str(source.resolve()),'stats':{'original':10,'output':5},'warnings':[]})
    source.with_suffix('.timing').write_text(json.dumps([start,time.monotonic_ns(),os.getpid()]))
    source.with_suffix('.finished').touch()
    print('WARNING: track '+str(number),flush=True)
stats.write_text(json.dumps({'tracks':records}))
'''


class WorkerChecks(unittest.TestCase):
    def setup_job(self, root, modes):
        engine = root / "engine.py"
        engine.write_text(ENGINE)
        candidates = []
        for number, mode in enumerate(modes):
            source = root / f"track-{number}.ass"
            source.write_text(mode)
            candidates.append({"track": {"id": number}, "input": source})
        return [sys.executable, str(engine)], candidates

    def test_default_and_override(self):
        for cpus, expected in ((None, 1), (1, 1), (2, 1), (3, 1), (16, 8)):
            with patch.object(os, "cpu_count", return_value=cpus):
                self.assertEqual(wrapper.parser().parse_args([]).workers, expected)
        self.assertEqual(wrapper.parser().parse_args(["--workers", "3"]).workers, 3)
        with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            wrapper.main(["--workers", "0"])

    def test_overlap_limit_order_and_sequential_equivalence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            command, candidates = self.setup_job(root, ["parallel"] * 3)
            with patch("sys.stdout", new_callable=io.StringIO) as console:
                parallel = wrapper.simplify_tracks(command, candidates, root, 2)
            self.assertEqual([Path(r["input"]).stem for r in parallel], ["track-0", "track-1", "track-2"])
            self.assertEqual(console.getvalue().splitlines(), ["  WARNING: track 0", "  WARNING: track 1", "  WARNING: track 2"])
            timings = [json.loads((root / f"track-{i}.timing").read_text()) for i in range(3)]
            self.assertLess(timings[1][1], timings[0][1])
            self.assertLess(max(timings[0][0], timings[1][0]), min(timings[0][1], timings[1][1]))
            events = sorted([(t[0], 1) for t in timings] + [(t[1], -1) for t in timings])
            active = peak = 0
            for _, delta in events:
                active += delta
                peak = max(peak, active)
            self.assertEqual(peak, 2)
            self.assertEqual(len({t[2] for t in timings}), 3)
            outputs = [(root / f"track-{i}.simple.ass").read_bytes() for i in range(3)]
            for candidate in candidates:
                candidate["input"].write_text("serial")
            with patch("sys.stdout", new_callable=io.StringIO):
                serial = wrapper.simplify_tracks(command, candidates, root, 1)
            self.assertEqual(serial, parallel)
            self.assertEqual(outputs, [(root / f"track-{i}.simple.ass").read_bytes() for i in range(3)])

    def test_limit_capped_at_track_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            command, candidates = self.setup_job(root, ["serial", "serial"])
            original = subprocess.Popen
            with patch.object(wrapper.subprocess, "Popen", wraps=original) as launch, \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(len(wrapper.simplify_tracks(command, candidates, root, 100)), 2)
            self.assertEqual(launch.call_count, 2)

    def check_cleanup(self, interrupt):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            command, candidates = self.setup_job(root, ["wait", "wait" if interrupt else "fail", "serial"])
            processes = []
            original = subprocess.Popen
            def launch(*args, **kwargs):
                process = original(*args, **kwargs)
                processes.append(process)
                return process
            with patch.object(wrapper.subprocess, "Popen", side_effect=launch):
                if interrupt:
                    with patch.object(wrapper.time, "sleep", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                        wrapper.simplify_tracks(command, candidates, root, 2)
                else:
                    with self.assertRaisesRegex(RuntimeError, "track 1.*deliberate failure"):
                        wrapper.simplify_tracks(command, candidates, root, 2)
            self.assertEqual(len(processes), 2)
            self.assertTrue(all(p.poll() is not None for p in processes))
            self.assertFalse((root / "track-2.started").exists())

    def test_failure_stops_other_tracks_before_cleanup(self):
        self.check_cleanup(False)

    def test_cancellation_stops_children_before_cleanup(self):
        self.check_cleanup(True)


if __name__ == "__main__":
    unittest.main()
