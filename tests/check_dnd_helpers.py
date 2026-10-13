"""Check folder routing, terminal arguments, and generated desktop launchers."""

import configparser
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dnd_helper", ROOT / "dnd helper/dnd_helper.py")
dnd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dnd)


class DropHelperChecks(unittest.TestCase):
    def test_real_child_gets_correct_folder_paths_and_duplicate_folders_run_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folders = [root / "media with spaces", root / "other media"]
            for folder in folders:
                folder.mkdir()
            script = root / "remove_subtitles.py"
            script.write_text(
                "import json,sys\nfrom pathlib import Path\n"
                "with Path(__file__).with_suffix('.log').open('a') as out:\n"
                " out.write(json.dumps([sys.argv[1:],str(Path.cwd())])+'\\n')\n")
            with patch.object(dnd, "ROOT", root), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(dnd.run_tool("remove_subtitles", [str(folders[0]),
                                                                    str(folders[0]), str(folders[1])]), 0)
            calls = [json.loads(line) for line in script.with_suffix(".log").read_text().splitlines()]
            self.assertEqual(calls, [[[str(folder)], str(folder)] for folder in folders])

    def test_rejects_file_drops_before_starting_any_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "subtitle_flags.py").touch()
            file = root / "episode.mkv"
            file.touch()
            with patch.object(dnd, "ROOT", root), patch.object(dnd.subprocess, "run") as run, \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(dnd.run_tool("subtitle_flags", [str(root), str(file)]), 2)
                run.assert_not_called()

    def test_missing_script_and_multiple_folder_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            second = root / "second"
            second.mkdir()
            with patch.object(dnd, "ROOT", root), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(dnd.run_tool("sync_fonts", []), 2)
                (root / "sync_fonts.py").touch()
                with patch.object(dnd.subprocess, "run", side_effect=[
                        subprocess.CompletedProcess([], 2), subprocess.CompletedProcess([], 0)]) as run:
                    self.assertEqual(dnd.run_tool("sync_fonts", [str(root), str(second)]), 1)
                    self.assertEqual(run.call_count, 2)

    def test_pause_option_can_precede_or_follow_dropped_folders(self):
        for args in (["remove_subtitles", "--pause", "media"],
                     ["--pause", "remove_subtitles", "media"],
                     ["remove_subtitles", "media", "--pause"]):
            with patch.object(dnd, "run_tool", return_value=0) as run, \
                 patch.object(dnd.sys.stdin, "isatty", return_value=False), \
                 patch("builtins.input") as pause:
                self.assertEqual(dnd.main(args), 0)
                run.assert_called_once_with("remove_subtitles", ["media"])
                pause.assert_not_called()

    def test_generated_linux_launchers_are_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / 'helpers with spaces $cash %percent "quotes"'
            helper.mkdir()
            with patch.object(dnd, "HELPER_DIR", helper), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(dnd.install_linux(), 0)
            for tool in dnd.TOOLS:
                launcher = helper / "linux" / (tool + ".desktop")
                entry = configparser.ConfigParser(interpolation=None)
                entry.read(launcher)
                self.assertEqual(entry["Desktop Entry"]["Terminal"], "true")
                self.assertIn("%F", entry["Desktop Entry"]["Exec"])
                self.assertTrue(launcher.stat().st_mode & 0o111)
                if shutil.which("desktop-file-validate"):
                    result = subprocess.run(["desktop-file-validate", str(launcher)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
