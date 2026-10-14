"""Single-file inputs must never scan or modify neighboring MKVs."""

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
TOOLS = ("subtitle_flags", "remove_subtitles", "sync_fonts", "simplify_subtitles")
modules = {}
for name in TOOLS:
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    modules[name] = module

INFO = {"tracks": [{"id": 0, "type": "subtitles", "properties": {
    "number": 1, "codec_id": "S_TEXT/ASS", "language_ietf": "en", "track_name": "English",
    "default_track": False, "forced_track": False}}]}


class SingleFileChecks(unittest.TestCase):
    def test_positional_and_input_aliases_route_only_selected_file(self):
        for name, module in modules.items():
            for alias in (None, "-i", "--input-dir"):
                with self.subTest(tool=name, alias=alias), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    source = root / "chosen episode.MKV"
                    source.touch()
                    (root / "another.mkv").touch()
                    args = ([alias] if alias else []) + [str(source)]
                    with patch("sys.stdout", new_callable=io.StringIO):
                        if name == "subtitle_flags":
                            with patch.object(module.shutil, "which", return_value="tool"), \
                                 patch.object(module, "identify", return_value=INFO) as scan, \
                                 patch.object(module, "edit_file", return_value=True) as edit, \
                                 patch("builtins.input", side_effect=["3", "y"]):
                                self.assertEqual(module.main(args), 0)
                            scan.assert_called_once_with(source)
                            self.assertEqual(edit.call_args.args[0], source)
                        elif name == "remove_subtitles":
                            with patch.object(module.shutil, "which", return_value="tool"), \
                                 patch.object(module, "identify", return_value=INFO) as scan, \
                                 patch.object(module, "find_files") as find, \
                                 patch.object(module, "remux", return_value=True) as remux, \
                                 patch("builtins.input", side_effect=["1", "y"]):
                                self.assertEqual(module.main(args + ["--recursive"]), 0)
                            find.assert_not_called()
                            scan.assert_called_once_with("tool", source)
                            self.assertEqual(remux.call_args.args[1].path, source)
                            self.assertEqual(remux.call_args.args[2], root / "output" / source.name)
                        elif name == "sync_fonts":
                            with patch.object(module, "find_tool", side_effect=lambda name: name), \
                                 patch.object(module, "inspect_fonts", return_value={}) as scan, \
                                 patch.object(module, "scan_local_fonts") as fonts, \
                                 patch.object(module, "choose_plans", return_value={source: {}}), \
                                 patch.object(module, "process", return_value="unchanged") as process:
                                self.assertEqual(module.main(args), 0)
                            scan.assert_called_once_with(source, "mkvmerge", "mkvextract")
                            self.assertEqual(fonts.call_args.args[1], root)
                            self.assertEqual(process.call_args.args[:2], (source, root / "output"))
                        else:
                            engine = root / "engine.py"
                            engine.touch()
                            with patch.object(module, "find_tool", side_effect=lambda name, _: name), \
                                 patch.object(module, "run", return_value="--stats-json --suffix --scroll-concurrency-limit"), \
                                 patch.object(module, "find_files") as find, \
                                 patch.object(module, "scan_batch", return_value={}) as scan, \
                                 patch.object(module, "process_batch") as process:
                                self.assertEqual(module.main(args + ["--simplifier", str(engine), "--yes", "--recursive"]), 0)
                            find.assert_not_called()
                            self.assertEqual(scan.call_args.args[:3], ([source], root, root / "output"))
                            self.assertEqual(process.call_args.args[:3], ([source], root, root / "output"))

    def test_invalid_file_missing_input_and_conflicting_aliases(self):
        for name, module in modules.items():
            with self.subTest(tool=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                invalid = root / "subtitle.ass"
                invalid.touch()
                with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
                    self.assertNotEqual(module.main(["-i", str(invalid)]), 0)
                    self.assertNotEqual(module.main(["-i", str(root / "missing.mkv")]), 0)
                    with self.assertRaises(SystemExit):
                        module.main([folder, "-i", folder])
                self.assertFalse((root / "output").exists())

    def test_single_file_custom_output_and_font_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "episode.mkv"
            source.touch()
            fonts = root / "loose fonts"
            fonts.mkdir()
            output = root / "cleaned"
            sync = modules["sync_fonts"]
            with patch.object(sync, "find_tool", side_effect=lambda name: name), \
                 patch.object(sync, "inspect_fonts", return_value={}), \
                 patch.object(sync, "scan_local_fonts") as scan_fonts, \
                 patch.object(sync, "choose_plans", return_value={source: {}}), \
                 patch.object(sync, "process", return_value="unchanged") as process, \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(sync.main(["-i", str(source), "-o", str(output), "-f", str(fonts)]), 0)
            self.assertEqual(scan_fonts.call_args.args[1], fonts)
            self.assertEqual(process.call_args.args[:2], (source, output))

    def test_real_single_file_remux_and_in_place_flags(self):
        merge = shutil.which("mkvmerge")
        self.assertTrue(merge and shutil.which("mkvextract") and shutil.which("mkvpropedit"), "MKVToolNix required")
        font = Path(os.environ.get("SIMPLIFY_SUBTITLES_TEST_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        self.assertTrue(font.is_file(), "Set SIMPLIFY_SUBTITLES_TEST_FONT to a real TTF")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, neighbor = root / "chosen.MKV", root / "neighbor.mkv"
            subtitle = root / "input.srt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n")
            result = subprocess.run([merge, "-o", str(source), "--attachment-mime-type", "font/ttf",
                                     "--attach-file", str(font), "--language", "0:en", "--track-name", "0:English",
                                     str(subtitle), "--language", "0:de", "--track-name", "0:German", str(subtitle)],
                                    capture_output=True, text=True)
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
            shutil.copyfile(source, neighbor)
            neighbor_hash = hashlib.sha256(neighbor.read_bytes()).hexdigest()
            with patch("sys.stdout", new_callable=io.StringIO), patch("builtins.input", side_effect=["1", "3", "y"]):
                self.assertEqual(modules["subtitle_flags"].main(["-i", str(source)]), 0)
            info = json.loads(subprocess.check_output([merge, "-J", str(source)]))
            self.assertTrue(all(not t["properties"]["default_track"] for t in info["tracks"]))
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            removed = root / "removed"
            with patch("sys.stdout", new_callable=io.StringIO), patch("builtins.input", side_effect=["1", "y"]):
                self.assertEqual(modules["remove_subtitles"].main(["-i", str(source), "-o", str(removed)]), 0)
            output_info = json.loads(subprocess.check_output([merge, "-J", str(removed / source.name)]))
            self.assertEqual([t["properties"]["track_name"] for t in output_info["tracks"]], ["German"])
            engine = Path(os.environ.get("SIMPLIFY_SUBTITLES_TEST_ENGINE", ROOT / "simplify_ass.py"))
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(modules["simplify_subtitles"].main(["-i", str(source), "--yes", "--simplifier", str(engine)]), 0)
            self.assertEqual(hashlib.sha256((root / "output" / source.name).read_bytes()).hexdigest(), source_hash)
            cleaned = root / "fonts cleaned"
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(modules["sync_fonts"].main(["-i", str(source), "-o", str(cleaned)]), 0)
            output_info = json.loads(subprocess.check_output([merge, "-J", str(cleaned / source.name)]))
            self.assertEqual(output_info["attachments"], [])
            self.assertEqual(len(output_info["tracks"]), 2)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)
            self.assertEqual(hashlib.sha256(neighbor.read_bytes()).hexdigest(), neighbor_hash)
            self.assertFalse(any((p / neighbor.name).exists() for p in (root / "output", removed, cleaned)))


if __name__ == "__main__":
    unittest.main()
