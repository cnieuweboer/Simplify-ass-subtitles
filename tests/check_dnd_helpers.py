"""Check standalone sibling wrappers and Linux launcher installation."""

import configparser
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "dnd helper"
TOOLS = ("subtitle_properties", "subtitle_tracks", "sync_fonts", "simplify_subtitles")


def fake_tool(path):
    path.write_text(
        "import json,sys\nfrom pathlib import Path\n"
        "with Path(__file__).with_suffix('.log').open('a') as out:\n"
        " out.write(json.dumps(sys.argv[1:])+'\\n')\n")


class DropHelperChecks(unittest.TestCase):
    def test_each_copied_wrapper_runs_only_its_sibling_python_script(self):
        for tool in TOOLS:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                scripts = root / "copied tools with spaces"
                media = root / "dropped folder"
                scripts.mkdir()
                media.mkdir()
                wrapper = scripts / (tool + ".sh")
                shutil.copyfile(HELPERS / "linux" / wrapper.name, wrapper)
                script = scripts / (tool + ".py")
                fake_tool(script)
                result = subprocess.run(["sh", str(wrapper), str(media)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(script.with_suffix(".log").read_text()), [str(media)])

    def test_no_drop_defaults_to_the_sibling_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "subtitle_tracks.sh"
            shutil.copyfile(HELPERS / "linux" / wrapper.name, wrapper)
            fake_tool(root / "subtitle_tracks.py")
            result = subprocess.run(["sh", str(wrapper)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads((root / "subtitle_tracks.log").read_text()), [str(root)])

    def test_missing_script_and_missing_drop_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "sync_fonts.sh"
            shutil.copyfile(HELPERS / "linux" / wrapper.name, wrapper)
            result = subprocess.run(["sh", str(wrapper)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            fake_tool(root / "sync_fonts.py")
            media = root / "episode.mkv"
            result = subprocess.run(["sh", str(wrapper), str(root), str(media)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / "sync_fonts.log").exists())

    def test_each_wrapper_passes_a_single_mkv_without_expanding_its_folder(self):
        for tool in TOOLS:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                wrapper = root / (tool + ".sh")
                shutil.copyfile(HELPERS / "linux" / wrapper.name, wrapper)
                fake_tool(root / (tool + ".py"))
                media = root / "selected episode.MKV"
                media.touch()
                (root / "another episode.mkv").touch()
                result = subprocess.run(["sh", str(wrapper), str(media)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads((root / (tool + ".log")).read_text()), [str(media)])

    def test_standalone_installer_creates_only_available_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / 'tools with spaces $cash %percent "quotes"'
            scripts.mkdir()
            # The installer is also portable when copied beside a single tool.
            setup = scripts / "setup-linux.sh"
            shutil.copyfile(HELPERS / "linux/setup-linux.sh", setup)
            fake_tool(scripts / "subtitle_tracks.py")
            result = subprocess.run(["sh", str(setup)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            launcher = scripts / "subtitle_tracks.desktop"
            entry = configparser.ConfigParser(interpolation=None)
            entry.read(launcher)
            self.assertEqual(entry["Desktop Entry"]["Terminal"], "true")
            self.assertIn("%f", entry["Desktop Entry"]["Exec"])
            self.assertFalse((scripts / "sync_fonts.desktop").exists())
            self.assertTrue(launcher.stat().st_mode & 0o111)
            if shutil.which("desktop-file-validate"):
                result = subprocess.run(["desktop-file-validate", str(launcher)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            wrapper = scripts / "subtitle_tracks.sh"
            result = subprocess.run(["sh", str(wrapper), str(scripts)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads((scripts / "subtitle_tracks.log").read_text()), [str(scripts)])

    def test_installer_accepts_an_external_tools_folder_and_can_relocate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "tools"
            scripts.mkdir()
            for tool in TOOLS:
                fake_tool(scripts / (tool + ".py"))
            setup = HELPERS / "linux/setup-linux.sh"
            result = subprocess.run(["sh", str(setup), str(scripts)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            moved = root / "moved"
            scripts.rename(moved)
            result = subprocess.run(["sh", str(setup), str(moved)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for tool in TOOLS:
                self.assertIn(str(moved), (moved / (tool + ".desktop")).read_text())

    def test_installer_with_only_simplify_subtitles(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory)
            fake_tool(scripts / "simplify_subtitles.py")
            result = subprocess.run(["sh", str(HELPERS / "linux/setup-linux.sh"), str(scripts)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([path.name for path in scripts.glob("*.desktop")], ["simplify_subtitles.desktop"])
            first, second = scripts / "first", scripts / "second"
            first.mkdir()
            second = second.with_suffix(".mkv")
            second.touch()
            result = subprocess.run(["sh", str(scripts / "simplify_subtitles.sh"), str(first), str(second)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([json.loads(line) for line in (scripts / "simplify_subtitles.log").read_text().splitlines()],
                             [[str(first)], [str(second)]])


if __name__ == "__main__":
    unittest.main()
