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
TOOLS = ("simplify_subtitles", "subtitle_tracks", "subtitle_properties", "sync_fonts")


def checkout(root):
    repository = root / "downloaded checkout with spaces"
    windows = repository / "installer" / "windows"
    shutil.copytree(INSTALLER, windows)
    for name in (*TOOLS, "simplify_ass"):
        (repository / (name + ".py")).write_text("# " + name + " version one\n")
    package = repository / "_simplify_ass"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "font_metrics.py").write_text("# measurement version one\n")
    return repository


def load_installer():
    spec = importlib.util.spec_from_file_location("windows_install", INSTALLER / "install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    return installer


class InstallerChecks(unittest.TestCase):
    def run_installer(self, repository, *args):
        return subprocess.run([sys.executable, str(repository / "installer/windows/install.py"), *args],
                              input="1\ny\nn\nn\n", capture_output=True, text=True)

    def test_package_is_required_before_touching_an_existing_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root/'tools'
            owner = load_installer(); owner.install(repository, target)
            before = {str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}
            (repository/'_simplify_ass/__init__.py').unlink()
            with self.assertRaisesRegex(RuntimeError, 'complete repository'):
                owner.install(repository, target)
            self.assertEqual(before, {str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()})

    def test_failed_first_package_upgrade_restores_the_old_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root/'tools'
            owner = load_installer(); owner.install(repository, target)
            package = target/'simplify-ass/_simplify_ass'; shutil.rmtree(package)
            before = {str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}
            (repository/'simplify_ass.py').write_text('# new engine\n')
            original = Path.replace
            def replace(source, destination):
                if source.name.startswith('new-') and Path(destination).name=='font_metrics.py':
                    raise PermissionError('locked module')
                return original(source, destination)
            with patch.object(Path, 'replace', replace), self.assertRaises(PermissionError):
                owner.install(repository, target)
            self.assertEqual(before, {str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()})
            self.assertFalse(package.exists())

    def test_reinstall_bridge_preserves_existing_launcher_choices(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root/'tools'
            owner = load_installer(); owner.install(repository, target, individual_launchers=True)
            shutil.rmtree(target/'simplify-ass/_simplify_ass')
            (target/'bin/subtitle_tracks.cmd').unlink()
            launchers = {p.name for p in (target/'bin').iterdir()}
            with patch.object(owner, '__file__', str(repository/'installer/windows/install.py')), \
                 patch.object(owner, 'prompt_key', return_value='1') as prompt, \
                 patch.object(owner, 'offer_path_change'), patch.object(owner, 'offer_dependencies'), \
                 patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(owner.main(['--target',str(target),'--keep-launchers']),0)
            self.assertEqual(prompt.call_count,1)
            self.assertEqual({p.name for p in (target/'bin').iterdir()},launchers)
            for name in owner.source_modules(repository):
                self.assertEqual((target/'simplify-ass'/name).read_bytes(),(repository/name).read_bytes())

    def test_uninstall_retains_unrelated_package_files_and_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root/'tools'
            owner = load_installer(); owner.install(repository, target)
            cache = target/'simplify-ass/_simplify_ass/__pycache__'; cache.mkdir()
            managed = cache/'font_metrics.cpython-312.pyc'; managed.write_bytes(b'generated')
            unrelated = cache/'user.cpython-312.pyc'; unrelated.write_bytes(b'user')
            notes = cache/'font_metrics.notes.txt'; notes.write_text('keep')
            with patch('sys.stdout', new_callable=io.StringIO):owner.remove(target)
            self.assertFalse(managed.exists())
            self.assertEqual(unrelated.read_bytes(),b'user')
            self.assertEqual(notes.read_text(),'keep')

    def test_nested_modules_are_discovered_retired_and_uninstalled_by_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root / "tools"
            owner = load_installer()
            nested = repository / "_simplify_ass/geometry"
            nested.mkdir()
            (nested / "__init__.py").write_text("")
            (nested / "outlines.py").write_text("VALUE = 214\n")
            (nested / "README.md").write_text("not runtime")
            owner.install(repository, target)
            installed = target / "simplify-ass/_simplify_ass/geometry"
            self.assertEqual((installed / "outlines.py").read_text(), "VALUE = 214\n")
            self.assertFalse((installed / "README.md").exists())
            cache = installed / "__pycache__"; cache.mkdir()
            (cache / "outlines.cpython-312.pyc").write_bytes(b"owned cache")
            user = installed / "user.py"; user.write_text("# user\n")
            user_cache = cache / "user.cpython-312.pyc"; user_cache.write_bytes(b"user cache")
            shutil.rmtree(nested)
            owner.install(repository, target)
            self.assertFalse((installed / "outlines.py").exists())
            self.assertFalse((cache / "outlines.cpython-312.pyc").exists())
            settings = json.loads((target / "simplify-ass/install_settings.json").read_text())
            self.assertEqual(settings["version"], 2)
            self.assertEqual(settings["engine_modules"], list(owner.source_modules(repository)))
            with patch("sys.stdout", new_callable=io.StringIO):
                owner.remove(target)
            self.assertEqual(user.read_text(), "# user\n")
            self.assertEqual(user_cache.read_bytes(), b"user cache")

    def test_retired_module_deletion_failure_restores_sources_caches_and_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root / "tools"
            owner = load_installer(); owner.install(repository, target)
            package = target / "simplify-ass/_simplify_ass"
            cache = package / "__pycache__"; cache.mkdir()
            retired_cache = cache / "font_metrics.cpython-312.pyc"; retired_cache.write_bytes(b"old cache")
            before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            (repository / "_simplify_ass/font_metrics.py").unlink()
            nested = repository / "_simplify_ass/new/deep"; nested.mkdir(parents=True)
            (nested / "helper.py").write_text("# new\n")
            original = Path.unlink
            def unlink(path, *args, **kwargs):
                if path == retired_cache:
                    raise PermissionError("locked retired cache")
                return original(path, *args, **kwargs)
            with patch.object(Path, "unlink", unlink), self.assertRaises(PermissionError):
                owner.install(repository, target)
            self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()})
            self.assertFalse((package / "new").exists())
            self.assertFalse(list(target.glob(".subtitle-tools-install-*")))
            owner.install(repository, target)
            self.assertFalse(retired_cache.exists())
            self.assertFalse((package / "__pycache__").exists())
            with patch("sys.stdout", new_callable=io.StringIO):
                owner.remove(target)
            self.assertFalse((target / "simplify-ass").exists())

    def test_invalid_ownership_and_unowned_collisions_fail_without_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root / "tools"
            owner = load_installer(); owner.install(repository, target)
            settings = target / "simplify-ass/install_settings.json"
            original = settings.read_bytes()
            invalid = ("../outside.py", "_simplify_ass/../../outside.py", "_simplify_ass/C:bad.py",
                       "_simplify_ass//bad.py", "_simplify_ass/__pycache__/bad.py", "_simplify_ass/CON.py",
                       "_simplify_ass/bad.py:stream", "_simplify_ass/../bad.py", "_simplify_ass/xx\\bad.py")
            for name in invalid:
                data = json.loads(original); data["engine_modules"].append(name)
                settings.write_text(json.dumps(data))
                before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
                with self.subTest(name=name):
                    for action in (lambda: owner.install(repository, target, True), lambda: owner.remove(target)):
                        with self.assertRaisesRegex(RuntimeError, "ownership inventory"):
                            action()
                        self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()})
            settings.write_bytes(original)
            user = target / "simplify-ass/_simplify_ass/new.py"; user.write_text("# user\n")
            (repository / "_simplify_ass/new.py").write_text("# incoming\n")
            with self.assertRaisesRegex(RuntimeError, "unrelated file"):
                owner.install(repository, target)
            self.assertEqual(user.read_text(), "# user\n")
            self.assertEqual(settings.read_bytes(), original)

    def test_staging_failure_does_not_take_ownership_or_change_installed_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root / "tools"
            owner = load_installer(); owner.install(repository, target)
            before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            added = repository / "_simplify_ass/helper.py"; added.write_text("# new\n")
            original = shutil.copy2
            def copy(source, destination, *args, **kwargs):
                if source == added:
                    raise OSError("unreadable new module")
                return original(source, destination, *args, **kwargs)
            with patch.object(owner.shutil, "copy2", copy), self.assertRaises(OSError):
                owner.install(repository, target)
            self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()})
            self.assertFalse(list(target.glob(".subtitle-tools-install-*")))

    def test_case_only_renames_and_corrupt_settings_are_rejected_before_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root / "tools"
            owner = load_installer(); owner.install(repository, target)
            before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            (repository / "_simplify_ass/font_metrics.py").rename(repository / "_simplify_ass/Font_metrics.py")
            with self.assertRaisesRegex(RuntimeError, "Case-only"):
                owner.install(repository, target)
            self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()})
            settings = target / "simplify-ass/install_settings.json"
            for invalid in ("{broken", "[]", '{"version": 2, "launchers": []}'):
                settings.write_text(invalid)
                with self.assertRaisesRegex(RuntimeError, "ownership inventory"):
                    owner.remove(target)
                self.assertTrue((target / "simplify-ass/simplify_ass.py").exists())

    def test_linked_package_is_rejected_before_install_or_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repository = checkout(root); target = root / "tools"
            owner = load_installer(); owner.install(repository, target)
            package = target / "simplify-ass/_simplify_ass"
            outside = root / "outside"; package.rename(outside)
            try:
                package.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Directory symlinks unavailable")
            before = {p.name: p.read_bytes() for p in outside.iterdir()}
            for action in (lambda: owner.install(repository, target), lambda: owner.remove(target)):
                with self.assertRaisesRegex(RuntimeError, "Linked"):
                    action()
                self.assertEqual(before, {p.name: p.read_bytes() for p in outside.iterdir()})
            self.assertTrue((target / "simplify-ass/simplify_ass.py").exists())

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
            self.assertEqual(len(list(target.rglob("*.py"))), 10)
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
            installer.install(repository, target, individual_launchers=True)
            previous = (target / "simplify-ass/simplify_subtitles.py").read_bytes()
            (repository / "simplify_subtitles.py").write_text("# updated\n")
            original = Path.replace
            def replace(source, destination):
                if source.name == "new-1" or source.name.endswith("-simplify_subtitles.py"):
                    raise PermissionError("locked file")
                return original(source, destination)
            with patch.object(Path, "replace", replace), self.assertRaisesRegex(RuntimeError, "Recovery copies were kept"):
                installer.install(repository, target, individual_launchers=True)
            recovery = list(target.glob(".subtitle-tools-install-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual((recovery[0] / "old-0-simplify_subtitles.py").read_bytes(), previous)

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
            self.assertIn("Removed 17 installed file(s)", result.stdout)
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

    def test_default_install_only_creates_menu_launcher(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "tools"
            result = subprocess.run([sys.executable, str(repository / "installer/windows/install.py"), str(target)],
                                    input="\nn\nn\n", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([path.name for path in (target / "bin").iterdir()], ["subtitle_tools.cmd"])
            settings = json.loads((target / "simplify-ass/install_settings.json").read_text())
            self.assertEqual(settings["launchers"], ["subtitle_tools"])
            self.assertEqual(len(list((target / "simplify-ass").glob("*.py"))), 8)

    def test_reinstall_removes_only_our_optional_launchers_and_rolls_back_deletions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = checkout(root)
            target = root / "tools"
            installer = load_installer()
            installer.install(repository, target, individual_launchers=True)
            other = target / "bin/other-tool.cmd"
            other.write_text("keep")
            before = {str(path.relative_to(target)): path.read_bytes() for path in target.rglob("*") if path.is_file()}
            original = Path.unlink
            def unlink(path, *args, **kwargs):
                if path == target / "bin/subtitle_tracks.cmd":
                    raise PermissionError("locked launcher")
                return original(path, *args, **kwargs)
            with patch.object(Path, "unlink", unlink), self.assertRaises(PermissionError):
                installer.install(repository, target, individual_launchers=False)
            after = {str(path.relative_to(target)): path.read_bytes() for path in target.rglob("*") if path.is_file()}
            self.assertEqual(after, before)
            installer.install(repository, target, individual_launchers=False)
            self.assertEqual({path.name for path in (target / "bin").iterdir()}, {"subtitle_tools.cmd", "other-tool.cmd"})
            self.assertEqual(other.read_text(), "keep")

    def test_default_target_and_conflicting_target_options(self):
        spec = importlib.util.spec_from_file_location("windows_install", INSTALLER / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with patch.object(installer, "install", return_value=(Path("bin"), Path("simplify-ass"))) as copy, \
             patch.object(installer, "installed_files", return_value=[]), \
             patch.object(installer, "offer_path_change"), \
             patch.object(installer, "offer_dependencies"), \
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
                installer.install(repository, target, individual_launchers=True)
            self.assertEqual(set(call.args[0] for call in unblock.call_args_list), set(path for path in installer.installed_files(target) if path.is_file()))
            placed = root / "placed"
            placed.mkdir()
            repository.rename(placed / "simplify-ass")
            with patch.object(installer, "unblock") as unblock:
                installer.install(placed / "simplify-ass", placed, individual_launchers=True)
            self.assertEqual(unblock.call_count, 17)

    def test_prompt_only_accepts_listed_keys_and_defaults_to_no_or_cancel(self):
        installer = self.installer
        with patch.object(installer, "WINDOWS", False), patch("builtins.input", side_effect=["3", "1"]):
            self.assertEqual(installer.prompt_key("Choose: ", ("1", "2", "q")), "1")
        with patch.object(installer, "WINDOWS", False), patch("builtins.input", side_effect=EOFError):
            self.assertEqual(installer.prompt_key("Confirm: ", ("y", "n")), "n")
            self.assertEqual(installer.prompt_key("Choose: ", ("1", "2", "q")), "q")

    def test_dependency_check_uses_the_installers_python(self):
        installer = self.installer
        result = subprocess.CompletedProcess([], 0, '["fonttools"]\n', '')
        with patch.object(installer.subprocess, "run", return_value=result) as run:
            self.assertEqual(installer.missing_packages(), ["fonttools"])
        self.assertEqual(run.call_args.args[0][:2], [sys.executable, "-c"])

    def test_dependency_install_is_optional_and_installs_only_missing_packages(self):
        installer = self.installer
        with patch.object(installer, "missing_packages", return_value=[]), \
             patch.object(installer, "prompt_key") as prompt, patch("sys.stdout", new_callable=io.StringIO):
            installer.offer_dependencies()
        prompt.assert_not_called()
        with patch.object(installer, "missing_packages", return_value=["Pillow"]), \
             patch.object(installer, "prompt_key", return_value="n"), \
             patch.object(installer.subprocess, "run") as run, patch("sys.stdout", new_callable=io.StringIO):
            installer.offer_dependencies()
        run.assert_not_called()
        for venv in (False, True):
            with patch.object(installer, "missing_packages", side_effect=[["Pillow", "uharfbuzz"], []]), \
                 patch.object(installer, "prompt_key", return_value="y"), \
                 patch.object(installer.subprocess, "run") as run, \
                 patch.object(sys, "prefix", "venv" if venv else sys.base_prefix), \
                 patch("sys.stdout", new_callable=io.StringIO):
                installer.offer_dependencies()
            command = run.call_args.args[0]
            self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
            self.assertEqual(command[-2:], ["Pillow", "uharfbuzz"])
            self.assertEqual("--user" in command, not venv)

    def test_dependency_install_failures_are_reported(self):
        installer = self.installer
        with patch.object(installer, "missing_packages", return_value=["fonttools"]), \
             patch.object(installer, "prompt_key", return_value="y"), \
             patch.object(installer.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")), \
             patch("sys.stdout", new_callable=io.StringIO), self.assertRaisesRegex(RuntimeError, "installation failed"):
            installer.offer_dependencies()

    def test_windows_confirmation_enter_selects_default_no(self):
        installer = self.installer
        for enter in ("\r", "\n"):
            console = SimpleNamespace(getwch=MagicMock(side_effect=[enter, "y"]))
            with self.subTest(enter=repr(enter)), patch.object(installer, "WINDOWS", True), \
                 patch.object(sys.stdin, "isatty", return_value=True), \
                 patch.dict(sys.modules, {"msvcrt": console}), \
                 patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(installer.prompt_key("Install individual launchers? (y/N): ", ("y", "n")), "n")
            self.assertEqual(console.getwch.call_count, 1)

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
