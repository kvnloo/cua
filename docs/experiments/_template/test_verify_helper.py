#!/usr/bin/env python3
"""UNIT controls for verify_helper.check_cited (standard library only; run under bin/hostless).

Each test builds a throwaway git repository under $TMPDIR with the repository rules that dropped
evidence from published packets (*.log, build/), then a packet that cites its files.

  positive control: a cited log that git ignores, a cited build/ output, and a cited file that was
                    never added are each reported (ignored / ignored / untracked);
  negative control: the same packet with the packet-local .gitignore from this template and every
                    cited file committed passes with no finding;
  scope:            with --readme files only the Files section is read (a README without one is
                    read whole), so a citation elsewhere is reported only with --readme all;
  template:         this directory (the template itself) passes.

usage: python3 test_verify_helper.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_helper import check_cited  # noqa: E402

README = """# Example packet

Results come from `raw/trials.jsonl` and `raw/run.log`.

## Files

| File | Contents |
|---|---|
| `raw/trials.jsonl`, `raw/run.log` | trial records and the session log |
| `raw/build/report.txt` | build output |
| `raw/extra.json` | extra records |
| `verify_artifacts.py` | verifier |
"""
OUTSIDE = "\n## Method\n\nSee also `raw/notes.log`.\n"


def sh(cwd: Path, *cmd: str) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


class CheckCited(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="verify-helper-")
        self.repo = Path(self.tmp.name)
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        os.environ.update(env)
        sh(self.repo, "git", "init", "-q")
        (self.repo / ".gitignore").write_text("*.log\nbuild/\n")
        self.pkt = self.repo / "docs" / "experiments" / "example"
        (self.pkt / "raw" / "build").mkdir(parents=True)
        for rel, text in {"raw/trials.jsonl": "{}\n", "raw/run.log": "log\n", "raw/build/report.txt": "ok\n",
                          "raw/extra.json": "{}\n", "verify_artifacts.py": "print('ok')\n",
                          "example-summary.json": json.dumps({"source": "raw/run.log"}) + "\n"}.items():
            (self.pkt / rel).write_text(text)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def commit(self, *paths: str) -> None:
        sh(self.repo, "git", "add", *paths)
        sh(self.repo, "git", "commit", "-q", "-m", "packet")

    def test_positive_control_ignored_and_untracked_cited_files_fail(self) -> None:
        (self.pkt / "README.md").write_text(README)
        # a plain `git add` of the packet: the repository rules silently drop the log and build/
        self.commit(".gitignore", "docs/experiments/example/README.md", "docs/experiments/example/raw/trials.jsonl",
                    "docs/experiments/example/verify_artifacts.py", "docs/experiments/example/example-summary.json")
        got = {(f["path"], f["kind"]) for f in check_cited(self.pkt)}
        self.assertEqual(got, {("raw/run.log", "ignored"), ("raw/build/report.txt", "ignored"),
                               ("raw/extra.json", "untracked")})
        sources = {f["source"] for f in check_cited(self.pkt) if f["path"] == "raw/run.log"}
        self.assertEqual(sources, {"README.md"})

    def test_headline_json_citation_is_checked(self) -> None:
        (self.pkt / "README.md").write_text("# Example\n\n## Files\n\n- `example-summary.json`\n")
        self.commit(".gitignore", "docs/experiments/example/README.md", "docs/experiments/example/example-summary.json")
        got = {(f["path"], f["kind"], f["source"]) for f in check_cited(self.pkt)}
        self.assertEqual(got, {("raw/run.log", "ignored", "example-summary.json")})

    def test_negative_control_template_gitignore_and_committed_files_pass(self) -> None:
        (self.pkt / "README.md").write_text(README)
        (self.pkt / ".gitignore").write_text((HERE / ".gitignore").read_text())
        self.commit(".gitignore", "docs/experiments/example")
        self.assertEqual(check_cited(self.pkt), [])

    def test_scope_files_section_only(self) -> None:
        (self.pkt / "README.md").write_text(README + OUTSIDE)
        (self.pkt / ".gitignore").write_text((HERE / ".gitignore").read_text())
        self.commit(".gitignore", "docs/experiments/example")
        self.assertEqual(check_cited(self.pkt), [])
        self.assertEqual([(f["path"], f["kind"]) for f in check_cited(self.pkt, "all")], [("raw/notes.log", "untracked")])

    def test_template_itself_passes(self) -> None:
        if subprocess.run(["git", "-C", str(HERE), "rev-parse"], capture_output=True).returncode:
            self.skipTest("not inside a git checkout")
        self.assertEqual(check_cited(HERE, "all"), [])


if __name__ == "__main__":
    unittest.main()
