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

UNIT controls for verify_helper.check_privacy (PUB-02), each in a throwaway repository with a names
file that holds only a non-private dummy name (built at run time, so this file does not contain it):
  planted name:     the dummy hex-encoded, base64-encoded and inside a raw/ gzip member: caught 3/3;
  encoded list:     two quoted base64 literals of name-like tokens fail with no names file entry;
  absolute path:    a planted home path is caught;
  user name:        the local user name in a raw/ gzip member is user-name-in-raw, elsewhere plain-name;
  clean:            the same packet without plants, and the template itself, pass.

usage: python3 test_verify_helper.py -v
"""

from __future__ import annotations

import base64
import getpass
import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_helper import check_cited, check_privacy  # noqa: E402

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


DUMMY = "zz-" + "planted-name"  # non-private control name; never a literal in this file


class CheckPrivacy(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="verify-privacy-")
        self.repo = Path(self.tmp.name) / "repo"
        self.pkt = self.repo / "docs" / "experiments" / "example"
        (self.pkt / "raw").mkdir(parents=True)
        for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                     "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}.items():
            os.environ[k] = v
        sh(self.repo, "git", "init", "-q")
        names = Path(self.tmp.name) / "names.txt"
        names.write_text(DUMMY + "\n")
        self.saved = os.environ.get("CUA_PRIVACY_NAMES_FILE")
        os.environ["CUA_PRIVACY_NAMES_FILE"] = str(names)
        (self.pkt / "README.md").write_text("# Example\n\nClean text, `raw/trials.jsonl`.\n")
        (self.pkt / "raw" / "trials.jsonl").write_text('{"trial": 1, "sha": "8f3a646b4c0d2e1f"}\n')

    def tearDown(self) -> None:
        if self.saved is None:
            os.environ.pop("CUA_PRIVACY_NAMES_FILE", None)
        else:
            os.environ["CUA_PRIVACY_NAMES_FILE"] = self.saved
        self.tmp.cleanup()

    def commit(self) -> None:
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-q", "-m", "packet")

    def kinds(self) -> set[tuple[str, str]]:
        return {(f["where"], f["kind"]) for f in check_privacy(self.pkt)}

    def test_clean_packet_passes(self) -> None:
        self.commit()
        self.assertEqual(check_privacy(self.pkt), [])

    def test_planted_name_hex_base64_gzip_caught(self) -> None:
        (self.pkt / "notes.txt").write_text(f"id {DUMMY.encode().hex()} end\n")
        (self.pkt / "cfg.json").write_text(json.dumps({"k": base64.b64encode(DUMMY.encode()).decode()}) + "\n")
        (self.pkt / "raw" / "log.txt.gz").write_bytes(gzip.compress(f"session {DUMMY} ok\n".encode()))
        self.commit()
        got = self.kinds()
        self.assertIn(("notes.txt", "encoded-name"), got)
        self.assertIn(("cfg.json", "encoded-name"), got)
        self.assertIn(("raw/log.txt.gz!gunzip", "plain-name"), got)
        self.assertEqual({w for w, _ in got}, {"notes.txt", "cfg.json", "raw/log.txt.gz!gunzip"})
        self.assertFalse(any(DUMMY in f["where"] + f["detail"] for f in check_privacy(self.pkt)))

    def test_encoded_name_list_fails_without_its_names(self) -> None:
        enc = [base64.b64encode(n.encode()).decode() for n in ("alpha-node-01", "beta-node-02")]
        (self.pkt / "check.py").write_text(f"_N = [{enc[0]!r}, {enc[1]!r}]\n")
        self.commit()
        self.assertEqual(self.kinds(), {("check.py", "encoded-list")})

    def test_absolute_path_plant_caught(self) -> None:
        plant = "/" + "home/example-user/work/run"  # built at run time so this file stays clean
        (self.pkt / "raw" / "run.txt").write_text(f"cwd={plant}\n")
        self.commit()
        self.assertEqual(self.kinds(), {("raw/run.txt", "abs-path")})

    def test_user_name_in_raw_member_and_outside_raw(self) -> None:
        try:
            user = getpass.getuser()
        except (KeyError, OSError):
            self.skipTest("no local user name")
        (self.pkt / "raw" / "xhost.txt.gz").write_bytes(gzip.compress(f"SI:localuser:{user}\n".encode()))
        (self.pkt / "about.txt").write_text(f"by {user}\n")
        self.commit()
        got = self.kinds()
        self.assertIn(("raw/xhost.txt.gz!gunzip", "user-name-in-raw"), got)
        self.assertIn(("about.txt", "plain-name"), got)

    def test_template_itself_passes_privacy(self) -> None:
        if subprocess.run(["git", "-C", str(HERE), "rev-parse"], capture_output=True).returncode:
            self.skipTest("not inside a git checkout")
        self.assertEqual(check_privacy(HERE), [])


if __name__ == "__main__":
    unittest.main()
