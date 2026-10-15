"""Track addition/removal, matching, confirmation, and real MKVToolNix checks."""

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
    "subtitle_tracks", Path(__file__).resolve().parents[1] / "subtitle_tracks.py")
remove = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = remove
spec.loader.exec_module(remove)


def run_removal(argv):
    with patch.object(remove, "action_mode", return_value="remove"):
        return remove.main(argv)


def track(track_id, name="English", language="en", codec="S_TEXT/ASS", kind="subtitles"):
    return {"id": track_id, "type": kind, "properties": {
        "track_name": name, "language_ietf": language, "codec_id": codec,
        "uid": track_id + 100, "default_track": False, "forced_track": False}}


class RemovalChecks(unittest.TestCase):
    def test_duplicate_catalog_and_layout_warnings(self):
        from copy import deepcopy
        first = {"tracks": [track(3, ""), track(9, "")]}
        for entry in first["tracks"]:
            entry["properties"]["track_name"] = ""
        second = deepcopy(first)
        for entry in second["tracks"]:
            entry["id"] += 10
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            catalog, duplicates = remove.subtitle_catalog([first, second])
        self.assertEqual(len(catalog), 2)
        self.assertEqual([key[3] for key in catalog], [1, 2])
        self.assertNotIn("WARNING:", output.getvalue())
        self.assertIn("occurrence 2", remove.group_label(catalog[1]))
        self.assertEqual(list(remove.subtitle_groups(first, duplicates).values()), catalog)
        self.assertEqual(list(remove.subtitle_groups(second, duplicates).values()), catalog)
        # Missing peer, missing entire group, different name/codec/language, reordered layout.
        for variant in ({"tracks": second["tracks"][:1]}, {"tracks": []}):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                _, other_duplicates = remove.subtitle_catalog([first, variant])
            self.assertEqual(duplicates, other_duplicates)
            self.assertIn("Cannot verify subtitle groups", output.getvalue())
        for field, value in (("track_name", "Signs"), ("language", "jpn"),
                             ("codec_id", "S_TEXT/UTF8")):
            variant = deepcopy(second)
            if field == "language":
                variant["tracks"][0]["properties"].pop("language_ietf", None)
            variant["tracks"][0]["properties"][field] = value
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                remove.subtitle_catalog([first, variant])
            self.assertIn("Cannot verify subtitle groups", output.getvalue())
        other = deepcopy(second["tracks"][0])
        other["id"] = 99
        other["properties"]["track_name"] = "Signs"
        for variant in ({"tracks": [other, *second["tracks"]]},
                        {"tracks": [*second["tracks"], other]}):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                remove.subtitle_catalog([{"tracks": [other, *first["tracks"]]}, variant])
            self.assertEqual("WARNING:" in output.getvalue(), variant["tracks"][0] != other)
        with patch("sys.stdout", new_callable=io.StringIO):
            groups = remove.subtitle_groups({"tracks": first["tracks"][:1]}, duplicates)
        self.assertEqual(list(groups.values()), catalog[:1])

    def test_duplicate_remove_keep_and_language_selection(self):
        first = {"tracks": [track(3, ""), track(9, "")]}
        second = {"tracks": [track(4, ""), track(6, "")]}
        for answer, wanted in (("1", [{3}, {4}]), ("k 1", [{9}, {6}]),
                               ("en", [{3, 9}, {4, 6}])):
            with tempfile.TemporaryDirectory() as folder:
                for name in ("a.mkv", "b.mkv"):
                    Path(folder, name).touch()
                with patch.object(remove.shutil, "which", return_value="tool"), \
                     patch.object(remove, "identify", side_effect=[first, second]), \
                     patch.object(remove, "remux", return_value=True) as remux, \
                     patch("builtins.input", side_effect=[answer, "y"]), \
                     patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(run_removal([folder]), 0)
                self.assertEqual([call.args[3] for call in remux.call_args_list], wanted)
                self.assertIn("occurrence 1", output.getvalue())
                self.assertIn("occurrence 2", output.getvalue())

    def test_legacy_language_verification_accepts_only_new_ietf_tags(self):
        before = {"tracks": [track(3, ""), track(9, "")]}
        for entry in before["tracks"]:
            del entry["properties"]["language_ietf"]
            entry["properties"]["language"] = "eng"
        after = deepcopy(before)
        after["tracks"] = after["tracks"][:1]
        after["tracks"][0]["properties"]["language_ietf"] = "en"
        remove.verify_output(before, after, {9})
        after["tracks"][0]["properties"]["language"] = "jpn"
        with self.assertRaises(RuntimeError):
            remove.verify_output(before, after, {9})
        after["tracks"][0]["properties"]["language"] = "eng"
        before["tracks"][0]["properties"]["language_ietf"] = "en-US"
        with self.assertRaises(RuntimeError):
            remove.verify_output(before, after, {9})

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
            self.assertEqual(remove.manual_selection([a, b]), ({a, b}, False))

    def test_keep_selection_and_empty_input(self):
        catalog = [remove.subtitle_key(track(1)), remove.subtitle_key(track(2, codec="S_TEXT/UTF8"))]
        with patch("builtins.input", side_effect=["k", "k 0", "k 3", "k 1,2 1"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.manual_selection(catalog), (set(catalog), True))
        for answer in ("", "q"):
            with patch("builtins.input", return_value=answer), \
                 patch("sys.stdout", new_callable=io.StringIO):
                with self.assertRaises(EOFError):
                    remove.manual_selection(catalog)

    def test_keep_preview_removes_nonmatching_tracks_and_keeps_duplicate_groups(self):
        root = Path("/media")
        kept = track(2)
        info = {"tracks": [track(0, kind="video"), track(1, kind="audio"), kept,
                           track(3), track(4, codec="S_TEXT/UTF8")]}
        missing = {"tracks": [track(7, "French", "fr")]}
        items = [remove.ScannedFile(root / "match.mkv", info, (), {}),
                 remove.ScannedFile(root / "missing.mkv", missing, (), {}),
                 remove.ScannedFile(root / "unchanged.mkv", {"tracks": [kept]}, (), {})]
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            plan = remove.preview(items, root, root / "output", False,
                                  {remove.subtitle_key(kept)}, 0, keep=True)
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0][2], {4})
        self.assertEqual(plan[1][2], {7})
        self.assertIn("No selected keep tracks found: ALL subtitles will be removed.", output.getvalue())
        self.assertIn("REMOVE ID 7", output.getvalue())
        self.assertIn("all subtitles already match the keep selection; skipped", output.getvalue())
        self.assertIn("KEEP ID 2", output.getvalue())
        self.assertIn("KEEP ID 3", output.getvalue())
        self.assertIn("REMOVE ID 4", output.getvalue())

    def test_language_selection_matches_only_displayed_codes(self):
        catalog = [remove.subtitle_key(t) for t in (
            track(1, "English", "en", "S_TEXT/ASS"),
            track(2, "Signs", "en", "S_TEXT/UTF8"),
            track(3, "English US", "en-US"),
            track(4, "English legacy", "eng"),
            track(5, "German", "de"),
            track(6, "German legacy", "ger"),
            track(7, "Japanese", "ja"),
        )]
        self.assertEqual(remove.parse_selection("k en, de", catalog),
                         ({catalog[0], catalog[1], catalog[4]}, True))
        self.assertEqual(remove.parse_selection("ja", catalog), ({catalog[6]}, False))
        self.assertEqual(remove.parse_selection("en-US", catalog), ({catalog[2]}, False))
        self.assertEqual(remove.parse_selection("eng", catalog), ({catalog[3]}, False))
        self.assertEqual(remove.parse_selection("k en, 3", catalog), (set(catalog[:3]), True))

    def test_unlisted_aliases_and_invalid_language_selections_are_rejected(self):
        catalog = [remove.subtitle_key(t) for t in (
            track(1, "English", "en"), track(2, "German", "de"), track(3, "Japanese", "ja"))]
        for answer in ("eng", "ger", "jp", "deu", "jpn", "en-US", "xyz",
                       "k eng", "en;de", "k", "0", "k en,"):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                remove.parse_selection(answer, catalog)

    def test_language_keep_removes_all_subtitles_in_nonmatching_episode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "one.mkv", root / "two.mkv"
            first.touch()
            second.touch()
            english = track(1, "Signs", "en")
            japanese = track(2, "Japanese", "ja")
            infos = [{"tracks": [english, japanese]}, {"tracks": [japanese]}]
            with patch.object(remove.shutil, "which", return_value="mkvmerge"), \
                 patch.object(remove, "identify", side_effect=infos), \
                 patch.object(remove, "remux", return_value=True) as remux, \
                 patch("builtins.input", side_effect=["k en", "y"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(run_removal([folder]), 0)
            self.assertEqual(len(remux.call_args_list), 2)
            self.assertEqual([call.args[3] for call in remux.call_args_list], [{2}, {2}])
            self.assertIn("ALL subtitles will be removed", output.getvalue())

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
                                (["1", "2", "y"], {9}),
                                (["1", "k 1", "y"], {9}),
                                (["2", "m", "k 1", "y"], {9})):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder, "episode.mkv")
                path.write_bytes(b"source")
                with patch.object(remove.shutil, "which", return_value="mkvmerge"), \
                     patch.object(remove, "identify", return_value=info), \
                     patch.object(remove, "remux", return_value=True) as remux, \
                     patch("builtins.input", side_effect=answers), \
                     patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(run_removal([folder]), 0)
                if wanted is None:
                    remux.assert_not_called()
                else:
                    self.assertEqual(remux.call_args.args[3], wanted)
                self.assertIn("KEEP ID", output.getvalue())
                self.assertIn("REMOVE ID", output.getvalue())
                self.assertEqual(path.read_bytes(), b"source")
                self.assertFalse(Path(folder, "output").exists())

    def test_input_and_output_aliases(self):
        for input_option, output_option in (("-i", "-o"), ("--input", "--output")):
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
                    self.assertEqual(run_removal([input_option, str(media),
                                                  output_option, str(output)]), 0)
                identify.assert_called_once_with("mkvmerge", source)
                self.assertEqual(remux.call_args.args[1].path, source)
                self.assertEqual(remux.call_args.args[2], output / source.name)

    def test_conflicting_input_forms_are_rejected(self):
        with patch("sys.stderr", new_callable=io.StringIO), \
             patch.object(remove, "find_files") as scan:
            with self.assertRaises(SystemExit) as raised:
                run_removal(["media", "--input", "other-media"])
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
                self.assertEqual(run_removal([folder]), 0)
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
    def test_real_unnamed_duplicate_flags_and_removal_in_legacy_mkv(self):
        flag_spec = importlib.util.spec_from_file_location(
            "duplicate_flags", Path(__file__).resolve().parents[1] / "subtitle_properties.py")
        flags = importlib.util.module_from_spec(flag_spec)
        flag_spec.loader.exec_module(flags)
        tool = shutil.which("mkvmerge")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "audio.wav"
            with wave.open(str(audio), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(b"\x00\x00" * 8000)
            subtitle = root / "text.srt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:00,900\nText\n")
            source = root / "episode.mkv"
            args = [tool, "--disable-language-ietf", "-o", str(source), str(audio)]
            for _ in range(2):
                args += ["--language", "0:eng", "--default-track-flag", "0:0", str(subtitle)]
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
            before = remove.identify(tool, source)
            subs = [t for t in before["tracks"] if t["type"] == "subtitles"]
            with patch("sys.stdout", new_callable=io.StringIO):
                catalog, duplicates = flags.subtitle_catalog([before])
                flags.edit_file(source, before, True, True, {catalog[1]}, {catalog[1]}, duplicates)
            flagged = flags.identify(source)
            values = list(flags.desired_flags(flagged, False, False, set(), set()).values())
            self.assertEqual(values, [(False, False), (True, True)])
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch("builtins.input", side_effect=["k 1", "y"]), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(run_removal([str(source)]), 0)
            after = remove.identify(tool, root / "output" / source.name)
            kept = [t for t in after["tracks"] if t["type"] == "subtitles"]
            self.assertEqual(len(kept), 1)
            self.assertEqual(kept[0]["properties"]["uid"], subs[0]["properties"]["uid"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)

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


LANGUAGES = {"en": ("en", "English"), "eng": ("en", "English"),
             "de": ("de", "German"), "deu": ("de", "German"),
             "und": ("und", "Undetermined")}


class AdditionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def items(self, names):
        result = []
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"MKV")
            result.append(remove.ScannedFile(path, {"tracks": [track(0, kind="audio")]},
                                             remove.file_stamp(path), {}))
        return result

    def subtitles(self, names):
        result = []
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("subtitle", encoding="utf-8")
            result.append(path)
        return result

    def test_exact_multilanguage_and_track_number_groups(self):
        items = self.items(["episode 2.mkv", "episode 1.mkv"])
        paths = self.subtitles([f"episode {episode}.{suffix}.srt"
                                for episode in (1, 2) for suffix in ("en.1", "en.2", "de")])
        groups, rejected = remove.match_additions(items, paths, LANGUAGES)
        self.assertFalse(rejected)
        self.assertEqual(len(groups), 3)
        self.assertEqual({g.name for g in groups}, {"English 1", "English 2", "German"})
        for group in groups:
            self.assertFalse(group.ordered)
            self.assertEqual(len(group.pairs), 2)
            for item, path in group.pairs:
                self.assertTrue(path.stem.startswith(item.path.stem + "."))

    def test_ordered_groups_use_natural_order_and_preserve_exact_matches(self):
        items = self.items(["episode 2.mkv", "episode 10.mkv"])
        paths = self.subtitles(["different 10.en.1.srt", "different 2.en.1.srt",
                                "episode 10.de.srt", "different 99.de.srt"])
        groups, rejected = remove.match_additions(items, paths, LANGUAGES)
        self.assertFalse(rejected)
        self.assertTrue(all(g.ordered for g in groups))
        english = next(g for g in groups if g.language == "en")
        self.assertEqual([(a.path.name, b.name) for a, b in english.pairs],
                         [("episode 2.mkv", "different 2.en.1.srt"),
                          ("episode 10.mkv", "different 10.en.1.srt")])
        german = next(g for g in groups if g.language == "de")
        self.assertEqual([(a.path.name, b.name) for a, b in german.pairs],
                         [("episode 2.mkv", "different 99.de.srt"),
                          ("episode 10.mkv", "episode 10.de.srt")])

    def test_ordered_dot_episode_numbers_do_not_become_track_groups(self):
        items = self.items(["episode 1.mkv", "episode 2.mkv"])
        for names, expected in ((["Other.01.en.srt", "Other.02.en.srt"], 1),
                                ([f"Other.{episode:02d}.en.{number}.srt"
                                  for episode in (1, 2) for number in (1, 2)], 2),
                                ([f"Other.{episode:02d}.{number}.en.srt"
                                  for episode in (1, 2) for number in (1, 2)], 2)):
            groups, rejected = remove.match_additions(items, self.subtitles(names), LANGUAGES)
            self.assertFalse(rejected)
            self.assertEqual(len(groups), expected)
            self.assertTrue(all(len(g.pairs) == 2 for g in groups))

    def test_incomplete_and_duplicate_groups_are_excluded(self):
        items = self.items(["one.mkv", "two.mkv"])
        for names in (["one.en.srt"], ["one.en.srt", "ONE.EN.SRT"],
                      ["one.en.srt", "two.en.srt", "three.en.srt"]):
            groups, rejected = remove.match_additions(items, self.subtitles(names), LANGUAGES)
            self.assertEqual(groups, [])
            self.assertTrue(rejected)

    def test_single_file_ignores_neighbor_subtitles(self):
        items = self.items(["one.mkv", "two.mkv"])
        paths = self.subtitles(["one.en.srt", "two.en.srt", "random.de.srt"])
        groups, rejected = remove.match_additions(items[:1], paths, LANGUAGES, allow_ordered=False)
        self.assertFalse(rejected)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].pairs[0][1].name, "one.en.srt")

    def test_recursive_folders_are_independent_and_outputs_excluded(self):
        items = self.items(["season1/one.mkv", "season2/one.mkv"])
        paths = self.subtitles(["season1/one.en.srt", "season2/different.de.srt",
                                "output/one.en.srt", "season1/output/one.en.srt",
                                "custom/one.en.srt"])
        discovered = remove.find_files(self.root, self.root / "custom", True, remove.SUBTITLE_EXTENSIONS)
        self.assertEqual(set(discovered), set(paths[:2]))
        self.assertEqual(remove.find_files(self.root, None, False, remove.SUBTITLE_EXTENSIONS), [])
        groups, rejected = remove.match_additions(items, discovered, LANGUAGES)
        self.assertFalse(rejected)
        self.assertEqual(len(groups), 2)
        for group in groups:
            item, path = group.pairs[0]
            self.assertEqual(item.path.parent, path.parent)

    def test_longest_exact_basename_and_case_insensitive_suffix(self):
        items = self.items(["show.mkv", "show extended.mkv"])
        paths = self.subtitles(["SHOW.EN.srt", "SHOW EXTENDED.en.SRT"])
        groups, rejected = remove.match_additions(items, paths, LANGUAGES)
        self.assertFalse(rejected)
        self.assertEqual(len(groups), 1)
        self.assertCountEqual([(a.path.stem.casefold(), b.stem.casefold()) for a, b in groups[0].pairs],
                         [("show", "show.en"), ("show extended", "show extended.en")])

    def test_ambiguous_casefolded_mkv_basenames_are_rejected(self):
        items = self.items(["show.mkv", "SHOW.MKV"])
        groups, rejected = remove.match_additions(items, self.subtitles(["show.en.srt"]), LANGUAGES)
        self.assertEqual(groups, [])
        self.assertIn("ambiguous", rejected[0])

    def test_vobsub_companion_is_not_an_extra_group_and_is_stamped(self):
        items = self.items(["one.mkv"])
        paths = self.subtitles(["one.en.idx", "one.en.sub"])
        groups, rejected = remove.match_additions(items, paths, LANGUAGES)
        self.assertFalse(rejected)
        self.assertEqual(len(groups), 1)
        with patch.object(remove, "identify", return_value={"tracks": [track(0)]}):
            checked = remove.scan_additions("tool", groups)
        self.assertEqual(set(checked[0].pairs[0][1].stamps), set(paths))
        paths[1].unlink()
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.scan_additions("tool", remove.match_additions(items, paths[:1], LANGUAGES)[0]), [])

    def test_bad_subtitle_excludes_entire_group(self):
        items = self.items(["one.mkv", "two.mkv"])
        paths = self.subtitles(["one.en.srt", "two.en.srt"])
        groups, _ = remove.match_additions(items, paths, LANGUAGES)
        with patch.object(remove, "identify", side_effect=[{"tracks": [track(0)]}, RuntimeError("bad subtitle")]), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(remove.scan_additions("tool", groups), [])
        self.assertIn("entire group skipped", output.getvalue())

    def test_group_editing_exclusion_and_single_final_confirmation(self):
        items = self.items(["one.mkv"])
        self.subtitles(["one.en.srt", "one.de.srt"])
        with patch.object(remove, "language_catalog", return_value=LANGUAGES), \
             patch.object(remove, "identify", return_value={"tracks": [track(0)]}), \
             patch("builtins.input", side_effect=["x 1", "2", "nonsense", "en-US", "Custom", "y"]), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            plan = remove.addition_plan("tool", items, self.root, None, False, 0)
        self.assertEqual(len(plan), 1)
        self.assertEqual(len(plan[0][2]), 1)
        _, group = plan[0][2][0]
        self.assertEqual((group.name, group.language), ("Custom", "en-US"))
        self.assertIn("one.en.srt", output.getvalue())
        self.assertIn("[excluded]", output.getvalue())

    def test_main_add_cancel_and_empty_mkv_subtitle_catalog(self):
        self.items(["one.mkv"])
        self.subtitles(["one.en.srt"])
        for answer, expected in (("n", 0), ("y", 1)):
            with patch.object(remove.shutil, "which", return_value="tool"), \
                 patch.object(remove, "language_catalog", return_value=LANGUAGES), \
                 patch.object(remove, "identify", side_effect=[{"tracks": [track(0, kind="audio")]},
                                                            {"tracks": [track(0)]}]), \
                 patch.object(remove, "remux", return_value=True) as remux, \
                 patch("builtins.input", side_effect=["2", answer]), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(remove.main(["-i", str(self.root / "one.mkv"), "-r"]), 0)
            self.assertEqual(remux.call_count, expected)
        self.assertFalse((self.root / "output").exists())

    def test_existing_outputs_and_recursive_output_paths(self):
        items = self.items(["one.mkv", "season/two.mkv"])
        paths = self.subtitles(["one.en.srt", "season/two.en.srt"])
        groups, _ = remove.match_additions(items, paths, LANGUAGES)
        with patch.object(remove, "identify", return_value={"tracks": [track(0)]}):
            groups = remove.scan_additions("tool", groups)
        with patch("sys.stdout", new_callable=io.StringIO):
            plan = remove.preview_additions(items, groups, self.root, self.root / "cleaned", 0)
        self.assertEqual([target.relative_to(self.root) for _, target, _ in plan],
                         [Path("cleaned/one.mkv"), Path("cleaned/season/two.mkv")])
        existing = self.root / "output/one.mkv"
        existing.parent.mkdir()
        existing.write_bytes(b"existing")
        with patch("sys.stdout", new_callable=io.StringIO):
            plan = remove.preview_additions(items, groups, self.root, None, 0)
        self.assertEqual([target.relative_to(self.root) for _, target, _ in plan],
                         [Path("season/output/two.mkv")])
        self.assertEqual(existing.read_bytes(), b"existing")

    def test_language_catalog_uses_tool_data(self):
        output = "English language name | ISO 639-3 code | ISO 639-2 code | ISO 639-1 code\n"
        output += "English | eng | eng | en\nUndetermined | und | und | \n"
        with patch.object(remove.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output, "")):
            languages = remove.language_catalog("tool")
        self.assertEqual(remove.normalize_language("eng", languages), "en")
        self.assertEqual(remove.normalize_language("en-US", languages), "en-US")
        self.assertEqual(remove.suffix_language("en.2", languages), "en")
        for value in ("English", "xx", "en;ja", "en_XX"):
            with self.assertRaises(ValueError):
                remove.normalize_language(value, languages)

    def test_changed_subtitle_prevents_remux(self):
        items = self.items(["one.mkv"])
        paths = self.subtitles(["one.en.srt"])
        groups, _ = remove.match_additions(items, paths, LANGUAGES)
        with patch.object(remove, "identify", return_value={"tracks": [track(0)]}):
            groups = remove.scan_additions("tool", groups)
        additions = [(groups[0].pairs[0][1], groups[0])]
        paths[0].write_text("changed subtitle")
        with patch.object(remove.subprocess, "run") as run, self.assertRaises(RuntimeError):
            remove.remux("tool", items[0], self.root / "output/one.mkv", set(), additions)
        run.assert_not_called()
        self.assertFalse((self.root / "output").exists())


    def test_added_metadata_is_verified_and_failures_clean_partial_files(self):
        import json
        items = self.items(["one.mkv"])
        paths = self.subtitles(["one.en.srt"])
        groups, _ = remove.match_additions(items, paths, LANGUAGES)
        with patch.object(remove, "identify", return_value={"tracks": [track(0)]}):
            groups = remove.scan_additions("tool", groups)
        additions = [(groups[0].pairs[0][1], groups[0])]
        good = deepcopy(items[0].info)
        good["tracks"].append(track(1, "English"))
        remove.verify_additions(items[0].info, good, additions)
        for field, value in (("track_name", "Wrong"), ("language_ietf", "de"),
                             ("default_track", True), ("forced_track", True)):
            bad = deepcopy(good)
            bad["tracks"][-1]["properties"][field] = value
            with self.assertRaises(RuntimeError):
                remove.verify_additions(items[0].info, bad, additions)
        reversed_tracks = dict(good, tracks=list(reversed(good["tracks"])))
        with self.assertRaises(RuntimeError):
            remove.verify_additions(items[0].info, reversed_tracks, additions)
        target = self.root / "output/one.mkv"
        for failure in ("tool", "verify", "subtitle_changed", "source_changed"):
            bad = deepcopy(good)
            bad["tracks"][-1]["properties"]["forced_track"] = True
            def run(args, **kwargs):
                options = json.loads(Path(args[1][1:]).read_text())
                Path(options[options.index("-o") + 1]).write_bytes(b"partial output")
                if failure == "subtitle_changed":
                    paths[0].write_text("changed during remux")
                if failure == "source_changed":
                    items[0].path.write_bytes(b"changed source")
                return subprocess.CompletedProcess(args, 2 if failure == "tool" else 0, "", "tool error")
            # Restore snapshots between the different failure scenarios.
            items[0].stamp = remove.file_stamp(items[0].path)
            additions[0][0].stamps = {paths[0]: remove.file_stamp(paths[0])}
            with patch.object(remove.subprocess, "run", side_effect=run), \
                 patch.object(remove, "identify", return_value=bad if failure == "verify" else good), \
                 self.assertRaises(RuntimeError):
                remove.remux("tool", items[0], target, set(), additions)
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.iterdir()), [])

    def test_action_menu_ignores_unlisted_keys_and_cancel_is_read_only(self):
        with patch.object(sys.stdin, "isatty", return_value=False), \
             patch("builtins.input", side_effect=["9", "12", "2"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.action_mode(), "add")
        self.items(["one.mkv"])
        with patch.object(remove.shutil, "which", return_value="tool"), \
             patch.object(remove, "identify", return_value={"tracks": [track(0)]}), \
             patch("builtins.input", return_value="q"), \
             patch.object(remove, "remux") as remux, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.main([str(self.root)]), 0)
        remux.assert_not_called()
        self.assertFalse((self.root / "output").exists())


