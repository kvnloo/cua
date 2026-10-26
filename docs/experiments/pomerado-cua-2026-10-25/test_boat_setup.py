"""Bats-free, unprivileged refusal tests for the Boat VM preflight.

All filesystem mutations stay inside a TemporaryDirectory. The inspector's
fake-root seam cannot be selected by the real CLI or executable setup script.
No sudo, browser, CUA, Pomerado, network, or mint is used.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from boat_preflight import inspect_chrome, validate_driver_version


class ChromePreflightFakeRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="boat-preflight-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.google = self.root / "opt/google"
        self.chrome_dir = self.google / "chrome"
        self.chrome_dir.mkdir(parents=True)
        self.chrome = self.chrome_dir / "google-chrome"
        self.chrome.write_text("#!/bin/sh\nexit 0\n")
        self.chrome.chmod(0o755)
        self.fake_uids: dict[Path, int] = {}
        self.fake_gids: dict[Path, int] = {}

    def fake_lstat(self, path: Path) -> SimpleNamespace:
        real = os.lstat(path)
        # Only the mock return value has uid/gid 0. No chown is ever issued.
        return SimpleNamespace(
            st_mode=real.st_mode,
            st_uid=self.fake_uids.get(path, 0),
            st_gid=self.fake_gids.get(path, 0),
        )

    def findings(self):
        return inspect_chrome(root=self.root, lstat_fn=self.fake_lstat)

    def test_clean_fake_root_is_idempotently_accepted(self) -> None:
        self.assertEqual(self.findings(), [])
        self.assertEqual(self.findings(), [])

    def test_missing_binary_fails_closed(self) -> None:
        self.chrome.unlink()
        found = self.findings()
        self.assertEqual([(f.code, f.path) for f in found],
                         [("MISSING", "/opt/google/chrome/google-chrome")])

    def test_unowned_opt_prints_exact_chown_remedy(self) -> None:
        self.fake_uids[self.root / "opt"] = 1000
        found = self.findings()
        self.assertEqual([(f.code, f.path, f.remedy) for f in found],
                         [("OWNER", "/opt", "sudo chown root:root /opt")])

    def test_wrong_group_owner_is_refused(self) -> None:
        self.fake_gids[self.google] = 1000
        self.assertEqual(self.findings()[0].remedy,
                         "sudo chown root:root /opt/google")

    def test_group_writable_ancestor_is_refused(self) -> None:
        self.google.chmod(0o775)
        found = self.findings()
        self.assertEqual([(f.code, f.remedy) for f in found],
                         [("MODE", "sudo chmod go-w /opt/google")])

    def test_world_writable_binary_is_refused(self) -> None:
        self.chrome.chmod(0o777)
        self.assertEqual(self.findings()[0].code, "MODE")

    def test_symlink_ancestor_is_refused_without_following(self) -> None:
        backup = self.root / "google.original"
        self.google.rename(backup)
        self.google.symlink_to(backup, target_is_directory=True)
        found = self.findings()
        self.assertEqual([(f.code, f.path) for f in found],
                         [("SYMLINK", "/opt/google")])

    def test_symlink_executable_is_refused(self) -> None:
        target = self.chrome_dir / "real-chrome"
        self.chrome.rename(target)
        self.chrome.symlink_to(target)
        self.assertEqual(self.findings()[0].code, "SYMLINK")

    def test_nonregular_binary_is_refused(self) -> None:
        self.chrome.unlink()
        self.chrome.mkdir()
        self.assertEqual(self.findings()[0].code, "TYPE")

    def test_nonexecutable_binary_is_refused(self) -> None:
        self.chrome.chmod(0o644)
        self.assertEqual(self.findings()[0].code, "EXEC")

    def test_unowned_mount_root_is_refused(self) -> None:
        self.fake_uids[self.root] = 123
        self.assertEqual(self.findings()[0].path, "/")

    def test_readonly_fake_root_never_mutates_modes(self) -> None:
        self.google.chmod(0o777)
        old = os.stat(self.google).st_mode
        self.assertTrue(self.findings())
        self.assertEqual(os.stat(self.google).st_mode, old)


class DriverPinTests(unittest.TestCase):
    def test_expected_version_only(self) -> None:
        validate_driver_version("cua-driver 0.34.0", "0.34.0")

    def test_boat_preinstalled_release_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "BRANCH_DRIVER_MISMATCH"):
            validate_driver_version("cua-driver 0.23.2", "0.34.0")

    def test_version_output_must_be_exact(self) -> None:
        with self.assertRaises(ValueError):
            validate_driver_version("cua-driver 0.34.0 debug", "0.34.0")

    def test_cli_refuses_old_version_without_running_setup(self) -> None:
        checker = Path(__file__).with_name("boat_preflight.py")
        completed = subprocess.run(
            [sys.executable, str(checker), "version",
             "--observed", "cua-driver 0.23.2", "--expected", "0.34.0"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("BRANCH_DRIVER_MISMATCH", completed.stderr)

    def test_setup_shell_parses_without_running_a_vm(self) -> None:
        if not shutil.which("bash"):
            self.skipTest("bash not installed")
        script = Path(__file__).with_name("boat_setup.sh")
        completed = subprocess.run(["bash", "-n", str(script)],
                                   capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
