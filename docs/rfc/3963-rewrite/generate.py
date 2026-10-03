#!/usr/bin/env python3
"""Generate the trycua/cua issue 3963 rewrite draft from the loop STATE (stdlib only).

Inputs
  rows.spec.json     one hand-maintained record per row: the STATE locator, the claim template
                     and a pointer for every number in it (packet file + line, packet JSON path, or
                     STATE path). Templates hold no bare numbers and no wave-schedule text.
                     'exclusions' names every STATE.dispositions key that has no row, with a reason.
  pending-plan.json  the lanes of the wave in flight and the rows each one touches; those rows read
                     'PENDING: wave-<N> lane <id>' (no hand-written wave strings anywhere else).
                     'deferred' items read 'DEFERRED: wave-<N> <item>'.
  STATE.json         the loop state (--state): dispositions, heads, pins, provider_budget.
  git objects        every packet file is read with `git show <sha>:<path>` at the row's SHA;
                     upstream drift is counted with git rev-list / git diff.

Gates (any failure exits 2 and writes nothing)
  coverage   every STATE.dispositions key maps to exactly one primary row, or is listed in
             rows.spec.json 'exclusions' with a reason (split rows name their primary row in
             'split_of'; rows that cite a sub-record use state_subkey / state_field)
  budget     STATE.provider_budget: used + remaining == cap, and the ledger sums equal the used
             reached and attempt counts
  pin        upstream pin = the newest STATE.pins upstream_main_* key, or --upstream-pin; live
             upstream main is read with git ls-remote and must equal --upstream-live when given
  wave text  no template, head_reason or plan note carries a hand-written wave schedule
  pointers   every number placeholder resolves to its pointer

Outputs (rewritten in place unless --check)
  dispositions.json, claims.json (generated entries), README.md and PENDING.md (generated
  blocks), provenance.json (STATE hash, plan hash, generator hash, pin, live heads, freshness,
  sha_refs), REGEN-DIFF.md (every row that changed against the previous draft)

Run under the loop's hostless wrapper, from the repository root:

    python3 docs/rfc/3963-rewrite/generate.py --state <STATE.json> --upstream-live <sha>
    python3 docs/rfc/3963-rewrite/generate.py --state <STATE.json> --check

Write mode reads live upstream main and the cited PR heads with git ls-remote (read-only) and
records them. --check never touches the network: it reuses the values recorded in
provenance.json and exits 1 when a regeneration would change any generated content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DOC_REL = "docs/rfc/3963-rewrite"
SPEC = "rows.spec.json"
PLAN = "pending-plan.json"
GRAPH = "dependency-graph.json"
TABLE_START = "<!-- dispositions-table:start -->"
TABLE_END = "<!-- dispositions-table:end -->"
NOTES_START = "<!-- head-notes:start -->"
NOTES_END = "<!-- head-notes:end -->"
MOVING_START = "<!-- moving-rows:start -->"
MOVING_END = "<!-- moving-rows:end -->"
GEN_BLOCK = re.compile(r"(<!-- gen:([a-z0-9-]+) -->)(.*?)(<!-- /gen:\2 -->)", re.S)
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.]+)\}")
TABLE_HEAD = ("| ID | Disposition | Class | Branch @ SHA | Packet | Claim boundary | Blocker | Pending |\n"
              "|---|---|---|---|---|---|---|---|")
WAVE_TEXT = re.compile(r"(?i:scheduled (?:in )?wave)|\bOPEN:|\bPENDING:|\bDEFERRED:|\bwave-\d+ lanes? [A-Z]")
PIN_KEY = re.compile(r"^upstream_main_(?:(latest_seen|tested)_)?w(\d+)$")
LINUX_CORE = re.compile(r"/(platform-linux|cua-driver-core|cua-driver-sdk)/")
FORK = "kvnloo/cua"
UP = "trycua" + "/cua"
FORK_URL = "https://github.com/" + FORK + ".git"
UP_URL = "https://github.com/" + UP + ".git"


class GenError(Exception):
    pass


# ---------------------------------------------------------------- git helpers
class Repo:
    def __init__(self, path: Path, head: str = "HEAD"):
        self.path = path
        self.head = head
        self._show: dict[tuple[str, str], str | None] = {}
        self._full: dict[str, str | None] = {}
        self._anc: dict[tuple[str, str], bool] = {}

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, text=True)

    def full(self, sha: str) -> str | None:
        if sha not in self._full:
            p = self.git("rev-parse", "--verify", "-q", sha + "^{commit}")
            self._full[sha] = p.stdout.strip() if p.returncode == 0 else None
        return self._full[sha]

    def show(self, sha: str, path: str) -> str | None:
        key = (sha, path)
        if key not in self._show:
            p = subprocess.run(["git", "-C", str(self.path), "show", "%s:%s" % key], capture_output=True)
            self._show[key] = p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None
        return self._show[key]

    def is_ancestor(self, a: str, b: str) -> bool:
        key = (a, b)
        if key not in self._anc:
            self._anc[key] = self.git("merge-base", "--is-ancestor", a, b).returncode == 0
        return self._anc[key]

    def count(self, a: str, b: str) -> int:
        p = self.git("rev-list", "--count", "%s..%s" % (a, b))
        if p.returncode != 0:
            raise GenError("git rev-list %s..%s failed (objects missing?)" % (a[:9], b[:9]))
        return int(p.stdout.strip())

    def changed(self, a: str, b: str, path: str) -> list[str]:
        p = self.git("diff", "--name-only", "%s..%s" % (a, b), "--", path)
        if p.returncode != 0:
            raise GenError("git diff %s..%s failed (objects missing?)" % (a[:9], b[:9]))
        return sorted(p.stdout.split())

    def remote_url(self, which: str) -> str:
        want = {"fork": FORK, "upstream": UP}[which]
        for name in ("upstream", "origin", "fork"):
            p = self.git("remote", "get-url", name)
            u = p.stdout.strip()
            if p.returncode == 0 and re.sub(r"\.git$", "", u.rstrip("/")).endswith(want):
                return u
        return FORK_URL if which == "fork" else UP_URL

    def ls_remote(self, which: str, refs: list[str]) -> dict[str, str]:
        p = self.git("ls-remote", self.remote_url(which), *refs)
        if p.returncode != 0:
            raise GenError("git ls-remote on the %s failed" % which)
        out = {}
        for line in p.stdout.splitlines():
            sha, ref = line.split("\t")
            out[ref] = sha
        return out


# ---------------------------------------------------------------- formatting
def fmt_value(v, fmt: str) -> str:
    if fmt in ("raw", "text"):
        return v if isinstance(v, str) else json.dumps(v)
    if fmt == "int":
        return "%d" % v
    m = re.fullmatch(r"f(\d)", fmt)
    if m:
        return "%.*f" % (int(m.group(1)), v)
    m = re.fullmatch(r"pct(\d)", fmt)
    if m:
        return "%.*f%%" % (int(m.group(1)), v * 100)
    m = re.fullmatch(r"ci(\d)", fmt)
    if m:
        d = int(m.group(1))
        return "[%.*f, %.*f]" % (d, v[0], d, v[1])
    m = re.fullmatch(r"sci(\d)", fmt)  # signed CI: [-1.4, +0.5]
    if m:
        d = int(m.group(1))
        return "[%+.*f, %+.*f]" % (d, v[0], d, v[1])
    raise GenError("unknown format %r" % fmt)


def json_get(obj, path):
    for part in path:
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def dotted(state: dict, path: str):
    obj = state
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


# ---------------------------------------------------------------- gates
def coverage(spec: dict, state: dict) -> list[str]:
    """Every STATE.dispositions key maps to exactly one primary row or to an exclusion."""
    disp = state.get("dispositions", {})
    excl = spec.get("exclusions", {})
    ids = {r["id"]: r for r in spec["rows"]}
    errs: list[str] = []
    primary: dict[str, list[str]] = {}
    for r in spec["rows"]:
        k = r.get("state_key")
        if not k:
            errs.append("row %s has no state_key" % r["id"])
            continue
        if k not in disp and k not in state:
            errs.append("row %s: state_key %s is not in STATE" % (r["id"], k))
            continue
        if r.get("split_of"):
            p = ids.get(r["split_of"])
            if not p or p.get("state_key") != k or p.get("split_of"):
                errs.append("row %s: split_of %s is not a primary row on STATE key %s" % (r["id"], r["split_of"], k))
            continue
        if r.get("state_subkey") is not None or r.get("state_field") or k not in disp:
            continue  # cites a sub-record or a top-level list, not a disposition record
        primary.setdefault(k, []).append(r["id"])
    for k in disp:
        rows = primary.get(k, [])
        if k in excl:
            if not str(excl[k]).strip():
                errs.append("exclusion %s has no reason" % k)
            if rows:
                errs.append("STATE key %s is excluded but has row(s) %s" % (k, ", ".join(rows)))
        elif len(rows) != 1:
            errs.append("STATE key %s maps to %d primary rows%s (needs exactly 1, or an exclusion with a reason)" % (
                k, len(rows), (": " + ", ".join(rows)) if rows else ""))
    for k in excl:
        if k not in disp:
            errs.append("exclusion %s is not a STATE.dispositions key (stale)" % k)
    return errs


def budget_nums(state: dict) -> dict:
    b = state["provider_budget"]
    out = {}
    for name, path in (("budget.used", "provider_budget.used_requests_reached_provider"),
                       ("budget.cap", "provider_budget.cap_requests"),
                       ("budget.remaining", "provider_budget.remaining_reached"),
                       ("budget.attempts", "provider_budget.used_attempts")):
        val = dotted(state, path)
        out[name] = {"kind": "state", "json_path": path, "fmt": "int", "value": val, "text": "%d" % val}
    errs = budget_errors(b)
    if errs:
        raise GenError("STATE.provider_budget gate: " + "; ".join(errs))
    return out


def budget_errors(b: dict) -> list[str]:
    errs = []
    if b["used_requests_reached_provider"] + b["remaining_reached"] != b["cap_requests"]:
        errs.append("used %d + remaining %d != cap %d" % (b["used_requests_reached_provider"], b["remaining_reached"], b["cap_requests"]))
    led = b.get("ledger", [])
    lr = sum(int(x.get("reached", 0)) for x in led)
    la = sum(int(x.get("attempts", 0)) for x in led)
    if lr != b["used_requests_reached_provider"]:
        errs.append("ledger reached sum %d != used %d" % (lr, b["used_requests_reached_provider"]))
    if la != b["used_attempts"]:
        errs.append("ledger attempts sum %d != used attempts %d" % (la, b["used_attempts"]))
    return errs


def state_pin(state: dict) -> tuple[str, str]:
    """Newest upstream_main_* pin: highest wave suffix; on a tie the plain key, then latest_seen."""
    best = None
    for k, v in state.get("pins", {}).items():
        m = PIN_KEY.match(k)
        h = re.match(r"[0-9a-f]{40}", v) if isinstance(v, str) else None
        if not (m and h):
            continue
        rank = (int(m.group(2)), {None: 2, "latest_seen": 1, "tested": 0}[m.group(1)])
        if best is None or rank > best[0]:
            best = (rank, k, h.group(0))
    if not best:
        raise GenError("STATE.pins has no upstream_main_*_wN key with a full SHA")
    return best[1], best[2]


def wave_text_errors(spec: dict, plan: dict) -> list[str]:
    errs = []
    for r in spec["rows"]:
        for f in ("claim_boundary", "blocker", "pending", "head_reason"):
            if WAVE_TEXT.search(r.get(f) or ""):
                errs.append("%s.%s carries hand-written wave-schedule text" % (r["id"], f))
    for lane, info in plan["lanes"].items():
        for rid, note in info.get("rows", {}).items():
            if WAVE_TEXT.search(note or ""):
                errs.append("plan lane %s note for %s carries wave-schedule text" % (lane, rid))
    return errs


# ---------------------------------------------------------------- heads
def split_branch(b: str) -> str:
    return b.split(" (")[0].strip()


def state_head(state: dict, key: str | None):
    node = state.get("dispositions", {}).get(key) if key else None
    if not isinstance(node, dict):
        return None, None
    commit = node.get("commit")
    m = re.match(r"[0-9a-f]{7,40}", commit or "")
    return (split_branch(node["branch"]) if node.get("branch") else None), (m.group(0) if m else None)


def resolve_head(repo: Repo, state: dict, spec_row: dict):
    """Branch and SHA for a row, always read from STATE. Returns (branch, sha, note)."""
    head = spec_row.get("head", "state")
    if head is None:
        return None, None, None
    sb, sc = state_head(state, spec_row.get("state_key"))
    if head == "state":
        branch, commit, src = sb, sc, "STATE.dispositions.%s" % spec_row.get("state_key")
    elif "state_key" in head:
        branch, commit = state_head(state, head["state_key"])
        src = "STATE.dispositions.%s" % head["state_key"]
    elif "wave" in head:
        waves = [w for w in state.get("waves", []) if w.get("wave") == head["wave"]]
        if not waves:
            raise GenError("%s: STATE has no wave %s" % (spec_row["id"], head["wave"]))
        text = waves[0]["branches"][head["branches_key"]]
        branch, commit = [x.strip() for x in text.split(" @ ")]
        src = "STATE.waves[wave=%s].branches[%r]" % (head["wave"], head["branches_key"])
    else:
        raise GenError("%s: unknown head form %r" % (spec_row["id"], head))
    if not branch or not commit:
        raise GenError("%s: %s has no branch/commit" % (spec_row["id"], src))
    full = repo.full(commit)
    if not full:
        raise GenError("%s: commit %s from %s does not resolve" % (spec_row["id"], commit, src))
    note = None
    sfull = repo.full(sc) if sc else None
    if head != "state" and (sb != branch or sfull != full):
        reason = spec_row.get("head_reason")
        if not reason:
            raise GenError("%s: head differs from STATE.dispositions.%s and has no head_reason" % (
                spec_row["id"], spec_row.get("state_key")))
        note = {"row": spec_row["id"], "cited": "%s @ %s" % (branch, full[:9]), "source": src,
                "state_row_head": ("%s @ %s" % (sb, (sfull or sc)[:9])) if (sfull or sc) else "%s (no commit)" % (sb or "no branch"),
                "reason": reason}
    return branch, full, note


# ---------------------------------------------------------------- numbers
def resolve_num(repo: Repo, state: dict, rows_by_id: dict, row_id: str, name: str, src: dict) -> dict:
    kind = src["src"]
    where = "%s.%s" % (row_id, name)
    if kind in ("line", "json"):
        owner = rows_by_id[src.get("of", row_id)]
        sha, packet = owner["sha"], owner["packet"]
        if not (sha and packet):
            raise GenError("%s: row %s has no packet" % (where, owner["id"]))
        path = packet.rstrip("/") + "/" + src.get("file", "README.md")
        body = repo.show(sha, path)
        if body is None:
            raise GenError("%s: %s unreadable at %s" % (where, path, sha[:9]))
        if kind == "line":
            ctx, text = src["context"], src["text"]
            if text not in ctx:
                raise GenError("%s: text %r not inside context %r" % (where, text, ctx))
            hits = [i for i, ln in enumerate(body.splitlines(), 1) if ctx in ln]
            if len(hits) != 1:
                raise GenError("%s: context %r found on %d lines of %s (needs exactly 1)" % (where, ctx, len(hits), path))
            return {"kind": "packet_line", "sha": sha, "path": path, "line": hits[0], "context": ctx, "text": text}
        data = json.loads(body)
        try:
            val = json_get(data, src["path"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise GenError("%s: JSON path %s missing in %s" % (where, src["path"], path))
        fmt = src.get("fmt", "raw")
        return {"kind": "packet_json", "sha": sha, "path": path, "json_path": src["path"], "fmt": fmt,
                "value": val, "text": fmt_value(val, fmt)}
    if kind == "state":
        val = dotted(state, src["path"])
        fmt = src.get("fmt", "raw")
        return {"kind": "state", "json_path": src["path"], "fmt": fmt, "value": val, "text": fmt_value(val, fmt)}
    if kind == "state_text":
        try:
            val = dotted(state, src["path"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise GenError("%s: STATE has no %s" % (where, src["path"]))
        if isinstance(val, list):
            val = " | ".join(str(x) for x in val)
        ctx, text = src["context"], src["text"]
        if ctx not in str(val) or text not in ctx:
            raise GenError("%s: STATE %s does not contain %r (or text not in context)" % (where, src["path"], ctx))
        return {"kind": "state_text", "json_path": src["path"], "context": ctx, "text": text}
    raise GenError("%s: unknown number source %r" % (where, kind))


def render(template: str | None, nums: dict, where: str) -> str | None:
    if template is None:
        return None

    def sub(m):
        if m.group(1) not in nums:
            raise GenError("%s: placeholder {%s} has no pointer" % (where, m.group(1)))
        return nums[m.group(1)]["text"]
    return PLACEHOLDER.sub(sub, template)


# ---------------------------------------------------------------- pending (from the plan)
def plan_marks(plan: dict, row_ids: set) -> tuple[dict, dict]:
    """Row id -> [(lane, note)] for the wave in flight, and row id -> [(wave, item, note)] deferred."""
    lanes: dict[str, list] = {}
    for lane, info in plan["lanes"].items():
        if not info.get("scope"):
            raise GenError("plan lane %s has no scope" % lane)
        for rid, note in info.get("rows", {}).items():
            if rid not in row_ids:
                raise GenError("plan lane %s names row %s, which is not a draft row" % (lane, rid))
            lanes.setdefault(rid, []).append((lane, note))
        if not info.get("rows") and not info.get("note"):
            raise GenError("plan lane %s touches no row and has no note" % lane)
    deferred: dict[str, list] = {}
    for d in plan.get("deferred", []):
        if int(d["wave"]) <= int(plan["wave"]):
            raise GenError("deferred item %r is not after wave %s" % (d["item"], plan["wave"]))
        for rid, note in d.get("rows", {}).items():
            if rid not in row_ids:
                raise GenError("deferred item %r names row %s, which is not a draft row" % (d["item"], rid))
            deferred.setdefault(rid, []).append((d["wave"], d["item"], note))
    return lanes, deferred


def pending_text(plan: dict, marks: list, deferred: list, static: str | None) -> str | None:
    parts = []
    w = plan["wave"]
    if marks:
        named = ", ".join("%s (%s)" % (l, n) if n else l for l, n in marks)
        parts.append("PENDING: wave-%s lane%s %s. No wave-%s result is cited." % (w, "s" if len(marks) > 1 else "", named, w))
    for dw, item, note in deferred:
        parts.append("DEFERRED: wave-%s %s%s." % (dw, item, (" (%s)" % note) if note else ""))
    if static:
        parts.append(("Also: " + static[0].lower() + static[1:]) if parts else static)
    return " ".join(parts) or None


# ---------------------------------------------------------------- build
def cell(s) -> str:
    return "" if s is None else str(s).replace("|", "/")


def build(repo: Repo, state: dict, spec: dict, plan: dict) -> dict:
    errs = coverage(spec, state) + wave_text_errors(spec, plan)
    if errs:
        raise GenError("%d gate failure(s):\n  " % len(errs) + "\n  ".join(errs))
    rows_out, claims, notes = [], [], []
    by_id: dict[str, dict] = {}
    gnums = budget_nums(state)
    marks, deferred = plan_marks(plan, {s["id"] for s in spec["rows"]})
    # pass 1: heads
    for s in spec["rows"]:
        branch, sha, note = resolve_head(repo, state, s)
        r = {"id": s["id"], "kind": s["kind"], "disposition": s["disposition"], "class": s["class"],
             "branch": branch, "sha": sha, "packet": s.get("packet") if sha else None,
             "owner": s["owner"]}
        if s.get("packet") and not sha:
            raise GenError("%s: packet without a head" % s["id"])
        if note:
            notes.append(note)
            r["head_note"] = note["reason"]
        by_id[s["id"]] = r
        rows_out.append((s, r))
    # pass 2: numbers and text
    errors = []
    for s, r in rows_out:
        nums = dict(gnums)
        for name, src in s.get("nums", {}).items():
            try:
                nums[name] = resolve_num(repo, state, by_id, s["id"], name, src)
            except GenError as e:
                errors.append(str(e))
        if errors:
            continue
        r["blocker"] = render(s.get("blocker"), nums, s["id"] + ".blocker")
        static = render(s.get("pending"), nums, s["id"] + ".pending")
        r["pending"] = pending_text(plan, marks.get(s["id"], []), deferred.get(s["id"], []), static)
        if marks.get(s["id"]):
            r["pending_lanes"] = [l for l, _ in marks[s["id"]]]
        for k in ("state_key", "state_subkey", "state_field", "state_expect", "diff_reason", "split_of"):
            if s.get(k) is not None:
                r[k] = s[k]
        r["claim_boundary"] = render(s["claim_boundary"], nums, s["id"] + ".claim_boundary")
        used = set()
        for field in ("claim_boundary", "blocker", "pending"):
            used |= set(PLACEHOLDER.findall(s.get(field) or ""))
        r["numbers"] = {}
        for name in sorted(used):
            ptr = dict(nums[name])
            ptr.pop("value", None)
            r["numbers"][name] = ptr
            claims.append({"id": "G-%s-%s" % (s["id"], name), "generated": True, "row": s["id"],
                           "text": ptr["text"], "readme_row": s["id"], "source": ptr})
    if errors:
        raise GenError("%d number pointer(s) failed:\n  " % len(errors) + "\n  ".join(errors))
    for cid, name in (("S01", "budget.used"), ("S02", "budget.cap"), ("S03", "budget.remaining"),
                      ("S04", "budget.attempts")):
        ptr = dict(gnums[name])
        ptr.pop("value", None)
        claims.append({"id": cid, "generated": True, "row": "STATE", "text": ptr["text"],
                       "readme_block": "budget", "source": ptr})
    rows = [r for _, r in rows_out]
    return {"rows": rows, "claims": claims, "notes": notes, "budget": gnums}


# ---------------------------------------------------------------- freshness, pin, live heads
def freshness(repo: Repo, state: dict, spec: dict, prov: dict, live: dict, pin_override: str | None) -> dict:
    fs = spec["freshness"]
    if pin_override:
        pin_key, pin = "--upstream-pin", pin_override
    else:
        pin_key, pin = state_pin(state)
    pin_full = repo.full(pin)
    live_full = repo.full(live["main"])
    base = prov["base"]["sha"]
    tested = prov["freshness"]["tested_upstream"]
    recert = fs["recert_tested"]
    for label, sha, full in (("STATE pin", pin, pin_full), ("live upstream main", live["main"], live_full)):
        if not full:
            raise GenError("%s %s is not in this clone: fetch upstream main read-only first" % (label, sha[:9]))
    if not repo.is_ancestor(pin_full, live_full):
        raise GenError("STATE pin %s is not an ancestor of live upstream main %s" % (pin[:9], live["main"][:9]))
    paths = [p for p in repo.changed(base, live_full, "libs/cua-driver") if LINUX_CORE.search(p)]
    since_pin = [p for p in repo.changed(pin_full, live_full, "libs/cua-driver") if LINUX_CORE.search(p)]
    known = {p["path"]: p for p in fs["linux_core_paths"]}
    missing = [p for p in paths if p not in known]
    if missing:
        raise GenError("Linux/core paths changed since the base without a status in rows.spec.json freshness: " + ", ".join(missing))
    stale = [p for p in known if p not in paths]
    if stale:
        raise GenError("rows.spec.json freshness lists paths that did not change since the base: " + ", ".join(stale))
    rows = []
    for p in fs["linux_core_paths"]:
        m = repo.full(p["merge"])
        if not m or not repo.is_ancestor(m, live_full):
            raise GenError("merge %s for %s is not on live upstream main" % (p["merge"][:9], p["path"]))
        if p["path"] not in repo.changed(m + "^", m, p["path"]):
            raise GenError("merge %s does not touch %s" % (p["merge"][:9], p["path"]))
        node = dotted(state, p["state_path"])
        text = " | ".join(map(str, node)) if isinstance(node, list) else json.dumps(node) if isinstance(node, dict) else str(node)
        if p["state_context"] not in text:
            raise GenError("freshness status of %s: STATE %s no longer contains %r" % (p["path"], p["state_path"], p["state_context"]))
        rows.append(dict(p, merge=m))
    return {"state_pin_key": pin_key, "state_pin": pin_full, "live_main": live_full, "live_read": live["read"],
            "live_read_utc": live["utc"], "base": base, "tested_upstream": tested, "recert_tested": repo.full(recert),
            "commits_past_base": repo.count(base, live_full), "commits_past_tested": repo.count(tested, live_full),
            "commits_past_recert": repo.count(recert, live_full), "commits_past_pin": repo.count(pin_full, live_full),
            "linux_core_paths": rows, "linux_core_paths_since_pin": since_pin,
            "other_libs_cua_driver_files_since_pin": [p for p in repo.changed(pin_full, live_full, "libs/cua-driver") if not LINUX_CORE.search(p)]}


def read_live(repo: Repo, spec: dict, expect_main: str | None) -> dict:
    """Read live upstream main and every cited PR head with git ls-remote (read-only)."""
    utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    main = repo.ls_remote("upstream", ["refs/heads/main"]).get("refs/heads/main")
    if not main:
        raise GenError("git ls-remote returned no upstream main")
    if expect_main and not main.startswith(expect_main):
        raise GenError("live upstream main is %s, expected %s (--upstream-live)" % (main[:9], expect_main))
    heads = []
    by_remote: dict[str, list] = {}
    for h in spec["pr_heads"]:
        by_remote.setdefault(h["remote"], []).append(h)
    for remote, hs in by_remote.items():
        got = repo.ls_remote(remote, [h["ref"] for h in hs])
        for h in hs:
            heads.append({"label": h["label"], "remote": remote, "ref": h["ref"], "cited": h["cited"],
                          "live": got.get(h["ref"])})
    moved = [h for h in heads if h["live"] != h["cited"]]
    if moved:
        raise GenError("cited PR heads moved: " + "; ".join("%s cited %s, live %s" % (
            h["label"], h["cited"][:9], (h["live"] or "absent")[:9]) for h in moved))
    return {"main": main, "read": "git ls-remote (read-only) at generation time", "utc": utc,
            "heads": sorted(heads, key=lambda h: h["label"])}


def recorded_live(prov: dict) -> dict:
    fr, lh = prov.get("freshness_now", {}), prov.get("live_heads", {})
    if not fr.get("live_main"):
        raise GenError("provenance.json records no live upstream main; run generate.py once without --check")
    return {"main": fr["live_main"], "read": fr["live_read"], "utc": fr["live_read_utc"], "heads": lh.get("heads", [])}


# ---------------------------------------------------------------- rendering
def table(rows: list[dict]) -> str:
    out = [TABLE_HEAD]
    for r in rows:
        head = ("%s @ `%s`" % (r["branch"], r["sha"][:9])) if r.get("sha") else "—"
        out.append("| %s |" % " | ".join([
            r["id"], r["disposition"], cell(r["class"]), head, cell(r.get("packet") or "—"),
            cell(r["claim_boundary"]), cell(r.get("blocker") or ""), cell(r.get("pending") or "")]))
    return "\n".join(out)


def head_notes(notes: list[dict]) -> str:
    if not notes:
        return "No row cites a head other than its STATE row's head."
    out = ["Rows whose cited head differs from the head in their own STATE row (generated from STATE; the STATE row"
           " head is written plain because it may be unpublished):"]
    for n in notes:
        out.append("- **%s** cites %s (from %s); its STATE row names %s. %s" % (
            n["row"], n["cited"].replace(" @ ", " @ `") + "`", n["source"], n["state_row_head"], n["reason"]))
    return "\n".join(out)


def moving_rows(rows: list[dict]) -> str:
    out = ["| Row | Disposition | What can still move it |", "|---|---|---|"]
    for r in rows:
        if r.get("pending"):
            out.append("| %s | %s | %s |" % (r["id"], r["disposition"], cell(r["pending"])))
    return "\n".join(out)


def mermaid(graph: dict) -> str:
    groups = [("Deltas", "delta"), ("Owners", "owner"), ("Prerequisites", None)]
    out = ["", "```mermaid", "flowchart LR"]
    for title, kind in groups:
        out.append("  subgraph %s" % title)
        for n in graph["nodes"]:
            k = n["kind"]
            if (kind and k == kind) or (kind is None and k not in ("delta", "owner")):
                out.append("    %s[%s]" % (n["id"], n.get("short", n["label"])))
        out.append("  end")
    for e in graph["edges"]:
        out.append("  %s --> %s" % (e["from"], e["to"]))
    out += ["```", ""]
    return "\n".join(out)


def gen_blocks(build_out: dict, spec: dict, plan: dict, fresh: dict, graph: dict) -> dict:
    t = {k: v["text"] for k, v in build_out["budget"].items()}
    w = plan["wave"]
    lane_rows = ["| Lane | Scope (planner input, pending-plan.json) | Rows marked PENDING |", "|---|---|---|"]
    for lane, info in plan["lanes"].items():
        rows = [r["id"] for r in build_out["rows"] if lane in r.get("pending_lanes", [])]
        lane_rows.append("| %s | %s | %s |" % (lane, cell(info["scope"]), ", ".join(rows) or "none: %s" % cell(info.get("note", ""))))
    deferred = ["| Item | Wave | Rows marked DEFERRED |", "|---|---|---|"]
    for d in plan.get("deferred", []):
        deferred.append("| %s | wave-%s | %s |" % (cell(d["item"]), d["wave"], ", ".join(d.get("rows", {})) or "none"))
    fr = ["| Upstream item | Path | Merged as | Status |", "|---|---|---|---|"]
    for p in fresh["linux_core_paths"]:
        fr.append("| %s PR %d (%s) | `%s` | `%s` | %s |" % (UP, p["pr"], p["title"], p["path"], p["merge"][:9], cell(p["status"])))
    cov = ["STATE.dispositions keys without a row of their own (rows.spec.json `exclusions`, checked by the coverage gate):"]
    for k, why in spec["exclusions"].items():
        cov.append("- **%s:** %s" % (k, why))
    splits: dict[str, list] = {}
    for r in build_out["rows"]:
        if r.get("split_of"):
            splits.setdefault(r["split_of"], []).append(r["id"])
    cov.append("")
    cov.append("STATE records split into several rows, one per verdict (`split_of`): " + "; ".join(
        "%s → %s" % (p, ", ".join([p] + c)) for p, c in splits.items()) + ".")
    drift = ("upstream main at generation is `%s` (%s, %s): %d commits past the base, %d past the tested %s, %d past"
             " FRESH-07's `%s` and %d past the STATE pin `%s` (STATE.pins.%s). %d Linux or core Driver paths changed since the"
             " base; none since the STATE pin." if not fresh["linux_core_paths_since_pin"] else "")
    if not drift:
        raise GenError("Linux/core paths changed since the STATE pin: %s" % ", ".join(fresh["linux_core_paths_since_pin"]))
    drift = drift % (fresh["live_main"][:9], fresh["live_read"].split(" (")[0], fresh["live_read_utc"],
                     fresh["commits_past_base"], fresh["commits_past_tested"], fresh["tested_upstream"][:9],
                     fresh["commits_past_recert"], fresh["recert_tested"][:9], fresh["commits_past_pin"],
                     fresh["state_pin"][:9], fresh["state_pin_key"], len(fresh["linux_core_paths"]))
    return {
        "budget": "%s of %s reached used, %s remain (%s attempts)" % (
            t["budget.used"], t["budget.cap"], t["budget.remaining"], t["budget.attempts"]),
        "wave-lanes": "\n" + "\n".join(lane_rows) + "\n",
        "deferred": "\n" + "\n".join(deferred) + "\n",
        "freshness": "\n" + "\n".join(fr) + "\n",
        "drift": drift,
        "coverage": "\n" + "\n".join(cov) + "\n",
        "mermaid": mermaid(graph),
        "wave": str(w),
    }


def replace_between(text: str, start: str, end: str, body: str, name: str) -> str:
    i, j = text.find(start), text.find(end)
    if i < 0 or j < i:
        raise GenError("%s markers missing" % name)
    return text[:i + len(start)] + "\n" + body + "\n" + text[j:]


def sub_blocks(text: str, blocks: dict, name: str) -> str:
    def sub(m):
        if m.group(2) not in blocks:
            raise GenError("unknown gen block %s in %s" % (m.group(2), name))
        return m.group(1) + blocks[m.group(2)] + m.group(4)
    return GEN_BLOCK.sub(sub, text)


def render_readme(readme: str, build_out: dict, blocks: dict) -> str:
    readme = replace_between(readme, TABLE_START, TABLE_END, table(build_out["rows"]), "dispositions-table")
    readme = replace_between(readme, NOTES_START, NOTES_END, head_notes(build_out["notes"]), "head-notes")
    return sub_blocks(readme, blocks, "README.md")


def render_pending(pending: str, build_out: dict, blocks: dict) -> str:
    pending = replace_between(pending, MOVING_START, MOVING_END, moving_rows(build_out["rows"]), "moving-rows")
    return sub_blocks(pending, blocks, "PENDING.md")


# ---------------------------------------------------------------- regeneration diff
DIFF_FIELDS = ("disposition", "class", "branch", "sha", "packet", "claim_boundary", "blocker", "pending")


def regen_diff(repo: Repo, prev: dict, rows: list[dict]) -> str:
    body = repo.show(prev["sha"], DOC_REL + "/dispositions.json")
    if body is None:
        raise GenError("previous draft %s has no dispositions.json" % prev["sha"][:9])
    old = {r["id"]: r for r in json.loads(body)["rows"]}
    new = {r["id"]: r for r in rows}
    lines = ["| Row | Change | Fields changed | Disposition | Head |", "|---|---|---|---|---|"]
    n = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}

    def head(r):
        return "%s @ %s" % (r["branch"], r["sha"][:9]) if r.get("sha") else "none"
    for rid in [r["id"] for r in rows] + [i for i in old if i not in new]:
        a, b = old.get(rid), new.get(rid)
        if a is None:
            n["added"] += 1
            lines.append("| %s | added | all | %s | %s |" % (rid, b["disposition"], head(b)))
        elif b is None:
            n["removed"] += 1
            lines.append("| %s | removed | all | %s (was) | %s (was) |" % (rid, a["disposition"], head(a)))
        else:
            f = [k for k in DIFF_FIELDS if (a.get(k) or None) != (b.get(k) or None)]
            if not f:
                n["unchanged"] += 1
                continue
            n["changed"] += 1
            d = b["disposition"] if a["disposition"] == b["disposition"] else "%s -> %s" % (a["disposition"], b["disposition"])
            h = "unchanged" if (a.get("sha"), a.get("branch")) == (b.get("sha"), b.get("branch")) else "%s -> %s" % (head(a), head(b))
            lines.append("| %s | changed | %s | %s | %s |" % (rid, ", ".join(f), d, h))
    out = ["# Regeneration diff (generated)", "",
           "Every row of `dispositions.json` that changed against the previous draft, %s @ %s (provenance.json"
           " `parent_revision`). Generated by `generate.py`; do not edit. Text fields are named, not quoted; the"
           " previous text is at that commit." % (prev["branch"], prev["sha"][:9]), "",
           "Rows before: %d. Rows now: %d. Added %d, removed %d, changed %d, unchanged %d." % (
               len(old), len(new), n["added"], n["removed"], n["changed"], n["unchanged"]), ""]
    return "\n".join(out + lines) + "\n"


# ---------------------------------------------------------------- sha_refs
BACKTICK = re.compile(r"`([0-9a-f]{7,40})`")


def sha_refs(repo: Repo, rows: list[dict], md_texts: list[str], spec: dict, fresh: dict) -> dict:
    """Map every backticked SHA in the markdown to a ref that holds it, so a verifier in a
    heads-only clone knows exactly what to fetch."""
    cands = [("self", "HEAD", repo.full(repo.head))]
    seen = set()
    for r in rows:
        if r.get("sha") and r["branch"] not in seen:
            seen.add(r["branch"])
            cands.append(("fork", "refs/heads/" + r["branch"], r["sha"]))
    cands.append(("upstream", "refs/heads/main", fresh["live_main"]))
    for e in spec.get("extra_refs", []):
        cands.append((e["remote"], e["ref"], repo.full(e["sha"])))
    out = {}
    for text in md_texts:
        for m in BACKTICK.finditer(text):
            short = m.group(1)
            full = repo.full(short)
            if not full:
                raise GenError("backticked SHA %s does not resolve" % short)
            if full in out:
                continue
            for remote, ref, tip in cands:
                if tip and repo.is_ancestor(full, tip):
                    out[full] = {"remote": remote, "ref": ref}
                    break
            else:
                raise GenError("backticked SHA %s is on no known ref (add it to extra_refs)" % short)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- main
def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def dump_json(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def generate(repo_path: Path, state_path: str, plan_path: str | None = None, live: dict | None = None,
             upstream_pin: str | None = None, head: str = "HEAD") -> dict:
    """Return {filename: new content} for every generated file. live=None reuses the live
    upstream main and PR heads recorded in provenance.json (check mode)."""
    repo = Repo(repo_path, head)
    raw = Path(state_path).read_bytes()
    state = json.loads(raw)
    spec = load(SPEC)
    plan_file = Path(plan_path) if plan_path else HERE / PLAN
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    graph = load(GRAPH)
    prov = load("provenance.json")
    if live is None:
        live = recorded_live(prov)
        if upstream_pin is None and prov.get("freshness_now", {}).get("state_pin_key") == "--upstream-pin":
            upstream_pin = prov["freshness_now"]["state_pin"]
    out = build(repo, state, spec, plan)
    fresh = freshness(repo, state, spec, prov, live, upstream_pin)
    blocks = gen_blocks(out, spec, plan, fresh, graph)
    disp = {"schema": "rfc3963-rewrite-dispositions/v3",
            "note": spec["dispositions_note"],
            "generated_by": "generate.py from rows.spec.json + pending-plan.json + STATE.json",
            "rows": out["rows"]}
    claims_doc = load("claims.json")
    curated = [c for c in claims_doc["claims"] if not c.get("generated")]
    claims_doc["claims"] = curated + out["claims"]
    readme = render_readme((HERE / "README.md").read_text(encoding="utf-8"), out, blocks)
    pending = render_pending((HERE / "PENDING.md").read_text(encoding="utf-8"), out, blocks)
    diff = regen_diff(repo, prov["parent_revision"], out["rows"])
    md = [readme, pending, (HERE / "REVIEW-CHECKLIST.md").read_text(encoding="utf-8")]
    prov["sha_refs"] = sha_refs(repo, out["rows"], md, spec, fresh)
    prov["inputs"]["loop_state"]["sha256"] = hashlib.sha256(raw).hexdigest()
    prov["inputs"]["pending_plan"] = {"file": PLAN if not plan_path else plan_file.name, "sha256": sha256_file(plan_file),
                                      "wave": plan["wave"], "lanes": list(plan["lanes"])}
    prov["generator"] = {"file": "generate.py", "sha256": sha256_file(HERE / "generate.py"),
                         "note": "content hash of the generator that wrote these files; the commit SHA is recorded by the lane mirror"}
    prov["freshness_now"] = fresh
    prov["live_heads"] = {"read": live["read"], "utc": live["utc"], "heads": live["heads"]}
    prov["provider_budget_at_generation"] = {k: v["value"] for k, v in out["budget"].items()}
    return {"dispositions.json": dump_json(disp), "claims.json": dump_json(claims_doc),
            "README.md": readme, "PENDING.md": pending, "provenance.json": dump_json(prov),
            "REGEN-DIFF.md": diff}


def compare(new: dict) -> list[str]:
    """Differences between a regeneration and the committed files (provenance's STATE hash is
    compared separately by the verifier and ignored here)."""
    diffs = []
    for name, text in new.items():
        p = HERE / name
        old = p.read_text(encoding="utf-8") if p.is_file() else ""
        if name == "provenance.json":
            a, b = json.loads(old or "{}"), json.loads(text)
            for x in (a, b):
                x.get("inputs", {}).get("loop_state", {}).pop("sha256", None)
            if a != b:
                keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
                diffs.append("provenance.json differs from regeneration in %s" % ", ".join(keys))
            continue
        if old != text:
            ol, nl = old.splitlines(), text.splitlines()
            first = next((i for i, (x, y) in enumerate(zip(ol, nl)) if x != y), min(len(ol), len(nl)))
            diffs.append("%s differs from regeneration at line %d" % (name, first + 1))
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--pending-plan", help="plan of the wave in flight (default: pending-plan.json next to this file)")
    ap.add_argument("--upstream-pin", help="override the newest STATE.pins upstream_main_* key")
    ap.add_argument("--upstream-live", help="expected live upstream main (checked with git ls-remote)")
    ap.add_argument("--repo")
    ap.add_argument("--head", default="HEAD", help="commit whose history holds this draft (default HEAD)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    repo = Path(a.repo) if a.repo else Path(subprocess.run(
        ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip())
    try:
        live = None if a.check else read_live(Repo(repo), load(SPEC), a.upstream_live)
        new = generate(repo, a.state, a.pending_plan, live, a.upstream_pin, a.head)
    except GenError as e:
        print("GENERATE ERROR: %s" % e)
        return 2
    if a.check:
        d = compare(new)
        for x in d:
            print("DRIFT " + x)
        print("generated content %s" % ("is up to date" if not d else "is stale (%d files)" % len(d)))
        return 1 if d else 0
    for name, text in new.items():
        (HERE / name).write_text(text, encoding="utf-8")
    print("wrote %s; live upstream main %s read %s" % (", ".join(sorted(new)), live["main"][:9], live["utc"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
