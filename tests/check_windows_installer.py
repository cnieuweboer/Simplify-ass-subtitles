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
from types import SimpleNamespace
from unittest.mock import MagicMock


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


def load_installer():
    spec = importlib.util.spec_from_file_location("windows_install", INSTALLER / "install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    return installer


class InstallerChecks(unittest.TestCase):
    def run_installer(self, repository, *args):
        return subprocess.run([sys.executable, str(repository / "installer/windows/install.py"), *args],
                              input="1\nn\n", capture_output=True, text=True)

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
            self.assertEqual(len(list(target.rglob("*.py"))), 8)
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

    def test_failed_rollback_keeps_recovery_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "tools"
            installer = load_installer()
            installer.install(repository, target)
            previous = (target / "simplify-ass/simplify_subtitles.py").read_bytes()
            (repository / "simplify_subtitles.py").write_text("# updated\n")
            original = Path.replace
            def replace(source, destination):
                if source.name == "new-1" or source.name == "old-simplify_subtitles.py":
                    raise PermissionError("locked file")
                return original(source, destination)
            with patch.object(Path, "replace", replace), self.assertRaisesRegex(RuntimeError, "Recovery copies were kept"):
                installer.install(repository, target)
            recovery = list(target.glob(".subtitle-tools-install-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual((recovery[0] / "old-simplify_subtitles.py").read_bytes(), previous)

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

    def test_reinstall_cancel_and_removal_preserve_unrelated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "tools"
            self.assertEqual(self.run_installer(repository, str(target)).returncode, 0)
            old = (target / "simplify-ass/simplify_ass.py").read_bytes()
            (repository / "simplify_ass.py").write_text("# new version\n")
            result = subprocess.run([sys.executable, str(repository / "installer/windows/install.py"), str(target)],
                                    input="q\n", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Existing installation found", result.stdout)
            self.assertEqual((target / "simplify-ass/simplify_ass.py").read_bytes(), old)
            other = target / "bin/other-tool.cmd"
            media = target / "simplify-ass/keep.mkv"
            other.write_text("other tool")
            media.write_text("user media")
            # Uninstall remains available even with an incomplete source checkout.
            (repository / "simplify_ass.py").unlink()
            result = subprocess.run([sys.executable, str(repository / "installer/windows/install.py"), str(target)],
                                    input="2\nn\n", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Removed 14 installed file(s)", result.stdout)
            self.assertEqual(other.read_text(), "other tool")
            self.assertEqual(media.read_text(), "user media")
            self.assertFalse(any(path.exists() for path in load_installer().installed_files(target)))

    def test_removal_cleans_only_empty_managed_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "tools"
            self.assertEqual(self.run_installer(repository, str(target)).returncode, 0)
            with patch("sys.stdout", new_callable=io.StringIO):
                load_installer().remove(target)
            self.assertFalse((target / "bin").exists())
            self.assertFalse((target / "simplify-ass").exists())

    def test_default_target_and_conflicting_target_options(self):
        spec = importlib.util.spec_from_file_location("windows_install", INSTALLER / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with patch.object(installer, "install", return_value=(Path("bin"), Path("simplify-ass"))) as copy, \
             patch.object(installer, "installed_files", return_value=[]), \
             patch.object(installer, "offer_path_change"), \
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


class MaintenanceChecks(unittest.TestCase):
    def setUp(self):
        self.installer = load_installer()

    def test_path_changes_preserve_other_entries_and_normalize_duplicates(self):
        installer = self.installer
        original = r"%UNTOUCHED_VARIABLE%\bin;D:\Keep;;C:\TOOLS\bin" + "\\"
        folder = Path(r"C:\Tools\bin")
        self.assertTrue(installer.has_path(original, folder))
        self.assertEqual(installer.updated_path(original, folder, True), original)
        self.assertEqual(installer.updated_path(original, folder, False), r"%UNTOUCHED_VARIABLE%\bin;D:\Keep;")
        original = ';'.join(fr"D:\Other Tools\{i}" for i in range(200))
        expanded = installer.updated_path(original, folder, True)
        self.assertGreater(len(expanded), 1024)
        self.assertEqual(expanded, original + ";" + str(folder))
        self.assertEqual(installer.updated_path(expanded, folder, False), original)
        with patch.dict(os.environ, {"SUBTITLE_INSTALL_TEST_ROOT": r"C:\Tools"}):
            self.assertTrue(installer.has_path(r'"%SUBTITLE_INSTALL_TEST_ROOT%\bin\"', folder))

    def test_shared_bin_warning_precedes_optional_path_removal(self):
        installer = self.installer
        with tempfile.TemporaryDirectory() as folder:
            bin_dir = Path(folder) / "bin"
            bin_dir.mkdir()
            other = bin_dir / "other-tool.cmd"
            other.touch()
            with patch.object(installer, "WINDOWS", True), \
                 patch.object(installer, "read_user_path", return_value=(str(bin_dir), 2)), \
                 patch.object(installer, "write_user_path") as write, \
                 patch("sys.stdout", new_callable=io.StringIO) as console:
                def confirm(prompt, allowed):
                    self.assertIn("Other files or folders remain", console.getvalue())
                    self.assertIn("from your user PATH? (y/N)", prompt)
                    return "n"
                with patch.object(installer, "prompt_key", side_effect=confirm):
                    installer.offer_path_change(bin_dir, adding=False)
            write.assert_not_called()
            self.assertTrue(other.is_file())

    def test_path_confirmation_preserves_edits_made_while_prompting(self):
        installer = self.installer
        folder = Path(r"C:\Tools\bin")
        with patch.object(installer, "WINDOWS", True), \
             patch.object(installer, "read_user_path", side_effect=[(r"D:\Keep", 1), (r"D:\Keep;E:\New", 2)]), \
             patch.object(installer, "prompt_key", return_value="y"), \
             patch.object(installer, "write_user_path") as write, \
             patch("sys.stdout", new_callable=io.StringIO):
            installer.offer_path_change(folder, adding=True)
        write.assert_called_once_with(r"D:\Keep;E:\New;C:\Tools\bin", 2)
        with patch.object(installer, "WINDOWS", True), \
             patch.object(installer, "read_user_path", return_value=(r"C:\Tools\bin;D:\Keep;c:/TOOLS/bin/", 2)), \
             patch.object(installer, "prompt_key", return_value="y"), \
             patch.object(installer, "write_user_path") as write, \
             patch("sys.stdout", new_callable=io.StringIO):
            installer.offer_path_change(folder, adding=False)
        write.assert_called_once_with(r"D:\Keep", 2)

    def test_already_present_or_absent_path_does_not_prompt(self):
        installer = self.installer
        for value, adding in ((r"c:/tools/bin/", True), (r"D:\Keep", False)):
            with patch.object(installer, "WINDOWS", True), \
                 patch.object(installer, "read_user_path", return_value=(value, 2)), \
                 patch.object(installer, "prompt_key") as prompt, \
                 patch("sys.stdout", new_callable=io.StringIO):
                installer.offer_path_change(Path(r"C:\Tools\bin"), adding)
            prompt.assert_not_called()

    def test_registry_write_keeps_type_and_only_targets_current_user(self):
        installer = self.installer
        registry = SimpleNamespace(HKEY_CURRENT_USER=object(), KEY_READ=1, KEY_SET_VALUE=2,
                                   REG_SZ=1, REG_EXPAND_SZ=2,
                                   OpenKey=MagicMock(), CreateKeyEx=MagicMock(),
                                   QueryValueEx=MagicMock(return_value=(r"%USERPROFILE%\bin", 2)),
                                   SetValueEx=MagicMock())
        with patch.dict(sys.modules, {"winreg": registry}), patch.object(installer, "notify_environment", return_value=True):
            self.assertEqual(installer.read_user_path(), (r"%USERPROFILE%\bin", 2))
            for kind in (1, 2):
                installer.write_user_path(r"%USERPROFILE%\bin;C:\Tools\bin", kind)
                self.assertEqual(registry.SetValueEx.call_args.args[3:], (kind, r"%USERPROFILE%\bin;C:\Tools\bin"))
        registry.OpenKey.assert_called_once_with(registry.HKEY_CURRENT_USER, "Environment", 0, 1)
        self.assertTrue(all(call.args[0] is registry.HKEY_CURRENT_USER for call in registry.CreateKeyEx.call_args_list))

    def test_install_unblocks_all_managed_files_including_in_place_sources(self):
        installer = self.installer
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "tools"
            with patch.object(installer, "unblock") as unblock:
                installer.install(repository, target)
            self.assertEqual(set(call.args[0] for call in unblock.call_args_list), set(installer.installed_files(target)))
            placed = root / "placed"
            placed.mkdir()
            repository.rename(placed / "simplify-ass")
            with patch.object(installer, "unblock") as unblock:
                installer.install(placed / "simplify-ass", placed)
            self.assertEqual(unblock.call_count, 14)

    def test_prompt_only_accepts_listed_keys_and_defaults_to_no_or_cancel(self):
        installer = self.installer
        with patch.object(installer, "WINDOWS", False), patch("builtins.input", side_effect=["3", "1"]):
            self.assertEqual(installer.prompt_key("Choose: ", ("1", "2", "q")), "1")
        with patch.object(installer, "WINDOWS", False), patch("builtins.input", side_effect=EOFError):
            self.assertEqual(installer.prompt_key("Confirm: ", ("y", "n")), "n")
            self.assertEqual(installer.prompt_key("Choose: ", ("1", "2", "q")), "q")

    def test_windows_prompt_ignores_extended_and_unlisted_keys_without_enter(self):
        installer = self.installer
        console = SimpleNamespace(getwch=MagicMock(side_effect=["\xe0", "1", "9", "\r", "2"]))
        with patch.object(installer, "WINDOWS", True), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch.dict(sys.modules, {"msvcrt": console}), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(installer.prompt_key("Choose: ", ("1", "2", "q")), "2")
            self.assertEqual(console.getwch.call_count, 5)

    @unittest.skipUnless(os.name == "nt", "NTFS Zone.Identifier requires Windows")
    def test_native_unblock_removes_only_the_download_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "tool.cmd"
            script.write_text("@echo off\n")
            marker = Path(str(script) + ":Zone.Identifier")
            marker.write_text("[ZoneTransfer]\nZoneId=3\n")
            self.installer.unblock(script)
            self.installer.unblock(script)
            self.assertFalse(marker.exists())
            self.assertEqual(script.read_text(), "@echo off\n")


if __name__ == "__main__":
    unittest.main()
