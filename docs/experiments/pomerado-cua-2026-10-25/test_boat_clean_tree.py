"""Local, git-only clean-tree controls for Boat's pinned Driver build.

These tests never start Boat, CUA, Chrome, Pomerado, or an API client.
"""
from __future__ import annotations

from pathlib import Path
import re
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


    def _run_exact_index_gate(self) -> subprocess.CompletedProcess[str]:
        """Execute the production shell gate against a disposable Git repo."""
        script = Path(__file__).with_name("boat_setup.sh").read_text()
        match = re.search(r"(?ms)^reject_git_index_flags\(\) \{\n.*?^\}\n", script)
        self.assertIsNotNone(match, "index flag guard missing from Boat setup")
        self.assertIn('reject_git_index_flags "$repo_root"', script)
        program = (
            "set -euo pipefail\n"
            'die() { echo "$*" >&2; exit 2; }\n'
            + match.group(0)
            + 'reject_git_index_flags "$1"\n'
        )
        return subprocess.run(
            ["bash", "-c", program, "guard", str(self.repo)],
            capture_output=True, text=True, timeout=10, check=False,
        )

    def test_no_hidden_index_flags_allows_clean_tree(self) -> None:
        result = self._run_exact_index_gate()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_assume_unchanged_does_not_hide_tampered_tracked_source(self) -> None:
        _git(self.repo, "update-index", "--assume-unchanged", "Cargo.toml")
        (self.repo / "Cargo.toml").write_text("[workspace]\n# hidden tampering\n")
        self.assertEqual(_git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertIn("h Cargo.toml", _git(self.repo, "ls-files", "-v"))
        result = self._run_exact_index_gate()
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_skip_worktree_does_not_hide_tampered_tracked_source(self) -> None:
        _git(self.repo, "update-index", "--skip-worktree", "Cargo.toml")
        (self.repo / "Cargo.toml").write_text("[workspace]\n# hidden tampering\n")
        self.assertEqual(_git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertIn("S Cargo.toml", _git(self.repo, "ls-files", "-v"))
        result = self._run_exact_index_gate()
        self.assertEqual(result.returncode, 2, result.stderr)


    def _run_exact_ignored_source_gate(self) -> subprocess.CompletedProcess[str]:
        """Execute the production ignored-source guard against disposable Git."""
        script = Path(__file__).with_name("boat_setup.sh").read_text()
        match = re.search(r"(?ms)^reject_ignored_driver_sources\(\) \{\n.*?^\}\n", script)
        self.assertIsNotNone(match, "ignored source guard missing from Boat setup")
        self.assertIn('reject_ignored_driver_sources "$repo_root"', script)
        program = (
            "set -euo pipefail\n"
            'die() { echo "$*" >&2; exit 2; }\n'
            + match.group(0)
            + 'reject_ignored_driver_sources "$1"\n'
        )
        return subprocess.run(
            ["bash", "-c", program, "guard", str(self.repo)],
            capture_output=True, text=True, timeout=10, check=False,
        )

    def test_git_ignored_build_script_must_block_branch_build(self) -> None:
        # A Git local exclude can hide an untracked Cargo auto-build script
        # from status/ls-files -v without changing the reviewed HEAD.
        crate = self.repo / "libs/cua-driver/rust/crates/cua-driver"
        crate.mkdir(parents=True)
        (self.repo / ".git/info/exclude").write_text("build.rs\n")
        (crate / "build.rs").write_text('fn main() { println!("cargo:warning=unexpected"); }\n')
        self.assertEqual(_git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual(self._run_exact_index_gate().returncode, 0)
        result = self._run_exact_ignored_source_gate()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ignored untracked Driver files", result.stderr)

    def test_ignored_driver_env_must_block_branch_build(self) -> None:
        crate = self.repo / "libs/cua-driver/rust/crates/cua-driver"
        crate.mkdir(parents=True)
        (self.repo / ".git/info/exclude").write_text(".env\n")
        (crate / ".env").write_text("FIXTURE_ONLY=1\n")
        self.assertEqual(_git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        result = self._run_exact_ignored_source_gate()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ignored untracked Driver files", result.stderr)

    def test_ignored_rust_target_cache_stays_allowed(self) -> None:
        cache = self.repo / "libs/cua-driver/rust/target/release"
        cache.mkdir(parents=True)
        (cache / "cua-driver").write_bytes(b"ignored-cargo-cache")
        self.assertEqual(_git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")
        result = self._run_exact_ignored_source_gate()
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
