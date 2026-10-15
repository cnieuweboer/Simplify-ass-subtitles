"""Check immediate tool dispatch, current-folder input, and argument forwarding."""

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "installer/windows/subtitle_tools.py"


def load_menu():
    spec = importlib.util.spec_from_file_location("subtitle_tools_menu", SOURCE)
    menu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(menu)
    return menu


class MenuChecks(unittest.TestCase):
    def test_menu_routes_track_and_property_actions_to_new_scripts(self):
        menu = load_menu()
        self.assertEqual(menu.OPTIONS[1], ("Add or remove subtitle tracks", "subtitle_tracks.py"))
        self.assertEqual(menu.OPTIONS[2], ("Rename tracks or edit default/forced flags", "subtitle_properties.py"))

    def test_all_choices_run_only_selected_tool_and_forward_arguments(self):
        menu = load_menu()
        for number, (_, tool) in enumerate(menu.OPTIONS, 1):
            with self.subTest(choice=number), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                scripts = root / "installed tools" / "simplify-ass"
                media = root / "current media"
                scripts.mkdir(parents=True)
                media.mkdir()
                selector = scripts / "subtitle_tools.py"
                shutil.copyfile(SOURCE, selector)
                for _, script in menu.OPTIONS:
                    (scripts / script).write_text(
                        "import json,sys,os\nfrom pathlib import Path\n"
                        "Path(__file__).with_suffix('.log').write_text(json.dumps([os.getcwd(),sys.argv[1:]]))\n"
                        "raise SystemExit(7)\n")
                args = ["--input", "another media folder", "-o", "cleaned", "-r", "-f", "fonts"]
                result = subprocess.run([sys.executable, str(selector), *args], input=str(number) + "\n",
                                        cwd=media, capture_output=True, text=True)
                self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
                self.assertEqual([path.name for path in scripts.glob("*.log")], [Path(tool).with_suffix(".log").name])
                cwd, forwarded = json.loads((scripts / Path(tool).with_suffix(".log")).read_text())
                self.assertEqual(Path(cwd), media)
                self.assertEqual(forwarded, [] if number == 5 else ["--input", str(media), *args])
                if number == 5:
                    self.assertIn("media-processing options are ignored", result.stdout)

    def test_no_arguments_uses_current_folder(self):
        menu = load_menu()
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "simplify_subtitles.py"
            script.touch()
            child = SimpleNamespace(wait=lambda: 0)
            with patch.object(menu, "__file__", str(Path(folder) / "subtitle_tools.py")), \
                 patch.object(menu, "choose", return_value="1"), \
                 patch.object(menu.subprocess, "Popen", return_value=child) as start, \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(menu.main([]), 0)
            self.assertEqual(start.call_args.args[0], [sys.executable, str(script), "--input", str(Path.cwd())])

    def test_cancel_never_starts_a_tool(self):
        menu = load_menu()
        with patch.object(menu, "choose", return_value="q"), \
             patch.object(menu.subprocess, "Popen") as start, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(menu.main(["-i", "media"]), 0)
        start.assert_not_called()

    def test_missing_tool_fails_without_starting_another_tool(self):
        menu = load_menu()
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(menu, "__file__", str(Path(folder) / "subtitle_tools.py")), \
             patch.object(menu, "choose", return_value="3"), \
             patch.object(menu.subprocess, "Popen") as start, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(menu.main([]), 2)
        start.assert_not_called()

    def test_first_interrupt_allows_child_cleanup(self):
        menu = load_menu()
        child = SimpleNamespace(wait=MagicMock(side_effect=[KeyboardInterrupt, 0]), kill=MagicMock())
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "simplify_subtitles.py").touch()
            with patch.object(menu, "__file__", str(Path(folder) / "subtitle_tools.py")), \
                 patch.object(menu, "choose", return_value="1"), \
                 patch.object(menu.subprocess, "Popen", return_value=child), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(menu.main([]), 130)
        self.assertEqual(child.wait.call_count, 2)
        child.kill.assert_not_called()

    def test_windows_menu_accepts_only_listed_single_keys_without_enter(self):
        menu = load_menu()
        console = SimpleNamespace(getwch=MagicMock(side_effect=["\xe0", "1", "9", "\r", "4"]))
        with patch.object(menu, "WINDOWS", True), patch.object(sys.stdin, "isatty", return_value=True), \
             patch.dict(sys.modules, {"msvcrt": console}), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(menu.choose(), "4")
        self.assertEqual(console.getwch.call_count, 5)

    @unittest.skipUnless(os.name == "nt", "Native CMD menu self-update requires Windows")
    def test_update_can_replace_running_menu_launcher(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / "simplify-ass"
            scripts.mkdir()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            shutil.copyfile(SOURCE, scripts / "subtitle_tools.py")
            launcher = bin_dir / "subtitle_tools.cmd"
            shutil.copyfile(ROOT / "installer/windows/bin/subtitle_tools.cmd", launcher)
            (scripts / "subtitle_tools_update.py").write_text(
                "from pathlib import Path\n"
                "p=Path(__file__).resolve().parent.parent/'bin'/'subtitle_tools.cmd'\n"
                "p.write_text('@echo off\\necho SHOULD_NOT_RUN\\nexit /b 99\\n')\n"
                "print('Update finished')\nraise SystemExit(7)\n")
            result = subprocess.run(["cmd.exe", "/d", "/s", "/c", f'""{launcher}""'],
                                    input="5\n", capture_output=True, text=True)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("Update finished", result.stdout)
            self.assertNotIn("SHOULD_NOT_RUN", result.stdout)


if __name__ == "__main__":
    unittest.main()
