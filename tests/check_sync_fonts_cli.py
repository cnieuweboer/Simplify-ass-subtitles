"""Check font-sync folder defaults, overrides, and no-argument console lifetime."""

import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "sync_fonts", Path(__file__).resolve().parents[1] / "sync_fonts.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class FontSyncCliChecks(unittest.TestCase):
    def run_main(self, argv, source, script, output, fonts_dir=None):
        inspection = {"missing": set(), "log": []}
        with patch.object(sync, "__file__", str(script)), \
             patch.object(sync, "find_tool", side_effect=lambda name: name), \
             patch.object(sync, "inspect_fonts", return_value=inspection) as inspect, \
             patch.object(sync, "local_font_catalog", return_value=[]) as catalog, \
             patch.object(sync, "choose_plans", return_value={source: {}}), \
             patch.object(sync, "process", return_value="unchanged") as process, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(sync.main(argv), 0)
        inspect.assert_called_once_with(source, "mkvmerge", "mkvextract")
        self.assertEqual(catalog.call_args.args[0], fonts_dir or source.parent)
        self.assertEqual(process.call_args.args[:5], (source, output, "mkvmerge", False, False))
        self.assertTrue(output.is_dir())

    def test_no_arguments_use_script_folder_despite_different_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / "media"
            scripts.mkdir()
            source = scripts / "episode.mkv"
            source.touch()
            with patch.object(sync.Path, "cwd", return_value=root):
                self.run_main([], source, scripts / "sync_fonts.py", scripts / "output")

    def test_input_and_output_overrides_route_mkvs_and_fonts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media = root / "media"
            media.mkdir()
            source = media / "episode.mkv"
            source.touch()
            output = root / "nested" / "cleaned"
            self.run_main(["-i", str(media), "-o", str(output)], source,
                          root / "sync_fonts.py", output)

    def test_legacy_positional_input_still_works(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "episode.mkv"
            source.touch()
            self.run_main([folder], source, root / "scripts" / "sync_fonts.py", root / "output")

    def test_separate_font_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media, fonts = root / "media", root / "fonts"
            media.mkdir()
            fonts.mkdir()
            source = media / "episode.mkv"
            source.touch()
            self.run_main(["-i", str(media), "-f", str(fonts)], source,
                          root / "sync_fonts.py", media / "output", fonts)

    def test_font_catalog_is_shared_across_mkvs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inspections = {root / name: {"missing": set()} for name in ("one.mkv", "two.mkv")}
            catalog = [{"path": root / "font.ttf"}]
            with patch.object(sync, "local_font_catalog", return_value=catalog) as read:
                sync.scan_local_fonts(inspections, root / "fonts")
            read.assert_called_once()
            for inspection in inspections.values():
                self.assertIs(inspection["local_fonts"], catalog)

    def test_reject_invalid_paths_and_conflicting_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            blocked = root / "not-a-folder"
            blocked.touch()
            with patch("sys.stdout", new_callable=io.StringIO), \
                 patch("sys.stderr", new_callable=io.StringIO), \
                 patch.object(sync, "find_tool") as tool:
                self.assertEqual(sync.main(["-i", str(root / "missing")]), 2)
                self.assertEqual(sync.main(["-i", folder, "-f", str(root / "missing")]), 2)
                self.assertEqual(sync.main(["-i", folder, "-f", str(blocked)]), 2)
                self.assertEqual(sync.main(["-i", folder, "-o", folder]), 2)
                self.assertEqual(sync.main(["-i", folder, "-o", str(blocked)]), 2)
                with self.assertRaises(SystemExit) as raised:
                    sync.main([folder, "-i", folder])
                self.assertEqual(raised.exception.code, 2)
                tool.assert_not_called()

    def test_windows_no_argument_console_pauses_on_success_failure_and_interrupt(self):
        for result in (0, 2, KeyboardInterrupt()):
            with patch.object(sync.sys, "platform", "win32"), \
                 patch.object(sync.sys.stdin, "isatty", return_value=True), \
                 patch.object(sync, "main", side_effect=result if isinstance(result, BaseException) else None,
                              return_value=result), \
                 patch("builtins.input", return_value="") as pause, \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(sync.cli([]), 130 if isinstance(result, BaseException) else result)
                pause.assert_called_once()

    def test_cli_arguments_non_windows_and_redirected_input_never_pause(self):
        for platform, arguments, terminal in (("win32", ["--preview"], True),
                                              ("linux", [], True), ("win32", [], False)):
            with patch.object(sync.sys, "platform", platform), \
                 patch.object(sync.sys.stdin, "isatty", return_value=terminal), \
                 patch.object(sync, "main", return_value=0), \
                 patch("builtins.input") as pause:
                self.assertEqual(sync.cli(arguments), 0)
                pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
