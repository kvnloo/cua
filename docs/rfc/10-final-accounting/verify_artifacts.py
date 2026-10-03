#!/usr/bin/env python3
"""Verify the kvnloo/cua#10 accounting table and the kvnloo/cua#74 posting queue.

Stdlib only. Run under the lane's hostless wrapper from any checkout of the fork that has the cited commits.

  python3 docs/rfc/10-final-accounting/verify_artifacts.py [--target 10|74|all] [--offline]
          [--extra-md FILE ...]

Environment (all optional; nothing below is ever committed):
  CUA_PRIVACY_NAMES_FILE  newline-separated private names (whole-token, case-insensitive; hex/base64 forms too)
  CUA_LOOP_STATE          loop STATE.json; when set, the committed state extract is re-derived and compared

Checks:
  A. every number in accounting.json / queue.json re-read with `git show <sha>:<path>` and compared within the
     stated rounding; within-row derived ratios recomputed;
  B. every cited SHA exists; packet branches and queue refs are on origin at the cited SHA (read-only ls-remote);
  C. the generated README sections equal a fresh render of the JSON;
  D. each queue item has the eight fields; free text carries no bare numbers (numbers come from pointers);
  E. the READY NOW booleans recomputed from their sources (state extract, ls-remote, git diff, PR refs);
  F. every pending owner decision in the state extract is covered by a queue item;
  G. no upstream autolink pattern in rendered text; fork items written kvnloo/cua#N;
  H. privacy: names (plus hex/base64 forms), absolute local paths and secret-like strings in the working tree and
     in every commit of the branch since the pinned main.
"""
import argparse
import base64
import binascii
import getpass
import hashlib
import json
import os
import re
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RFC = os.path.dirname(HERE)
Q_DIR = os.path.join(RFC, "74-posting-queue")
sys.path.insert(0, HERE)
sys.path.insert(0, Q_DIR)
import rfc_common as C  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    if not ok:
        print("FAIL  %s  %s" % (name, detail))


def skip(name, why):
    RESULTS.append((name, None, why))
    print("SKIP  %s  %s" % (name, why))


# --------------------------------------------------------------------------- A. pointers

def resolve_acc_pointer(acc, ptr):
    f = ptr["from"]
    meta = acc["packets"][f["packet"]]
    data = C.show_json(meta["sha"], meta["dir"] + "/" + meta["files"][f["file"]])
    return C.resolve(data, f["path"])


