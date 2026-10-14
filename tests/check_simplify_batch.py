"""Batch consistency policy plus real MKV remuxes with a deterministic test engine."""

from collections import Counter
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("simplify_subtitles", ROOT / "simplify_subtitles.py")
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


def track(name="A", language="en", codec="S_TEXT/ASS"):
    return {"id": 0, "type": "subtitles", "properties": {
        "track_name": name, "language_ietf": language, "codec_id": codec}}


class BatchPolicyChecks(unittest.TestCase):
    def test_filename_prefix_strips_leading_release_groups_and_ignores_case(self):
        for name in ("[Group] Show Episode 01.mkv", "[Other] [1080p] SHOW-Episode02.mkv", "Show Episode03.mkv"):
            self.assertEqual(wrapper.filename_prefix(Path(name)), "showe")
        self.assertNotEqual(wrapper.filename_prefix(Path("[Group] Other Show.mkv")), "showe")

    def test_groups_distinguish_names_languages_and_formats(self):
        first = wrapper.subtitle_group(track())
        for other in (track("Different"), track(language="de"), track(codec="S_TEXT/SSA")):
            self.assertNotEqual(first, wrapper.subtitle_group(other))

    def test_warnings_and_confirmation_happen_before_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("[Group] Show Episode1.mkv", "[Group] Other Episode2.mkv"):
                (root / name).touch()
            infos = [{"tracks": [track("A"), track("B")]}, {"tracks": [track("B")]}]
            with patch.object(wrapper, "find_tool", side_effect=lambda name, _: name), \
                 patch.object(wrapper, "identify", side_effect=infos), \
                 patch.object(wrapper, "run", return_value="--stats-json --suffix --scroll-concurrency-limit"), \
                 patch.object(wrapper, "extract_items") as extract, \
                 patch("sys.stdout", new_callable=io.StringIO) as console:
                def confirm(prompt):
                    self.assertIn("Filename prefixes differ", console.getvalue())
                    self.assertIn("Subtitle groups vary", console.getvalue())
                    self.assertIn("present in 1/2 files", console.getvalue())
                    self.assertEqual(prompt, "Proceed? (y/N): ")
                    return "n"
                with patch("builtins.input", side_effect=confirm):
                    self.assertEqual(wrapper.main([folder, "--keep-originals", "--filtered"]), 0)
                extract.assert_not_called()
            self.assertFalse((root / "output").exists())

    def test_matching_prefixes_and_groups_do_not_warn(self):
        scans = {Path(name): {"before": {"tracks": [track()]}} for name in
                 ("[Group] Show Episode1.mkv", "[Other] Show Episode2.mkv")}
        with patch("sys.stdout", new_callable=io.StringIO) as console:
            wrapper.batch_warnings(scans)
        self.assertNotIn("WARNING", console.getvalue())

    def test_source_change_during_extraction_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mkv"
            source.write_bytes(b"before")
            scan = {"before": {"tracks": []}, "stamp": wrapper.stamp(source)}
            with patch.object(wrapper, "extract_items", side_effect=lambda *args: source.write_bytes(b"after changed")):
                with self.assertRaises(RuntimeError):
                    wrapper.prepare_file(source, root / "output.mkv", wrapper.parser().parse_args([]),
                                         "merge", "extract", root / "work", scan)


TEST_ENGINE = r'''import json,sys
from pathlib import Path
if '--help' in sys.argv:
    print('--stats-json --suffix --scroll-concurrency-limit --level --fonts-dir')
    raise SystemExit(0)
stats_path=Path(sys.argv[sys.argv.index('--stats-json')+1])
limit=int(sys.argv[sys.argv.index('--scroll-concurrency-limit')+1])
inputs=[Path(value) for value in sys.argv[sys.argv.index('--')+1:]]
records=[]
for source in inputs:
    text=source.read_text(encoding='utf-8-sig')
    rows=[line for line in text.splitlines() if line.startswith('Dialogue:')]
    simple='Title: C' in text
    first=True
    result=[]
    for line in text.splitlines():
        if line.startswith('Dialogue:') and not simple:
            if not first: continue
            first=False
        result.append(line)
        if line.strip()=='[Script Info]': result.append('; Simplified by simplify_ass.py')
    output=source.with_name(source.stem+'.simple'+source.suffix)
    output.write_text('\n'.join(result)+'\n',encoding='utf-8')
    count=sum(line.startswith('Dialogue:') for line in result)
    records.append({'input':str(source.resolve()),'stats':{'original':len(rows),'output':count,
                    'max_concurrent_in':len(rows),'max_concurrent_out':count,
                    'scrolling_concurrency_limit':limit,'scrolling_events_dropped':0},'warnings':[]})
    with Path(__file__).with_suffix('.jsonl').open('a') as log:
        log.write(json.dumps([source.parent.name,source.name])+'\n')
stats_path.write_text(json.dumps({'tracks':records}))
'''


