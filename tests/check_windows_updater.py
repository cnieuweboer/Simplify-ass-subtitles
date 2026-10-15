"""Check pinned downloads, arbitrary install roots, and failed-update rollback."""

import hashlib
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

from check_windows_installer import INSTALLER, TOOLS, checkout, load_installer


def load_updater():
    spec = importlib.util.spec_from_file_location("windows_updater", INSTALLER / "subtitle_tools_update.py")
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    return updater


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class UpdaterChecks(unittest.TestCase):
    def setUp(self):
        self.updater = load_updater()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = checkout(self.root)
        self.target = self.root / "My relocated tools with spaces"
        load_installer().install(self.repository, self.target, individual_launchers=True)
        (self.target / "bin/other-tool.cmd").write_text("unrelated")
        (self.target / "simplify-ass/user.mkv").write_text("user media")
        self.before = snapshot(self.target)
        self.sha = "a" * 40
        self.tree_sha = "b" * 40
        self.files = {tool + ".py": ("# updated " + tool + "\n").encode() for tool in (*TOOLS, "simplify_ass")}
        for name in ("install.py", "subtitle_tools_update.py", "subtitle_tools.py"):
            self.files["installer/windows/" + name] = (INSTALLER / name).read_bytes()
        for tool in (*TOOLS, "subtitle_tools_update", "subtitle_tools"):
            name = "installer/windows/bin/" + tool + ".cmd"
            self.files[name] = (INSTALLER / "bin" / (tool + ".cmd")).read_bytes()
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        # No installed file may change before every download finishes.
        self.assertEqual(snapshot(self.target), self.before)
        if url == self.updater.API + "/commits/main":
            return json.dumps({"sha": self.sha, "commit": {"tree": {"sha": self.tree_sha}}}).encode()
        if url == self.updater.API + f"/git/trees/{self.tree_sha}?recursive=1":
            entries = []
            for name, data in self.files.items():
                sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                entries.append({"path": name, "sha": sha, "type": "blob", "mode": "100644"})
            entries.append({"path": "fixtures/large.mkv", "sha": "c" * 40, "type": "blob", "mode": "100644"})
            return json.dumps({"tree": entries, "truncated": False}).encode()
        prefix = self.updater.RAW + "/" + self.sha + "/"
        self.assertTrue(url.startswith(prefix), url)
        return self.files[url[len(prefix):]]

    def test_updates_every_managed_file_from_one_revision_and_keeps_unrelated_files(self):
        with patch.object(self.updater, "download", side_effect=self.fetch), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.updater.update(self.target), self.sha)
        for tool in (*TOOLS, "simplify_ass"):
            self.assertEqual((self.target / "simplify-ass" / (tool + ".py")).read_bytes(), self.files[tool + ".py"])
        for name in ("install.py", "subtitle_tools_update.py", "subtitle_tools.py"):
            self.assertEqual((self.target / "simplify-ass" / name).read_bytes(), self.files["installer/windows/" + name])
        for tool in (*TOOLS, "subtitle_tools_update", "subtitle_tools"):
            self.assertEqual((self.target / "bin" / (tool + ".cmd")).read_bytes(), self.files["installer/windows/bin/" + tool + ".cmd"])
        self.assertEqual((self.target / "bin/other-tool.cmd").read_text(), "unrelated")
        self.assertEqual((self.target / "simplify-ass/user.mkv").read_text(), "user media")
        self.assertEqual(self.calls.count(self.updater.API + "/commits/main"), 1)
        self.assertFalse(any("fixtures" in url for url in self.calls))
        self.assertFalse(list(self.target.glob(".subtitle-tools-install-*")))

    def test_download_failure_or_invalid_content_never_modifies_installation(self):
        for mode in ("network", "hash", "syntax", "missing"):
            with self.subTest(mode=mode):
                saved = dict(self.files)
                if mode == "syntax":
                    self.files["sync_fonts.py"] = b"def broken(:\n"
                if mode == "missing":
                    del self.files["sync_fonts.py"]
                def fetch(url):
                    if url.endswith("/sync_fonts.py"):
                        if mode == "network":
                            raise OSError("connection failed")
                        if mode == "hash":
                            return b"wrong download"
                    return self.fetch(url)
                with patch.object(self.updater, "download", side_effect=fetch), patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(self.updater.main(["--target", str(self.target)]), 1)
                self.assertEqual(snapshot(self.target), self.before)
                self.files = saved

    def test_update_respects_opted_out_and_manually_removed_launchers(self):
        installer = load_installer()
        for individual in (False, True):
            with self.subTest(individual=individual):
                installer.install(self.repository, self.target, individual_launchers=individual)
                missing = self.target / "bin/remove_subtitles.cmd"
                missing.unlink(missing_ok=True)
                self.before = snapshot(self.target)
                with patch.object(self.updater, "download", side_effect=self.fetch), patch("sys.stdout", new_callable=io.StringIO):
                    self.updater.update(self.target)
                self.assertFalse(missing.exists())
                self.assertTrue((self.target / "bin/subtitle_tools.cmd").is_file())
                if not individual:
                    self.assertEqual({p.name for p in (self.target / "bin").iterdir()}, {"subtitle_tools.cmd", "other-tool.cmd"})
                settings = json.loads((self.target / "simplify-ass/install_settings.json").read_text())
                self.assertNotIn("remove_subtitles", settings["launchers"])

    def check_rollback(self, interrupt):
        # Simulate upgrading an installation made before updater support existed.
        for path in (self.target / "simplify-ass/install.py", self.target / "simplify-ass/subtitle_tools_update.py",
                     self.target / "bin/subtitle_tools_update.cmd", self.target / "simplify-ass/subtitle_tools.py",
                     self.target / "bin/subtitle_tools.cmd", self.target / "simplify-ass/install_settings.json"):
            path.unlink()
        self.before = snapshot(self.target)
        original = Path.replace
        def replace(source, destination):
            if source.name.startswith("new-") and Path(destination).name == "subtitle_tools.cmd":
                if interrupt:
                    raise KeyboardInterrupt
                raise PermissionError("locked launcher")
            return original(source, destination)
        with patch.object(self.updater, "download", side_effect=self.fetch), \
             patch.object(Path, "replace", replace), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.updater.main(["--target", str(self.target)]), 130 if interrupt else 1)
        self.assertEqual(snapshot(self.target), self.before)
        self.assertFalse(list(self.target.glob(".subtitle-tools-install-*")))

    def test_failed_replacement_restores_previous_and_removes_new_files(self):
        self.check_rollback(False)

    def test_cancellation_during_replacement_rolls_back(self):
        self.check_rollback(True)

    def test_default_target_follows_installed_updater_after_relocation(self):
        location = self.target / "simplify-ass/subtitle_tools_update.py"
        with patch.object(self.updater, "__file__", str(location)), \
             patch.object(self.updater, "download", side_effect=self.fetch), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.updater.main([]), 0)
        self.assertEqual((self.target / "simplify-ass/sync_fonts.py").read_bytes(), self.files["sync_fonts.py"])

    def test_unknown_installation_fails_without_downloading(self):
        target = self.root / "not an installation"
        with patch.object(self.updater, "download") as download, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.updater.main(["--target", str(target)]), 1)
        download.assert_not_called()
        self.assertFalse(target.exists())

    def test_download_limit_and_remote_path_selection(self):
        with patch.object(self.updater, "urlopen", return_value=io.BytesIO(b"123456789")), \
             patch.object(self.updater, "MAX_DOWNLOAD", 8):
            with self.assertRaisesRegex(RuntimeError, "download limit"):
                self.updater.download("https://api.github.com/example")
        for name in ("../bad.py", "/bad.py", "installer/windows/../bad.py", "fixtures/font.ttf", "README.md"):
            self.assertFalse(self.updater.selected_file(name), name)

    @unittest.skipUnless(os.name == "nt", "Native CMD self-update requires Windows")
    def test_cmd_can_replace_itself_and_keep_the_updaters_exit_status(self):
        script = self.target / "simplify-ass/subtitle_tools_update.py"
        script.write_text("from pathlib import Path\nimport sys\n"
                          "p=Path(__file__).resolve().parent.parent/'bin'/'subtitle_tools_update.cmd'\n"
                          "p.write_text('@echo off\\necho SHOULD_NOT_RUN\\nexit /b 99\\n')\n"
                          "print('Update finished')\nsys.exit(7)\n")
        launcher = self.target / "bin/subtitle_tools_update.cmd"
        result = subprocess.run(["cmd.exe", "/d", "/s", "/c", f'""{launcher}""'],
                                capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertIn("Update finished", result.stdout)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout)


if __name__ == "__main__":
    unittest.main()