@unittest.skipUnless(shutil.which("mkvmerge"), "MKVToolNix is required")
class RealAdditionChecks(unittest.TestCase):
    def test_real_multiple_groups_appended_with_flags_names_languages_and_sources_preserved(self):
        tool = shutil.which("mkvmerge")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wav = root / "audio.wav"
            with wave.open(str(wav), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(b"\x00\x00" * 8000)
            original = root / "original.srt"
            original.write_text("1\n00:00:00,000 --> 00:00:00,900\nOriginal\n")
            originals = {}
            for episode in (1, 2):
                source = root / f"Episode {episode}.mkv"
                result = subprocess.run([tool, "--disable-language-ietf", "-o", str(source), str(wav),
                                         "--language", "0:de", "--track-name", "0:Existing",
                                         "--default-track-flag", "0:1", "--forced-display-flag", "0:1",
                                         str(original)], capture_output=True, text=True)
                self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
                originals[source] = hashlib.sha256(source.read_bytes()).hexdigest()
                (root / f"Episode {episode}.en.1.srt").write_text(original.read_text())
                (root / f"Episode {episode}.de.srt").write_text(original.read_text())
                (root / f"Episode {episode}.en.2.ass").write_text(
                    "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\n"
                    "Format: Name, Fontname, Fontsize, PrimaryColour, Alignment, Outline, Shadow\n"
                    "Style: Default,Arial,20,&H00FFFFFF&,2,0,0\n[Events]\n"
                    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                    "Dialogue: 0,0:00:00.00,0:00:00.90,Default,,0,0,0,,Added\n")
            # This unrelated subtitle cannot form a complete group.
            with patch("builtins.input", side_effect=["2", "2", "en-US", "Custom 日本語", "y"]), \
                 patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(remove.main([str(root)]), 0, output.getvalue())
            self.assertIn("incomplete group skipped", output.getvalue())
            for source, digest in originals.items():
                before = remove.identify(tool, source)
                after = remove.identify(tool, root / "output" / source.name)
                self.assertEqual(len(after["tracks"]), len(before["tracks"]) + 3)
                remove.verify_output(before, dict(after, tracks=after["tracks"][:len(before["tracks"])]), set())
                added = after["tracks"][len(before["tracks"]):]
                self.assertEqual([t["properties"].get("track_name") for t in added],
                                 ["German", "Custom 日本語", "English 2"])
                self.assertEqual([t["properties"].get("language_ietf") for t in added], ["de", "en-US", "en"])
                for t in added:
                    self.assertFalse(t["properties"]["default_track"])
                    self.assertFalse(t["properties"]["forced_track"])
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            self.assertEqual(len(list((root / "output").iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
