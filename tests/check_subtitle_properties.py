"""Flag/rename menus, batch grouping, and real in-place edits of generated MKVs."""

from copy import deepcopy
import importlib.util
import hashlib
import io
import os
from pathlib import Path
import subprocess
import shutil
import wave
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "subtitle_properties", Path(__file__).resolve().parents[1] / "subtitle_properties.py")
flags = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flags)


def run_flags(argv):
    with patch.object(flags, "property_action", return_value="flags"):
        return flags.main(argv)


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
                self.assertEqual(run_flags([folder]), 0)
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
        script = ("import subtitle_properties as w; "
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
                        self.assertEqual(run_flags([folder]), 0)
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
                self.assertEqual(run_flags([folder]), 0)
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
                        self.assertEqual(run_flags([folder]), 0)
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
                self.assertEqual(run_flags([folder]), 0)
            self.assertIn("Remove default and forced", console.getvalue())
            self.assertEqual(edit.call_count, 2)
            self.assertTrue(all(call.args[2:4] == (True, True) for call in edit.call_args_list))


LANGUAGES = {"en": "English", "eng": "English", "de": "German", "und": "Undetermined"}


class RenameChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "episode.mkv"
        self.path.write_bytes(b"not user media")
        self.info = {"tracks": [track(1, kind="audio", default=True, forced=True),
                                track(2, default=True), track(3, forced=True)]}
        for entry in self.info["tracks"][1:]:
            entry["properties"]["track_name"] = ""
        with patch("sys.stdout", new_callable=io.StringIO):
            self.catalog, self.duplicates = flags.subtitle_catalog([self.info])

    def test_suggestions_use_language_names_and_avoid_existing_names(self):
        catalog = [("", "en", "S_TEXT/ASS", 1), ("", "en", "S_TEXT/ASS", 2),
                   ("", "en", "S_TEXT/UTF8"), ("English 1", "en", "S_TEXT/ASS"),
                   ("", "en-US", "S_TEXT/ASS"), ("", "und", "S_TEXT/ASS")]
        suggestions = flags.suggested_names(catalog, LANGUAGES)
        self.assertEqual([suggestions[key] for key in catalog],
                         ["English 2", "English 3", "English 4", "English 1", "English 1", "Undetermined 1"])
        self.assertEqual(flags.suggested_names([("", "xyz", "ASS")], {})[("", "xyz", "ASS")], "xyz 1")

    def test_default_custom_and_cleared_names(self):
        for answers, expected in ((["1,2", "", "Custom 日本語"], ["English 1", "Custom 日本語"]),
                                  (["1,2", "-", "-"], ["", ""])):
            with patch.object(flags, "language_names", return_value=LANGUAGES), \
                 patch("builtins.input", side_effect=answers), patch("sys.stdout", new_callable=io.StringIO):
                renames = flags.rename_selection(self.catalog)
            self.assertEqual([renames[key] for key in self.catalog], expected)
        named = [("Original", "en", "S_TEXT/ASS")]
        with patch.object(flags, "language_names") as languages, \
             patch("builtins.input", side_effect=["1", "Replacement"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(flags.rename_selection(named), {named[0]: "Replacement"})
        languages.assert_not_called()

    def test_edit_commands_target_occurrence_and_preserve_all_flags(self):
        after = deepcopy(self.info)
        after["tracks"][2]["properties"]["track_name"] = "English Signs"
        with patch.object(flags.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run, \
             patch.object(flags, "identify", return_value=after), patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(flags.edit_file(self.path, self.info, False, False, set(), set(),
                                            self.duplicates, {self.catalog[1]: "English Signs"}))
        self.assertEqual(run.call_args.args[0], ["mkvpropedit", str(self.path), "--edit", "track:@3",
                                                "--set", "name=English Signs"])
        self.assertEqual(self.info["tracks"][2]["properties"]["track_name"], "")

    def test_rename_verification_checks_unselected_properties_and_metadata(self):
        expected_flags = flags.desired_flags(self.info, False, False, set(), set())
        expected_names = flags.desired_names(self.info, {self.catalog[0]: "English 1"}, self.duplicates)
        good = deepcopy(self.info)
        good["tracks"][1]["properties"]["track_name"] = "English 1"
        flags.verify_properties(self.info, good, expected_flags, expected_names)
        for index, key, value in ((1, "track_name", "Wrong"), (2, "track_name", "Unselected changed"),
                                  (1, "default_track", False), (2, "forced_track", False),
                                  (0, "default_track", False), (0, "track_name", "Audio changed"),
                                  (1, "language", "jpn"), (1, "language_ietf", "en-US"),
                                  (1, "uid", 123), (1, "number", 9),
                                  (1, "flag_hearing_impaired", True)):
            bad = deepcopy(good)
            bad["tracks"][index]["properties"][key] = value
            with self.subTest(key=key, index=index), self.assertRaises(RuntimeError):
                flags.verify_properties(self.info, bad, expected_flags, expected_names)
        for field in ("attachments", "chapters", "global_tags", "track_tags"):
            bad = deepcopy(good)
            bad[field] = [{"changed": True}]
            with self.assertRaises(RuntimeError):
                flags.verify_properties(self.info, bad, expected_flags, expected_names)
        bad = dict(good, tracks=list(reversed(good["tracks"])))
        with self.assertRaises(RuntimeError):
            flags.verify_properties(self.info, bad, expected_flags, expected_names)

    def test_cancel_before_confirmation_never_changes_files(self):
        for answers in (["q"], ["2", "q"], ["2", "1,2", "English 1", "q"],
                        ["2", "1", "", "n"]):
            with patch.object(flags.shutil, "which", return_value="tool"), \
                 patch.object(flags, "identify", return_value=self.info), \
                 patch.object(flags, "language_names", return_value=LANGUAGES), \
                 patch.object(flags, "edit_file") as edit, \
                 patch("builtins.input", side_effect=answers), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(flags.main([str(self.path)]), 0)
            edit.assert_not_called()
            self.assertEqual(self.path.read_bytes(), b"not user media")

    def test_batch_preview_and_confirmation_only_once(self):
        second = self.root / "other.mkv"
        second.write_bytes(b"not user media")
        with patch.object(flags.shutil, "which", return_value="tool"), \
             patch.object(flags, "identify", return_value=self.info), \
             patch.object(flags, "language_names", return_value=LANGUAGES), \
             patch.object(flags, "edit_file", return_value=True) as edit, \
             patch("builtins.input", side_effect=["2", "1,2", "", "Custom", "y"]) as read, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(flags.main(["-i", str(self.root)]), 0)
        self.assertEqual(read.call_count, 5)
        self.assertEqual(edit.call_count, 2)
        for call in edit.call_args_list:
            self.assertEqual(call.args[2:], (False, False, set(), set()))
            self.assertEqual(call.kwargs["renames"], {self.catalog[0]: "English 1", self.catalog[1]: "Custom"})
        self.assertIn("episode.mkv", output.getvalue())
        self.assertIn("other.mkv", output.getvalue())
        self.assertIn("Rename 4 track(s) in 2 file(s) in place", output.getvalue())
        self.assertNotIn("Clear default:", output.getvalue())
        self.assertNotIn("Remove existing subtitle flags", output.getvalue())

    def test_named_group_reordering_uses_each_files_track_number(self):
        first = {"tracks": [track(2), track(3)]}
        first["tracks"][1]["properties"]["track_name"] = "Signs"
        second = {"tracks": [track(7), track(9)]}
        second["tracks"][0]["properties"]["track_name"] = "Signs"
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            catalog, duplicates = flags.subtitle_catalog([first, second])
        self.assertNotIn("WARNING", output.getvalue())
        rename = {next(key for key in catalog if key[0] == "Signs"): "Signs & Songs"}
        self.assertEqual(flags.desired_names(first, rename, duplicates), {2: "English", 3: "Signs & Songs"})
        self.assertEqual(flags.desired_names(second, rename, duplicates), {7: "Signs & Songs", 9: "English"})

    def test_no_selection_or_unchanged_name_skips_edit_and_confirmation(self):
        for answers in (["2", ""], ["2", "1", "-"]):
            with patch.object(flags.shutil, "which", return_value="tool"), \
                 patch.object(flags, "identify", return_value=self.info), \
                 patch.object(flags, "language_names", return_value=LANGUAGES), \
                 patch.object(flags, "edit_file") as edit, \
                 patch("builtins.input", side_effect=answers), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(flags.main([str(self.path)]), 0)
            edit.assert_not_called()
            self.assertIn("No track names need changing", output.getvalue())

    def test_source_changes_after_preview_prevent_editing(self):
        stamp = flags.file_stamp(self.path)
        self.path.write_bytes(b"changed source")
        with patch.object(flags.subprocess, "run") as run, self.assertRaises(RuntimeError):
            flags.edit_file(self.path, self.info, False, False, set(), set(), self.duplicates,
                            {self.catalog[0]: "English 1"}, source_stamp=stamp)
        run.assert_not_called()

    def test_recursive_input_aliases_and_single_file_scope(self):
        nested = self.root / "season/other.mkv"
        nested.parent.mkdir()
        nested.write_bytes(b"neighbor")
        output = self.root / "output/existing.mkv"
        output.parent.mkdir()
        output.write_bytes(b"existing")
        for args, expected in (([str(self.root)], [self.path]),
                               (["--input", str(self.root), "-r"], [self.path, nested]),
                               (["-i", str(self.path), "-r"], [self.path])):
            with patch.object(flags.shutil, "which", return_value="tool"), \
                 patch.object(flags, "identify", return_value=self.info) as identify, \
                 patch.object(flags, "language_names", return_value=LANGUAGES), \
                 patch.object(flags, "edit_file", return_value=True) as edit, \
                 patch("builtins.input", side_effect=["2", "1", "Custom", "y"]), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(flags.main(args), 0)
            self.assertEqual([call.args[0] for call in identify.call_args_list], expected)
            self.assertEqual([call.args[0] for call in edit.call_args_list], expected)

    def test_language_names_come_from_tool_and_unavailable_names_fall_back(self):
        output = "English | eng | eng | en\nUndetermined | und | und | \n"
        with patch.object(flags.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output, "")):
            self.assertEqual(flags.language_names(), {"en": "English", "eng": "English", "und": "Undetermined"})
        with patch.object(flags.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, "", "error")), \
             patch("sys.stdout", new_callable=io.StringIO) as console:
            self.assertEqual(flags.language_names(), {})
        self.assertIn("displayed codes", console.getvalue())


@unittest.skipUnless(shutil.which("mkvmerge") and shutil.which("mkvpropedit") and shutil.which("mkvextract"),
                     "MKVToolNix is required for real in-place checks")
class RealPropertyChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wav = self.root / "audio.wav"
        with wave.open(str(self.wav), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(8000)
            out.writeframes(b"\x00\x00" * 8000)
        self.srt = self.root / "text.srt"
        self.srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nKeep text\n", encoding="utf-8")
        self.ass = self.root / "text.ass"
        self.ass.write_text("[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\n"
                            "Format: Name, Fontname, Fontsize, PrimaryColour, Alignment, Outline, Shadow\n"
                            "Style: Default,Arial,20,&H00FFFFFF&,2,0,0\n[Events]\n"
                            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                            "Dialogue: 0,0:00:00.00,0:00:00.90,Default,,0,0,0,,Keep text\n", encoding="utf-8")
        self.chapters = self.root / "chapters.txt"
        self.chapters.write_text("CHAPTER01=00:00:00.000\nCHAPTER01NAME=Start\n")
        self.attachment = self.root / "attachment.txt"
        self.attachment.write_text("Preserve attachment\n")
        self.tags = self.root / "tags.xml"
        self.tags.write_text('<Tags><Tag><Targets/><Simple><Name>TITLE</Name><String>Fixture</String></Simple></Tag></Tags>')

    def create(self, name, subtitles, legacy=False):
        source = self.root / name
        args = ["mkvmerge", "-o", str(source), "--chapters", str(self.chapters),
                "--global-tags", str(self.tags), "--attachment-mime-type", "text/plain",
                "--attach-file", str(self.attachment)]
        if legacy:
            args.append("--disable-language-ietf")
        args += ["--language", "0:jpn", "--track-name", "0:Audio", str(self.wav)]
        for name, language, default, forced, subtitle in subtitles:
            args += ["--language", "0:" + language, "--track-name", "0:" + name,
                     "--default-track-flag", f"0:{int(default)}", "--forced-display-flag", f"0:{int(forced)}",
                     str(subtitle)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        return source

    def payloads(self, source, label):
        directory = self.root / label
        directory.mkdir()
        info = flags.identify(source)
        args = ["mkvextract", str(source), "tracks"]
        paths = []
        for entry in info["tracks"]:
            path = directory / f"track-{entry['id']}"
            paths.append(path)
            args.append(f"{entry['id']}:{path}")
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        return [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]

    def test_real_unnamed_batch_renames_and_flags_preserve_payloads_and_metadata(self):
        sources = [self.create(f"episode {episode}.mkv", [
            ("", "eng", True, True, self.ass), ("", "eng", False, False, self.ass)], legacy=True)
                   for episode in (1, 2)]
        before = [flags.identify(path) for path in sources]
        payloads = [self.payloads(path, f"before-{index}") for index, path in enumerate(sources)]
        with patch("builtins.input", side_effect=["2", "1,2", "", "Signs 日本語", "y"]), \
             patch("sys.stdout", new_callable=io.StringIO) as console:
            self.assertEqual(flags.main([str(self.root)]), 0, console.getvalue())
        for index, source in enumerate(sources):
            after = flags.identify(source)
            subs = [t for t in after["tracks"] if t["type"] == "subtitles"]
            self.assertEqual([t["properties"].get("track_name") for t in subs], ["English 1", "Signs 日本語"])
            self.assertEqual([(t["properties"]["default_track"], t["properties"]["forced_track"]) for t in subs],
                             [(True, True), (False, False)])
            self.assertEqual(self.payloads(source, f"after-rename-{index}"), payloads[index])
            self.assertEqual(after["container"]["properties"]["segment_uid"],
                             before[index]["container"]["properties"]["segment_uid"])
            self.assertEqual(after["attachments"], before[index]["attachments"])
            self.assertEqual(after["chapters"], before[index]["chapters"])
            self.assertEqual(after["global_tags"], before[index]["global_tags"])
        neighbor_digest = hashlib.sha256(sources[1].read_bytes()).hexdigest()
        # Set flags on only the second named track of one file; -r must not broaden file input.
        with patch("builtins.input", side_effect=["1", "1", "1", "2", "y"]), \
             patch("sys.stdout", new_callable=io.StringIO) as console:
            self.assertEqual(flags.main(["-i", str(sources[0]), "-r"]), 0, console.getvalue())
        after = flags.identify(sources[0])
        subs = [t for t in after["tracks"] if t["type"] == "subtitles"]
        self.assertEqual([t["properties"].get("track_name") for t in subs], ["English 1", "Signs 日本語"])
        self.assertEqual([(t["properties"]["default_track"], t["properties"]["forced_track"]) for t in subs],
                         [(False, False), (True, True)])
        self.assertEqual(self.payloads(sources[0], "after-flags"), payloads[0])
        self.assertEqual(hashlib.sha256(sources[1].read_bytes()).hexdigest(), neighbor_digest)
        self.assertFalse((self.root / "output").exists())

    def test_real_named_tracks_in_different_orders_and_clear_name(self):
        full = ("Full", "en", True, False, self.srt)
        signs = ("Signs", "en", False, True, self.srt)
        sources = [self.create("one.mkv", [full, signs]), self.create("two.mkv", [signs, full])]
        payloads = [self.payloads(path, f"before-{index}") for index, path in enumerate(sources)]
        with patch("builtins.input", side_effect=["2", "2", "Signs & Songs", "y"]), \
             patch("sys.stdout", new_callable=io.StringIO) as console:
            self.assertEqual(flags.main([str(self.root)]), 0, console.getvalue())
        self.assertNotIn("WARNING", console.getvalue())
        for index, source in enumerate(sources):
            subs = [t for t in flags.identify(source)["tracks"] if t["type"] == "subtitles"]
            self.assertEqual([t["properties"].get("track_name") for t in subs],
                             ["Full", "Signs & Songs"] if index == 0 else ["Signs & Songs", "Full"])
            self.assertEqual(self.payloads(source, f"after-{index}"), payloads[index])
        with patch("builtins.input", side_effect=["2", "2", "-", "y"]), \
             patch("sys.stdout", new_callable=io.StringIO) as console:
            self.assertEqual(flags.main(["--input", str(sources[0])]), 0, console.getvalue())
        subs = [t for t in flags.identify(sources[0])["tracks"] if t["type"] == "subtitles"]
        self.assertEqual([t["properties"].get("track_name") or "" for t in subs], ["Full", ""])


if __name__ == "__main__":
    unittest.main()
