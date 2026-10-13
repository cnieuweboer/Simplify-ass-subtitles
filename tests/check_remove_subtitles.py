"""Removal detection/menu checks and optional real MKVToolNix remux checks."""

from copy import deepcopy
import hashlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

spec = importlib.util.spec_from_file_location(
    "remove_subtitles", Path(__file__).resolve().parents[1] / "remove_subtitles.py")
remove = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = remove
spec.loader.exec_module(remove)


def track(track_id, name="English", language="en", codec="S_TEXT/ASS", kind="subtitles"):
    return {"id": track_id, "type": kind, "properties": {
        "track_name": name, "language_ietf": language, "codec_id": codec,
        "uid": track_id + 100, "default_track": False, "forced_track": False}}


class RemovalChecks(unittest.TestCase):
    def test_same_language_pairs_and_unnamed_originals(self):
        info = {"tracks": [track(0, "English", codec="S_TEXT/SSA"),
                           track(1, "English (Simplified)"),
                           track(2, "English (Simplified)", "fr"),
                           track(3, "", "ja", "S_TEXT/UTF8"),
                           track(4, "Simplified", "ja"),
                           track(5, "Simplified", "de"),
                           track(6, "Orphan (Simplified)"),
                           track(7, "English  (simplified)"),
                           track(8, "English(Simplified)"),
                           track(9, "Orphan", kind="audio")]}
        self.assertEqual(remove.simplified_pairs(info), {1: [0], 4: [3], 7: [0]})

    def test_manual_grouping_and_multiselection(self):
        a = remove.subtitle_key(track(1))
        b = remove.subtitle_key(track(2, codec="S_TEXT/UTF8"))
        self.assertNotEqual(a, b)
        self.assertEqual(a, remove.subtitle_key(track(17)))
        with patch("builtins.input", side_effect=["0", "3", "abc", "1,2 1"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.manual_selection([a, b]), {a, b})

    def test_recursion_excludes_output_trees(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("a.MKV", "season/b.mkv", "output/old.mkv", "season/output/old.mkv",
                         "custom/old.mkv", "ignore.txt"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual(remove.find_files(root, root / "custom", False), [root / "a.MKV"])
            self.assertEqual(remove.find_files(root, root / "custom", True),
                             [root / "a.MKV", root / "season/b.mkv"])

    def test_confirmation_and_switch_to_manual(self):
        info = {"tracks": [track(3), track(9, "English (Simplified)")]}
        for answers, wanted in ((["2", "m", "1", "y"], {3}),
                                (["2", "n"], None),
                                (["1", "2", "y"], {9})):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder, "episode.mkv")
                path.write_bytes(b"source")
                with patch.object(remove.shutil, "which", return_value="mkvmerge"), \
                     patch.object(remove, "identify", return_value=info), \
                     patch.object(remove, "remux", return_value=True) as remux, \
                     patch("builtins.input", side_effect=answers), \
                     patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(remove.main([folder]), 0)
                if wanted is None:
                    remux.assert_not_called()
                else:
                    self.assertEqual(remux.call_args.args[3], wanted)
                self.assertIn("KEEP ID", output.getvalue())
                self.assertIn("REMOVE ID", output.getvalue())
                self.assertEqual(path.read_bytes(), b"source")
                self.assertFalse(Path(folder, "output").exists())

    def test_input_and_output_aliases(self):
        for input_option, output_option in (("-i", "-o"), ("--input-dir", "--output-dir")):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                media = root / "media"
                media.mkdir()
                source = media / "episode.mkv"
                source.touch()
                output = root / "cleaned"
                info = {"tracks": [track(3)]}
                with patch.object(remove.shutil, "which", return_value="mkvmerge"), \
                     patch.object(remove, "identify", return_value=info) as identify, \
                     patch.object(remove, "remux", return_value=True) as remux, \
                     patch("builtins.input", side_effect=["1", "y"]), \
                     patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(remove.main([input_option, str(media),
                                                  output_option, str(output)]), 0)
                identify.assert_called_once_with("mkvmerge", source)
                self.assertEqual(remux.call_args.args[1].path, source)
                self.assertEqual(remux.call_args.args[2], output / source.name)

    def test_conflicting_input_forms_are_rejected(self):
        with patch("sys.stderr", new_callable=io.StringIO), \
             patch.object(remove, "find_files") as scan:
            with self.assertRaises(SystemExit) as raised:
                remove.main(["media", "--input-dir", "other-media"])
            self.assertEqual(raised.exception.code, 2)
            scan.assert_not_called()

    def test_no_pairs_skips_option_one_and_cancel_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "episode.mkv").touch()
            with patch.object(remove.shutil, "which", return_value="mkvmerge"), \
                 patch.object(remove, "identify", return_value={"tracks": [track(3)]}), \
                 patch.object(remove, "removal_mode") as mode, \
                 patch.object(remove, "remux") as remux, \
                 patch("builtins.input", return_value=""), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(remove.main([folder]), 0)
            mode.assert_not_called()
            remux.assert_not_called()
            self.assertFalse(Path(folder, "output").exists())

    def test_verification_uses_track_identity_not_renumbered_ids(self):
        before = {"tracks": [track(3), track(9, "English (Simplified)")]}
        after = deepcopy(before)
        after["tracks"] = [after["tracks"][0]]
        after["tracks"][0]["id"] = 0
        remove.verify_output(before, after, {9})
        after["tracks"][0]["properties"]["default_track"] = True
        with self.assertRaises(RuntimeError):
            remove.verify_output(before, after, {9})

    def test_existing_outputs_source_changes_and_failed_remux(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "source.mkv")
            path.write_bytes(b"source")
            target = Path(folder, "output", "source.mkv")
            target.parent.mkdir()
            info = {"tracks": [track(0), track(1, "English (Simplified)")]}
            item = remove.ScannedFile(path, info, remove.file_stamp(path), {1: [0]})
            target.write_bytes(b"existing output")
            with patch.object(remove.subprocess, "run") as run, \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertFalse(remove.remux("tool", item, target, {1}))
                run.assert_not_called()
            self.assertEqual(target.read_bytes(), b"existing output")
            target.unlink()
            path.write_bytes(b"changed source")
            with self.assertRaises(RuntimeError):
                remove.remux("tool", item, target, {1})
            item.stamp = remove.file_stamp(path)
            with patch.object(remove.subprocess, "run", return_value=subprocess.CompletedProcess([], 2)):
                with self.assertRaises(RuntimeError):
                    remove.remux("tool", item, target, {1})
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.iterdir()), [])
            self.assertEqual(path.read_bytes(), b"changed source")

    def test_warning_output_is_verified_and_bad_output_is_discarded(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, "source.mkv")
            source.write_bytes(b"source")
            info = {"tracks": [track(0), track(1, "English (Simplified)")]}
            item = remove.ScannedFile(source, info, remove.file_stamp(source), {1: [0]})
            target = Path(folder, "output", "source.mkv")
            good = {"tracks": [deepcopy(info["tracks"][0])]}
            def run(args):
                Path(args[args.index("-o") + 1]).write_bytes(b"remuxed")
                return subprocess.CompletedProcess(args, 1)
            for after, valid in ((info, False), (good, True)):
                with patch.object(remove.subprocess, "run", side_effect=run), \
                     patch.object(remove, "identify", return_value=after), \
                     patch("sys.stdout", new_callable=io.StringIO):
                    if valid:
                        self.assertTrue(remove.remux("tool", item, target, {1}))
                    else:
                        with self.assertRaises(RuntimeError):
                            remove.remux("tool", item, target, {1})
                        self.assertFalse(target.exists())
                        self.assertEqual(list(target.parent.iterdir()), [])
            self.assertEqual(target.read_bytes(), b"remuxed")


