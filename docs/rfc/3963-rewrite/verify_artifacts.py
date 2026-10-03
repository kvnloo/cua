#!/usr/bin/env python3
"""Verify the trycua/cua issue 3963 rewrite draft (stdlib only).

Run from anywhere inside a clone, under the loop's hostless wrapper:

    python3 docs/rfc/3963-rewrite/verify_artifacts.py --all-commits
    python3 docs/rfc/3963-rewrite/verify_artifacts.py --state <loop STATE.json> --all-commits

Checks
  files       every companion file exists and parses
  sections    README.md carries the ten required sections; PENDING.md exists
  rows        dispositions.json: required ids, allowed values, no PENDING row, BLOCKED blocker
              class, README table agrees with the JSON
  numbers     rows.spec.json templates carry no bare number (every number is a pointer)
  shas        every row SHA, packet README, backticked SHA and provenance SHA resolves. A SHA
              missing from the clone is fetched read-only by the ref recorded for it (row
              branch, provenance sha_refs, census ref, upstream main); with --no-fetch, or when
              the ref is not published, it is reported NEED with the exact command, not FAIL
  origin      every row branch head on the fork equals its SHA (git ls-remote, read-only); a
              mismatch or a missing branch is flagged UNPUBLISHED (not a failure)
  state       every row matches STATE.json (needs --state); a mismatch with a recorded
              diff_reason is listed as DIFF, without one it FAILS; every STATE row is covered
  regen       generate.py run against --state reproduces every generated file byte for byte
  claims      generated claims: each number is on its recorded packet line / at its JSON path /
              in STATE, and in its row of the README table; curated claims: the needle is on
              its recorded line (next to its anchor), the text in its README section
  open        rows that name a wave-7 lane say 'OPEN: scheduled wave 7'; every README line
              that names a wave-7 lane is marked OPEN or scheduled; no claim cites one
  graph       dependency-graph.json and the README mermaid block agree; open-lane nodes match
              the OPEN rows
  pending     every moving row and every wave-7 lane is named in PENDING.md
  freshness   upstream head and commit count in provenance; README lists each Linux/core path
              with its status
  autolink    no upstream autolink forms and no at-mentions in any text file of the draft
  privacy     no private names (plain, hex or base64; names read from the file named by
              CUA_PRIVACY_NAMES_FILE or --names-file, never stored here), no absolute local
              paths, no secret-like tokens in any file of the directory (tracked or not); with
              --all-commits every commit of the branch since the base is scanned

Exit status is 1 if any check FAILs. NEED never fails the run; it names what to fetch.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DOC_REL = "docs/rfc/3963-rewrite"
BASE_SHA = "5de1a37997e6c423899dd0a56aaa63bcf5abee8f"

FILES = ["README.md", "PENDING.md", "REVIEW-CHECKLIST.md", "rows.spec.json", "generate.py", "dispositions.json",
         "claims.json", "dependency-graph.json", "provenance.json", "verify_artifacts.py"]
SECTIONS = ["## 1. North-star", "## 2. Invariants", "## 3. Existing owners", "## 4. Dispositions",
            "## 5. Remaining deltas", "## 6. Owner decisions", "## 7. Non-goals", "## 8. Gates",
            "## 9. Dependency graph", "## 10. Whole-task accounting summary"]
REQUIRED_IDS = (["R2-0%d" % i for i in range(1, 10)] + ["R2-10", "R2-07b", "R2-07c", "R2-07d", "R2-07e", "R2-07e-MODAL"]
                + ["B-0%d" % i for i in range(1, 9)] + ["N-01R", "N-02", "N-03", "N-04"]
                + ["FIX-01", "FIX-02", "FIX-02-F4", "FIX-03", "FIX-03-SIDE", "RECERT-FIX", "BUG-01",
                   "OWN-09", "OWN-09R", "OWN-16", "OWN-16W", "OWN-20", "OWN-20G", "OWN-20P", "OWN-20Q",
                   "OWN-20Q-DLG", "OWN-20Q-A2", "OWN-20Q-R3N", "OWN-36", "OWN-75", "OWN-75R", "OWN-78",
                   "OWN-78A", "OWN-78L", "OWN-105", "PKT-01", "PUB-02", "PUB-03", "DOC-3963", "DOC-10-74"])
WAVE6 = ["B-08", "R2-07e", "OWN-78L", "OWN-20Q", "FIX-03", "PUB-03"]
ALLOWED = {"KEEP", "REVISE", "KILL", "BLOCKED", "SUPERSEDED"}
BLOCKER_CLASS = re.compile(r"\b(hardware|owner decision|budget)\b", re.I)
TOKEN = re.compile(r"\b(KEEP_H1|KEEP|REVISE|KILL|BLOCKED|RECERTIFIED|ACCEPTED|PENDING|SUPERSEDED|CONFIRMED_BUG)\b")
ALIAS = {"KEEP_H1": "KEEP", "RECERTIFIED": "KEEP", "ACCEPTED": "KEEP"}
NOT_TABLED = {
    "N-01": "hard-stop record superseded by N-01R (no evidence)",
    "B-01R": "text-fix lane; its head is the accepted B-01 commit",
    "owner_rows_linux": "owner-row summary map (rows cite it via state_subkey)",
    "owner_rows_blocked_hardware": "blocked-row map (rows cite it via state_subkey)",
}
OPEN_PREFIX = "OPEN: scheduled wave 7"
FORK = "kvnloo/cua"
UP = "trycua" + "/cua"
FORK_URL = "https://github.com/" + FORK + ".git"
UP_URL = "https://github.com/" + UP + ".git"

results: list[tuple[str, str, str]] = []


def rec(status: str, check: str, detail: str) -> None:
    results.append((status, check, detail))


def git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def git_bytes(repo: Path, *args: str) -> bytes | None:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def load_json(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def clean(msg: str) -> str:
    """Keep local paths and upstream links out of the report (it is committed as a log)."""
    msg = msg.replace(UP_URL, "<upstream URL, the " + UP + " repository on GitHub>")
    return re.sub(r"(?<![\w.~-])/(?:home|mnt|Users|root|var|tmp)/\S*", "<local path>", msg)


# ---------------------------------------------------------------- refs and fetching
class Objects:
    """Resolves SHAs; fetches a missing one read-only by its recorded ref, or says what to fetch."""

    def __init__(self, repo: Path, allow_fetch: bool):
        self.repo = repo
        self.allow_fetch = allow_fetch
        self.refs: dict[str, dict] = {}       # full or short sha -> {"remote", "ref"}
        self.status: dict[str, tuple[str, str]] = {}
        self.fetched: list[str] = []
        self._ls: dict[str, dict[str, str] | None] = {}

    def full(self, sha: str) -> str | None:
        p = git(self.repo, "rev-parse", "--verify", "-q", sha + "^{commit}")
        return p.stdout.strip() if p.returncode == 0 else None

    def add_ref(self, sha: str | None, remote: str, ref: str) -> None:
        if sha and sha not in self.refs:
            self.refs[sha] = {"remote": remote, "ref": ref}

    def ref_of(self, sha: str) -> dict | None:
        if sha in self.refs:
            return self.refs[sha]
        for k, v in self.refs.items():
            if k.startswith(sha) or sha.startswith(k):
                return v
        return None

    def url(self, remote: str) -> str | None:
        want = {"fork": FORK, "upstream": UP}.get(remote)
        if not want:
            return None
        for name in ("origin", "upstream", "fork"):
            p = git(self.repo, "remote", "get-url", name)
            u = p.stdout.strip()
            if p.returncode == 0 and re.sub(r"\.git$", "", u.rstrip("/")).endswith(want):
                return u
        return FORK_URL if remote == "fork" else UP_URL

    def ls_remote(self, url: str, refs: list[str]) -> dict[str, str] | None:
        p = git(self.repo, "ls-remote", url, *refs)
        if p.returncode != 0:
            return None
        out = {}
        for line in p.stdout.splitlines():
            sha, ref = line.split("\t")
            out[ref] = sha
        return out

    def prefetch(self, shas: list[str]) -> None:
        """Fetch, in one command per remote, every published ref that holds a missing SHA."""
        missing = [s for s in dict.fromkeys(shas) if s and not self.full(s)]
        if not missing:
            return
        by_url: dict[str, set] = {}
        for s in missing:
            r = self.ref_of(s)
            if not r:
                continue
            u = self.url(r["remote"])
            if u:
                by_url.setdefault(u, set()).add(r["ref"])
        for u, refs in by_url.items():
            listed = self.ls_remote(u, sorted(refs))
            self._ls[u] = listed
            if not self.allow_fetch or listed is None:
                continue
            present = sorted(r for r in refs if r in listed)
            for i in range(0, len(present), 40):
                chunk = present[i:i + 40]
                p = git(self.repo, "fetch", "--no-tags", "--no-write-fetch-head", "-q", u, *chunk)
                if p.returncode == 0:
                    self.fetched += chunk

    def ensure(self, sha: str) -> tuple[str, str]:
        """Return (status, detail): OK, FETCHED, NEED or FAIL."""
        if sha in self.status:
            return self.status[sha]
        r = self.ref_of(sha)
        if self.full(sha):
            st = ("FETCHED", "fetched %s" % r["ref"]) if r and r["ref"] in self.fetched else ("OK", "")
        elif not r:
            st = ("FAIL", "%s does not resolve and no ref is recorded for it" % sha[:9])
        elif r["remote"] == "self":
            st = ("FAIL", "%s should be in this branch's history but does not resolve" % sha[:9])
        else:
            u = self.url(r["remote"])
            listed = self._ls.get(u)
            cmd = "git fetch --no-tags %s %s" % (u or (FORK_URL if r["remote"] == "fork" else UP_URL), r["ref"])
            if listed is not None and r["ref"] not in listed:
                st = ("NEED", "needs ref %s, which is not published on the %s (held or local only); "
                      "fetch it from the lane's local clone" % (r["ref"], r["remote"]))
            elif not self.allow_fetch or listed is None:
                st = ("NEED", "needs ref %s: run `%s` in this clone, or re-run without --no-fetch/--offline" % (r["ref"], cmd))
            else:
                st = ("FAIL", "ref %s was fetched but does not contain %s" % (r["ref"], sha[:9]))
        self.status[sha] = st
        return st


def register_refs(obj: Objects, rows: list[dict], prov: dict) -> None:
    for r in rows:
        if r.get("sha") and r.get("branch"):
            obj.add_ref(r["sha"], "fork", "refs/heads/" + r["branch"])
    for sha, info in prov.get("sha_refs", {}).items():
        obj.add_ref(sha, info["remote"], info["ref"])
    cen = prov["inputs"]["census_branch"]
    obj.add_ref(cen["sha"], "fork", "refs/heads/" + cen["ref"].split("origin/", 1)[-1])
    fr = prov.get("freshness_now", {})
    if fr.get("upstream_main"):
        obj.add_ref(fr["upstream_main"], "upstream", "refs/heads/main")
        for p in fr.get("linux_core_paths", []):
            obj.add_ref(p["merge"], "upstream", "refs/heads/main")
    obj.add_ref(prov.get("freshness", {}).get("tested_upstream"), "upstream", "refs/heads/main")
    obj.add_ref(prov["base"]["sha"], "self", "HEAD")
    par = prov.get("parent_revision", {})
    obj.add_ref(par.get("sha"), "self", "HEAD")


def report_obj(check: str, label: str, st: tuple[str, str]) -> bool:
    status, detail = st
    if status in ("OK", "FETCHED"):
        return True
    rec("NEED" if status == "NEED" else "FAIL", check, "%s: %s" % (label, detail))
    return False


# ---------------------------------------------------------------- files / sections
def check_files() -> bool:
    ok = True
    for f in FILES:
        if not (HERE / f).is_file():
            rec("FAIL", "files", "missing " + f)
            ok = False
    for f in FILES:
        if f.endswith(".json") and (HERE / f).is_file():
            try:
                load_json(f)
            except ValueError as e:
                rec("FAIL", "files", "%s does not parse: %s" % (f, e))
                ok = False
    if ok:
        rec("PASS", "files", "%d files present and parse" % len(FILES))
    return ok


def check_sections(readme: str) -> None:
    missing = [s for s in SECTIONS if s not in readme]
    if missing:
        rec("FAIL", "sections", "README missing: " + "; ".join(missing))
    else:
        rec("PASS", "sections", "README has all %d required sections (section 11 = PENDING.md)" % len(SECTIONS))
    pend = (HERE / "PENDING.md").read_text(encoding="utf-8")
    if "PENDING" not in pend.splitlines()[0]:
        rec("FAIL", "sections", "PENDING.md title line missing")


def section_text(readme: str, sec: str) -> str | None:
    """Text of the README section whose heading starts with `sec` (e.g. '## 1.')."""
    m = re.search(r"^%s[^\n]*\n" % re.escape(sec), readme, re.M)
    if not m:
        return None
    nxt = re.search(r"^## ", readme[m.end():], re.M)
    return readme[m.start(): m.end() + (nxt.start() if nxt else len(readme))]


# ---------------------------------------------------------------- rows
def table_rows(readme: str) -> dict[str, tuple[list[str], str]]:
    m = re.search(r"<!-- dispositions-table:start -->(.*?)<!-- dispositions-table:end -->", readme, re.S)
    out: dict[str, tuple[list[str], str]] = {}
    if not m:
        return out
    for line in m.group(1).strip().splitlines()[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0]:
            out[cells[0]] = (cells, line)
    return out


def check_rows(rows: list[dict], readme: str, wave7: list[str]) -> None:
    ids = [r["id"] for r in rows]
    bad = 0
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        rec("FAIL", "rows", "duplicate ids: " + ", ".join(dup))
        bad += 1
    missing = [i for i in REQUIRED_IDS if i not in ids]
    if missing:
        rec("FAIL", "rows", "required ids missing: " + ", ".join(missing))
        bad += 1
    for r in rows:
        for k in ("id", "disposition", "class", "branch", "sha", "packet", "owner", "blocker", "pending", "numbers"):
            if k not in r:
                rec("FAIL", "rows", "%s lacks field %s" % (r.get("id"), k))
                bad += 1
        d = r.get("disposition")
        if d == "PENDING":
            rec("FAIL", "rows", "%s is PENDING: wave-6 PENDING rows must be cleared" % r["id"])
            bad += 1
        elif d not in ALLOWED:
            rec("FAIL", "rows", "%s disposition %r not allowed" % (r["id"], d))
            bad += 1
        if d == "BLOCKED" and not (r.get("blocker") and BLOCKER_CLASS.search(r["blocker"])):
            rec("FAIL", "rows", "%s BLOCKED without a hardware / owner decision / budget blocker" % r["id"])
            bad += 1
        if d in ("KEEP", "REVISE", "KILL") and not (r.get("sha") and r.get("packet")):
            rec("FAIL", "rows", "%s %s without sha and packet" % (r["id"], d))
            bad += 1
        pend = r.get("pending") or ""
        named = [l for l in wave7 if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(l), pend)]
        if named and not pend.startswith(OPEN_PREFIX):
            rec("FAIL", "rows", "%s names wave-7 lane(s) %s without '%s'" % (r["id"], ", ".join(named), OPEN_PREFIX))
            bad += 1
    table = table_rows(readme)
    for r in rows:
        if r["id"] not in table:
            rec("FAIL", "rows", "%s missing from README table" % r["id"])
            bad += 1
            continue
        cells = table[r["id"]][0]
        if cells[1] != r["disposition"]:
            rec("FAIL", "rows", "%s README table says %s, JSON %s" % (r["id"], cells[1], r["disposition"]))
            bad += 1
        if r.get("sha") and ("`%s`" % r["sha"][:9]) not in cells[3]:
            rec("FAIL", "rows", "%s README table SHA cell does not cite %s" % (r["id"], r["sha"][:9]))
            bad += 1
        if (r.get("claim_boundary") or "").replace("|", "/") != cells[5]:
            rec("FAIL", "rows", "%s README claim cell differs from JSON" % r["id"])
            bad += 1
        if (r.get("pending") or "").replace("|", "/") != (cells[7] if len(cells) > 7 else ""):
            rec("FAIL", "rows", "%s README Pending cell differs from JSON" % r["id"])
            bad += 1
    extra = sorted(set(table) - set(ids))
    if extra:
        rec("FAIL", "rows", "README table rows not in JSON: " + ", ".join(extra))
        bad += 1
    if not bad:
        n = {d: sum(1 for r in rows if r["disposition"] == d) for d in sorted(ALLOWED)}
        rec("PASS", "rows", "%d rows, 0 PENDING, table agrees; %s" % (len(rows), ", ".join("%s %d" % kv for kv in n.items())))


# ---------------------------------------------------------------- numbers
PLACE = re.compile(r"\{[A-Za-z0-9_.]+\}")
EXEMPT = [
    re.compile(r"\b(?:PR|PRs|issue)\s+\d{3,5}\b"),                  # upstream item numbers (plain text)
    re.compile(re.escape(FORK) + r"#\d+"),                          # fork items
    re.compile(r"\b(?:Part|Phase|step|wave|wave-|section)\s?\d+\b", re.I),  # names of parts, phases, waves, sections
    re.compile(r"\b\d+\.\d+\.\d+\b"),                               # versions
    re.compile(r"[A-Za-z_'][\w'.-]*\d[\w'-]*|\d+[A-Za-z_][\w'-]*"),  # identifiers: R2-07e, GTK3, F'S, n7_presat, 2237cf9c6
]
BARE = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,/]\d+)*%?")


def check_numbers(spec: dict) -> None:
    bad = 0
    n = 0
    for r in spec["rows"]:
        for field in ("claim_boundary", "blocker", "pending"):
            t = r.get(field) or ""
            if not t:
                continue
            n += 1
            s = PLACE.sub(" ", t)
            for rx in EXEMPT:
                s = rx.sub(" ", s)
            hits = BARE.findall(s)
            if hits:
                rec("FAIL", "numbers", "%s.%s carries bare number(s) %s without a pointer" % (r["id"], field, hits))
                bad += 1
    if not bad:
        rec("PASS", "numbers", "%d row templates: every number is a pointer (packet line / packet JSON / STATE)" % n)


# ---------------------------------------------------------------- shas / origin
HEX = re.compile(r"`([0-9a-f]{7,40})`")


def check_shas(obj: Objects, rows: list[dict], md_texts: dict[str, str], prov: dict) -> None:
    want = [r["sha"] for r in rows if r.get("sha")]
    cited = sorted({m.group(1) for t in md_texts.values() for m in HEX.finditer(t)})
    extra = [prov["base"]["sha"], prov["inputs"]["census_branch"]["sha"], prov.get("parent_revision", {}).get("sha")]
    fr = prov.get("freshness_now", {})
    extra += [fr.get("upstream_main")] + [p["merge"] for p in fr.get("linux_core_paths", [])]
    obj.prefetch(want + cited + [x for x in extra if x])
    bad = need = n = 0
    for r in rows:
        if not r.get("sha"):
            continue
        n += 1
        if not report_obj("shas", "row %s sha %s" % (r["id"], r["sha"][:9]), obj.ensure(r["sha"])):
            need += obj.ensure(r["sha"])[0] == "NEED"
            bad += obj.ensure(r["sha"])[0] == "FAIL"
            continue
        if r.get("packet"):
            path = r["packet"].rstrip("/") + "/README.md"
            if git_bytes(obj.repo, "cat-file", "-e", "%s:%s" % (r["sha"], path)) is None:
                rec("FAIL", "shas", "%s packet README %s missing at %s" % (r["id"], path, r["sha"][:9]))
                bad += 1
    for s in cited:
        n += 1
        st = obj.ensure(s)
        if not report_obj("shas", "backticked SHA %s" % s, st):
            need += st[0] == "NEED"
            bad += st[0] == "FAIL"
    cen = prov["inputs"]["census_branch"]
    st = obj.ensure(cen["sha"])
    n += 1
    if st[0] == "OK":
        rec("PASS", "shas", "census SHA %s resolves in this clone" % cen["sha"][:9])
    elif st[0] == "FETCHED":
        rec("PASS", "shas", "census SHA %s fetched read-only from the fork ref %s" % (cen["sha"][:9], cen["ref"].split("origin/", 1)[-1]))
    else:
        report_obj("shas", "census SHA %s" % cen["sha"][:9], st)
        need += st[0] == "NEED"
        bad += st[0] == "FAIL"
    for s in [x for x in extra if x and x != cen["sha"]]:
        n += 1
        st = obj.ensure(s)
        if not report_obj("shas", "provenance SHA %s" % s[:9], st):
            need += st[0] == "NEED"
            bad += st[0] == "FAIL"
    if not bad:
        rec("PASS", "shas", "%d SHA references checked: %d resolve%s, %d NEED a ref" % (
            n, n - need, (" (%d refs fetched read-only)" % len(obj.fetched)) if obj.fetched else "", need))


def check_origin(obj: Objects, rows: list[dict], offline: bool) -> None:
    if offline:
        rec("SKIP", "origin", "--offline")
        return
    branches = sorted({r["branch"] for r in rows if r.get("branch") and r.get("sha")})
    url = obj.url("fork")
    heads = obj.ls_remote(url, ["refs/heads/" + b for b in branches])
    if heads is None:
        rec("FAIL", "origin", "git ls-remote on the fork failed")
        return
    ok = 0
    for r in rows:
        if not (r.get("branch") and r.get("sha")):
            continue
        h = heads.get("refs/heads/" + r["branch"])
        if h == r["sha"]:
            ok += 1
        else:
            rec("FLAG", "origin", "UNPUBLISHED %s: %s on the fork is %s, cited %s" % (
                r["id"], r["branch"], h[:9] if h else "absent", r["sha"][:9]))
    rec("PASS", "origin", "%d cited branch heads equal the fork" % ok)


# ---------------------------------------------------------------- state / regen
def state_text(state: dict, r: dict):
    key = r["state_key"]
    sub = r.get("state_subkey")
    node = state.get("dispositions", {}).get(key)
    if node is None and key in state:
        node = state[key]
    if node is None:
        return None
    if sub is not None:
        node = node.get(sub.replace(FORK + "#", "#")) if isinstance(node, dict) else None
        if node is None:
            return None
    if isinstance(node, dict):
        node = node.get(r.get("state_field", "disposition"))
    if isinstance(node, list):
        node = " | ".join(str(x) for x in node)
    return None if node is None else str(node)


def check_state(rows: list[dict], state_path: str | None) -> dict | None:
    if not state_path:
        rec("SKIP", "state", "no --state given; STATE comparison, regeneration and state claims skipped")
        return None
    raw = Path(state_path).read_bytes()
    state = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    prov = load_json("provenance.json")["inputs"]["loop_state"]["sha256"]
    if digest == prov:
        rec("PASS", "state", "STATE.json sha256 equals the one the rows were generated from (%s)" % digest[:12])
    else:
        rec("FLAG", "state", "STATE.json sha256 %s differs from generation-time %s (see regen)" % (digest[:12], prov[:12]))
    bad = diffs = 0
    for r in rows:
        if not r.get("state_key"):
            rec("FAIL", "state", "%s has no state_key" % r["id"])
            bad += 1
            continue
        text = state_text(state, r)
        if text is None:
            rec("FAIL", "state", "%s: STATE has no %s/%s" % (r["id"], r["state_key"], r.get("state_subkey", "")))
            bad += 1
            continue
        if r["state_expect"] not in text:
            rec("FAIL", "state", "%s: STATE text no longer contains %r" % (r["id"], r["state_expect"]))
            bad += 1
            continue
        if r["state_key"] == "owner_rows_blocked_hardware":
            norm = "BLOCKED"
        else:
            m = TOKEN.search(r["state_expect"])
            norm = ALIAS.get(m.group(1), m.group(1)) if m else None
        if norm != r["disposition"]:
            if r.get("diff_reason"):
                rec("DIFF", "state", "%s: STATE %s vs draft %s; reason: %s" % (r["id"], norm, r["disposition"], r["diff_reason"]))
                diffs += 1
            else:
                rec("FAIL", "state", "%s: STATE %s vs draft %s with no diff_reason" % (r["id"], norm, r["disposition"]))
                bad += 1
    covered = {r["state_key"] for r in rows}
    for key, val in state.get("dispositions", {}).items():
        if not isinstance(val, dict) or key in covered:
            continue
        if key in NOT_TABLED:
            rec("PASS", "state", "STATE row %s covered: %s" % (key, NOT_TABLED[key]))
        else:
            rec("FAIL", "state", "STATE row %s has no draft row" % key)
            bad += 1
    if not bad:
        rec("PASS", "state", "every row matches STATE.json (%d listed as DIFF with a reason)" % diffs)
    return state


def check_regen(repo: Path, state_path: str | None, need_objects: bool) -> None:
    if not state_path:
        rec("SKIP", "regen", "no --state given")
        return
    if need_objects:
        rec("NEED", "regen", "packet objects are missing from this clone (see shas NEED); fetch them to regenerate")
        return
    sys.path.insert(0, str(HERE))
    try:
        import generate  # noqa: E402  (the generator committed next to this file)
        new = generate.generate(repo, state_path)
        diffs = generate.compare(new)
    except Exception as e:  # GenError or a malformed input
        rec("FAIL", "regen", "generate.py failed: %s" % clean(str(e))[:400])
        return
    if diffs:
        for d in diffs:
            rec("FAIL", "regen", d + " (re-run generate.py --state)")
    else:
        rec("PASS", "regen", "generate.py --state reproduces dispositions.json, claims.json, README/PENDING blocks and sha_refs")


# ---------------------------------------------------------------- claims
def json_get(obj, path):
    for part in path:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def dotted(obj, path: str):
    return json_get(obj, path.split("."))


def fmt_value(v, fmt: str) -> str:
    if fmt in ("raw", "text"):
        return v if isinstance(v, str) else json.dumps(v)
    if fmt == "int":
        return "%d" % v
    m = re.fullmatch(r"(f|pct|ci|sci)(\d)", fmt)
    if not m:
        raise ValueError("unknown fmt " + fmt)
    d = int(m.group(2))
    if m.group(1) == "f":
        return "%.*f" % (d, v)
    if m.group(1) == "pct":
        return "%.*f%%" % (d, v * 100)
    if m.group(1) == "ci":
        return "[%.*f, %.*f]" % (d, v[0], d, v[1])
    return "[%+.*f, %+.*f]" % (d, v[0], d, v[1])


def gen_block(text: str, name: str) -> str | None:
    m = re.search(r"<!-- gen:%s -->(.*?)<!-- /gen:%s -->" % (name, name), text, re.S)
    return m.group(1) if m else None


def check_claims(obj: Objects, readme: str, state: dict | None) -> None:
    claims = load_json("claims.json")["claims"]
    table = table_rows(readme)
    cache: dict[tuple[str, str], str | None] = {}
    bad = skipped = need = 0

    def body(sha: str, path: str):
        st = obj.ensure(sha)
        if st[0] == "NEED":
            return "NEED"
        key = (sha, path)
        if key not in cache:
            b = git_bytes(obj.repo, "show", "%s:%s" % key)
            cache[key] = b.decode("utf-8", "replace") if b is not None else None
        return cache[key]

    for c in claims:
        cid, src = c["id"], c["source"]
        # README side
        if c.get("readme_row"):
            row = table.get(c["readme_row"])
            if not row or c["text"] not in row[1]:
                rec("FAIL", "claims", "%s text %r not in README table row %s" % (cid, c["text"], c["readme_row"]))
                bad += 1
        elif c.get("readme_block"):
            blk = gen_block(readme, c["readme_block"])
            if blk is None or c["text"] not in blk:
                rec("FAIL", "claims", "%s text %r not in README block %s" % (cid, c["text"], c["readme_block"]))
                bad += 1
        else:
            sec = section_text(readme, c.get("section", ""))
            ctx = c.get("readme_context", c["text"])
            if sec is None or ctx not in sec or c["text"] not in ctx:
                rec("FAIL", "claims", "%s text %r not in README %s%s" % (
                    cid, c["text"], c.get("section"), "" if ctx == c["text"] else " (context %r)" % ctx))
                bad += 1
        # source side
        kind = src["kind"]
        if kind in ("packet", "packet_line", "packet_json"):
            b = body(src["sha"], src["path"])
            if b == "NEED":
                need += 1
                continue
            if b is None:
                rec("FAIL", "claims", "%s source %s:%s unreadable" % (cid, src["sha"][:9], src["path"]))
                bad += 1
                continue
            if kind == "packet_json":
                try:
                    val = fmt_value(json_get(json.loads(b), src["json_path"]), src.get("fmt", "raw"))
                except (KeyError, IndexError, TypeError, ValueError) as e:
                    rec("FAIL", "claims", "%s JSON path %s unreadable in %s: %s" % (cid, src["json_path"], src["path"], e))
                    bad += 1
                    continue
                expect = c.get("needle", src.get("text", c["text"]))
                if val != expect or (c.get("generated") and val != c["text"]):
                    rec("FAIL", "claims", "%s %s at %s is %r, cited %r" % (cid, src["path"], ".".join(map(str, src["json_path"])), val, expect))
                    bad += 1
                continue
            lines = b.splitlines()
            ln = src.get("line")
            needle = src.get("context") if kind == "packet_line" else str(c["needle"])
            line = lines[ln - 1] if ln and 0 < ln <= len(lines) else None
            if line is None:
                rec("FAIL", "claims", "%s has no valid line pointer into %s" % (cid, src["path"]))
                bad += 1
            elif needle not in line or (c.get("anchor") and c["anchor"] not in line):
                rec("FAIL", "claims", "%s needle %r not on line %d of %s at %s" % (cid, needle, ln, src["path"], src["sha"][:9]))
                bad += 1
            elif kind == "packet_line" and src["text"] not in needle:
                rec("FAIL", "claims", "%s text %r not inside its context" % (cid, src["text"]))
                bad += 1
        elif kind in ("state", "state_text"):
            if state is None:
                skipped += 1
                continue
            try:
                val = dotted(state, src["json_path"])
            except (KeyError, IndexError, TypeError, ValueError):
                val = None
            if kind == "state":
                if val is None or fmt_value(val, src.get("fmt", "raw")) != c["text"]:
                    rec("FAIL", "claims", "%s STATE %s = %r, cited %r" % (cid, src["json_path"], val, c["text"]))
                    bad += 1
            else:
                val = " | ".join(map(str, val)) if isinstance(val, list) else str(val)
                if src["context"] not in val or c["text"] not in src["context"]:
                    rec("FAIL", "claims", "%s STATE %s no longer contains %r" % (cid, src["json_path"], src["context"]))
                    bad += 1
        else:
            rec("FAIL", "claims", "%s unknown source kind %s" % (cid, kind))
            bad += 1
    if need:
        rec("NEED", "claims", "%d claims need packet objects that are not in this clone (see shas)" % need)
    if not bad:
        gen = sum(1 for c in claims if c.get("generated"))
        rec("PASS", "claims", "%d claims (%d generated, %d curated) traced to their pointer%s%s" % (
            len(claims), gen, len(claims) - gen, " (%d state claims skipped)" % skipped if skipped else "",
            " (%d NEED)" % need if need else ""))


# ---------------------------------------------------------------- open / graph / pending / freshness
def check_open(rows: list[dict], readme: str, claims: list[dict], wave7: list[str]) -> None:
    bad = 0
    rx = {l: re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(l)) for l in wave7}
    for i, line in enumerate(readme.splitlines(), 1):
        for lane, r in rx.items():
            if r.search(line) and not re.search(r"OPEN|scheduled|in flight|disposition pending", line):
                rec("FAIL", "open", "README line %d names wave-7 lane %s without marking it OPEN/scheduled" % (i, lane))
                bad += 1
    for r in rows:
        for lane, x in rx.items():
            if x.search(r.get("claim_boundary") or "") or x.search(r.get("class") or ""):
                rec("FAIL", "open", "%s claim/class cites wave-7 lane %s" % (r["id"], lane))
                bad += 1
    for c in claims:
        if any(x.search(c.get("row", "")) for x in rx.values()):
            rec("FAIL", "open", "claim %s belongs to wave-7 lane %s" % (c["id"], c["row"]))
            bad += 1
    marked = {l: sorted(r["id"] for r in rows if (r.get("pending") or "").startswith(OPEN_PREFIX) and rx[l].search(r["pending"]))
              for l in wave7}
    for l, ids in marked.items():
        if not ids:
            rec("FAIL", "open", "wave-7 lane %s marks no row" % l)
            bad += 1
    if not bad:
        rec("PASS", "open", "%d OPEN rows across %d wave-7 lanes; no claim cites a wave-7 result" % (
            len({i for ids in marked.values() for i in ids}), len(wave7)))
    return marked


EDGE = re.compile(r"^\s*([A-Za-z0-9]+)\s*-->\s*([A-Za-z0-9]+)\s*$")
NODE = re.compile(r"^\s*([A-Za-z0-9]+)\[")


def check_graph(readme: str, rows: list[dict], wave7: list[str], marked: dict) -> None:
    g = load_json("dependency-graph.json")
    ids = {n["id"] for n in g["nodes"]}
    row_ids = {r["id"] for r in rows}
    bad = 0
    m = re.search(r"```mermaid\n(.*?)```", readme, re.S)
    if not m:
        rec("FAIL", "graph", "README has no mermaid block")
        return
    medges, mnodes = set(), set()
    for line in m.group(1).splitlines():
        e = EDGE.match(line)
        if e:
            medges.add((e.group(1), e.group(2)))
        n = NODE.match(line)
        if n:
            mnodes.add(n.group(1))
    jedges = {(e["from"], e["to"]) for e in g["edges"]}
    if medges != jedges:
        rec("FAIL", "graph", "mermaid edges differ from JSON: only mermaid %s; only JSON %s" % (
            sorted(medges - jedges), sorted(jedges - medges)))
        bad += 1
    if mnodes != ids:
        rec("FAIL", "graph", "mermaid nodes differ from JSON: %s / %s" % (sorted(mnodes - ids), sorted(ids - mnodes)))
        bad += 1
    for a, b in jedges:
        if a not in ids or b not in ids:
            rec("FAIL", "graph", "edge %s->%s has an unknown endpoint" % (a, b))
            bad += 1
    for n in g["nodes"]:
        if n["kind"] == "delta":
            if not any(e["from"] == n["id"] and e["type"] == "owned_by" for e in g["edges"]):
                rec("FAIL", "graph", "%s has no owner edge" % n["id"])
                bad += 1
            for ev in n.get("evidence", []):
                if ev not in row_ids:
                    rec("FAIL", "graph", "%s evidence %s is not a dispositions row" % (n["id"], ev))
                    bad += 1
            if ("**%s " % n["id"]) not in readme:
                rec("FAIL", "graph", "%s not described in README section 5" % n["id"])
                bad += 1
        for rr in n.get("rows", []):
            if rr not in row_ids:
                rec("FAIL", "graph", "%s row %s is not a dispositions row" % (n["id"], rr))
                bad += 1
        if n["kind"] == "open_lane":
            want = sorted({i for l in n["lanes"] for i in marked.get(l, [])})
            if any(l not in wave7 for l in n["lanes"]):
                rec("FAIL", "graph", "%s names a lane that is not a wave-7 lane" % n["id"])
                bad += 1
            if sorted(n["rows"]) != want:
                rec("FAIL", "graph", "%s rows %s differ from the rows marked OPEN for %s: %s" % (
                    n["id"], sorted(n["rows"]), "/".join(n["lanes"]), want))
                bad += 1
    if not bad:
        rec("PASS", "graph", "%d nodes, %d edges; mermaid and JSON agree; open-lane nodes match the OPEN rows" % (len(ids), len(jedges)))


def check_pending(rows: list[dict], wave7: list[str]) -> None:
    text = (HERE / "PENDING.md").read_text(encoding="utf-8")
    bad = 0
    for r in rows:
        if r.get("pending") and not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(r["id"]), text):
            rec("FAIL", "pending", "%s can move but is not named in PENDING.md" % r["id"])
            bad += 1
    for lane in wave7:
        if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(lane), text):
            rec("FAIL", "pending", "PENDING.md does not name wave-7 lane %s" % lane)
            bad += 1
    for lane in WAVE6:
        for line in text.splitlines():
            if line.startswith("|") and re.match(r"\|\s*%s\s*\|" % re.escape(lane), line) and "PENDING" in line:
                rec("FAIL", "pending", "PENDING.md still lists wave-6 lane %s as pending" % lane)
                bad += 1
    if "Owner rulings" not in text:
        rec("FAIL", "pending", "PENDING.md has no owner-ruling list")
        bad += 1
    if not bad:
        rec("PASS", "pending", "%d moving rows and %d wave-7 lanes named in PENDING.md" % (
            sum(1 for r in rows if r.get("pending")), len(wave7)))


def check_freshness(obj: Objects, readme: str, prov: dict) -> None:
    fr = prov.get("freshness_now")
    if not fr:
        rec("FAIL", "freshness", "provenance.json has no freshness_now")
        return
    bad = 0
    sec = section_text(readme, "## 8.") or ""
    for p in fr["linux_core_paths"]:
        line = next((l for l in sec.splitlines() if ("%s PR %d" % (UP, p["pr"])) in l), None)
        if not line or p["status"] not in line or p["path"] not in line:
            rec("FAIL", "freshness", "README section 8 lacks the line for %s PR %d with %r" % (UP, p["pr"], p["status"]))
            bad += 1
    if ("`%s`" % fr["upstream_main"][:9]) not in readme:
        rec("FAIL", "freshness", "README does not cite upstream main %s" % fr["upstream_main"][:9])
        bad += 1
    tested = prov["freshness"]["tested_upstream"]
    st1, st2 = obj.ensure(fr["upstream_main"]), obj.ensure(tested)
    if st1[0] in ("OK", "FETCHED") and st2[0] in ("OK", "FETCHED"):
        cnt = git(obj.repo, "rev-list", "--count", "%s..%s" % (tested, fr["upstream_main"])).stdout.strip()
        if cnt != str(fr["commits_past_tested"]):
            rec("FAIL", "freshness", "rev-list %s..%s counts %s, provenance says %s" % (tested[:9], fr["upstream_main"][:9], cnt, fr["commits_past_tested"]))
            bad += 1
        files = set(git(obj.repo, "diff", "--name-only", "%s..%s" % (prov["base"]["sha"], fr["upstream_main"]), "--", "libs/cua-driver").stdout.split())
        core = {f for f in files if re.search(r"/(platform-linux|cua-driver-core|cua-driver-sdk)/", f)}
        if core != {p["path"] for p in fr["linux_core_paths"]}:
            rec("FAIL", "freshness", "Linux/core paths changed since the base: %s; provenance lists %s" % (
                sorted(core), sorted(p["path"] for p in fr["linux_core_paths"])))
            bad += 1
    else:
        rec("NEED", "freshness", "upstream objects missing: %s" % (st1[1] or st2[1]))
        return
    if not bad:
        rec("PASS", "freshness", "upstream main %s is %s commits past %s; the %d Linux/core paths since the base are listed with their status" % (
            fr["upstream_main"][:9], fr["commits_past_tested"], tested[:9], len(fr["linux_core_paths"])))


# ---------------------------------------------------------------- autolink / privacy
AUTOLINK = [
    ("owner/repo hash-number", re.compile(re.escape(UP) + r"#\d")),
    ("owner/repo at-ref", re.compile(re.escape(UP) + "@")),
    ("upstream URL", re.compile(r"github\.com/" + "trycua", re.I)),
    ("bare hash-number", re.compile(r"(?<!" + re.escape(FORK) + r")(?<![&\w])#\d")),
    ("at-mention", re.compile(r"(?<![\w.@/+-])@[A-Za-z][A-Za-z0-9-]{0,38}\b")),
]
GENERIC = [
    ("absolute local path", re.compile(r"(?<![\w.~-])/(?:home|mnt|Users|root|var/folders|tmp)/")),
    ("secret-like token", re.compile(r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")),
]


def autolink_hits(name: str, text: str) -> list[str]:
    hits = []
    for label, rx in AUTOLINK:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append("%s:%d %s" % (name, line, label))  # the matched text is not echoed into logs
    return hits


def dir_files() -> dict[str, bytes]:
    out = {}
    for p in sorted(HERE.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[str(p.relative_to(HERE))] = p.read_bytes()
    return out


def check_autolink(files: dict[str, bytes]) -> None:
    hits = []
    n = 0
    for name, data in files.items():
        if name.startswith("raw" + os.sep):
            continue  # verifier logs (not rendered as markdown); the privacy scan still covers them
        n += 1
        hits += autolink_hits(name, data.decode("utf-8", "replace"))
    if hits:
        for h in hits[:40]:
            rec("FAIL", "autolink", h)
    else:
        rec("PASS", "autolink", "no upstream autolink form or at-mention in %d files" % n)


def name_patterns(name: str) -> list[tuple[str, "re.Pattern[bytes]"]]:
    raw = name.encode("utf-8")
    pats = [("plain", re.compile(rb"(?<![A-Za-z0-9])" + re.escape(raw) + rb"(?![A-Za-z0-9])", re.I)),
            ("hex", re.compile(re.escape(binascii.hexlify(raw)), re.I))]
    for pad in range(3):
        b = base64.b64encode(b"\0" * pad + raw + b"\0\0")
        lead = 4 if pad else 0
        usable = (len(b"\0" * pad + raw) // 3) * 4
        core = b[lead:usable]
        if len(core) >= 8:
            pats.append(("base64", re.compile(re.escape(core))))
    return pats


def load_names(path: str | None) -> list[str] | None:
    path = path or os.environ.get("CUA_PRIVACY_NAMES_FILE")
    if not path or not Path(path).is_file():
        return None
    names = [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines()]
    return [n for n in names if n and not n.startswith("#")]


def privacy_hits(label: str, data: bytes, names: list[str] | None) -> list[str]:
    hits = []
    text = data.decode("utf-8", "replace")
    for kind, rx in GENERIC:
        for m in rx.finditer(text):
            hits.append("%s: %s at offset %d" % (label, kind, m.start()))
    if names:
        for i, n in enumerate(names):
            for kind, rx in name_patterns(n):
                if rx.search(data):
                    hits.append("%s: private-name entry %d present (%s form)" % (label, i + 1, kind))
                    break
    return hits


def check_privacy(repo: Path, files: dict[str, bytes], names: list[str] | None, all_commits: bool, base: str) -> None:
    if names is None:
        rec("SKIP", "privacy", "no names file (CUA_PRIVACY_NAMES_FILE); only generic path/secret patterns run")
    hits = []
    for name, data in files.items():
        hits += privacy_hits(name, data, names)
    if hits:
        for h in hits[:40]:
            rec("FAIL", "privacy", h)
    else:
        rec("PASS", "privacy", "0 findings over %d files in the directory (tracked or not)%s" % (
            len(files), "" if names else " (generic patterns only)"))
    if not all_commits:
        return
    chits = []
    scanned = 0
    commits = git(repo, "rev-list", "%s..HEAD" % base).stdout.split()
    for c in commits:
        msg = git_bytes(repo, "log", "-1", "--format=%an <%ae>%n%cn <%ce>%n%B", c) or b""
        chits += privacy_hits("commit %s message" % c[:9], msg, names)
        chits += autolink_hits("commit %s message" % c[:9], msg.decode("utf-8", "replace"))
        for f in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", c).stdout.split():
            blob = git_bytes(repo, "show", "%s:%s" % (c, f))
            if blob is None:
                continue
            scanned += 1
            chits += privacy_hits("commit %s %s" % (c[:9], f), blob, names)
            if f.endswith((".md", ".json", ".py")):
                chits += autolink_hits("commit %s %s" % (c[:9], f), blob.decode("utf-8", "replace"))
    if chits:
        for h in chits[:40]:
            rec("FAIL", "privacy-commits", h)
    else:
        rec("PASS", "privacy-commits", "0 findings in %d commits since %s (%d blobs and every message)" % (
            len(commits), base[:9], scanned))


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", help="repository to resolve SHAs in (default: the one holding this file)")
    ap.add_argument("--state", help="loop STATE.json to compare dispositions with and regenerate from")
    ap.add_argument("--names-file", help="private-name list (default: $CUA_PRIVACY_NAMES_FILE)")
    ap.add_argument("--offline", action="store_true", help="no git ls-remote and no fetch")
    ap.add_argument("--no-fetch", action="store_true", help="never fetch a missing SHA; report NEED instead")
    ap.add_argument("--all-commits", action="store_true", help="privacy/autolink scan every commit since the base")
    ap.add_argument("--base", default=BASE_SHA)
    a = ap.parse_args()
    repo = Path(a.repo) if a.repo else Path(git(HERE, "rev-parse", "--show-toplevel").stdout.strip())
    if not check_files():
        return report()
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    files = dir_files()
    md = {f: (HERE / f).read_text(encoding="utf-8") for f in FILES if f.endswith(".md")}
    rows = load_json("dispositions.json")["rows"]
    spec = load_json("rows.spec.json")
    prov = load_json("provenance.json")
    claims = load_json("claims.json")["claims"]
    wave7 = list(spec["wave7_lanes"])
    obj = Objects(repo, allow_fetch=not (a.offline or a.no_fetch))
    if a.offline:
        obj.url = lambda remote: None  # type: ignore[assignment]
    register_refs(obj, rows, prov)
    check_sections(readme)
    check_rows(rows, readme, wave7)
    check_numbers(spec)
    check_shas(obj, rows, md, prov)
    check_origin(obj, rows, a.offline)
    state = check_state(rows, a.state)
    need_objects = any(s == "NEED" for s, c, _ in results if c == "shas")
    check_regen(repo, a.state, need_objects)
    check_claims(obj, readme, state)
    marked = check_open(rows, readme, claims, wave7)
    check_graph(readme, rows, wave7, marked)
    check_pending(rows, wave7)
    check_freshness(obj, readme, prov)
    check_autolink(files)
    check_privacy(repo, files, load_names(a.names_file), a.all_commits, a.base)
    return report()


def report() -> int:
    order = {"FAIL": 0, "NEED": 1, "DIFF": 2, "FLAG": 3, "SKIP": 4, "PASS": 5}
    for status, check, detail in sorted(results, key=lambda r: (order[r[0]], r[1])):
        print("%-4s %-15s %s" % (status, check, clean(detail)))
    n = {k: sum(1 for r in results if r[0] == k) for k in order}
    print("SUMMARY " + " ".join("%s=%d" % kv for kv in n.items()))
    return 1 if n["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
