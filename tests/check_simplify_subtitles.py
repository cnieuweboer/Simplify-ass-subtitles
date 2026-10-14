"""Check batch-wrapper policy, menus, and real MKV extraction/remux contracts."""

from copy import deepcopy
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
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("simplify_subtitles", ROOT / "simplify_subtitles.py")
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


class WrapperChecks(unittest.TestCase):
    def test_defaults_and_strict_reduction_thresholds(self):
        args = wrapper.parser().parse_args([])
        self.assertEqual(args.scroll_concurrency_limit, 0)
        self.assertEqual(args.minimum_subtitle_bytes, 50000)
        self.assertEqual(args.minimum_event_reduction_percent, 10)
        self.assertFalse(wrapper.passed_reduction({"original": 100, "output": 90}, 10)[0])
        self.assertTrue(wrapper.passed_reduction({"original": 100, "output": 89}, 10)[0])
        self.assertFalse(wrapper.passed_reduction({"original": 0, "output": 0}, 0)[0])
        for stats in ({}, {"original": -1, "output": 0}, {"original": 1, "output": "0"}):
            with self.assertRaises(RuntimeError):
                wrapper.passed_reduction(stats, 10)

    def test_markers_only_in_header_with_unicode_encodings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "track.ass")
            for encoding in ("utf-8-sig", "utf-16", "utf-32"):
                path.write_text("[Script Info]\n" + "\n" * 1000 + wrapper.GENERATED_MARKER +
                                "\n[V4+ Styles]\n", encoding=encoding)
                self.assertTrue(wrapper.has_generated_marker(path))
            path.write_text("[Script Info]\n[V4+ Styles]\n[Events]\n" + wrapper.GENERATED_MARKER)
            self.assertFalse(wrapper.has_generated_marker(path))

    def test_stats_aliases_preserve_current_and_missing_values(self):
        self.assertEqual(wrapper.normalize_stats({"prototype_scrolling_events_removed": 3}),
                         {"scrolling_events_dropped": 3})
        self.assertEqual(wrapper.normalize_stats({"scrolling_events_dropped": 0,
                                                  "prototype_scrolling_events_removed": 3}),
                         {"scrolling_events_dropped": 0})
        self.assertNotIn("scrolling_events_dropped", wrapper.normalize_stats({}))

    def test_child_output_is_quiet_but_warnings_and_failures_remain_visible(self):
        code = ("import sys; print('duplicate layers removed: 42'); "
                "print('Exact fonts unavailable (kept positions): Missing Family'); "
                "sys.stderr.write('WARNING: a meaningful warning\\n')")
        with patch("sys.stdout", new_callable=io.StringIO) as console:
            wrapper.run([sys.executable, "-c", code], "subtitle simplification", warnings_ok=False)
        self.assertNotIn("duplicate layers removed", console.getvalue())
        self.assertIn("Missing Family", console.getvalue())
        self.assertIn("a meaningful warning", console.getvalue())
        with self.assertRaises(RuntimeError) as raised:
            wrapper.run([sys.executable, "-c",
                         "import sys; print('filters: 42'); sys.stderr.write('ERROR: broken input\\n'); sys.exit(2)"],
                        "subtitle simplification", warnings_ok=False)
        self.assertIn("broken input", str(raised.exception))
        self.assertNotIn("filters: 42", str(raised.exception))

    def test_event_and_concurrency_summary_does_not_invent_missing_counts(self):
        track = {"id": 3, "properties": {"track_name": "Full"}}
        stats = {"original": 100, "output": 60, "max_concurrent_in": 20, "max_concurrent_out": 5}
        with patch("sys.stdout", new_callable=io.StringIO) as console:
            wrapper.track_summary(track, stats, True)
        self.assertIn("events 100 -> 60 (-40.0%)", console.getvalue())
        self.assertIn("peak concurrency 20 -> 5 (-75.0%)", console.getvalue())
        with patch("sys.stdout", new_callable=io.StringIO) as console:
            wrapper.track_summary(track, {}, False)
        self.assertIn("events unavailable", console.getvalue())
        self.assertIn("peak concurrency unavailable", console.getvalue())

    def test_converted_subtitle_formats(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "converted.ass")
            for script_type, codec in (("v4.00", "S_TEXT/SSA"), ("v4.00+", "S_TEXT/ASS")):
                path.write_text(f"[Script Info]\nScriptType: {script_type}\n[Events]\n")
                self.assertEqual(wrapper.converted_codec(path), codec)
            path.write_text("[Script Info]\n[Events]\n")
            with self.assertRaises(RuntimeError):
                wrapper.converted_codec(path)

    def test_recursive_scan_excludes_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("one.MKV", "season/two.mkv", "output/old.mkv", "season/output/old.mkv", "custom/old.mkv"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual(wrapper.find_files(root, root / "custom", True),
                             [root / "one.MKV", root / "season/two.mkv"])

    def test_tool_paths_are_absolute_for_extraction_working_directories(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            directory = Path(folder)
            executable = "mkvextract.exe" if os.name == "nt" else "mkvextract"
            tool = directory / executable
            tool.touch()
            relative = Path(os.path.relpath(directory, Path.cwd()))
            self.assertEqual(wrapper.find_tool("mkvextract", relative), str(tool.resolve()))

    def test_menu_choices_cancellation_and_no_argument_folder_default(self):
        for answers, mode, all_tracks, execute in ((["1", "1", "y"], "add", False, True),
                                                  (["2", "2", "y"], "replace", True, True),
                                                  (["1", "2", "n"], "add", True, False)):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / "episode.mkv").touch()
                (root / "simplify_ass.py").touch()
                with patch.object(wrapper, "__file__", str(root / "simplify_subtitles.py")), \
                     patch.object(wrapper, "find_tool", side_effect=lambda name, _: name), \
                     patch.object(wrapper, "run", return_value="--stats-json --suffix --scroll-concurrency-limit"), \
                     patch.object(wrapper, "process_file", return_value="copied unchanged") as process, \
                     patch("builtins.input", side_effect=answers), \
                     patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(wrapper.main([]), 0)
                if execute:
                    self.assertEqual(process.call_args.args[0], root / "episode.mkv")
                    self.assertEqual(process.call_args.args[2].mode, mode)
                    self.assertEqual(process.call_args.args[2].process_all_tracks, all_tracks)
                    self.assertEqual(process.call_args.args[2].scroll_concurrency_limit, 0)
                else:
                    process.assert_not_called()
                self.assertFalse((root / "output").exists())

    def test_validation_protects_sources_and_rejects_negative_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media = root / "episode.mkv"
            media.write_bytes(b"unchanged source")
            with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(wrapper.main(["-i", folder, "-o", folder]), 2)
                with self.assertRaises(SystemExit):
                    wrapper.main(["--scroll-concurrency-limit", "-1"])
                with self.assertRaises(SystemExit):
                    wrapper.main([folder, "-i", folder])
                self.assertEqual(wrapper.main([folder, "--report", str(media), "--yes"]), 2)
            self.assertEqual(media.read_bytes(), b"unchanged source")

    def test_verification_checks_metadata_order_and_attachments(self):
        before = {"tracks": [{"type": "subtitles", "properties": {
            "codec_id": "S_TEXT/ASS", "track_name": "Full", "language_ietf": "en", "uid": 5}}],
                  "attachments": [{"file_name": "font.ttf", "size": 10}]}
        after = deepcopy(before)
        wrapper.verify_output(before, after, [(before["tracks"][0], True)])
        after["tracks"][0]["properties"]["forced_track"] = True
        with self.assertRaises(RuntimeError):
            wrapper.verify_output(before, after, [(before["tracks"][0], True)])
        after = deepcopy(before)
        after["attachments"] = []
        with self.assertRaises(RuntimeError):
            wrapper.verify_output(before, after, [(before["tracks"][0], True)])


@unittest.skipUnless(shutil.which("mkvmerge") and shutil.which("mkvextract"), "MKVToolNix required")
class RealBatchChecks(unittest.TestCase):
    def test_add_replace_copy_thresholds_marker_skip_and_failure_cleanup(self):
        merge = shutil.which("mkvmerge")
        extract = shutil.which("mkvextract")
        engine = Path(os.environ.get("SIMPLIFY_SUBTITLES_TEST_ENGINE", ROOT / "simplify_ass.py")).resolve()
        font = Path(os.environ.get("SIMPLIFY_SUBTITLES_TEST_FONT",
                                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        self.assertTrue(font.is_file(), "Required synthetic-fixture font: DejaVu Sans regular")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media = root / "media"
            media.mkdir()
            wav = root / "audio.wav"
            with wave.open(str(wav), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(b"\0\0" * 8000)
            av = wav
            if shutil.which("ffmpeg"):
                av = root / "av.mkv"
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=16x16:r=2:d=1",
                                "-i", str(wav), "-c:v", "ffv1", "-c:a", "copy", str(av)],
                               capture_output=True, check=True)
            ass = root / "original.ass"
            ass.write_text("[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n"
                           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Alignment, Outline, Shadow\n"
                           "Style: Default,DejaVu Sans,24,&H00FFFFFF&,2,0,0\n[Events]\n"
                           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                           "Dialogue: 0,0:00:00.00,0:00:00.45,Default,,0,0,0,,{\\blur8}Hello subtitle\n"
                           "Dialogue: 0,0:00:00.45,0:00:00.90,Default,,0,0,0,,{\\blur8}Hello subtitle\n")
            srt = root / "other.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nUntouched SRT\n")
            chapters = root / "chapters.txt"
            chapters.write_text("CHAPTER01=00:00:00.000\nCHAPTER01NAME=Start\n")
            source = media / "episode.mkv"
            command = [merge, "-o", str(source), "--chapters", str(chapters),
                       "--attachment-mime-type", "font/ttf", "--attachment-name", "../unsafe/font.ttf",
                       "--attach-file", str(font), str(av),
                       "--track-name", "0:SRT", "--language", "0:de", str(srt),
                       "--track-name", "0:Full", "--language", "0:en", "--default-track-flag", "0:1",
                       "--forced-display-flag", "0:1", "--hearing-impaired-flag", "0:1", str(ass),
                       "--track-name", "0:", "--language", "0:und", "--default-track-flag", "0:0", str(ass)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
            before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            before = wrapper.identify(merge, source)
            base_args = ["-i", str(media), "--simplifier", str(engine), "--yes"]
            reports = {}
            for label, extra in (("add", ["--process-all-tracks"]),
                                 ("replace", ["--replace-originals", "--process-all-tracks"]),
                                 ("size-copy", []),
                                 ("reduction-copy", ["--minimum-subtitle-bytes", "0",
                                                      "--minimum-event-reduction-percent", "100"]),
                                 ("filtered", ["--minimum-subtitle-bytes", "0"]),
                                 ("explicit-limit", ["--process-all-tracks", "--scroll-concurrency-limit", "32"])):
                report = root / (label + ".json")
                with patch("sys.stdout", new_callable=io.StringIO) as console:
                    status = wrapper.main(base_args + ["-o", str(root / label), "--report", str(report)] + extra)
                self.assertEqual(status, 0, console.getvalue())
                reports[label] = json.loads(report.read_text())
                if label == "add":
                    self.assertIn("Extracting fonts... [1/1]", console.getvalue())
                    self.assertIn("events 2 -> 2", console.getvalue())
                    self.assertIn("peak concurrency 1 -> 1", console.getvalue())
                    self.assertNotIn("duplicate layers removed:", console.getvalue())
                    self.assertNotIn("mkvmerge v", console.getvalue())
                    self.assertNotIn("is written to", console.getvalue())
            added = wrapper.identify(merge, root / "add" / source.name)
            replaced = wrapper.identify(merge, root / "replace" / source.name)
            self.assertEqual(len(added["tracks"]), len(before["tracks"]) + 2)
            self.assertEqual(len(replaced["tracks"]), len(before["tracks"]))
            original = next(t for t in before["tracks"] if t["properties"].get("track_name") == "Full")
            replacement = next(t for t in replaced["tracks"] if t["properties"].get("track_name") == "Full")
            self.assertEqual(wrapper.signature(original), wrapper.signature(replacement))
            new_tracks = [t for t in added["tracks"] if t["properties"].get("track_name") in ("Full (Simplified)", "Simplified")]
            self.assertEqual(len(new_tracks), 2)
            self.assertTrue(all(not t["properties"]["default_track"] and not t["properties"]["forced_track"] for t in new_tracks))
            for label in ("size-copy", "reduction-copy"):
                self.assertEqual(hashlib.sha256((root / label / source.name).read_bytes()).hexdigest(), before_hash)
            for label in ("add", "replace"):
                self.assertTrue(all(t["SelectedForRemux"] for t in reports[label]["Tracks"]))
                self.assertTrue(all(t["Stats"]["scrolling_concurrency_limit"] == 0 for t in reports[label]["Tracks"]))
            self.assertTrue(all(not t["SelectedForRemux"] for t in reports["filtered"]["Tracks"]))
            self.assertEqual(hashlib.sha256((root / "filtered" / source.name).read_bytes()).hexdigest(), before_hash)
            self.assertTrue(all(t["Stats"]["scrolling_concurrency_limit"] == 32 for t in reports["explicit-limit"]["Tracks"]))
            converted = root / "roundtrip.ass"
            run = subprocess.run([extract, str(root / "replace" / source.name), "tracks", f"{replacement['id']}:{converted}"],
                                 capture_output=True, text=True)
            self.assertIn(run.returncode, (0, 1), run.stdout + run.stderr)
            self.assertIn("Hello subtitle", converted.read_text(encoding="utf-8-sig"))
            self.assertNotIn("\\blur8", converted.read_text(encoding="utf-8-sig"))
            # Replaced tracks have markers and are copied unchanged on another run.
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(wrapper.main(["-i", str(root / "replace"), "-o", str(root / "marked-copy"),
                                               "--simplifier", str(engine), "--process-all-tracks", "--yes"]), 0)
            self.assertEqual((root / "replace" / source.name).read_bytes(), (root / "marked-copy" / source.name).read_bytes())
            # Existing outputs are skipped and verification failures never publish a file.
            with patch.object(wrapper, "process_file") as process, patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(wrapper.main(base_args + ["-o", str(root / "add")]), 0)
                process.assert_not_called()
            with patch.object(wrapper, "verify_output", side_effect=RuntimeError("verification failed")), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(wrapper.main(base_args + ["-o", str(root / "bad"), "--process-all-tracks"]), 1)
            self.assertEqual(list((root / "bad").iterdir()), [])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before_hash)


if __name__ == "__main__":
    unittest.main()
