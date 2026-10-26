"""Local, git-only clean-tree controls for Boat's pinned Driver build.

These tests never start Boat, CUA, Chrome, Pomerado, or an API client.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


def _git(directory: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=directory, capture_output=True, text=True,
        check=True, timeout=10,
    )
    return result.stdout


class BoatCleanTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        if not shutil.which("git"):
            self.skipTest("git not installed")
        self.temp = tempfile.TemporaryDirectory(prefix="cua-boat-clean-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        _git(self.repo, "init", "-q")
        (self.repo / ".gitignore").write_text("target/\n")
        (self.repo / "Cargo.toml").write_text("[workspace]\n")
        _git(self.repo, "add", ".gitignore", "Cargo.toml")
        _git(self.repo, "-c", "user.name=Fixture",
             "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")

    def test_clean_gate_detects_untracked_source_contamination(self) -> None:
        script = Path(__file__).with_name("boat_setup.sh").read_text()
        self.assertIn('status --porcelain --untracked-files=all', script)
        self.assertEqual(_git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        (self.repo / "untracked_patch.rs").write_text("fn injected() {}\n")
        self.assertIn("?? untracked_patch.rs", _git(
            self.repo, "status", "--porcelain", "--untracked-files=all"))

    def test_ignored_build_cache_does_not_dirty_pinned_source(self) -> None:
        cache = self.repo / "target" / "release"
        cache.mkdir(parents=True)
        (cache / "cua-driver").write_bytes(b"cache")
        self.assertEqual(_git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")


if __name__ == "__main__":
    unittest.main()
