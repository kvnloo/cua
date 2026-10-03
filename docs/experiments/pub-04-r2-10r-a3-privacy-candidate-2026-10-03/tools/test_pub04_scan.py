#!/usr/bin/env python3
"""Unit tests for pub04_scan.py (standard library only; run under bin/hostless):

    TMPDIR=<lane temp> python3 -m unittest -v test_pub04_scan

Planted positive controls must hit their class; the public fork owner token must never count as a
private name. Every planted private value is built at run time (a dummy name from a temporary names
file, a temp-dir bus path assembled from parts, the verifying user's home), so this file commits none.
The fork owner token is public (it is the fork's GitHub account). The real-case check compares it with
the local user name read at run time and prints only whether that case was exercised.
"""
from __future__ import annotations

import base64
import getpass
import gzip
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

OWNER = "kvnloo"                 # public fork owner token (github.com/<owner>/cua), one token
DUMMY = "zq" + "plantee"         # planted private name (temporary names file only)
PREFIX = "qvx"                   # synthetic private name that prefixes a public handle
HANDLE = PREFIX + "loo"          # synthetic public handle
BUS = "/" + "tmp" + "/dbus-" + "PlantAbc123xyz"
SECRET = "gh" + "p_" + "A1b2C3d4" * 4


def enc_all(s: str) -> dict[str, str]:
    raw = s.encode()
    return {
        "plain": s, "upper": s.upper(), "hex": raw.hex(), "HEX": raw.hex().upper(),
        "b64": base64.b64encode(raw).decode(),
        "url-lower": "".join("%{:02x}".format(b) for b in raw),
        "url-upper": "".join("%{:02X}".format(b) for b in raw),
        "url-partial": "".join("%{:02x}".format(b) for b in raw[:3]) + s[3:],
        "hex-run": ("x/" + s + "/y").encode().hex(),
        "b64-run": base64.b64encode(("x/" + s + "/y").encode()).decode(),
        "email": f"7121943+{s}@users.noreply.github.com",
        "url-path": f"https://github.com/{s}/cua/pull/106",
    }