def check_acc_pointers(acc):
    n = 0
    for where, ptr in C.walk_pointers(acc):
        try:
            raw = resolve_acc_pointer(acc, ptr)
        except Exception as e:  # noqa: BLE001
            check("A.acc.resolve " + where, False, repr(e))
            continue
        nd = ptr["from"].get("round")
        ok = C.close(C.rnd(raw, nd), ptr["value"], nd)
        if not ok:
            check("A.acc.value " + where, False, "packet %r vs table %r" % (C.rnd(raw, nd), ptr["value"]))
        n += 1
    check("A.acc.pointers", n > 0, "%d pointers re-read" % n)

    def walk_derived(node, where=""):
        if isinstance(node, dict):
            if "derived" in node:
                yield where, node
            for k, v in node.items():
                if k != "derived":
                    yield from walk_derived(v, where + "/" + k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk_derived(v, "%s/%d" % (where, i))

    nd_count = 0
    for where, d in walk_derived(acc):
        spec = d["derived"]
        a = resolve_acc_pointer(acc, spec["num"])
        b = resolve_acc_pointer(acc, spec["den"])
        check("A.acc.derived.inputs " + where, C.close(a, spec["num"]["value"], spec["num"]["from"]["round"]) and
              C.close(b, spec["den"]["value"], spec["den"]["from"]["round"]))
        val = C.rnd(float(a) / float(b), spec["round"])
        check("A.acc.derived " + where, C.close(val, d["value"], spec["round"]), "%r vs %r" % (val, d["value"]))
        nd_count += 1
    check("A.acc.derived.count", True, "%d derived ratios" % nd_count)


def resolve_q_pointer(ptr):
    f = ptr["from"]
    data = C.show_json(f["sha"], f["file"])
    return C.resolve(data, f["path"])


def check_queue_pointers(q):
    n = 0
    for it in q["items"]:
        for e in it["fields"]["completed_evidence"]:
            for k, p in e["n"].items():
                if "check" in p:
                    c = p["check"]
                    if c["op"] == "same_blob":
                        a = C.git("rev-parse", "%s:%s" % tuple(c["a"])).stdout.strip()
                        b = C.git("rev-parse", "%s:%s" % tuple(c["b"])).stdout.strip()
                        check("A.queue.same_blob %s" % it["id"], (a == b) == p["value"], "%s vs %s" % (a[:12], b[:12]))
                    n += 1
                    continue
                if p["from"].get("key"):
                    f = p["from"]
                    parent = C.resolve(C.show_json(f["sha"], f["file"]), f["path"][:-1])
                    check("A.queue.key %s/%s" % (it["id"], k), p["value"] == f["path"][-1] and f["path"][-1] in parent)
                    n += 1
                    continue
                try:
                    raw = resolve_q_pointer(p)
                except Exception as ex:  # noqa: BLE001
                    check("A.queue.resolve %s/%s" % (it["id"], k), False, repr(ex))
                    continue
                nd = p["from"].get("round")
                if not C.close(C.rnd(raw, nd), p["value"], nd):
                    check("A.queue.value %s/%s" % (it["id"], k), False, "packet %r vs queue %r" % (raw, p["value"]))
                n += 1
            # template slots and pointers agree
            slots = set(re.findall(r"\{(\w+)\}", e["t"]))
            check("A.queue.slots %s" % it["id"], slots == set(e["n"].keys()), "%s vs %s" % (sorted(slots), sorted(e["n"])))
    check("A.queue.pointers", n > 0, "%d pointers re-read" % n)


# ---------------------------------------------------------------------- B. SHAs and origin

ORIGIN_URL = "https://github.com/kvnloo/cua.git"
UPSTREAM_URL = "https://github.com/trycua/cua.git"


def ls_remote(url, refs):
    p = C.git("ls-remote", url, *refs, check=False)
    out = {}
    for line in p.stdout.splitlines():
        sha, ref = line.split("\t")
        out[ref] = sha
    return out, p.returncode


def check_shas(acc, q, offline):
    shas = set()
    for k, m in acc["packets"].items():
        shas.add(m["sha"])
    for it in q["items"]:
        s = it["fields"]["exact_sha"]
        if s.get("candidate"):
            shas.add(s["candidate"]["sha"])
            for c in s["candidate"].get("commits", []):
                shas.add(c)
                check("B.ancestor %s %s" % (it["id"], c[:9]),
                      C.git("merge-base", "--is-ancestor", c, s["candidate"]["sha"], check=False).returncode == 0)
        for p in s.get("packets", []):
            shas.add(p["sha"])
    for sha in sorted(shas):
        check("B.sha_exists %s" % sha[:9], C.sha_exists(sha) and len(sha) == 40)
    check("B.sha.count", True, "%d SHAs" % len(shas))
    if offline:
        skip("B.origin.accounting_packets", "--offline")
        return
    refs = ["refs/heads/" + m["branch"] for m in acc["packets"].values()]
    heads, rc = ls_remote(ORIGIN_URL, refs)
    check("B.ls_remote.rc", rc == 0)
    for k, m in acc["packets"].items():
        got = heads.get("refs/heads/" + m["branch"])
        check("B.origin.packet %s" % k, got == m["sha"], "%s @ %s (origin %s)" % (m["branch"], m["sha"][:9], (got or "absent")[:9]))
    # R2-10: summary blob identical at the published head and at the held privacy rewrite r1c
    a = C.git("rev-parse", "030f6bdbf811e124e11daa2de0569bffb993b66d:docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json").stdout.strip()
    b = C.git("rev-parse", "eaca68df9d7f4757028ba787f2e2fa82c92bafe7:docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json").stdout.strip()
    check("B.r2-10.summary_blob_same_at_r1c", a == b)


# -------------------------------------------------------------------------- C. renders

def check_renders(target):
    import make_accounting as MA  # noqa: E402
    import make_queue as MQ  # noqa: E402
    if target in ("10", "all"):
        acc = json.load(open(os.path.join(HERE, "accounting.json")))
        txt = open(os.path.join(HERE, "README.md")).read()
        gen = MA.render(acc)
        check("C.readme10.generated_section", gen in txt)
    if target in ("74", "all"):
        q = json.load(open(os.path.join(Q_DIR, "queue.json")))
        txt = open(os.path.join(Q_DIR, "README.md")).read()
        gen = MQ.render(q)
        check("C.readme74.generated_section", gen in txt)


# ------------------------------------------------------------- D. eight fields, no bare numbers

ALLOWED_NUM = [
    r"kvnloo/cua#\d+", r"trycua/cua (?:PR|issue) \d+", r"trycua/cua \d+", r"PR \d+",
    r"`[^`]*`",                                   # code spans (SHAs, branch names, paths)
    r"\b[0-9a-f]{7,40}\b",                        # bare SHAs
    r"\b[A-Za-z][A-Za-z_]*[-']?\d+[A-Za-z0-9'_]*(?:-[A-Za-z0-9']+)*\b",  # identifiers: R2-07d, OWN-20P, F1, I2d, S0, W2c
    r"\b(?:exp|docs)/[\w./-]+",                   # branch names
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\bwave[- ]\d+\b", r"\bDeviation \d+\b",       # labels, not measurements
    r"\b100 ms\b",                                # the named 100 ms insert_text settle (a Driver constant, B-01 H_T)
]


def bare_numbers(text):
    t = text
    for rx in ALLOWED_NUM:
        t = re.sub(rx, " ", t)
    return re.findall(r"\d+(?:\.\d+)?", t)


FIELDS = ["delta", "canonical_owner", "exact_sha", "completed_evidence", "missing_evidence", "action_type",
          "dependency", "stop_condition"]


def check_fields(q):
    ids = set()
    for it in q["items"]:
        check("D.unique_id %s" % it["id"], it["id"] not in ids)
        ids.add(it["id"])
        f = it["fields"]
        check("D.eight_fields %s" % it["id"], list(f.keys()) == FIELDS and all(f[k] not in (None, "", []) or
                                                                               k in ("completed_evidence",) for k in FIELDS))
        texts = [f["delta"], f["action_type"], f["stop_condition"], it["title"]] + list(f["missing_evidence"]) + \
            list(f["dependency"]) + list(f["canonical_owner"]) + [e["t"] for e in f["completed_evidence"]]
        s = f["exact_sha"]
        if s.get("candidate"):
            texts.append(s["candidate"].get("note", ""))
        for t in texts:
            nums = bare_numbers(t)
            if nums:
                check("D.no_bare_numbers %s" % it["id"], False, "%r in %r" % (nums, t[:120]))


# ------------------------------------------------------------------------- E. READY NOW

def check_ready_now(q, offline):
    import make_queue as MQ  # noqa: E402
    ext = json.load(open(os.path.join(Q_DIR, q["state_extract"])))
    acc_all = set(x for v in ext["accepted_by_wave"].values() for x in v)
    heads = {}
    prheads = {}
    if not offline:
        branches = sorted({r["branch"] for it in q["items"] for r in it["ready_now"]["published_on_origin"].get("refs", [])})
        heads, rc = ls_remote(ORIGIN_URL, ["refs/heads/" + b for b in branches])
        up, rc2 = ls_remote(UPSTREAM_URL, ["refs/pull/%d/head" % p["number"] for p in q["pr_pins"] if p["repo"] == "trycua/cua"])
        ok, rc3 = ls_remote(ORIGIN_URL, ["refs/pull/%d/head" % p["number"] for p in q["pr_pins"] if p["repo"] == "kvnloo/cua"])
        check("E.ls_remote.rc", rc == 0 and rc2 == 0 and rc3 == 0)
        for p in q["pr_pins"]:
            src = up if p["repo"] == "trycua/cua" else ok
            prheads[(p["repo"], p["number"])] = src.get("refs/pull/%d/head" % p["number"])
    covered = set()
    for it in q["items"]:
        g = it["ready_now"]
        gi = it["gate_inputs"]
        covered |= set(gi["owner"])
        lanes_ok = bool(gi["lanes"]) and all(l in acc_all for l in gi["lanes"])
        check("E.accepted_packet %s" % it["id"], g["accepted_packet"]["value"] == lanes_ok)
        for l in gi["lanes"]:
            if l in MQ.QP and l in ext["dispositions"]:
                d = ext["dispositions"][l]
                want = MQ.QP[l][1]
                have = {d.get("commit"), d.get("accepted_commit")} | set(ext["wave5_pushed_branches"].values())
                ok_c = any(isinstance(x, str) and x.startswith(want[:9]) for x in have)
                check("E.packet_commit_matches_state %s/%s" % (it["id"], l), ok_c)
        if not offline:
            refs = g["published_on_origin"].get("refs", [])
            for r in refs:
                got = heads.get("refs/heads/" + r["branch"])
                want_ok = (got is None) if r.get("expect") == "absent" else (got == r["sha"])
                check("E.published %s %s" % (it["id"], r["branch"]), want_ok == r["ok"] and r["ok"], "origin %s" % got)
            check("E.published.value %s" % it["id"], g["published_on_origin"]["value"] == (bool(refs) and all(r["ok"] for r in refs)))
            for p in g["pr_head_unchanged"].get("prs", []):
                live = prheads.get((p["repo"], p["number"]))
                check("E.pr_head %s %s %d" % (it["id"], p["repo"], p["number"]), live == p["pinned"] and p["ok"], "live %s" % live)
        if gi["drift"]:
            d = MQ.drift_check(gi["drift"])
            rec = g["recertified_or_drift_free"]
            check("E.drift %s" % it["id"], d["value"] == rec["value"] and d["intersection"] == rec["intersection"] and
                  d["drift_non_allowlisted"] == rec["drift_non_allowlisted"])
        else:
            check("E.drift_na %s" % it["id"], g["recertified_or_drift_free"]["value"] is True)
        odp = ext["owner_decisions_pending"]
        blk = ext["blocked_items_w5"]
        for x in g["no_pending_owner_decision"]["owner_decisions_pending"]:
            check("E.owner_ref %s #%d" % (it["id"], x["index"]), odp[x["index"]].startswith(x["head"]))
        owner_blk = [i for i in gi["blocked"] if "owner" in blk[i].lower()]
        check("E.no_owner %s" % it["id"], g["no_pending_owner_decision"]["value"] == (not gi["owner"] and not owner_blk))
        check("E.no_w6 %s" % it["id"], g["no_pending_w6_lane"]["value"] == (not gi["pending"]) and
              all(l in q["pending_w6"] for l in gi["pending"]))
        check("E.review %s" % it["id"], g["fresh_review_done"]["value"] is False)
        allv = all(g[k]["value"] for k in MQ.GATE_ORDER)
        check("E.READY_NOW %s" % it["id"], g["READY_NOW"] == allv)
    check("E.ready_now_count", q["ready_now_count"] == sum(1 for i in q["items"] if i["ready_now"]["READY_NOW"]))
    # F. every pending owner decision is covered
    missing = [i for i in range(len(ext["owner_decisions_pending"])) if i not in covered]
    check("F.owner_decisions_covered", not missing, "uncovered indices %s" % missing)
    # state extract against STATE.json (optional)
    sp = os.environ.get("CUA_LOOP_STATE")
    if sp:
        os.environ["CUA_LOOP_STATE"] = sp
        fresh = MQ.state_extract()
        if fresh["state_sha256"] != ext["state_sha256"]:
            skip("F.state_extract_current", "STATE.json changed since the extract (sha256 %s.. vs %s..); "
                 "the committed extract stays the input of record" % (fresh["state_sha256"][:12], ext["state_sha256"][:12]))
            stale_keys = [k for k in ("owner_decisions_pending", "blocked_items_w5", "accepted_by_wave") if fresh[k] != ext[k]]
            check("F.state_extract_gate_inputs_unchanged", not stale_keys, "changed: %s" % stale_keys)
        else:
            check("F.state_extract_current", fresh == ext)
    else:
        skip("F.state_extract_current", "CUA_LOOP_STATE not set")
    prov = json.load(open(os.path.join(HERE, "provenance.json")))
    check("F.provenance_state_sha", prov["inputs"]["state_sha256"] == ext["state_sha256"])


# ----------------------------------------------------------------------- G. autolinks

def rendered_texts(extra):
    files = [os.path.join(HERE, "README.md"), os.path.join(Q_DIR, "README.md")] + list(extra)
    return [(f, open(f).read()) for f in files if os.path.exists(f)]


def check_autolinks(extra):
    for f, txt in rendered_texts(extra):
        bad = C.autolink_findings(txt)
        check("G.autolinks %s" % os.path.basename(f), not bad, repr(bad[:5]))
    for f in (os.path.join(HERE, "accounting.json"), os.path.join(Q_DIR, "queue.json")):
        txt = open(f).read()
        bad = [x for x in C.autolink_findings(txt) if x[0] in ("upstream short ref", "upstream URL", "upstream commit ref")]
        check("G.upstream_links %s" % os.path.basename(f), not bad, repr(bad[:5]))


# ------------------------------------------------------------------------- H. privacy

SECRET = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[bap]-[A-Za-z0-9-]{10,}|"
                    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|(?i:api[_-]?key|secret|token)\s*[:=]\s*['\"][^'\"]{12,})")


def private_names():
    names = set()
    nf = os.environ.get("CUA_PRIVACY_NAMES_FILE")
    if nf and os.path.exists(nf):
        for line in open(nf):
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line)
    for n in (socket.gethostname().split(".")[0], getpass.getuser()):
        if n:
            names.add(n)
    return sorted(names), bool(nf and os.path.exists(nf))


