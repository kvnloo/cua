#!/usr/bin/env python3
"""Verify the trycua/cua issue 3963 rewrite draft (stdlib only).

Run from anywhere inside the repository, under the loop's hostless wrapper:

    python3 docs/rfc/3963-rewrite/verify_artifacts.py --state <loop STATE.json> --all-commits

Checks
  files       every companion file exists and parses
  sections    README.md carries the ten required sections; PENDING.md exists
  rows        dispositions.json: required ids, allowed values, BLOCKED blocker class,
              PENDING rows cite no evidence, README table agrees with the JSON
  shas        every row SHA, packet README and backticked SHA in the markdown resolves
  origin      every row branch head on origin equals its SHA (git ls-remote, read-only);
              a mismatch or a missing branch is flagged UNPUBLISHED (not a failure)
  state       every row matches STATE.json (needs --state); a mismatch with a recorded
              diff_reason is listed as DIFF, without one it FAILS; every STATE row is covered
  claims      every claims.json needle is in its packet file at its SHA (or equals the
              STATE value), and every claim text is in README.md
  graph       dependency-graph.json and the README mermaid block agree
  pending     every row with a non-empty 'pending' field is named in PENDING.md
  autolink    no upstream autolink forms and no at-mentions in any file of the draft
  privacy     no private names (plain, hex or base64; names read from the file named by
              CUA_PRIVACY_NAMES_FILE or --names-file, never stored here), no absolute local
              paths, no secret-like tokens; with --all-commits every commit of the branch
              since the base is scanned (file blobs and commit messages)

Exit status is 1 if any check FAILs.
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

HERE = Path(__file__).resolve().parent
DOC_REL = "docs/rfc/3963-rewrite"
BASE_SHA = "5de1a37997e6c423899dd0a56aaa63bcf5abee8f"

FILES = ["README.md", "PENDING.md", "REVIEW-CHECKLIST.md", "dispositions.json", "claims.json",
         "dependency-graph.json", "provenance.json", "verify_artifacts.py"]
SECTIONS = ["## 1. North-star", "## 2. Invariants", "## 3. Existing owners", "## 4. Dispositions",
            "## 5. Remaining deltas", "## 6. Owner decisions", "## 7. Non-goals", "## 8. Gates",
            "## 9. Dependency graph", "## 10. Whole-task accounting summary"]
REQUIRED_IDS = (["R2-0%d" % i for i in range(1, 10)] + ["R2-10", "R2-07b", "R2-07c", "R2-07d", "R2-07e"]
                + ["B-0%d" % i for i in range(1, 9)] + ["N-01R", "N-02", "N-03", "N-04"]
                + ["FIX-01", "FIX-02", "RECERT-FIX", "BUG-01", "OWN-09", "OWN-09R", "OWN-16", "OWN-16W",
                   "OWN-20", "OWN-20G", "OWN-20P", "OWN-20Q", "OWN-36", "OWN-75", "OWN-75R", "OWN-78",
                   "OWN-78A", "OWN-78L", "OWN-105"])
REQUIRED_PENDING = ["B-08", "R2-07e", "OWN-78L", "OWN-20Q", "FIX-03", "PUB-03"]
ALLOWED = {"KEEP", "REVISE", "KILL", "BLOCKED", "PENDING", "SUPERSEDED"}
BLOCKER_CLASS = re.compile(r"\b(hardware|owner decision|budget)\b", re.I)
TOKEN = re.compile(r"\b(KEEP_H1|KEEP|REVISE|KILL|BLOCKED|RECERTIFIED|ACCEPTED|PENDING|SUPERSEDED|CONFIRMED_BUG)\b")
ALIAS = {"KEEP_H1": "KEEP", "RECERTIFIED": "KEEP", "ACCEPTED": "KEEP"}
# STATE disposition keys that are not separate rows, with the reason.
NOT_TABLED = {
    "N-01": "hard-stop record superseded by N-01R (no evidence)",
    "B-01R": "text-fix lane; its head is the accepted B-01 commit",
    "owner_rows_linux": "owner-row summary map (rows cite it via state_subkey)",
    "owner_rows_blocked_hardware": "blocked-row map (rows cite it via state_subkey)",
}
FORK = "kvnloo/cua"
UP = "trycua" + "/cua"

results: list[tuple[str, str, str]] = []


def rec(status: str, check: str, detail: str) -> None:
    results.append((status, check, detail))


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def git_bytes(repo: Path, *args: str) -> bytes | None:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def resolves(repo: Path, sha: str) -> str | None:
    p = git(repo, "rev-parse", "--verify", "-q", sha + "^{commit}", check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def load_json(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


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


# ---------------------------------------------------------------- rows
def table_rows(readme: str) -> dict[str, list[str]]:
    m = re.search(r"<!-- dispositions-table:start -->(.*?)<!-- dispositions-table:end -->", readme, re.S)
    out: dict[str, list[str]] = {}
    if not m:
        return out
    for line in m.group(1).strip().splitlines()[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0]:
            out[cells[0]] = cells
    return out


def check_rows(rows: list[dict], readme: str) -> None:
    ids = [r["id"] for r in rows]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        rec("FAIL", "rows", "duplicate ids: " + ", ".join(dup))
    missing = [i for i in REQUIRED_IDS + REQUIRED_PENDING if i not in ids]
    if missing:
        rec("FAIL", "rows", "required ids missing: " + ", ".join(missing))
    bad = 0
    for r in rows:
        for k in ("id", "disposition", "class", "branch", "sha", "packet", "owner", "blocker", "pending"):
            if k not in r:
                rec("FAIL", "rows", "%s lacks field %s" % (r.get("id"), k))
                bad += 1
        d = r.get("disposition")
        if d not in ALLOWED:
            rec("FAIL", "rows", "%s disposition %r not allowed" % (r["id"], d))
            bad += 1
        if d == "BLOCKED" and not (r.get("blocker") and BLOCKER_CLASS.search(r["blocker"])):
            rec("FAIL", "rows", "%s BLOCKED without a hardware / owner decision / budget blocker" % r["id"])
            bad += 1
        if d == "PENDING" and (r.get("sha") or r.get("packet") or not r.get("pending")):
            rec("FAIL", "rows", "%s PENDING must cite no sha/packet and must say what is pending" % r["id"])
            bad += 1
        if d in ("KEEP", "REVISE", "KILL") and not (r.get("sha") and r.get("packet")):
            rec("FAIL", "rows", "%s %s without sha and packet" % (r["id"], d))
            bad += 1
    table = table_rows(readme)
    for r in rows:
        cells = table.get(r["id"])
        if not cells:
            rec("FAIL", "rows", "%s missing from README table" % r["id"])
            bad += 1
            continue
        if cells[1] != r["disposition"]:
            rec("FAIL", "rows", "%s README table says %s, JSON %s" % (r["id"], cells[1], r["disposition"]))
            bad += 1
        if r.get("sha") and ("`%s`" % r["sha"][:9]) not in cells[3]:
            rec("FAIL", "rows", "%s README table SHA cell %r does not cite %s" % (r["id"], cells[3], r["sha"][:9]))
            bad += 1
        if (r.get("pending") or "") != (cells[7] if len(cells) > 7 else ""):
            rec("FAIL", "rows", "%s README Pending cell differs from JSON" % r["id"])
            bad += 1
    extra = sorted(set(table) - set(ids))
    if extra:
        rec("FAIL", "rows", "README table rows not in JSON: " + ", ".join(extra))
        bad += 1
    if not bad:
        n = {d: sum(1 for r in rows if r["disposition"] == d) for d in sorted(ALLOWED)}
        rec("PASS", "rows", "%d rows, table agrees; %s" % (len(rows), ", ".join("%s %d" % kv for kv in n.items())))


# ---------------------------------------------------------------- shas / origin
HEX = re.compile(r"`([0-9a-f]{7,40})`")


def check_shas(repo: Path, rows: list[dict], md_texts: dict[str, str]) -> None:
    bad = 0
    n = 0
    for r in rows:
        if not r.get("sha"):
            continue
        n += 1
        if not resolves(repo, r["sha"]):
            rec("FAIL", "shas", "%s sha %s does not resolve" % (r["id"], r["sha"]))
            bad += 1
            continue
        if r.get("packet"):
            path = r["packet"].rstrip("/") + "/README.md"
            if git_bytes(repo, "cat-file", "-e", "%s:%s" % (r["sha"], path)) is None:
                rec("FAIL", "shas", "%s packet README %s missing at %s" % (r["id"], path, r["sha"][:9]))
                bad += 1
    cited = set()
    for name, text in md_texts.items():
        for m in HEX.finditer(text):
            cited.add(m.group(1))
    for s in sorted(cited):
        n += 1
        if not resolves(repo, s):
            rec("FAIL", "shas", "backticked SHA %s does not resolve" % s)
            bad += 1
    prov = load_json("provenance.json")
    for s in (prov["base"]["sha"], prov["inputs"]["census_branch"]["sha"]):
        n += 1
        if not resolves(repo, s):
            rec("FAIL", "shas", "provenance SHA %s does not resolve" % s)
            bad += 1
    if not bad:
        rec("PASS", "shas", "%d SHA references resolve (rows, packet READMEs, backticked SHAs, provenance)" % n)


def check_origin(repo: Path, rows: list[dict], offline: bool) -> None:
    if offline:
        rec("SKIP", "origin", "--offline")
        return
    branches = sorted({r["branch"] for r in rows if r.get("branch") and r.get("sha")})
    p = git(repo, "ls-remote", "origin", *["refs/heads/" + b for b in branches], check=False)
    if p.returncode != 0:
        rec("FAIL", "origin", "git ls-remote failed: " + p.stderr.strip()[:200])
        return
    heads = {}
    for line in p.stdout.splitlines():
        sha, ref = line.split("\t")
        heads[ref[len("refs/heads/"):]] = sha
    ok = 0
    for r in rows:
        if not (r.get("branch") and r.get("sha")):
            continue
        h = heads.get(r["branch"])
        if h == r["sha"]:
            ok += 1
        else:
            rec("FLAG", "origin", "UNPUBLISHED %s: %s on origin is %s, cited %s" % (
                r["id"], r["branch"], h[:9] if h else "absent", r["sha"][:9]))
    rec("PASS", "origin", "%d cited branch heads equal origin" % ok)


# ---------------------------------------------------------------- state
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
        rec("SKIP", "state", "no --state given; STATE comparison and state claims skipped")
        return None
    raw = Path(state_path).read_bytes()
    state = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    prov = load_json("provenance.json")["inputs"]["loop_state"]["sha256"]
    if digest == prov:
        rec("PASS", "state", "STATE.json sha256 equals provenance (%s)" % digest[:12])
    else:
        rec("FLAG", "state", "STATE.json sha256 %s differs from provenance %s (state moved since drafting)" % (digest[:12], prov[:12]))
    bad = 0
    diffs = 0
    for r in rows:
        if not r.get("state_key"):
            if r["disposition"] != "PENDING":
                rec("FAIL", "state", "%s has no state_key and is not PENDING" % r["id"])
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
    covered = {r["state_key"] for r in rows if r.get("state_key")}
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


# ---------------------------------------------------------------- claims
def json_path(obj, path: str):
    for part in path.split("."):
        obj = obj[part]
    return obj


def check_claims(repo: Path, readme: str, state: dict | None) -> None:
    claims = load_json("claims.json")["claims"]
    cache: dict[tuple[str, str], str | None] = {}
    bad = 0
    skipped = 0
    for c in claims:
        if c["text"] not in readme:
            rec("FAIL", "claims", "%s text not in README: %r" % (c["id"], c["text"]))
            bad += 1
        src = c["source"]
        if src["kind"] == "packet":
            key = (src["sha"], src["path"])
            if key not in cache:
                b = git_bytes(repo, "show", "%s:%s" % key)
                cache[key] = b.decode("utf-8", "replace") if b is not None else None
            body = cache[key]
            if body is None:
                rec("FAIL", "claims", "%s source %s:%s unreadable" % (c["id"], src["sha"][:9], src["path"]))
                bad += 1
            elif str(c["needle"]) not in body:
                rec("FAIL", "claims", "%s needle %r not in %s at %s" % (c["id"], c["needle"], src["path"], src["sha"][:9]))
                bad += 1
        elif src["kind"] == "state":
            if state is None:
                skipped += 1
                continue
            try:
                val = json_path(state, src["json_path"])
            except (KeyError, TypeError):
                val = None
            if val != c["needle"]:
                rec("FAIL", "claims", "%s STATE %s = %r, expected %r" % (c["id"], src["json_path"], val, c["needle"]))
                bad += 1
    if not bad:
        rec("PASS", "claims", "%d claims traced to their packet or STATE (%d state claims skipped)" % (len(claims), skipped))


# ---------------------------------------------------------------- graph / pending
EDGE = re.compile(r"^\s*([A-Za-z0-9]+)\s*-->\s*([A-Za-z0-9]+)\s*$")
NODE = re.compile(r"^\s*([A-Za-z0-9]+)\[")


def check_graph(readme: str, rows: list[dict]) -> None:
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
    if not bad:
        rec("PASS", "graph", "%d nodes, %d edges; mermaid and JSON agree" % (len(ids), len(jedges)))


def check_pending(rows: list[dict]) -> None:
    text = (HERE / "PENDING.md").read_text(encoding="utf-8")
    bad = 0
    for r in rows:
        if (r.get("pending") or r["disposition"] == "PENDING") and not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(r["id"]), text):
            rec("FAIL", "pending", "%s can move but is not named in PENDING.md" % r["id"])
            bad += 1
    for lane in REQUIRED_PENDING:
        if lane not in text:
            rec("FAIL", "pending", "PENDING.md does not name %s" % lane)
            bad += 1
    if "Owner rulings" not in text:
        rec("FAIL", "pending", "PENDING.md has no owner-ruling list")
        bad += 1
    if not bad:
        rec("PASS", "pending", "%d moving rows all named in PENDING.md" % sum(1 for r in rows if r.get("pending")))


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
            hits.append("%s:%d %s %r" % (name, line, label, m.group(0)))
    return hits


def check_autolink(texts: dict[str, str]) -> None:
    hits = []
    for name, text in texts.items():
        hits += autolink_hits(name, text)
    if hits:
        for h in hits[:40]:
            rec("FAIL", "autolink", h)
    else:
        rec("PASS", "autolink", "no upstream autolink form or at-mention in %d files" % len(texts))


def name_patterns(name: str) -> list[tuple[str, "re.Pattern[bytes]"]]:
    """Plain form (case-insensitive, not inside a longer alphanumeric word, so a short user
    name does not match a public handle that merely starts with it), hex form, and base64
    forms at the three byte alignments (only the alignment-independent core)."""
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
                    # never print the name itself, only its entry number and the form found
                    hits.append("%s: private-name entry %d present (%s form)" % (label, i + 1, kind))
                    break
    return hits


def check_privacy(repo: Path, texts: dict[str, str], names: list[str] | None, all_commits: bool, base: str) -> None:
    if names is None:
        rec("SKIP", "privacy", "no names file (CUA_PRIVACY_NAMES_FILE); only generic path/secret patterns run")
    hits = []
    for name, text in texts.items():
        hits += privacy_hits(name, text.encode("utf-8"), names)
    scanned = len(texts)
    if all_commits:
        p = git(repo, "rev-list", "%s..HEAD" % base, check=False)
        commits = p.stdout.split()
        for c in commits:
            msg = git_bytes(repo, "log", "-1", "--format=%an <%ae>%n%cn <%ce>%n%B", c) or b""
            # the required author/committer identity is a public noreply address
            hits += privacy_hits("commit %s message" % c[:9], msg, names)
            hits += autolink_hits("commit %s message" % c[:9], msg.decode("utf-8", "replace"))
            files = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", c).stdout.split()
            for f in files:
                blob = git_bytes(repo, "show", "%s:%s" % (c, f))
                if blob is None:
                    continue
                scanned += 1
                hits += privacy_hits("commit %s %s" % (c[:9], f), blob, names)
                if f.endswith((".md", ".json", ".py")):
                    hits += autolink_hits("commit %s %s" % (c[:9], f), blob.decode("utf-8", "replace"))
        rec("PASS" if not hits else "FAIL", "privacy-commits", "%d commits since %s scanned" % (len(commits), base[:9]))
    if hits:
        for h in hits[:40]:
            rec("FAIL", "privacy", h)
    else:
        rec("PASS", "privacy", "0 findings over %d file contents%s" % (scanned, "" if names else " (generic patterns only)"))


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", help="repository to resolve SHAs in (default: the one holding this file)")
    ap.add_argument("--state", help="loop STATE.json to compare dispositions with")
    ap.add_argument("--names-file", help="private-name list (default: $CUA_PRIVACY_NAMES_FILE)")
    ap.add_argument("--offline", action="store_true", help="skip git ls-remote origin")
    ap.add_argument("--all-commits", action="store_true", help="privacy/autolink scan every commit since the base")
    ap.add_argument("--base", default=BASE_SHA)
    a = ap.parse_args()
    repo = Path(a.repo) if a.repo else Path(git(HERE, "rev-parse", "--show-toplevel").stdout.strip())
    if not check_files():
        return report()
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    texts = {f: (HERE / f).read_text(encoding="utf-8") for f in FILES}
    md = {f: t for f, t in texts.items() if f.endswith(".md")}
    rows = load_json("dispositions.json")["rows"]
    check_sections(readme)
    check_rows(rows, readme)
    check_shas(repo, rows, md)
    check_origin(repo, rows, a.offline)
    state = check_state(rows, a.state)
    check_claims(repo, readme, state)
    check_graph(readme, rows)
    check_pending(rows)
    check_autolink(texts)
    check_privacy(repo, texts, load_names(a.names_file), a.all_commits, a.base)
    return report()


def report() -> int:
    order = {"FAIL": 0, "DIFF": 1, "FLAG": 2, "SKIP": 3, "PASS": 4}
    for status, check, detail in sorted(results, key=lambda r: (order[r[0]], r[1])):
        print("%-4s %-15s %s" % (status, check, detail))
    n = {k: sum(1 for r in results if r[0] == k) for k in order}
    print("SUMMARY " + " ".join("%s=%d" % kv for kv in n.items()))
    return 1 if n["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
