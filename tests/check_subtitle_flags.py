"""Focused menu and in-place flag checks; no user media is modified."""

from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "subtitle_flags", Path(__file__).resolve().parents[1] / "subtitle_flags.py")
flags = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flags)


def track(number, codec="S_TEXT/ASS", default=False, forced=False, kind="subtitles"):
    return {"id": number - 1, "type": kind, "properties": {
        "number": number, "track_name": "English", "language": "eng",
        "codec_id": codec, "default_track": default, "forced_track": forced}}


class FlagChecks(unittest.TestCase):
    def setUp(self):
        self.info = {"tracks": [track(1, kind="video", default=True),
                                track(3, default=True),
                                track(5, codec="S_TEXT/UTF8", forced=True)]}
        self.ass = flags.subtitle_key(self.info["tracks"][1])
        self.srt = flags.subtitle_key(self.info["tracks"][2])

    def test_flag_combinations_and_in_place_selectors(self):
        for clear_default in (False, True):
            for clear_forced in (False, True):
                for defaults in (set(), {self.ass}, {self.ass, self.srt}):
                    for forced in (set(), {self.srt}, {self.ass, self.srt}):
                        after = deepcopy(self.info)
                        expected = {
                            3: (self.ass in defaults or not clear_default, self.ass in forced),
                            5: (self.srt in defaults, self.srt in forced or not clear_forced),
                        }
                        def run(args, **kwargs):
                            self.assertEqual(args[:2], ["mkvpropedit", "episode.mkv"])
                            number = None
                            for i in range(2, len(args), 2):
                                option, value = args[i:i + 2]
                                if option == "--edit":
                                    number = int(value.removeprefix("track:@"))
                                    self.assertIn(number, (3, 5))
                                else:
                                    prop, val = value.split("=")
                                    target = next(t for t in after["tracks"]
                                                  if t["properties"]["number"] == number)
                                    target["properties"][{"flag-default": "default_track",
                                                           "flag-forced": "forced_track"}[prop]] = bool(int(val))
                            return subprocess.CompletedProcess(args, 0, "", "")
                        with patch.object(flags.subprocess, "run", side_effect=run), \
                             patch.object(flags, "identify", return_value=after), \
                             patch("sys.stdout", new_callable=io.StringIO):
                            flags.edit_file(Path("episode.mkv"), self.info, clear_default,
                                            clear_forced, defaults, forced)
                        self.assertEqual(flags.desired_flags(after, False, False, set(), set()), expected)
                        self.assertEqual(after["tracks"][0], self.info["tracks"][0])

    def test_verification_failure_and_tool_failure(self):
        for returncode in (0, 2):
            with patch.object(flags.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], returncode, "", "failed")), \
                 patch.object(flags, "identify", return_value=self.info):
                with self.assertRaises(RuntimeError):
                    flags.edit_file(Path("episode.mkv"), self.info, True, True, set(), set())

    def test_grouping_and_input(self):
        self.assertNotEqual(self.ass, self.srt)
        duplicate = track(10, default=True)
        self.assertEqual(self.ass, flags.subtitle_key(duplicate))
        with patch("builtins.input", side_effect=["0", "4", "abc", "1, 2 1"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(flags.selection("Select", [self.ass, self.srt]), {self.ass, self.srt})

    def test_menu_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "episode.MKV").touch()
            for remove in range(1, 5):
                for setting in range(1, 4):
                    answers = [str(remove), str(setting)]
                    if setting == 1:
                        answers += ["1,2"]
                    elif setting == 2:
                        answers += ["1", "2"]
                    answers += ["y"]
                    catalog = sorted([self.ass, self.srt])
                    with patch.object(flags.shutil, "which", return_value="tool"), \
                         patch.object(flags, "identify", return_value=self.info), \
                         patch.object(flags, "edit_file", return_value=True) as edit, \
                         patch("builtins.input", side_effect=answers), \
                         patch("sys.stdout", new_callable=io.StringIO):
                        self.assertEqual(flags.main([folder]), 0)
                    expected_defaults = set(catalog) if setting == 1 else {catalog[0]} if setting == 2 else set()
                    expected_forced = set(catalog) if setting == 1 else {catalog[1]} if setting == 2 else set()
                    self.assertEqual(edit.call_args.args[2:], (remove in (1, 3), remove in (1, 2),
                                                               expected_defaults, expected_forced))

    def test_cancel_does_not_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "episode.mkv").touch()
            with patch.object(flags.shutil, "which", return_value="tool"), \
                 patch.object(flags, "identify", return_value=self.info), \
                 patch.object(flags, "edit_file") as edit, \
                 patch("builtins.input", side_effect=["1", "3", "n"]), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(flags.main([folder]), 0)
                edit.assert_not_called()

    def test_removal_menu_only_offers_present_subtitle_flags(self):
        for default, forced, expected_labels, actions in (
                (False, False, [], [(False, False)]),
                (True, False, ["Remove default", "Keep default"], [(True, False), (False, False)]),
                (False, True, ["Remove forced", "Keep forced"], [(False, True), (False, False)])):
            for number, expected in enumerate(actions, 1):
                with self.subTest(default=default, forced=forced, choice=number), tempfile.TemporaryDirectory() as folder:
                    Path(folder, "episode.mkv").touch()
                    # Video flags must never cause a subtitle removal question.
                    info = {"tracks": [track(1, kind="video", default=True, forced=True),
                                       track(2, default=default, forced=forced)]}
                    answers = ([str(number)] if expected_labels else []) + ["3", "y"]
                    with patch.object(flags.shutil, "which", return_value="tool"), \
                         patch.object(flags, "identify", return_value=info), \
                         patch.object(flags, "edit_file", return_value=True) as edit, \
                         patch("builtins.input", side_effect=answers), \
                         patch("sys.stdout", new_callable=io.StringIO) as console:
                        self.assertEqual(flags.main([folder]), 0)
                    self.assertEqual(edit.call_args.args[2:4], expected)
                    output = console.getvalue()
                    for label in expected_labels:
                        self.assertIn(label, output)
                    if not default:
                        self.assertNotIn("Remove default", output)
                    if not forced:
                        self.assertNotIn("Remove forced", output)
                    if not expected_labels:
                        self.assertNotIn("Option 1:", output)
                        self.assertIn("skipping removal options", output)

    def test_flags_detected_across_files_and_missing_default_property(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("a.mkv", "b.mkv"):
                Path(folder, name).touch()
            first = {"tracks": [track(1)]}
            del first["tracks"][0]["properties"]["default_track"]
            second = {"tracks": [track(1, forced=True)]}
            with patch.object(flags.shutil, "which", return_value="tool"), \
                 patch.object(flags, "identify", side_effect=[first, second]), \
                 patch.object(flags, "edit_file", return_value=True) as edit, \
                 patch("builtins.input", side_effect=["1", "3", "y"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as console:
                self.assertEqual(flags.main([folder]), 0)
            self.assertIn("Remove default and forced", console.getvalue())
            self.assertEqual(edit.call_count, 2)
            self.assertTrue(all(call.args[2:4] == (True, True) for call in edit.call_args_list))


if __name__ == "__main__":
    unittest.main()
