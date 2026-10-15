"""Exercise installation, updates, and launcher argument forwarding contracts."""

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
INSTALLER = ROOT / "installer" / "windows"
TOOLS = ("simplify_subtitles", "remove_subtitles", "subtitle_flags", "sync_fonts")


def checkout(root):
    repository = root / "downloaded checkout with spaces"
    windows = repository / "installer" / "windows"
    shutil.copytree(INSTALLER, windows)
    for name in (*TOOLS, "simplify_ass"):
        (repository / (name + ".py")).write_text("# " + name + " version one\n")
    return repository


class InstallerChecks(unittest.TestCase):
    def run_installer(self, repository, *args):
        return subprocess.run([sys.executable, str(repository / "installer/windows/install.py"), *args],
                              capture_output=True, text=True)

    def test_custom_target_layout_updates_and_preserves_unrelated_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "My Tools with spaces"
            (target / "bin").mkdir(parents=True)
            unrelated = target / "bin" / "some-other-tool.cmd"
            unrelated.write_text("keep me")
            result = self.run_installer(repository, str(target))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(str(target / "bin"), result.stdout)
            self.assertIn("PATH was not changed", result.stdout)
            for name in (*TOOLS, "simplify_ass"):
                self.assertEqual((target / "simplify-ass" / (name + ".py")).read_bytes(),
                                 (repository / (name + ".py")).read_bytes())
            for name in TOOLS:
                self.assertEqual((target / "bin" / (name + ".cmd")).read_bytes(),
                                 (repository / "installer/windows/bin" / (name + ".cmd")).read_bytes())
            self.assertEqual(len(list(target.rglob("*.py"))), 5)
            (repository / "simplify_ass.py").write_text("# version two\n")
            result = self.run_installer(repository, "--target", str(target))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((target / "simplify-ass/simplify_ass.py").read_text(), "# version two\n")
            self.assertEqual(unrelated.read_text(), "keep me")
            self.assertEqual(list(target.rglob(".install-*")), [])

    def test_missing_source_fails_before_touching_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            (repository / "sync_fonts.py").unlink()
            target = root / "tools"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("untouched")
            result = self.run_installer(repository, str(target))
            self.assertEqual(result.returncode, 1)
            self.assertIn("complete repository", result.stdout)
            self.assertEqual(list(target.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(), "untouched")

    def test_install_when_sources_already_occupy_the_tool_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "Tools"
            target.mkdir()
            installed = target / "simplify-ass"
            repository.rename(installed)
            result = self.run_installer(installed, str(target))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((target / "bin/simplify_subtitles.cmd").is_file())
            self.assertEqual((installed / "simplify_ass.py").read_text(), "# simplify_ass version one\n")

    def test_default_target_and_conflicting_target_options(self):
        spec = importlib.util.spec_from_file_location("windows_install", INSTALLER / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with patch.object(installer, "install", return_value=(Path("bin"), Path("simplify-ass"))) as copy, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(installer.main([]), 0)
        self.assertEqual(copy.call_args.args[1], Path(r"C:\Tools").resolve())
        with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            installer.main(["one", "--target", "two"])

    def test_cwd_input_can_be_overridden_by_either_alias(self):
        # The CMD files prepend this default; argparse must keep the last alias.
        for name in TOOLS:
            spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            if name == "simplify_subtitles":
                parser = module.parser()
            else:
                # Capture the real CLI parser before it can scan or edit anything.
                parsers = []
                def stop(parser, args):
                    parsers.append(parser)
                    raise EOFError
                with patch.object(module.argparse.ArgumentParser, "parse_args", stop), self.assertRaises(EOFError):
                    module.main([])
                parser = parsers[0]
            for alias in ("-i", "--input"):
                with self.subTest(tool=name, alias=alias):
                    args = parser.parse_args(["--input", "current folder", alias, "other folder", "-r"])
                    self.assertEqual(args.input, Path("other folder"))
                    self.assertTrue(args.recursive)

    @unittest.skipUnless(os.name == "nt", "Native CMD launchers require Windows")
    def test_cmd_launchers_keep_cwd_forward_arguments_and_exit_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "Tools with spaces"
            (target / "bin").mkdir(parents=True)
            (target / "simplify-ass").mkdir()
            media = root / "media with spaces"
            media.mkdir()
            for name in TOOLS:
                launcher = target / "bin" / (name + ".cmd")
                shutil.copyfile(INSTALLER / "bin" / launcher.name, launcher)
                script = target / "simplify-ass" / (name + ".py")
                script.write_text("import json,sys,os\nprint(json.dumps([os.getcwd(),sys.argv[1:]]))\nsys.exit(7)\n")
                override = r"D:\Another Folder"
                command = f'""{launcher}" -i "{override}" -r"'
                result = subprocess.run(["cmd.exe", "/d", "/s", "/c", command], cwd=media,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
                cwd, args = json.loads(result.stdout.strip())
                self.assertEqual(Path(cwd), media)
                self.assertEqual(args, ["--input", str(media) + "\\.", "-i", override, "-r"])


if __name__ == "__main__":
    unittest.main()