@unittest.skipUnless(shutil.which("mkvmerge") and shutil.which("mkvextract"), "MKVToolNix required")
class RealSeriesChecks(unittest.TestCase):
    def test_consistent_add_with_absent_tracks_and_unchanged_replace_and_all_modes(self):
        merge = shutil.which("mkvmerge")
        font = Path(os.environ.get("SIMPLIFY_SUBTITLES_TEST_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        self.assertTrue(font.is_file(), "Required fixture font: DejaVu Sans regular")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media, scratch = root / "media", root / "temporary"
            media.mkdir()
            scratch.mkdir()
            engine = root / "test_engine.py"
            engine.write_text(TEST_ENGINE)
            sources = []
            for episode in (1, 2, 3):
                source = media / f"[Group{episode}] Show Episode{episode}.mkv"
                command = [merge, "-o", str(source), "--attachment-mime-type", "font/ttf",
                           "--attach-file", str(font)]
                for name in ("A", "B", "C"):
                    if episode == 3 and name == "A":
                        continue
                    long = name != "A" or episode == 2
                    text = "Text" * 16000 if long else "Short signs"
                    subtitle = root / f"{episode}-{name}.ass"
                    subtitle.write_text("[Script Info]\nScriptType: v4.00+\n" + f"Title: {name}\n"
                                        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Alignment, Outline, Shadow\n"
                                        "Style: Default,DejaVu Sans,24,&H00FFFFFF&,2,0,0\n[Events]\n"
                                        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" +
                                        f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{text}\n" +
                                        (f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{text}\n" if name != "C" else ""))
                    command += ["--track-name", "0:" + name, "--language", "0:en", str(subtitle)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
                sources.append(source)
            hashes = {source: hashlib.sha256(source.read_bytes()).hexdigest() for source in sources}
            base = ["-i", str(media), "--simplifier", str(engine), "--temp-dir", str(scratch), "--yes"]
            actual_extract = wrapper.extract_items
            def extract(*args):
                self.assertEqual(list(scratch.rglob("*.mkv")), [])
                return actual_extract(*args)
            report_path = root / "series.json"
            with patch.object(wrapper, "extract_items", side_effect=extract) as extraction, \
                 patch("sys.stdout", new_callable=io.StringIO) as console:
                status = wrapper.main(base + ["-o", str(root / "consistent"), "--report", str(report_path)])
            self.assertEqual(status, 0, console.getvalue())
            assessment, writing = console.getvalue().split("Batch subtitle groups:", 1)
            first_episode = assessment.split("[Assess 2/", 1)[0]
            self.assertIn("Simplifying 3 subtitle track(s)...", first_episode)
            self.assertIn("Track 0 (A):", first_episode)
            self.assertNotIn("Retaining", assessment)
            self.assertNotIn("Simplifying", writing)
            self.assertEqual(len([call for call in extraction.call_args_list if call.args[2] == "tracks"]), 3)
            self.assertEqual(len([call for call in extraction.call_args_list if call.args[2] == "attachments"]), 3)
            self.assertEqual(list(scratch.iterdir()), [])
            data = json.loads(report_path.read_text())
            self.assertTrue(data["GroupConsistency"])
            groups = {item["Name"]: item for item in data["Groups"]}
            self.assertEqual((groups["A"]["QualifyingFiles"], groups["A"]["PresentFiles"]), (1, 2))
            self.assertTrue(groups["A"]["Selected"])
            self.assertTrue(groups["B"]["Selected"])
            self.assertFalse(groups["C"]["Selected"])
            for episode, source in enumerate(sources, 1):
                info = wrapper.identify(merge, root / "consistent" / source.name)
                names = [t["properties"].get("track_name") for t in info["tracks"]]
                self.assertIn("B (Simplified)", names)
                self.assertEqual("A (Simplified)" in names, episode != 3)
                self.assertNotIn("C (Simplified)", names)
            forced = next(t for t in data["Tracks"] if t["File"] == str(sources[0]) and t["Name"] == "A")
            self.assertTrue(forced["SelectedForRemux"])
            self.assertFalse(forced["QualifiedIndividually"])
            calls = Counter(tuple(json.loads(line)) for line in engine.with_suffix(".jsonl").read_text().splitlines())
            self.assertTrue(all(count == 1 for count in calls.values()))
            for label, options in (("replace", ["--replace-originals"]), ("all", ["--process-all-tracks"])):
                report = root / (label + ".json")
                with patch.object(wrapper, "scan_batch") as scan, patch("sys.stdout", new_callable=io.StringIO) as console:
                    status = wrapper.main(base + ["-o", str(root / label), "--report", str(report)] + options)
                self.assertEqual(status, 0, console.getvalue())
                scan.assert_not_called()
                result = json.loads(report.read_text())
                self.assertFalse(result["GroupConsistency"])
                first_names = [t["properties"].get("track_name") for t in wrapper.identify(merge, root / label / sources[0].name)["tracks"]]
                if label == "all":
                    self.assertIn("C (Simplified)", first_names)
                    self.assertIn("A (Simplified)", first_names)
                else:
                    self.assertEqual(first_names, ["A", "B", "C"])
                    self.assertEqual([t["Name"] for t in result["Tracks"] if t["File"] == str(sources[0]) and t["SelectedForRemux"]], ["B"])
                self.assertEqual(list(scratch.iterdir()), [])
            with patch.object(wrapper, "verify_output", side_effect=RuntimeError("verification failed")), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(wrapper.main(base + ["-o", str(root / "broken")]), 1)
            self.assertEqual(list(scratch.iterdir()), [])
            self.assertEqual(list((root / "broken").iterdir()), [])
            for source, expected in hashes.items():
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
