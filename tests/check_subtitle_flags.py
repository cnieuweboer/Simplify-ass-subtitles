"""Focused menu and in-place flag checks; no user media is modified."""

from copy import deepcopy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
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
    def test_duplicate_catalog_and_layout_warnings(self):
        from copy import deepcopy
        first = {"tracks": [track(3), track(5)]}
        for entry in first["tracks"]:
            entry["properties"]["track_name"] = ""
        second = deepcopy(first)
        for entry in second["tracks"]:
            entry["id"] += 10
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            catalog, duplicates = flags.subtitle_catalog([first, second])
        self.assertEqual(len(catalog), 2)
        self.assertEqual([key[3] for key in catalog], [1, 2])
        self.assertNotIn("WARNING:", output.getvalue())
        self.assertIn("occurrence 2", flags.group_label(catalog[1]))
        self.assertEqual(list(flags.subtitle_groups(first, duplicates).values()), catalog)
        self.assertEqual(list(flags.subtitle_groups(second, duplicates).values()), catalog)
        # Missing peer, missing entire group, different name/codec/language, reordered layout.
        for variant in ({"tracks": second["tracks"][:1]}, {"tracks": []}):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                _, other_duplicates = flags.subtitle_catalog([first, variant])
            self.assertEqual(duplicates, other_duplicates)
            self.assertIn("Cannot verify subtitle groups", output.getvalue())
        for field, value in (("track_name", "Signs"), ("language", "jpn"),
                             ("codec_id", "S_TEXT/UTF8")):
            variant = deepcopy(second)
            if field == "language":
                variant["tracks"][0]["properties"].pop("language_ietf", None)
            variant["tracks"][0]["properties"][field] = value
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                flags.subtitle_catalog([first, variant])
            self.assertIn("Cannot verify subtitle groups", output.getvalue())
        other = deepcopy(second["tracks"][0])
        other["id"] = 99
        other["properties"]["track_name"] = "Signs"
        for variant in ({"tracks": [other, *second["tracks"]]},
                        {"tracks": [*second["tracks"], other]}):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                flags.subtitle_catalog([{"tracks": [other, *first["tracks"]]}, variant])
            self.assertEqual("WARNING:" in output.getvalue(), variant["tracks"][0] != other)
        with patch("sys.stdout", new_callable=io.StringIO):
            groups = flags.subtitle_groups({"tracks": first["tracks"][:1]}, duplicates)
        self.assertEqual(list(groups.values()), catalog[:1])

    def test_duplicate_selection_only_changes_selected_occurrence(self):
        info = {"tracks": [track(2), track(4)]}
        for entry in info["tracks"]:
            entry["properties"]["track_name"] = ""
        with patch("sys.stdout", new_callable=io.StringIO):
            catalog, duplicates = flags.subtitle_catalog([info])
        self.assertEqual(flags.desired_flags(info, True, True, {catalog[1]}, {catalog[0]}, duplicates),
                         {2: (False, True), 4: (True, False)})
        with tempfile.TemporaryDirectory() as folder:
            for name in ("a.mkv", "b.mkv"):
                Path(folder, name).touch()
            with patch.object(flags.shutil, "which", return_value="tool"), \
                 patch.object(flags, "identify", return_value=info), \
                 patch.object(flags, "edit_file", return_value=True) as edit, \
                 patch("builtins.input", side_effect=["1", "2", "y"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(flags.main([folder]), 0)
            self.assertEqual(edit.call_count, 2)
            for call in edit.call_args_list:
                self.assertEqual(call.args[4:6], ({catalog[1]}, {catalog[1]}))
                self.assertEqual(call.kwargs["duplicate_keys"], duplicates)
            self.assertIn("occurrence 1", output.getvalue())
            self.assertIn("occurrence 2", output.getvalue())

    def test_single_key_fallback_ignores_unlisted_answers(self):
        with patch.object(sys.stdin, "isatty", return_value=False), \
             patch("builtins.input", side_effect=["3", "12", "yes", "Y"]) as read:
            self.assertEqual(flags.single_key("Proceed: ", ("y", "n")), "y")
            self.assertEqual(read.call_count, 4)

    def test_single_key_windows_ignores_extended_keys(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        console = SimpleNamespace(getwch=Mock(side_effect=["\xe0", "1", "9", "\r", "2"]))
        with patch.object(sys.stdin, "isatty", return_value=True), \
             patch.object(sys, "platform", "win32"), \
             patch.dict(sys.modules, {"msvcrt": console}), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(flags.single_key("Choose: ", ("1", "2", "q")), "2")
            self.assertEqual(console.getwch.call_count, 5)

    @unittest.skipIf(os.name == "nt", "POSIX terminal check")
    def test_single_key_terminal_without_enter_and_restoration(self):
        import select
        import termios
        master, slave = os.openpty()
        previous = termios.tcgetattr(slave)
        script = ("import subtitle_flags as w; "
                  "print('RESULT=' + w.single_key('Choose: ', ('1','2','q')))")
        process = subprocess.Popen([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                                   stdin=slave, stdout=slave, stderr=slave)
        try:
            output = b""
            while b"Choose: " not in output:
                self.assertTrue(select.select([master], [], [], 5)[0], "Prompt timed out")
                output += os.read(master, 4096)
            # Enter, an invalid digit and a function-key sequence must not select 1.
            os.write(master, b"\r9\x1b[11~")
            self.assertFalse(select.select([master], [], [], 0.15)[0])
            os.write(master, b"2")
            process.wait(timeout=5)
            while select.select([master], [], [], 0.1)[0]:
                output += os.read(master, 4096)
            self.assertEqual(process.returncode, 0, output)
            self.assertIn(b"RESULT=2", output)
            self.assertEqual(termios.tcgetattr(slave), previous)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

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

    def test_menu_rejects_keys_outside_its_current_options(self):
        with patch.object(sys.stdin, "isatty", return_value=False), \
             patch("builtins.input", side_effect=["4", "3", "12", "2"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(flags.choice("Default flags", ["Remove default", "Keep default"]), 2)
        with patch.object(sys.stdin, "isatty", return_value=False), \
             patch("builtins.input", return_value="q"), \
             patch("sys.stdout", new_callable=io.StringIO), self.assertRaises(EOFError):
            flags.choice("Default flags", ["Remove default", "Keep default"])

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