def tar_gz(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        names = Path(cls.tmp.name) / "names.txt"
        names.write_text(f"{DUMMY}\n{PREFIX}\n")
        cls._old = os.environ.get("CUA_PRIVACY_NAMES_FILE")
        os.environ["CUA_PRIVACY_NAMES_FILE"] = str(names)
        import pub04_scan
        cls.P = pub04_scan
        cls.sc = pub04_scan.Scanner(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._old is None:
            os.environ.pop("CUA_PRIVACY_NAMES_FILE", None)
        else:
            os.environ["CUA_PRIVACY_NAMES_FILE"] = cls._old
        cls.tmp.cleanup()

    def kinds_text(self, text: str, in_raw: bool = False) -> set[str]:
        return {f["kind"] for f in self.sc.scan_text("t", text, in_raw)}

    def kinds_blob(self, path: str, data: bytes) -> set[str]:
        return {f["kind"] for f in self.sc.scan_blob(path, data)}

    def private(self, kinds: set[str]) -> set[str]:
        return kinds & self.P.PRIVATE


class PlantedPositives(Base):
    def test_dummy_name_every_encoding_hits(self) -> None:
        want = {"plain": "plain-name", "upper": "plain-name", "hex": "encoded-name", "HEX": "encoded-name",
                "b64": "encoded-name", "url-lower": "url-encoded", "url-upper": "url-encoded",
                "url-partial": "url-encoded", "hex-run": "encoded-name", "b64-run": "encoded-name",
                "email": "plain-name", "url-path": "plain-name"}
        for case, text in enc_all(DUMMY).items():
            with self.subTest(case=case):
                self.assertIn(want[case], self.kinds_text(f"line: {text} end"))

    def test_dummy_name_in_raw_file_tar_and_gz_members_and_path_names(self) -> None:
        self.assertIn("plain-name", self.kinds_blob("raw/logs/a.log", f"user={DUMMY}\n".encode()))
        self.assertIn("plain-name", self.kinds_blob("raw/x.jsonl.gz", gzip.compress(f'{{"u": "{DUMMY}"}}\n'.encode())))
        tg = tar_gz({f"trials/{DUMMY}/t.json": b"{}", "trials/b.json": f"host {DUMMY}".encode()})
        found = self.sc.scan_blob("raw/t.tar.gz", tg)
        self.assertTrue(any(f["kind"] == "plain-name" and f["where"].endswith("#name") for f in found))
        self.assertTrue(any(f["kind"] == "plain-name" and f["where"].endswith("b.json") for f in found))
        self.assertIn("plain-name", self.kinds_blob(f"raw/{DUMMY}/a.txt", b"clean\n"))
        self.assertIn("encoded-name", self.kinds_blob(f"raw/{DUMMY.encode().hex()}.txt", b"clean\n"))
        self.assertIn("encoded-name", self.kinds_blob(f"raw/{base64.b64encode(DUMMY.encode()).decode()}.txt", b"x\n"))

    def test_tmp_dbus_plain_url_base64_gz(self) -> None:
        self.assertIn("tmp-dbus", self.kinds_text(f"dbus=unix:path={BUS},guid=00"))
        self.assertIn("tmp-dbus", self.kinds_text("unix%3Apath%3D" + BUS.replace("/", "%2F")))
        self.assertIn("tmp-dbus", self.kinds_text(base64.b64encode(f"path={BUS}".encode()).decode()))
        self.assertIn("tmp-dbus", self.kinds_blob("raw/s.log.gz", gzip.compress(f"[session] {BUS}\n".encode())))

    def test_local_root_abs_path_and_secret(self) -> None:
        self.assertIn("abs-path", self.kinds_text(f"cwd {Path.home()}/work/x"))
        self.assertIn("abs-path", self.kinds_text(f"cwd {self.tmp.name}/x"))
        self.assertIn("secret-like", self.kinds_text(f"token={SECRET}"))

    def test_clean_text_has_no_finding(self) -> None:
        self.assertEqual(self.kinds_text("plain words, placeholder <session-bus> and <user>"), set())


class OwnerTokenNegatives(Base):
    def test_owner_token_every_encoding_is_not_private(self) -> None:
        for case, text in enc_all(OWNER).items():
            with self.subTest(case=case):
                self.assertEqual(self.private(self.kinds_text(f"line: {text} end")), set())

    def test_synthetic_prefix_handle_every_encoding_is_not_private(self) -> None:
        for case, text in enc_all(HANDLE).items():
            with self.subTest(case=case):
                self.assertEqual(self.private(self.kinds_text(f"line: {text} end")), set())

    def test_owner_token_in_paths_members_and_raw(self) -> None:
        tg = tar_gz({f"{OWNER}/t.json": OWNER.encode(), "u.txt": "".join("%{:02x}".format(b) for b in OWNER.encode()).encode()})
        self.assertEqual(self.private(self.kinds_blob(f"raw/{OWNER}-t.tar.gz", tg)), set())
        self.assertEqual(self.private(self.kinds_blob("raw/o.log.gz", gzip.compress(OWNER.encode()))), set())
        self.assertEqual(self.private(self.kinds_blob(f"docs/{OWNER.encode().hex()}.md", b"x")), set())

    def test_real_case_reported(self) -> None:
        exercised = OWNER.lower().startswith(getpass.getuser().lower())
        print(f"\n[real case] local user name is a prefix of the fork owner token: {exercised}", file=sys.stderr)
        for case, text in enc_all(OWNER).items():
            with self.subTest(case=case):
                hits = [f for f in self.sc.scan_text("t", text) if f["kind"] in self.P.PRIVATE]
                self.assertFalse(any("(user)" in f["detail"] for f in hits))


class CommitWalk(Base):
    def test_per_commit_scan_message_paths_members(self) -> None:
        repo = Path(self.tmp.name) / "repo"
        env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="T",
                   GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

        def g(*a: str) -> str:
            return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True, env=env).stdout

        subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
        (repo / "README.md").write_text(f"github.com/{OWNER}/cua {OWNER.encode().hex()} "
                                        + "".join("%{:02x}".format(b) for b in OWNER.encode()) + "\n")
        g("add", "-A")
        g("commit", "-q", "-m", f"clean commit by {OWNER}")
        (repo / "raw").mkdir()
        (repo / "raw" / f"{DUMMY.encode().hex()}.bin").write_bytes(b"x")
        (repo / "raw" / "t.tar.gz").write_bytes(tar_gz({f"m/{DUMMY}.json": b"{}"}))
        g("add", "-A")
        g("commit", "-q", "-m", f"planted {DUMMY}")
        (repo / "raw" / "s.log.gz").write_bytes(gzip.compress(f"[session] {BUS}\n".encode()))
        g("add", "-A")
        g("commit", "-q", "-m", "bus")
        commits, found = self.P.scan_commits(str(repo), ["HEAD"], self.sc, {})
        self.assertEqual(len(commits), 3)
        per = {c: {f["kind"] for f in found if f["commit"] == c[:12]} for c in commits}
        where = {c: {f["where"] for f in found if f["commit"] == c[:12]} for c in commits}
        self.assertEqual(per[commits[0]] & self.P.PRIVATE, set())
        self.assertTrue({"plain-name", "encoded-name"} <= per[commits[1]])
        self.assertIn("<commit message>", where[commits[1]])
        self.assertTrue(any(w.endswith("#name") and "t.tar.gz!" in w for w in where[commits[1]]))
        self.assertEqual(per[commits[2]] & self.P.PRIVATE, {"tmp-dbus"})


if __name__ == "__main__":
    unittest.main()