def encodings(name):
    """Hex (both cases) and the alignment-independent cores of the base64 forms of a name."""
    b = name.encode()
    out = set()
    if len(b) >= 4:
        out |= {binascii.hexlify(b).decode(), binascii.hexlify(b).decode().upper()}
    for pad in range(3):
        e = base64.b64encode(b"\0" * pad + b).decode().rstrip("=")
        core = e[(pad * 4 + 2) // 3:][:-1]
        if len(core) >= 6:
            out.add(core)
    return sorted(out)


def scan_text(label, txt, names):
    hits = []
    for i, n in enumerate(names):
        if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(n), txt, re.I):
            hits.append("name#%d" % i)
        for e in encodings(n):
            if e in txt:
                hits.append("name#%d(encoded)" % i)
    if C.ABS_PATH.search(txt):
        hits.append("absolute-path")
    if SECRET.search(txt):
        hits.append("secret-like")
    return hits


def check_privacy(extra):
    names, have_file = private_names()
    if not have_file:
        skip("H.names_file", "CUA_PRIVACY_NAMES_FILE not set: host and user names only")
    files = []
    for root in (HERE, Q_DIR):
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d != "__pycache__"]
            for f in fn:
                files.append(os.path.join(dp, f))
    files += list(extra)
    for f in files:
        if f.endswith(".pyc"):
            continue
        txt = open(f, errors="replace").read()
        hits = scan_text(f, txt, names)
        check("H.tree %s" % os.path.relpath(f, RFC) if f.startswith(RFC) else "H.extra %s" % os.path.basename(f), not hits,
              ",".join(sorted(set(hits))))
    base = "5de1a37997e6c423899dd0a56aaa63bcf5abee8f"
    revs = [r for r in C.git("rev-list", "%s..HEAD" % base).stdout.split() if r]
    for r in revs:
        body = C.git("show", "--format=%an <%ae>%n%cn <%ce>%n%B", "-p", r).stdout
        hits = scan_text(r, body, names)
        check("H.commit %s" % r[:9], not hits, ",".join(sorted(set(hits))))
    check("H.commits.count", True, "%d commits scanned" % len(revs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["10", "74", "all"], default="all")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--extra-md", nargs="*", default=[])
    a = ap.parse_args()
    acc = json.load(open(os.path.join(HERE, "accounting.json")))
    q = json.load(open(os.path.join(Q_DIR, "queue.json")))
    if a.target in ("10", "all"):
        check_acc_pointers(acc)
    if a.target in ("74", "all"):
        check_queue_pointers(q)
        check_fields(q)
        check_ready_now(q, a.offline)
    check_shas(acc, q, a.offline)
    check_renders(a.target)
    check_autolinks(a.extra_md)
    check_privacy(a.extra_md)
    failed = [r for r in RESULTS if r[1] is False]
    skipped = [r for r in RESULTS if r[1] is None]
    print("verify_artifacts: %d checks, %d failed, %d skipped" % (len(RESULTS), len(failed), len(skipped)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