@unittest.skipUnless(shutil.which("mkvmerge"), "MKVToolNix is required for real remux checks")
class RealRemuxChecks(unittest.TestCase):
    def test_real_remux_preserves_original_audio_flags_chapters_and_attachment(self):
        tool = shutil.which("mkvmerge")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wav = root / "audio.wav"
            with wave.open(str(wav), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(b"\x00\x00" * 8000)
            srt = root / "original.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nOriginal\n", encoding="utf-8")
            ass = root / "simplified.ass"
            ass.write_text("[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\n"
                           "Format: Name, Fontname, Fontsize, PrimaryColour, Alignment, Outline, Shadow\n"
                           "Style: Default,Arial,20,&H00FFFFFF&,2,0,0\n[Events]\n"
                           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                           "Dialogue: 0,0:00:00.00,0:00:00.90,Default,,0,0,0,,Simplified\n",
                           encoding="utf-8")
            chapters = root / "chapters.txt"
            chapters.write_text("CHAPTER01=00:00:00.000\nCHAPTER01NAME=Start\n")
            attached = root / "attachment.txt"
            attached.write_text("An attachment to preserve\n")
            source = root / "episode.mkv"
            media = wav
            if shutil.which("ffmpeg"):
                # A tiny video track tests that subtitle selection never drops video.
                media = root / "av.mkv"
                subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                                "color=c=black:s=16x16:r=2:d=1", "-i", str(wav),
                                "-c:v", "ffv1", "-c:a", "copy", str(media)], check=True,
                               capture_output=True)
            args = [tool, "-o", str(source), "--chapters", str(chapters),
                    "--attachment-mime-type", "text/plain", "--attach-file", str(attached), str(media)]
            for name, language, subtitle in (("English", "en", srt),
                                             ("English (Simplified)", "en", ass),
                                             ("", "ja", srt), ("Simplified", "ja", ass),
                                             ("Orphan (Simplified)", "de", ass)):
                args += ["--track-name", "0:" + name, "--language", "0:" + language,
                         "--default-track-flag", "0:0", "--forced-display-flag", "0:0", str(subtitle)]
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
            before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            before = remove.identify(tool, source)
            pairs = remove.simplified_pairs(before)
            self.assertEqual(len(pairs), 2)
            item = remove.ScannedFile(source, before, remove.file_stamp(source), pairs)
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertTrue(remove.remux(tool, item, root / "output" / source.name, set(pairs)))
            after = remove.identify(tool, root / "output" / source.name)
            self.assertEqual(len(after["tracks"]), len(before["tracks"]) - 2)
            self.assertIn("Orphan (Simplified)", [remove.subtitle_key(t)[0] for t in after["tracks"]])
            # Exercise removing all subtitles too; audio, attachment and chapters remain.
            all_subs = {t["id"] for t in before["tracks"] if t["type"] == "subtitles"}
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertTrue(remove.remux(tool, item, root / "all-removed.mkv", all_subs))
            stripped = remove.identify(tool, root / "all-removed.mkv")
            self.assertEqual([t["type"] for t in stripped["tracks"]],
                             [t["type"] for t in before["tracks"] if t["type"] != "subtitles"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before_hash)
            self.assertEqual(list((root / "output").glob("*.partial.mkv")), [])


if __name__ == "__main__":
    unittest.main()
